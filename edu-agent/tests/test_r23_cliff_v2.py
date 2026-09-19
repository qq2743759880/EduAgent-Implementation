# -*- coding: utf-8 -*-
"""W-NEXT-R23-001（R22 Crit-S4 承接：断崖层黑洞 28/64 final_docs=2）V2 断崖测试。

R22 实证：min-max 归一恒使 top1=1.0，V1 相对跌幅 (prev-cur)/prev 首步被系统性放大
（[1.0, 0.595, ...] 首步 40.5%>40% 即斩）→ 28/64 query 收缩至 2 docs；golden 在
rerank top5 的 5 条中 3 条被 V1 斩落（hit@5 0.0312 vs 5-doc 窗口上限 0.0781）。

本套件断言（V2=本轮 top20 分位下限断崖（v2c，接手者定稿），灰度开关 RERANK_CLIFF_V2 默认 False）：
  ① 默认关：_cliff_cutoff 行为与 V1 逐位一致（含真实 probe 分数向量回归样例）
  ② 开启：score<分位线即停（低于分位线的边缘条不保留，与 probe keep_quantile 逐位一致）；
     top1 恒保；final_max_k 上限不变；宽分布下分位线可在 ≤5 窗内截断（非恒 cap 补满）
  ③ 开启后经 retrieve_three_channel 全链：channel_health 键集/语义不动（FUSIONBLIND 禁动项）、
     docs 数≤final_max_k、排序=分数降序（V2 只改"在第几条停"，不改排序/分数/上限）
  ④ cutoff_drop_ratio 参数在 V1 路径仍生效（既有调用方契约不变）
真实分数向量取自 scripts/eval/data/r23_runs/r23_cliff_probe_probe64.json（idx23/idx59）。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.auth import UserRole
from app.chat import retriever as R
from app.chat.retriever import _cliff_cutoff, _cliff_cutoff_v2
from app.config import settings as st

RETRIEVE_KW = dict(user_id=1, role=UserRole.STUDENT, use_hyde=False,
                   enable_graph=False, top_k=5, final_max_k=5, cutoff_drop_ratio=0.40)

# 真实测量向量（probe64 idx23）：V1 首步相对跌幅 40.5%>40% → 斩至 2；golden 在 rerank rank3
PROBE_IDX23_SCORES = [1.0, 0.595, 0.517, 0.38, 0.359, 0.356, 0.348, 0.341, 0.335, 0.33,
                      0.325, 0.32, 0.315, 0.31, 0.305, 0.3, 0.295, 0.29, 0.285, 0.28]


def _docs(scores: list[float], prefix: str = "c"):
    return [R.RetrievedDoc(doc_id=f"{prefix}{i}", score=s, content=f"text-{i}",
                           source_file=None, content_type=None, series_code=None,
                           series_name=None, module_codes=[], keywords=[],
                           tenant_id=None, visibility=None, source_channel="hybrid")
            for i, s in enumerate(scores)]


@pytest.fixture()
def v2_on(monkeypatch):
    monkeypatch.setattr(st, "RERANK_CLIFF_V2", True)
    monkeypatch.setattr(st, "RERANK_CLIFF_V2_QUANT", 0.60)
    yield


# ════════════════ ① V1 语义（显式 False；默认已随用户裁定 2026-09-19 翻为 True） ════════════════
def test_explicit_false_matches_v1_on_real_probe_vector(monkeypatch):
    """显式 RERANK_CLIFF_V2=False：真实 probe 向量上与 V1 语义逐位一致（28/64 收缩形态保留）。"""
    monkeypatch.setattr(st, "RERANK_CLIFF_V2", False)
    docs = _docs(PROBE_IDX23_SCORES)
    out = _cliff_cutoff(docs, final_max_k=5, drop_ratio=0.40)
    assert [d.doc_id for d in out] == ["c0", "c1"]   # 1.0→0.595 跌 40.5%>40% → 边缘条保留后停


def test_explicit_false_param_drop_ratio_still_honored(monkeypatch):
    """V1 路径 cutoff_drop_ratio 参数仍生效（既有调用方契约不变）。"""
    monkeypatch.setattr(st, "RERANK_CLIFF_V2", False)
    docs = _docs([1.0, 0.85, 0.7, 0.6])
    assert [d.doc_id for d in _cliff_cutoff(docs, final_max_k=5, drop_ratio=0.40)] == ["c0", "c1", "c2", "c3"]
    assert [d.doc_id for d in _cliff_cutoff(docs, final_max_k=5, drop_ratio=0.10)] == ["c0", "c1"]


# ════════════════ ② 开启：分位线触发/停止语义/top1 恒保/宽分布截断 ════════════════
def test_v2_on_recovers_probe_golden_at_rank3(v2_on):
    """真实 probe 向量：q=0.6 floor=xs[12]=0.341 → 保 c0..c4（1.0/0.595/0.517/0.38/0.359），
    golden 所在 rank3 得保（V1 斩至 2 的修复目标形态）。"""
    docs = _docs(PROBE_IDX23_SCORES)
    out = _cliff_cutoff(docs, final_max_k=5, drop_ratio=0.40)
    assert len(out) == 5
    assert [d.doc_id for d in out][:3] == ["c0", "c1", "c2"]


def test_v2_on_stops_before_below_quant_edge(v2_on):
    """score<分位线即停：低于分位线的边缘条不保留（与 probe keep_quantile 逐位一致）。"""
    docs = _docs([1.0, 0.9, 0.2, 0.19, 0.18])
    # n=5, idx=int(0.6*5)=3 → floor=sorted[3]=0.9；c1=0.9 不<0.9 保；c2=0.2<0.9 停（边缘不保留）
    out = _cliff_cutoff(docs, final_max_k=5, drop_ratio=0.40)
    assert [d.doc_id for d in out] == ["c0", "c1"]


def test_v2_on_top1_always_kept_even_below_quant(v2_on):
    """top1 恒保（min-1-doc），即使其分数低于分位线。"""
    out = _cliff_cutoff(_docs([0.1]), final_max_k=5, drop_ratio=0.40)
    assert [d.doc_id for d in out] == ["c0"]
    out2 = _cliff_cutoff(_docs([0.1, 0.05]), final_max_k=5, drop_ratio=0.40)
    # n=2, idx=1 → floor=0.1；c1=0.05<0.1 停（边缘不保留）
    assert [d.doc_id for d in out2] == ["c0"]


def test_v2_on_wide_spread_cuts_within_top5(v2_on):
    """宽分布（v2c 非恒 cap 补满的证据面）：q=0.6 floor=0.7 → 保 4 条（c4=0.6<0.7 截断）。"""
    docs = _docs([1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.45, 0.4])
    out = _cliff_cutoff(docs, final_max_k=5, drop_ratio=0.40)
    assert [d.doc_id for d in out] == ["c0", "c1", "c2", "c3"]


def test_v2_on_custom_quant_monkeypatch(v2_on):
    """分位可配置（RERANK_CLIFF_V2_QUANT）：docs=[1.0,0.5,0.45]，n=3。
    q=0.34→idx=1 floor=0.5：c1=0.5 不<0.5 保、c2=0.45<0.5 停 → [c0,c1]；
    q=0.10→idx=0 floor=0.45：c2 不<0.45 保 → [c0,c1,c2]；
    q=0.80→idx=2 floor=1.0：c1<1.0 停 → [c0]。"""
    docs = _docs([1.0, 0.5, 0.45])
    st.RERANK_CLIFF_V2_QUANT = 0.34
    assert [d.doc_id for d in _cliff_cutoff(docs, final_max_k=5, drop_ratio=0.4)] == ["c0", "c1"]
    st.RERANK_CLIFF_V2_QUANT = 0.10
    assert [d.doc_id for d in _cliff_cutoff(docs, final_max_k=5, drop_ratio=0.4)] == ["c0", "c1", "c2"]
    st.RERANK_CLIFF_V2_QUANT = 0.80
    assert [d.doc_id for d in _cliff_cutoff(docs, final_max_k=5, drop_ratio=0.4)] == ["c0"]


def test_v2_empty_and_single_input(v2_on):
    assert _cliff_cutoff([], final_max_k=5, drop_ratio=0.4) == []
    assert _cliff_cutoff_v2([], final_max_k=5) == []


def test_v2_does_not_mutate_scores_or_reorder(v2_on):
    """V2 只改截断决策：不改分数、不改入参列表顺序（docs 已由 rerank 排好序）。"""
    scores = PROBE_IDX23_SCORES[:6]
    docs = _docs(scores)
    before = [(d.doc_id, d.score) for d in docs]
    _cliff_cutoff(docs, final_max_k=5, drop_ratio=0.40)
    assert [(d.doc_id, d.score) for d in docs] == before


# ════════════════ ②b 开关接线 + 灰度默认（R23 接手者补锁） ════════════════
def test_config_grayscale_defaults():
    """默认红线（用户裁定 2026-09-19 开启）：RERANK_CLIFF_V2 默认 True、quant 默认 0.60。
    直接新建 Settings 实例读源码默认（防进程内前序测试 monkeypatch 残留误判）。"""
    from app.config import Settings

    fresh = Settings()
    assert fresh.RERANK_CLIFF_V2 is True
    assert fresh.RERANK_CLIFF_V2_QUANT == 0.60


def test_switch_wiring_dispatches_to_v2(monkeypatch):
    """开关接线：RERANK_CLIFF_V2=True 时 _cliff_cutoff 派发 _cliff_cutoff_v2（参数仅传 final_max_k，
    drop_ratio 不进 V2——V1 相对跌幅参数与 V2 分位下限互不串扰）。"""
    calls: list[tuple[int]] = []
    monkeypatch.setattr(st, "RERANK_CLIFF_V2", True)
    monkeypatch.setattr(st, "RERANK_CLIFF_V2_QUANT", 0.60)
    orig_v2 = R._cliff_cutoff_v2

    def _spy(docs, *, final_max_k):
        calls.append((final_max_k,))
        return orig_v2(docs, final_max_k=final_max_k)

    monkeypatch.setattr(R, "_cliff_cutoff_v2", _spy)
    out = _cliff_cutoff(_docs(PROBE_IDX23_SCORES[:4]), final_max_k=5, drop_ratio=0.40)
    assert calls == [(5,)]
    # n=4, idx=int(0.6*4)=2 → floor=升序 xs[2]=0.595：c1=0.595 不<保，c2=0.517<0.595 停
    assert [d.doc_id for d in out] == ["c0", "c1"]


# ════════════════ ③ 全链语义安全（channel_health 禁动项 + docs 形态） ════════════════
def _install_chain_stubs(monkeypatch, scores: list[float]):
    rows = [{"chunk_id": f"c{i}", "score": 0.9, "content": f"text-{i}", "source_file": "f.md",
             "content_type": "question", "tags": [], "module_codes": [], "tenant_id": "_default",
             "series_code": None, "series_name": None, "visibility": None}
            for i in range(len(scores))]

    def _ok_encoder(texts):
        from app.knowledge.importer.embedder import DenseResult
        return DenseResult(vectors=[[0.1] * st.EMBEDDING_DIM for _ in texts],
                           backend="bge_m3", normalized=True, precision="fp32",
                           embedding_model="test-bge-m3", max_length=8192)

    def _milvus_rows_all(*a, **kw):
        return rows

    async def _graph_noop(*a, **kw):
        return [], None

    async def _rerank_score(q, docs):
        # 仿真实 rerank：按 scores 归一赋分并降序（本测试 scores 已降序，只赋分）
        for d, s in zip(docs, scores):
            d.score = s
        docs.sort(key=lambda d: d.score, reverse=True)
        return docs[:20], None

    monkeypatch.setattr(R, "encode_dense_batch_detailed", _ok_encoder)
    monkeypatch.setattr(R, "_milvus_hybrid_search", _milvus_rows_all)
    monkeypatch.setattr(R, "_graph_expand", _graph_noop)
    monkeypatch.setattr(R, "_rerank_docs", _rerank_score)


_HEALTH_KEYS = {"dense", "sparse", "milvus_hybrid", "graph", "kg_expand", "rerank"}


@pytest.mark.asyncio
async def test_full_chain_v2_off_vs_on_channel_health_unchanged(monkeypatch):
    """全链 V2 off/on 各跑一遍：channel_health 键集与 dense/sparse/graph/kg_expand/rerank
    语义位逐字段一致（FUSIONBLIND 禁动语义）；仅 docs 数量（截断决策）按 V2 变化。"""
    scores = PROBE_IDX23_SCORES
    bundles = {}
    for flag in (False, True):
        monkeypatch.setattr(st, "RERANK_CLIFF_V2", flag)
        monkeypatch.setattr(st, "RERANK_CLIFF_V2_QUANT", 0.60)
        _install_chain_stubs(monkeypatch, scores)
        bundles[flag] = await R.retrieve_three_channel("什么是现在完成时", **RETRIEVE_KW)
    off, on = bundles[False], bundles[True]
    # channel_health：键集一致 + 各通道 status/reason 一致（断崖层不触任何通道语义）
    assert set(off.channel_health.keys()) == _HEALTH_KEYS == set(on.channel_health.keys())
    for k in _HEALTH_KEYS:
        assert off.channel_health[k] == on.channel_health[k], f"channel_health[{k}] 被 V2 改动"
    # docs 形态：V2 在本向量上多保 golden 位（2→5），且不超 final_max_k、分数降序
    assert len(off.docs) == 2 and len(on.docs) == 5
    assert all(on.docs[i].score >= on.docs[i + 1].score for i in range(len(on.docs) - 1))
    assert [d.doc_id for d in on.docs] == [f"c{i}" for i in range(5)]
    # 其余既有字段语义不变
    assert on.raw_retrieved_count == off.raw_retrieved_count == len(scores)
    assert on.degraded_reason == off.degraded_reason is None
    assert on.rewrite_query is None and off.rewrite_query is None
    assert on.graph_entities == [] and off.graph_entities == []
