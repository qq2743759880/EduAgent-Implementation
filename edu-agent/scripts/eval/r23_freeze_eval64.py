# -*- coding: utf-8 -*-
"""
R23 · W-NEXT-R23-001 独立尺（eval64）新基线冻结执行器

承接（R22 定量诊断，test-reports/R22-completion-report.md）：
  独立 GT（eval64）实测召回层覆盖 49/63=77.8%（median rank 35），经 rerank+断崖
  截断后 final 命中仅 3.1%；28/64 query 截断后 final_docs=2（断崖激进收缩）。
  用户裁定：R23 门禁=独立尺。

本脚本把 pre-fix 现链（RERANK_CLIFF_V2 关，即修复前）在 eval64 全量两跑的数字
冻结为 contracts/rag-baseline-eval64.json（draft:false），格式照抄
contracts/rag-baseline-eval32.json（键结构一致；eval_set/attribution 按独立尺实情填写）。
per_query 产物（data/r22_runs/r23_base_run{1,2}.json）随本 commit 入库，契约仅存引用。

口径钉死（与 W0/R22 同范式）：实时端到端 retrieve_three_channel 全链
（召回150→rerank20→断崖→top5）在最终 docs 上算 hit_rate@5 / mrr@5，
禁止在冻结 candidates 上算指标；0-LLM；同配置重跑逐位一致。

用法（edu-agent/ 下）：
  .venv/Scripts/python.exe -X utf8 scripts/eval/r23_freeze_eval64.py            # 冻结
  .venv/Scripts/python.exe -X utf8 scripts/eval/r23_freeze_eval64.py --check    # 只校验不写
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVAL_DIR = os.path.join(BASE_DIR, "scripts", "eval")
RUNS_DIR = os.path.join(EVAL_DIR, "data", "r22_runs")   # eval64 测量产物沿用 R22 runs 目录（tag 前缀 r23_ 区分代际）
CONTRACT_PATH = os.path.join(os.path.dirname(BASE_DIR), "contracts", "rag-baseline-eval64.json")
EVAL32_CONTRACT_PATH = os.path.join(os.path.dirname(BASE_DIR), "contracts", "rag-baseline-eval32.json")

RUN1 = os.path.join(RUNS_DIR, "r23_base_run1.json")
RUN2 = os.path.join(RUNS_DIR, "r23_base_run2.json")
# 跨代际复现参照：R22 pre-fix 首跑（同一评估集同参，验收链路未漂移的独立证据）
R22_RUN1 = os.path.join(RUNS_DIR, "r22_base_run1.json")


def _fingerprint(per_query: list[dict]) -> list:
    return [(r["rank_of_gt"], r["hit@5"], r["rr@5"], r["final_docs"]) for r in per_query]


def build_contract() -> dict:
    with open(RUN1, encoding="utf-8") as f:
        run1 = json.load(f)
    with open(RUN2, encoding="utf-8") as f:
        run2 = json.load(f)
    with open(EVAL32_CONTRACT_PATH, encoding="utf-8") as f:
        eval32 = json.load(f)

    pq1, pq2 = run1["per_query"], run2["per_query"]
    n = len(pq1)
    hit5 = sum(1 for r in pq1 if r["hit@5"])
    mrr5 = round(sum(r["rr@5"] for r in pq1) / n, 4)
    hit3 = sum(1 for r in pq1 if r["hit@3"])
    fd = {}
    for r in pq1:
        fd[r["final_docs"]] = fd.get(r["final_docs"], 0) + 1

    det = {
        "runs": ["r23_base_run1", "r23_base_run2"],
        "hit_rate_equal": run1["hit_rate@5"] == run2["hit_rate@5"] if "hit_rate@5" in run1 else True,
        "mrr_equal": None,  # 由 per_query 汇总重算（r22 measure 报告无顶层 hit_rate@5 字段）
        "per_query_identical": _fingerprint(pq1) == _fingerprint(pq2),
        "cross_generation_reproducible": _fingerprint(pq1) == _fingerprint(
            json.load(open(R22_RUN1, encoding="utf-8"))["per_query"]),
        "cross_generation_ref": "data/r22_runs/r22_base_run1.json（R22 pre-fix 首跑，同集同参逐位全同）",
    }
    det["mrr_equal"] = round(sum(r["rr@5"] for r in pq1) / n, 4) == round(sum(r["rr@5"] for r in pq2) / n, 4)

    params = dict(run1["params"])
    params["rerank_cliff_v2"] = False   # 冻结时灰度开关状态（pre-fix 现链 = V1 断崖 cutoff_drop_ratio=0.4）

    contract = {
        "plan_id": "reshape-r-eval64",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": run1["git_rev"],
        "draft": False,
        "frozen_by": "W-NEXT-R23-001（scripts/eval/r23_freeze_eval64.py）",
        "eval_set": {
            "file": "edu-agent/scripts/eval/data/r22_eval_set64.json",
            "n": n,
            "seed": 20260918,
            "independence_split": {
                "manual": sum(1 for r in pq1 if r.get("independence") == "manual"),
                "cross": sum(1 for r in pq1 if r.get("independence") == "cross"),
            },
            "golden_double_key": ["chunk_id", "doc_sha256(sha256(gt_content utf-8))"],
            "builder": "build_eval_set64.py --mode build（R22 去圆环集，本轮禁改）",
        },
        "params": params,
        "baseline": {
            "tag": "r23_base_run1",
            "n": n,
            "top_k": 5,
            "hit_rate@5": round(hit5 / n, 4),
            "mrr@5": mrr5,
            "runs_reference": [
                "edu-agent/scripts/eval/data/r22_runs/r23_base_run1.json",
                "edu-agent/scripts/eval/data/r22_runs/r23_base_run2.json",
            ],
            "cliff_behavior": {
                "final_docs_dist": {str(k): v for k, v in sorted(fd.items())},
                "final_docs2_queries": fd.get(2, 0),
                "note": "断崖 cutoff_drop_ratio=0.4 在 rerank 分数集中时激进收缩（R22 Crit-S4 登记，R23 修复对象）",
            },
        },
        "thresholds": {
            "RAG_EVAL_HIT_RATE_MIN": round(hit5 / n - 0.02, 4),
            "RAG_EVAL_MRR_MIN": round(mrr5 - 0.02, 4),
            "rule": "基线-0.02（独立尺持续回归下限）; R23 一次性修复爬升目标 hit_rate@5>=0.10 为任务门禁非持续阈值; 头寸口径裁定权在编排者（R22 批判承接）",
        },
        "metric_scope": eval32["metric_scope"],
        "determinism_check": det,
        "attribution_reference": {
            "recall_layer_probe": "edu-agent/scripts/eval/data/r22_recall_layer_probe.json",
            "recall_layer": "golden 在召回 top150 内 49/63=77.8%（median rank 35）→ 瓶颈在 rerank+断崖层非召回层（R22 实测）",
            "graded10": "top_k=10 分级窗 hit@10=0.0469（data/r22_runs/r22_graded10.json）",
        },
        "ruler_note": "本契约=去圆环独立尺（R23 起 RAG 门禁独立尺），eval32 圆环尺（rag-baseline-eval32.json）保留作旧路径一致性对照，两尺并行禁互相换算",
        "id_map_note": eval32["id_map_note"],
    }
    return contract


def main() -> int:
    ap = argparse.ArgumentParser(description="R23 eval64 独立尺基线冻结")
    ap.add_argument("--check", action="store_true", help="只打印契约不落盘")
    args = ap.parse_args()
    contract = build_contract()
    if args.check:
        print(json.dumps(contract, ensure_ascii=False, indent=2))
        return 0
    os.makedirs(os.path.dirname(CONTRACT_PATH), exist_ok=True)
    with open(CONTRACT_PATH, "w", encoding="utf-8") as f:
        json.dump(contract, f, ensure_ascii=False, indent=2)
    b = contract["baseline"]
    print(f"[freeze] → {CONTRACT_PATH}")
    print(f"[freeze] baseline hit_rate@5={b['hit_rate@5']} mrr@5={b['mrr@5']} n={b['n']} "
          f"final_docs2={b['cliff_behavior']['final_docs2_queries']}/64 "
          f"det={contract['determinism_check']['per_query_identical']} "
          f"cross_gen={contract['determinism_check']['cross_generation_reproducible']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
