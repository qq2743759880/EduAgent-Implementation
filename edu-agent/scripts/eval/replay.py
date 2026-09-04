# -*- coding: utf-8 -*-
"""
task29 GWT① 回放 + LLM-as-judge 评分：
  - 意图路由准确率（新路由 vs 重构前基线，全评估集真实 LLM 分类）
  - L0 误判 L3 攻防（W1）：L0 样本是否被升档到 L3（over-escalation）
  - 答案质量 judge（0-1 pass/fail，代表性子集真实回放完整 harness）

输出 JSON 结果，供 run_task29 汇总进报告。不伪造：全部真实 LLM 调用。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # edu-agent/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/

from scripts.eval.eval_dataset import ALL, by_intent, by_effort, stats as ds_stats
from scripts.eval import harnesses
from scripts.eval import llm_judge
from scripts.eval.harnesses import route_classify, SIXNODE_ROUTE_PROMPT, BASELINE_ROUTE_PROMPT


def _sample(pid: str):
    for s in ALL:
        if s.id == pid:
            return s
    raise KeyError(pid)


async def routing_accuracy() -> dict:
    """全评估集真实路由分类 → 准确率（六节点/循环走新路由，基线走旧路由 prompt）。"""
    routers = {
        "new_router": SIXNODE_ROUTE_PROMPT,
        "baseline_router": BASELINE_ROUTE_PROMPT,
    }
    detail = {}
    summary = {}
    for rname, prompt in routers.items():
        per_intent = {i: {"hit": 0, "total": 0} for i in ("chitchat", "knowledge", "tool", "learning")}
        d = {}
        for s in ALL:
            pred = await route_classify(s.query, prompt)
            ok = llm_judge.routing_pass(pred, s.intent)
            per_intent[s.intent]["total"] += 1
            per_intent[s.intent]["hit"] += ok
            d[s.id] = {"pred": pred, "gt": s.intent, "correct": ok,
                       "gt_effort": s.effort}
        total_hit = sum(v["hit"] for v in per_intent.values())
        total = sum(v["total"] for v in per_intent.values())
        summary[rname] = {
            "accuracy": round(total_hit / total, 4) if total else 0.0,
            "total": total,
            "hits": total_hit,
            "per_intent": {k: (round(v["hit"] / v["total"], 4) if v["total"] else 0.0) for k, v in per_intent.items()},
        }
        detail[rname] = d
    return {"summary": summary, "detail": detail}


async def answer_judge(harness_name: str, subset_ids: list[str]) -> dict:
    """代表性子集真实回放完整 harness → judge 0-1 通过率 + 每次延迟/调用/token。

    诚实性：judge 置信度分级（high=JSON/medium=裸0/1, low=文本抓取）。pass_rate 用
    high+medium（可全量捕获判分）样本；另有 pass_rate_full（含 low）供对比。low 样本
    单独列出，避免将语义不可靠的兜底判分混入主结论。
    """
    fn = harnesses.HARNESSES[harness_name]
    rows = []
    for pid in subset_ids:
        s = _sample(pid)
        res = await fn(s)
        verdict = llm_judge.judge_answer(s.query, res.answer, s.answer_guide)
        rows.append({
            "id": s.id, "intent": s.intent, "effort": s.effort,
            "pred_intent": res.intent, "pred_effort": res.effort,
            "judge_score": verdict["score"], "judge_reason": verdict["reason"],
            "judge_confidence": verdict.get("confidence", "high"),
            "latency_ms": round(res.latency_ms, 1),
            "llm_calls": res.llm_calls,
            "prompt_tokens": res.prompt_tokens,
            "completion_tokens": res.completion_tokens,
            "degraded": res.degraded,
            "error": res.error,
            "answer_preview": (res.answer or "")[:120],
        })
    reliable = [r for r in rows if r["judge_confidence"] in ("high", "medium")]
    passed_full = sum(1 for r in rows if r["judge_score"] == 1)
    passed_reliable = sum(1 for r in reliable if r["judge_score"] == 1)
    conf_counts = {}
    for r in rows:
        conf_counts[r["judge_confidence"]] = conf_counts.get(r["judge_confidence"], 0) + 1
    return {
        "harness": harness_name,
        "samples": len(rows),
        "pass_rate": round(passed_reliable / len(reliable), 4) if reliable else 0.0,
        "pass_rate_full": round(passed_full / len(rows), 4) if rows else 0.0,
        "reliable_n": len(reliable),
        "confidence_breakdown": conf_counts,
        "rows": rows,
    }


async def l0_escalation() -> dict:
    """L0 攻防：用 6 节点图真实回放全部 L0 样本，检测是否被过度升级。

    诚实性说明（R1-R5 审查修正）：图内 plan_node 只产出 L1/L2（无 L3 路径），
    因此「L0 误判 L3」结构性恒为 0，单看它无判别力且会掩盖真实缺陷。
    故本测试同时报告：
      - l0_misjudged_as_l3_rate：GWT① 验收门槛（<5%）
      - l0_escalated_to_L1p_rate：L0 被过度升级到 L1+（chitchat→knowledge 等），
        反映闲聊被误升到全检索档位的成本/延迟浪费（本环境实测为高发问题）
      - real_effort_dist：真实档位分布，供判别力
    """
    rows = []
    l3_hit = 0
    l1p_hit = 0
    for s in by_effort("L0"):
        res = await harnesses.HARNESSES["sixnode"](s)
        is_l3 = res.effort == "L3"
        is_l1p = res.effort in ("L1", "L2", "L3")
        l3_hit += 1 if is_l3 else 0
        l1p_hit += 1 if is_l1p else 0
        rows.append({"id": s.id, "pred_intent": res.intent, "real_effort": res.effort,
                     "is_l3": is_l3, "is_l1p": is_l1p, "latency_ms": round(res.latency_ms, 1)})
    total = len(rows)
    return {
        "rows": rows,
        "l0_misjudged_as_l3": l3_hit, "total": total,
        "l0_misjudged_as_l3_rate": round(l3_hit / total, 4) if total else 0.0,
        "l0_escalated_to_L1p": l1p_hit,
        "l0_escalated_to_L1p_rate": round(l1p_hit / total, 4) if total else 0.0,
        "real_effort_dist": {e: sum(1 for r in rows if r["real_effort"] == e) for e in ("L0", "L1", "L2", "L3")},
    }


def pick_subset(n: int = 10) -> list[str]:
    """跨意图+跨档位抽代表性子集（L0/L1/L2/L3 均衡），保证答案评测有覆盖面。"""
    chosen: list[str] = []
    buckets = [
        ["L0-1", "L0-3", "L0-6"],
        ["L1-1", "L1-2", "L1-3", "L1-5"],
        ["L2-1", "L2-2", "L2-6", "L2-L1", "L2-L2"],
        ["L3-1", "L3-2", "L3-5", "L3-6"],
    ]
    i = 0
    flat = [x for b in buckets for x in b]
    # 交替取，保证到 n 个
    while len(chosen) < n:
        for b in buckets:
            if len(chosen) >= n:
                break
            if i < len(b):
                chosen.append(b[i])
        i += 1
    return chosen[:n]


async def main(subset_size: int = 10) -> dict:
    routing = await routing_accuracy()
    escalation = await l0_escalation()
    subset = pick_subset(subset_size)
    answer_results = {}
    for name in ("sixnode", "baseline", "loop"):
        answer_results[name] = await answer_judge(name, subset)
    return {
        "dataset_stats": ds_stats(),
        "subset_ids": subset,
        "routing": routing,
        "l0_escalation": escalation,
        "answer_judge": answer_results,
    }


if __name__ == "__main__":
    n = int(os.environ.get("EVAL_SUBSET", "10"))
    out = asyncio.run(main(n))
    print(json.dumps(out, ensure_ascii=False, indent=2))