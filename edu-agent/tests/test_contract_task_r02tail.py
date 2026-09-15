# -*- coding: utf-8 -*-
"""R02-tail TTFT 检索段优化契约测试。

覆盖面（全部 mock，不依赖 live Milvus/Neo4j/sidecar/GPU）：
  1. rerank sidecar 连接失败熔断：连接级失败触发冷却窗（RERANK_SIDECAR_COOLDOWN_S），
     窗内后续请求跳过 sidecar 直接进程内直连（attempt 计数不再增长），降级标签
     仍为 rerank_sidecar_unavailable（与既有失败回退语义一致）；冷却到期自动重试。
  2. 熔断可关（cooldown=0 → 逐请求尝试，现行为）。
  3. retrieve_three_channel 图谱通道与 Milvus 通道并行化：两通道产物均进 bundle、
     降级原因仍按 milvus→graph 固定顺序汇总；检索参数语义不变（hyde/top_k 透传）。
  4. sixnode.fan_out memory 召回与检索并行：recall 在检索结束前已启动（重叠执行），
     产物语义与串行版一致（成功→记忆摘要；失败→占位）。
"""
from __future__ import annotations

import asyncio
import time

import httpx
import pytest

import app.chat.retriever as retr
from app.chat.retriever import RetrievedDoc, _rerank_docs, retrieve_three_channel
from app.config import settings


def _doc(i: int) -> RetrievedDoc:
    return RetrievedDoc(
        doc_id=f"c{i}", score=0.5, content=f"内容{i}", source_file=None,
        content_type=None, series_code=None, series_name=None, module_codes=[],
        keywords=[], tenant_id=None, visibility=None, source_channel="hybrid",
    )


@pytest.fixture()
def breaker_reset(monkeypatch):
    """隔离熔断全局态：进出都清零，冷却窗参数固定。"""
    monkeypatch.setattr(retr, "_SIDECAR_FAIL_UNTIL", 0.0)
    monkeypatch.setattr(settings, "RERANK_SIDECAR_COOLDOWN_S", 60.0)
    yield
    retr._SIDECAR_FAIL_UNTIL = 0.0


def _mk_reranker_spy(scores):
    """假 Reranker.get()：恒返回给定分数（本地直连成功）。"""
    class _FakeRK:
        def __init__(self):
            self.calls = 0

        def rerank(self, query, contents, *, batch_size=None):
            self.calls += 1
            return list(scores)

    return _FakeRK()


@pytest.mark.asyncio
async def test_sidecar_breaker_skips_after_connect_failure(monkeypatch, breaker_reset):
    """连接失败 → 熔断；窗内第二次请求不再尝试 sidecar，本地直连兜底语义不变。"""
    import httpx as _hx

    attempts = {"n": 0}

    def _fail_post(self, url, **kw):
        attempts["n"] += 1
        raise _hx.ConnectError("connection refused", request=None)

    monkeypatch.setattr(_hx.AsyncClient, "post", _fail_post)
    rk = _mk_reranker_spy([0.9, 0.1])
    monkeypatch.setattr(retr.Reranker, "get", classmethod(lambda cls: rk))

    docs = [_doc(0), _doc(1)]
    out1, deg1 = await _rerank_docs("q", docs)
    assert attempts["n"] == 1                      # 首次：尝试了 sidecar
    assert [d.doc_id for d in out1] == ["c0", "c1"]  # 本地分数重排（0.9>0.1 保序）
    assert deg1 == "rerank_sidecar_unavailable"    # 降级标签与既有失败回退一致
    assert retr._sidecar_breaker_open()            # 熔断已开启

    out2, deg2 = await _rerank_docs("q", [_doc(0), _doc(1)])
    assert attempts["n"] == 1                      # 冷却窗内：不再尝试 sidecar
    assert [d.doc_id for d in out2] == ["c0", "c1"]
    assert deg2 == "rerank_sidecar_unavailable"    # 语义同「sidecar 失败回退本地」


@pytest.mark.asyncio
async def test_sidecar_breaker_expires_and_retries(monkeypatch, breaker_reset):
    """冷却到期 → 自动重试 sidecar（自愈，不丧失 sidecar 优先级）。"""
    retr._SIDECAR_FAIL_UNTIL = time.time() - 1.0   # 已过期
    assert not retr._sidecar_breaker_open()

    ok = {"hit": False}

    async def _fake_sidecar(query, contents):
        ok["hit"] = True
        return [1.0, 0.0]

    monkeypatch.setattr(retr, "_rerank_via_sidecar", _fake_sidecar)
    out, deg = await _rerank_docs("q", [_doc(0), _doc(1)])
    assert ok["hit"]                               # sidecar 恢复 → 正常走 sidecar
    assert deg is None                             # 不标降级
    assert [d.doc_id for d in out] == ["c0", "c1"]


@pytest.mark.asyncio
async def test_sidecar_breaker_disabled_when_cooldown_zero(monkeypatch, breaker_reset):
    """RERANK_SIDECAR_COOLDOWN_S=0 → 熔断关闭，逐请求尝试（现行为兼容）。"""
    monkeypatch.setattr(settings, "RERANK_SIDECAR_COOLDOWN_S", 0.0)

    def _fail_post(self, url, **kw):
        raise httpx.ConnectError("refused", request=None)

    monkeypatch.setattr(httpx.AsyncClient, "post", _fail_post)
    rk = _mk_reranker_spy([0.5])
    monkeypatch.setattr(retr.Reranker, "get", classmethod(lambda cls: rk))
    await _rerank_docs("q", [_doc(0)])
    await _rerank_docs("q", [_doc(0)])
    assert not retr._sidecar_breaker_open()        # 失败不熔断


@pytest.mark.asyncio
async def test_retrieve_three_channel_parallel_channels_and_degrade_order(monkeypatch):
    """图谱通道与 Milvus 通道并行：两通道产物均进 bundle；降级原因 milvus→graph 顺序不变。

    用 asyncio.Event 让 _graph_expand 在 Milvus 仍在飞时即被调度（并行证据：
    graph 在 milvus 完成前启动），并断言 bundle 完整性与 degrade 拼接顺序。
    """
    milvus_done = asyncio.Event()
    graph_started_while_milvus_flying = {"v": False}

    def _fake_milvus_safe(query, *, user_id, role, top_k):
        time.sleep(0.05)                            # 模拟远端耗时
        milvus_done.set()
        return [_doc(0), _doc(1)], "Milvus 降级标记"

    async def _fake_graph_expand(query, *, enable_graph, top_k_keywords=5):
        if not milvus_done.is_set():
            graph_started_while_milvus_flying["v"] = True
        await asyncio.sleep(0.01)
        from app.chat.schemas import GraphEntity

        return [GraphEntity(entity_type="Keyword", entity_name="X", related=["Y"], hop=1)], "Neo4j 降级标记"

    async def _fake_rerank(query, docs):
        return docs, None

    monkeypatch.setattr(retr, "_milvus_hybrid_search_safe", _fake_milvus_safe)
    monkeypatch.setattr(retr, "_graph_expand", _fake_graph_expand)
    monkeypatch.setattr(retr, "_rerank_docs", _fake_rerank)
    monkeypatch.setattr(retr, "_maybe_shadow", lambda *a, **k: None)

    bundle = await retrieve_three_channel(
        "线性代数 特征值", user_id=2, role=None,
        use_hyde=True, enable_graph=True, top_k=12, final_max_k=5, cutoff_drop_ratio=0.40,
    )
    assert graph_started_while_milvus_flying["v"] is True      # 并行（graph 先于 milvus 完成启动）
    assert [d.doc_id for d in bundle.docs] == ["c0", "c1"]     # docs 来自 Milvus 通道
    assert bundle.graph_entities[0].entity_name == "X"         # graph_entities 来自图谱通道
    assert bundle.raw_retrieved_count == 2
    # 降级顺序恒 milvus→graph（契约：degrade_parts 组装顺序不随并行完成顺序漂移）
    assert bundle.degraded_reason == "Milvus 降级标记；Neo4j 降级标记"


@pytest.mark.asyncio
async def test_sixnode_fanout_memory_parallel_with_retrieval(monkeypatch):
    """fan_out：memory 召回与三通道检索重叠执行（recall 启动早于检索结束），产物语义不变。"""
    from langchain_core.messages import HumanMessage

    import app.ai.harness.sixnode as sx
    import app.chat.retriever as retr_mod
    from app.ai.harness.sixnode import SixNodeHarness

    marks = {"ret_end": None, "mem_start": None}

    class _FakeBundle:
        docs = [_doc(0)]
        graph_entities = []
        raw_retrieved_count = 1
        rewrite_query = None
        degraded_reason = None

    async def _fake_retrieve(query, **kw):
        await asyncio.sleep(0.05)
        marks["ret_end"] = time.perf_counter()
        return _FakeBundle()

    async def _fake_recall(user_id, query, top_k=3):
        marks["mem_start"] = time.perf_counter()
        await asyncio.sleep(0.05)
        return [{"content": "用户偏好雅思听力"}]

    monkeypatch.setattr(retr_mod, "retrieve_three_channel", _fake_retrieve)

    import app.ai.memory.service as memsvc

    monkeypatch.setattr(memsvc, "recall_topk", _fake_recall)

    state = {
        "messages": [HumanMessage(content="什么是特征值？")],
        "user_id": 2,
        "intent": "knowledge",
        "tasks": [],
    }
    out = await SixNodeHarness().fan_out(state)
    assert marks["mem_start"] < marks["ret_end"]   # 并行重叠（串行版 recall 恒在检索后启动）
    summaries = [d["summary"] for d in out["subagent_results"]]
    assert any("特征值" in s or "来源" in s for s in summaries)   # search 摘要
    assert any("用户记忆" in s for s in summaries)               # memory 摘要（产物语义不变）
    assert out["retrieval"]["retrieved_count"] == 1
