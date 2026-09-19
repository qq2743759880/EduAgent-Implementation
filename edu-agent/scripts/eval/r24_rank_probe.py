# -*- coding: utf-8 -*-
"""
R24 · W-NEXT-R24-001 排名质量诊断探针（承接 R23 移交：新瓶颈 = rerank 排名质量）

R23 收口事实（test-reports/R23-completion-report.md + r23_cliff_probe_probe64.json）：
  断崖层 V2 已开启（RERANK_CLIFF_V2=True，q=0.60）→ final 恒为 rerank 全序前缀 cap 补满 5 条，
  hit@5 已吃满结构上限（ceiling = golden 落 rerank top5 比例 = 5/64 = 0.0781）。
  独立 GT（eval64）golden：rerank top20 内仅 14/64；召回层（r22 隔离重放口径）覆盖 77.8%，
  median rank 35 —— golden 大量堆在 20 名开外。R24 问题：golden 是被 rerank 压下去，
  还是召回序本来就靠后？

探针口径（只读测量 + 探针内变量臂，不改任何正产默认值）：
  Phase A（rank 模式）对每条 query 走真实链路前段（与 r23_cliff_probe 同范式）：
    _milvus_hybrid_search_safe（召回150）→ 去重（与 retrieve_three_channel 融合段同语义）
    → _rerank_docs（sidecar 全量打分 + min-max 归一 + 排序；mergerd 原地排序 = 全序 150）。
    同时捕获【召回层原始序位】与【rerank 后全序序位】→ 双层四桶直方图 + 迁移矩阵
    （回答：rerank 压下去 vs 召回序本来就靠后）。
  Phase A-离线（不额外烧卡）：
    ① rerank 窗 20→50：在捕获的 rerank 全序分数向量上离线模拟 V2 断崖（q=0.60）
      —— 结构预期：final 恒为同一全序前缀 cap5 → hit@5/mrr@5 逐位不变（no-op 证明）。
    ② hyde on/off：离线 diff _rewrite_query_by_hyde_if_enabled(use_hyde=True) 是否改写
      —— 若 0 条改写即 no-op 证明；有改写才对改写子集补跑 realtime 对照臂。
  Phase B（grid 模式，realtime）：dense/sparse 权重臂（与 r20min_run._run_sensitivity
    同款 loader.py:315-348 逐字段重放，仅换 ranker）：
      rrf_k60（同通道基线）vs WeightedRanker(0.7,0.3) vs WeightedRanker(0.3,0.7)
    每臂：召回150 → 去重 → rerank（sidecar）→ golden 双层 rank → hit@5/mrr@5/覆盖。
    重放通道与主链口径不同 → 只做同通道相对对照（继承 r20min 教训，不与 Phase A 混算）。
  Phase C（r12-judge 模式）：R12 移交「语义 30% 抽检 30/30 judge_failed」（LLM 429 周
    配额死亡，dualrun_results.json semantic 记录 equivalent=null）→ 真 LLM judge 补跑：
    复用 r12 存档 30 条 (old_answer_head, new_answer_head) 对，judge prompt 与
    r20b_dualrun_probe.semantic_pair 逐字一致。如实登记两条口径限制：
    ① old 侧是 429 降级规则答案（非真实生成）② 存档 head 截 200 字符。

产出（data/r24_runs/）：
  r24_rank_probe_<tag>.json    Phase A per_query 双层 rank + 直方图 + 迁移矩阵 + 窗口/hyde 离线网格
  r24_grid_<tag>.json          Phase B dense/sparse 权重臂对比
  r24_worst10_<tag>.json       rerank 掉得最深的 10 条 case 证据包（归因输入）
  r24_r12_semantic_judge.json  Phase C R12 judge 补跑数字

用法（edu-agent/ 下）：
  .venv/Scripts/python.exe -X utf8 scripts/eval/r24_rank_probe.py --mode rank --tag probe64
  .venv/Scripts/python.exe -X utf8 scripts/eval/r24_rank_probe.py --mode grid --tag probe64
  .venv/Scripts/python.exe -X utf8 scripts/eval/r24_rank_probe.py --mode r12-judge
红线：只读 retriever.py / config.py（0 改动）；sidecar 8601 只调用不启停；contracts/ 冻结值不触。
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
OUT_DIR = os.path.join(DATA_DIR, "r24_runs")
sys.path.insert(0, BASE_DIR)

SET_PATH = os.path.join(DATA_DIR, "r22_eval_set64.json")
TOP_K_EVAL = 5
RERANK_TOPK_PROD = 20          # 生产 RETRIEVER_RERANK_TOPK（只读对照，不改）
CLIFF_V2_QUANT = 0.60          # 生产 RERANK_CLIFF_V2_QUANT（只读对照，不改）
WINDOWS = [20, 50]             # 候选①：rerank 窗 20（现行）vs 50（候选）
BUCKETS4 = [(1, 20), (21, 50), (51, 150), (151, 10**9)]  # 任务口径四桶（>150 含 miss）


def _bucket4(rank: int | None) -> str:
    if rank is None:
        return ">150(miss)"
    for lo, hi in BUCKETS4:
        if lo <= rank <= hi:
            return f"{lo}-{hi}" if hi != 10**9 else ">150"
    return ">150(miss)"


def _hist4(ranks: list[int | None]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in ranks:
        b = _bucket4(r)
        out[b] = out.get(b, 0) + 1
    return dict(sorted(out.items()))


def _cliff_v2_keep(scores_desc: list[float], final_max_k: int, q: float) -> int:
    """与 retriever._cliff_cutoff_v2 逐行为对齐的重放（只读；输入=窗口内降序分数向量）。"""
    if not scores_desc:
        return 0
    xs = sorted(scores_desc)
    floor = xs[min(int(q * len(xs)), len(xs) - 1)]
    kept = 1
    for s in scores_desc[1:]:
        if s < floor or kept >= final_max_k:
            break
        kept += 1
    return min(kept, final_max_k)


def _load_cases() -> list[dict]:
    with open(SET_PATH, encoding="utf-8") as f:
        return json.load(f)["cases"]


def _dump(path: str, payload: dict) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ============================================================
# Phase A：rank 画像（realtime 召回+rerank 前段，双层 rank 捕获）
# ============================================================
async def phase_a(tag: str) -> dict:
    from app.auth import UserRole
    from app.chat.retriever import _milvus_hybrid_search_safe, _rerank_docs
    from r20min_run import _match_golden  # 只读复用 W0 双键解析（与两代基线同口径）

    cases = _load_cases()
    rows: list[dict] = []
    t_start = time.perf_counter()

    for idx, case in enumerate(cases):
        t0 = time.perf_counter()
        # 1) 召回（生产通道同函数）：返回顺序 = RRF 融合序
        milvus_docs, _degrade, _health = await asyncio.to_thread(
            _milvus_hybrid_search_safe,
            case["query"], user_id=1, role=UserRole.STUDENT, top_k=TOP_K_EVAL,
        )
        # 2) 融合去重（与 retrieve_three_channel 融合段同语义：按 doc_id 去重保序）
        seen: set[str] = set()
        merged = []
        for d in milvus_docs:
            if not d.doc_id or d.doc_id in seen:
                continue
            seen.add(d.doc_id)
            merged.append(d)
        recall_ids = [d.doc_id for d in merged]          # rerank 原地排序前先捕召回序
        recall_docs = [{"chunk_id": cid,
                        "content": next((d.content for d in merged if d.doc_id == cid), "")}
                       for cid in recall_ids]
        gt_id_r, via_r = _match_golden(case, recall_docs)
        recall_rank = recall_ids.index(gt_id_r) + 1 if via_r != "miss" and gt_id_r in recall_ids else None
        # 3) rerank（sidecar）：_rerank_docs 原地对 merged 全量打分排序 → merged 变全序
        top20, _rr = await _rerank_docs(case["query"], merged)
        full_ids = [d.doc_id for d in merged]
        full_scores = [round(float(d.score), 6) for d in merged]
        full_types = [d.content_type for d in merged]
        full_docs = [{"chunk_id": cid,
                      "content": next((d.content for d in merged if d.doc_id == cid), "")}
                     for cid in full_ids]
        gt_id, via = _match_golden(case, full_docs)
        rerank_rank = full_ids.index(gt_id) + 1 if via != "miss" and gt_id in full_ids else None
        top5 = [{"chunk_id": d.doc_id, "score": round(float(d.score), 6),
                 "content_type": d.content_type, "content_head": (d.content or "")[:200]}
                for d in top20[:TOP_K_EVAL]]
        # golden 自身内容（供归因；来自召回池，miss 则空）
        golden_content_head = ""
        if rerank_rank is not None:
            golden_content_head = (full_docs[rerank_rank - 1]["content"] or "")[:400]
        rows.append({
            "idx": idx,
            "query": case["query"],
            "independence": case.get("independence"),
            "source": case.get("source"),
            "golden_chunk_id": case["golden"]["chunk_id"],
            "gt_resolved_id": gt_id,
            "gt_resolve_via": via,
            "recall_rank": recall_rank,
            "rerank_rank": rerank_rank,
            "raw_recall_n": len(recall_ids),
            "golden_content_head": golden_content_head,
            "gt_content": case.get("gt_content", ""),
            "rerank_top5": top5,
            "rerank_full_scores": full_scores,
            "golden_rerank_score": (full_scores[rerank_rank - 1] if rerank_rank else None),
        })
        print(f"[rank:{tag}] {idx + 1}/{len(cases)} recall={recall_rank} rerank={rerank_rank} "
              f"({time.perf_counter() - t0:.1f}s)", flush=True)
        # 检查点：每 16 条落盘（宿主限速保护）
        if (idx + 1) % 16 == 0 or idx + 1 == len(cases):
            _dump(os.path.join(OUT_DIR, f"r24_rank_probe_{tag}.json"),
                  _phase_a_report(tag, rows, len(cases), t_start, partial=True))

    report = _phase_a_report(tag, rows, len(cases), t_start, partial=False)

    # ---- 离线网格①：rerank 窗 20→50（V2 断崖 q=0.60 下重放；同一全序截不同窗口）----
    win_grid: dict[str, dict] = {}
    final_sets: dict[str, list[list[str]]] = {}
    for win in WINDOWS:
        hits = 0
        mrr = 0.0
        finals: list[list[str]] = []
        for r in rows:
            scores_w = r["rerank_full_scores"][:win]
            kept = _cliff_v2_keep(scores_w, TOP_K_EVAL, CLIFF_V2_QUANT)
            # final = 该窗口分数向量的前 kept 条（窗口截断自同一全序 → 前缀语义）
            gpos = r["rerank_rank"]
            if gpos is not None and gpos <= kept:
                hits += 1
                mrr += 1.0 / gpos
            finals.append([f"#{i + 1}" for i in range(min(kept, TOP_K_EVAL))])
        win_grid[f"window_{win}"] = {
            "hit@5": round(hits / len(rows), 4), "mrr@5": round(mrr / len(rows), 4),
            "note": "窗口截断自同一 rerank 全序；V2 断崖只决定前缀停点 → 结构上 hit@5 应与窗口无关",
        }
        final_sets[f"window_{win}"] = finals
    if len(final_sets) == 2:
        identical = final_sets[f"window_{WINDOWS[0]}"] == final_sets[f"window_{WINDOWS[1]}"]
        win_grid["window20_vs_window50_final_top5_identical"] = bool(identical)
    report["window_grid"] = win_grid

    # ---- 离线网格②：hyde on/off 改写 diff ----
    from app.chat.retriever import _rewrite_query_by_hyde_if_enabled
    hyde_changed: list[dict] = []
    for idx, case in enumerate(cases):
        rw, done, _deg = _rewrite_query_by_hyde_if_enabled(case["query"], use_hyde=True)
        if done and rw != case["query"]:
            hyde_changed.append({"idx": idx, "query": case["query"], "rewritten": rw})
    report["hyde_grid"] = {
        "n_changed": len(hyde_changed),
        "changed_cases": hyde_changed,
        "verdict": ("no-op（64 条 query 轻量同义词表 0 命中，hyde on 与 off 同串 → 检索结果逐位不变）"
                    if not hyde_changed else "有改写 → 需 realtime 对照臂（本探针按子集补跑）"),
    }
    report["partial"] = False
    _dump(os.path.join(OUT_DIR, f"r24_rank_probe_{tag}.json"), report)
    _dump_worst10(tag, rows)
    print(f"[rank:{tag}] ceiling rerank-top5={report['ceiling']['golden_in_rerank_top5']}/{report['n']} "
          f"recall_cover={report['recall_layer']['in150']}/{report['n']} "
          f"wall={report['wall_seconds']}s")
    _print_transition(report)
    return report


def _median(vals: list[int]) -> float:
    xs = sorted(vals)
    if not xs:
        return -1
    m = len(xs) // 2
    return float(xs[m]) if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def _phase_a_report(tag: str, rows: list[dict], n_total: int, t_start: float, *, partial: bool) -> dict:
    n = len(rows)
    recall_ranks = [r["recall_rank"] for r in rows]
    rerank_ranks = [r["rerank_rank"] for r in rows]
    in5 = sum(1 for x in rerank_ranks if x is not None and x <= 5)
    in10 = sum(1 for x in rerank_ranks if x is not None and x <= 10)
    in20 = sum(1 for x in rerank_ranks if x is not None and x <= 20)
    in150 = sum(1 for x in recall_ranks if x is not None)
    # 迁移矩阵：召回桶 × rerank 桶（仅召回命中的 golden 参与）
    trans: dict[str, dict[str, int]] = {}
    promoted = demoted = same = 0
    rr_valid = [r for r in rows if r["recall_rank"] is not None and r["rerank_rank"] is not None]
    for r in rr_valid:
        rb, pb = _bucket4(r["recall_rank"]), _bucket4(r["rerank_rank"])
        trans.setdefault(rb, {}).setdefault(pb, 0)
        trans[rb][pb] += 1
        if r["rerank_rank"] < r["recall_rank"]:
            promoted += 1
        elif r["rerank_rank"] > r["recall_rank"]:
            demoted += 1
        else:
            same += 1
    # 现行断崖（V2 q=0.60）重放 hit@5（应=ceiling：final 恒 top5 前缀 cap 补满）
    v2_hits = 0
    for r in rows:
        kept = _cliff_v2_keep(r["rerank_full_scores"][:RERANK_TOPK_PROD], TOP_K_EVAL, CLIFF_V2_QUANT)
        if r["rerank_rank"] is not None and r["rerank_rank"] <= kept:
            v2_hits += 1
    return {
        "tag": tag,
        "set": "eval64",
        "set_file": SET_PATH,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                  cwd=BASE_DIR).stdout.strip(),
        "mode": ("probe(realtime recall150+rerank 全序捕获; 双层 rank 画像; "
                 "窗口/hyde 离线模拟; 0-LLM; 不触 graph/kg_expand)"),
        "partial": partial,
        "n": n,
        "n_total_expected": n_total,
        "ceiling": {
            "golden_in_rerank_top5": in5,
            "golden_in_rerank_top10": in10,
            "golden_in_rerank_top20": in20,
            "ceiling_hit@5": round(in5 / n, 4),
            "cliff_v2_q0.60_replay_hit@5": round(v2_hits / n, 4),
            "note": "V2 断崖重放应与 ceiling 一致（cap 补满语义，校验位）",
        },
        "recall_layer": {
            "in150": in150,
            "coverage": round(in150 / n, 4),
            "median_rank_in150": _median([x for x in recall_ranks if x is not None]),
            "hist4": _hist4(recall_ranks),
        },
        "rerank_layer": {
            "median_rank": _median([x for x in rerank_ranks if x is not None]),
            "hist4": _hist4(rerank_ranks),
            "hist_fine": {
                "rank1_5": in5, "rank6_10": in10 - in5, "rank11_20": in20 - in10,
                "rank21_50": sum(1 for x in rerank_ranks if x is not None and 21 <= x <= 50),
                "rank51_150": sum(1 for x in rerank_ranks if x is not None and 51 <= x <= 150),
                "miss_or_recall_miss": n - in20 - sum(1 for x in rerank_ranks if x is not None and 21 <= x <= 150),
            },
        },
        "transition_recall_bucket_to_rerank_bucket": trans,
        "pairwise_recall_vs_rerank": {
            "n_both_hit": len(rr_valid),
            "rerank_promoted": promoted,
            "rerank_demoted": demoted,
            "unchanged": same,
            "median_rank_delta_rerank_minus_recall": _median(
                [r["rerank_rank"] - r["recall_rank"] for r in rr_valid]),
        },
        "wall_seconds": round(time.perf_counter() - t_start, 1),
        "per_query": rows,
    }


def _print_transition(report: dict) -> None:
    for rb, cols in report["transition_recall_bucket_to_rerank_bucket"].items():
        print(f"[rank] recall[{rb}] -> " + " ".join(f"rerank[{k}]={v}" for k, v in sorted(cols.items())))
    pw = report["pairwise_recall_vs_rerank"]
    print(f"[rank] both_hit={pw['n_both_hit']} promoted={pw['rerank_promoted']} "
          f"demoted={pw['rerank_demoted']} same={pw['unchanged']} "
          f"medianΔ={pw['median_rank_delta_rerank_minus_recall']}")


def _dump_worst10(tag: str, rows: list[dict]) -> None:
    """rerank 掉得最深的 10 条（rerank rank 降序，miss 按 recall rank 降序其次）。"""
    def key(r: dict):
        rr = r["rerank_rank"] if r["rerank_rank"] is not None else 10**6
        return (-rr, -(r["recall_rank"] or 0))
    worst = sorted(rows, key=key)[:10]
    _dump(os.path.join(OUT_DIR, f"r24_worst10_{tag}.json"), {
        "tag": tag, "picked_by": "rerank_rank desc（miss 最深），tie-break recall_rank desc",
        "cases": worst,
    })


# ============================================================
# Phase B：dense/sparse 权重臂（realtime 重放，同通道相对对照）
# ============================================================
async def phase_b(tag: str) -> dict:
    from app.chat.retriever import _rerank_docs
    from app.chat.schemas import RetrievedDoc
    from app.config import settings
    from app.knowledge.importer.embedder import build_sparse_vector, encode_dense_batch, ensure_jieba_ready
    from app.knowledge.importer.loader import (COLLECTION_NAME, COURSE_PUBLIC, INTERNAL_FILTER_EXPR,
                                               _and_filter, get_milvus_client)
    from r20min_run import _match_golden
    from pymilvus import AnnSearchRequest, RRFRanker, WeightedRanker

    cases = _load_cases()
    ensure_jieba_ready()
    client = get_milvus_client()
    tenant_ids = ["_default", COURSE_PUBLIC, "user_1"]  # 与 _search_tenant_ids(1, STUDENT) 一致
    exclude = getattr(settings, "RETRIEVER_EXCLUDE_CONTENT_TYPES", ()) or ()
    filter_expr = None
    if exclude:
        quoted = ", ".join(f'"{ct}"' for ct in exclude)
        filter_expr = f"content_type not in [{quoted}]"
    filter_expr = _and_filter(filter_expr, INTERNAL_FILTER_EXPR)  # 学员视角（include_internal=False）
    recall_k = int(getattr(settings, "RETRIEVER_RECALL_TOPK", 150))
    timeout = float(getattr(settings, "MILVUS_SEARCH_TIMEOUT", 8.0))

    print(f"[grid:{tag}] 预计算 {len(cases)} 条 dense+sparse 向量...", flush=True)
    dense_all = encode_dense_batch([c["query"] for c in cases])
    sparse_all = [build_sparse_vector(c["query"]) for c in cases]

    arms = [
        ("rrf_k60_base", lambda: RRFRanker(k=60)),
        ("weighted_dense70_sparse30", lambda: WeightedRanker(0.7, 0.3)),
        ("weighted_dense30_sparse70", lambda: WeightedRanker(0.3, 0.7)),
    ]
    report: dict = {"tag": tag, "ran_at": datetime.now(timezone.utc).isoformat(),
                    "mode": "replay(loader.py:315-348 逐字段重放, 仅换 ranker; 同通道相对对照, 不与主链混算)",
                    "arms": {}}
    for arm_name, make_ranker in arms:
        t0 = time.perf_counter()
        rows: list[dict] = []
        for idx, (case, dvec, svec) in enumerate(zip(cases, dense_all, sparse_all)):
            dense_req = AnnSearchRequest(
                data=[[float(x) for x in dvec]], anns_field="dense_vec",
                param={"metric_type": "COSINE", "params": {"nprobe": int(getattr(settings, "RAG_DENSE_NPROBE", 32))}},
                limit=recall_k, expr=filter_expr,
            )
            sparse_req = AnnSearchRequest(
                data=[svec], anns_field="sparse_vec", param={"metric_type": "IP"},
                limit=recall_k, expr=filter_expr,
            )
            res = client.hybrid_search(
                collection_name=COLLECTION_NAME, reqs=[dense_req, sparse_req],
                ranker=make_ranker(), limit=recall_k, timeout=timeout,
                partition_names=tenant_ids, output_fields=["chunk_id", "content", "content_type"],
            )
            docs: list[RetrievedDoc] = []
            seen: set[str] = set()
            for hits in res:
                for h in hits:
                    ent = h.get("entity") or {}
                    cid = str(ent.get("chunk_id") or "")
                    if not cid or cid in seen:
                        continue
                    seen.add(cid)
                    docs.append(RetrievedDoc(doc_id=cid, score=0.0,
                                             content=str(ent.get("content") or ""),
                                             content_type=ent.get("content_type"),
                                             source_channel="hybrid"))
            recall_ids = [d.doc_id for d in docs]
            recall_docs = [{"chunk_id": d.doc_id, "content": d.content} for d in docs]
            gt_r, via_r = _match_golden(case, recall_docs)
            recall_rank = recall_ids.index(gt_r) + 1 if via_r != "miss" else None
            top20, _rr = await _rerank_docs(case["query"], docs)
            full_ids = [d.doc_id for d in docs]
            full_docs = [{"chunk_id": d.doc_id, "content": d.content} for d in docs]
            gt_id, via = _match_golden(case, full_docs)
            rerank_rank = full_ids.index(gt_id) + 1 if via != "miss" else None
            rows.append({"idx": idx, "recall_rank": recall_rank, "rerank_rank": rerank_rank,
                         "raw_recall_n": len(recall_ids)})
        n = len(rows)
        in5 = sum(1 for r in rows if r["rerank_rank"] and r["rerank_rank"] <= 5)
        cov = sum(1 for r in rows if r["recall_rank"])
        hit = sum(1 for r in rows if r["rerank_rank"] and r["rerank_rank"] <= TOP_K_EVAL)
        mrr = sum(1.0 / r["rerank_rank"] for r in rows if r["rerank_rank"] and r["rerank_rank"] <= TOP_K_EVAL)
        report["arms"][arm_name] = {
            "hit@5": round(hit / n, 4),
            "mrr@5": round(mrr / n, 4),
            "ceiling_rerank_top5": f"{in5}/{n}",
            "recall150_coverage": f"{cov}/{n}",
            "median_rerank_rank": _median([r["rerank_rank"] for r in rows if r["rerank_rank"]]),
            "wall_seconds": round(time.perf_counter() - t0, 1),
            "per_query": rows,
        }
        print(f"[grid:{tag}] {arm_name}: hit@5={hit / n:.4f} mrr@5={mrr / n:.4f} "
              f"ceiling={in5}/{n} cover={cov}/{n} ({report['arms'][arm_name]['wall_seconds']}s)", flush=True)
        _dump(os.path.join(OUT_DIR, f"r24_grid_{tag}.json"), report)  # 每臂落盘（限速保护）
    return report


# ============================================================
# Phase C：R12 语义 30% judge 补跑（复用 r12 存档样本清单）
# ============================================================
def phase_r12_judge() -> dict:
    import re as _re

    from app.chat.generator import _ChatClient

    def _judge_call(prompt: str) -> str:
        # 与 r20b_dualrun_probe.semantic_pair 同调用路径（_ChatClient.call_chat）：
        # strong 走 LLM_STRONG_BASE_URL/KEY（deepseek 官方，周配额已重置）；fast=minimax@dashscope 本轮 401 错配不可用
        return _ChatClient.get().call_chat(
            messages=[{"role": "user", "content": prompt}],
            model="strong", temperature=0.0, max_tokens=512, timeout=120.0,
        )

    EVAL_DIR = os.path.dirname(DATA_DIR)  # r20b 产物在 scripts/eval/ 根（非 data/）
    with open(os.path.join(EVAL_DIR, "dualrun_results.json"), encoding="utf-8") as f:
        r12 = json.load(f)
    sem = [x for x in r12.get("semantic", []) if x.get("old_answer_head") is not None
           or x.get("new_answer_head") is not None]
    sem = [x for x in sem if "sample_id" in x]
    records: list[dict] = []
    t0 = time.perf_counter()
    for i, rec in enumerate(sem):
        query = None
        # 复用 r12 样本清单取 query（dualrun_samples.json 同 seed 同集）
        try:
            with open(os.path.join(EVAL_DIR, "dualrun_samples.json"), encoding="utf-8") as f:
                samples = json.load(f)["samples"]
            s = next((x for x in samples if x["sample_id"] == rec["sample_id"]), None)
            query = s["query"] if s else None
        except Exception:
            pass
        prompt = (
            "判断以下两个针对同一问题的回答语义是否等价（要点一致即可，措辞不同不算分歧）。\n"
            f"问题：{query or '(样本清单缺 query，仅对比答案)'}\n\n"
            f"回答A：{rec.get('old_answer_head') or ''}\n\n回答B：{rec.get('new_answer_head') or ''}\n\n"
            '只输出 JSON：{"equivalent": true|false}'
        )
        try:
            raw = _judge_call(prompt)
            m = _re.search(r'"equivalent"\s*:\s*(true|false)', raw)
            equivalent = (m.group(1) == "true") if m else None
            judge_raw = raw[:200]
        except Exception as exc:  # LLM 抖动不阻塞
            equivalent, judge_raw = None, f"{type(exc).__name__}: {str(exc)[:150]}"
        records.append({"sample_id": rec["sample_id"], "source": rec.get("source"),
                        "equivalent": equivalent, "judge_raw": judge_raw})
        print(f"[r12judge] {i + 1}/{len(sem)} sample_id={rec['sample_id']} equivalent={equivalent}", flush=True)
        if (i + 1) % 5 == 0 or i + 1 == len(sem):
            _dump(os.path.join(OUT_DIR, "r24_r12_semantic_judge.json"), {
                "ran_at": datetime.now(timezone.utc).isoformat(),
                "reuses": "r12 dualrun_results.json semantic 30 条（old/new_answer_head 存档）+ dualrun_samples.json 样本清单",
                "judge_model_note": ("r12 原 judge=model fast（minimax-m3@dashscope）本轮 401 invalid_api_key "
                                     "（.env LLM_BASE_URL 默认 dashscope + LLM_API_KEY=deepseek key 错配）→ "
                                     "改 model strong（deepseek-flash@api.deepseek.com，LLM 周配额已重置）"),
                "caveats": [
                    "old 侧 = r12 当时 429 降级规则答案（非真实生成）——本补验判定的是『降级规则答案 vs 新路径 LLM 答案』语义面",
                    "old/new 答案均为 200 字符 head 存档（r12 semantic_pair 截断），judge 输入非全文",
                ],
                "n": len(records),
                "equivalent": sum(1 for x in records if x["equivalent"] is True),
                "not_equivalent": sum(1 for x in records if x["equivalent"] is False),
                "judge_failed": sum(1 for x in records if x["equivalent"] is None),
                "wall_seconds": round(time.perf_counter() - t0, 1),
                "records": records,
            })
    summary = {k: v for k, v in json.loads(json.dumps({
        "n": len(records),
        "equivalent": sum(1 for x in records if x["equivalent"] is True),
        "not_equivalent": sum(1 for x in records if x["equivalent"] is False),
        "judge_failed": sum(1 for x in records if x["equivalent"] is None),
        "wall_seconds": round(time.perf_counter() - t0, 1),
    })) .items()}
    print(f"[r12judge] DONE n={summary['n']} eq={summary['equivalent']} "
          f"neq={summary['not_equivalent']} failed={summary['judge_failed']}")
    return summary


# ============================================================
# Phase B2：hyde-on 对照臂（realtime，仅对离线 diff 出的改写子集）
# ============================================================
async def phase_hyde(tag: str) -> dict:
    """hyde on/off 对照：基线=Phase A（use_hyde=False，契约口径）；实验臂=改写子集按
    生产链路真实顺序（rewrite → recall → rerank）重跑。只对照改写子集（未改写 query 两臂逐位同串）。"""
    from app.auth import UserRole
    from app.chat.retriever import (_milvus_hybrid_search_safe, _rerank_docs,
                                    _rewrite_query_by_hyde_if_enabled)
    from r20min_run import _match_golden

    with open(os.path.join(OUT_DIR, f"r24_rank_probe_{tag}.json"), encoding="utf-8") as f:
        base = json.load(f)
    base_rows = {r["idx"]: r for r in base["per_query"]}
    cases = _load_cases()
    changed = [(idx, case) for idx, case in enumerate(cases)
               if base["hyde_grid"]["n_changed"] and any(c["idx"] == idx for c in base["hyde_grid"]["changed_cases"])]
    rows: list[dict] = []
    t0 = time.perf_counter()
    for k, (idx, case) in enumerate(changed):
        rw, done, _deg = _rewrite_query_by_hyde_if_enabled(case["query"], use_hyde=True)
        milvus_docs, _degrade, _health = await asyncio.to_thread(
            _milvus_hybrid_search_safe, rw, user_id=1, role=UserRole.STUDENT, top_k=TOP_K_EVAL,
        )
        seen: set[str] = set()
        merged = []
        for d in milvus_docs:
            if not d.doc_id or d.doc_id in seen:
                continue
            seen.add(d.doc_id)
            merged.append(d)
        recall_ids = [d.doc_id for d in merged]
        recall_docs = [{"chunk_id": d.doc_id, "content": d.content} for d in merged]
        gt_r, _via_r = _match_golden(case, recall_docs)
        recall_rank = recall_ids.index(gt_r) + 1 if gt_r in recall_ids else None
        await _rerank_docs(rw, merged)
        full_ids = [d.doc_id for d in merged]
        full_docs = [{"chunk_id": d.doc_id, "content": d.content} for d in merged]
        gt_id, _via = _match_golden(case, full_docs)
        rerank_rank = full_ids.index(gt_id) + 1 if gt_id in full_ids else None
        b = base_rows[idx]
        rows.append({"idx": idx, "query": case["query"], "rewritten": rw,
                     "base_recall_rank": b["recall_rank"], "hyde_recall_rank": recall_rank,
                     "base_rerank_rank": b["rerank_rank"], "hyde_rerank_rank": rerank_rank})
        print(f"[hyde:{tag}] {k + 1}/{len(changed)} idx={idx} recall {b['recall_rank']}->{recall_rank} "
              f"rerank {b['rerank_rank']}->{rerank_rank}", flush=True)

    def _metrics(ranks: list, key: str) -> dict:
        n = len(ranks)
        hit = sum(1 for r in ranks if r[key] is not None and r[key] <= TOP_K_EVAL)
        mrr = sum(1.0 / r[key] for r in ranks if r[key] is not None and r[key] <= TOP_K_EVAL)
        cov = sum(1 for r in ranks if r[key] is not None)
        return {"hit@5": round(hit / n, 4), "mrr@5": round(mrr / n, 4), f"cover": cov,
                "n": n}
    rep = {
        "tag": tag, "ran_at": datetime.now(timezone.utc).isoformat(),
        "mode": ("hyde on/off 对照臂（生产链路真实顺序 rewrite→recall150→rerank；"
                 "仅离线 diff 改写子集；基线=r24_rank_probe 同 idx 记录, use_hyde=False 契约口径）"),
        "n_changed_subset": len(changed),
        "baseline_hyde_off": {"rerank": _metrics(rows, "base_rerank_rank"),
                              "recall": _metrics(rows, "base_recall_rank")},
        "arm_hyde_on": {"rerank": _metrics(rows, "hyde_rerank_rank"),
                        "recall": _metrics(rows, "hyde_recall_rank")},
        "wall_seconds": round(time.perf_counter() - t0, 1),
        "per_query": rows,
    }
    _dump(os.path.join(OUT_DIR, f"r24_hyde_{tag}.json"), rep)
    print(f"[hyde:{tag}] OFF rerank hit@5={rep['baseline_hyde_off']['rerank']['hit@5']} "
          f"mrr@5={rep['baseline_hyde_off']['rerank']['mrr@5']} | "
          f"ON hit@5={rep['arm_hyde_on']['rerank']['hit@5']} "
          f"mrr@5={rep['arm_hyde_on']['rerank']['mrr@5']} (n={len(changed)})")
    return rep


# ============================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="R24 排名质量诊断探针")
    ap.add_argument("--mode", default="rank", choices=["rank", "grid", "hyde", "r12-judge", "all-rank-grid"])
    ap.add_argument("--tag", default="probe64")
    args = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    if args.mode in ("rank", "all-rank-grid"):
        asyncio.run(phase_a(args.tag))
    if args.mode in ("grid", "all-rank-grid"):
        asyncio.run(phase_b(args.tag))
    if args.mode == "hyde":
        asyncio.run(phase_hyde(args.tag))
    if args.mode == "r12-judge":
        phase_r12_judge()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
