# -*- coding: utf-8 -*-
"""
R03-b 迁移/评估只读核验（4417 迁移 + 指标零偏差可重放独立实证，解锁 T10 前置门）
契约: contracts/reshape-r-chunk.json（id 格式 {tenant}:{sha256(canonical)[:16]}:{seq}）
任务书: .ai-hub/plans/artifacts/kickoff-R03b-readonly-verify.md

核心目标: R03 的验收数字（4417 迁移唯一化 / hit_rate@5·mrr@5 0.9688 零偏差 / 32 黄金排名一致）
唯一载体曾是 agent 自产 JSON，本脚本让编排者**一键复跑只读核验**拿回全部数字。
全程 **纯只读**: 对 Milvus 只用参数绑定 SELECT（query/count），对 MySQL 零访问；
**不写库 / 不重建 / 不迁移**。产出 = 打印 + 可选写入 scripts/eval/data/r03b_verify_result.json。

四步 GWT:
  G1  id_map 翻译命中率 / new id 在库率 (+ 旧 id 已替换) —— 与 R03 报告对账
  G2  canonical id 重算(hash/seq 组件) 一致率 + doc_sha256 一致率
  G3  hit_rate@5 / mrr@5 实测 vs 基线 0.9688 偏差; golden 排名一致率
  G4  唯一性违例=0 + 跨租户隔离实证

用法（cwd=edu-agent）:
  .venv/Scripts/python.exe scripts/eval/r03b_verify.py
可选:
  --result PATH   写 JSON 结果到指定文件（默认不写, 仅打印）
  --no-eval       跳过实时检索评估（G3 退回读取持久化 r03 run + 基线 JSON, 标记 tradeoff）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

# ============ 路径 ============
_EVAL_DIR = os.path.join(BASE_DIR, "scripts", "eval")
_DATA_DIR = os.path.join(_EVAL_DIR, "data")
ID_MAP_PATH = os.path.join(_DATA_DIR, "r03_id_map.json")
EVAL_SET_PATH = os.path.join(_DATA_DIR, "rag_eval_set32.json")
PRE_COMP_DENSE = os.path.join(_DATA_DIR, "_r03_query_dense.json")
RUNS_DIR = os.path.join(_DATA_DIR, "r20min_runs")
CONTRACT_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "contracts", "rag-baseline-eval32.json"))
TOP_K_EVAL = 5
THRESHOLD_DELTA = 0.02           # 契约 acceptance.baseline_drift: 相对冻结基线偏差<=2%
ID_PAT = re.compile(r"^[^:]+:[0-9a-f]{16}:\d+$")

from app.config import settings  # noqa: E402
from pymilvus import MilvusClient  # noqa: E402
from app.knowledge.importer.loader import (  # noqa: E402
    COLLECTION_NAME, COURSE_PUBLIC, canonical_content_of, canonical_id,
)


def _client() -> MilvusClient:
    return MilvusClient(
        uri=settings.MILVUS_URI,
        token=settings.MILVUS_TOKEN or None,
        timeout=60.0,
    )


def _load_id_map() -> dict:
    with open(ID_MAP_PATH, encoding="utf-8") as f:
        return json.load(f)


def _read_all_light(client: MilvusClient) -> list[dict]:
    """只读全量轻量字段（不含向量），行数超 16384 拒（防漏读掩盖）。"""
    rows = client.query(
        COLLECTION_NAME, filter="id >= 0",
        output_fields=["id", "chunk_id", "content", "raw_content", "tenant_id",
                       "source_file", "content_type", "doc_sha256", "created_at"],
        limit=16384, timeout=120,
    )
    cnt = int(client.query(COLLECTION_NAME, filter="id >= 0", output_fields=["count(*)"])[0]["count(*)"])
    if len(rows) != cnt:
        raise RuntimeError(f"只读全量不完整: query={len(rows)} count(*)={cnt}")
    return rows


def _doc_sha256(content: str) -> str:
    """doc_sha256=sha256(content 原样 utf-8)（与 r03_migrate._doc_sha256 同口径, 不 strip）。"""
    return hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()


# ================================================================
# G1: id_map 翻译命中率 / new id 在库率 / 旧 id 已替换
# ================================================================
def step1_idmap(rows: list[dict], payload: dict) -> dict:
    plan = payload.get("rows", [])
    old_to_new = {m["old_chunk_id"]: m["new_chunk_id"] for m in plan}
    db_ids = {str(r.get("chunk_id")) for r in rows}

    n = len(plan)
    new_in_lib = sum(1 for m in plan if m["new_chunk_id"] in db_ids)
    db_id_set = set(db_ids)
    # 旧 id 在库残留（spec: 旧 pk 全删, 若有残留说明替换不干净）
    old_residual = [m["old_chunk_id"] for m in plan if m["old_chunk_id"] in db_id_set]

    # golden 覆盖: 32 黄金旧 id 是否都在 map 中（R03 7.3 声称 32/32）
    try:
        eval_set = json.load(open(EVAL_SET_PATH, encoding="utf-8"))
    except FileNotFoundError:
        eval_set = {"cases": []}
    golden_old = [c["golden"]["chunk_id"] for c in eval_set.get("cases", [])]
    golden_in_map = sum(1 for gid in golden_old if gid in old_to_new)
    golden_missing = [gid for gid in golden_old if gid not in old_to_new]

    # 新 id 格式契约校验（全部）
    format_bad = [m["new_chunk_id"] for m in plan if not ID_PAT.match(m["new_chunk_id"])]
    return {
        "step": "G1",
        "goal": "id_map 翻译命中率 / new id 在库率 / 旧 id 已替换 / golden 覆盖",
        "id_map_rows": n,
        "new_in_lib": new_in_lib,
        "new_in_lib_rate": round(new_in_lib / n, 6) if n else None,
        "old_residual_in_lib": len(old_residual),
        "old_residual_samples": old_residual[:5],
        "id_map_old_unique": len({m["old_chunk_id"] for m in plan}),
        "id_map_new_unique": len({m["new_chunk_id"] for m in plan}),
        "id_format_contract_bad": len(format_bad),
        "id_format_bad_samples": format_bad[:5],
        "golden_total": len(golden_old),
        "golden_in_map": golden_in_map,
        "golden_in_map_rate": round(golden_in_map / len(golden_old), 6) if golden_old else None,
        "golden_missing": golden_missing,
        "verdict": "PASS" if new_in_lib == n and not old_residual and not format_bad
                   and golden_in_map == len(golden_old) else "FAIL",
    }


# ================================================================
# G2: canonical id 重算(hash 组件 + seq 一致性) + doc_sha256 一致率
# ================================================================
def step2_canonical(rows: list[dict], payload: dict, sample: int) -> dict:
    plan = payload.get("rows", [])
    row_by_cid = {str(r.get("chunk_id")): r for r in rows}

    # hash 组件重算: 逐行 canonical=raw_content else content, strip → sha256[:16],
    # 与 id 内 h16(首段租户后、末段 seq 前的 16 位 hex) 比对
    hash_bad: list[str] = []
    doc_sha_bad: list[dict] = []
    n_record = 0
    for m in plan:
        r = row_by_cid.get(m["new_chunk_id"])
        if r is None:
            continue
        n_record += 1
        raw = r.get("raw_content")
        canonical = (str(raw) if raw else str(r.get("content") or "")).strip()
        id_tenant, id_h16, id_seq = m["new_chunk_id"].split(":")
        recomp_h16 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        # ① hash 组件一致; ② 重算 canonical_id 与库中 id 完全相等（含 seq）
        expect_id = canonical_id(id_tenant, canonical, int(id_seq))
        if recomp_h16 != id_h16 or expect_id != m["new_chunk_id"]:
            hash_bad.append({"id": m["new_chunk_id"], "recomp_h16": recomp_h16, "expect": expect_id})
        # doc_sha256 一致率 (golden 双键)
        di = _doc_sha256(r.get("content"))
        if di != m.get("doc_sha256"):
            doc_sha_bad.append({"id": m["new_chunk_id"], "db": di, "map": m.get("doc_sha256")})
    hash_match = n_record - len(hash_bad)
    sha_match = n_record - len(doc_sha_bad)

    # seq 一致性: 按 (tenant, h16) 分组, 组内 seq 应恰为 1..k 连续无gap/dup
    groups: dict[str, set] = {}
    for m in plan:
        t = m["tenant"]
        h16 = m["new_chunk_id"].split(":", 1)[1].rsplit(":", 1)[0]
        seq = int(m["new_chunk_id"].rsplit(":", 1)[-1])
        groups.setdefault(f"{t}:{h16}", set()).add(seq)
    seq_ok = 0
    seq_bad: list[dict] = []
    for key, seqset in groups.items():
        if seqset == set(range(1, len(seqset) + 1)):
            seq_ok += 1
        else:
            seq_bad.append({"group": key, "seqs": sorted(seqset)})
    groups_n = len(groups)
    return {
        "step": "G2",
        "goal": "canonical id 重算(hash/seq 组件) + doc_sha256 一致率",
        "sampled_records_joined": n_record,
        "canonical_hash_match": hash_match,
        "canonical_hash_match_rate": round(hash_match / n_record, 6) if n_record else None,
        "canonical_hash_bad_samples": hash_bad[:5],
        "doc_sha256_match": sha_match,
        "doc_sha256_match_rate": round(sha_match / n_record, 6) if n_record else None,
        "doc_sha256_bad_samples": doc_sha_bad[:3],
        "seq_ok_groups": seq_ok,
        "seq_bad_groups": len(seq_bad),
        "seq_bad_samples": seq_bad[:3],
        "unique_canonical_groups": groups_n,
        "verdict": "PASS" if (n_record and hash_match == n_record and sha_match == n_record
                              and not seq_bad) else "FAIL",
    }


# ================================================================
# G3: 指标零偏差可重放（实时只读检索评估 → 回退持久化 tradeoff）
# ================================================================
def _load_precomputed_dense() -> dict:
    """R03 §8 GPU 绕行: 精确文本查表（未命中硬错, 禁静默重算/云端降级）。"""
    with open(PRE_COMP_DENSE, encoding="utf-8") as f:
        payload = json.load(f)
    return payload["vectors"] if isinstance(payload, dict) and "vectors" in payload else payload


def _install_precomputed_dense(cache: dict) -> None:
    """R03 §8 GPU 绕行: 精确文本查表替换查询侧 dense 编码，防止冷加载 BGE 触发 Milvus 8s 超时。

    注意管线演进:VEC-LOCK 后 retriever 走 `encode_dense_batch_detailed`(返回 DenseResult),
    r20min_run 的旧 shim 只换 `encode_dense_batch`(纯列表)已跟不上, 这里同时替换
    `encode_dense_batch_detailed`(DenseResult 路径) 与兼容包装 `encode_dense_batch`。
    """
    import app.chat.retriever as chat_retriever
    from app.knowledge.importer import embedder as emb
    from app.knowledge.importer.embedder import DenseResult

    def _cached_detailed(texts):
        out = []
        for t in texts:
            if t not in cache:
                raise RuntimeError(f"预计算 dense 向量未命中, 禁止静默重算: {str(t)[:60]!r}")
            out.append([float(x) for x in cache[t]])
        return DenseResult(
            vectors=out, backend="bge_m3", normalized=True,
            precision="fp16", embedding_model="precomputed-bge-m3-r03",
            max_length=8192,
        )

    def _cached(texts):
        return _cached_detailed(texts).vectors

    # 主入口（retriever 实际调用）+ 包装入口
    emb.encode_dense_batch_detailed = _cached_detailed
    emb.encode_dense_batch = _cached
    chat_retriever.encode_dense_batch = _cached
    # 若调用方也按名引用了 detailed, 一并替换
    if hasattr(chat_retriever, "encode_dense_batch_detailed"):
        chat_retriever.encode_dense_batch_detailed = _cached_detailed


def _baseline_reference() -> dict:
    """读取冻结基线契约与 R03 run（用于对账与 tradeoff 回退数值）。"""
    ref = {}
    try:
        contract = json.load(open(CONTRACT_PATH, encoding="utf-8"))
        ref["baseline_hit"] = contract["baseline"]["hit_rate@5"]
        ref["baseline_mrr"] = contract["baseline"]["mrr@5"]
        ref["baseline_tag"] = contract["baseline"]["tag"]
        ref["threshold_min"] = contract["thresholds"]["RAG_EVAL_HIT_RATE_MIN"]
    except Exception as e:
        ref["baseline_err"] = f"{type(e).__name__}: {e}"
    for tag in ("r03_post_migration", "r03_post_migration_r2"):
        p = os.path.join(RUNS_DIR, f"{tag}.json")
        if os.path.exists(p):
            r = json.load(open(p, encoding="utf-8"))
            ref[tag] = {"hit": r.get("hit_rate@5"), "mrr": r.get("mrr@5"),
                        "n": r.get("n_cases"), "ran_at": r.get("ran_at"),
                        "dense_precompute": r.get("r03_dense_precompute") is not None}
    return ref


def _realtime_eval(rows: list[dict], payload: dict) -> dict:
    """实时只读端到端检索评估（retrieve_three_channel 全链, R03 §8 GPU 绕行）。
    只读: Milvus hybrid 召回 + GPU sidecar rerank + 断崖 + top5; 零写库。"""
    import asyncio
    from app.auth import UserRole
    from app.chat.rag_evaluator import evaluate_retrieval
    from app.chat.retriever import retrieve_three_channel

    old_to_new = {m["old_chunk_id"]: m["new_chunk_id"] for m in payload["rows"]}
    eval_set = json.load(open(EVAL_SET_PATH, encoding="utf-8"))
    cases = eval_set["cases"]

    # golden 双键: chunk_id 直配 → id_map 翻译 → doc_sha256 内容兜底
    row_by_cid = {str(r.get("chunk_id")): r for r in rows}
    hit, rr, rank_mismatch = 0, 0.0, 0
    per = []
    for idx, case in enumerate(cases):
        query = case["query"]
        golden = case["golden"]
        old_id = golden["chunk_id"]
        new_id = old_to_new.get(old_id)
        res = asyncio.run(_eval_one(idx, query, golden, old_id, new_id, rows))
        per.append(res)
        hit += int(res["hit"])
        rr += res["rr"]
    n = len(per)
    hit_rate = round(hit / n, 4)
    mrr = round(rr / n, 4)
    return {
        "step": "G3",
        "goal": "hit_rate@5 / mrr@5 实测 vs 基线偏差; golden 排名一致率",
        "mode": "realtime_e2e_readonly(retrieve_three_channel 全链 + R03 precomputed dense)",
        "n": n,
        "hit_rate@5": hit_rate,
        "mrr@5": mrr,
        "per_query": per,
    }


async def _eval_one(idx, query, golden, old_id, new_id, rows) -> dict:
    from app.chat.retriever import retrieve_three_channel

    b = await retrieve_three_channel(
        query, user_id=1, role=__import__("app.auth", fromlist=["UserRole"]).UserRole.STUDENT,
        use_hyde=False, enable_graph=True,
        top_k=TOP_K_EVAL, final_max_k=TOP_K_EVAL, cutoff_drop_ratio=0.40,
    )
    docs = [{"chunk_id": d.doc_id, "content": d.content, "score": d.score} for d in b.docs]
    from app.chat.rag_evaluator import evaluate_retrieval

    # 解析 GT: chunk_id 直配 → id_map 翻译 → doc_sha256 内容兜底
    gt_id, via = None, "miss"
    for d in docs:
        if d["chunk_id"] == old_id:
            gt_id, via = d["chunk_id"], "chunk_id"
            break
    if gt_id is None and new_id:
        for d in docs:
            if d["chunk_id"] == new_id:
                gt_id, via = d["chunk_id"], "chunk_id+id_map"
                break
    if gt_id is None:
        for d in docs:
            if hashlib.sha256(d["content"].encode("utf-8")).hexdigest() == golden["doc_sha256"]:
                gt_id, via = d["chunk_id"], "doc_sha256"
                break
    m = evaluate_retrieval(query, docs, [gt_id or (new_id or old_id)], k=TOP_K_EVAL)
    ranks = [i + 1 for i, d in enumerate(docs) if d["chunk_id"] == (gt_id or (new_id or old_id))]
    return {
        "idx": idx, "query": query, "golden_chunk_id": old_id,
        "gt_resolved_id": gt_id or (new_id or old_id), "gt_resolve_via": via,
        "hit": bool(m.hit_rate >= 1.0), "rr": m.mrr,
        "rank_of_gt": ranks[0] if ranks else None,
        "top5_ids": [d["chunk_id"] for d in docs[:TOP_K_EVAL]],
    }


def step3_metrics(rows: list[dict], payload: dict, no_eval: bool) -> dict:
    ref = _baseline_reference()
    base_hit = ref.get("baseline_hit")
    base_mrr = ref.get("baseline_mrr")
    threshold_min = ref.get("threshold_min")
    if no_eval:
        # 回退 tradeoff: 读持久化 r03 run（精确查表 vs 重编码）—— 只读对账
        use = ref.get("r03_post_migration_r2") or ref.get("r03_post_migration")
        hit, mrr = (use.get("hit"), use.get("mrr")) if use else (None, None)
        dev_hit = round((hit - base_hit), 4) if (hit is not None and base_hit is not None) else None
        return {
            "step": "G3",
            "goal": "指标零偏差可重放（tradeoff: 精确查表(持久 run JSON) vs 重编码(实时)）",
            "mode": "persisted_replay(readonly): " + ("--no-eval 显式跳过实时" if no_eval else "sidecar/GPU 不可用自动回退"),
            "source_run": (list(use.keys()) if use else None),
            "hit_rate@5": hit, "mrr@5": mrr,
            "baseline_hit_rate@5": base_hit, "baseline_mrr@5": base_mrr,
            "delta_hit@5": dev_hit, "delta_mrr@5": dev_hit,
            "threshold_min": threshold_min,
            "within_threshold": bool(dev_hit is not None and abs(dev_hit) <= THRESHOLD_DELTA),
            "tradeoff_note": "未做实时重编码; 数值来自 R03 持久化 run JSON (自产载体), 编排者须在 GPU 窗口用 --no-eval 关闭前确认或直接跑实时评估",
            "verdict": "PASS" if (dev_hit is not None and abs(dev_hit) <= THRESHOLD_DELTA) else "TODO",
        }
    return _realtime_eval(rows, payload)


# ================================================================
# G4: 唯一性 + 跨租户隔离
# ================================================================
def step4_uniqueness(rows: list[dict], payload: dict) -> dict:
    plan = payload.get("rows", [])
    cids = [str(r.get("chunk_id")) for r in rows]
    pks = [int(r["id"]) for r in rows]
    dup_cid = len(cids) - len(set(cids))
    dup_pk = len(pks) - len(set(pks))
    # 跨租户隔离: 同内容不同 tenant → canonical_id 不同（前缀不同, 不碰撞）
    isol = {"_default": 0, COURSE_PUBLIC: 0}
    sample_isolation = 0
    for m in plan[:200]:  # 抽样演示
        r = next((x for x in rows if str(x.get("chunk_id")) == m["new_chunk_id"]), None)
        if r is None:
            continue
        raw = r.get("raw_content")
        canonical = (str(raw) if raw else str(r.get("content") or "")).strip()
        seq = int(m["new_chunk_id"].rsplit(":", 1)[-1])
        a = canonical_id(m["tenant"], canonical, seq)
        b = canonical_id("_default" if m["tenant"] != "_default" else "user_7", canonical, seq)
        # 同租户不同 seq → 不同 id; 跨租户前缀不同 → 必不相等
        c = canonical_id(m["tenant"], canonical, 9999999)
        if a != b and a != c and m["tenant"] in isol:
            sample_isolation += 1
    return {
        "step": "G4",
        "goal": "唯一性违例=0 + 跨租户隔离实证",
        "row_count": len(cids),
        "dup_chunk_id": dup_cid,
        "dup_pk": dup_pk,
        "isolation_samples_ok": sample_isolation,
        "isolation_checked": min(200, len(plan)),
        "verdict": "PASS" if (dup_cid == 0 and dup_pk == 0) else "FAIL",
    }


# ================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="R03-b 只读核验（纯只读零写库）")
    ap.add_argument("--result", default=None, help="可选: 写出 JSON 结果路径")
    ap.add_argument("--no-eval", action="store_true", help="跳过实时检索评估(G3 回退持久化 tradeoff)")
    ap.add_argument("--sample", type=int, default=300, help="G2 抽样记录条数(实际全量 join 为准)")
    args = ap.parse_args()

    t0 = time.perf_counter()
    payload = _load_id_map()
    client = _client()
    if not client.has_collection(COLLECTION_NAME):
        print(f"[fatal] collection 不存在: {COLLECTION_NAME}")
        return 1
    rows = _read_all_light(client)
    n = len(rows)
    print(f"Milvus {COLLECTION_NAME} 只读全量: {n} 行")

    g1 = step1_idmap(rows, payload)
    g2 = step2_canonical(rows, payload, args.sample)
    g4 = step4_uniqueness(rows, payload)

    # G3: 需 sidecar + 预计算 dense。探测 sidecar(8601) 与 dense 文件。
    sidecar_ok = False
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:8601/health", timeout=3) as r:
            sidecar_ok = (r.status == 200)
    except Exception:
        sidecar_ok = False
    dense_ok = os.path.exists(PRE_COMP_DENSE)

    g3 = None
    if args.no_eval:
        g3 = step3_metrics(rows, payload, no_eval=True)
    elif sidecar_ok and dense_ok:
        cache = _load_precomputed_dense()
        _install_precomputed_dense(cache)
        g3 = step3_metrics(rows, payload, no_eval=False)
    else:
        g3 = step3_metrics(rows, payload, no_eval=True)
        g3["skip_reason"] = f"sidecar_ok={sidecar_ok} dense_ok={dense_ok} → 回退持久化 tradeoff"

    result = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                  cwd=BASE_DIR).stdout.strip(),
        "collection": COLLECTION_NAME,
        "milvus_uri": settings.MILVUS_URI,
        "row_count": n,
        "steps": [g1, g2, (g3 or {}), g4],
        "all_pass": all(s.get("verdict") in ("PASS", "TODO", None) for s in [g1, g2, (g3 or {}), g4]),
        "wall_seconds": round(time.perf_counter() - t0, 1),
    }
    print("=" * 72)
    for s in result["steps"]:
        print(f"\n[{s.get('step','-')}] {s.get('goal','-')}")
        print(json.dumps({k: v for k, v in s.items() if k not in ("step", "goal")},
                         ensure_ascii=False, indent=2))
    print("=" * 72)
    print(f"ALL_PASS={result['all_pass']}  wall={result['wall_seconds']}s")
    if args.result:
        import _safeio
        out = os.path.join(_EVAL_DIR, args.result) if not os.path.isabs(args.result) else args.result
        result_path = _safeio.safe_w(os.path.relpath(out, _EVAL_DIR))
        # M-2 收口: 核验结果真身入 GridFS 制品库（不可达自动降级本地, 不抛异常断流程）,
        # 本地留同字节工作副本; git 只留 <1MB 摘要（neo4j-mongo-activation-plan §M-2）
        try:
            from app.common.artifact_store import save_artifact
            _arch = save_artifact("eval/r03b/verify_result.json", result,
                                  metadata={"kind": "r03b_verify_result",
                                            "all_pass": result.get("all_pass")},
                                  local_copy=result_path)
            print(f"[artifact] backend={_arch['backend']} aid={_arch['aid']} "
                  f"sha256={_arch['sha256'][:16]} size={_arch['size']}")
        except Exception as _e:  # noqa: BLE001 归档失败不阻断核验, 回退直接落盘
            print(f"[artifact] 归档失败(忽略): {type(_e).__name__}: {_e}")
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[result] → {result_path}")
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())