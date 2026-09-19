# -*- coding: utf-8 -*-
"""
R23 · W-NEXT-R23-001 断崖诊断探针（S-4 承接：28/64 query 断崖后 final_docs=2 的黑洞归因）

R22 批判 S-4（test-reports/R22-completion-report.md §6）：断崖层"黑洞"现象未经专门批判，
cutoff_drop_ratio=0.4 是否应有最小保留数属检索正产改动，越界禁碰——R23 本任务即承接轮。

探针口径（只读测量，不改任何正产行为）：
  对每条 query 走真实链路前段（与 retrieve_three_channel 逐函数一致）：
    _milvus_hybrid_search_safe（召回150）→ 去重 → _rerank_docs（BGE rerank 全量打分
    + min-max 归一 + 排序 + 保 top20）→ 在**真实产出的 top20 分数向量**上离线模拟
    V1 现行断崖 与 V2 候选规则（绝对分位/自适应）的截断行为。
  跳过 _graph_expand：graph 通道只产 graph_entities 不产 docs（retriever.py:765 实读），
  对 docs/final 命中零贡献；kg_expand 默认 disabled（settings.KG_EXPAND_ENABLED=False）。

产出（data/r23_runs/）：
  r23_cliff_probe_<set>.json   per_query：top20 ids/scores、golden 全序 rank、V1 重放、V2 候选网格
  汇总打印：golden post-rerank 分布（天花板=golden 在 rerank top5 比例）+ 各规则 hit@5

用法（edu-agent/ 下）：
  .venv/Scripts/python.exe -X utf8 scripts/eval/r23_cliff_probe.py --set eval64 --tag probe64
  .venv/Scripts/python.exe -X utf8 scripts/eval/r23_cliff_probe.py --set eval32 --tag probe32
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "scripts", "eval", "data")
OUT_DIR = os.path.join(DATA_DIR, "r23_runs")
sys.path.insert(0, BASE_DIR)

SET_PATHS = {
    "eval64": os.path.join(DATA_DIR, "r22_eval_set64.json"),
    "eval32": os.path.join(DATA_DIR, "rag_eval_set32.json"),
}

TOP_K_EVAL = 5
RERANK_TOPK = 20

# ---- V2 候选规则网格（全部只作用于截断决策，不改分数、不改排序、不改 final_max_k 上限）----
FLOORS = [0.30, 0.40, 0.45, 0.50, 0.55, 0.60]           # a) 绝对归一分下限：score >= F 保留
SPREAD_TS = [0.25, 0.35, 0.45, 0.55, 0.65, 0.75]        # b) 展宽相对：top1 相对 top20 尾的累计落差 <= T 保留
QUANTILES = [0.50, 0.60, 0.70, 0.80]                    # c) 本轮分数分布分位下限：score >= quantile(top20, q)
MED_MULTS = [2.0, 3.0, 4.0]                             # d) 相邻落差 > c × 中位相邻落差 即断崖


# ============================================================
# 断崖规则实现（与 retriever._cliff_cutoff V1 逐行为对齐 + V2 候选）
#   输入：scores = rerank top20 归一分（降序），k = final_max_k
#   输出：保留条数（前缀语义不变——所有规则都只决定"在第几条停"）
# ============================================================
def keep_v1(scores: list[float], k: int, drop_ratio: float = 0.4) -> int:
    """V1 现行断崖（retriever._cliff_cutoff 同逻辑重放：相对相邻跌幅 + 断点边缘条保留）。"""
    if not scores:
        return 0
    kept = 1
    for i in range(1, len(scores)):
        prev, cur = scores[kept - 1], scores[i]
        if prev > 1e-9 and (prev - cur) / prev > drop_ratio:
            return min(kept + 1, len(scores))   # 断点边缘条计入后停
        kept += 1
        if kept >= k:
            break
    return min(kept, k)


def keep_floor(scores: list[float], k: int, floor: float) -> int:
    """V2-a 绝对归一分下限：连续保留 score>=floor 的前缀（至少保 1 条）。"""
    if not scores:
        return 0
    kept = 1
    for s in scores[1:]:
        if s < floor or kept >= k:
            break
        kept += 1
    return kept


def keep_spread(scores: list[float], k: int, t: float) -> int:
    """V2-b 展宽相对：累计落差 (s1-si)/max(s1-s_tail,eps) <= t 保留（对 top20 内展宽自适应）。"""
    if not scores:
        return 0
    spread = max(scores[0] - scores[-1], 1e-9)
    kept = 1
    for s in scores[1:]:
        if (scores[0] - s) / spread > t or kept >= k:
            break
        kept += 1
    return kept


def keep_quantile(scores: list[float], k: int, q: float) -> int:
    """V2-c 本轮分数分布分位下限：score >= top20 分位值 Q(q) 保留（按本轮分布自适应）。"""
    if not scores:
        return 0
    xs = sorted(scores)
    idx = min(int(q * len(xs)), len(xs) - 1)
    floor = xs[idx]
    kept = 1
    for s in scores[1:]:
        if s < floor or kept >= k:
            break
        kept += 1
    return kept


def keep_medmult(scores: list[float], k: int, c: float) -> int:
    """V2-d 中位落差倍数：相邻跌幅 > c×中位相邻落差 触发断崖（断点边缘条保留，同 V1 语义）。"""
    if not scores:
        return 0
    drops = [scores[i - 1] - scores[i] for i in range(1, len(scores))]
    pos = sorted(d for d in drops if d > 1e-12)
    med = pos[len(pos) // 2] if pos else 0.0
    if med <= 1e-12:
        return min(len(scores), k)
    kept = 1
    for i in range(1, len(scores)):
        if scores[i - 1] - scores[i] > c * med:
            return min(kept + 1, len(scores), k)
        kept += 1
        if kept >= k:
            break
    return min(kept, k)


RULES = (
    [("v1_current", lambda s, k: keep_v1(s, k, 0.4))]
    + [(f"v2a_floor_{f}", lambda s, k, f=f: keep_floor(s, k, f)) for f in FLOORS]
    + [(f"v2b_spread_{t}", lambda s, k, t=t: keep_spread(s, k, t)) for t in SPREAD_TS]
    + [(f"v2c_quant_{q}", lambda s, k, q=q: keep_quantile(s, k, q)) for q in QUANTILES]
    + [(f"v2d_medmult_{c}", lambda s, k, c=c: keep_medmult(s, k, c)) for c in MED_MULTS]
)


def probe(set_key: str, tag: str) -> dict:
    from app.auth import UserRole
    from app.chat.retriever import _milvus_hybrid_search_safe, _rerank_docs

    with open(SET_PATHS[set_key], encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    from r20min_run import _match_golden  # 只读复用 W0 双键解析（与两代基线同口径）

    rows: list[dict] = []
    t_start = time.perf_counter()

    async def _one(idx: int, case: dict) -> None:
        milvus_docs, _degrade, _health = await asyncio.to_thread(
            _milvus_hybrid_search_safe,
            case["query"], user_id=1, role=UserRole.STUDENT, top_k=TOP_K_EVAL,
        )
        # 与 retrieve_three_channel 融合段同语义：按 doc_id 去重保序（kg_expand disabled → 无并入）
        seen: set[str] = set()
        merged = []
        for d in milvus_docs:
            if not d.doc_id or d.doc_id in seen:
                continue
            seen.add(d.doc_id)
            merged.append(d)
        raw_n = len(merged)
        top20, _rr_degrade = await _rerank_docs(case["query"], merged)
        # 注意：_rerank_docs 原地对 merged 全量排序打分 → merged 现为全序（150），可取 golden 全序 rank
        full_ids = [d.doc_id for d in merged]
        scores20 = [round(float(d.score), 6) for d in top20]
        ids20 = [d.doc_id for d in top20]
        docs20 = [{"chunk_id": d.doc_id, "content": d.content, "score": d.score} for d in top20]
        gt_id, gt_via = _match_golden(case, docs20)
        # golden 全序 rank（>20 时 _match_golden 在 top20 上 miss → 用全序重解析）
        full_rank = None
        if gt_via == "miss":
            full_docs = [{"chunk_id": cid, "content": next((d.content for d in merged if d.doc_id == cid), "")}
                         for cid in full_ids]
            gt_id2, gt_via2 = _match_golden(case, full_docs)
            if gt_via2 != "miss" and gt_id2 in full_ids:
                full_rank = full_ids.index(gt_id2) + 1
                gt_id, gt_via = gt_id2, f"{gt_via2}(full_order)"
        elif gt_id in full_ids:
            full_rank = full_ids.index(gt_id) + 1
        v1_keep = keep_v1(scores20, TOP_K_EVAL, 0.4)
        rows.append({
            "idx": idx,
            "query": case["query"],
            "independence": case.get("independence"),
            "golden_chunk_id": case["golden"]["chunk_id"],
            "raw_recall": raw_n,
            "golden_recall_rank_in_full": None,  # 召回层 rank 属另一通道口径，此处不混算（见 r22_recall_layer_probe）
            "golden_full_rank_after_rerank": full_rank,
            "golden_in_rerank_top20": gt_via != "miss" and (full_rank is None or full_rank <= RERANK_TOPK),
            "golden_rank_in_top20": (full_rank if (full_rank is not None and full_rank <= RERANK_TOPK) else None),
            "gt_resolved_id": gt_id,
            "gt_resolve_via": gt_via,
            "scores_top20": scores20,
            "ids_top20_head5": ids20[:TOP_K_EVAL],
            "v1_keep": v1_keep,
            "v1_final_ids": ids20[:v1_keep],
        })

    sem = asyncio.Semaphore(1)

    async def _run_all() -> None:
        tasks = [_one(i, c) for i, c in enumerate(cases)]
        for t in tasks:
            await t

    asyncio.run(_run_all())

    # ---- 汇总 + V1 重放一致性 + V2 候选网格 ----
    n = len(rows)
    full_ranks = [r["golden_full_rank_after_rerank"] for r in rows]
    in5 = sum(1 for r in full_ranks if r is not None and r <= 5)
    in10 = sum(1 for r in full_ranks if r is not None and r <= 10)
    in20 = sum(1 for r in full_ranks if r is not None and r <= 20)
    v1_hit5 = sum(1 for r in rows if r["v1_keep"] >= (r["golden_rank_in_top20"] or 10**9)
                  and r["golden_rank_in_top20"] is not None)
    grid = {}
    for name, fn in RULES:
        kept_list = [fn(r["scores_top20"], TOP_K_EVAL) for r in rows]
        hit = sum(1 for r, kp in zip(rows, kept_list)
                  if r["golden_rank_in_top20"] is not None and r["golden_rank_in_top20"] <= kp)
        hit3 = sum(1 for r, kp in zip(rows, kept_list)
                   if r["golden_rank_in_top20"] is not None and r["golden_rank_in_top20"] <= min(kp, 3))
        from collections import Counter
        fd = dict(Counter(min(kp, TOP_K_EVAL) for kp in kept_list))
        grid[name] = {
            "hit@5": round(hit / n, 4),
            "hit@3": round(hit3 / n, 4),
            "mrr@5": round(sum(
                (1.0 / r["golden_rank_in_top20"])
                if (r["golden_rank_in_top20"] is not None and r["golden_rank_in_top20"] <= kp) else 0.0
                for r, kp in zip(rows, kept_list)) / n, 4),
            "final_docs_dist": {str(k): v for k, v in sorted(fd.items())},
            "mean_final_docs": round(sum(min(kp, TOP_K_EVAL) for kp in kept_list) / n, 2),
        }

    report = {
        "tag": tag,
        "set": set_key,
        "set_file": SET_PATHS[set_key],
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                  cwd=BASE_DIR).stdout.strip(),
        "mode": "probe(realtime recall+rerank 前段, cliff 离线模拟; 不触 graph/kg_expand; 0-LLM)",
        "n": n,
        "ceiling": {
            "golden_in_rerank_top5": in5,
            "golden_in_rerank_top10": in10,
            "golden_in_rerank_top20": in20,
            "ceiling_hit@5_any_prefix_rule": round(in5 / n, 4),
            "note": "final docs 恒为 rerank 全序前缀（断崖只决定停在第几条）→ hit@5 上限=golden 落 rerank top5 比例",
        },
        "golden_full_rank_hist_after_rerank": {
            "rank1_5": in5, "rank6_10": in10 - in5, "rank11_20": in20 - in10,
            "beyond20_or_miss": n - in20,
        },
        "v1_replay": {
            "hit@5": round(v1_hit5 / n, 4),
            "note": "V1 重放应与基线 run hit@5 一致（探针与主链同函数同参的校验位）",
        },
        "rules_grid": grid,
        "wall_seconds": round(time.perf_counter() - t_start, 1),
        "per_query": rows,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"r23_cliff_probe_{tag}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[probe:{tag}] ceiling rerank-top5={in5}/{n} top10={in10} top20={in20} "
          f"v1_replay_hit@5={report['v1_replay']['hit@5']} wall={report['wall_seconds']}s → {out_path}")
    top = sorted(grid.items(), key=lambda kv: (-kv[1]["hit@5"], -kv[1]["mrr@5"]))[:6]
    for name, g in top:
        print(f"[probe:{tag}]   {name:<18} hit@5={g['hit@5']:<7} mrr@5={g['mrr@5']:<7} "
              f"fd={g['final_docs_dist']} mean={g['mean_final_docs']}")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="R23 断崖诊断探针")
    ap.add_argument("--set", required=True, choices=["eval64", "eval32"])
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    probe(args.set, args.tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
