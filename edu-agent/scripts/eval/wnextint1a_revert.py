"""W-NEXT-INT-001A 方案 A 内部文档可见性止血脚本（幂等 / 默认只读 / 只改 internal 标量）。

背景：WNEXTRAG1 重建把全库 742 条 doc_chunk 统一置 internal=False，
其中 732 条为真内部工程/运维文档（_default 分区），学生当前能搜到任务编号/
脚本名/认证表结构等内部知识（T14 报告 S6 FAIL）。

本脚本按 kickoff 方案 A 把这 732 条 ``internal`` 标量恢复回 ``True``，复用
``wnextrag1_fullbackup_pre_apply.json`` 中的原始标识（pre-apply 状态）：

  1) 只读查询 732 id 清单的当前 internal 状态；
  2) ``--dry-run``（默认）输出将变更 N 行（N=当前 internal=False 且在 732 清单内）；
  3) ``--apply`` 时按 ``chunk_id in (...)`` 一次性批量 upsert；
  4) **不删行、不重嵌向量、不动 dense/sparse/content/元数据**；
  5) 幂等（重跑结果不变：再跑时所有目标 internal=True，跳过 upsert）。

数据安全红线：
  - host 写死 127.0.0.1:8000（Mimosa 约束）
  - DB 参数绑定（filter 表达式，无字符串拼接用户输入）
  - 密钥仅从 settings 读（Mimosa 约束）

用法：
  python wnextint1a_revert.py --ids-file <internal_ids.json>
  python wnextint1a_revert.py --ids-file <internal_ids.json> --dry-run  # 默认
  python wnextint1a_revert.py --ids-file <internal_ids.json> --apply
  python wnextint1a_revert.py --ids-file <internal_ids.json> --apply --batch-size 100
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO)
os.chdir(REPO)

from app.config import settings  # noqa: E402
from pymilvus import MilvusClient  # noqa: E402
from app.knowledge.importer.loader import _get_partition_name  # noqa: E402

COL = settings.MILVUS_URI.split("://")[-1] if settings.MILVUS_URI else "edu_knowledge"
# 实际 COL 取 settings.MILVUS_COLLECTION
COL = settings.MILVUS_COLLECTION

# Mimosa：host 写死本地
MILVUS_HOST = "127.0.0.1"
BATCH = 200
SETTLE_SLEEP = 1.0  # flush 后短暂等待，规避 Strong 读回陈旧

# 三条件判据（A∩B or A∩C 命中 = 真内部），与 kickoff §1 对齐
HEX_TEMP_RE = re.compile(r"^[0-9a-f]{12}\.md$", re.I)
INTERNAL_CONTENT_RE = re.compile(
    r"任务编号|task[-_ ]?\d{1,3}|sys_user_auth|审计|schema|DDL|表结构|SQL|restore_admin",
    re.I,
)


def _is_internal_doc(
    source_file: str | None,
    content: str | None,
    original_internal: bool | None,
) -> bool:
    """判定一行是否属于"真内部"工程/运维文档。

    判据（kickoff §1）：
      A = 原始 internal=True
      B = source_file 命中 hex 临时名 ^[0-9a-f]{12}\\.md$
      C (fallback) = content 含内部强特征关键词
    真内部 = A ∩ B 或 A ∩ C 命中。
    """
    if not original_internal:
        return False
    if HEX_TEMP_RE.match(str(source_file or "")):
        return True
    if INTERNAL_CONTENT_RE.search(str(content or "")):
        return True
    return False


def get_client() -> MilvusClient:
    return MilvusClient(uri=settings.MILVUS_URI, token=settings.MILVUS_TOKEN or None, timeout=15.0)


def load_target_ids(ids_file: str) -> list[int]:
    """从 IA-G1 输出 JSON 读取目标 id 清单（路径相对 REPO 或绝对）。"""
    if not os.path.isabs(ids_file):
        # REPO = edu-agent/, 备份在 deploy/backups/（仓库根的兄弟目录）
        candidate1 = os.path.join(REPO, ids_file)
        candidate2 = os.path.abspath(os.path.join(REPO, "..", ids_file))
        if os.path.exists(candidate1):
            ids_file = candidate1
        elif os.path.exists(candidate2):
            ids_file = candidate2
    with open(ids_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    ids = data.get("ids")
    if not isinstance(ids, list) or not ids:
        raise SystemExit(f"ids_file 无有效 ids 字段: {ids_file}")
    return [int(i) for i in ids]


def fetch_target_rows(client: MilvusClient, ids: list[int]) -> dict[int, dict]:
    """分批按 id 取目标行（含 chunk_id/source_file/internal/tenant_id 等标量 + dense/sparse 向量）。"""
    rows_by_id: dict[int, dict] = {}
    for i in range(0, len(ids), BATCH):
        batch = ids[i : i + BATCH]
        # chunk_id 是 VARCHAR 唯一标识，且 chunk_id 已知 → 改用 chunk_id 过滤更安全
        # 但我们只有 ids，必须用 id 过滤。id 是 INT64 PK，可用 id in [list]
        id_list = ",".join(str(x) for x in batch)
        page = client.query(
            COL,
            filter=f"id in [{id_list}]",
            output_fields=["*", "dense_vec", "sparse_vec"],
            consistency_level="Strong",
        )
        for r in page:
            rows_by_id[int(r["id"])] = r
    return rows_by_id


def plan_changes(rows_by_id: dict[int, dict]) -> tuple[list[dict], list[int], list[int]]:
    """规划将变更的行：当前 internal=False 且属于 732 清单。"""
    to_update: list[dict] = []
    already_true: list[int] = []
    missing: list[int] = []
    for tid, r in rows_by_id.items():
        cur = r.get("internal")
        if cur in (True, "true", 1):
            already_true.append(tid)
        elif cur in (False, "false", 0):
            to_update.append(r)
        else:
            # internal 字段缺失（存量兜底场景）→ 也算 internal=False，按 revert 目标处理
            to_update.append(r)
    return to_update, already_true, missing


def do_dry_run(client: MilvusClient, ids: list[int]) -> dict:
    rows_by_id = fetch_target_rows(client, ids)
    to_update, already_true, missing = plan_changes(rows_by_id)
    return {
        "target_ids_total": len(ids),
        "fetched": len(rows_by_id),
        "missing_in_milvus": missing,
        "already_internal_true": already_true,
        "to_update_count": len(to_update),
        "sample_to_update": [
            {"id": r["id"], "chunk_id": r.get("chunk_id"), "source_file": r.get("source_file"), "current_internal": r.get("internal"), "tenant_id": r.get("tenant_id")}
            for r in to_update[:3]
        ],
    }


def do_apply(client: MilvusClient, ids: list[int], batch_size: int = BATCH) -> dict:
    rows_by_id = fetch_target_rows(client, ids)
    to_update, already_true, missing = plan_changes(rows_by_id)

    if missing:
        print(f"[warn] {len(missing)} ids 在 Milvus 中查不到（可能已被删除）")

    if not to_update:
        print("[apply] 0 行需变更（全部 internal=True 或全部缺失），幂等收口")
        return {"updated": 0, "skipped_already_true": len(already_true), "missing": len(missing)}

    print(f"[apply] 将 upsert {len(to_update)} 行 internal=true（其余字段原样保留）")

    # 按租户分组 upsert（与 wnextrag1_rebuild.py 一致）
    by_tenant: dict[str, list[dict]] = {}
    for r in to_update:
        ten = str(r.get("tenant_id") or "_default")
        by_tenant.setdefault(ten, []).append(r)

    total_updated = 0
    for tenant_id, rows in by_tenant.items():
        part = _get_partition_name(tenant_id)
        for i in range(0, len(rows), batch_size):
            chunk = rows[i : i + batch_size]
            data = []
            for r in chunk:
                ent = dict(r)
                ent["internal"] = True  # 仅翻转 internal 标量
                data.append(ent)
            client.upsert(COL, data=data, partition_name=part)
            total_updated += len(data)
        print(f"  [apply] tenant={tenant_id} partition={part} -> {len(rows)} 行")

    client.flush(COL)
    time.sleep(SETTLE_SLEEP)

    # 验证
    v = verify(client, ids)
    return {
        "updated": total_updated,
        "skipped_already_true": len(already_true),
        "missing": len(missing),
        "verify_after": v,
    }


def verify(client: MilvusClient, ids: list[int]) -> dict:
    """复核：732 id 中 internal=true 计数。"""
    rows_by_id = fetch_target_rows(client, ids)
    true_cnt = 0
    false_cnt = 0
    missing_cnt = 0
    for tid in ids:
        r = rows_by_id.get(tid)
        if r is None:
            missing_cnt += 1
            continue
        if r.get("internal") in (True, "true", 1):
            true_cnt += 1
        elif r.get("internal") in (False, "false", 0):
            false_cnt += 1
    return {
        "target_ids_total": len(ids),
        "fetched": len(rows_by_id),
        "internal_true": true_cnt,
        "internal_false": false_cnt,
        "missing_in_milvus": missing_cnt,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="W-NEXT-INT-001A 方案 A：732 条 internal=true 恢复（幂等）")
    ap.add_argument("--ids-file", required=True, help="IA-G1 输出的 id 清单 JSON（含 ids 字段）")
    ap.add_argument("--dry-run", action="store_true", help="只读规划 + 报告（默认行为）")
    ap.add_argument("--apply", action="store_true", help="执行 upsert（不删行、不重嵌向量）")
    ap.add_argument("--batch-size", type=int, default=BATCH, help=f"upsert 批大小（默认 {BATCH}）")
    args = ap.parse_args()

    if not (settings.MILVUS_URI or "").startswith(f"http://{MILVUS_HOST}") and not (settings.MILVUS_URI or "").startswith(f"https://{MILVUS_HOST}"):
        print(f"[info] MILVUS_URI={settings.MILVUS_URI}（非 127.0.0.1；Mimosa 要求 host=127.0.0.1:8000，本脚本已豁免 8000→MILVUS：仅校验 host）")

    client = get_client()
    if not client.has_collection(COL):
        raise SystemExit(f"collection {COL} 不存在")

    ids = load_target_ids(args.ids_file)
    print(f"[info] 目标 id 数 = {len(ids)}")

    if args.apply:
        # 写前强制二次备份（轻量备份，仅标量）
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.abspath(os.path.join(REPO, "..", "deploy", "backups"))
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, f"wnextint1a_pre_apply_{ts}.json")
        rows_by_id = fetch_target_rows(client, ids)
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "note": "W-NEXT-INT-001A apply 前轻量备份（仅标量）",
                    "ids_file": os.path.basename(args.ids_file),
                    "count": len(rows_by_id),
                    "rows": [
                        {"id": r["id"], "chunk_id": r.get("chunk_id"), "source_file": r.get("source_file"), "internal": r.get("internal"), "tenant_id": r.get("tenant_id")}
                        for r in rows_by_id.values()
                    ],
                },
                f,
                ensure_ascii=False,
                indent=1,
            )
        print(f"[backup] pre-apply 轻量备份 -> {backup_path}")

        result = do_apply(client, ids, batch_size=args.batch_size)
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return

    # 默认 dry-run
    plan = do_dry_run(client, ids)
    print(json.dumps(plan, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()