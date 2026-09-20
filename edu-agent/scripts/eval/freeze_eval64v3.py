# -*- coding: utf-8 -*-
"""
EVALFREEZE-B1 · eval64-v3 改写面尺基线冻结执行器（仿 r23_freeze_eval64.py）

承接 TO-EXEC-EVALFREEZE-B1：V3 改写面尺双跑（--group-hit，含 CO-IDX31-GROUPHIT-001）
逐位一致 → 冻结为 contracts/rag-baseline-eval64-v3.json（draft:false）。

口径：实时端到端 retrieve_three_channel 全链（召回150→rerank20→断崖→top5）在 final docs 上算
hit_rate@5 / mrr@5，0-LLM；与 V2 尺同参，唯一差异=打分侧 --group-hit（仅 idx31 生效）。

用法（edu-agent/ 下）：
  .venv/Scripts/python.exe -X utf8 scripts/eval/freeze_eval64v3.py           # 冻结
  .venv/Scripts/python.exe -X utf8 scripts/eval/freeze_eval64v3.py --check   # 只打印不落盘
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVAL_DIR = os.path.join(BASE_DIR, "scripts", "eval")
RUNS_DIR = os.path.join(EVAL_DIR, "data", "r64v3_runs")
SET_PATH = os.path.join(EVAL_DIR, "data", "r64v3_eval_set64.json")
CONTRACT_PATH = os.path.join(os.path.dirname(BASE_DIR), "contracts", "rag-baseline-eval64-v3.json")
V2_CONTRACT_PATH = os.path.join(os.path.dirname(BASE_DIR), "contracts", "rag-baseline-eval64-v2.json")

RUN1 = os.path.join(RUNS_DIR, "r64v3gh_run1.json")
RUN2 = os.path.join(RUNS_DIR, "r64v3gh_run2.json")


def _fingerprint(per_query: list[dict]) -> list:
    return [(r["rank_of_gt"], r["hit@5"], r["rr@5"], r["final_docs"]) for r in per_query]


def build_contract() -> dict:
    with open(RUN1, encoding="utf-8") as f:
        run1 = json.load(f)
    with open(RUN2, encoding="utf-8") as f:
        run2 = json.load(f)
    with open(V2_CONTRACT_PATH, encoding="utf-8") as f:
        v2 = json.load(f)
    with open(SET_PATH, "rb") as f:
        set_sha = hashlib.sha256(f.read()).hexdigest()

    pq1, pq2 = run1["per_query"], run2["per_query"]
    n = len(pq1)
    hit5 = sum(1 for r in pq1 if r["hit@5"])
    hit3 = sum(1 for r in pq1 if r["hit@3"])
    mrr5 = round(sum(r["rr@5"] for r in pq1) / n, 4)
    fd: dict = {}
    for r in pq1:
        fd[r["final_docs"]] = fd.get(r["final_docs"], 0) + 1

    det = {
        "runs": ["r64v3gh_run1", "r64v3gh_run2"],
        "per_query_identical": _fingerprint(pq1) == _fingerprint(pq2),
        "note": "V3 改写面尺新起点（本冻结即代际起点）；复现性以放宽双跑逐位一致为准",
    }
    if not det["per_query_identical"]:
        raise SystemExit("[freezev3] 双跑指纹不一致——按 TO-EXEC-EVALFREEZE-B1 铁律停手上报，勿冻结")

    # idx31 组命中留痕
    gh_rows = [r for r in pq1 if r.get("group_hit_applied")]
    if len(gh_rows) != 1:
        raise SystemExit(f"[freezev3] 预期仅 idx31 group_hit_applied=1，实测 {len(gh_rows)}——停手上报")
    gh = gh_rows[0]

    params = dict(run1["params"])
    contract = {
        "plan_id": "reshape-r-eval64-v3",
        "change_order": "contracts/CO-IDX31-GROUPHIT-001.md",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": run1["git_rev"],
        "draft": False,
        "frozen_by": "W-NEXT-EVALFREEZE-B1（scripts/eval/freeze_eval64v3.py，measure --group-hit 双跑）",
        "eval_set": {
            "file": "edu-agent/scripts/eval/data/r64v3_eval_set64.json",
            "sha256": set_sha,
            "n": n,
            "seed": 20260918,
            "query_face": "V2 query 面经 LLM 同义改写（deepseek-flash,thinking off,temp0.3，口语/正式轮换）；"
                          "护栏四条（字面重叠<60%/v3 非 golden 子串/golden 双键逐键继承/长度±50%）；"
                          "1 条重叠 62.5% 剔除不补位不凑数（64→63）",
            "golden_form": "content_block 逐字内容块（继承 V2，建集时活体 sha 复核；golden/gt_content 不改）",
            "golden_double_key": ["chunk_id", "doc_sha256(sha256(gt_content utf-8))"],
            "builder": "build_eval_set64.py --mode buildv3（measure --group-hit）",
            "dropped_from_v2": "v1_idx=11（改写字面重叠 62.5%>0.60 护栏，剔除不补位）",
        },
        "params": params,
        "baseline": {
            "tag": "r64v3gh_run1",
            "n": n,
            "top_k": 5,
            "hit_rate@5": round(hit5 / n, 4),
            "mrr@5": mrr5,
            "hit@3": round(hit3 / n, 4),
            "by_golden_type": {
                "content_block": {
                    "n": n,
                    "hit_rate@5": round(hit5 / n, 4),
                    "mrr@5": mrr5,
                }
            },
            "module_level_secondary": {
                "note": "V1 golden（路由卡）是否进 final docs——模块路由能力次级读数，非门禁主尺",
                "n": len(pq1),
                "module_hit@5": 0.1429,
                "module_mrr@5": 0.0511,
            },
            "runs_reference": [
                "edu-agent/scripts/eval/data/r64v3_runs/r64v3gh_run1.json",
                "edu-agent/scripts/eval/data/r64v3_runs/r64v3gh_run2.json",
            ],
            "cliff_behavior": {
                "final_docs_dist": {str(k): v for k, v in sorted(fd.items())},
                "note": "V2 断崖（RERANK_CLIFF_V2=True, quant=0.60）现产线实况",
            },
        },
        "thresholds": {
            "RAG_EVAL_HIT_RATE_MIN": round(hit5 / n - 0.02, 4),
            "RAG_EVAL_MRR_MIN": round(mrr5 - 0.02, 4),
            "rule": "基线-0.02（持续回归下限）；无目标预设；门禁适用范围裁定权在编排者",
        },
        "metric_scope": v2["metric_scope"],
        "determinism_check": det,
        "idx31_group_hit": {
            "applied": True,
            "change_order": "contracts/CO-IDX31-GROUPHIT-001.md",
            "case_idx": gh["idx"],
            "v1_idx": 31,
            "group_size": gh["group_size"],
            "definition": "golden 组=norm(V2 题干) 子串命中的兄弟块族（建集 verbatim_candidates）；"
                          "组内任一成员进 top5 记 hit，mrr 取组内最好排名",
            "best_rank": gh["rank_of_gt"],
            "rr@5": gh["rr@5"],
            "scope_note": "仅 verbatim_dup_count>1 的 golden 生效；V2/V3 集实测仅 idx31 一条；"
                          "--group-hit 默认关，关时 V1/V2 单键口径零改动",
            "toxicity_evidence": "同环境无 flag 对照跑 vs --group-hit 跑 per_query 四元组仅 idx31 一行变动，其余逐位一致",
        },
        "attribution_reference": {
            "pre_relaxed_runs": [
                "edu-agent/scripts/eval/data/r64v3_runs/r64v3_base_run1.json",
                "edu-agent/scripts/eval/data/r64v3_runs/r64v3_base_run2.json",
            ],
            "pre_relaxed_baseline": "单键口径 hit@5=62/63=0.9841, mrr@5=0.9683（唯一 miss=idx31）",
            "after_relaxed_baseline": "组命中口径 hit@5=63/63=1.0, mrr@5=0.9841（idx31 组内 rank1）",
            "rewrite_stress_evidence": "EVAL64V3 证伪 V2 P0-①：子串代理税=0（shared-63 严格对照）；V3 为改写面终尺",
        },
        "ruler_note": "本契约=改写面主尺 eval64-v3（含 idx31 组命中放宽 CO-IDX31-GROUPHIT-001，终版形态）；"
                      "内容块尺 contracts/rag-baseline-eval64-v2.json（单键口径，0.9844/0.9414）与 "
                      "路由卡尺 contracts/rag-baseline-eval64.json（0.0781）零改动保留作对照；"
                      "三尺并行禁互相换算",
        "id_map_note": v2["id_map_note"],
    }
    return contract


def main() -> int:
    ap = argparse.ArgumentParser(description="eval64-v3 改写面尺基线冻结")
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
    print(f"[freezev3] → {CONTRACT_PATH}")
    print(f"[freezev3] baseline hit@5={b['hit_rate@5']} mrr@5={b['mrr@5']} n={b['n']} "
          f"det={contract['determinism_check']['per_query_identical']} "
          f"idx31_group_rank={contract['idx31_group_hit']['best_rank']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
