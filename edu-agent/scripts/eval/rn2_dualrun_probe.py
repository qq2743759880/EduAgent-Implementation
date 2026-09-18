# -*- coding: utf-8 -*-
"""R-N2 KG-3 GraphRAG 第四通道双跑对账探针（复用 R20-b/R20-min 双跑对账范式）。

口径（对齐 scripts/eval/r20min_run.py 测量仪，详档 reshape-r-kg planId §KG-3）：
- 样本：冻结评估集 scripts/eval/data/rag_eval_set32.json 全量 32 条（不重 build）。
- 每 query 走 retriever.retrieve_three_channel 完整链（Milvus hybrid 召回 150 →
  rerank 20 → 断崖截断 → final top5），在最终 docs 上算 hit_rate@5 / MRR@5。
- golden 双键解析复用 r20min_run._match_golden（chunk_id → id_map → doc_sha256）。
- 双跑：同一进程同批 query，先 KG_EXPAND_ENABLED=False（off 基线）再 =True（on），
  逐条登记 doc_ids 分歧与 intent（rule_router 确定性分类）；「on-off」差异即第四通道净效应。

登记指标（派单硬门）：
1. docs 分歧率：final top5 doc_ids 逐条不一致占比（当前 MENTIONS/RELATED=0 → 预期 0%）。
2. intent 分歧率：off vs on 两轮 classify_intent 不一致占比（通道在决策后、重排前 → 结构性 0）。
3. hit_rate@5 / mrr@5 双跑对比 + 对 R20 基线 0.9688 的 delta（不得退化）。
4. 通道观测：on 轮 kg_expand 并入数 / 降级原因（超时/熔断/断连）。

诚实登记红线：当前图谱 MENTIONS/RELATED 全 0（R-N1 已披露），预期「零分歧零增益」；
本探针禁造假增益，结果如实落盘。

用法（edu-agent/ 下，需 Milvus + Neo4j + rerank sidecar 8601 在线）：
  .venv/Scripts/python.exe scripts/eval/rn2_dualrun_probe.py            # 全量 32 条
  .venv/Scripts/python.exe scripts/eval/rn2_dualrun_probe.py --limit 3  # 冒烟

产物：
  scripts/eval/data/rn2_runs/rn2-dualrun-summary.json   汇总指标 + 门槛对照
  scripts/eval/data/rn2_runs/rn2-dualrun-results.json   逐样本双跑明细
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings  # noqa: E402

try:
    from _safeio import safe_w  # 直接运行（脚本目录在 sys.path）
except ImportError:  # 以包形式导入
    from scripts.eval._safeio import safe_w  # type: ignore[no-redef]

import r20min_run as base  # 复用 R20-min 冻结评估集 + golden 双键解析（范式复用，不改其行为）

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(BASE_DIR, "scripts", "eval", "data", "rn2_runs")
BASELINE_HIT_RATE = 0.9688  # R20/R03 冻结基线（blind-t14/critique-rounds 登记）


def _git_rev() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(BASE_DIR), text=True
        ).strip()
    except Exception:
        return "unknown"


def log(msg: str) -> None:
    print(f"[rn2 {datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _classify(query: str) -> str:
    """intent 代理：rule_router 确定性分类（0-LLM，双跑同输入必同输出）。"""
    try:
        from app.ai.rule_router import classify_intent

        return classify_intent(query) or "knowledge"
    except Exception:
        return "knowledge"


async def _run_batch(cases: list[dict], kg_expand_on: bool, limit: int | None) -> list[dict]:
    """单轮全链评估（retrieve_three_channel 实时端到端，与 r20min --mode eval 同口径）。"""
    from app.auth import UserRole
    from app.chat.rag_evaluator import evaluate_retrieval
    from app.chat.retriever import retrieve_three_channel

    settings.KG_EXPAND_ENABLED = bool(kg_expand_on)  # 灰度开关：进程内翻转（探针期，验后进程退出）
    log(f"KG_EXPAND_ENABLED={settings.KG_EXPAND_ENABLED} 起跑 {len(cases)} 条")
    results: list[dict] = []
    t0_wall = time.perf_counter()
    for i, case in enumerate(cases):
        t0 = time.perf_counter()
        bundle = await retrieve_three_channel(
            case["query"],
            user_id=1,
            role=UserRole.STUDENT,
            use_hyde=base.PARAMS["use_hyde"],
            enable_graph=base.PARAMS["enable_graph"],
            top_k=base.PARAMS["final_max_k"],
            final_max_k=base.PARAMS["final_max_k"],
            cutoff_drop_ratio=base.PARAMS["cutoff_drop_ratio"],
        )
        lat_ms = round((time.perf_counter() - t0) * 1000, 1)
        docs = [{"chunk_id": d.doc_id, "content": d.content, "score": d.score} for d in bundle.docs]
        gt_id, gt_via = base._match_golden(case, docs)
        m = evaluate_retrieval(case["query"], docs, [gt_id], k=base.TOP_K_EVAL)
        results.append({
            "idx": i,
            "query": case["query"],
            "golden_chunk_id": case["golden"]["chunk_id"],
            "gt_resolved_id": gt_id,
            "gt_resolve_via": gt_via,
            "hit": bool(m.hit_rate >= 1.0),
            "rr": m.mrr,
            "top5_ids": [d["chunk_id"] for d in docs[: base.TOP_K_EVAL]],
            "final_count": len(docs),
            "raw_retrieved_count": int(bundle.raw_retrieved_count or 0),
            "intent": _classify(case["query"]),
            "degraded_reason": bundle.degraded_reason,
            "kg_expand_reason": next(
                (p for p in (bundle.degraded_reason or "").split("；") if "kg_expand" in p), None
            ),
            "latency_ms": lat_ms,
        })
        if (i + 1) % 8 == 0 or i + 1 == len(cases):
            log(f"  进度 {i + 1}/{len(cases)}（{time.perf_counter() - t0_wall:.0f}s）")
    return results


async def run_probe(limit: int | None) -> int:
    # 环境自证（Milvus/Neo4j；sidecar 由 retriever 自行降级）
    import app.database as db

    db.init_milvus()
    try:
        db.init_neo4j()
        log(f"环境自证 OK：milvus={settings.MILVUS_URI} neo4j={settings.NEO4J_URI}")
    except Exception as exc:  # noqa: BLE001
        log(f"WARN Neo4j init 异常（通道将按 neo4j_not_connected 降级，继续）: {exc}")

    with open(base.EVAL_SET_PATH, encoding="utf-8") as f:
        eval_set = json.load(f)
    cases = eval_set["cases"]
    if limit:
        cases = cases[:limit]
    log(f"冻结评估集 {len(cases)} 条（rag_eval_set32.json，built_at={eval_set['meta']['built_at']}）")

    # ---- 预热（冒烟实测教训：进程首查 BGE-M3 冷加载 ~13s > Milvus 8s 预算 → off 轮
    #      假性「Milvus 检索超时」空 docs。双跑前循环 warmup 至单轮无超时（GPU 已热），
    #      off/on 同温起跑；warmup 不计入任何指标）----
    from app.auth import UserRole
    from app.chat.retriever import retrieve_three_channel

    t_w = time.perf_counter()
    for attempt in range(1, 4):
        b_w = await retrieve_three_channel(
            "warmup 线性代数特征值预热查询",
            user_id=1, role=UserRole.STUDENT,
            use_hyde=False, enable_graph=False,
            top_k=5, final_max_k=5, cutoff_drop_ratio=1.0,
        )
        deg = b_w.degraded_reason or ""
        if "Milvus" not in deg:
            break
        log(f"  warmup 第 {attempt} 轮未热透（{deg}），重试")
    log(f"warmup 完成（{time.perf_counter() - t_w:.1f}s，GPU/Milvus/sidecar 已热）")

    # 双跑：off → on（同进程同批同温；off 先跑确立基线，on 后跑测净效应）
    off = await _run_batch(cases, kg_expand_on=False, limit=limit)
    on = await _run_batch(cases, kg_expand_on=True, limit=limit)

    # ---- 对账 ----
    pairs = []
    for o, n in zip(off, on):
        assert o["idx"] == n["idx"]
        pairs.append({
            "idx": o["idx"],
            "query": o["query"],
            "intent_match": o["intent"] == n["intent"],
            "docs_match": o["top5_ids"] == n["top5_ids"],
            "off_top5": o["top5_ids"],
            "on_top5": n["top5_ids"],
            "off_hit": o["hit"], "on_hit": n["hit"],
            "off_rr": o["rr"], "on_rr": n["rr"],
            "off_degraded": o["degraded_reason"], "on_degraded": n["degraded_reason"],
            "off_lat_ms": o["latency_ms"], "on_lat_ms": n["latency_ms"],
        })
    n = len(pairs)
    intent_div = sum(1 for p in pairs if not p["intent_match"])
    docs_div = sum(1 for p in pairs if not p["docs_match"])
    hit_off = round(sum(p["off_hit"] for p in pairs) / n, 4)
    hit_on = round(sum(p["on_hit"] for p in pairs) / n, 4)
    mrr_off = round(sum(p["off_rr"] for p in pairs) / n, 4)
    mrr_on = round(sum(p["on_rr"] for p in pairs) / n, 4)
    kg_degrades = [p["on_degraded"] for p in pairs if p["on_degraded"] and "kg_expand" in p["on_degraded"]]

    summary = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": _git_rev(),
        "baseline_ref": {
            "hit_rate@5": BASELINE_HIT_RATE,
            "source": "R20-min 冻结基线（blind-t14-rag-e2e / critique-R03-R15b 登记）",
        },
        "params": {**base.PARAMS, "kg_expand": {
            "KG_EXPAND_ENABLED_off_then_on": True,
            "KG_EXPAND_SEED_TOPK": settings.KG_EXPAND_SEED_TOPK,
            "KG_EXPAND_HOPS": settings.KG_EXPAND_HOPS,
            "KG_EXPAND_TIMEOUT_MS": settings.KG_EXPAND_TIMEOUT_MS,
            "KG_EXPAND_RRF_K": settings.KG_EXPAND_RRF_K,
            "KG_EXPAND_RRF_WEIGHT": settings.KG_EXPAND_RRF_WEIGHT,
        }},
        "n_cases": n,
        "intent_divergence": {"count": intent_div, "rate": round(intent_div / n, 4)},
        "docs_divergence": {"count": docs_div, "rate": round(docs_div / n, 4)},
        "hit_rate@5": {"off": hit_off, "on": hit_on, "delta": round(hit_on - hit_off, 4),
                       "vs_baseline": round(hit_on - BASELINE_HIT_RATE, 4),
                       "not_degraded_vs_baseline": hit_on >= BASELINE_HIT_RATE,
                       "not_degraded_vs_off": hit_on >= hit_off},
        "mrr@5": {"off": mrr_off, "on": mrr_on, "delta": round(mrr_on - mrr_off, 4)},
        "kg_expand_channel": {
            "neighbors_fused_expected": 0,
            "degrade_events_on": len(kg_degrades),
            "degrade_reasons_sample": sorted({k for k in kg_degrades})[:5],
            "note": "当前 kg_sync 子图 MENTIONS/RELATED=0（R-N1 已披露）→ 通道预期产出 0 邻居（零增益）",
        },
        "conclusion": (
            "零分歧零增益" if intent_div == 0 and docs_div == 0 and hit_on == hit_off
            else "存在分歧——需逐条核查（见 results）"
        ),
        "pairs": pairs,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(safe_w(os.path.join(OUT_DIR, "rn2-dualrun-summary.json")), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open(safe_w(os.path.join(OUT_DIR, "rn2-dualrun-results.json")), "w", encoding="utf-8") as f:
        json.dump({"off": off, "on": on}, f, ensure_ascii=False, indent=2)
    log(f"完成：intent分歧={intent_div}/{n} docs分歧={docs_div}/{n} "
        f"hit_rate@5 off={hit_off} on={hit_on}（vs基线{BASELINE_HIT_RATE} delta={round(hit_on - BASELINE_HIT_RATE, 4)}）")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 条（冒烟）")
    args = ap.parse_args()
    sys.exit(asyncio.run(run_probe(args.limit)))
