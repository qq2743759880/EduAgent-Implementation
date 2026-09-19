# -*- coding: utf-8 -*-
"""W-NEXT-FUSIONBLIND-001（R20-min Crit-2 承接：融合层对 dense 故障失明）注入测试。

Crit-2 实证：本地 BGE 缺失 + DashScope 429 → encode 静默退化 sha256 伪向量，dense 通道
空转、稀疏通道补偿 → hit_rate 照常产出无报警（可观测性盲区）。

本套件在故障真实发生点注入（mock encode_dense_batch_detailed / _milvus_hybrid_search，
让真实 _milvus_hybrid_search_safe 代码路径执行，非整段换桩），逐态断言：
  ① channel_health 显式标记（dense failed/idle + 原因，只增不改既有字段语义）
  ② WARN 带通道名+原因；连续 N 次失败升级 ERROR（RETRIEVER_CHANNEL_FAIL_ERROR_N）
  ③ 主链不崩（恒返回 RetrievalBundle）；空转态稀疏兜底结果仍可用
三态映射：抛错→dense failed；超时→dense failed(timeout)；返回空→hybrid empty / 空转→dense idle。
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from loguru import logger

from app.auth import UserRole
from app.chat import retriever as R
from app.chat.retriever import RetrievalBundle
from app.config import settings as st
from app.knowledge.importer.embedder import DenseResult

RETRIEVE_KW = dict(user_id=1, role=UserRole.STUDENT, use_hyde=False,
                   enable_graph=False, top_k=5, final_max_k=5, cutoff_drop_ratio=0.40)


@pytest.fixture(autouse=True)
def _reset_streak():
    """连续失败计数是模块级全局态——逐用例清零防串扰。"""
    R._CHANNEL_FAIL_STREAK.clear()
    yield
    R._CHANNEL_FAIL_STREAK.clear()


@pytest.fixture()
def cap_logs():
    """loguru 捕获：条目形如 'LEVEL|message'。"""
    records: list[str] = []

    def _sink(msg):
        records.append(str(msg))

    hid = logger.add(_sink, format="{level.name}|{message}", level="INFO")
    yield records
    logger.remove(hid)


def _warns(records: list[str], channel: str = "dense") -> list[str]:
    return [r for r in records if r.startswith("WARNING|") and f"channel={channel} FAILED" in r]


def _errors(records: list[str], channel: str = "dense") -> list[str]:
    return [r for r in records if r.startswith("ERROR|") and f"channel={channel} FAILED" in r]


def _ok_encoder(texts):
    return DenseResult(
        vectors=[[0.1] * st.EMBEDDING_DIM for _ in texts],
        backend="bge_m3", normalized=True, precision="fp32",
        embedding_model="test-bge-m3", max_length=8192,
    )


def _sha_encoder(texts):
    return DenseResult(
        vectors=[[0.2] * st.EMBEDDING_DIM for _ in texts],
        backend="sha256", normalized=True, precision="fp32",
        embedding_model="sha256-pseudo", max_length=None,
    )


def _milvus_rows(*ids: str) -> list[dict]:
    return [
        {"chunk_id": i, "score": 0.9, "content": f"content-{i}", "source_file": "f.md",
         "content_type": "question", "tags": [], "module_codes": [], "tenant_id": "_default",
         "series_code": None, "series_name": None, "visibility": None}
        for i in ids
    ]


def _install_common(monkeypatch):
    """隔离图通道与重排（本套件聚焦 dense/sparse 注入，不触真实 Neo4j/reranker）。"""

    async def _graph_noop(*a, **kw):
        return [], None

    async def _rerank_passthrough(q, docs):
        return docs, None

    monkeypatch.setattr(R, "_graph_expand", _graph_noop)
    monkeypatch.setattr(R, "_rerank_docs", _rerank_passthrough)


# ══════════════════════════════════════════════════════════════
# 态 1：抛错（嵌入异常）→ dense failed + sparse skipped + WARN + 主链不崩
# ══════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_dense_embed_raises_marks_failed_and_no_crash(monkeypatch, cap_logs):
    _install_common(monkeypatch)

    def _boom(texts):
        raise RuntimeError("BGE offline + DashScope 429")

    monkeypatch.setattr(R, "encode_dense_batch_detailed", _boom)

    bundle = await R.retrieve_three_channel("什么是现在完成时", **RETRIEVE_KW)

    # ③ 主链不崩：恒返回 RetrievalBundle（稀疏兜底在本态结构性不可达：loader 契约
    #    dense+sparse 成对建请求，嵌入失败即整通道不可用——如实降级为空 docs + 留痕）
    assert isinstance(bundle, RetrievalBundle)
    assert bundle.docs == []
    # 既有字段语义不变：degraded_reason 原文原样
    assert bundle.degraded_reason == "Milvus 检索跳过（RuntimeError）"
    # ① channel_health 标记
    ch = bundle.channel_health
    assert ch["dense"]["status"] == "failed"
    assert "RuntimeError" in ch["dense"]["reason"]
    assert ch["sparse"]["status"] == "skipped"
    assert ch["milvus_hybrid"]["status"] == "failed"
    # ② WARN 带通道名+原因
    assert any("RuntimeError" in r for r in _warns(cap_logs))


# ══════════════════════════════════════════════════════════════
# 态 2：超时 → dense failed(timeout) + 主链不崩
# ══════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_dense_timeout_marks_failed(monkeypatch, cap_logs):
    _install_common(monkeypatch)

    def _slow(texts):
        time.sleep(0.6)  # 远超测试用短超时
        return _ok_encoder(texts)

    monkeypatch.setattr(R, "encode_dense_batch_detailed", _slow)
    monkeypatch.setattr(R, "_milvus_hybrid_search", lambda **kw: [])  # 后台线程余波兜底
    monkeypatch.setattr(R.settings, "MILVUS_SEARCH_TIMEOUT", 0.15)

    bundle = await R.retrieve_three_channel("什么是虚拟语气", **RETRIEVE_KW)

    assert isinstance(bundle, RetrievalBundle)
    assert bundle.docs == []
    assert "超时" in (bundle.degraded_reason or "")
    ch = bundle.channel_health
    assert ch["dense"]["status"] == "failed"
    assert ("timeout" in ch["dense"]["reason"]) or ("超时" in ch["dense"]["reason"])
    assert ch["milvus_hybrid"]["status"] == "failed"
    assert ch["sparse"]["status"] == "unknown", "超时时稀疏阶段未知，不妄断 failed"
    assert any("timeout" in r for r in _warns(cap_logs))
    # 等待 to_thread 残留线程在 monkeypatch 仍生效窗内跑完（防 teardown 后触真实 Milvus）
    await asyncio.sleep(0.6)


# ══════════════════════════════════════════════════════════════
# 态 3a：空转（sha256 伪向量，Crit-2 真实形态）→ dense idle + 稀疏兜底结果仍可用
# ══════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_dense_idle_pseudo_vector_sparse_fallback_usable(monkeypatch, cap_logs):
    _install_common(monkeypatch)
    monkeypatch.setattr(R, "encode_dense_batch_detailed", _sha_encoder)
    monkeypatch.setattr(R, "_milvus_hybrid_search", lambda **kw: _milvus_rows("s1", "s2"))
    monkeypatch.setattr(R.settings, "EMBED_BACKEND", "cuda")  # 触发既有 cuda 空间失配标记

    bundle = await R.retrieve_three_channel("什么是定语从句", **RETRIEVE_KW)

    # 稀疏兜底：dense 空转但结果仍可用（稀疏通道经融合产出 docs）
    assert [d.doc_id for d in bundle.docs] == ["s1", "s2"]
    assert all(d.content for d in bundle.docs)
    # 既有 degraded_reason 语义不变：异空间降级留痕
    assert "query_embed_fallback:sha256" in (bundle.degraded_reason or "")
    # ① channel_health：dense idle（空转显式化，Crit-2 核心诉求）
    ch = bundle.channel_health
    assert ch["dense"]["status"] == "idle"
    assert "sha256" in ch["dense"]["reason"]
    assert ch["sparse"]["status"] == "ok"
    assert ch["milvus_hybrid"]["status"] == "ok"
    # ② WARN 留痕（通道名+原因）
    assert any("sha256" in r for r in _warns(cap_logs))


# ══════════════════════════════════════════════════════════════
# 态 3b：返回空（嵌入正常、hybrid 0 行）→ milvus_hybrid empty、dense 不背锅
# ══════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_hybrid_zero_rows_marks_empty_dense_ok(monkeypatch):
    _install_common(monkeypatch)
    monkeypatch.setattr(R, "encode_dense_batch_detailed", _ok_encoder)
    monkeypatch.setattr(R, "_milvus_hybrid_search", lambda **kw: [])

    bundle = await R.retrieve_three_channel("什么是非谓语动词", **RETRIEVE_KW)

    assert bundle.docs == []
    assert bundle.degraded_reason is None, "0 行非通道故障，degraded_reason 语义不变"
    ch = bundle.channel_health
    assert ch["milvus_hybrid"]["status"] == "empty"
    assert ch["dense"]["status"] == "ok"
    assert ch["sparse"]["status"] == "ok"


# ══════════════════════════════════════════════════════════════
# ② 连续失败升级：N=2 → 第 1 次 WARN、第 2 次 ERROR；成功清零
# ══════════════════════════════════════════════════════════════
def test_consecutive_dense_failures_escalate_to_error(monkeypatch, cap_logs):
    # Settings 未注册该字段（pydantic 禁未知字段赋值）→ 经模块常量注入阈值（生产走 settings 优先）
    monkeypatch.setattr(R, "_CHANNEL_FAIL_ERROR_N_DEFAULT", 2)

    def _boom(texts):
        raise RuntimeError("embed down")

    monkeypatch.setattr(R, "encode_dense_batch_detailed", _boom)
    kw = dict(user_id=1, role=UserRole.STUDENT, top_k=5)

    d1, r1, h1 = R._milvus_hybrid_search_safe("q1", **kw)
    assert d1 == [] and h1["dense"]["status"] == "failed"
    assert len(_warns(cap_logs)) == 1 and _errors(cap_logs) == [], "第 1 次失败=WARN"

    d2, _r2, _h2 = R._milvus_hybrid_search_safe("q2", **kw)
    assert d2 == []
    assert len(_errors(cap_logs)) == 1, "连续第 2 次失败升级 ERROR"
    assert R._CHANNEL_FAIL_STREAK["dense"] == 2

    # 成功 → 计数清零（恢复）
    monkeypatch.setattr(R, "encode_dense_batch_detailed", _ok_encoder)
    monkeypatch.setattr(R, "_milvus_hybrid_search", lambda **kw: _milvus_rows("s1"))
    d3, _r3, h3 = R._milvus_hybrid_search_safe("q3", **kw)
    assert [x.doc_id for x in d3] == ["s1"] and h3["dense"]["status"] == "ok"
    assert "dense" not in R._CHANNEL_FAIL_STREAK


# ══════════════════════════════════════════════════════════════
# 全健康态：channel_health 全量键与状态（回归防线：只增不改）
# ══════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_all_healthy_channel_health_shape(monkeypatch):
    _install_common(monkeypatch)
    monkeypatch.setattr(R, "encode_dense_batch_detailed", _ok_encoder)
    monkeypatch.setattr(R, "_milvus_hybrid_search", lambda **kw: _milvus_rows("h1"))
    monkeypatch.setattr(R.settings, "KG_EXPAND_ENABLED", False, raising=False)

    bundle = await R.retrieve_three_channel("什么是宾语从句", **RETRIEVE_KW)

    assert [d.doc_id for d in bundle.docs] == ["h1"]
    assert bundle.degraded_reason is None
    ch = bundle.channel_health
    assert set(ch.keys()) == {"milvus_hybrid", "dense", "sparse", "graph", "kg_expand", "rerank"}
    assert ch["dense"]["status"] == "ok" and ch["dense"]["backend"] == "bge_m3"
    assert ch["sparse"]["status"] == "ok"
    assert ch["milvus_hybrid"]["status"] == "ok"
    assert ch["graph"]["status"] == "disabled"     # enable_graph=False
    assert ch["kg_expand"]["status"] == "disabled"  # 灰度默认关
    assert ch["rerank"]["status"] == "ok"


def test_dense_health_from_backend_levels():
    """_dense_health_from_backend 定级口径单测：ok / idle（空转）/ degraded。"""
    assert R._dense_health_from_backend("bge_m3", None) == ("ok", None)
    st_, reason = R._dense_health_from_backend("sha256", None)
    assert st_ == "idle" and "sha256" in reason
    st_, reason = R._dense_health_from_backend("cloud", "query_embed_fallback:cloud")
    assert st_ == "idle" and reason == "query_embed_fallback:cloud"
    st_, reason = R._dense_health_from_backend("cloud", None)
    assert st_ == "degraded" and "cloud" in reason
