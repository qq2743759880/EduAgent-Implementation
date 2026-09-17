"""W-NEXT-MINIO-002 存量审计：跨 knowledge_import_task 查复用 object_key + 同名覆盖。

W-NEXT-MINIO-001 修复了「未来不再发生」：upload.py 现在为每次上传派生
``{content_hash8}_{rand6}_{safe_name}`` 三段格式 → 同名同内容、同名不同内容都
不会互相覆盖。但「存量历史」——修复前所有已写入的 source_files[].object_key
仍是旧格式（``safe_name`` 直接拼）——已经有「多条 task 行复用同一 key」的事实在
MySQL 留痕。本脚本只读，不动任何数据，输出可机验 JSON 给 ㉒ 守卫消费。

输出契约（末尾 [WM2] 一行单行 JSON）：
  - duplicate_object_keys: List[{object_key, reuse_count, task_ids, safe_name,
    file_sizes, has_size_drift}]：object_key 横跨多条 task 的明细
  - cross_task_reused_key_count：被复用的 object_key 数
  - max_reuse_count：单 key 最大复用次数
  - affected_task_rows：所有被复用的 key 涉及 task 行总数（去重前）
  - total_tasks_scanned / total_object_keys：扫描总数
  - same_task_safe_name_collisions：单条 task 内 file_name 重复条目（罕见，正常应 0）
  - affected_task_ids：去重后的 task_id 清单
  - status：PASS（被复用 key ≤ warn_reuse_threshold 且无 size drift）或 WARN

退出码：0=PASS；1=WARN（历史已覆盖风险，但无 size drift）；2=FAIL（DB/IO 不可达）。

Mimosa 安全约束：
  ① host 仅读 settings.MINIO_ENDPOINT / MYSQL_HOST（来自 .env，不接受入参）
  ② SQL 全走 %s 参数绑定（fetch_all 内部）
  ③ 密钥仅从环境变量读（settings.MINIO_*_KEY 默认值仅 DEBUG 模式走，
     生产由 .env 注入——与 W-NEXT-MINIO-001 同口径）

用法：
  PYTHONPATH=. .venv/Scripts/python.exe scripts/eval/wnextminio2_audit_history.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# 允许直接 python scripts/eval/wnextminio2_audit_history.py 跑（PYTHONPATH=. 兜底）
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app.config import settings  # noqa: E402
from app.database import fetch_all, init_mysql  # noqa: E402


# 阈值：复用 key 数 ≥ 此值 → WARN（历史已覆盖风险；非阻断，仅提醒）
WARN_REUSE_THRESHOLD = 1  # 修复前路径下任何复用都视作历史告警
# 阈值：跨多 task 的 key 出现 size drift（被覆盖前 size ≠ 最新 size）→ 强告警
WARN_SIZE_DRIFT_THRESHOLD = 1


def _classify_reuse_severity(
    reuse_count: int,
    has_size_drift: bool,
) -> str:
    """返回 'pass' / 'warn_size_drift' / 'warn_reuse' 三档。

    pass：无 size drift 且 reuse_count ≤ WARN_REUSE_THRESHOLD
    warn_size_drift：file_size 在不同 task 上不一致（被覆盖痕迹）
    warn_reuse：跨多 task 复用（即使 size 一致也意味着同时刻指向同一 MinIO key）
    """
    if has_size_drift:
        return "warn_size_drift"
    if reuse_count > WARN_REUSE_THRESHOLD:
        return "warn_reuse"
    return "pass"


async def _scan_history() -> dict[str, Any]:
    """扫描 knowledge_import_task.source_files，统计 object_key 复用。"""
    await init_mysql()
    rows = await fetch_all(
        "SELECT task_id, source_files, created_at FROM knowledge_import_task "
        "WHERE source_files IS NOT NULL AND source_files != '' "
        "ORDER BY created_at"
    )

    # key -> [occurrence] 每个 occurrence 是 (task_id, file_name, file_size, created_at, raw_item)
    occurrences_by_key: dict[str, list[dict]] = defaultdict(list)
    # 顺手统计 task 内 safe_name 重复条目（同一 task 多次出现同一 file_name）
    same_task_safe_name_dups: list[dict] = []
    # task -> [object_key]
    keys_by_task: dict[str, list[str]] = defaultdict(list)

    for r in rows:
        tid = r["task_id"]
        sfm_raw = r.get("source_files") or ""
        if not sfm_raw:
            continue
        try:
            sfm = json.loads(sfm_raw) if isinstance(sfm_raw, str) else sfm_raw
        except Exception:
            continue
        if not isinstance(sfm, list):
            continue

        # 同一 task 内 file_name 聚合（按 file_name 计重）
        names_in_task: dict[str, int] = Counter()
        for item in sfm:
            if not isinstance(item, dict):
                continue
            k = item.get("object_key")
            if not k:
                continue
            occ = {
                "task_id": tid,
                "file_name": item.get("file_name") or item.get("original_name") or "",
                "file_size": item.get("file_size"),
                "created_at": r.get("created_at"),
                "object_key": k,
            }
            occurrences_by_key[k].append(occ)
            keys_by_task[tid].append(k)
            names_in_task[occ["file_name"]] += 1
        for fname, c in names_in_task.items():
            if c > 1:
                same_task_safe_name_dups.append(
                    {"task_id": tid, "file_name": fname, "count_in_task": c}
                )

    total_keys = sum(len(v) for v in occurrences_by_key.values())
    cross_task_dups: dict[str, list[dict]] = {
        k: v for k, v in occurrences_by_key.items() if len(v) > 1
    }

    duplicate_entries: list[dict] = []
    affected_task_ids: set[str] = set()
    affected_task_rows = 0
    for key, occ_list in sorted(cross_task_dups.items(), key=lambda x: -len(x[1])):
        reuse_count = len(occ_list)
        sizes = [o["file_size"] for o in occ_list if o["file_size"] is not None]
        size_set = sorted(set(sizes))
        has_size_drift = len(size_set) > 1
        severity = _classify_reuse_severity(reuse_count, has_size_drift)
        task_ids = [o["task_id"] for o in occ_list]
        file_names = sorted({o["file_name"] for o in occ_list})
        affected_task_ids.update(task_ids)
        affected_task_rows += reuse_count
        duplicate_entries.append(
            {
                "object_key": key,
                "reuse_count": reuse_count,
                "task_ids": task_ids,
                "safe_name": file_names[0] if len(file_names) == 1 else file_names,
                "file_size_set": size_set,
                "has_size_drift": has_size_drift,
                "severity": severity,
            }
        )

    cross_task_count = len(cross_task_dups)
    max_reuse = max((len(v) for v in cross_task_dups.values()), default=0)

    # 汇总 severity 统计
    severity_counts = Counter(e["severity"] for e in duplicate_entries)
    has_size_drift_total = sum(1 for e in duplicate_entries if e["has_size_drift"])

    return {
        "total_tasks_scanned": len(rows),
        "total_object_keys": total_keys,
        "cross_task_reused_key_count": cross_task_count,
        "max_reuse_count": max_reuse,
        "affected_task_rows": affected_task_rows,
        "affected_task_id_count": len(affected_task_ids),
        "affected_task_ids_sample": sorted(affected_task_ids)[:20],
        "has_size_drift_count": has_size_drift_total,
        "severity_counts": dict(severity_counts),
        "same_task_safe_name_collisions": len(same_task_safe_name_dups),
        "same_task_safe_name_examples": same_task_safe_name_dups[:5],
        "duplicate_object_keys": duplicate_entries,
        "thresholds": {
            "warn_reuse_threshold": WARN_REUSE_THRESHOLD,
            "warn_size_drift_threshold": WARN_SIZE_DRIFT_THRESHOLD,
        },
        "minio_endpoint": settings.MINIO_ENDPOINT,
        "mysql_host": settings.MYSQL_HOST,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _evaluate(report: dict[str, Any]) -> dict[str, Any]:
    """将扫描结果归一为 PASS / WARN 标记。"""
    has_drift = report["has_size_drift_count"] >= WARN_SIZE_DRIFT_THRESHOLD
    cross = report["cross_task_reused_key_count"]

    if has_drift:
        status = "WARN"
        reason = (
            f"发现 {report['has_size_drift_count']} 个 object_key 跨多 task 时 "
            f"file_size 不一致（被覆盖痕迹；无法恢复历史字节内容）"
        )
    elif cross > 0:
        status = "WARN"
        reason = (
            f"发现 {cross} 个 object_key 跨多 task 复用（最大复用 {report['max_reuse_count']} 次）"
            f"——W-NEXT-MINIO-001 仅防止未来覆盖，已发生历史无法回填"
        )
    else:
        status = "PASS"
        reason = "未发现复用 object_key"

    return {
        "status": status,
        "reason": reason,
        "summary": {
            "duplicate_keys": cross,
            "max_reuse_count": report["max_reuse_count"],
            "affected_task_rows": report["affected_task_rows"],
            "has_size_drift_count": report["has_size_drift_count"],
        },
    }


async def _async_main() -> int:
    try:
        report = await _scan_history()
    except Exception as exc:
        # DB 不可达 / 配置缺失等：FAIL 语义
        out = {
            "status": "FAIL",
            "reason": f"audit 探针执行失败: {type(exc).__name__}: {exc}",
            "error": str(exc),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }
        print("[WM2] " + json.dumps(out, ensure_ascii=False))
        return 2

    verdict = _evaluate(report)
    out = {**report, **verdict}
    print("[WM2] " + json.dumps(out, ensure_ascii=False))

    if verdict["status"] == "PASS":
        return 0
    if verdict["status"] == "WARN":
        return 1
    return 2


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    sys.exit(main())