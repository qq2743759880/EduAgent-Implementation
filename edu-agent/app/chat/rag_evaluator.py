# -*- coding: utf-8 -*-
"""
RAG 检索质量评估器（Phase 2 AI Agent 深度优化）

面试考点：
- Hit Rate（命中率）：检索结果中是否包含正确答案
- MRR（Mean Reciprocal Rank）：第一个正确答案的排名倒数均值
- NDCG（Normalized Discounted Cumulative Gain）：考虑排序位置的质量评估
- 为什么需要评估？没有评估就无法知道 RAG 改好了还是改差了

task32：在既有 top-5 指标基础上，新增「top-20 命中率」BGE-rerank vs 规则基线 A/B 离线对比。
见 `compare_rerank_vs_rule()`：同一份冻结召回候选（保证 A/B 公平），分别用 _rerank_docs(BGE)
与 _rule_rerank 取 top-20，统计命中率、相对提升、逐例差距分析；`data_hash` 保证同数据同参数可复现。

用法：
  from app.chat.rag_evaluator import evaluate_retrieval, compare_rerank_vs_rule
  score = evaluate_retrieval(query, retrieved_docs, ground_truth_doc_ids)
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any


def _normalize(text: str) -> str:
    """文本归一化：去标点、小写、去空格。"""
    import re
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text.lower().strip())


class RetrievalMetrics:
    """检索质量指标容器。"""

    __slots__ = ("hit_rate", "mrr", "ndcg", "precision_at_k", "recall_at_k", "retrieved_count", "relevant_count")

    def __init__(self):
        self.hit_rate: float = 0.0
        self.mrr: float = 0.0
        self.ndcg: float = 0.0
        self.precision_at_k: float = 0.0
        self.recall_at_k: float = 0.0
        self.retrieved_count: int = 0
        self.relevant_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "hit_rate": round(self.hit_rate, 4),
            "mrr": round(self.mrr, 4),
            "ndcg": round(self.ndcg, 4),
            "precision@k": round(self.precision_at_k, 4),
            "recall@k": round(self.recall_at_k, 4),
            "retrieved": self.retrieved_count,
            "relevant": self.relevant_count,
        }


def evaluate_retrieval(
    query: str,
    retrieved_docs: list[dict[str, Any]],
    ground_truth_doc_ids: list[str],
    *,
    k: int = 5,
) -> RetrievalMetrics:
    """
    评估单次检索质量。

    Args:
        query: 用户查询
        retrieved_docs: 检索返回的文档列表（每个含 chunk_id/content/score）
        ground_truth_doc_ids: 标注的相关文档 ID 列表
        k: 评估 top-k 结果

    Returns:
        RetrievalMetrics 对象
    """
    metrics = RetrievalMetrics()
    metrics.retrieved_count = len(retrieved_docs)
    metrics.relevant_count = len(ground_truth_doc_ids)

    if not retrieved_docs or not ground_truth_doc_ids:
        return metrics

    # 取 top-k
    top_k_docs = retrieved_docs[:k]
    gt_set = set(ground_truth_doc_ids)

    # ── 1. Hit Rate：top-k 中是否至少命中一个相关文档 ──
    hit = any(doc.get("chunk_id") in gt_set for doc in top_k_docs)
    metrics.hit_rate = 1.0 if hit else 0.0

    # ── 2. MRR：第一个相关文档的排名倒数 ──
    for rank, doc in enumerate(top_k_docs, start=1):
        if doc.get("chunk_id") in gt_set:
            metrics.mrr = 1.0 / rank
            break

    # ── 3. Precision@k：top-k 中相关文档占比 ──
    relevant_in_top_k = sum(1 for doc in top_k_docs if doc.get("chunk_id") in gt_set)
    metrics.precision_at_k = relevant_in_top_k / k if k > 0 else 0.0

    # ── 4. Recall@k：相关文档中被检索到的比例 ──
    metrics.recall_at_k = relevant_in_top_k / len(gt_set) if gt_set else 0.0

    # ── 5. NDCG@k：考虑排序位置的折扣累积增益 ──
    dcg = 0.0
    idcg = 0.0
    for i, doc in enumerate(top_k_docs):
        rel = 1.0 if doc.get("chunk_id") in gt_set else 0.0
        pos = i + 1
        dcg += rel / math.log2(pos + 1)
    # IDCG：理想排序（所有相关文档排最前面）
    for i in range(min(len(gt_set), k)):
        idcg += 1.0 / math.log2(i + 2)
    metrics.ndcg = dcg / idcg if idcg > 0 else 0.0

    return metrics


def evaluate_batch(
    test_cases: list[dict[str, Any]],
    retriever_fn,
) -> dict[str, Any]:
    """
    批量评估检索质量。

    Args:
        test_cases: 测试用例列表，每个包含 {query, ground_truth_doc_ids, top_k}
        retriever_fn: 检索函数 (query, top_k) -> list[dict]

    Returns:
        汇总指标 {avg_hit_rate, avg_mrr, avg_ndcg, ...}
    """
    total_hit = 0.0
    total_mrr = 0.0
    total_ndcg = 0.0
    total_precision = 0.0
    total_recall = 0.0
    n = len(test_cases)

    if n == 0:
        return {"avg_hit_rate": 0, "avg_mrr": 0, "avg_ndcg": 0, "total_cases": 0}

    for case in test_cases:
        query = case["query"]
        gt_ids = case["ground_truth_doc_ids"]
        k = case.get("top_k", 5)

        docs = retriever_fn(query, top_k=k)
        metrics = evaluate_retrieval(query, docs, gt_ids, k=k)

        total_hit += metrics.hit_rate
        total_mrr += metrics.mrr
        total_ndcg += metrics.ndcg
        total_precision += metrics.precision_at_k
        total_recall += metrics.recall_at_k

    return {
        "avg_hit_rate": round(total_hit / n, 4),
        "avg_mrr": round(total_mrr / n, 4),
        "avg_ndcg": round(total_ndcg / n, 4),
        "avg_precision@k": round(total_precision / n, 4),
        "avg_recall@k": round(total_recall / n, 4),
        "total_cases": n,
    }


# ============================================================
# 预置测试用例（教育领域）
# ============================================================
EDU_RAG_TEST_CASES = [
    {
        "query": "英语现在完成时的用法",
        "ground_truth_doc_ids": ["ENG-L1-M1-S1-chunk-0", "ENG-L1-M1-S1-chunk-1"],
        "top_k": 5,
    },
    {
        "query": "Python 装饰器是什么",
        "ground_truth_doc_ids": ["PRG-L2-M1-S1-chunk-0"],
        "top_k": 5,
    },
    {
        "query": "一元二次方程求根公式",
        "ground_truth_doc_ids": ["MATH-L2-M2-S1-chunk-0"],
        "top_k": 5,
    },
]


# ============================================================
# task32 · top-20 命中率 + BGE-rerank vs 规则基线 A/B 离线评估
# ============================================================
def _hit_at_k(ordered_chunk_ids: list[str], ground_truth: set[str], k: int) -> bool:
    """top-k 命中：ordered 前 k 中是否至少包含一个 ground-truth doc id。"""
    return bool(ground_truth) and any(rid in ground_truth for rid in ordered_chunk_ids[:k])


def _first_gt_rank(ordered_chunk_ids: list[str], ground_truth: set[str]) -> int | None:
    """第一个 ground-truth 的 1-based 排名；不在 ordered 内或为空 → None。"""
    for rank, rid in enumerate(ordered_chunk_ids, start=1):
        if rid in ground_truth:
            return rank
    return None


def _candidates_to_docs(candidates: list[dict]) -> list[Any]:
    """把冻结候选 dicts 转成 RetrievedDoc（doc_id/content/score 三要素即可重排）。"""
    from app.chat.schemas import RetrievedDoc

    docs: list[Any] = []
    for c in candidates or []:
        docs.append(RetrievedDoc(
            doc_id=str(c.get("doc_id") or ""),
            content=str(c.get("content") or ""),
            score=float(c.get("score") or 0.0),
        ))
    return docs


def _rule_order(query: str, docs: list[Any], k: int) -> list[str]:
    """规则基线 top-k 排序（_rule_rerank，不截断到召回之外的语义）。"""
    from app.chat.retriever import _rule_rerank

    docs = copy.deepcopy(list(docs))
    ordered = _rule_rerank(query, docs)
    return [d.doc_id for d in ordered][:k]


def _rerank_order(query: str, docs: list[Any], k: int) -> tuple[list[str], str | None]:
    """BGE-reranker top-k 排序；不可用 → 规则兜底 + 返回 degraded_reason（如实标注，不伪造）。"""
    from app.chat.retriever import _normalize_rerank_scores
    from app.knowledge.reranker import Reranker

    rk = Reranker.get()  # 懒加载单例，task31 契约①
    docs = copy.deepcopy(list(docs))
    scores = rk.rerank(query, [d.content or "" for d in docs])
    if scores is None:  # reranker 不可用 → 规则兜底 + 标注降级（GWT① 降级契约）
        return _rule_order(query, docs, k), ("reranker_unavailable: " + str(rk.load_error or "load error"))
    if len(scores) != len(docs):
        scores = scores[: len(docs)] or [0.0] * len(docs)
    norm = _normalize_rerank_scores(list(scores))
    for d, s in zip(docs, norm):
        d.score = round(max(0.0, min(1.0, float(s))), 6)
    docs.sort(key=lambda d: d.score, reverse=True)
    return [d.doc_id for d in docs][:k], None


@dataclass
class RerankAbtReport:
    """BGE-rerank vs 规则基线 A/B 离线评估报告（可复现）。"""

    params: dict[str, Any]
    per_case: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    gap_analysis: list[str] = field(default_factory=list)
    data_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "params": self.params,
            "per_case": self.per_case,
            "summary": self.summary,
            "gap_analysis": self.gap_analysis,
            "data_hash": self.data_hash,
        }


def _data_hash(
    cases: list[dict],
    *,
    k: int,
    recall_topk: int,
    params: dict | None,
    use_reranker: bool,
) -> str:
    """可复现性指纹：同数据 + 同参数 → 同 hash（GWT④）。

    指纹覆盖冻结候选的 doc_id+content（不含 score，避免召回阶段分数噪声影响判定），
    ground_truth、query、k、recall_topk、params、use_reranker。
    """
    canonical = json.dumps(
        {
            "k": k,
            "recall_topk": recall_topk,
            "params": params or {},
            "use_reranker": use_reranker,
            "cases": [
                {
                    "query": c.get("query", ""),
                    "ground_truth_doc_ids": sorted(c.get("ground_truth_doc_ids") or []),
                    "candidates": sorted(
                        candidate.get("doc_id", "")
                        + "\u0000"
                        + candidate.get("content", "")
                        for candidate in (c.get("candidates") or [])
                    ),
                }
                for c in cases
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _gap_analysis(per_case: list[dict], k: int, summary: dict) -> list[str]:
    """逐例差距分析 → 洞察 + 调参建议（GWT②③：输出差距分析与优化方向）。"""
    recovered = [p for p in per_case if (not p["rule_hit"]) and p["rerank_hit"]]
    regressed = [p for p in per_case if p["rule_hit"] and (not p["rerank_hit"])]
    both_hit = [p for p in per_case if p["rule_hit"] and p["rerank_hit"]]
    both_miss = [p for p in per_case if (not p["rule_hit"]) and (not p["rerank_hit"])]

    lines: list[str] = []
    lines.append(
        f"[差距] 召回候选均可达(=冻结候选数={summary.get('total_cases', 0)})，BGE-rerank 命中 {summary.get('rerank_hits', 0)}/"
        f"{summary.get('total_cases', 0)}，规则基线命中 {summary.get('rule_hits', 0)}/${summary.get('total_cases', 0)}。"
    )
    if recovered:
        lines.append(
            f"[规则漏→重排中 {len(recovered)} 例] 这些查询 BGE 通过语义（近义/改写）命中了 top-{k}，规则因词面不重叠漏掉："
            + "；".join(f"`{p['query']}`(重排rank={p['rerank_rank_of_gt']})" for p in recovered[:8])
            + ("；…" if len(recovered) > 8 else "")
        )
    if regressed:
        lines.append(
            f"[规则中→重排漏 {len(regressed)} 例] 重排反伤（回归）需警惕："
            + "；".join(f"`{p['query']}`(规则rank={p['rule_rank_of_gt']})" for p in regressed[:8])
        )
    if both_miss:
        lines.append(
            f"[双漏 {len(both_miss)} 例] 语义与规则都未在 top-{k} 命中，多为 gt 未被召回或候选语义区分度不足，"
            f"需从召回层入手（提升 recall_topk / 增加查询改写）。"
        )

    # 调参建议（据失败模式给出可落地方案）
    target_abs = summary.get("absolute_gain_pct", 0.0)
    if summary.get("target_met"):
        lines.append(f"[达标] 提升 {summary.get('relative_improvement_pct')}% ≥ +15% 目标，保持现状并周期性复评。")
    else:
        suggestions = []
        if regressed:
            suggestions.append("保留断崖冗余：可放宽 RETRIEVER_RERANK_TOPK(20→30) 再 _cliff_cutoff，减少重排对 RRF 正确序的过度挤压")
        if both_miss:
            suggestions.append("抬召回边界：RETRIEVER_RECALL_TOPK(150→200/300)，并启用 HyDE 改写提升语义召回")
        if any(p.get("gt_in_recall") is False for p in per_case):
            suggestions.append("补召回盲区：该轮评估存在 ground-truth 未被召回样本，A/B 对其无效，需先修召回")
        suggestions.append("重排打分与截断联动：对 rerank 分数极差过大的查询采用分段截断，避免单点连坐一片")
        lines.append(
            f"[未达标] 当前绝对增益 {target_abs}pt / 相对提升 {summary.get('relative_improvement_pct')}%。"
            f"调参建议：" + "；".join(dict.fromkeys(suggestions))
        )
    return lines


def compare_rerank_vs_rule(
    cases: list[dict],
    *,
    k: int = 20,
    recall_topk: int = 150,
    params: dict | None = None,
    use_reranker: bool = True,
) -> RerankAbtReport:
    """BGE-rerank vs 规则基线在**同一份冻结召回候选**上的 top-k 命中率 A/B。

    Args:
        cases: [{"query", "ground_truth_doc_ids", "candidates":[{"doc_id","content","score"}], "note"}]
               candidates 应为同一 symmetric 召回结果（build 阶段已冻结为 JSON，保证公平与可复现）。
        k: top-k 命中评估窗（task32 默认 20；顶多等于召回候选数）。
        recall_topk: 召回候选数（仅用于指纹/记录，指示 A/B 的上界）。
        params: 评估参数（模型路径/重排 topk/cliff 等），写入报告以便对齐。
        use_reranker: True=用真实 BGE-reranker 排序；False=重排退化为规则（用于对照/降级验证）。

    Returns:
        RerankAbtReport（per_case + summary + gap_analysis + data_hash）。
    """
    from app.knowledge.reranker import Reranker  # noqa: F401  # 供 _rerank_order 懒加载使用

    per_case: list[dict[str, Any]] = []
    for i, case in enumerate(cases or []):
        query = str(case.get("query") or "")
        gt: set[str] = set(case.get("ground_truth_doc_ids") or [])
        docs = _candidates_to_docs(case.get("candidates") or [])
        recall_ids = {d.doc_id for d in docs}

        rule_ids = _rule_order(query, docs, k)
        if use_reranker:
            rerank_ids, degrade = _rerank_order(query, docs, k)
        else:
            rerank_ids, degrade = rule_ids, None

        per_case.append({
            "idx": i,
            "query": query,
            "note": case.get("note"),
            "ground_truth_doc_ids": sorted(gt),
            "recall_count": len(docs),
            "gt_in_recall": bool(gt & recall_ids),
            "rule_hit": _hit_at_k(rule_ids, gt, k),
            "rerank_hit": _hit_at_k(rerank_ids, gt, k),
            "rule_rank_of_gt": _first_gt_rank(rule_ids, gt),
            "rerank_rank_of_gt": _first_gt_rank(rerank_ids, gt),
            "rule_topk_ids": rule_ids,
            "rerank_topk_ids": rerank_ids,
            "rerank_degraded": degrade,
        })

    n = len(per_case)
    rule_hits = sum(p["rule_hit"] for p in per_case)
    rerank_hits = sum(p["rerank_hit"] for p in per_case)
    rule_rate = (rule_hits / n) if n else 0.0
    rerank_rate = (rerank_hits / n) if n else 0.0
    if rule_rate > 0:
        rel_improve = round((rerank_rate - rule_rate) / rule_rate * 100.0, 2)
    elif rerank_rate > rule_rate:
        rel_improve = float("inf")  # 规则基线 0 命中，rerank 从 0 起有意义地超过
    else:
        rel_improve = 0.0
    abs_gain = round((rerank_rate - rule_rate) * 100.0, 2)

    summary = {
        "k": k,
        "total_cases": n,
        "rule_hits": rule_hits,
        "rerank_hits": rerank_hits,
        "rule_hit_rate": round(rule_rate, 4),
        "rerank_hit_rate": round(rerank_rate, 4),
        "absolute_gain_pct": abs_gain,
        "relative_improvement_pct": rel_improve,
        "target_met": bool(rel_improve >= 15.0),  # GWT③：较规则基线提升 ≥+15%
        "recall_topk": recall_topk,
    }
    gap = _gap_analysis(per_case, k, summary)
    data_hash = _data_hash(cases, k=k, recall_topk=recall_topk, params=params, use_reranker=use_reranker)
    return RerankAbtReport(
        params={
            "k": k,
            "recall_topk": recall_topk,
            "use_reranker": use_reranker,
            **(params or {}),
        },
        per_case=per_case,
        summary=summary,
        gap_analysis=gap,
        data_hash=data_hash,
    )