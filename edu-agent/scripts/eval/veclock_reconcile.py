# -*- coding: utf-8 -*-
"""
VEC-LOCK 步骤2：存量向量对账（只读，零直写 Milvus）

覆盖集合：edu_knowledge（主库）/ user_memory（记忆向量）/ pf_bagu_kb（八股题库库）

产出（deploy/backups/veclock_reconcile_<ts>.json + 嫌疑清单）：
  1. embed_fallback 标记分布（sha256/cloud 各多少）+ 无标记存量行数
  2. 向量范数合格率（抽样 ≥100 条，|‖v‖₂−1|<1e-3）
  3. 相同向量簇占比（大量完全相同向量 = sha256/占位污染指纹）
  4. 异模型指纹探测：抽样 chunk 文本用当前 BGE-M3 重编码，与库内向量余弦
     （同模型同参数应 >0.999；<0.9 = 异模型/异参数/伪向量嫌疑）
  5. 空文本/占位污染：纯标点/'.'/空文本 chunk 数

用法：
  .venv\\Scripts\\python.exe scripts\\eval\\veclock_reconcile.py            # 抽样对账
  .venv\\Scripts\\python.exe scripts\\eval\\veclock_reconcile.py --full     # edu_knowledge 全量指纹（完整嫌疑清单+分类）
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.knowledge.importer.embedder import is_blank_text, _get_bge_model, encode_dense_batch_detailed  # noqa: E402
from app.knowledge.importer.loader import get_milvus_client  # noqa: E402

HANDBOOK = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
# 脚本在 edu-agent/scripts/eval/ 下，HANDBOOK 应指向 EduAgent实施手册
BACKUP_DIR = HANDBOOK / "deploy" / "backups"

COLS = {
    "edu_knowledge": {"id_field": "chunk_id", "content_field": "content", "vec_field": "dense_vec",
                      "meta_fields": ["embed_fallback", "embedding_model", "embed_precision", "embed_normalized"]},
    "user_memory": {"id_field": "id", "content_field": "content", "vec_field": "vector", "meta_fields": []},
    "pf_bagu_kb": {"id_field": "id", "content_field": "text", "vec_field": "dense", "meta_fields": []},
}

SAMPLE_NORM = 200   # 范数/相同簇抽样数
SAMPLE_RE = 40      # 异模型指纹重编码抽样数


def _cos(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return float("nan")
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _norm2(v) -> float:
    return math.sqrt(sum(float(x) * float(x) for x in v))


def _analyze_vectors(vecs: list[list[float]]) -> dict:
    """范数合格率 + 相同向量簇占比（去重指纹）。"""
    n = len(vecs)
    norms = [_norm2(v) for v in vecs]
    norm_pass = sum(1 for x in norms if abs(x - 1.0) < 1e-3)
    zero_vecs = sum(1 for v in vecs if _norm2(v) < 1e-6)
    # 相同向量簇：四舍五入到 6 位后去重统计
    from collections import Counter
    cnt = Counter(tuple(round(float(x), 6) for x in v) for v in vecs)
    dupe = sum(1 for v in vecs if cnt[tuple(round(float(x), 6) for x in v)] > 1)
    max_cluster = max(cnt.values()) if cnt else 0
    return {
        "sampled": n,
        "norm_pass_rate": round(norm_pass / n, 4) if n else 0,
        "norm_pass": norm_pass,
        "zero_vector_rows": zero_vecs,
        "identical_cluster_rate": round(dupe / n, 4) if n else 0,
        "identical_cluster_rows": dupe,
        "max_cluster_size": max_cluster,
        "distinct_vectors": len(cnt),
    }


def _scan_meta(client, col: str) -> dict:
    """全量扫描元数据（不带向量）：fallback 分布 / 无标记行 / 空文本。"""
    info = COLS[col]
    idf, ctf = info["id_field"], info["content_field"]
    out = {"total": 0, "fallback_dist": {}, "unmarked": 0, "blank_content": 0, "dot_placeholder": 0}
    offset = 0
    batch = 1000
    out_fields = [idf, ctf] + info.get("meta_fields", [])
    while True:
        rows = client.query(
            col,
            filter="",
            output_fields=out_fields,
            limit=batch,
            offset=offset,
        )
        if not rows:
            break
        for r in rows:
            out["total"] += 1
            fb = r.get("embed_fallback")
            if fb:
                out["fallback_dist"][str(fb)] = out["fallback_dist"].get(str(fb), 0) + 1
            if not fb and not r.get("embedding_model"):
                out["unmarked"] += 1
            content = str(r.get(ctf) or "")
            if is_blank_text(content):
                out["blank_content"] += 1
            if content.strip() == ".":
                out["dot_placeholder"] += 1
        offset += batch
        if len(rows) < batch:
            break
    return out


def _sample_vectors(client, col: str, n: int) -> list[dict]:
    """抽样带向量的行（chunk_id + content + vec）。"""
    info = COLS[col]
    idf, ctf, vf = info["id_field"], info["content_field"], info["vec_field"]
    rows = client.query(
        col,
        filter="",
        output_fields=[idf, ctf, vf],
        limit=n,
    )
    return [{**r, "id": str(r.get(idf) or ""), "content": str(r.get(ctf) or ""), "vec": r.get(vf) or []} for r in rows]


def _reencode_fingerprint(client, col: str, samples: list[dict]) -> dict:
    """异模型指纹：用当前 BGE-M3 重编码 content，与库内向量算余弦。"""
    texts = [s["content"] for s in samples if s["content"]]
    if not texts:
        return {"skipped": "no content samples"}
    res = encode_dense_batch_detailed(texts)
    cosines: list[float] = []
    suspects: list[dict] = []
    for s, vec in zip([x for x in samples if x["content"]], res.vectors):
        stored = s["vec"]
        c = _cos(stored, vec)
        cosines.append(c)
        if c < 0.9:
            suspects.append({"id": s["id"], "cosine": round(c, 4), "backend_now": res.backend})
    n = len(cosines)
    return {
        "reencoded": n,
        "backend_now": res.backend,
        "cos_ge_0999": round(sum(1 for c in cosines if c >= 0.999) / n, 4) if n else 0,
        "cos_09_0999": round(sum(1 for c in cosines if 0.9 <= c < 0.999) / n, 4) if n else 0,
        "cos_lt_09": round(sum(1 for c in cosines if c < 0.9) / n, 4) if n else 0,
        "median_cos": round(sorted(cosines)[n // 2], 4) if n else 0,
        "suspect_count": len(suspects),
        "suspects": suspects,
    }


def _full_edu_scan(client) -> dict:
    """edu_knowledge 全量指纹：重编码全部非空行，产完整嫌疑清单 + 分类（供人工裁决处置）。"""
    print("[reconcile] --full：拉取 edu_knowledge 全量行（chunk_id/content/类型/来源/向量）…")
    rows: list[dict] = []
    offset = 0
    page = 4000
    while True:
        part = client.query(
            "edu_knowledge",
            filter="",
            output_fields=["chunk_id", "content", "content_type", "source_file", "tenant_id", "dense_vec"],
            limit=page,
            offset=offset,
        )
        if not part:
            break
        rows.extend(part)
        offset += len(part)
        if len(part) < page:
            break
    print(f"[reconcile] --full：共 {len(rows)} 行")
    out = {"total": len(rows), "checked": 0, "suspects": [], "blank_rows": []}
    from app.knowledge.importer.embedder import encode_dense_batch_detailed

    texts: list[str] = []
    pending: list[dict] = []
    for r in rows:
        content = str(r.get("content") or "")
        rec = {
            "id": str(r.get("chunk_id") or ""),
            "content": content,
            "content_type": r.get("content_type"),
            "source_file": r.get("source_file"),
            "tenant_id": r.get("tenant_id"),
            "vec": r.get("dense_vec") or [],
        }
        if is_blank_text(content):
            out["blank_rows"].append(rec)
            continue
        texts.append(content)
        pending.append(rec)
    out["blank_count"] = len(out["blank_rows"])
    print(f"[reconcile] --full：非空待检 {len(pending)}，空文本 {out['blank_count']}（重编码中…）")
    batch = 16
    sus = []
    for i in range(0, len(texts), batch):
        seg = texts[i : i + batch]
        res = encode_dense_batch_detailed(seg)
        for rec, vec in zip(pending[i : i + batch], res.vectors):
            c = _cos(rec["vec"], vec)
            rec["cosine"] = round(c, 4)
            if c < 0.9:
                sus.append(rec)
    out["checked"] = len(pending)
    out["suspect_count"] = len(sus)
    out["suspects"] = sus
    # 分类统计（按 content_type / source_file 前缀）
    by_type: Counter = Counter(s.get("content_type") or "None" for s in sus)
    by_source: Counter = Counter((str(s.get("source_file") or "")[:60]) for s in sus)
    out["by_content_type"] = dict(by_type)
    out["by_source_top"] = dict(by_source.most_common(15))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="VEC-LOCK 存量对账（只读）")
    ap.add_argument("--full", action="store_true", help="edu_knowledge 全量指纹扫描（完整嫌疑清单+分类）")
    args = ap.parse_args()
    os.makedirs(BACKUP_DIR, exist_ok=True)
    client = get_milvus_client()
    if args.full:
        full = _full_edu_scan(client)
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = BACKUP_DIR / f"veclock_full_fingerprint_{ts}.json"
        out_path.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[reconcile] --full 报告 → {out_path}")
        print(f"[reconcile] --full 摘要：checked={full['checked']} 嫌疑={full['suspect_count']} "
              f"空文本={full['blank_count']} by_type={full['by_content_type']}")
        return
    report: dict = {
        "script": "veclock_reconcile.py",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "backend_config": {"EMBED_BACKEND": os.getenv("EMBED_BACKEND")},
        "collections": {},
    }
    all_suspects: dict[str, list] = {}
    for col in COLS:
        print(f"[reconcile] === {col} ===")
        if col not in client.list_collections():
            print(f"[reconcile] {col} 不存在，跳过")
            continue
        meta = _scan_meta(client, col)
        print(f"[reconcile] {col} total={meta['total']} fallback={meta['fallback_dist']} "
              f"unmarked={meta['unmarked']} blank={meta['blank_content']} dot={meta['dot_placeholder']}")
        section = {"meta": meta}
        if col == "edu_knowledge":
            # 主库做完整四步
            vec_rows = _sample_vectors(client, col, SAMPLE_NORM)
            section["vectors"] = _analyze_vectors([r["vec"] for r in vec_rows if r["vec"]])
            re_rows = _sample_vectors(client, col, SAMPLE_RE)
            fp = _reencode_fingerprint(client, col, re_rows)
            section["reencode_fingerprint"] = fp
            all_suspects[col] = fp.get("suspects", [])
        else:
            # user_memory 全量（124 行小）；pf_bagu_kb 抽样
            n = SAMPLE_NORM if col == "pf_bagu_kb" else 500
            vec_rows = _sample_vectors(client, col, n)
            section["vectors"] = _analyze_vectors([r["vec"] for r in vec_rows if r["vec"]])
            re_rows = _sample_vectors(client, col, min(SAMPLE_RE, max(n // 5, 1)))
            fp = _reencode_fingerprint(client, col, re_rows)
            section["reencode_fingerprint"] = fp
            all_suspects[col] = fp.get("suspects", [])
        report["collections"][col] = section

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = BACKUP_DIR / f"veclock_reconcile_{ts}.json"
    suspect_path = BACKUP_DIR / f"veclock_suspects_{ts}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    suspect_path.write_text(json.dumps(all_suspects, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[reconcile] 报告 → {out_path}")
    print(f"[reconcile] 嫌疑清单 → {suspect_path}")
    print("[reconcile] 摘要：")
    for col, sec in report["collections"].items():
        v = sec.get("vectors", {})
        fp = sec.get("reencode_fingerprint", {})
        print(f"  {col}: 范数合格率={v.get('norm_pass_rate')} 相同簇占比={v.get('identical_cluster_rate')} "
              f"重编码cos<0.9占比={fp.get('cos_lt_09')} 嫌疑数={len(fp.get('suspects', []))}")


if __name__ == "__main__":
    main()
