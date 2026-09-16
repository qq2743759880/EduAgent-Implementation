# -*- coding: utf-8 -*-
"""WNEXT11 任务一 步骤1-2：只读核查 + 备份（零 Milvus 写入）。

扫 `_default` 分区存量行，用 loader.classify_internal（与 loader.py 导入期
internal 打标口径逐字一致：source_file + (raw_content or content)）判定，
产出「应标 internal=true 的 id 清单」并落 deploy/backups/（含时间戳），
同时导出 _default 全量标量字段快照（不含向量）作为数据安全备份。

模式（幂等，可反复跑）：
  python scripts/eval/_wn11_scan_backup.py

铁律：本脚本只读。回填由 _wn11_backfill.py 单独执行（须 --confirm）。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.knowledge.importer.loader import (  # noqa: E402
    COLLECTION_NAME,
    classify_internal,
    get_milvus_client,
)

BACKUP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "deploy", "backups",
)


def main() -> int:
    client = get_milvus_client()
    if not client.has_collection(COLLECTION_NAME):
        print(f"[fatal] collection 不存在: {COLLECTION_NAME}")
        return 1

    # 只扫 _default 分区（kickoff：存量 internal 均在 _default）
    it = client.query_iterator(
        collection_name=COLLECTION_NAME,
        filter="",
        partition_names=["_default"],
        output_fields=["id", "chunk_id", "source_file", "content_type", "content",
                       "raw_content", "tenant_id", "visibility", "created_at"],
        batch_size=500,
    )
    rows = []
    while True:
        b = it.next()
        if not b:
            break
        rows.extend(b)
    it.close()

    total = len(rows)
    internal_rows = []
    scalar_snapshot = []
    for r in rows:
        sf = str(r.get("source_file") or "")
        body = r.get("raw_content") or r.get("content") or ""   # 与 loader 导入期口径一致
        flag = bool(classify_internal(sf, str(body)))
        scalar_snapshot.append({
            "id": r.get("id"),
            "chunk_id": r.get("chunk_id"),
            "source_file": sf,
            "content_type": str(r.get("content_type") or ""),
            "tenant_id": str(r.get("tenant_id") or ""),
            "visibility": str(r.get("visibility") or ""),
            "created_at": str(r.get("created_at") or ""),
            "content_head": str(body)[:200],
            "internal_pred": flag,
        })
        if flag:
            internal_rows.append({
                "id": r.get("id"),
                "chunk_id": r.get("chunk_id"),
                "source_file": sf,
                "content_type": str(r.get("content_type") or ""),
            })

    # 幂等保护：如果某行已经有 internal=true（重复跑/部分执行），不计入待回填清单
    pending = [r for r in internal_rows if not _has_internal(client, r["id"])]
    already = len(internal_rows) - len(pending)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(BACKUP_DIR, exist_ok=True)

    list_path = os.path.join(BACKUP_DIR, f"wnext11_internal_ids_{ts}.json")
    payload = {
        "meta": {
            "task": "WNEXT11 任务一 存量 internal 回填清单（id 清单）",
            "generated_at": datetime.now().astimezone().isoformat(),
            "collection": COLLECTION_NAME,
            "partition": "_default",
            "classify_rule": "loader.classify_internal(source_file, raw_content or content)",
            "total_scanned": total,
            "internal_pred_count": len(internal_rows),
            "already_tagged": already,
            "pending_backfill": len(pending),
        },
        "rows": pending,
    }
    with open(list_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    snap_path = os.path.join(BACKUP_DIR, f"wnext11_edu_knowledge_default_scalar_{ts}.json")
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "task": "WNEXT11 _default 全量标量字段快照（不含向量，数据安全备份）",
                "generated_at": datetime.now().astimezone().isoformat(),
                "collection": COLLECTION_NAME,
                "partition": "_default",
                "rows": total,
            },
            "rows": scalar_snapshot,
        }, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print("[scan] _default 存量只读核查（零 Milvus 写入）")
    print(f"  total_scanned        = {total}")
    print(f"  internal_pred_count  = {len(internal_rows)}  ({len(internal_rows)/total:.1%})")
    print(f"  already_tagged       = {already}")
    print(f"  pending_backfill     = {len(pending)}")
    print(f"  id 清单 → {list_path}")
    print(f"  标量快照 → {snap_path}")
    print("=" * 60)
    return 0


def _has_internal(client, pk) -> bool:
    """查询该行是否已带 internal=true（动态字段存在性探测）。"""
    try:
        res = client.query(
            COLLECTION_NAME,
            filter=f"id == {int(pk)}",
            partition_names=["_default"],
            output_fields=["internal"],
        )
        for r in res:
            v = r.get("internal")
            if isinstance(v, bool) and v:
                return True
            if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes"):
                return True
        return False
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
