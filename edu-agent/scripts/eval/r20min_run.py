# -*- coding: utf-8 -*-
"""
R20-min 评估基线冻结 · W0 测量仪执行器（reshape-r dev-plan v1.1 W0）
详档: .ai-hub/plans/tasks/taskR20min-eval-baseline.md v1.2

口径钉死（详档步骤 2）: 实时端到端检索 —— 每 query 走
retriever.retrieve_three_channel 完整链（Milvus hybrid 召回 150 → BGE rerank 20 →
断崖截断 → final top5），在最终 docs 上算 hit_rate@5 / MRR@5。
禁止在冻结 candidates 上算指标（漏掉召回层与截断层，数字虚高）。

golden 双键: chunk_id + doc_sha256(=sha256(GT 原文 utf-8))。
R03 迁移后 chunk_id 变更时，评估 harness 解析顺序: chunk_id 直配 → id_map(old→new)
翻译 → doc_sha256 内容兜底（见 _match_golden），冻结评估集 rag_eval_set32.json 不重 build。

确定性: 不经 LLM；同配置重跑须逐位一致。临时参数覆盖（nprobe）以 monkeypatch
注入、仅本脚本运行时生效、验后还原（进程退出即还原），不改任何正产代码。

用法（edu-agent/ 下）:
  .venv/Scripts/python.exe scripts/eval/r20min_run.py --mode smoke
  .venv/Scripts/python.exe scripts/eval/r20min_run.py --mode build
  .venv/Scripts/python.exe scripts/eval/r20min_run.py --mode eval --tag base_run1
  .venv/Scripts/python.exe scripts/eval/r20min_run.py --mode eval --tag base_run2
  .venv/Scripts/python.exe scripts/eval/r20min_run.py --mode eval --tag nprobe1_probe --nprobe-override 1
  .venv/Scripts/python.exe scripts/eval/r20min_run.py --mode freeze
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.config import settings  # noqa: E402
try:
    from _safeio import safe_w  # 直接运行（脚本目录在 sys.path）
except ImportError:  # 以包形式导入（pytest: from scripts.eval import ...）
    from scripts.eval._safeio import safe_w  # Mimosa 路径穿越防护:写出统一收容校验


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVAL_DIR = os.path.join(BASE_DIR, "scripts", "eval")
DATA_DIR = os.path.join(EVAL_DIR, "data")
EVAL_SET_PATH = os.path.join(DATA_DIR, "rag_eval_set32.json")
RUNS_DIR = os.path.join(DATA_DIR, "r20min_runs")
CONTRACT_PATH = os.path.join(os.path.dirname(BASE_DIR), "contracts", "rag-baseline-eval32.json")
SEED = 20260914
TOP_K_EVAL = 5

# 生产参数（chat 正产默认, app/chat/schemas.py _BaseRagRequest + config.py）
PARAMS = {
    "recall_topk": int(getattr(settings, "RETRIEVER_RECALL_TOPK", 150)),
    "rerank_topk": int(getattr(settings, "RETRIEVER_RERANK_TOPK", 20)),
    "final_max_k": 5,
    "cutoff_drop_ratio": 0.40,
    "use_hyde": False,      # W0 钉死关闭：HyDE 是纯字符串扩展（非 LLM），其波动不属于本测量仪口径
    "enable_graph": True,   # 与生产默认一致（Neo4j 不可达时自动降级跳过, degraded_reason 留痕）
    "nprobe": 10,           # loader.hybrid_search 硬编码默认（本脚本运行时可覆盖做灵敏度实验）
    "rrf_k": 60,
    "embed_backend": str(getattr(settings, "EMBED_BACKEND", "cloud")),
    "rerank_sidecar": "http://127.0.0.1:8601",
    "role": "student",      # 非 admin 租户范围（与生产学员一致）
}


# ============================================================
# nprobe 灵敏度通道说明（详档步骤 5）:
#   loader.hybrid_search 的 dense nprobe=10 硬编码（loader.py:318）, 无法用配置或
#   monkeypatch 干净覆盖（闭包内字面量）。禁改正产代码 ⇒ 灵敏度实验走
#   _run_sensitivity(): 与生产 hybrid_search 同参重放（dense/sparse 向量 + filter +
#   partitions + RRFRanker(k=60), loader.py:315-348 逐字段对照实现）, 仅 dense
#   nprobe 不同; 该通道只出召回层布尔口径, 仅作同通道相对对照, 不与主链混算。
# ============================================================


# R03 验收专用（GPU 显存争议缓解，不改任何检索语义）:
#   本机 8GB 卡无法同时驻留 BGE-M3 fp16(~2.3G) 与 rerank sidecar fp16(~1.1G)
#   ——同载在模型加载期触发原生 0xC0000005 崩溃（非 Python 异常）。
#   验收路径：先以独立进程用基线同口径 embedder(EMBED_BACKEND=cuda/fp16) 预算全部
#   query dense 向量落盘 → 再启动 GPU sidecar → 本进程把两处 encode_dense_batch 绑定
#   替换为精确文本查表。Milvus 召回/rerank/断崖/top5 链路零改动；未命中文本直接硬错，
#   禁止静默重算或云端降级（EMBED_BACKEND 契约仍为 cuda）。
_R03_PRECOMPUTED_DENSE = os.environ.get("R03_PRECOMPUTED_DENSE")


def _install_r03_precomputed_dense() -> dict:
    """安装 R03 预计算 dense 查表补丁，返回向量缓存（仅 eval 主通道使用）。"""
    import app.chat.retriever as chat_retriever
    from app.knowledge.importer import embedder as _embedder_mod

    with open(_R03_PRECOMPUTED_DENSE, encoding="utf-8") as f:
        payload = json.load(f)
    cache = payload["vectors"] if isinstance(payload, dict) and "vectors" in payload else payload

    def _cached_encode_dense_batch(texts):
        out = []
        for t in texts:
            if t not in cache:
                raise RuntimeError(f"R03 预计算 dense 向量未命中，禁止静默重算/降级：{str(t)[:60]!r}")
            out.append(cache[t])
        return out

    # VEC-LOCK：retriever 查询侧改为调用 encode_dense_batch_detailed（单一事实源），
    # 预计算补丁须同步覆盖 detailed 入口，否则查询向量会被真实 BGE 重算（破坏 R03 显存约束）。
    def _cached_encode_dense_batch_detailed(texts):
        from app.knowledge.importer.embedder import DenseResult

        return DenseResult(
            vectors=_cached_encode_dense_batch(texts),
            backend="bge_m3",
            normalized=True,
            precision="fp16",
            embedding_model="r03-precomputed",
            max_length=8192,
        )

    # 两处绑定都要替换：函数内 `from ...embedder import encode_dense_batch` 在调用时
    # 从模块属性重取；retriever.py 是模块加载期按名绑定，须改其本地引用。
    _embedder_mod.encode_dense_batch = _cached_encode_dense_batch
    _embedder_mod.encode_dense_batch_detailed = _cached_encode_dense_batch_detailed
    chat_retriever.encode_dense_batch_detailed = _cached_encode_dense_batch_detailed
    return cache


# ============================================================
# 构建评估集（32 条, 双键 golden）
# ============================================================
def build_eval_set(limit: int = 32) -> None:
    from app.knowledge.importer.embedder import build_sparse_vector, encode_dense_batch, ensure_jieba_ready
    from app.knowledge.importer.loader import COLLECTION_NAME, COURSE_PUBLIC, get_milvus_client, hybrid_search

    os.makedirs(DATA_DIR, exist_ok=True)
    ensure_jieba_ready()
    client = get_milvus_client()
    tenant_ids = ["_default", COURSE_PUBLIC]
    exclude = getattr(settings, "RETRIEVER_EXCLUDE_CONTENT_TYPES", ()) or ()
    filter_expr = None
    if exclude:
        quoted = ", ".join(f'"{ct}"' for ct in exclude)
        filter_expr = f"content_type not in [{quoted}]"

    # ① 全量捞 question 块 → 按 bank 分桶 → 字典序确定性抽前 limit 条（复用 build_eval_set32 口径）
    rows = client.query(
        COLLECTION_NAME,
        filter="content_type == 'question'",
        output_fields=["question_bank_code", "chunk_id", "content"],
        limit=8000,
    )
    by_bank: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        bank = str(row.get("question_bank_code") or "unknown_bank")
        cid = str(row.get("chunk_id") or "")
        content = str(row.get("content") or "")
        if cid and content.strip():
            by_bank.setdefault(bank, []).append((cid, content))

    # ② 确定性抽样: 洗牌顺序由 seed 固定; 覆盖尽可能多的 bank（每 bank ≤2 条）
    rng = random.Random(SEED)
    banks = sorted(by_bank.keys())
    rng.shuffle(banks)
    picked: list[tuple[str, str]] = []
    per_bank: dict[str, int] = {}
    for bank in banks:
        cands = sorted(by_bank[bank], key=lambda x: x[0])
        rng.shuffle(cands)
        for cid, content in cands:
            if per_bank.get(bank, 0) >= 2:
                break
            picked.append((cid, content))
            per_bank[bank] = per_bank.get(bank, 0) + 1
            if len(picked) >= limit:
                break
        if len(picked) >= limit:
            break

    # ③ 题干 query 提取（与 build_eval_set32._extract_query 同口径）
    sys.path.insert(0, EVAL_DIR)
    from build_eval_set32 import _extract_query  # noqa: E402

    cases: list[dict] = []
    for cid, content in picked:
        query = _extract_query(content)
        if not query or len(query) < 6:
            continue
        cases.append({
            "query": query,
            "golden": {"chunk_id": cid, "doc_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()},
            "gt_content": content[:8000],
        })

    # ④ 冻结候选段（仅溯源对照用, 明确不用于算指标 —— 详档步骤 2）
    dense_all = encode_dense_batch([c["query"] for c in cases])
    sparse_all = [build_sparse_vector(c["query"]) for c in cases]
    for c, dense_vec, sparse_vec in zip(cases, dense_all, sparse_all):
        recall = hybrid_search(
            dense_vec=[float(x) for x in dense_vec],
            sparse_vec=sparse_vec,
            tenant_ids=tenant_ids,
            top_k=PARAMS["recall_topk"],
            filter_expr=filter_expr,
            timeout=float(getattr(settings, "MILVUS_SEARCH_TIMEOUT", 8.0)),
        )
        c["frozen_candidates"] = [
            {"doc_id": str(r.get("chunk_id") or ""), "score": float(r.get("score") or 0.0)}
            for r in recall[:PARAMS["recall_topk"]]
        ]
        # R03: 冻结召回命中判定兼容新旧 id（golden 旧 id + id_map 映射新 id）
        _gt_ids = {c["golden"]["chunk_id"]}
        _mapped = _load_id_map().get(c["golden"]["chunk_id"])
        if _mapped:
            _gt_ids.add(_mapped)
        c["gt_in_frozen_recall"] = any(x["doc_id"] in _gt_ids for x in c["frozen_candidates"])

    out = {
        "meta": {
            "builder": "r20min_run.py --mode build (query 提取复用 build_eval_set32._extract_query)",
            "built_at": datetime.now(timezone.utc).isoformat(),
            "seed": SEED,
            "limit": limit,
            "n_cases": len(cases),
            "recall_topk": PARAMS["recall_topk"],
            "tenant_ids": tenant_ids,
            "filter_expr": filter_expr,
            "milvus_collection": COLLECTION_NAME,
            "golden_double_key": ["chunk_id", "doc_sha256(sha256(gt_content utf-8))"],
            "note": "frozen_candidates 仅溯源对照; 指标判定=实时端到端检索链(r20min_run --mode eval)",
        },
        "cases": cases,
    }
    with open(safe_w(EVAL_SET_PATH), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[build] n={len(cases)} → {EVAL_SET_PATH}")
    print(f"[build] gt_in_frozen_recall={sum(1 for c in cases if c['gt_in_frozen_recall'])}/{len(cases)}")


# ============================================================
# 实时端到端评估
# ============================================================
# R03 golden 双键解析（契约 C-R-CHUNK read_compat / baseline_compat）
# 优先级：① chunk_id 直配（旧 golden；id_map 翻译成新 id 同等待遇）
#         ② doc_sha256 内容兜底（sha256(检索回块 content utf-8) == golden.doc_sha256）
#         ③ 均不中 → 返回 id_map 映射值（或旧 id），按未命中计入指标
# id_map 缺失（迁移前环境）→ 空映射，行为退回纯 chunk_id 口径
# ============================================================
_ID_MAP_CACHE: dict | None = None


def _load_id_map() -> dict[str, str]:
    """懒加载 R03 old→new chunk_id 映射（scripts/eval/data/r03_id_map.json）。"""
    global _ID_MAP_CACHE
    if _ID_MAP_CACHE is None:
        path = os.path.join(DATA_DIR, "r03_id_map.json")
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
            _ID_MAP_CACHE = {m["old_chunk_id"]: m["new_chunk_id"] for m in payload.get("rows", [])}
        except FileNotFoundError:
            _ID_MAP_CACHE = {}
    return _ID_MAP_CACHE


def _sha_resolve(case: dict) -> str:
    """golden 主键解析：chunk_id 经 id_map 翻译成迁移后新 id（无映射则原样返回）。"""
    old_id = case["golden"]["chunk_id"]
    return _load_id_map().get(old_id, old_id)


def _match_golden(case: dict, docs: list[dict]) -> tuple[str, str]:
    """在最终命中文档上解析 GT，返回 (实际参与判定的 chunk_id, 解析路径)。

    解析路径留痕: chunk_id / chunk_id+id_map / doc_sha256 / miss ——
    供 R03 验收证明「golden 按 doc_sha256 解析不受 ID 变更影响」。
    """
    golden = case["golden"]
    old_id = golden["chunk_id"]
    new_id = _load_id_map().get(old_id)
    # ① 主键直配：旧 id（迁移前/未迁移行）或 id_map 新 id
    for d in docs:
        if d["chunk_id"] == old_id:
            return d["chunk_id"], "chunk_id"
    if new_id is not None:
        for d in docs:
            if d["chunk_id"] == new_id:
                return d["chunk_id"], "chunk_id+id_map"
    # ② doc_sha256 内容兜底（与 build 同口径：content 原样 sha256，不 strip）
    for d in docs:
        if hashlib.sha256(d["content"].encode("utf-8")).hexdigest() == golden["doc_sha256"]:
            return d["chunk_id"], "doc_sha256"
    # ③ 未命中：用映射后 id 保持指标判定口径（ranks 自然为空）
    return new_id or old_id, "miss"


async def _eval_one(sem, idx: int, case: dict, results: list, trace_hook=None) -> None:
    from app.auth import UserRole
    from app.chat.rag_evaluator import evaluate_retrieval
    from app.chat.retriever import retrieve_three_channel

    async with sem:
        t0 = time.perf_counter()
        bundle = await retrieve_three_channel(
            case["query"],
            user_id=1,
            role=UserRole.STUDENT,
            use_hyde=PARAMS["use_hyde"],
            enable_graph=PARAMS["enable_graph"],
            top_k=PARAMS["final_max_k"],
            final_max_k=PARAMS["final_max_k"],
            cutoff_drop_ratio=PARAMS["cutoff_drop_ratio"],
        )
        lat_ms = round((time.perf_counter() - t0) * 1000, 1)

        docs = [{"chunk_id": d.doc_id, "content": d.content, "score": d.score} for d in bundle.docs]
        gt_id, gt_via = _match_golden(case, docs)  # R03: chunk_id → doc_sha256 → id_map
        m = evaluate_retrieval(case["query"], docs, [gt_id], k=TOP_K_EVAL)

        ranks = [i + 1 for i, d in enumerate(docs) if d["chunk_id"] == gt_id]
        trace = {
            "recall_layer": int(bundle.raw_retrieved_count),                       # 召回(融合后, retriever.py:535)
            "rerank_layer": min(PARAMS["rerank_topk"], int(bundle.raw_retrieved_count)),  # rerank 保留数(retriever.py:462)
            "final_layer": len(docs),                                              # 断崖+final 截断后
            "degraded_reason": bundle.degraded_reason,
            "rewrite_query": bundle.rewrite_query,
        }
        if trace_hook is not None:
            trace_hook(idx, case, trace)
        results.append({
            "idx": idx,
            "query": case["query"],
            "golden_chunk_id": case["golden"]["chunk_id"],
            "golden_doc_sha256": case["golden"]["doc_sha256"],
            "gt_resolved_id": gt_id,        # R03: 实际参与判定的 chunk_id（迁移后为新 id）
            "gt_resolve_via": gt_via,       # R03: 解析路径留痕 chunk_id/chunk_id+id_map/doc_sha256/miss
            "hit": bool(m.hit_rate >= 1.0),
            "rr": m.mrr,
            "rank_of_gt": ranks[0] if ranks else None,
            "top5_ids": [d["chunk_id"] for d in docs[:TOP_K_EVAL]],
            "latency_ms": lat_ms,
            "trace": trace,
        })


def run_eval(tag: str, nprobe_override: int | None = None) -> dict:
    """跑实时端到端评估并落盘。nprobe_override 仅走独立直连重放通道（不改产码）。"""
    from app.knowledge.importer.embedder import build_sparse_vector, encode_dense_batch, ensure_jieba_ready

    with open(EVAL_SET_PATH, encoding="utf-8") as f:
        eval_set = json.load(f)
    cases = eval_set["cases"]
    ensure_jieba_ready()

    r03_precomp = None
    if _R03_PRECOMPUTED_DENSE and nprobe_override is None:
        _cache0 = _install_r03_precomputed_dense()
        r03_precomp = {
            "path": _R03_PRECOMPUTED_DENSE,
            "n_vectors": len(_cache0),
            "precompute_backend": "cuda fp16 BGE-M3（独立进程预算，与基线 embedder 同口径）",
            "eval_process_dense": "exact_text_lookup（未命中即硬错；召回/rerank/断崖链路不变）",
        }

    effective_params = dict(PARAMS)
    if nprobe_override is not None:
        effective_params["nprobe"] = int(nprobe_override)
        effective_params["nprobe_override_mode"] = "isolated_replay_channel"

    if nprobe_override is None:
        sem = asyncio.Semaphore(1)  # 串行: GPU/Milvus 稳定性优先, 顺序固定保证可复现
        results: list[dict] = []
        t_start = time.perf_counter()

        # 预编码全部 query（批量一次, 与检索链一致——retriever 内部亦经 encode_dense_batch）
        _ = encode_dense_batch([c["query"] for c in cases])

        async def _run_all() -> None:
            tasks = [_eval_one(sem, i, c, results) for i, c in enumerate(cases)]
            for t in tasks:  # 逐个 await 保持提交顺序=完成顺序确定性
                await t

        asyncio.run(_run_all())
        wall_s = round(time.perf_counter() - t_start, 1)
    else:
        results, wall_s = _run_sensitivity(cases, nprobe_override)

    n = len(results)
    hit_rate = round(sum(r["hit"] for r in results) / n, 4)
    mrr = round(sum(r["rr"] for r in results) / n, 4)
    report = {
        "tag": tag,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=BASE_DIR).stdout.strip(),
        "mode": "realtime_e2e_retrieval(retrieve_three_channel 全链)" if nprobe_override is None else f"isolated_replay_nprobe={nprobe_override}",
        "params": effective_params,
        "seed": SEED,
        "n_cases": n,
        "hit_rate@5": hit_rate,
        "mrr@5": mrr,
        "wall_seconds": wall_s,
        "r03_dense_precompute": r03_precomp,
        "per_query": results,
    }
    os.makedirs(RUNS_DIR, exist_ok=True)
    out_path = os.path.join(RUNS_DIR, f"{tag}.json")
    # M-2 收口: run 报告（含 per_query 全量）真身入 GridFS 制品库, 本地留同字节工作副本
    # （r03b_verify._baseline_reference 等下游读者依赖该路径）; mongo 不可达自动降级
    # test-reports/artifacts_local/, 归档层自身失败回退直接落盘——均不阻断评估主流程。
    try:
        from app.common.artifact_store import save_artifact
        _arch = save_artifact(f"eval/runs/{tag}.json", report,
                              metadata={"kind": "r20min_run_report", "tag": tag,
                                        "n_cases": n, "hit_rate@5": hit_rate, "mrr@5": mrr},
                              local_copy=out_path)
        print(f"[artifact] backend={_arch['backend']} aid={_arch['aid']} "
              f"sha256={_arch['sha256'][:16]} size={_arch['size']}")
    except Exception as _e:  # noqa: BLE001
        print(f"[artifact] 归档失败(忽略, 回退直接落盘): {type(_e).__name__}: {_e}")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[eval:{tag}] hit_rate@5={hit_rate} mrr@5={mrr} n={n} wall={wall_s}s → {out_path}")
    return report


def _run_sensitivity(cases: list[dict], nprobe: int) -> tuple[list[dict], float]:
    """灵敏度对照通道: 与生产 hybrid_search 同参重放, 仅 dense nprobe 不同（loader.py:315-348 逐字段一致）。

    该通道绕过 rerank/断崖层, 与主链不同口径 —— 因此本通道结果**只用于相对对照**
    （同通道 base vs nprobe=1 的差值）, 不与主链绝对值混算。为使对照可判定,
    此处补跑一条 nprobe=10 的同通道基线。
    """
    from pymilvus import AnnSearchRequest, RRFRanker

    from app.knowledge.importer.embedder import build_sparse_vector, encode_dense_batch
    from app.knowledge.importer.loader import COLLECTION_NAME, COURSE_PUBLIC, get_milvus_client

    client = get_milvus_client()
    tenant_ids = ["_default", COURSE_PUBLIC]
    exclude = getattr(settings, "RETRIEVER_EXCLUDE_CONTENT_TYPES", ()) or ()
    filter_expr = None
    if exclude:
        quoted = ", ".join(f'"{ct}"' for ct in exclude)
        filter_expr = f"content_type not in [{quoted}]"

    t0 = time.perf_counter()
    dense_all = encode_dense_batch([c["query"] for c in cases])
    sparse_all = [build_sparse_vector(c["query"]) for c in cases]

    # 同通道双跑: nprobe=10(对照) 与 nprobe=nprobe(实验); 另跑 dense 单通道对照
    # （nprobe 是 dense IVF 探测参数, 稀疏通道会补偿融合层召回 → 受影响组件=dense 单通道）
    channel_results: dict[int, list[set[str]]] = {10: [], nprobe: []}
    dense_ids: dict[int, list[list[str]]] = {10: [], nprobe: []}
    for np_ in (10, nprobe):
        for dense_vec, sparse_vec in zip(dense_all, sparse_all):
            dense_list = [float(x) for x in dense_vec]
            dense_req = AnnSearchRequest(
                data=[dense_list],
                anns_field="dense_vec",
                param={"metric_type": "COSINE", "params": {"nprobe": np_}},
                limit=PARAMS["recall_topk"],
                expr=filter_expr,
            )
            sparse_req = AnnSearchRequest(
                data=[sparse_vec],
                anns_field="sparse_vec",
                param={"metric_type": "IP"},
                limit=PARAMS["recall_topk"],
                expr=filter_expr,
            )
            res = client.hybrid_search(
                collection_name=COLLECTION_NAME,
                reqs=[dense_req, sparse_req],
                ranker=RRFRanker(k=PARAMS["rrf_k"]),
                limit=PARAMS["recall_topk"],
                timeout=float(getattr(settings, "MILVUS_SEARCH_TIMEOUT", 8.0)),
                partition_names=tenant_ids,
                output_fields=["chunk_id"],
            )
            channel_results[np_].append({
                str(h["entity"].get("chunk_id") or "") for hits in res for h in hits
            })
            # dense 单通道（同 nprobe）
            dres = client.search(
                collection_name=COLLECTION_NAME,
                data=[dense_list],
                anns_field="dense_vec",
                limit=PARAMS["recall_topk"],
                search_params={"metric_type": "COSINE", "params": {"nprobe": np_}},
                timeout=float(getattr(settings, "MILVUS_SEARCH_TIMEOUT", 8.0)),
                partition_names=tenant_ids,
                output_fields=["chunk_id"],
            )
            dense_ids[np_].append([
                str(h["entity"].get("chunk_id") or "") for hits in dres for h in hits
            ])

    results: list[dict] = []
    for i, c in enumerate(cases):
        # R03: 灵敏度通道召回集是迁移后新 id；golden 旧 id 经 id_map 翻译（无内容快照，不走 sha 兜底）
        gt_old = c["golden"]["chunk_id"]
        gt = _load_id_map().get(gt_old, gt_old)
        base_ids, probe_ids = channel_results[10][i], channel_results[nprobe][i]
        base_hit = gt in base_ids
        probe_hit = gt in probe_ids
        base_dense_hit = gt in dense_ids[10][i]
        probe_dense_hit = gt in dense_ids[nprobe][i]
        base_dense_rank = (dense_ids[10][i].index(gt) + 1) if base_dense_hit else None
        probe_dense_rank = (dense_ids[nprobe][i].index(gt) + 1) if probe_dense_hit else None
        results.append({
            "idx": i,
            "query": c["query"],
            "golden_chunk_id": gt,
            "golden_doc_sha256": c["golden"]["doc_sha256"],
            "hit": probe_hit,
            "rr": 1.0 if probe_hit else 0.0,  # 召回层布尔口径（排名无意义, 只对照 recall 掉落）
            "rank_of_gt": 1 if probe_hit else None,
            "top5_ids": [],
            "latency_ms": None,
            "trace": {
                "recall_layer": len(probe_ids),
                "rerank_layer": None,
                "final_layer": None,
                "degraded_reason": "sensitivity_isolated_replay: 召回层布尔口径, 只对照 base(nprobe=10) 差值",
                "base_recall_hit": base_hit,
                "probe_recall_hit": probe_hit,
                "recall_drop": bool(base_hit and not probe_hit),
                "dense_channel": {
                    "base_hit_nprobe10": base_dense_hit,
                    "probe_hit": probe_dense_hit,
                    "dense_recall_drop": bool(base_dense_hit and not probe_dense_hit),
                    "base_dense_rank": base_dense_rank,
                    "probe_dense_rank": probe_dense_rank,
                    "dense_rank_shift": (base_dense_rank - probe_dense_rank)
                    if (base_dense_rank and probe_dense_rank) else None,
                },
            },
        })
    wall_s = round(time.perf_counter() - t0, 1)
    return results, wall_s


# ============================================================
# 冻结契约
# ============================================================
def freeze() -> None:
    base1 = json.load(open(os.path.join(RUNS_DIR, "base_run1.json"), encoding="utf-8"))
    base2 = json.load(open(os.path.join(RUNS_DIR, "base_run2.json"), encoding="utf-8"))
    probe = json.load(open(os.path.join(RUNS_DIR, "nprobe1_probe.json"), encoding="utf-8"))
    eval_set = json.load(open(EVAL_SET_PATH, encoding="utf-8"))

    hit, mrr = base1["hit_rate@5"], base1["mrr@5"]
    det = {
        "runs": ["base_run1", "base_run2"],
        "hit_rate_equal": base1["hit_rate@5"] == base2["hit_rate@5"],
        "mrr_equal": base1["mrr@5"] == base2["mrr@5"],
        "per_query_identical": [r["hit"] for r in base1["per_query"]] == [r["hit"] for r in base2["per_query"]]
        and [r["rr"] for r in base1["per_query"]] == [r["rr"] for r in base2["per_query"]],
    }
    # 灵敏度判定: 同通道(召回层布尔口径)对照 —— 实验通道 vs 其自带 nprobe=10 对照;
    # 稀疏通道会补偿融合层 → 受影响组件=dense 单通道(掉点或 GT 排名回归都算可见下降)
    probe_rows = probe["per_query"]
    dropped = sum(1 for r in probe_rows if r["trace"].get("recall_drop"))
    base_hits = sum(1 for r in probe_rows if r["trace"].get("base_recall_hit"))
    probe_hits = sum(1 for r in probe_rows if r["trace"].get("probe_recall_hit"))
    d_rows = [r["trace"]["dense_channel"] for r in probe_rows]
    d_base = sum(1 for d in d_rows if d["base_hit_nprobe10"])
    d_probe = sum(1 for d in d_rows if d["probe_hit"])
    d_dropped = sum(1 for d in d_rows if d["dense_recall_drop"])
    # dense_rank_shift = base_rank - probe_rank: >0=probe 排名改善, <0=probe 排名劣化
    d_improved = sum(1 for d in d_rows if (d["dense_rank_shift"] or 0) > 0)
    d_regressed = sum(1 for d in d_rows if (d["dense_rank_shift"] or 0) < 0)
    sens_pass = probe_hits < base_hits or d_dropped > 0
    sens = {
        "channel": "isolated_replay(召回层布尔口径, 同通道 base=nprobe10 自对照)",
        "nprobe": probe["params"]["nprobe"],
        "fusion_layer": {"base_recall_hits": base_hits, "probe_recall_hits": probe_hits, "dropped": dropped},
        "dense_channel": {
            "base_hits_nprobe10": d_base,
            "probe_hits": d_probe,
            "dropped": d_dropped,
            "rank_improved_queries": d_improved,
            "rank_regressed_queries": d_regressed,
        },
        "verdict": "PASS 指标可见下降" if sens_pass else "FAIL 无可见下降(记录: nprobe 覆盖对召回无差, R03 迁移对照仍以主链指标为准)",
    }
    contract = {
        "plan_id": "reshape-r-eval",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": base1["git_rev"],
        "draft": False,
        "eval_set": {
            "file": "edu-agent/scripts/eval/data/rag_eval_set32.json",
            "n": eval_set["meta"]["n_cases"],
            "limit": eval_set["meta"]["limit"],
            "seed": eval_set["meta"]["seed"],
            "golden_double_key": eval_set["meta"]["golden_double_key"],
        },
        "params": base1["params"],
        "baseline": {"tag": "base_run1", "n": base1["n_cases"], "top_k": TOP_K_EVAL, "hit_rate@5": hit, "mrr@5": mrr},
        "thresholds": {
            "RAG_EVAL_HIT_RATE_MIN": round(hit - 0.02, 4),
            "RAG_EVAL_MRR_MIN": round(mrr - 0.02, 4),
            "rule": "基线-0.02; R03 迁移后重跑偏差<=2% 超即回滚; R22 起 CI 拦截(W0 只冻结不拦截)",
        },
        "metric_scope": "实时端到端检索链(retriever.retrieve_three_channel 全链: 召回150→rerank20→断崖→top5), 禁止在冻结 candidates 上算指标",
        "determinism_check": det,
        "sensitivity_probe": sens,
        "id_map_note": "R03 迁移须输出 old→new chunk_id id_map 落盘; golden 双键中 doc_sha256 为迁移后解析兜底键",
    }
    os.makedirs(os.path.dirname(CONTRACT_PATH), exist_ok=True)
    with open(safe_w(CONTRACT_PATH), "w", encoding="utf-8") as f:
        json.dump(contract, f, ensure_ascii=False, indent=2)
    print(f"[freeze] → {CONTRACT_PATH}")
    print(f"[freeze] baseline hit_rate@5={hit} mrr@5={mrr} determinism={det['hit_rate_equal'] and det['mrr_equal']} sensitivity={sens['verdict']}")


# ============================================================
# 回归门（详档步骤 4: exit 1 逻辑实现, W0 只冻结不接线拦截; R22 起 CI 接管）
# ============================================================
def gate() -> int:
    """按冻结契约阈值跑一遍实时端到端评估, 低于阈值 exit 1（供 R03 后对照/CI 复用）。"""
    try:
        with open(CONTRACT_PATH, encoding="utf-8") as f:
            contract = json.load(f)
    except FileNotFoundError:
        print("[gate] FAIL 契约文件不存在（先 --mode freeze）")
        return 1
    hit_min = contract["thresholds"]["RAG_EVAL_HIT_RATE_MIN"]
    mrr_min = contract["thresholds"]["RAG_EVAL_MRR_MIN"]
    rep = run_eval("gate_check")
    ok = rep["hit_rate@5"] >= hit_min and rep["mrr@5"] >= mrr_min
    print(f"[gate] hit_rate@5={rep['hit_rate@5']} (min={hit_min}) mrr@5={rep['mrr@5']} (min={mrr_min}) → {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


# ============================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="R20-min 评估基线冻结执行器")
    ap.add_argument("--mode", required=True, choices=["smoke", "build", "eval", "freeze", "gate"])
    ap.add_argument("--tag", default="run")
    ap.add_argument("--nprobe-override", type=int, default=None)
    args = ap.parse_args()

    if args.mode == "smoke":
        from app.auth import UserRole
        from app.chat.retriever import retrieve_three_channel
        from app.knowledge.importer.embedder import encode_dense_batch, ensure_jieba_ready

        ensure_jieba_ready()
        # 预热 BGE-M3（冷加载 ~18s 在 retriever 外层 wait_for(8s) 窗口内会误触超时降级;
        # 生产由 main.py 启动 warmup 掩盖, eval 侧显式预热等价）
        _ = encode_dense_batch(["预热"])

        async def _smoke() -> None:
            b = await retrieve_three_channel(
                "什么是现在完成时",
                user_id=1, role=UserRole.STUDENT,
                use_hyde=False, enable_graph=True,
                top_k=5, final_max_k=5, cutoff_drop_ratio=0.40,
            )
            print(f"[smoke] docs={len(b.docs)} raw={b.raw_retrieved_count} degrade={b.degraded_reason}")
            print(f"[smoke] top1={b.docs[0].doc_id if b.docs else None} score={b.docs[0].score if b.docs else None}")

        asyncio.run(_smoke())
        return 0
    if args.mode == "build":
        build_eval_set(32)
        return 0
    if args.mode == "eval":
        run_eval(args.tag, args.nprobe_override)
        return 0
    if args.mode == "gate":
        return gate()
    freeze()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
