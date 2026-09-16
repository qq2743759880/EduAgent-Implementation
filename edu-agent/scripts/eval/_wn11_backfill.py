# -*- coding: utf-8 -*-
"""WNEXT11 任务一 步骤3：幂等回填 internal=true（_default 分区，不重嵌向量）。

铁律（对齐 R03 created_at 补入做法）：
  - Milvus upsert 是**整行替换**——只传 {id, internal} 会清空 dense/sparse/content。
    因此必须「读全行（output_fields=[\"*\"]）→ 就地加 internal=True → 原样 upsert 回 _default」，
    向量/正文零改动、零重嵌。
  - 幂等：同一批可重跑；已有 internal=true 的行覆盖为 true，计数不翻倍。
  - 先备份后写：依赖 _wn11_scan_backup.py 落盘的 id 清单 JSON。

用法（cwd=edu-agent）：
  python scripts/eval/_wn11_backfill.py --list <清单JSON> --confirm
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.knowledge.importer.loader import COLLECTION_NAME, get_milvus_client  # noqa: E402

BATCH_SIZE = 200          # 与 loader.load_chunks 入库批大小一致
VERIFY_RETRIES = 6
VERIFY_SLEEP_S = 5.0
LOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wnext11.lock")
INTERNAL_FIELD = "internal"


def read_rows_by_pks(client, pks: list[int]) -> dict[int, dict]:
    """按主键批量读全行（含向量与动态字段），返回 {pk: row}。"""
    out: dict[int, dict] = {}
    for i in range(0, len(pks), BATCH_SIZE):
        batch = pks[i:i + BATCH_SIZE]
        expr = "id in [" + ",".join(str(int(p)) for p in batch) + "]"
        res = client.query(
            COLLECTION_NAME,
            filter=expr,
            partition_names=["_default"],
            output_fields=["*"],
        )
        for r in res:
            pk = int(r.get("id"))
            out[pk] = r
    return out


def backfill(client, manifest: dict) -> dict:
    rows = manifest["rows"]
    pks = [int(r["id"]) for r in rows]
    by_pk = read_rows_by_pks(client, pks)

    missing = [pk for pk in pks if pk not in by_pk]
    if missing:
        raise RuntimeError(f"清单中 {len(missing)} 行未读到（数据漂移？），中止：前5={missing[:5]}")

    # 读到的行不一定与清单完全同序，统一按清单顺序取
    ordered = [by_pk[pk] for pk in pks]

    upserted = 0
    t0 = time.perf_counter()
    for i in range(0, len(ordered), BATCH_SIZE):
        batch = ordered[i:i + BATCH_SIZE]
        for row in batch:
            row[INTERNAL_FIELD] = True   # 只补 dynamic scalar，其余字段原样透传
        client.upsert(COLLECTION_NAME, data=batch, partition_name="_default")
        upserted += len(batch)
        print(f"[backfill] 批 {i // BATCH_SIZE + 1}: 累计 {upserted}/{len(ordered)}")

    # 写后计数对账（可见性重试）
    expected = len(ordered)
    for attempt in range(1, VERIFY_RETRIES + 1):
        cnt = _count_internal_true(client)
        if cnt == expected:
            break
        print(f"[verify] 第 {attempt} 次 internal==true 计数 {cnt} != {expected}，{VERIFY_SLEEP_S}s 后重试…")
        time.sleep(VERIFY_SLEEP_S)
    else:
        return {"upserted": upserted, "internal_true_after": cnt, "expected": expected,
                "consistency": "FAIL", "elapsed_s": round(time.perf_counter() - t0, 1)}

    total = int(client.query(COLLECTION_NAME, filter="id >= 0",
                             partition_names=["_default"],
                             output_fields=["count(*)"])[0]["count(*)"])
    return {"upserted": upserted, "internal_true_after": cnt, "expected": expected,
            "total_rows_after": total, "consistency": "PASS",
            "elapsed_s": round(time.perf_counter() - t0, 1)}


def _count_internal_true(client) -> int:
    try:
        res = client.query(
            COLLECTION_NAME,
            filter=f"{INTERNAL_FIELD} == true",
            partition_names=["_default"],
            output_fields=["count(*)"],
        )
        return int(res[0]["count(*)"])
    except Exception as exc:
        print(f"[verify] internal==true 计数查询失败: {exc}")
        return -1


def main() -> int:
    ap = argparse.ArgumentParser(description="WNEXT11 存量 internal 幂等回填")
    ap.add_argument("--list", required=True, help="_wn11_scan_backup.py 落盘的 id 清单 JSON")
    ap.add_argument("--confirm", action="store_true", help="写库操作必须显式确认")
    args = ap.parse_args()

    if not args.confirm:
        print("[blocked] 回填为写库操作，须加 --confirm 显式确认")
        return 2
    if not os.path.exists(LOCK_PATH):
        print(f"[execute] FAIL 单写者锁不存在: {LOCK_PATH}")
        return 1

    with open(args.list, encoding="utf-8") as f:
        manifest = json.load(f)
    if manifest.get("meta", {}).get("task", "").find("id 清单") < 0:
        print("[execute] FAIL 输入非 WNEXT11 id 清单 JSON")
        return 1
    pending = len(manifest.get("rows", []))
    if pending == 0:
        print("[execute] 清单为空，无可回填")
        return 0

    client = get_milvus_client()
    if not client.has_collection(COLLECTION_NAME):
        print(f"[fatal] collection 不存在: {COLLECTION_NAME}")
        return 1

    before = _count_internal_true(client)
    print(f"[execute] 回填前 internal==true 计数 = {before}，待回填 = {pending}")
    result = backfill(client, manifest)
    print("=" * 60)
    print("[execute] 回填完成")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("=" * 60)
    return 0 if result.get("consistency") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
