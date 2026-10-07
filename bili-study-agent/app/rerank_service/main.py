# -*- coding: utf-8 -*-
"""
task-R1 Rerank sidecar（FastAPI 独立进程）。

- POST /rerank  body {query, contents:[str], batch_size?} → {scores:[float], latency_ms}
- GET  /health  → {model_loaded, device, gpu_mem_mb, batch_count, request_count}
- 复用 task31 的 Reranker.rerank_pairs 做推理（模型加载/批处理/降级不变），进程内单例天然隔离 GPU 阻塞。

启动：uvicorn app.rerank_service.main:app --port 8601
主应用与 sidecar 独立部署（systemd/进程管理器各管一个），主应用经 HTTP 调用（见 app/chat/retriever.py）。
"""
from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.rerank_service.batcher import BatchClosed, ContinuousBatcher


# ----------------------------------------------------------------------
# 请求/响应模型
# ----------------------------------------------------------------------
class RerankReq(BaseModel):
    query: str
    contents: list[str]
    batch_size: int | None = Field(None, description="保留兼容字段，连续批处理在 sidecar 端统一调度")


class RerankResp(BaseModel):
    scores: list[float]
    latency_ms: float


class HealthResp(BaseModel):
    model_loaded: bool
    device: str
    gpu_mem_mb: float
    batch_count: int
    request_count: int
    rejected_count: int


# ----------------------------------------------------------------------
# 推理函数（复用 task31 Reranker）
# ----------------------------------------------------------------------
def _infer_pairs(pairs: list[tuple[str, str]]) -> list[float]:
    """sidecar 实际推理：扁平对 → 分数（Reranker 单例，进程内隔离 GPU）。"""
    from app.knowledge.reranker import Reranker

    return Reranker.get().rerank_pairs(pairs)


def build_batcher(infer_fn=None) -> ContinuousBatcher:
    """构造按配置初始化的 batcher（可注入 fake 用于测试）。"""
    return ContinuousBatcher(
        infer_fn or _infer_pairs,
        window_ms=settings.RERANK_BATCH_WINDOW_MS,
        max_batch_pairs=settings.RERANK_MAX_BATCH_PAIRS,
        max_wait_ms=settings.RERANK_MAX_WAIT_MS,
        max_queue=settings.RERANK_QUEUE_MAX,
    )


# ----------------------------------------------------------------------
# 处理器（可单测，不依赖事件循环/HTTP 生命周期）
# ----------------------------------------------------------------------
async def _handle_rerank(req: RerankReq, batcher: ContinuousBatcher) -> RerankResp:
    if not req.contents:
        return RerankResp(scores=[], latency_ms=0.0)
    t0 = time.perf_counter()
    try:
        scores = await batcher.submit(req.query, req.contents)
    except BatchClosed as exc:
        # 队列满 / 推理失败 → 503，主应用据此走降级链（AC4）
        raise HTTPException(status_code=503, detail=str(exc))
    latency_ms = (time.perf_counter() - t0) * 1000.0
    return RerankResp(scores=scores, latency_ms=latency_ms)


def _gpu_mem_mb() -> float:
    try:
        import torch

        if torch.cuda.is_available():
            return float(torch.cuda.memory_allocated()) / (1024 * 1024)
    except Exception:
        pass
    return 0.0


async def _handle_health(batcher: ContinuousBatcher) -> HealthResp:
    from app.knowledge.reranker import Reranker

    rk = Reranker.get()
    return HealthResp(
        model_loaded=rk._model is not None,
        device=settings.RERANKER_DEVICE,
        gpu_mem_mb=_gpu_mem_mb(),
        batch_count=batcher.batch_count,
        request_count=batcher.request_count,
        rejected_count=batcher.rejected_count,
    )


# ----------------------------------------------------------------------
# FastAPI 应用
# ----------------------------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(title="EduAgent Rerank Sidecar", version="1.0")
    _batcher = build_batcher()

    @app.on_event("startup")
    async def _startup() -> None:
        _batcher.start()
        # 预热：触发模型加载（task39 冷启动预热），失败仅记警告，/health 仍可用
        try:
            from app.knowledge.reranker import Reranker

            Reranker.get().rerank("warmup", ["warmup"])
        except Exception as exc:  # noqa: BLE001
            import loguru

            loguru.logger.warning(f"[rerank-sidecar] 预热失败（不影响启动）：{exc}")

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await _batcher.stop()

    @app.post("/rerank", response_model=RerankResp)
    async def rerank(req: RerankReq):
        return await _handle_rerank(req, _batcher)

    @app.get("/health", response_model=HealthResp)
    async def health():
        return await _handle_health(_batcher)

    return app


app = create_app()
