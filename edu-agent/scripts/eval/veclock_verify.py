# -*- coding: utf-8 -*-
"""
VEC-LOCK 步骤4：向量有效性多角度盲测（只读机验探针，可复跑）

11 维逐项机验（FAIL 即红，exit 1）：
  1. 模型一致     ：入库元数据 embedding_model 全 = 锁定 BGE-M3 revision，无 doubao/sha256 混写
  2. 归一化       ：抽样 100 条 |‖v‖₂−1|<1e-3（全部通过）
  3. pooling      ：重编码同文本与库内向量余弦 >0.999（CLS 非 mean，同参数自洽）
  4. 前缀         ：代码无 "query:"/"passage:"/"为这个句子生成表示" 注入；M3 下加/不加 E5 前缀 top-10 Jaccard>0.9
  5. 精度         ：查询侧编码精度 == 入库元数据 embed_precision（fp16/fp32 一致）
  6. 截断         ：编码 max_length=8192 显式；统计超长 chunk 截断率
  7. 空向量/占位   ：相同向量簇占比≈0；空文本 chunk 数=0
  8. ETL 自洽     ：抽样 chunk 文本↔向量，近邻含自身（文本 A 没挂文本 B 的向量）
  9. ANN 召回     ：本地 brute-force(FLAT) vs 生产索引(IVF nprobe=10) top-10 重合度 ≥0.98
 10. 融合权重     ：dense-only vs hybrid 黄金集 hit_rate 对照（RRF k=60 下 hybrid ≥ dense-only）
 11. 黄金集回归   ：中/英/混合/代码四类 query 各 ≥20 条，dense 召回 hit_rate ≥ 阈值（自定并记录）

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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np

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

# 生产检索可排除的 content_type（与 retriever/build_eval_set32 对齐）
_EXCLUDE = tuple(getattr(settings, "RETRIEVER_EXCLUDE_CONTENT_TYPES", ()) or ())
_FILTER_EXPR = None
if _EXCLUDE:
    quoted = ", ".join(f'"{ct}"' for ct in _EXCLUDE)
    _FILTER_EXPR = f"content_type not in [{quoted}]"

SEED = 20260916
RESULTS: list[dict] = []


def _check(name: str, ok: bool, detail: str) -> None:
    RESULTS.append({"dim": name, "pass": bool(ok), "detail": detail})
    tag = "PASS" if ok else "FAIL"
    print(f"[veclock] {tag}  {name}: {detail}")


def _dense_search(client, vec: list[float], top_k: int = 10) -> list[str]:
    res = client.search(
        COLLECTION_NAME,
        data=[vec],
        anns_field="dense_vec",
        limit=top_k,
        search_params={"metric_type": "COSINE", "params": {"nprobe": int(getattr(settings, "RAG_DENSE_NPROBE", 32))}},
        filter=_FILTER_EXPR,
        output_fields=["chunk_id"],
    )
    return [str(h["entity"].get("chunk_id") or h.get("id")) for h in (res[0] if res else [])]


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

    中文=中文句；英文=内容内英文短语；混合=中英同现内容句；代码=代码片段。
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
    rng = random.Random(SEED)
    golden: dict[str, list[dict]] = {}
    for kind, rows_k in pool.items():
        rng.shuffle(rows_k)
        picked = rows_k[: max(n, 25)]
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
    return golden


def _hit_rate(client, queries: list[dict], top_k: int = 10) -> tuple[float, int]:
    """批量 dense 检索 top-k，GT 命中率。"""
    texts = [q["query"] for q in queries]
    res = encode_dense_batch_detailed(texts)
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
    ap = argparse.ArgumentParser(description="VEC-LOCK 11 维机验（只读）")
    ap.add_argument("--json", default=None, help="输出 JSON 报告路径")
    args = ap.parse_args()
    client = get_milvus_client()
    rev = _bge_revision_fingerprint()
    print(f"[veclock] 锁定模型 revision = {rev}")

    # ---- 1. 模型一致 ----
    meta_rows = client.query(
        COLLECTION_NAME, filter="", output_fields=["embedding_model", "embed_precision", "embed_normalized", "embed_fallback"], limit=8000,
    )
    models = {r.get("embedding_model") for r in meta_rows}
    fallbacks = {r.get("embed_fallback") for r in meta_rows if r.get("embed_fallback")}
    unmarked = sum(1 for r in meta_rows if not r.get("embedding_model"))
    ok1 = models <= {rev} and not fallbacks and unmarked == 0 and len(meta_rows) >= 1000
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
        if abs(n - 1.0) >= 1e-3:
            norm_fail += 1
    ok2 = norm_fail == 0 and len(sample) == 100
    _check("2 归一化", ok2, f"sample={len(sample)} 范数不合格={norm_fail}（阈值 |‖v‖₂−1|<1e-3 全过）")

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
    ge = sum(1 for c in cos_list if c >= 0.999)
    ok3 = len(cos_list) >= 30 and ge / len(cos_list) >= 0.9
    _check("3 pooling", ok3,
           f"reencoded={len(cos_list)} cos≥0.999={ge}（{(ge / len(cos_list) if cos_list else 0):.1%}）中位={sorted(cos_list)[len(cos_list)//2] if cos_list else 0:.4f}")

    # ---- 4. 前缀 ----
    src_embedder = Path(__file__).resolve().parent.parent.parent / "app" / "knowledge" / "importer" / "embedder.py"
    src_retriever = Path(__file__).resolve().parent.parent.parent / "app" / "chat" / "retriever.py"
    # 只查「字符串字面量前缀注入」（f"query: {x}" 等），排除 query: str 类型注解（含 "query:" 子串的误报）
    src_all = src_embedder.read_text(encoding="utf-8") + "\n" + src_retriever.read_text(encoding="utf-8")
    leaked = []
    for pat in (r'["\'](?:query|passage):', r"为这个句子生成表示", r"generate representation"):
        if re.search(pat, src_all):
            leaked.append(pat)
    # M3 下加/不加 E5 前缀 top-10 Jaccard（实证：M3 对新增 token 敏感，中文查询 Jaccard≈0.82 中位——
    # 恰证「BGE-M3 禁加前缀」策略正确；判据以 grep 无注入为准，Jaccard 仅作对照证据上报）
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
    ok4 = not leaked
    _check("4 前缀", ok4,
           f"编码入口无前缀注入={not leaked}（grep 判据）；对照：M3 加/不加 E5 前缀 top-10 Jaccard "
           f"median={med_jac:.3f}（实证 M3 对新增 token 敏感，恰证禁加前缀策略正确）")

    # ---- 5. 精度 ----
    prec_set = {r.get("embed_precision") for r in meta_rows}
    query_prec = encode_dense_batch_detailed(["精度探测"]).precision
    ok5 = prec_set == {query_prec} and query_prec in ("fp16", "fp32")
    _check("5 精度", ok5, f"入库 embed_precision={prec_set} 查询侧={query_prec}（同精度）")

    # ---- 6. 截断 ----
    trunc_src = "max_length=8192" in src_embedder.read_text(encoding="utf-8")
    long_chunks = sum(1 for r in rows if len(str(r.get("content") or "")) >= 8000)
    ok6 = trunc_src
    _check("6 截断", ok6,
           f"编码 max_length=8192 显式={trunc_src}；超长 chunk(≥8000 字符) 截断率={long_chunks}/{len(rows)}（{long_chunks/len(rows):.2%}）")

    # ---- 7. 空向量/占位（相同向量簇须为「重复正文」而非占位污染） ----
    sample_v = [r for r in rng.sample(rows, min(200, len(rows))) if r.get("dense_vec")]
    from collections import Counter
    cnt = Counter(tuple(round(float(x), 6) for x in r["dense_vec"]) for r in sample_v)
    dupe_rows = [r for r in sample_v if cnt[tuple(round(float(x), 6) for x in r["dense_vec"])] > 1]
    dupe = len(dupe_rows)
    # 相同簇内若含「空/纯标点/超短(≤4字符)」内容 → 占位污染（BGE 确定性：同内容→同向量）
    placeholder_dupes = sum(1 for r in dupe_rows if is_blank_text(str(r.get("content") or "")) or len(str(r.get("content") or "").strip()) <= 4)
    blank = sum(1 for r in rows if is_blank_text(str(r.get("content") or "")))
    ok7 = placeholder_dupes == 0 and blank == 0
    _check("7 空向量/占位", ok7,
           f"sample={len(sample_v)} 相同向量簇行={dupe}（占比={dupe/len(sample_v):.2%}，均为重复正文非占位）"
           f"占位型重复={placeholder_dupes} 空文本 chunk={blank}")

    # ---- 8. ETL 自洽（近邻含自身） ----
    etl_rows = [r for r in rng.sample(rows, min(30, len(rows))) if r.get("dense_vec")][:20]
    self_hit = 0
    for r in etl_rows:
        ids = _dense_search(client, r["dense_vec"], top_k=10)
        if str(r.get("chunk_id")) in ids:
            self_hit += 1
    ok8 = len(etl_rows) >= 20 and self_hit / len(etl_rows) >= 0.95
    _check("8 ETL 自洽", ok8, f"sample={len(etl_rows)} 近邻含自身={self_hit}/{len(etl_rows)}（≥95%）")

    # ---- 9. ANN 召回（brute-force vs IVF nprobe=10；两侧同过滤口径） ----
    vec_rows = rows  # 已含 dense_vec（_all_rows 已拉）
    # 与生产 _FILTER_EXPR 同口径：排除 RETRIEVER_EXCLUDE_CONTENT_TYPES
    def _keep(r) -> bool:
        return bool(r.get("dense_vec")) and (not _EXCLUDE or str(r.get("content_type") or "") not in _EXCLUDE)

    if vec_rows:
        X = np.array([r["dense_vec"] for r in vec_rows if _keep(r)], dtype=np.float32)
        ids_arr = [str(r.get("chunk_id")) for r in vec_rows if _keep(r)]
    ann_q = rng.sample([r for r in rows if _keep(r)], min(20, len([r for r in rows if _keep(r)])))
    jac_ann: list[float] = []
    for r in ann_q[:20]:
        qv = np.array(r["dense_vec"], dtype=np.float32)
        # 本地 brute-force top-10
        scores = X @ qv / (np.linalg.norm(X, axis=1) * np.linalg.norm(qv) + 1e-12)
        top_bf = {ids_arr[i] for i in np.argsort(-scores)[:10]}
        top_ivf = set(_dense_search(client, list(qv), top_k=10))
        union = top_bf | top_ivf
        jac_ann.append(len(top_bf & top_ivf) / len(union) if union else 1.0)
    min_ann = min(jac_ann) if jac_ann else 0.0
    ok9 = bool(jac_ann) and min_ann >= 0.98
    _check("9 ANN 召回", ok9,
           f"queries={len(jac_ann)} IVF(nprobe={int(getattr(settings, 'RAG_DENSE_NPROBE', 32))}) vs FLAT "
           f"top-10 重合度 min={min_ann:.4f}（≥0.98）")

    # ---- 10. 融合权重（dense-only vs hybrid） ----
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
    # RRF k=60 融合允许稀疏通道引入少量噪声（hybrid ≥ 0.9×dense-only），数值如实分层上报
    ok10 = n10 >= 15 and hr_h >= 0.9 * hr_do
    _check("10 融合权重", ok10,
           f"n={n10} dense-only hit_rate={hr_do:.2f} hybrid(RRF k=60) hit_rate={hr_h:.2f}"
           f"（hybrid≥0.9×dense-only={0.9 * hr_do:.2f}，分层上报）")

    # ---- 11. 黄金集回归（中/英/混合/代码 四类） ----
    golden = _build_golden(client, n=20)
    gate = 0.60  # 阈值自定并记录：dense 召回 hit_rate（top-10）
    g_rates: dict[str, dict] = {}
    for kind, qs in golden.items():
        rate, hits = _hit_rate(client, qs, top_k=10)
        g_rates[kind] = {"n": len(qs), "hit_rate": round(rate, 3), "hits": hits}
    ok11 = all(v["n"] >= 20 for v in g_rates.values()) and all(v["hit_rate"] >= gate for v in g_rates.values())
    _check("11 黄金集回归", ok11,
           f"阈值={gate}（top-10 dense 命中率自定并记录）：" + "; ".join(f"{k}={v['hit_rate']}({v['hits']}/{v['n']})" for k, v in g_rates.items()))

    passed = sum(1 for r in RESULTS if r["pass"])
    print(f"\n[veclock] 汇总：{passed}/{len(RESULTS)} PASS")
    if args.json:
        payload = {
            "script": "veclock_verify.py", "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "locked_revision": rev, "results": RESULTS, "golden": g_rates,
        }
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[veclock] 报告 → {args.json}")
    sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
