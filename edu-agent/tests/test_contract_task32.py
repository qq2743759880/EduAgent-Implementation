# -*- coding: utf-8 -*-
"""task32 RAG 离线评估（top-20 命中率 A/B）cycle测试。

GWT 覆盖（task32-rag-evaluator.md）：
- ① rag_evaluator 补 top-20 命中率指标（对照 _rule_rerank 规则基线）
- ② 离线评估集：规则重排低分样本（rule 不给 GT 第一 → BGE 语义捞回）
- ③ 相对提升计算 + target_met 判定（≥+15%）+ 差距分析/调参建议
- ④ data_hash 可复现（同数据同参数同结果）+ 对数据敏感

全部用 fake strategies（monkeypatch _rule_order/_rerank_order 或 fake Reranker），
不加载 GPU 模型、不依赖 Milvus，保证测试可离线跑。
"""
from __future__ import annotations

from app.chat.rag_evaluator import (
    _data_hash,
    _first_gt_rank,
    _hit_at_k,
    _rule_order,
    _rerank_order,
    compare_rerank_vs_rule,
)


def _cand(did: str, text: str, score: float = 0.5) -> dict:
    return {"doc_id": did, "content": text, "score": score}


def _case(query: str, gt: list[str], candidates: list[dict], note: str = "normal") -> dict:
    return {"query": query, "ground_truth_doc_ids": gt, "candidates": candidates, "note": note}


# ------------------------------------------------------------------
# 基础工具：_hit_at_k / _first_gt_rank
# ------------------------------------------------------------------
def test_hit_at_k_and_first_rank() -> None:
    gt = {"d1"}
    assert _hit_at_k(["d0", "d1", "d2"], gt, 2) is True
    assert _hit_at_k(["d0", "d2", "d1"], gt, 2) is False       # d1 在第3位，top-2 未命中
    assert _hit_at_k(["d1"], set(), 5) is False                # 空 gt → 不命中
    assert _hit_at_k(["d1"], gt, 5) is True
    assert _first_gt_rank(["d0", "d1"], gt) == 2
    assert _first_gt_rank(["d0", "d2"], gt) is None            # 不在列表 → None


# ------------------------------------------------------------------
# ①+②+③：compare_rerank_vs_rule —— 用 fake 排序策略注入可控场景
# ------------------------------------------------------------------
def _patch_strategies(monkeypatch, rule_ret, rerank_ret):
    """把 _rule_order/_rerank_order 换成假实现，返回 (rule_ids, rerank_ids, degrade)。"""
    monkeypatch.setattr(
        "app.chat.rag_evaluator._rule_order",
        lambda query, docs, k: rule_ret,
    )
    monkeypatch.setattr(
        "app.chat.rag_evaluator._rerank_order",
        lambda query, docs, k: rerank_ret,
    )


def test_compare_rerank_recovers_rule_miss(monkeypatch) -> None:
    """GWT②：规则不给 GT top-20（低分），BGE 语义捞回 → rerank_hit=True, rule_hit=False。"""
    cands = [_cand(f"d{i}", f"内容{i}") for i in range(30)]
    gt = ["gt_doc"]
    cases = [_case("递归是什么", gt, cands, note="rule_low_score")]
    # 规则把 gt_doc 排到 30 位（top-20 外）；BGE 升至第 1 位 → 捞回
    rule_ids = [f"d{i}" for i in range(30)]
    rerank_ids = ["gt_doc"] + rule_ids[:19]
    _patch_strategies(monkeypatch, rule_ids, (rerank_ids, None))

    rep = compare_rerank_vs_rule(cases, k=20, recall_topk=30, params={"t": 1})
    p = rep.per_case[0]
    assert p["rule_hit"] is False
    assert p["rerank_hit"] is True
    assert p["rule_rank_of_gt"] is None
    assert p["rerank_rank_of_gt"] == 1
    assert rep.summary["rule_hits"] == 0
    assert rep.summary["rerank_hits"] == 1
    assert rep.summary["relative_improvement_pct"] == float("inf")  # 规则 0→重排>0
    assert rep.summary["target_met"] is True
    assert any("规则漏→重排中" in line for line in rep.gap_analysis)


def test_compare_target_met_fifteen_percent(monkeypatch) -> None:
    """GWT③：规则 0.8→重排 1.0，相对提升 +25% ≥ +15% → target_met=True。

    构造：10 例，其中 q0/q1 两例规则把 GT 排到第 21 位（top-20 外 → 低分漏），
    其余 8 例 GT 排第 2；BGE 全部把 GT 捞回至 rank1 → 8/10 → 1.0，提升 25%。
    """
    cands = [_cand(f"d{i}", f"c{i}") for i in range(25)]
    cases = [_case(f"q{i}", ["gt"], cands) for i in range(10)]

    hit_order = ["d0", "gt"] + [f"d{i}" for i in range(2, 25)]        # GT 在 top-2
    miss_order = [f"d{i}" for i in range(21)] + ["gt"] + [f"d{i}" for i in range(21, 25)]  # GT 在 21 位
    rerank_first = ["gt"] + [f"d{i}" for i in range(25)]

    def _fake_rule(query, docs, k):
        idx = int(str(query)[1:])                                    # "q3" → 3
        return miss_order if idx < 2 else hit_order

    monkeypatch.setattr("app.chat.rag_evaluator._rule_order", _fake_rule)
    monkeypatch.setattr(
        "app.chat.rag_evaluator._rerank_order",
        lambda query, docs, k: (rerank_first, None),
    )

    rep = compare_rerank_vs_rule(cases, k=20, recall_topk=25, params={})
    assert rep.summary["total_cases"] == 10
    assert rep.summary["rule_hits"] == 8                            # 规则漏 q0/q1
    assert rep.summary["rerank_hits"] == 10
    assert rep.summary["rule_hit_rate"] == 0.8
    assert rep.summary["rerank_hit_rate"] == 1.0
    assert rep.summary["relative_improvement_pct"] == 25.0          # (1.0-0.8)/0.8
    assert rep.summary["target_met"] is True                        # 25% ≥ 15%


def test_compare_regression_reported(monkeypatch) -> None:
    """重排回归（rule 中但 rerank 漏）会在差距分析中体现，且未达标给调参建议。"""
    cands = [_cand(f"d{i}", f"c{i}") for i in range(25)]
    cases = [_case("q0", ["gt"], cands)]
    rule_ids = ["gt"] + [f"d{i}" for i in range(25)]             # 规则 rank1
    rerank_ids = [f"d{i}" for i in range(24)] + ["d30"]          # GT 不在 top（漏）
    _patch_strategies(monkeypatch, rule_ids, (rerank_ids, None))

    rep = compare_rerank_vs_rule(cases, k=20, recall_topk=25, params={})
    p = rep.per_case[0]
    assert p["rule_hit"] is True
    assert p["rerank_hit"] is False                              # 回归
    assert rep.summary["target_met"] is False
    assert any("规则中→重排漏" in line for line in rep.gap_analysis)
    assert any("调参建议" in line and "RETRIEVER_RERANK_TOPK" in line for line in rep.gap_analysis)


def test_use_reranker_false_makes_rerank_equal_rule(monkeypatch) -> None:
    """use_reranker=False → rerank 退化规则（对照/降级验证）。"""
    cands = [_cand(f"d{i}", f"c{i}") for i in range(25)]
    cases = [_case("q0", ["gt"], cands)]
    rule_ids = ["gt"] + [f"d{i}" for i in range(24)]
    _patch_strategies(monkeypatch, rule_ids, (rule_ids, None))
    rep = compare_rerank_vs_rule(cases, k=20, recall_topk=25, params={}, use_reranker=False)
    assert rep.per_case[0]["rerank_hit"] == rep.per_case[0]["rule_hit"]


# ------------------------------------------------------------------
# 真实 _rerank_order：fake Reranker（成功 / 失败）注入
# ------------------------------------------------------------------
class _FakeRerankerOk:
    load_error = None

    def rerank(self, query, contents, **kw):
        # 分数与位置正相关：越靠后的 content 分越高
        return [float(i) for i in range(len(contents))]


class _FakeRerankerFail:
    load_error = "模拟 GPU 不可用"

    def rerank(self, query, contents, **kw):
        return None


def test_rerank_order_with_fake_ok(monkeypatch) -> None:
    """真实 _rerank_order + fake Reranker 成功：按分数降序，无降级标注。"""
    from app.chat.schemas import RetrievedDoc
    monkeypatch.setattr("app.knowledge.reranker.Reranker.get", lambda: _FakeRerankerOk())
    docs = [RetrievedDoc(doc_id=f"d{i}", content=f"内容{i}", score=0.5) for i in range(5)]
    ids, degrade = _rerank_order("q", docs, 3)
    assert degrade is None
    assert ids == ["d4", "d3", "d2"]                             # 最高分前三


def test_rerank_order_fallback_degrade(monkeypatch) -> None:
    """真实 _rerank_order + fake Reranker 失败：规则兜底 + 如实降级标注。"""
    from app.chat.schemas import RetrievedDoc
    monkeypatch.setattr("app.knowledge.reranker.Reranker.get", lambda: _FakeRerankerFail())
    docs = [RetrievedDoc(doc_id=f"d{i}", content=f"内容{i}", score=0.5) for i in range(5)]
    ids, degrade = _rerank_order("q", docs, 3)
    assert ids == [d.doc_id for d in docs[:3]]                   # 规则兜底
    assert degrade is not None and "reranker_unavailable" in degrade


# ------------------------------------------------------------------
# ④ data_hash 可复现 + 敏感
# ------------------------------------------------------------------
def test_data_hash_reproducible() -> None:
    cands = [_cand("d1", "递归定义") for _ in range(2)]
    cases = [_case("q", ["d1"], cands)]
    base = _data_hash(cases, k=20, recall_topk=30, params=None, use_reranker=True)
    again = _data_hash(cases, k=20, recall_topk=30, params=None, use_reranker=True)
    assert base == again                                        # 同数据同参数 → 同 hash


def test_data_hash_sensitive_to_candidates() -> None:
    c1 = [_cand("d1", "递归定义")]
    c2 = [_cand("d1", "递归定义，函数调用自身")]
    h1 = _data_hash([_case("q", ["d1"], c1)], k=20, recall_topk=30, params=None, use_reranker=True)
    h2 = _data_hash([_case("q", ["d1"], c2)], k=20, recall_topk=30, params=None, use_reranker=True)
    assert h1 != h2                                             # 候选内容变化 → hash 变化


def test_data_hash_sensitive_to_k() -> None:
    cands = [_cand("d1", "递归")]
    h20 = _data_hash([_case("q", ["d1"], cands)], k=20, recall_topk=30, params=None, use_reranker=True)
    h10 = _data_hash([_case("q", ["d1"], cands)], k=10, recall_topk=30, params=None, use_reranker=True)
    assert h20 != h10                                           # 参数变化 → hash 变化