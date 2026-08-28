# -*- coding: utf-8 -*-
"""P1-4 性能优化单测：Milvus 超时降级、检索兜底、jieba 幂等缓存。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.chat import retriever
from app.chat.retriever import RetrievalBundle
from app.knowledge.importer import embedder


# ============================================================
# 1. Milvus 检索超时降级（asyncio.wait_for + to_thread）
# ============================================================
@pytest.mark.asyncio
async def test_milvus_timeout_degrades(monkeypatch):
    """Milvus 检索超过 MILVUS_SEARCH_TIMEOUT → 返回空 docs + degraded，不阻塞 event loop。"""
    # 注意：_milvus_hybrid_search_safe 是被 asyncio.to_thread 调用 → mock 需为同步函数
    def slow_safe(*a, **kw):
        time.sleep(0.3)  # 模拟慢（远超测试用短超时）
        return [], None

    monkeypatch.setattr(retriever, "_milvus_hybrid_search_safe", slow_safe)
    monkeypatch.setattr(retriever.settings, "MILVUS_SEARCH_TIMEOUT", 0.1)
    # 其他通道直接跳过
    monkeypatch.setattr(retriever, "_rewrite_query_by_hyde_if_enabled", lambda q, use_hyde: (q, False, None))
    monkeypatch.setattr(retriever, "_graph_expand", lambda *a, **kw: ([], None))
    monkeypatch.setattr(retriever, "_rule_rerank", lambda q, docs: docs)
    monkeypatch.setattr(retriever, "_cliff_cutoff", lambda docs, final_max_k, drop_ratio: docs)

    bundle = await retriever.retrieve_three_channel(
        "测试", user_id=1, role="student",
        use_hyde=False, enable_graph=False, top_k=5, final_max_k=3, cutoff_drop_ratio=0.3,
    )
    assert isinstance(bundle, RetrievalBundle)
    assert bundle.docs == []
    assert bundle.degraded_reason and "超时" in bundle.degraded_reason


@pytest.mark.asyncio
async def test_milvus_fast_returns_docs(monkeypatch):
    """Milvus 正常时返回 docs，无 degraded。"""
    from app.chat.schemas import RetrievedDoc

    doc = RetrievedDoc(doc_id="d1", score=0.9, content="内容")
    def fast_safe(*a, **kw):
        return [doc], None

    monkeypatch.setattr(retriever, "_milvus_hybrid_search_safe", fast_safe)
    monkeypatch.setattr(retriever.settings, "MILVUS_SEARCH_TIMEOUT", 5.0)
    monkeypatch.setattr(retriever, "_rewrite_query_by_hyde_if_enabled", lambda q, use_hyde: (q, False, None))
    monkeypatch.setattr(retriever, "_graph_expand", lambda *a, **kw: ([], None))

    # task31 后 _rerank_docs 已改为 async def；隔离重排阶段需用 async fake，
    # 否则 line498 `await _rerank_docs(...)` 会因「await 一个 tuple」而 TypeError（GWT③ 真实失配修复）
    async def _fake_rerank(q, docs):
        return (docs, None)

    monkeypatch.setattr(retriever, "_rerank_docs", _fake_rerank)
    monkeypatch.setattr(retriever, "_rule_rerank", lambda q, docs: docs)
    monkeypatch.setattr(retriever, "_cliff_cutoff", lambda docs, final_max_k, drop_ratio: docs)

    bundle = await retriever.retrieve_three_channel(
        "测试", user_id=1, role="student",
        use_hyde=False, enable_graph=False, top_k=5, final_max_k=3, cutoff_drop_ratio=0.3,
    )
    assert len(bundle.docs) == 1
    assert bundle.docs[0].doc_id == "d1"
    assert bundle.degraded_reason is None


# ============================================================
# 2. jieba 幂等缓存（不再每次读文件）
# ============================================================
def test_jieba_resources_idempotent():
    """连续调用只初始化一次，停用词缓存复用。"""
    s1, ok1 = embedder.ensure_jieba_ready()
    s2, ok2 = embedder.ensure_jieba_ready()
    assert ok1 == ok2
    assert s1 == s2  # 缓存一致


# ============================================================
# 3. loader.hybrid_search 签名含 timeout
# ============================================================
def test_hybrid_search_has_timeout_param():
    import inspect

    from app.knowledge.importer.loader import hybrid_search
    sig = inspect.signature(hybrid_search)
    assert "timeout" in sig.parameters
    assert sig.parameters["timeout"].default == 8.0
