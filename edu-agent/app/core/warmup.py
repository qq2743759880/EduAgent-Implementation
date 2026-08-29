# -*- coding: utf-8 -*-
"""task39 GWT③：冷启动预热（BGE-M3 / Reranker / 云端 embedding 连接池）。

背景（task-VEC/31 批判②）：
    main.py 旧实现 ``_warmup_local_models()`` 无条件加载本地 BGE-M3，存在两个问题：
      1. **与 EMBED_BACKEND=cloud 冲突**：``embedder.encode_dense_batch`` 云端优先，
         本地 BGE-M3 只是失败回退路径。无条件预加载会白占 1~2GB 显存 + 数十秒启动时间，
         正是 doc-architect-tech-arch.md §7 薄弱点 3「多 worker 重复加载本地模型 → OOM」的成因。
      2. **Reranker 完全没进预热链**：sidecar(8601) 自己预热了自己，但主应用的
         进程内回退路径（``Reranker.get()``）是冷的。sidecar 一旦不可达，
         首次检索要同步加载 ~2GB reranker（实测 10.9s），远超 GWT 的 3s 红线。

设计（后端感知预热，不牺牲显存）：
    - ``jieba``         ：无条件（纯 CPU，几十 ms，成本可忽略）
    - ``cloud_embed``   ：EMBED_BACKEND=cloud 时，发 1 条极小 embedding 请求，
                          预热 TLS 握手 + 连接池 + token bucket（实测首个请求的大头常在这）
    - ``bge_m3``        ：**仅当本地模型在主链路上**（EMBED_BACKEND=cuda）才预加载
    - ``reranker_sidecar``：HTTP 预热 sidecar（不占本进程显存，首选路径）
    - ``reranker_local``  ：**仅当 sidecar 不可达**才加载进程内 reranker（保底首请求 <3s）

可观测：``GET /health/warmup`` 返回每个组件的耗时/成败；``/health/detail`` 带 ``warmup`` 段。
预热在 lifespan 中以后台任务执行，不阻塞启动；失败只标记 degraded，绝不阻断服务。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from app.config import settings


# 预热状态（进程级单例，供 /health/warmup 读取）
_state: dict[str, Any] = {
    "status": "pending",  # pending | running | ready | degraded
    "started_at": None,
    "finished_at": None,
    "elapsed_ms": None,
    "components": {},
}
_state_lock = asyncio.Lock()
_ready = asyncio.Event()


def snapshot() -> dict[str, Any]:
    """返回预热状态快照（只读副本，供健康检查/压测断言）。"""
    return {
        "status": _state["status"],
        "started_at": _state["started_at"],
        "finished_at": _state["finished_at"],
        "elapsed_ms": _state["elapsed_ms"],
        "components": dict(_state["components"]),
    }


async def wait_ready(timeout: float | None = None) -> bool:
    """等待预热完成（压测/冒烟用）。超时返回 False。"""
    try:
        await asyncio.wait_for(_ready.wait(), timeout=timeout)
        return True
    except (asyncio.TimeoutError, TimeoutError):
        return False


def _record(name: str, ok: bool, elapsed_ms: float, detail: str = "") -> None:
    _state["components"][name] = {
        "ok": ok,
        "elapsed_ms": round(elapsed_ms, 1),
        "detail": detail[:300],
    }
    level = "INFO" if ok else "WARNING"
    logger.log(
        level,
        f"[预热] {name} {'完成' if ok else '失败/跳过'} {elapsed_ms:.0f}ms"
        + (f" — {detail[:200]}" if detail else ""),
    )


# ──────────────────────────────────────────────────────────────
# 各组件预热体（全部同步阻塞型，由 asyncio.to_thread 承载，不卡事件循环）
# ──────────────────────────────────────────────────────────────
def _warm_jieba() -> tuple[bool, str]:
    from app.knowledge.importer import embedder

    if not hasattr(embedder, "ensure_jieba_ready"):
        return False, "embedder 无 ensure_jieba_ready（跳过）"
    embedder.ensure_jieba_ready()
    return True, "jieba 词典 + 停用词已加载"


def _warm_bge_local() -> tuple[bool, str]:
    """仅本地优先时预加载 BGE-M3（cloud 模式下跳过，避免白占显存）。"""
    from app.knowledge.importer import embedder

    model = embedder._get_bge_model()  # noqa: SLF001 — 主动预热，失败内部已降级
    if model is None:
        return False, "BGE-M3 本地不可用（云端/哈希兜底生效）"
    return True, f"BGE-M3 已加载 device={getattr(settings, 'EMBED_DEVICE', '?')}"


def _warm_cloud_embed() -> tuple[bool, str]:
    """云端 embedding 预热：1 条极小请求，打通 TLS/连接池。"""
    from app.knowledge.importer import embedder

    if not hasattr(embedder, "_api_embed_batch"):
        return False, "embedder 无 _api_embed_batch（跳过）"
    try:
        vecs = embedder._api_embed_batch(["warmup"])  # noqa: SLF001
        if not vecs or not vecs[0]:
            return False, "云端 embedding 返回空向量"
        return True, f"云端 embedding 就绪 dim={len(vecs[0])}"
    except Exception as exc:  # noqa: BLE001 — 预热失败不阻断服务
        return False, f"{type(exc).__name__}: {exc}"


def _warm_reranker_local() -> tuple[bool, str]:
    """进程内 reranker 预加载（仅 sidecar 不可达时的保底路径）。"""
    from app.knowledge.reranker import Reranker

    rk = Reranker.get()
    scores = rk.rerank("warmup", ["warmup"])
    if scores is None:
        return False, f"进程内 reranker 不可用: {rk.load_error or 'unknown'}"
    return True, f"进程内 reranker 已加载 device={getattr(settings, 'RERANKER_DEVICE', '?')}"


def _warm_reranker_sidecar() -> tuple[bool, str]:
    """HTTP 预热 sidecar（8601）：不占本进程显存，走一次真实前向。"""
    import httpx

    url = str(getattr(settings, "RERANK_SERVICE_URL", "http://127.0.0.1:8601")).rstrip("/") + "/rerank"
    with httpx.Client(timeout=15.0, trust_env=False, proxy=None) as client:
        resp = client.post(url, json={"query": "warmup", "contents": ["warmup"]})
    if resp.status_code != 200:
        return False, f"sidecar 返回 {resp.status_code}"
    return True, f"rerank sidecar 已预热 {url}"


# ──────────────────────────────────────────────────────────────
# 编排
# ──────────────────────────────────────────────────────────────
async def run_warmup() -> dict[str, Any]:
    """执行全量预热（幂等：重复调用直接返回上次结果）。"""
    if _state["status"] in ("ready", "degraded"):
        return snapshot()

    async with _state_lock:
        if _state["status"] in ("ready", "degraded"):
            return snapshot()
        _state["status"] = "running"
        _state["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        t0 = time.perf_counter()

        cloud_first = str(getattr(settings, "EMBED_BACKEND", "cloud") or "cloud").lower() != "cuda"
        _record("embed_backend", True, 0.0,
                "cloud-first（本地 BGE 仅回退）" if cloud_first else "cuda-first（本地 BGE 主链路）")

        # 1) jieba：无条件（纯 CPU）
        await _run("jieba", _warm_jieba)

        # 2) 稠密向量：按后端策略二选一，不双份占显存
        if cloud_first:
            await _run("cloud_embed", _warm_cloud_embed)
            _record("bge_m3", True, 0.0, "skipped：EMBED_BACKEND=cloud，本地模型非主链路（按需懒加载）")
        else:
            await _run("bge_m3", _warm_bge_local)

        # 3) reranker：sidecar 优先（不占本进程显存），不可达才落本地
        ok, detail = await _run("reranker_sidecar", _warm_reranker_sidecar)
        if ok:
            _record("reranker_local", True, 0.0, "skipped：sidecar 可用，避免重复占显存（§7 薄弱点 3）")
        else:
            await _run("reranker_local", _warm_reranker_local)

        _state["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        _state["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        # 判定：任一「必选组件」失败 → degraded；skip 类（ok=True）不影响
        failed = [n for n, c in _state["components"].items() if not c["ok"]]
        _state["status"] = "degraded" if failed else "ready"
        logger.info(
            f"[预热] 完成 status={_state['status']} "
            f"elapsed={_state['elapsed_ms']}ms failed={failed or 'none'}"
        )
        _ready.set()
        return snapshot()


async def _run(name: str, fn) -> tuple[bool, str]:
    """跑一个同步预热体，记录耗时与结果（异常一律降级不抛出）。"""
    t = time.perf_counter()
    try:
        ok, detail = await asyncio.to_thread(fn)
    except Exception as exc:  # noqa: BLE001 — 预热永远不阻断服务
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    _record(name, ok, (time.perf_counter() - t) * 1000, detail)
    return ok, detail
