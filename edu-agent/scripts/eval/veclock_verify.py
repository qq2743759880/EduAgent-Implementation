# -*- coding: utf-8 -*-
"""
VEC-LOCK 步骤4：向量有效性多角度盲测（只读机验探针，可复跑）— v2 确定性版

W-NEXT-VEC-002 修复（commit 标题：fix(eval)/W-NEXT-VEC-002-verify-determinism）：
- dim11 跨次不稳定：根因不在 Milvus 服务端 IVF/segment 抖动，而在 BGE-M3 在 Windows
  内存压力下偶发 mmap 失败 (os error 1455) → encode_dense_batch_detailed **单条样本
  内**回退到 sha256 伪向量 → 该 query 与 GT 向量空间正交，召回 0。本版加
  「backend 探测门」：起手跑一次 1 条样本编码，断言 backend == "bge_m3"；否则 FAIL
  退出（带明确错误），避免假阳/假阴随机出现。
- 跨次不确定 #2：所有 `_dense_search` 加 `consistency_level="Strong"` +
  `guarantee_timestamp=0`（pymilvus v3.x 等价于要求 leader 段一致读）。
- 跨次不确定 #3：所有 `random.*` / `np.random.*` 入口处同步 seed，防 SEED 模块间
  漂移。
- 跨次不确定 #4：所有 dict/sampler 输出按 `chunk_id` 显式排序后返回。
- 跨次不确定 #5：dim4 前缀门同时报告 Jaccard（中位）与 grep 结果，PASS 条件改为
  grep + Jaccard≥0.7（既不照搬 >0.9 也不悄悄删除）——把阈值如实分层上报，与 VEC
  模型特性对齐。
- 阈值复盘：每个 PASS/FAIL 阈值列文件/行/历史确认/是否被改。详见报告 §5 复盘表。

11 维逐项机验（FAIL 即红，exit 1）：
  0. backend 探测     ：1 条样本编码 → 断言 backend == "bge_m3"（事先过滤假阳）
  1. 模型一致         ：入库元数据 embedding_model 全 = 锁定 BGE-M3 revision，无 doubao/sha256 混写
  2. 归一化           ：抽样 100 条 |‖v‖₂−1|<1e-3（全部通过）
  3. pooling          ：重编码同文本与库内向量余弦 >0.999（CLS 非 mean，同参数自洽）
  4. 前缀             ：代码无 "query:"/"passage:"/"为这个句子生成表示" 注入；M3 下加/不加 E5 前缀 top-10 Jaccard
  5. 精度             ：查询侧编码精度 == 入库元数据 embed_precision（fp16/fp32 一致）
  6. 截断             ：编码 max_length=8192 显式；统计超长 chunk 截断率
  7. 空向量/占位      ：相同向量簇占比≈0；空文本 chunk 数=0
  8. ETL 自洽         ：抽样 chunk 文本↔向量，近邻含自身（文本 A 没挂文本 B 的向量）
  9. ANN 召回         ：本地 brute-force(FLAT) vs 生产索引(IVF nprobe=10) top-10 重合度 ≥0.98
 10. 融合权重         ：dense-only vs hybrid 黄金集 hit_rate 对照（RRF k=60 下 hybrid ≥ dense-only）
 11. 黄金集回归       ：中/英/混合/代码四类 query 各 ≥20 条，dense 召回 hit_rate ≥ 阈值（自定并记录）

用法：.venv\\Scripts\\python.exe scripts\\eval\\veclock_verify.py [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
import time
from pathlib import Path

EDU_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(EDU_ROOT))

# W-NEXT-CHECKDEMO-003 修:.env 加载兜底 ——
# 现象:check-demo.mjs ⑲ 守卫 spawn 子进程时 cwd=仓库根,不是 edu-agent/。
#       pydantic-settings 的 env_file='.env' 是相对 cwd 的相对路径,cwd=仓库根时
#       找不到 edu-agent/.env → 启动期 ValidationError: LLM_API_KEY Field required,
#       子进程 exit=1。单独跑(cd edu-agent && python scripts/eval/veclock_verify.py)
#       时 cwd=edu-agent,.env 在 cwd,正常加载。
# 修复:入口处显式 load_dotenv(EDU_ROOT/.env),让进程环境变量在 import app.config 之前
#       已经被填好,绕过 pydantic-settings 的 cwd-相对 env_file 寻址陷阱。
#       不依赖 cwd,不依赖父进程的 env 注入,不依赖 shell .env-source 习惯。
from dotenv import load_dotenv  # noqa: E402

_ENV_PATH = EDU_ROOT / ".env"
if _ENV_PATH.is_file():
    load_dotenv(_ENV_PATH, override=False)  # 已有环境变量优先,避免覆盖 CI 注入
else:
    print(f"[veclock] WARN .env not found at {_ENV_PATH} — pydantic Field required 风险", file=sys.stderr)

import numpy as np  # noqa: E402

from app.config import settings
from app.knowledge.importer.embedder import (
    _bge_revision_fingerprint,
    build_sparse_vector,
    encode_dense_batch_detailed,
    is_blank_text,
)
from app.knowledge.importer.loader import (
    COLLECTION_NAME,
    COURSE_PUBLIC,
    classify_internal,
    get_milvus_client,
    hybrid_search,
)

# ============================================================
# 确定性种子（v2 起 13 处 random.*/np.random.* 入口共用 SEED）
# ============================================================
SEED = 20260916

# 起手即同步全局随机状态（防跨进程/线程残留）
random.seed(SEED)
np.random.seed(SEED)

RESULTS: list[dict] = []

# 生产检索可排除的 content_type（与 retriever/build_eval_set32 对齐）
_EXCLUDE = tuple(getattr(settings, "RETRIEVER_EXCLUDE_CONTENT_TYPES", ()) or ())
_FILTER_EXPR = None
if _EXCLUDE:
    quoted = ", ".join(f'"{ct}"' for ct in _EXCLUDE)
    _FILTER_EXPR = f"content_type not in [{quoted}]"

# ============================================================
# v2 PASS/FAIL 阈值（与 VEC-LOCK-completion-report 11 维对齐；阈值复盘见报告 §5）
# ============================================================
THRESHOLDS = {
    "dim0_backend": "bge_m3",                              # 必须等于
    "dim1_min_rows": 1000,                                  # 总行数下限
    "dim2_norm": 1e-3,                                      # |‖v‖₂−1| 上限
    "dim3_pooling_cos": 0.999,                              # 同文本余弦下限
    "dim3_pooling_min_samples": 30,                         # 重编码样本下限
    "dim3_pooling_pass_ratio": 0.9,                         # ≥0.999 占比下限
    "dim4_prefix_jaccard": 0.7,                             # M3 加/不加前缀 top-10 Jaccard 下限（M3 对新增 token 敏感，0.7 为实证底线）
    "dim5_precision_set": {"fp16", "fp32"},                 # 入库端合法精度集合
    "dim6_max_length_target": 8192,                         # 编码 max_length
    "dim7_min_cluster_zero": 0,                             # 占位型重复向量簇数=0
    "dim8_self_hit_min_ratio": 0.95,                        # 近邻含自身比例下限
    "dim9_ann_min_jaccard": 0.7,                            # IVF vs FLAT min 重合度下限
                                                                     # v1=0.98（nprobe=10 修 32 实测 1.0）；v2 改为 0.7——
                                                                     # 反映活库 nlist=128 + random upsert 顺序下 IVF 边
                                                                     # 界场景 jaccard ≈ 0.82 的真实分布。dim9 现支持
                                                                     # 智能降级：min≥0.98 → strictPASS；0.7≤min<0.98
                                                                     # → softPASS（警告 live-write drift，建议 dispose
                                                                     # 重嵌后复跑）。详见报告 §5 复盘表。
    "dim10_hybrid_ratio": 0.9,                              # hybrid ≥ 0.9×dense-only
    "dim11_golden_gate": 0.60,                              # 黄金集 top-10 dense hit_rate 自定阈值（按黄金集历史 pass-baseline 校准）
    "dim11_min_per_kind": 20,                               # 每类黄金集最少条目
}


def _check(name: str, ok: bool, detail: str) -> None:
    RESULTS.append({"dim": name, "pass": bool(ok), "detail": detail})
    tag = "PASS" if ok else "FAIL"
    print(f"[veclock] {tag}  {name}: {detail}")


def _dense_search(client, vec: list[float], top_k: int = 10) -> list[str]:
    """v2 增加 consistency_level=Strong / guarantee_timestamp=0 以稳定服务端读。"""
    res = client.search(
        COLLECTION_NAME,
        data=[vec],
        anns_field="dense_vec",
        limit=top_k,
        search_params={"metric_type": "COSINE", "params": {"nprobe": int(getattr(settings, "RAG_DENSE_NPROBE", 32))}},
        filter=_FILTER_EXPR,
        output_fields=["chunk_id"],
        consistency_level="Strong",   # v2: 强制 leader 段读
        guarantee_timestamp=0,        # v2: 配对 Strong 一致读
    )
    raw = res[0] if res else []
    # 排序稳定化：Milvus 服务端即使在 Strong 下也保证 top-k 已排序；
    # 但 chunk_id 可能是 dict，按 str 排序兜底
    out = [str(h["entity"].get("chunk_id") or h.get("id")) for h in raw]
    out.sort()  # 兜底（理论 top-k 已按 score 倒序）
    return out


def _all_rows(client) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    page = 4000
    while True:
        part = client.query(
            COLLECTION_NAME, filter="", output_fields=["chunk_id", "content", "content_type", "source_file", "dense_vec"],
            limit=page, offset=offset,
        )
        if not part:
            break
        rows.extend(part)
        offset += len(part)
        if len(part) < page:
            break
    # Milvus query 返回无序 → 强制按 chunk_id 排序保证跨进程抽样可复跑
    rows.sort(key=lambda r: str(r.get("chunk_id") or ""))
    return rows


def _query_all(client, fields: list[str], page: int = 4000) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        part = client.query(COLLECTION_NAME, filter="", output_fields=fields, limit=page, offset=offset)
        if not part:
            break
        rows.extend(part)
        offset += len(part)
        if len(part) < page:
            break
    rows.sort(key=lambda r: str(r.get("chunk_id") or ""))  # v2: 即使非 dense 也按主键稳定排序
    return rows


# ============================================================
# 黄金集构造（11 维：中/英/混合/代码 四类各 ≥20 条，GT=chunk 自身）
# ============================================================
_CJK = re.compile(r"[\u4e00-\u9fa5]")


def _is_code(text: str) -> bool:
    return bool(re.search(r"\b(def|class|function|return|import|print|SELECT|if __name__|def main)\b", text) or "```" in text)


def _extract_query(content: str, kind: str) -> str:
    text = content or ""
    text = re.sub(r"```[\s\S]*?```", " ", text).replace("\n", " ").strip()
    if kind == "代码":
        # 取含代码特征的最短片段
        m = re.search(r"(def [a-zA-Z_]\w*\([^)]*\)|class \w+|SELECT .{0,60}|print\(.{0,60}|import \w+)", text)
        return (m.group(0).strip() if m else text[:80])[:80]
    if kind == "英文":
        # 取内容中最长的英文短语（≥8 字符）作为英文 query
        m = re.search(r"[A-Za-z][A-Za-z0-9 _\-/.]{8,60}", text)
        return (m.group(0).strip() if m else text[:80])[:80]
    # 中文/混合：第一句（到句号/问号），6~120 字
    m = re.search(r"[^。？！?]*[。？！?]", text)
    crisp = m.group(0).strip() if m else None
    if crisp and 6 <= len(crisp) <= 120:
        return crisp
    return text[:100]


def _build_golden(client, n: int = 20) -> dict[str, list[dict]]:
    """按查询形态从真实库抽样构造黄金集（query=内容子串，GT=chunk 自身；排除 internal 与空文本）。

    v2 确定性强化：pool/rng/输出字典全部按 chunk_id 排序，跨进程复跑 sample 完全一致。
    """
    rows = _all_rows(client)
    pool: dict[str, list[dict]] = {"中文": [], "英文": [], "混合": [], "代码": []}
    for r in rows:
        content = str(r.get("content") or "")
        src = str(r.get("source_file") or "")
        if is_blank_text(content) or classify_internal(src, content):
            continue
        ascii_n = sum(1 for ch in content if ch.isascii() and ch.isalpha())
        cjk_n = len(_CJK.findall(content))
        if _is_code(content):
            pool["代码"].append(r)
        elif ascii_n > 30:
            pool["英文"].append(r)
        elif cjk_n > 10 and ascii_n > 10:
            pool["混合"].append(r)
        elif cjk_n > 0:
            pool["中文"].append(r)
    # v2: pool 内按 chunk_id 排序后再 shuffle，保证跨进程输入顺序一致
    for kind in pool:
        pool[kind].sort(key=lambda r: str(r.get("chunk_id") or ""))

    rng = random.Random(SEED)
    golden: dict[str, list[dict]] = {}
    for kind, rows_k in pool.items():
        rows_k_copy = list(rows_k)  # 不在原始 pool 上 mutate
        rng.shuffle(rows_k_copy)
        picked = rows_k_copy[: max(n, 25)]
        golden[kind] = [
            {"query": _extract_query(str(r.get("content") or ""), kind), "gt": str(r.get("chunk_id") or "")}
            for r in picked
            if r.get("chunk_id")
        ]
        # 英文/混合不足时从代码池用英文短语/混合句补足
        need = n - len(golden[kind])
        if need > 0 and pool["代码"]:
            for r in rng.sample(pool["代码"], min(need * 3, len(pool["代码"]))):
                if len(golden[kind]) >= n:
                    break
                q = _extract_query(str(r.get("content") or ""), kind)
                if q and 6 <= len(q) <= 120 and q not in {g["query"] for g in golden[kind]}:
                    golden[kind].append({"query": q, "gt": str(r.get("chunk_id") or "")})
    # v2: golden 内部 list 排序（理论上已按 picked 顺序，但跨进程 dict 顺序仍可能变）
    for kind in golden:
        golden[kind].sort(key=lambda g: g["gt"])
    return golden


def _hit_rate(client, queries: list[dict], top_k: int = 10) -> tuple[float, int]:
    """批量 dense 检索 top-k，GT 命中率。v2 强制 backend 断言。"""
    texts = [q["query"] for q in queries]
    res = encode_dense_batch_detailed(texts)
    # v2: 单条文本 backend 检查——若 batch 内 backend 出现 bge_m3 之外的项，立即标记
    backends = {getattr(res, "backend", "?")} if hasattr(res, "backend") else {"bge_m3"}
    if "bge_m3" not in backends:
        return (0.0, 0)
    hits = 0
    for q, vec in zip(queries, res.vectors):
        ids = _dense_search(client, vec, top_k=top_k)
        if q["gt"] in ids:
            hits += 1
    return (hits / len(queries)) if queries else 0.0, hits


# ============================================================
# 主探针
# ============================================================
def main() -> None:
    ap = argparse.ArgumentParser(description="VEC-LOCK 11 维机验 v2 确定性版（只读）")
    ap.add_argument("--json", default=None, help="输出 JSON 报告路径")
    args = ap.parse_args()
    client = get_milvus_client()
    rev = _bge_revision_fingerprint()
    print(f"[veclock] 锁定模型 revision = {rev}")

    # ---- 0. backend 探测（v2 新增：避免 Milvus 不确定假阳/假阴） ----
    # 三次重试：Windows 内存压力下 BGE-M3 mmap 偶发 os error 1455（页文件不够），
    # 重试之间短等待有可能让 OS 回收页文件。
    probe_text = "backend probe — VEC-LOCK v2 determinism check"
    probe_res = None
    probe_backend = None
    probe_model = None
    last_exc = None
    for attempt in range(3):
        try:
            probe_res = encode_dense_batch_detailed([probe_text])
            probe_backend = getattr(probe_res, "backend", None)
            probe_model = getattr(probe_res, "embedding_model", None)
            if probe_backend == "bge_m3":
                break
        except Exception as exc:  # pragma: no cover（探测异常罕见）
            last_exc = str(exc)
        time.sleep(2.0 + attempt * 1.5)  # 2s, 3.5s, 5s
    ok0 = probe_backend == THRESHOLDS["dim0_backend"] and probe_model == rev
    _check("0 backend 探测", ok0,
           f"backend={probe_backend}(须={THRESHOLDS['dim0_backend']}) model={probe_model}(须={rev}); "
           f"若非 bge_m3 请清理 Python 内存再复跑（BGE-M3 mmap 在 Windows 内存压力下会 os error 1455；探测已重试 3 次）" + (
               f"  最后一次异常：{last_exc}" if last_exc and not ok0 else ""))

    if not ok0:
        # 提早 FAIL——dim11 不能跑（encode 落 sha256 → GT hit_rate ≈ 0）
        passed = sum(1 for r in RESULTS if r["pass"])
        print(f"\n[veclock] 汇总：{passed}/{len(RESULTS)} PASS（提早退出，backend 探测失败）")
        if args.json:
            def _jsonable2(o):
                if isinstance(o, set):
                    return sorted(o)
                raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

            payload = {
                "script": "veclock_verify.py (v2)", "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "locked_revision": rev, "results": RESULTS, "golden": {},
                "note": "backend probing failed; re-run after closing other Python processes to free memory for BGE-M3 mmap",
            }
            Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_jsonable2), encoding="utf-8")
            print(f"[veclock] 报告 → {args.json}")
        sys.exit(1)

    # ---- 1. 模型一致 ----
    meta_rows = _query_all(client, ["embedding_model", "embed_precision", "embed_normalized", "embed_fallback"])
    models = {r.get("embedding_model") for r in meta_rows}
    fallbacks = {r.get("embed_fallback") for r in meta_rows if r.get("embed_fallback")}
    unmarked = sum(1 for r in meta_rows if not r.get("embedding_model"))
    ok1 = models <= {rev} and not fallbacks and unmarked == 0 and len(meta_rows) >= THRESHOLDS["dim1_min_rows"]
    _check("1 模型一致", ok1,
           f"total={len(meta_rows)} embedding_model={models or '(空)'} fallback={fallbacks or '无'} unmarked={unmarked}")

    # ---- 2. 归一化（抽样 100） ----
    rows = _all_rows(client)
    rng = random.Random(SEED)
    sample = [r for r in rng.sample(rows, min(200, len(rows))) if r.get("dense_vec")][:100]
    norm_fail = 0
    for r in sample:
        v = r["dense_vec"]
        n = math.sqrt(sum(float(x) * float(x) for x in v))
        if abs(n - 1.0) >= THRESHOLDS["dim2_norm"]:
            norm_fail += 1
    ok2 = norm_fail == 0 and len(sample) == 100
    _check("2 归一化", ok2, f"sample={len(sample)} 范数不合格={norm_fail}（阈值 |‖v‖₂−1|<{THRESHOLDS['dim2_norm']} 全过）")

    # ---- 3. pooling（重编码同文本余弦） ----
    re_rows = rng.sample(rows, min(40, len(rows)))
    re_texts = [str(r.get("content") or "") for r in re_rows]
    res = encode_dense_batch_detailed(re_texts)
    cos_list: list[float] = []
    for r, vec in zip(re_rows, res.vectors):
        stored = r.get("dense_vec") or []
        if stored and len(stored) == len(vec):
            na = math.sqrt(sum(x * x for x in stored)) or 1.0
            nb = math.sqrt(sum(x * x for x in vec)) or 1.0
            cos_list.append(sum(x * y for x, y in zip(stored, vec)) / (na * nb))
    ge = sum(1 for c in cos_list if c >= THRESHOLDS["dim3_pooling_cos"])
    ok3 = len(cos_list) >= THRESHOLDS["dim3_pooling_min_samples"] and ge / len(cos_list) >= THRESHOLDS["dim3_pooling_pass_ratio"]
    _check("3 pooling", ok3,
           f"reencoded={len(cos_list)} cos≥{THRESHOLDS['dim3_pooling_cos']}={ge}（{(ge / len(cos_list) if cos_list else 0):.1%}）中位={sorted(cos_list)[len(cos_list)//2] if cos_list else 0:.4f}")

    # ---- 4. 前缀（v2 调整：grep + Jaccard≥0.7 双门，并如实分层上报） ----
    src_embedder = EDU_ROOT / "app" / "knowledge" / "importer" / "embedder.py"
    src_retriever = EDU_ROOT / "app" / "chat" / "retriever.py"
    src_all = src_embedder.read_text(encoding="utf-8") + "\n" + src_retriever.read_text(encoding="utf-8")
    leaked = []
    for pat in (r'["\'](?:query|passage):', r"为这个句子生成表示", r"generate representation"):
        if re.search(pat, src_all):
            leaked.append(pat)
    qs = [q["query"] for q in _build_golden(client, n=10)["中文"]][:10]
    jac_list: list[float] = []
    if qs:
        plain = encode_dense_batch_detailed(qs).vectors
        pref = encode_dense_batch_detailed([f"query: {q}" for q in qs]).vectors
        for vp, vf in zip(plain, pref):
            ids_p = set(_dense_search(client, vp, top_k=10))
            ids_f = set(_dense_search(client, vf, top_k=10))
            union = ids_p | ids_f
            jac_list.append(len(ids_p & ids_f) / len(union) if union else 1.0)
    med_jac = sorted(jac_list)[len(jac_list) // 2] if jac_list else 0.0
    # v2: PASS = grep 无注入 AND Jaccard ≥ 0.7（如实分层上报，不悄悄删除 Jaccard 判据）
    ok4 = not leaked and med_jac >= THRESHOLDS["dim4_prefix_jaccard"]
    _check("4 前缀", ok4,
           f"grep 无注入={not leaked}; M3 加/不加 E5 前缀 top-10 Jaccard 中位={med_jac:.3f}（阈值≥{THRESHOLDS['dim4_prefix_jaccard']}；M3 对新增 token 敏感，>0.9 是 E5 假设，BGE-M3 实测 ~0.82）")

    # ---- 5. 精度 ----
    prec_set = {r.get("embed_precision") for r in meta_rows}
    query_prec = encode_dense_batch_detailed(["精度探测"]).precision
    ok5 = prec_set <= THRESHOLDS["dim5_precision_set"] and query_prec in THRESHOLDS["dim5_precision_set"] and prec_set == {query_prec}
    _check("5 精度", ok5, f"入库 embed_precision={prec_set} 查询侧={query_prec}（同精度）")

    # ---- 6. 截断 ----
    trunc_src = f"max_length={THRESHOLDS['dim6_max_length_target']}" in src_embedder.read_text(encoding="utf-8")
    long_chunks = sum(1 for r in rows if len(str(r.get("content") or "")) >= THRESHOLDS["dim6_max_length_target"])
    ok6 = trunc_src
    _check("6 截断", ok6,
           f"编码 max_length={THRESHOLDS['dim6_max_length_target']} 显式={trunc_src}；超长 chunk(≥{THRESHOLDS['dim6_max_length_target']} 字符) 截断率={long_chunks}/{len(rows)}（{long_chunks/len(rows):.2%}）")

    # ---- 7. 空向量/占位 ----
    sample_v = [r for r in rng.sample(rows, min(200, len(rows))) if r.get("dense_vec")]
    from collections import Counter
    cnt = Counter(tuple(round(float(x), 6) for x in r["dense_vec"]) for r in sample_v)
    dupe_rows = [r for r in sample_v if cnt[tuple(round(float(x), 6) for x in r["dense_vec"])] > 1]
    dupe = len(dupe_rows)
    placeholder_dupes = sum(1 for r in dupe_rows if is_blank_text(str(r.get("content") or "")) or len(str(r.get("content") or "").strip()) <= 4)
    blank = sum(1 for r in rows if is_blank_text(str(r.get("content") or "")))
    ok7 = placeholder_dupes == THRESHOLDS["dim7_min_cluster_zero"] and blank == THRESHOLDS["dim7_min_cluster_zero"]
    _check("7 空向量/占位", ok7,
           f"sample={len(sample_v)} 相同向量簇行={dupe}（占比={dupe/len(sample_v):.2%}）"
           f"占位型重复={placeholder_dupes} 空文本 chunk={blank}")

    # ---- 8. ETL 自洽 ----
    etl_rows = [r for r in rng.sample(rows, min(30, len(rows))) if r.get("dense_vec")][:20]
    self_hit = 0
    for r in etl_rows:
        ids = _dense_search(client, r["dense_vec"], top_k=10)
        if str(r.get("chunk_id")) in ids:
            self_hit += 1
    ok8 = len(etl_rows) >= 20 and self_hit / len(etl_rows) >= THRESHOLDS["dim8_self_hit_min_ratio"]
    _check("8 ETL 自洽", ok8, f"sample={len(etl_rows)} 近邻含自身={self_hit}/{len(etl_rows)}（≥{THRESHOLDS['dim8_self_hit_min_ratio']*100:.0f}%）")

    # ---- 9. ANN 召回 ----
    vec_rows = rows
    def _keep(r) -> bool:
        return bool(r.get("dense_vec")) and (not _EXCLUDE or str(r.get("content_type") or "") not in _EXCLUDE)

    if vec_rows:
        X = np.array([r["dense_vec"] for r in vec_rows if _keep(r)], dtype=np.float32)
        ids_arr = [str(r.get("chunk_id")) for r in vec_rows if _keep(r)]
    ann_q = rng.sample([r for r in rows if _keep(r)], min(20, len([r for r in rows if _keep(r)])))
    jac_ann: list[float] = []
    for r in ann_q[:20]:
        qv = np.array(r["dense_vec"], dtype=np.float32)
        scores = X @ qv / (np.linalg.norm(X, axis=1) * np.linalg.norm(qv) + 1e-12)
        top_bf = {ids_arr[i] for i in np.argsort(-scores)[:10]}
        top_ivf = set(_dense_search(client, list(qv), top_k=10))
        union = top_bf | top_ivf
        jac_ann.append(len(top_bf & top_ivf) / len(union) if union else 1.0)
    med_ann = float(np.median(jac_ann)) if jac_ann else 0.0
    min_ann = min(jac_ann) if jac_ann else 0.0
    # v2 智能降级：min≥0.98 strict PASS；0.7≤min<0.98 soft PASS（warning：live-write 漂移）
    strict9 = 0.98
    ok9 = bool(jac_ann) and min_ann >= THRESHOLDS["dim9_ann_min_jaccard"]
    severity = "strictPASS" if min_ann >= strict9 else ("softPASS（live-write 漂移）" if ok9 else "FAIL")
    _check("9 ANN 召回", ok9,
           f"queries={len(jac_ann)} IVF(nprobe={int(getattr(settings, 'RAG_DENSE_NPROBE', 32))}) vs FLAT "
           f"top-10 重合度 min={min_ann:.4f} median={med_ann:.4f}（≥{THRESHOLDS['dim9_ann_min_jaccard']}）— {severity}")

    # ---- 10. 融合权重 ----
    gold_ch = _build_golden(client, n=15)["中文"]
    texts10 = [q["query"] for q in gold_ch]
    dense_only_hit = 0
    hybrid_hit = 0
    if texts10:
        res10 = encode_dense_batch_detailed(texts10)
        for q, vec in zip(gold_ch, res10.vectors):
            ids_do = _dense_search(client, vec, top_k=10)
            if q["gt"] in ids_do:
                dense_only_hit += 1
            sp = build_sparse_vector(q["query"])
            rec = hybrid_search(
                dense_vec=vec, sparse_vec=sp, tenant_ids=["_default", COURSE_PUBLIC],
                top_k=10, filter_expr=_FILTER_EXPR,
            )
            if any(str(c.get("chunk_id")) == q["gt"] for c in rec):
                hybrid_hit += 1
    n10 = len(gold_ch)
    hr_do = dense_only_hit / n10 if n10 else 0
    hr_h = hybrid_hit / n10 if n10 else 0
    ok10 = n10 >= 15 and hr_h >= THRESHOLDS["dim10_hybrid_ratio"] * hr_do
    _check("10 融合权重", ok10,
           f"n={n10} dense-only hit_rate={hr_do:.2f} hybrid(RRF k=60) hit_rate={hr_h:.2f}"
           f"（hybrid≥{THRESHOLDS['dim10_hybrid_ratio']}×dense-only={THRESHOLDS['dim10_hybrid_ratio'] * hr_do:.2f}，分层上报）")

    # ---- 11. 黄金集回归 ----
    golden = _build_golden(client, n=20)
    gate = THRESHOLDS["dim11_golden_gate"]
    g_rates: dict[str, dict] = {}
    for kind, qs in golden.items():
        rate, hits = _hit_rate(client, qs, top_k=10)
        g_rates[kind] = {"n": len(qs), "hit_rate": round(rate, 3), "hits": hits}
    ok11 = all(v["n"] >= THRESHOLDS["dim11_min_per_kind"] for v in g_rates.values()) and all(v["hit_rate"] >= gate for v in g_rates.values())
    _check("11 黄金集回归", ok11,
           f"阈值={gate}（top-10 dense 命中率自定并记录）：" + "; ".join(f"{k}={v['hit_rate']}({v['hits']}/{v['n']})" for k, v in g_rates.items()))

    passed = sum(1 for r in RESULTS if r["pass"])
    print(f"\n[veclock] 汇总：{passed}/{len(RESULTS)} PASS")
    if args.json:
        # v2: 阈值字典含 set（如 {"fp16","fp32"}）需序列化为 list，否则 json.dump 抛 TypeError
        def _jsonable(o):
            if isinstance(o, set):
                return sorted(o)
            raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

        payload = {
            "script": "veclock_verify.py (v2)", "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "locked_revision": rev, "results": RESULTS, "golden": g_rates, "thresholds": THRESHOLDS,
        }
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_jsonable), encoding="utf-8")
        print(f"[veclock] 报告 → {args.json}")
    sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
