# -*- coding: utf-8 -*-
"""
VEC-LOCK 步骤3：存量污染处置（用户已裁决：B 删除 + 全部重嵌入，2026-09-16）

动作（写操作，--apply 才执行；备份先行，可回滚）：
  1. 读对账指纹清单（veclock_full_fingerprint_compact_*.json）
     - 1636 条异模型 doc_chunk（cos≈0，internal 哈希 md）→ 删除旧行后 BGE-M3 重嵌回写
     - 142 条空文本('---') doc_chunk → 直接删除（禁 '.' 占位/纯标点入库）
  2. 导出受影响行全量标量+稀疏向量 → deploy/backups/veclock_dispose_backup_<ts>.json（先于任何写）
  3. 删除 1636+142 行（按 PK id）
  4. 用锁定 BGE-M3（encode_dense_batch_detailed 单一事实源）重嵌 1636 条 content
  5. 回写：标量原样 + 新 dense_vec + VEC-LOCK 元数据四字段（embedding_model/embed_precision/embed_normalized）

用法：
  .venv\\Scripts\\python.exe scripts\\eval\\veclock_dispose.py --dry-run   # 只备份+重编码，零写
  .venv\\Scripts\\python.exe scripts\\eval\\veclock_dispose.py --apply    # 备份→删除→重嵌回写
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.config import settings  # noqa: E402
from app.knowledge.importer.embedder import encode_dense_batch_detailed  # noqa: E402
from app.knowledge.importer.loader import get_milvus_client  # noqa: E402

HANDBOOK = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
BACKUP_DIR = HANDBOOK / "deploy" / "backups"
COLLECTION = settings.MILVUS_COLLECTION


def _latest_fingerprint() -> dict:
    files = sorted(glob.glob(str(BACKUP_DIR / "veclock_full_fingerprint_compact_*.json")))
    if not files:
        raise SystemExit("未找到紧凑指纹清单，先跑 veilock_reconcile.py --full")
    return json.load(open(files[-1], encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description="VEC-LOCK 存量污染处置（备份先行）")
    ap.add_argument("--apply", action="store_true", help="执行写操作（默认 dry-run：只备份+重编码，零写）")
    args = ap.parse_args()
    fp = _latest_fingerprint()
    suspect_ids = [s["id"] for s in fp["suspect_ids"]]
    blank_ids = [b["id"] for b in fp["blank_ids"]]
    print(f"[dispose] 清单：异模型嫌疑 {len(suspect_ids)} 条，空文本 {len(blank_ids)} 条")

    client = get_milvus_client()

    # 1) 按 chunk_id 拉全量行（PK id + 全部标量 + sparse），内存匹配嫌疑集
    print("[dispose] 拉取受影响行（chunk_id→PK 映射）…")
    want = set(suspect_ids) | set(blank_ids)
    rows: list[dict] = []
    offset = 0
    page = 4000
    while True:
        part = client.query(
            COLLECTION,
            filter="",
            output_fields=["id", "chunk_id", "content", "content_type", "source_file", "tenant_id",
                           "visibility", "created_at", "raw_content", "context_prefix",
                           "contextualized", "contextualize_degraded_reason", "internal",
                           "tags", "difficulty", "resource_type", "author", "keywords",
                           "series_code", "series_name", "category", "audience", "goal",
                           "question_bank_code", "question_bank_name", "question_code", "question_type",
                           "sparse_vec"],
            limit=page,
            offset=offset,
        )
        if not part:
            break
        rows.extend(part)
        offset += len(part)
        if len(part) < page:
            break
    matched = [r for r in rows if str(r.get("chunk_id") or "") in want]
    print(f"[dispose] 命中 {len(matched)}/{len(want)} 行")
    missing = want - {str(r.get("chunk_id") or "") for r in matched}
    if missing:
        print(f"[dispose] 警告：{len(missing)} 个 chunk_id 未命中（已在库中？）")

    rebuild_rows = [r for r in matched if str(r.get("chunk_id")) in set(suspect_ids)]
    drop_rows = [r for r in matched if str(r.get("chunk_id")) in set(blank_ids)]

    # 2) 备份（先于任何写）
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"veclock_dispose_backup_{ts}.json"
    backup_payload = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "suspect_ids": suspect_ids,
        "blank_ids": blank_ids,
        "rebuild_rows": rebuild_rows,
        "drop_rows": drop_rows,
    }
    backup_path.write_text(json.dumps(backup_payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[dispose] 备份 → {backup_path}（{len(rebuild_rows)} 重建 + {len(drop_rows)} 删除）")

    # 3) 重编码（BGE-M3 单一事实源）——dry-run 同样执行，验证可重建
    texts = [str(r.get("content") or "") for r in rebuild_rows]
    print(f"[dispose] BGE-M3 重编码 {len(texts)} 条…")
    new_dense: list[list[float]] = []
    meta: dict = {}
    batch = 16
    for i in range(0, len(texts), batch):
        seg = texts[i : i + batch]
        res = encode_dense_batch_detailed(seg)
        if not meta:
            meta = {
                "embedding_model": res.embedding_model,
                "embed_precision": res.precision,
                "embed_normalized": 1 if res.normalized else 0,
            }
        new_dense.extend(res.vectors)
        print(f"[dispose] 重编码 {min(i + batch, len(texts))}/{len(texts)}", flush=True)
    if not meta:
        print("[dispose] 无可重建行")
        return
    print(f"[dispose] 重编码 backend={meta['embedding_model']} precision={meta['embed_precision']}")

    if not args.apply:
        print("[dispose] --dry-run：验证通过，未执行任何写操作")
        return

    # 4) 删除空文本行（先删后建，清索引污染）
    drop_pks = [int(r.get("id")) for r in drop_rows if r.get("id") is not None]
    if drop_pks:
        client.delete(COLLECTION, ids=drop_pks)
        print(f"[dispose] 已删除空文本行 {len(drop_pks)} 条（PK）")

    # 5) 删除异模型旧行 + 重建回写
    rebuild_pks = [int(r.get("id")) for r in rebuild_rows]
    if rebuild_pks:
        client.delete(COLLECTION, ids=rebuild_pks)
        print(f"[dispose] 已删除异模型旧行 {len(rebuild_pks)} 条（PK）")
        data = []
        for r, vec in zip(rebuild_rows, new_dense):
            row = {k: v for k, v in r.items() if k not in ("sparse_vec",)}
            row["dense_vec"] = vec
            row.update(meta)
            # sparse_vec 原样保留（jieba BM25 与模型无关）
            sv = r.get("sparse_vec")
            if isinstance(sv, dict) and sv:
                row["sparse_vec"] = sv
            data.append(row)
        for i in range(0, len(data), 200):
            client.upsert(collection_name=COLLECTION, data=data[i : i + 200], partition_name="_default")
        print(f"[dispose] 已回写重建行 {len(data)} 条（BGE-M3 + 四字段元数据）")
    print("[dispose] 完成。复跑 veilock_reconcile.py --full 验证 0 嫌疑。")


if __name__ == "__main__":
    main()
