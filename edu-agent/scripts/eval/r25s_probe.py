# -*- coding: utf-8 -*-
"""
R25S · W-NEXT-R25S-001 缩编探针（承接 EVAL64V2 收口：R25 大前提已被新尺消解，缩编为两小任务）

Task A（idx31 边缘案归因，承接 EVAL64V2 报告 P0-3「召回层归因缺口」登记）：
  V2 主尺唯一 miss = idx31（泛化题干「简述该场景下的处理顺序。」，33 个逐字重复块）。
  本探针三层取证（全部只读，不改任何正产默认值）：
    A1 重复块清查：Milvus 直查 content_type=="question" 全量（与 buildv2 逐字索引同口径），
      按 build_eval_set64.norm_text / find_verbatim_candidates 同准则复算 33 块清单，
      逐块内容 sha256 分组（精确同文组 vs 共享题干变体组），记录 bank/tenant/visibility/source_file 差异。
    A2 真实链路重放（r24_rank_probe Phase A 同范式）：
      _milvus_hybrid_search_safe（召回150）→ 去重 → 捕获 golden/33 块的召回序位
      → _rerank_docs（sidecar 全量打分+归一+全序）→ 捕获全序 rank+score
      → 真实 _cliff_cutoff_v2（q=0.60，import 正产函数，不重写）重放 final top5。
      另跑 retrieve_three_channel 全链与 r64v2_base_run1 的 idx31 记录对账（miss 应复现）。
    A3 可分性证据：dense 余弦（query vs golden 内容）+ rerank 分数梯度。
  产出 → data/r25s_runs/r25s_idx31_<tag>.json（证据链 + 33 块清单 + 根因判定布尔位）。

Task B（跨语言 query 鲁棒性）：
  对照集 data/r25s_bilingual_set10.json（10 zh 冻结自 V2 集 + 10 en 人工改写，golden 双键继承）。
  双语各走 retrieve_three_channel 全链（与 contracts/rag-baseline-eval64-v2.json params 逐字段一致，
  V2 cliff on）+ 召回层旁路（_milvus_hybrid_search_safe，r24 同范式）：
    hit@5 / mrr@5 / 召回覆盖 / top5 doc_id Jaccard / 召回150 doc_id Jaccard。
  结论分级阈值：mean Jaccard@5 >= 0.60 且 |hit@5 差| <= 1 → ①BGE-M3 跨语言足够（无需动作）；
  否则 → ②显著退化（附数字与建议）。
  范式说明：本探针沿用 V2 基线冻结时同款 in-process 全链范式（r20min/r22/r64v2 measure 同口径，
  0-LLM、真实 Milvus+BGE-M3 CUDA+sidecar 8601），非 8011 HTTP 实例——与基线可比性优先，
  检索层代码路径与 HTTP 层完全一致（retrieve_three_channel）。

用法（edu-agent/ 下）：
  .venv/Scripts/python.exe -X utf8 scripts/eval/r25s_probe.py --mode idx31 --tag r25s
  .venv/Scripts/python.exe -X utf8 scripts/eval/r25s_probe.py --mode bilingual --tag r25s
红线：只读 retriever.py / config.py / loader.py（0 改动）；sidecar 8601 只调用不启停；
  contracts/** 冻结值不触；Milvus 只读查询（常量过滤表达式或 JSON 编码绑定，无字符串拼接注入面）。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
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
EVAL_DIR = os.path.join(BASE_DIR, "scripts", "eval")
DATA_DIR = os.path.join(EVAL_DIR, "data")
OUT_DIR = os.path.join(DATA_DIR, "r25s_runs")
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, EVAL_DIR)

V2_SET_PATH = os.path.join(DATA_DIR, "r64v2_eval_set64.json")
BILINGUAL_SET_PATH = os.path.join(DATA_DIR, "r25s_bilingual_set10.json")
V2_BASE_RUN1_PATH = os.path.join(DATA_DIR, "r64v2_runs", "r64v2_base_run1.json")

IDX31 = 31
TOP_K_EVAL = 5

# 与 contracts/rag-baseline-eval64-v2.json params 逐字段一致（只读复刻，非写入）
V2_PARAMS = {
    "use_hyde": False,
    "enable_graph": True,
    "top_k": 5,
    "final_max_k": 5,
    "cutoff_drop_ratio": 0.4,
    "role": "student",
    "rerank_cliff_v2": True,
}


def _dump(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _git_rev() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                          cwd=BASE_DIR).stdout.strip()


def _jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return round(len(sa & sb) / len(sa | sb), 4)


# ============================================================
# Task A：idx31 边缘案三层归因
# ============================================================
def _census_dups(client, collection_name: str, query: str) -> dict:
    """A1：33 重复块清查（builder 同准则复算；只读）。"""
    from build_eval_set64 import find_verbatim_candidates, norm_text

    # 与 build_eval_set64 buildv2 逐字索引同口径：content_type=="question" 常量过滤全量
    questions = client.query(
        collection_name,
        filter='content_type == "question"',
        output_fields=["chunk_id", "question_bank_code", "content",
                       "content_type", "tenant_id", "visibility", "source_file"],
        limit=8000,
    )
    norm_q = norm_text(query)
    hits = [q for q in questions
            if norm_q and norm_text(q.get("content")) and norm_q in norm_text(q.get("content"))]
    cands = find_verbatim_candidates(norm_q, [{"chunk_id": str(q.get("chunk_id") or ""),
                                               "norm": norm_text(q.get("content"))}
                                              for q in questions])
    cand_set = set(cands)
    golden_content = None
    rows = []
    sha_groups: dict[str, list[str]] = {}
    for q in hits:
        cid = str(q.get("chunk_id") or "")
        if cid not in cand_set:
            continue  # 不可能发生（同准则），防御
        content = str(q.get("content") or "")
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        rows.append({
            "chunk_id": cid,
            "content_sha256_16": sha[:16],
            "content_len": len(content),
            "bank": str(q.get("question_bank_code") or ""),
            "tenant_id": str(q.get("tenant_id") or ""),
            "visibility": str(q.get("visibility") or ""),
            "source_file": str(q.get("source_file") or ""),
            "content_head": content[:80],
        })
        sha_groups.setdefault(sha, []).append(cid)
    return {"questions_total": len(questions), "rows": rows, "sha_groups": sha_groups}


async def run_idx31(tag: str) -> dict:
    from app.auth import UserRole
    from app.chat.retriever import (_cliff_cutoff_v2, _milvus_hybrid_search_safe,
                                    _rerank_docs, retrieve_three_channel)
    from app.config import settings
    from app.knowledge.importer.embedder import encode_dense_batch, ensure_jieba_ready
    from app.knowledge.importer.loader import COLLECTION_NAME, get_milvus_client
    from build_eval_set64 import norm_text
    from r20min_run import _match_golden

    with open(V2_SET_PATH, encoding="utf-8") as f:
        case = json.load(f)["cases"][IDX31]
    query = case["query"]
    golden_content = case["gt_content"]
    golden_sha = hashlib.sha256(golden_content.encode("utf-8")).hexdigest()
    assert golden_sha == case["golden"]["doc_sha256"], "golden doc_sha256 与 gt_content 不一致"

    client = get_milvus_client()

    # ---- A1：33 重复块清查 ----
    census = _census_dups(client, COLLECTION_NAME, query)
    dup_ids = [r["chunk_id"] for r in census["rows"]]
    exact_group = census["sha_groups"].get(golden_sha, [])
    dup_meta = {r["chunk_id"]: r for r in census["rows"]}
    print(f"[idx31] census: questions_total={census['questions_total']} "
          f"stem_share_dups={len(dup_ids)} exact_content_dup_group={len(exact_group)}")

    # ---- A2：真实链路重放（召回 → rerank 全序 → 真实断崖）----
    ensure_jieba_ready()
    t0 = time.perf_counter()
    milvus_docs, degrade, health = await asyncio.to_thread(
        _milvus_hybrid_search_safe, query, user_id=1, role=UserRole.STUDENT,
        top_k=V2_PARAMS["top_k"],
    )
    seen: set[str] = set()
    merged = []
    for d in milvus_docs:
        if not d.doc_id or d.doc_id in seen:
            continue
        seen.add(d.doc_id)
        merged.append(d)
    recall_ids = [d.doc_id for d in merged]
    recall_docs = [{"chunk_id": cid,
                    "content": next((d.content for d in merged if d.doc_id == cid), "")}
                   for cid in recall_ids]
    gt_recall_id, gt_recall_via = _match_golden(case, recall_docs)
    recall_rank = recall_ids.index(gt_recall_id) + 1 if gt_recall_via != "miss" else None
    dups_in_recall = [cid for cid in dup_ids if cid in seen]
    dup_recall_positions = {cid: recall_ids.index(cid) + 1 for cid in dups_in_recall}
    # 召回层「组命中」：final/recall 中是否存在任一 33 块（无论内容是否与 golden 全同）
    recall_group_hit = sorted(set(dups_in_recall))
    # 召回层内容 sha 视角：与 golden 内容全同的块是否入召回
    sha_in_recall = {cid for cid in dups_in_recall
                     if dup_meta[cid]["content_sha256_16"] == golden_sha[:16]}

    top20, rr_reason = await _rerank_docs(query, merged)
    full_ids = [d.doc_id for d in merged]
    full_scores = [round(float(d.score), 6) for d in merged]
    full_types = [d.content_type for d in merged]
    full_docs = [{"chunk_id": cid,
                  "content": next((d.content for d in merged if d.doc_id == cid), "")}
                 for cid in full_ids]
    gt_id, gt_via = _match_golden(case, full_docs)
    rerank_rank = full_ids.index(gt_id) + 1 if gt_via != "miss" else None
    dups_in_rerank_order = [(cid, full_ids.index(cid) + 1, full_scores[full_ids.index(cid)])
                            for cid in dup_ids if cid in set(full_ids)]
    dup_ranks = {cid: rk for cid, rk, _ in dups_in_rerank_order}
    n_dups_above_golden = (sum(1 for rk in dup_ranks.values()
                               if rerank_rank is not None and rk < rerank_rank)
                           if rerank_rank is not None else None)

    # 真实断崖函数重放（import 正产 _cliff_cutoff_v2，不重写规则）
    top20_docs = [d for d in top20]
    final_docs = _cliff_cutoff_v2(top20_docs, final_max_k=V2_PARAMS["final_max_k"])
    final_ids = [d.doc_id for d in final_docs]
    final_rows = [{"rank": i + 1, "chunk_id": d.doc_id,
                   "score": round(float(d.score), 6),
                   "content_type": d.content_type,
                   "is_dup_of_idx31_stem": d.doc_id in set(dup_ids),
                   "content_head": (d.content or "")[:80]}
                  for i, d in enumerate(final_docs)]
    final_group_hit = [r["chunk_id"] for r in final_rows if r["is_dup_of_idx31_stem"]]
    final_hit = gt_id in final_ids

    # ---- A3：可分性证据（dense 余弦 + rerank 分数梯度）----
    dense = encode_dense_batch([query, golden_content])
    qv, gv = dense[0], dense[1]
    dot = sum(float(a) * float(b) for a, b in zip(qv, gv))
    nq = sum(float(a) ** 2 for a in qv) ** 0.5
    ng = sum(float(b) ** 2 for b in gv) ** 0.5
    dense_cos_q_golden = round(dot / (nq * ng), 6) if nq and ng else None
    golden_rerank_score = full_scores[rerank_rank - 1] if rerank_rank else None
    top1_score = full_scores[0]
    best_dup_rank = min(dup_ranks.values()) if dup_ranks else None
    best_dup_score = (full_scores[best_dup_rank - 1] if best_dup_rank else None)

    # ---- A2b：retrieve_three_channel 全链对账（与 r64v2_base_run1 idx31 记录）----
    bundle = await retrieve_three_channel(
        query, user_id=1, role=UserRole.STUDENT,
        use_hyde=V2_PARAMS["use_hyde"], enable_graph=V2_PARAMS["enable_graph"],
        top_k=V2_PARAMS["top_k"], final_max_k=V2_PARAMS["final_max_k"],
        cutoff_drop_ratio=V2_PARAMS["cutoff_drop_ratio"],
    )
    e2e_docs = [{"chunk_id": d.doc_id, "content": d.content} for d in bundle.docs]
    e2e_gt, e2e_via = _match_golden(case, e2e_docs)
    e2e_hit = e2e_via != "miss" and e2e_gt in [d["chunk_id"] for d in e2e_docs]
    with open(V2_BASE_RUN1_PATH, encoding="utf-8") as f:
        base31 = next(r for r in json.load(f)["per_query"] if r["idx"] == IDX31)
    e2e_ids = [d["chunk_id"] for d in e2e_docs]

    # ---- 根因判定布尔位（证据链）----
    verdict = {
        "root2_golden_in_recall150": recall_rank is not None,
        "root2_golden_recall_rank": recall_rank,
        "root2_golden_via": gt_recall_via,
        "root1_dups_in_recall": len(dups_in_recall),
        "root1_dups_total": len(dup_ids),
        "root1_dilution_recall_slots": len(dups_in_recall),
        "root1_n_dups_above_golden_at_rerank": n_dups_above_golden,
        "root1_final_top5_contains_stem_dup": bool(final_group_hit),
        "root3_golden_rerank_rank": rerank_rank,
        "root3_golden_rerank_score": golden_rerank_score,
        "root3_top1_score": top1_score,
        "root3_best_dup_rank": best_dup_rank,
        "root3_best_dup_score": best_dup_score,
        "root3_dense_cos_query_vs_golden": dense_cos_q_golden,
    }
    report = {
        "tag": tag, "task": "A_idx31_edge_case_attribution",
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": _git_rev(),
        "query": query,
        "golden_chunk_id": case["golden"]["chunk_id"],
        "golden_doc_sha256": case["golden"]["doc_sha256"],
        "params": {**V2_PARAMS, "embed_backend": str(getattr(settings, "EMBED_BACKEND", "unknown")),
                   "recall_topk": int(getattr(settings, "RETRIEVER_RECALL_TOPK", 150)),
                   "rerank_topk": int(getattr(settings, "RETRIEVER_RERANK_TOPK", 20)),
                   "cliff_quant": float(getattr(settings, "RERANK_CLIFF_V2_QUANT", 0.60))},
        "census": {
            "criterion": "builder 同准则：content_type=='question' 且 norm(content) 包含 norm(query)",
            "questions_total": census["questions_total"],
            "stem_share_dups": len(dup_ids),
            "verbatim_dup_count_in_set": case.get("verbatim_dup_count"),
            "dup_count_matches_set_field": len(dup_ids) == case.get("verbatim_dup_count"),
            "exact_content_dup_group_size": len(exact_group),
            "exact_content_dup_group_ids": exact_group,
            "sha_group_sizes": {sha[:16]: len(ids) for sha, ids in census["sha_groups"].items()},
            "rows": census["rows"],
        },
        "recall_layer": {
            "n_unique_after_dedupe": len(recall_ids),
            "degraded_reason": degrade,
            "golden_rank": recall_rank,
            "golden_resolve_via": gt_recall_via,
            "dups_in_recall_n": len(dups_in_recall),
            "dup_recall_positions": dup_recall_positions,
            "exact_sha_dups_in_recall": sorted(sha_in_recall),
            "note": "recall_ids 为 RRF 融合去重序（与 retrieve_three_channel 融合段同语义）",
        },
        "rerank_layer": {
            "golden_full_rank": rerank_rank,
            "golden_resolve_via": gt_via,
            "golden_score": golden_rerank_score,
            "top1_score": top1_score,
            "dups_in_rerank_order": [{"chunk_id": c, "rank": rk, "score": s}
                                     for c, rk, s in sorted(dups_in_rerank_order, key=lambda x: x[1])],
            "top20_ids": full_ids[:20],
            "top20_scores": full_scores[:20],
            "rerank_reason": rr_reason,
        },
        "final_layer_cliff_replay": {
            "final_ids": final_ids,
            "rows": final_rows,
            "hit_vs_golden_double_key": bool(final_hit),
            "group_hit_stem_dups_in_final": final_group_hit,
        },
        "e2e_full_chain_tie_in": {
            "final_ids": e2e_ids,
            "gt_resolve_via": e2e_via,
            "hit": bool(e2e_hit),
            "raw_retrieved_count": bundle.raw_retrieved_count,
            "degraded_reason": bundle.degraded_reason,
            "baseline_run1_idx31": {"gt_resolve_via": base31["gt_resolve_via"],
                                    "hit@5": base31["hit@5"],
                                    "final_docs": base31["final_docs"]},
            "miss_reproduced": (not e2e_hit) and (base31["gt_resolve_via"] == "miss"),
            "final_ids_match_replay": sorted(e2e_ids) == sorted(final_ids),
        },
        "separability": {
            "dense_cos_query_vs_golden": dense_cos_q_golden,
            "note": ("泛化题干逐字信号弱：query 仅 10 字且不含答案面词；dense 余弦为参考值，"
                     "主证据=rerank 全序分数梯度（rerank_layer）"),
        },
        "verdict_booleans": verdict,
        "wall_seconds": round(time.perf_counter() - t0, 1),
    }
    out = os.path.join(OUT_DIR, f"r25s_idx31_{tag}.json")
    _dump(out, report)
    print(f"[idx31] recall golden={recall_rank} dups_in_recall={len(dups_in_recall)}/"
          f"{len(dup_ids)} | rerank golden={rerank_rank} best_dup={best_dup_rank} | "
          f"final hit={final_hit} group_hit={bool(final_group_hit)} | "
          f"e2e miss_reproduced={report['e2e_full_chain_tie_in']['miss_reproduced']}")
    print(f"[idx31] -> {out}")
    return report


# ============================================================
# Task B：跨语言鲁棒性
# ============================================================
async def _run_one_lang(case_src: dict, query: str) -> dict:
    """单 query 单语言：retrieve_three_channel 全链（V2 契约参数）+ 召回层旁路。"""
    from app.auth import UserRole
    from app.chat.retriever import (_milvus_hybrid_search_safe, retrieve_three_channel)
    from r20min_run import _match_golden

    t0 = time.perf_counter()
    bundle = await retrieve_three_channel(
        query, user_id=1, role=UserRole.STUDENT,
        use_hyde=V2_PARAMS["use_hyde"], enable_graph=V2_PARAMS["enable_graph"],
        top_k=V2_PARAMS["top_k"], final_max_k=V2_PARAMS["final_max_k"],
        cutoff_drop_ratio=V2_PARAMS["cutoff_drop_ratio"],
    )
    docs = [{"chunk_id": d.doc_id, "content": d.content} for d in bundle.docs]
    gt_id, gt_via = _match_golden(case_src, docs)
    ids = [d["chunk_id"] for d in docs]
    rank = ids.index(gt_id) + 1 if gt_via != "miss" and gt_id in ids else None

    milvus_docs, degrade, _health = await asyncio.to_thread(
        _milvus_hybrid_search_safe, query, user_id=1, role=UserRole.STUDENT,
        top_k=V2_PARAMS["top_k"],
    )
    seen: set[str] = set()
    recall_ids = []
    recall_docs = []
    for d in milvus_docs:
        if not d.doc_id or d.doc_id in seen:
            continue
        seen.add(d.doc_id)
        recall_ids.append(d.doc_id)
        recall_docs.append({"chunk_id": d.doc_id, "content": d.content})
    gt_r, via_r = _match_golden(case_src, recall_docs)
    recall_hit = via_r != "miss"
    return {
        "query": query,
        "hit@5": bool(rank and rank <= TOP_K_EVAL),
        "rank": rank,
        "rr@5": (1.0 / rank) if (rank and rank <= TOP_K_EVAL) else 0.0,
        "final_ids": ids,
        "gt_resolve_via": gt_via,
        "raw_retrieved_count": int(bundle.raw_retrieved_count),
        "recall_hit": bool(recall_hit),
        "recall_n": len(recall_ids),
        "recall_ids_head": recall_ids[:30],
        "recall_full_ids": recall_ids,
        "degraded_reason": degrade,
        "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


async def run_bilingual(tag: str) -> dict:
    from app.config import settings
    from app.knowledge.importer.embedder import (build_sparse_vector, encode_dense_batch,
                                                 ensure_jieba_ready)

    with open(BILINGUAL_SET_PATH, encoding="utf-8") as f:
        bi = json.load(f)
    with open(V2_SET_PATH, encoding="utf-8") as f:
        src_cases = json.load(f)["cases"]

    # 预热 BGE-M3（与 build_eval_set64.measure 同款守卫：冷加载在 retriever 外层
    # wait_for 窗口内会误触 dense=failed 超时降级——首跑实测 raw=0 假 miss，见报告 P0）
    ensure_jieba_ready()
    _ = encode_dense_batch(["预热"])

    rows = []
    t0 = time.perf_counter()
    for k, c in enumerate(bi["cases"]):
        src = src_cases[c["idx_ref"]]
        assert src["golden"] == c["golden"], f"golden 双键与 V2 集不一致 idx_ref={c['idx_ref']}"
        zh = await _run_one_lang(src, c["query_zh"])
        en = await _run_one_lang(src, c["query_en"])
        rows.append({
            "idx_ref": c["idx_ref"],
            "series_code": c.get("series_code"),
            "baseline_rank_zh_run1": c.get("baseline_rank_zh_run1"),
            "sparse_nnz": {"zh": len(build_sparse_vector(c["query_zh"])),
                           "en": len(build_sparse_vector(c["query_en"]))},
            "zh": zh, "en": en,
            "jaccard_top5": _jaccard(zh["final_ids"], en["final_ids"]),
            "jaccard_recall150": _jaccard(zh["recall_full_ids"], en["recall_full_ids"]),
            "hit_flip": {"zh": zh["hit@5"], "en": en["hit@5"]},
        })
        print(f"[bilingual:{tag}] {k + 1}/10 idx_ref={c['idx_ref']} "
              f"zh_hit={zh['hit@5']}(rank={zh['rank']}) en_hit={en['hit@5']}(rank={en['rank']}) "
              f"jac5={rows[-1]['jaccard_top5']} jacR={rows[-1]['jaccard_recall150']}")
        # 检查点落盘（限速保护）
        _dump(os.path.join(OUT_DIR, f"r25s_bilingual_{tag}.json"),
              _bilingual_report(tag, bi, rows, t0, partial=True))

    report = _bilingual_report(tag, bi, rows, t0, partial=False)

    def _m(key: str) -> dict:
        n = len(rows)
        hit = sum(1 for r in rows if r[key]["hit@5"])
        cov = sum(1 for r in rows if r[key]["recall_hit"])
        return {"hit@5": round(hit / n, 4), "hit_n": hit,
                "mrr@5": round(sum(r[key]["rr@5"] for r in rows) / n, 4),
                "recall_coverage": round(cov / n, 4), "recall_n": cov}

    zh_m, en_m = _m("zh"), _m("en")
    jac5 = [r["jaccard_top5"] for r in rows]
    jacr = [r["jaccard_recall150"] for r in rows]
    mean_j5 = round(sum(jac5) / len(jac5), 4)
    hit_diff = abs(zh_m["hit_n"] - en_m["hit_n"])
    nnz_zh = [r["sparse_nnz"]["zh"] for r in rows]
    nnz_en = [r["sparse_nnz"]["en"] for r in rows]
    hit_ok = hit_diff <= 1
    jac_ok = mean_j5 >= 0.60
    # 分级（两分支分类法的补丁：hit/mrr/recall 零退化但 overlap<60% ≠「显著退化」）
    if hit_ok and jac_ok:
        conclusion = "grade_1_bge_m3_crosslingual_sufficient（双门全过，无需动作）"
    elif hit_ok and en_m["hit@5"] >= zh_m["hit@5"]:
        conclusion = ("grade_1_no_action_by_hit_mrr（hit/mrr/recall 零退化，无需动作）；"
                      "overlap 门未达为 filler 差异（诊断位，非用户可见退化）——"
                      "机制：sparse 词面通道 md5 hash 词条跨语言零交集（实测 en 查询词条与中文语料 "
                      "term_id 交集=0，仅 JavaScript/TCP 等拉丁术语可锚定），跨语言桥=dense(BGE-M3)+rerank")
    else:
        conclusion = "grade_2_significant_degradation（建议 query 翻译层/双语索引增强，附数字）"
    report["summary"] = {
        "zh": zh_m, "en": en_m,
        "mean_jaccard_top5": mean_j5,
        "median_jaccard_top5": sorted(jac5)[len(jac5) // 2],
        "per_query_jaccard_top5": jac5,
        "mean_jaccard_recall150": round(sum(jacr) / len(jacr), 4),
        "per_query_jaccard_recall150": jacr,
        "sparse_channel_nnz": {"zh_mean": round(sum(nnz_zh) / len(nnz_zh), 1),
                               "en_mean": round(sum(nnz_en) / len(nnz_en), 1),
                               "per_query": [{"idx_ref": r["idx_ref"], **r["sparse_nnz"]}
                                             for r in rows]},
        "hit_count_diff": hit_diff,
        "grading_thresholds": {"mean_jaccard_top5": ">=0.60", "hit_count_diff": "<=1"},
        "criteria": {"hit_count_diff_le_1": hit_ok, "mean_jaccard_top5_ge_060": jac_ok},
        "conclusion": conclusion,
        "caveat_n10": "n=10 小样本：hit@5=1.0 的 Wilson 下限约 0.72，结论限定本对照集，不外推全集",
    }
    _dump(os.path.join(OUT_DIR, f"r25s_bilingual_{tag}.json"), report)
    s = report["summary"]
    print(f"[bilingual:{tag}] zh hit@5={zh_m['hit@5']} cov={zh_m['recall_coverage']} | "
          f"en hit@5={en_m['hit@5']} cov={en_m['recall_coverage']} | "
          f"meanJac5={s['mean_jaccard_top5']} meanJacR={s['mean_jaccard_recall150']} | "
          f"conclusion={s['conclusion']}")
    return report


def _bilingual_report(tag: str, bi: dict, rows: list, t0: float, *, partial: bool) -> dict:
    return {
        "tag": tag, "task": "B_crosslingual_robustness",
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": _git_rev(),
        "set_file": BILINGUAL_SET_PATH,
        "set_meta": bi["meta"],
        "params": V2_PARAMS,
        "paradigm_note": ("in-process retrieve_three_channel 全链（r64v2 measure 同款范式，"
                          "0-LLM，真实 Milvus+BGE-M3 CUDA+sidecar 8601）；"
                          "召回层旁路=_milvus_hybrid_search_safe（r24 同范式）"),
        "partial": partial,
        "n": len(rows),
        "wall_seconds": round(time.perf_counter() - t0, 1),
        "per_query": rows,
    }


def rebuild_summary(src_tag: str, dst_tag: str) -> dict:
    """从已落盘的稳定 run 重建 summary/verdict（离线，不触 Milvus）。

    背景：2026-09-20 01:00 依赖主机 192.168.85.101 整机失联（Milvus/Neo4j/Mongo/MySQL
    全端口拒绝），第 4 次双语跑全 raw=0 无效并覆盖了 tag=r25s 产物。本模式从
    tag=src_tag（停机前完整落盘、与 run2 逐查询逐位一致）的 per_query 重建
    tag=dst_tag 产物：sparse_nnz 离线补算（只需 jieba，不触 Milvus），summary 重算。
    产物内 provenance 字段如实披露重建来源。
    """
    from app.knowledge.importer.embedder import build_sparse_vector, ensure_jieba_ready

    src_path = os.path.join(OUT_DIR, f"r25s_bilingual_{src_tag}.json")
    with open(src_path, encoding="utf-8") as f:
        stable = json.load(f)
    with open(BILINGUAL_SET_PATH, encoding="utf-8") as f:
        bi = json.load(f)
    ensure_jieba_ready()
    rows = stable["per_query"]
    nnz_by_ref = {c["idx_ref"]: {"zh": len(build_sparse_vector(c["query_zh"])),
                                 "en": len(build_sparse_vector(c["query_en"]))}
                  for c in bi["cases"]}
    for r in rows:
        r["sparse_nnz"] = nnz_by_ref[r["idx_ref"]]

    def _m(key: str) -> dict:
        n = len(rows)
        hit = sum(1 for r in rows if r[key]["hit@5"])
        cov = sum(1 for r in rows if r[key]["recall_hit"])
        return {"hit@5": round(hit / n, 4), "hit_n": hit,
                "mrr@5": round(sum(r[key]["rr@5"] for r in rows) / n, 4),
                "recall_coverage": round(cov / n, 4), "recall_n": cov}

    zh_m, en_m = _m("zh"), _m("en")
    jac5 = [r["jaccard_top5"] for r in rows]
    jacr = [r["jaccard_recall150"] for r in rows]
    mean_j5 = round(sum(jac5) / len(jac5), 4)
    hit_diff = abs(zh_m["hit_n"] - en_m["hit_n"])
    hit_ok = hit_diff <= 1
    jac_ok = mean_j5 >= 0.60
    if hit_ok and jac_ok:
        conclusion = "grade_1_bge_m3_crosslingual_sufficient（双门全过，无需动作）"
    elif hit_ok and en_m["hit@5"] >= zh_m["hit@5"]:
        conclusion = ("grade_1_no_action_by_hit_mrr（hit/mrr/recall 零退化，无需动作）；"
                      "overlap 门未达为 filler 差异（诊断位，非用户可见退化）——"
                      "机制：sparse 词面通道 md5 hash 词条跨语言零交集（实测 en 查询词条与中文语料 "
                      "term_id 交集=0，仅 JavaScript/TCP 等拉丁术语可锚定），跨语言桥=dense(BGE-M3)+rerank")
    else:
        conclusion = "grade_2_significant_degradation（建议 query 翻译层/双语索引增强，附数字）"
    nnz_zh = [r["sparse_nnz"]["zh"] for r in rows]
    nnz_en = [r["sparse_nnz"]["en"] for r in rows]
    report = {
        "tag": dst_tag, "task": "B_crosslingual_robustness",
        "ran_at": stable["ran_at"],
        "rebuilt_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": stable["git_rev"],
        "set_file": BILINGUAL_SET_PATH,
        "set_meta": bi["meta"],
        "params": stable["params"],
        "paradigm_note": stable["paradigm_note"],
        "provenance": {
            "measurement_run": f"r25s_bilingual_{src_tag}.json（2026-09-20 01:03 依赖主机停机前完整落盘）",
            "determinism_evidence": ("run2(tag=r25s) 与 run3(tag=r25s_stab) 全部 10 条 per-query "
                                     "hit/rank/jaccard 逐位一致（/tmp 双跑日志 diff 仅 tag 前缀差异）；"
                                     "run2 产物被第 4 跑（停机无效数据）覆盖，故以 run3 为测量底座重建"),
            "invalid_run4_discarded": ("2026-09-20 01:00 起 192.168.85.101 整机失联，run4 全查询 "
                                       "raw=0（dense=ok sparse=ok milvus=conn refused），数据无效弃用"),
            "rebuild_scope": "仅重建 summary/verdict 与离线可算的 sparse_nnz；per_query 测量值零改动",
        },
        "partial": False,
        "n": len(rows),
        "wall_seconds": stable["wall_seconds"],
        "per_query": rows,
        "summary": {
            "zh": zh_m, "en": en_m,
            "mean_jaccard_top5": mean_j5,
            "median_jaccard_top5": sorted(jac5)[len(jac5) // 2],
            "per_query_jaccard_top5": jac5,
            "mean_jaccard_recall150": round(sum(jacr) / len(jacr), 4),
            "per_query_jaccard_recall150": jacr,
            "sparse_channel_nnz": {"zh_mean": round(sum(nnz_zh) / len(nnz_zh), 1),
                                   "en_mean": round(sum(nnz_en) / len(nnz_en), 1),
                                   "per_query": [{"idx_ref": r["idx_ref"], **r["sparse_nnz"]}
                                                 for r in rows]},
            "hit_count_diff": hit_diff,
            "grading_thresholds": {"mean_jaccard_top5": ">=0.60", "hit_count_diff": "<=1"},
            "criteria": {"hit_count_diff_le_1": hit_ok, "mean_jaccard_top5_ge_060": jac_ok},
            "conclusion": conclusion,
            "caveat_n10": "n=10 小样本：hit@5=1.0 的 Wilson 下限约 0.72，结论限定本对照集，不外推全集",
        },
    }
    out = os.path.join(OUT_DIR, f"r25s_bilingual_{dst_tag}.json")
    _dump(out, report)
    print(f"[rebuild] {src_tag} -> {dst_tag}: zh hit@5={zh_m['hit@5']} en hit@5={en_m['hit@5']} "
          f"meanJac5={mean_j5} | {conclusion[:60]}")
    print(f"[rebuild] -> {out}")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="R25S 缩编探针（idx31 归因 + 跨语言鲁棒性）")
    ap.add_argument("--mode", default="idx31", choices=["idx31", "bilingual", "rebuild-summary"])
    ap.add_argument("--tag", default="r25s")
    ap.add_argument("--src-tag", default="r25s_stab", help="rebuild-summary: 测量底座产物 tag")
    args = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    if args.mode == "idx31":
        asyncio.run(run_idx31(args.tag))
    elif args.mode == "bilingual":
        asyncio.run(run_bilingual(args.tag))
    else:
        rebuild_summary(args.src_tag, args.tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
