# -*- coding: utf-8 -*-
"""
task31 RAG reranker - bge-reranker-v2-m3 本地化重排（tech-source-audit 三，零 API 成本）。

职责（对应 GWT ①）：
- 懒加载单例：进程内只加载一次模型，避免多 worker/请求重复加载撑爆显存（薄弱点 W3：OOM 缓解）。
- 失败返回 None：GPU 不可用 / 模型缺失 / 加载或推理异常 → 返回 None，调用方回退 `_rule_rerank`，
  并置 degraded_reason="reranker_unavailable"（GWT② 降级，质量不劣于现状）。
- 按 batch_size=RERANKER_BATCH_SIZE(16) 分批，避免一次喂 150 对 token 超限。

实现说明（transformers 5.x 兼容修复）：
  任务文档按 FlagReranker + compute_score 设计。但实测 FlagReranker 的 compute_score 内部调用
  tokenizer.prepare_for_model(...)（site-packages/FlagEmbedding/inference/reranker/encoder_only/base.py:147），
  该 API 在 transformers 5.x 已移除 → 一律 AttributeError → 永久降级（task31 实证首跑即如此）。
  因此直接用同款模型 AutoTokenizer + AutoModelForSequenceClassification 重写打分（batch 多对编码，
  与 FlagReranker 语义等价、效果一致），保留相同的外部契约（懒加载单例 / 返回 None / 降级）。

懒加载-once：首次 `rerank` 触发加载；加载失败记入 `_load_error`，后续调用直接返回 None（不再反复
尝试加载，避免每请求 OOM 重试拖垮进程）。
"""
from __future__ import annotations

import threading
from pathlib import Path

from loguru import logger

from app.config import settings


class Reranker:
    """本地 bge-reranker-v2-m3 重排器（OLP 线程安全懒加载单例）。"""

    _instance: "Reranker | None" = None
    _lock = threading.Lock()

    # ------------------------------------------------------------------
    @classmethod
    def get(cls) -> "Reranker":
        """取全局单例（线程安全懒创建）。"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ------------------------------------------------------------------
    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None
        self._load_error: str | None = None  # None=未尝试或成功；非 None=加载失败（不再重试）
        self._last_error: str | None = None  # 最近一次推理错误

    # ------------------------------------------------------------------
    def _load(self) -> None:
        """懒加载-once：仅当尚未尝试且模型路径存在时加载；失败记录 _load_error。"""
        if self._load_error is not None or self._model is not None:
            return
        model_dir = Path(getattr(settings, "RERANKER_PATH", "") or "")
        if not model_dir.exists():
            self._load_error = f"reranker 模型目录不存在: {model_dir}"
            logger.warning(f"[reranker] {self._load_error}")
            return
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            device = getattr(settings, "RERANKER_DEVICE", "cuda")
            self._tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
            self._model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
            # R1-①：按 RERANKER_PRECISION 选择精度。fp16（默认）= .half() 省显存；
            # fp32 = 跳过 .half()，分数噪声 < 1e-4，跨请求批处理排序更稳定。
            precision = getattr(settings, "RERANKER_PRECISION", "fp16")
            if precision == "fp16" and device != "cpu" and torch.cuda.is_available():
                self._model = self._model.half().to(device)  # fp16 省显存 + 加速
            else:
                self._model = self._model.to(device)  # fp32 / CPU：不 .half()
            self._model.eval()
            logger.info(f"[reranker] 模型已加载 device={device}（{self._tokenizer.__class__.__name__}）")
        except Exception as exc:  # noqa: BLE001 - 任何加载失败都降级，绝不 500
            self._load_error = f"reranker 加载失败: {type(exc).__name__}: {exc}"
            self._model = None
            self._tokenizer = None
            logger.warning(f"[reranker] {self._load_error}")

    # ------------------------------------------------------------------
    def rerank(
        self,
        query: str,
        contents: list[str],
        *,
        batch_size: int | None = None,
    ) -> list[float] | None:
        """对 query×contents 逐对打分，返回与 contents 对齐的分数列表。

        每对 = (query, content)，用 AutoModelForSequenceClassification 双句分类打分。
        Batch 编码（text= queries, text_pair= passages）兼容 transformers 5.x；
        单次批量 = batch_size=RERANKER_BATCH_SIZE(16)，超长分批，控制峰值显存。
        返回 None = reranker 不可用（调用方须用 _rule_rerank 兜底）。
        """
        if not contents:
            return []
        self._load()
        if self._model is None:
            return None
        try:
            import torch

            bsz = max(1, int(batch_size if batch_size is not None else settings.RERANKER_BATCH_SIZE))
            all_scores: list[float] = []
            device = next(self._model.parameters()).device
            for i in range(0, len(contents), bsz):
                queries = [query] * bsz if (bsz <= len(contents)) else [query] * len(contents)
                passages = contents[i : i + bsz]
                queries = queries[: len(passages)]
                inputs = self._tokenizer(
                    text=queries,
                    text_pair=passages,
                    return_tensors="pt",
                    truncation=True,
                    padding=True,
                    max_length=int(getattr(settings, "RERANKER_MAX_LENGTH", 512)),
                )
                inputs = {k: v.to(device) for k, v in inputs.items()}
                with torch.no_grad():
                    logits = self._model(**inputs, return_dict=True).logits.view(-1,).float()
                all_scores.extend(float(s) for s in logits.cpu().tolist())
            self._last_error = None
            return all_scores
        except Exception as exc:  # noqa: BLE001 - 推理失败降级，不 500
            self._last_error = f"reranker 推理失败: {type(exc).__name__}: {exc}"
            logger.warning(f"[reranker] {self._last_error}")
            return None

    @property
    def load_error(self) -> str | None:
        return self._load_error or self._last_error

    # ------------------------------------------------------------------
    def rerank_pairs(self, pairs: list[tuple[str, str]]) -> list[float] | None:
        """对扁平 (query, content) 对列表批量打分，返回与 pairs 对齐的分数列表。

        供 task-R1 sidecar **跨请求连续批处理**复用：把多个请求的 (query, content) 对
        拼接成一条大 batch 一次前向。每个对是独立序列（无跨对注意力），分数只取决于
        该 (query, content)，故合并跨请求不改变单对分数。

        一致性（AC1）：对单请求，rerank_pairs([(query, c) for c in contents]) 与
        rerank(query, contents) 分批方式完全一致（同样按 RERANKER_BATCH_SIZE 分组、
        同样 text=[query]*n / text_pair=contents 构造），分数逐位相等。
        返回 None = reranker 不可用（调用方走降级）。
        """
        if not pairs:
            return []
        self._load()
        if self._model is None:
            return None
        try:
            import torch

            bsz = max(1, int(getattr(settings, "RERANKER_BATCH_SIZE", 16)))
            all_scores: list[float] = []
            device = next(self._model.parameters()).device
            for i in range(0, len(pairs), bsz):
                batch = pairs[i : i + bsz]
                queries = [q for q, _ in batch]
                passages = [c for _, c in batch]
                inputs = self._tokenizer(
                    text=queries,
                    text_pair=passages,
                    return_tensors="pt",
                    truncation=True,
                    padding=True,
                    max_length=int(getattr(settings, "RERANKER_MAX_LENGTH", 512)),
                )
                inputs = {k: v.to(device) for k, v in inputs.items()}
                with torch.no_grad():
                    logits = self._model(**inputs, return_dict=True).logits.view(-1,).float()
                all_scores.extend(float(s) for s in logits.cpu().tolist())
            self._last_error = None
            return all_scores
        except Exception as exc:  # noqa: BLE001 - 推理失败降级，不 500
            self._last_error = f"reranker 推理失败: {type(exc).__name__}: {exc}"
            logger.warning(f"[reranker] {self._last_error}")
            return None