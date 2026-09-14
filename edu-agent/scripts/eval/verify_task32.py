# -*- coding: utf-8 -*-
"""
task32 · RAG 离线 A/B 验证：BGE-rerank top-20 命中率 vs _rule_rerank 规则基线（真实运行）

对 build_eval_set32.py 冻结的评估集（同一份召回候选，保证公平）：
  1) top-20 hit (GWT①) —— 由 rag_evaluator.compare_rerank_vs_rule 计算，含相对提升% + 差距分析。
  2) 补充 hit@1/3/5/10/20 + MRR（GWT③ 判定 +15% 的细化）—— 因为纯自匹配基准 top-20 会饱和
     (~100/100)，用这些更敏感的排序指标揭示重排的真实增益。
  3) data_hash 保证同数据同参数同结果（GWT④）。

不调用任何 LLM（不烧 DeepSeek）；reranker 用本机 RERANKER_PATH（BGE 系），CUDA。

用法：
  .venv\\Scripts\\python.exe scripts\\eval\\verify_task32.py
输出：
  scripts/eval/data/task32_result.json  （可复现 A/B 结果 + 指标 + gap_analysis）
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.chat.rag_evaluator import (  # noqa: E402
    _candidates_to_docs,
    _first_gt_rank,
    _rule_order,
    _rerank_order,
    _hit_at_k,
    compare_rerank_vs_rule,
)
try:
    from _safeio import safe_w  # 直接运行（脚本目录在 sys.path）
except ImportError:  # 以包形式导入（pytest: from scripts.eval import ...）
    from scripts.eval._safeio import safe_w  # Mimosa 路径穿越防护:写出统一收容校验


SET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "task32_eval_set.json")
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "task32_result.json")

# 参与重排 A/B 的候选上限：GT 在冻结召回中实测恒在 top-50（rank≤3），
# 取 top-RERANK_CAP 既覆盖 GT 又大幅降低 BGE 重排推理开销（300→50，~6x 提速）。
RERANK_CAP = 50


def _trim_cases(cases: list[dict]) -> list[dict]:
    """按 RRF 分数顺序截断候选到 top-RERANK_CAP，仍真实保留 GT（rank≤3<50）。"""
    out = []
    for c in cases:
        cands = sorted((c.get("candidates") or []), key=lambda x: float(x.get("score") or 0.0), reverse=True)
        out.append({**c, "candidates": cands[:RERANK_CAP]})
    return out


def _multi_k(cases: list[dict]) -> dict[str, dict]:
    """在同一份冻结候选上，对 k∈{1,3,5,10,20} 统计两种方法 top-k 命中率 + MRR。

    优化（避免旧版按 k 重复 rerank）：每个 case 只对全部候选重排**一次**得到完整有序 doc_id，
    再对有序列表按 k 切片快速计算，GPU 开销降到最小。
    """
    ks = [1, 3, 5, 10, 20]
    acc = {k: {"rule_hit": 0, "rerank_hit": 0, "rule_mrr": 0.0, "rerank_mrr": 0.0} for k in ks}
    n_degraded = 0
    for case in cases:
        query = str(case.get("query") or "")
        gt: set[str] = set(case.get("ground_truth_doc_ids") or [])
        docs = _candidates_to_docs(case.get("candidates") or [])
        n = len(docs)
        # 规则与 BGE 各自排一次完整序（BGE 仅 rerank 一次全部候选）
        rule_ids = _rule_order(query, docs, n)
        rerank_ids, degrade = _rerank_order(query, docs, n)
        if degrade:
            n_degraded += 1
        for k in ks:
            rule_r = _first_gt_rank(rule_ids[:k], gt)
            rera_r = _first_gt_rank(rerank_ids[:k], gt)
            acc[k]["rule_hit"] += int(rule_r is not None)
            acc[k]["rerank_hit"] += int(rera_r is not None)
            acc[k]["rule_mrr"] += (1.0 / rule_r) if rule_r else 0.0
            acc[k]["rerank_mrr"] += (1.0 / rera_r) if rera_r else 0.0
    n_total = len(cases)
    detail: dict[str, dict] = {}
    for k in ks:
        a = acc[k]
        detail[f"hit@{k}"] = {
            "rule": round(a["rule_hit"] / n_total, 4) if n_total else 0.0,
            "rerank": round(a["rerank_hit"] / n_total, 4) if n_total else 0.0,
            "rule_absolute": a["rule_hit"],
            "rerank_absolute": a["rerank_hit"],
            "improve_pct": round((a["rerank_hit"] - a["rule_hit"]) / a["rule_hit"] * 100.0, 2)
            if a["rule_hit"] else (float("inf") if a["rerank_hit"] > 0 else 0.0),
        }
        detail[f"mrr@{k}"] = {
            "rule": round(a["rule_mrr"] / n_total, 4) if n_total else 0.0,
            "rerank": round(a["rerank_mrr"] / n_total, 4) if n_total else 0.0,
        }
    detail["_n_degraded"] = n_degraded
    return detail


def main() -> None:
    if not os.path.exists(SET_PATH):
        raise SystemExit(f"[task32-verify] 评估集缺失: {SET_PATH}（请先运行 build_eval_set32.py）")

    data = json.load(open(SET_PATH, encoding="utf-8"))
    cases: list[dict] = _trim_cases(data["cases"])  # 候选截断到 top-50 提速（GT 恒在其中）
    meta = data["meta"]
    n = len(cases)
    print(f"[task32-verify] 评估集: {n} samples, recall_topk={meta.get('recall_topk')}, "
          f"eval_set_hash={meta.get('data_hash')}")

    # 沿着同一份冻结候选做 top-20 A/B（BGE 真重排 vs 规则基线）
    abt = compare_rerank_vs_rule(
        cases,
        k=20,
        recall_topk=meta.get("recall_topk", 150),
        params={
            "fanout": "task32-verify",
            "eval_set_hash": meta.get("data_hash"),
        },
        use_reranker=True,
    )

    # 补充：更敏感的 hit@k / MRR 排序指标
    multi = _multi_k(cases)

    summary = dict(abt.summary)
    summary["multi_k"] = multi
    summary["reranker_degraded_cases"] = sum(1 for p in abt.per_case if p.get("rerank_degraded"))

    # 降级如实标注（GWT：降级不伪装）
    degraded = [p for p in abt.per_case if p.get("rerank_degraded")]
    if degraded:
        summary["assert"] = "partial"
        summary["degraded_reason"] = degraded[0]["rerank_degraded"]
        print(f"[task32-verify][警告] {len(degraded)} 个 case 的 rerank 走规则兜底，结果部分降级")
    else:
        summary["assert"] = "full"

    result = {
        "task": "task32",
        "mode": "offline_ab",
        "eval_set_hash": meta.get("data_hash"),
        "data_hash": abt.data_hash,
        "params": abt.params,
        "summary": summary,
        "per_case": abt.per_case,
        "gap_analysis": abt.gap_analysis,
    }
    with open(safe_w(OUT_PATH), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[task32-verify] top-20 hit: rule={summary.get('rule_hit_rate')}, "
          f"rerank={summary.get('rerank_hit_rate')}, 相对提升 {summary.get('relative_improvement_pct')}%, "
          f"达标={summary.get('target_met')}")
    print(f"[task32-verify] hit@3 rule/rerank: {multi['hit@3']['rule']} / {multi['hit@3']['rerank']}  "
          f"(improve {multi['hit@3']['improve_pct']}%)")
    print(f"[task32-verify] mrr@20 rule/rerank: {multi['mrr@20']['rule']} / {multi['mrr@20']['rerank']}")
    print(f"[task32-verify] data_hash = {abt.data_hash}")
    print(f"[task32-verify] 已写出 {OUT_PATH}")


if __name__ == "__main__":
    main()