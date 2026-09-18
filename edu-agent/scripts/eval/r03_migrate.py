# -*- coding: utf-8 -*-
"""
R03 chunk_id 唯一化 · Milvus 存量一次性锁定窗口迁移（契约 contracts/reshape-r-chunk.json）

新 chunk_id 格式: {tenant}:{sha256(canonical_content)[:16]}:{seq}
  canonical_content = contextualize 之前原文 = raw_content（有值）否则 content；与
                      app.knowledge.importer.loader.canonical_content_of 同规则（.strip()）
  seq               = 同 (tenant, hash16) 全局序号（1-based），迁移保留全部存量行不折叠

迁移铁律（契约 migration.forbidden）:
  向量原地 —— 不重新 parse/chunk、不重嵌；dense_vec/sparse_vec 从旧行原样透传。
  只改：INT64 主键 id（crc32(new_chunk_id)，与 loader.load_chunks 同算法）+ chunk_id；
  增补：created_at 走 dynamic field（存量行原本无该字段，盖锁定窗口起点 UTC 戳）。

模式:
  dry-run   只读全量 → 算新 ID → id_map 落盘 → 影响清单；**零 Milvus 写入**
  execute   锁定窗口公告 → 两阶段（先全量 delete 旧 PK，再分批 upsert 新行，
            彻底规避新旧 PK 交叉覆盖）→ id_map(含窗口时间戳) 落盘 → 反查一致性
  rollback  按 id_map 反向回放（契约 migration.rollback）：新 PK 全删 → 旧行旧 PK 写回

用法（cwd=edu-agent）:
  .venv/Scripts/python.exe scripts/eval/r03_migrate.py --mode dry-run
  .venv/Scripts/python.exe scripts/eval/r03_migrate.py --mode execute --confirm
  .venv/Scripts/python.exe scripts/eval/r03_migrate.py --mode rollback --confirm
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import zlib
from datetime import datetime, timezone

# 注入 edu-agent/ 到 sys.path（与 _r03_probe.py 同构）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pymilvus import MilvusClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.knowledge.importer.loader import COLLECTION_NAME, _get_partition_name, canonical_id  # noqa: E402
try:
    from _safeio import safe_w  # 直接运行（脚本目录在 sys.path）
except ImportError:  # 以包形式导入
    from scripts.eval._safeio import safe_w  # noqa: E402  Mimosa 路径穿越防护

EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
ID_MAP_PATH = os.path.join(EVAL_DIR, "data", "r03_id_map.json")
LOCK_PATH = os.path.join(EVAL_DIR, "r03.lock")
BATCH_SIZE = 200              # 与 loader.load_chunks 入库批大小一致
QUERY_LIMIT = 16384           # Milvus query 单次上限；存量 4417 < 上限，超出则拒绝执行防漏行
VERIFY_RETRIES = 6            # 写后可见性重试次数
VERIFY_SLEEP_S = 5.0


# ============================================================
# 计划生成（dry-run / execute 共用，确定性：同数据 → 同计划）
# ============================================================
def _canonical_of_row(row: dict) -> str:
    """行字典版 canonical_content，规则与 loader.canonical_content_of 逐字一致。

    存量行均无 raw_content（探查实证 0/4417）→ 实际取 content.strip()；
    保留 raw_content 优先分支以兼容未来带 contextualize 前缀的行。
    """
    raw = row.get("raw_content")
    return (str(raw) if raw else str(row.get("content") or "")).strip()


def _doc_sha256(row: dict) -> str:
    """golden 双键之 doc_sha256=sha256(content 原样 utf-8)（r20min build 同口径，不 strip）。"""
    return hashlib.sha256(str(row.get("content") or "").encode("utf-8")).hexdigest()


def read_all_rows(client: MilvusClient) -> list[dict]:
    """全量读行（含向量与全部动态字段）。行数超 QUERY_LIMIT 直接拒绝（防静默漏迁）。"""
    rows = client.query(
        COLLECTION_NAME,
        filter="id >= 0",            # INT64 PK 全量；参数化过滤器，无拼接
        output_fields=["*"],
        limit=QUERY_LIMIT,
    )
    count_rep = client.query(COLLECTION_NAME, filter="id >= 0", output_fields=["count(*)"])
    total = int(count_rep[0]["count(*)"])
    if len(rows) != total:
        raise RuntimeError(f"全量读取不完整: query={len(rows)} count(*)={total}，停止迁移")
    if total >= QUERY_LIMIT:
        raise RuntimeError(f"行数 {total} >= query 上限 {QUERY_LIMIT}，须改分页后再迁移")
    return rows


def build_plan(rows: list[dict]) -> list[dict]:
    """生成 old→new 迁移计划。

    seq 规则：按 (tenant, hash16) 分组，组内按 (source_file, old_chunk_id, old_pk)
    字典序排序后编 1..N —— 全局唯一且确定性，存量 4417 行全部保留不折叠。
    """
    groups: dict[str, list[dict]] = {}
    for row in rows:
        tenant = str(row.get("tenant_id") or "_default")
        canonical = _canonical_of_row(row)
        h16 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        groups.setdefault(f"{tenant}:{h16}", []).append(row)

    plan: list[dict] = []
    for key, grp in groups.items():
        tenant, h16 = key.rsplit(":", 1)
        ordered = sorted(
            grp,
            key=lambda r: (str(r.get("source_file") or ""), str(r.get("chunk_id") or ""), int(r["id"])),
        )
        for seq, row in enumerate(ordered, start=1):
            old_id = str(row["chunk_id"])
            new_id = canonical_id(tenant, _canonical_of_row(row), seq)  # 复用 loader 唯一生成函数
            assert new_id == f"{tenant}:{h16}:{seq}", (new_id, key, seq)
            plan.append({
                "old_chunk_id": old_id,
                "new_chunk_id": new_id,
                "old_pk": int(row["id"]),
                "new_pk": zlib.crc32(new_id.encode("utf-8")),   # 与 loader.load_chunks 同 PK 算法
                "tenant": tenant,
                "source_file": str(row.get("source_file") or ""),
                "content_type": str(row.get("content_type") or ""),
                "doc_sha256": _doc_sha256(row),
                "had_created_at": "created_at" in row,
            })
    # 确定性输出：按旧 PK 排序落盘，diff 友好
    plan.sort(key=lambda m: m["old_pk"])
    return plan


def plan_fingerprint(plan: list[dict]) -> list[list]:
    """映射指纹：execute 前与 dry-run 落盘计划逐项比对，防读侧漂移。"""
    return [[m["old_chunk_id"], m["new_chunk_id"], m["old_pk"], m["new_pk"]] for m in plan]


def write_id_map(plan: list[dict], mode: str, window_start: str | None, window_end: str | None) -> None:
    tenants: dict[str, int] = {}
    seq_gt1 = 0
    for m in plan:
        tenants[m["tenant"]] = tenants.get(m["tenant"], 0) + 1
        if m["new_chunk_id"].rsplit(":", 1)[-1] != "1":
            seq_gt1 += 1
    payload = {
        "meta": {
            "contract": "contracts/reshape-r-chunk.json",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "collection": COLLECTION_NAME,
            "milvus_uri": settings.MILVUS_URI,
            "id_format": "{tenant}:{sha256(canonical_content)[:16]}:{seq}",
            "canonical_rule": "(raw_content if present else content).strip() —— 同 loader.canonical_content_of",
            "seq_rule": "global per (tenant, sha16); order by (source_file, old_chunk_id, old_pk)",
            "pk_rule": "zlib.crc32(new_chunk_id) —— 同 loader.load_chunks",
            "total": len(plan),
            "tenant_dist": tenants,
            "rows_seq_gt_1": seq_gt1,
            "lock_window_start": window_start,
            "lock_window_end": window_end,
            "rollback": "scripts/eval/r03_migrate.py --mode rollback --confirm（按本映射反向回放）",
        },
        "rows": plan,
    }
    # M-2 收口: 51K 行 id_map（1.87MB 大文件教训的反面落地）真身入 GridFS 制品库,
    # 本地留同字节工作副本（r03b_verify 等下游读者依赖该路径）; mongo 不可达自动降级
    # test-reports/artifacts_local/, 归档层自身失败回退直接落盘——均不阻断迁移主流程。
    try:
        from app.common.artifact_store import save_artifact
        _arch = save_artifact("eval/r03/id_map.json", payload,
                              metadata={"kind": "r03_id_map", "rows": len(plan)},
                              local_copy=safe_w(ID_MAP_PATH))
        print(f"[artifact] backend={_arch['backend']} aid={_arch['aid']} "
              f"sha256={_arch['sha256'][:16]} size={_arch['size']}")
    except Exception as _e:  # noqa: BLE001
        print(f"[artifact] 归档失败(忽略, 回退直接落盘): {type(_e).__name__}: {_e}")
        with open(safe_w(ID_MAP_PATH), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


def impact_summary(rows: list[dict], plan: list[dict]) -> dict:
    """影响清单：旧/新唯一性、租户分布、seq>1 计数、新旧 PK 交集（两阶段安全裕度）。"""
    old_ids = [str(r["chunk_id"]) for r in rows]
    new_ids = [m["new_chunk_id"] for m in plan]
    old_pks = set(int(r["id"]) for r in rows)
    new_pks = set(m["new_pk"] for m in plan)
    tenants: dict[str, int] = {}
    ctypes: dict[str, int] = {}
    for r in rows:
        t = str(r.get("tenant_id") or "_default")
        tenants[t] = tenants.get(t, 0) + 1
        ct = str(r.get("content_type") or "")
        ctypes[ct] = ctypes.get(ct, 0) + 1
    return {
        "rows": len(rows),
        "old_chunk_id_unique": len(set(old_ids)),
        "new_chunk_id_unique": len(set(new_ids)),
        "old_pk_unique": len(old_pks),
        "new_pk_unique": len(new_pks),
        "new_pk_collisions": len(new_ids) - len(set(new_ids)),
        "old_new_pk_overlap": len(old_pks & new_pks),
        "unchanged_ids": len(set(old_ids) & set(new_ids)),
        "tenant_dist": tenants,
        "content_type_dist": ctypes,
    }


# ============================================================
# dry-run
# ============================================================
def mode_dry_run(client: MilvusClient) -> int:
    before = int(client.query(COLLECTION_NAME, filter="id >= 0", output_fields=["count(*)"])[0]["count(*)"])
    rows = read_all_rows(client)
    plan = build_plan(rows)
    write_id_map(plan, "dry-run", None, None)
    summary = impact_summary(rows, plan)
    after = int(client.query(COLLECTION_NAME, filter="id >= 0", output_fields=["count(*)"])[0]["count(*)"])
    print("=" * 60)
    print("[dry-run] R03 迁移影响清单（零 Milvus 写入）")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[dry-run] count(*) before={before} after={after} → {'零写入 PASS' if before == after else 'FAIL 行数变化!'}")
    print(f"[dry-run] id_map → {ID_MAP_PATH}")
    print("=" * 60)
    if before != after:
        return 1
    if summary["new_pk_collisions"] != 0 or summary["new_chunk_id_unique"] != len(rows):
        print("[dry-run] FAIL 新 ID/PK 存在冲突，禁止 execute")
        return 1
    return 0


# ============================================================
# execute
# ============================================================
def _banner(title: str, ts: str) -> None:
    print("=" * 60)
    print(f"  {title}")
    print(f"  锁定窗口起(UTC): {ts}")
    print("  窗口内导入任务暂停（编排者已授权）；检索/向量原地，不重嵌")
    print("=" * 60)


def _new_row_from_old(row: dict, mapping: dict, created_at_stamp: str) -> dict:
    """旧行 → 新行：全字段透传（含向量/动态字段），仅换 PK/chunk_id + 补 created_at。"""
    new_row = dict(row)
    new_row["id"] = mapping["new_pk"]
    new_row["chunk_id"] = mapping["new_chunk_id"]
    # created_at：原本有则保留旧值；存量行无 → 盖窗口起点戳（dynamic field 承载）
    if not mapping["had_created_at"]:
        new_row["created_at"] = created_at_stamp
    return new_row


def mode_execute(client: MilvusClient) -> int:
    # 0) 单写者锁存在性检查（锁由开工工程师建立，完工才删）
    if not os.path.exists(LOCK_PATH):
        print(f"[execute] FAIL 单写者锁不存在: {LOCK_PATH}")
        return 1

    # 1) 现读现算，并与 dry-run 落盘计划指纹比对（防 dry-run 后数据已变）
    rows = read_all_rows(client)
    plan = build_plan(rows)
    with open(ID_MAP_PATH, encoding="utf-8") as f:
        prev = json.load(f)
    if prev.get("meta", {}).get("mode") != "dry-run":
        print("[execute] FAIL id_map 非 dry-run 产物，先跑 --mode dry-run")
        return 1
    if plan_fingerprint(plan) != [[m["old_chunk_id"], m["new_chunk_id"], m["old_pk"], m["new_pk"]]
                                  for m in prev["rows"]]:
        print("[execute] FAIL 现算计划与 dry-run id_map 不一致（数据已变），重新 dry-run 后再执行")
        return 1

    summary = impact_summary(rows, plan)
    if summary["new_pk_collisions"] != 0:
        print("[execute] FAIL 新 PK 冲突，中止")
        return 1

    window_start = datetime.now(timezone.utc).isoformat()
    _banner("[execute] R03 迁移锁定窗口开启", window_start)
    t0 = time.perf_counter()
    by_old_pk = {int(r["id"]): r for r in rows}
    old_pks = [m["old_pk"] for m in plan]

    # 2) 阶段 A：分批删除全部旧 PK（pks 结构化传参，无表达式拼接）
    deleted = 0
    for i in range(0, len(old_pks), BATCH_SIZE):
        batch_pks = old_pks[i:i + BATCH_SIZE]
        client.delete(COLLECTION_NAME, pks=batch_pks)
        deleted += len(batch_pks)
        print(f"[execute] phase A delete 批 {i // BATCH_SIZE + 1}: 累计 {deleted}/{len(old_pks)}")

    # 3) 阶段 B：分批 upsert 新行（同向量/同动态字段，换 PK+chunk_id，补 created_at）
    #    先全删后全写 → 杜绝「新 PK == 尚未迁移旧 PK」交叉覆盖（本批实测交集=0，仍取最稳路线）
    upserted = 0
    by_partition: dict[str, list[dict]] = {}
    for m in plan:
        row = by_old_pk[m["old_pk"]]
        part = _get_partition_name(m["tenant"])
        by_partition.setdefault(part, []).append(_new_row_from_old(row, m, window_start))
    for part, part_rows in by_partition.items():
        for i in range(0, len(part_rows), BATCH_SIZE):
            batch = part_rows[i:i + BATCH_SIZE]
            client.upsert(COLLECTION_NAME, data=batch, partition_name=part)
            upserted += len(batch)
            print(f"[execute] phase B upsert 分区={part} 批 {i // BATCH_SIZE + 1}: 累计 {upserted}")

    # 4) 反查一致性（带可见性重试）
    verify = _verify_after(client, plan, rows, deleted, upserted)
    window_end = datetime.now(timezone.utc).isoformat()
    dur = round(time.perf_counter() - t0, 1)
    write_id_map(plan, "execute", window_start, window_end)
    print("=" * 60)
    print(f"[execute] 迁移完成: deleted={deleted} upserted={upserted} 窗口时长={dur}s")
    print(f"[execute] 锁定窗口止(UTC): {window_end}")
    print(json.dumps(verify, ensure_ascii=False, indent=2))
    print(f"[execute] id_map(含窗口时间戳) → {ID_MAP_PATH}")
    print("=" * 60)
    return 0 if verify["consistency"] == "PASS" else 1


def _verify_after(client: MilvusClient, plan: list[dict], old_rows: list[dict],
                  deleted: int, upserted: int) -> dict:
    """写后反查：行数/新旧 ID 集合/PK 集合/向量逐行原地一致性。"""
    expected = len(plan)
    actual_rows: list[dict] = []
    for attempt in range(1, VERIFY_RETRIES + 1):
        cnt = int(client.query(COLLECTION_NAME, filter="id >= 0", output_fields=["count(*)"])[0]["count(*)"])
        if cnt == expected:
            actual_rows = read_all_rows(client)
            break
        print(f"[verify] 第 {attempt} 次 count(*)={cnt} != {expected}，{VERIFY_SLEEP_S}s 后重试…")
        time.sleep(VERIFY_SLEEP_S)
    else:
        return {"consistency": "FAIL", "reason": f"行数不收敛: 期望 {expected}"}

    actual_by_pk = {int(r["id"]): r for r in actual_rows}
    new_pk_set = {m["new_pk"] for m in plan}
    old_pk_set = {m["old_pk"] for m in plan}
    new_id_set = {m["new_chunk_id"] for m in plan}
    old_by_pk = {int(r["id"]): r for r in old_rows}
    plan_by_new_pk = {m["new_pk"]: m for m in plan}

    missing_pks = new_pk_set - set(actual_by_pk)
    lingering_old = old_pk_set & set(actual_by_pk)
    actual_ids = {str(r.get("chunk_id")) for r in actual_rows}
    id_mismatch = actual_ids ^ new_id_set

    # 向量原地：按映射逐行比对 dense（逐分量）/ sparse（逐键值）/ content
    vec_bad: list[str] = []
    content_bad: list[str] = []
    created_at_missing = 0
    for npk, m in plan_by_new_pk.items():
        new_r = actual_by_pk.get(npk)
        old_r = old_by_pk[m["old_pk"]]
        if new_r is None:
            continue
        if new_r.get("dense_vec") != old_r.get("dense_vec"):
            vec_bad.append(m["new_chunk_id"])
        if new_r.get("sparse_vec") != old_r.get("sparse_vec"):
            vec_bad.append(m["new_chunk_id"] + ":sparse")
        if new_r.get("content") != old_r.get("content"):
            content_bad.append(m["new_chunk_id"])
        if not m["had_created_at"] and not new_r.get("created_at"):
            created_at_missing += 1

    ok = (
        deleted == expected and upserted == expected
        and not missing_pks and not lingering_old and not id_mismatch
        and not vec_bad and not content_bad and created_at_missing == 0
    )
    return {
        "consistency": "PASS" if ok else "FAIL",
        "expected_rows": expected,
        "actual_rows": len(actual_rows),
        "deleted": deleted,
        "upserted": upserted,
        "missing_new_pks": len(missing_pks),
        "lingering_old_pks": len(lingering_old),
        "chunk_id_set_xor": len(id_mismatch),
        "vector_mismatches": len(vec_bad),
        "content_mismatches": len(content_bad),
        "created_at_missing": created_at_missing,
        "samples": vec_bad[:5] or content_bad[:5],
    }


# ============================================================
# rollback（契约：id_map 反向回放）
# ============================================================
def mode_rollback(client: MilvusClient) -> int:
    if not os.path.exists(ID_MAP_PATH):
        print("[rollback] FAIL id_map 不存在，无法反向回放")
        return 1
    with open(ID_MAP_PATH, encoding="utf-8") as f:
        payload = json.load(f)
    plan = payload["rows"]
    window_start = datetime.now(timezone.utc).isoformat()
    _banner("[rollback] R03 反向回放窗口开启", window_start)

    # 当前行按 new_pk 取（含已迁移向量/动态字段）
    current = {int(r["id"]): r for r in read_all_rows(client)}
    new_pks = [m["new_pk"] for m in plan]

    restored_rows: dict[str, list[dict]] = {}
    skipped = 0
    for m in plan:
        r = current.get(m["new_pk"])
        if r is None:
            skipped += 1  # 该行不在新集合（异常），跳过并计数
            continue
        old_row = dict(r)
        old_row["id"] = m["old_pk"]
        old_row["chunk_id"] = m["old_chunk_id"]
        # 迁移时补盖的 created_at 撤掉，恢复旧行原始形态（原本就有的保留）
        if not m["had_created_at"]:
            old_row.pop("created_at", None)
        part = _get_partition_name(m["tenant"])
        restored_rows.setdefault(part, []).append(old_row)

    deleted = 0
    for i in range(0, len(new_pks), BATCH_SIZE):
        client.delete(COLLECTION_NAME, pks=new_pks[i:i + BATCH_SIZE])
        deleted += len(new_pks[i:i + BATCH_SIZE])
    written = 0
    for part, rows in restored_rows.items():
        for i in range(0, len(rows), BATCH_SIZE):
            client.upsert(COLLECTION_NAME, data=rows[i:i + BATCH_SIZE], partition_name=part)
            written += len(rows[i:i + BATCH_SIZE])

    for attempt in range(1, VERIFY_RETRIES + 1):
        cnt = int(client.query(COLLECTION_NAME, filter="id >= 0", output_fields=["count(*)"])[0]["count(*)"])
        if cnt == len(plan):
            break
        time.sleep(VERIFY_SLEEP_S)
    after_rows = {int(r["id"]): r for r in read_all_rows(client)}
    old_id_set = {m["old_chunk_id"] for m in plan}
    actual_ids = {str(r.get("chunk_id")) for r in after_rows.values()}
    ok = actual_ids == old_id_set and written == len(plan) and skipped == 0
    print(f"[rollback] deleted={deleted} restored={written} skipped={skipped} count={cnt} "
          f"id_set_match={actual_ids == old_id_set} → {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


# ============================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="R03 chunk_id 唯一化存量迁移（dry-run/execute/rollback）")
    ap.add_argument("--mode", required=True, choices=["dry-run", "execute", "rollback"])
    ap.add_argument("--confirm", action="store_true", help="变更类模式（execute/rollback）必须显式确认")
    args = ap.parse_args()

    if args.mode in ("execute", "rollback") and not args.confirm:
        print(f"[blocked] {args.mode} 为破坏性操作，须加 --confirm 显式确认")
        return 2

    client = MilvusClient(
        uri=settings.MILVUS_URI,
        token=settings.MILVUS_TOKEN or None,
        timeout=30.0,
    )
    if not client.has_collection(COLLECTION_NAME):
        print(f"[fatal] collection 不存在: {COLLECTION_NAME}")
        return 1

    if args.mode == "dry-run":
        return mode_dry_run(client)
    if args.mode == "execute":
        return mode_execute(client)
    return mode_rollback(client)


if __name__ == "__main__":
    raise SystemExit(main())
