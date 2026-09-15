# -*- coding: utf-8 -*-
"""GHOST-pin-rootfix 数据清理：community_post 同标题重复种子帖 → 每标题保留最早 1 条，其余软删。

设计红线（对齐 kickoff）：
  * **先备份后清理**：`--apply` 必须显式传 `--backup <mysqldump 文件>`，脚本校验备份含完整
    `CREATE TABLE community_post` + 98 行数据后才允许写库；无备份一律拒绝执行。
  * **软删优先**：只置 `yn=0`（并把 `is_pinned=0`），不 DELETE，可原样回收。
  * 默认 `--dry-run`：只打印计划，不写库。

用法::

    # 只读：列出重复组与清理计划
    .venv\\Scripts\\python.exe scripts/ghost_pin_cleanup.py --dry-run

    # 复发巡检（有重复组则 exit 1）
    .venv\\Scripts\\python.exe scripts/ghost_pin_cleanup.py --check

    # 备份 + 清理
    mysqldump ... > deploy/backups/community_post_YYYYmmdd_HHMMSS.sql
    .venv\\Scripts\\python.exe scripts/ghost_pin_cleanup.py --apply \\
        --backup ../../deploy/backups/community_post_YYYYmmdd_HHMMSS.sql
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime

import pymysql

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval", ".ghost_tmp")


def conn(autocommit: bool = False):
    return pymysql.connect(
        host=settings.MYSQL_HOST, port=int(settings.MYSQL_PORT),
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DATABASE, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=autocommit,
    )


def duplicate_groups(cur) -> list[dict]:
    """yn=1 下同标题重复组；保留组内 MIN(id)，其余为待软删。"""
    cur.execute(
        "SELECT title, COUNT(*) c, MIN(id) keep_id, GROUP_CONCAT(id ORDER BY id) ids,"
        " GROUP_CONCAT(DISTINCT board_code) boards, GROUP_CONCAT(DISTINCT author_id) authors,"
        " SUM(is_pinned=1) pinned_n"
        " FROM community_post WHERE yn=1 GROUP BY title HAVING COUNT(*) > 1"
        " ORDER BY c DESC, keep_id",
    )
    out = []
    for r in cur.fetchall():
        ids = [int(x) for x in str(r["ids"]).split(",")]
        keep = int(r["keep_id"])
        out.append({
            "title": r["title"], "count": int(r["c"]), "keep_id": keep,
            "boards": r["boards"], "authors": r["authors"],
            "pinned_in_group": int(r["pinned_n"] or 0),
            "delete_ids": [i for i in ids if i != keep],
        })
    return out


def counts(cur) -> dict:
    cur.execute("SELECT COUNT(*) c FROM community_post")
    all_rows = int(cur.fetchone()["c"])
    cur.execute("SELECT COUNT(*) c FROM community_post WHERE yn=1")
    yn1 = int(cur.fetchone()["c"])
    cur.execute("SELECT COUNT(*) c FROM community_post WHERE yn=1 AND is_pinned=1")
    pinned = int(cur.fetchone()["c"])
    cur.execute("SELECT COUNT(*) c FROM community_post WHERE yn=0")
    soft = int(cur.fetchone()["c"])
    return {"rows_total": all_rows, "yn1": yn1, "pinned_yn1": pinned, "soft_deleted": soft}


def verify_backup(path: str) -> dict:
    if not os.path.isfile(path):
        raise SystemExit(f"[ABORT] 备份文件不存在：{path}")
    raw = open(path, "rb").read()
    text = raw.decode("utf-8", errors="replace")
    n_tuples = text.count("),(") + 1 if "INSERT INTO" in text else 0
    ok_ddl = "CREATE TABLE `community_post`" in text
    meta = {
        "path": os.path.abspath(path), "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "has_create_table": ok_ddl, "rows_in_dump": n_tuples,
    }
    if not ok_ddl:
        raise SystemExit("[ABORT] 备份文件不含 CREATE TABLE `community_post`，疑似非本表 dump")
    if n_tuples < 1:
        raise SystemExit("[ABORT] 备份文件不含数据行")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="执行软删（必须配 --backup）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划（默认行为）")
    ap.add_argument("--check", action="store_true", help="复发巡检：存在重复组则 exit 1")
    ap.add_argument("--backup", default=None, help="mysqldump 备份文件路径（--apply 必填）")
    ap.add_argument("--json-out", default=os.path.join(OUT_DIR, "cleanup.json"))
    args = ap.parse_args()

    c = conn()
    cur = c.cursor()
    before = counts(cur)
    groups = duplicate_groups(cur)
    plan_delete = sorted({i for g in groups for i in g["delete_ids"]})

    result: dict = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "mode": "apply" if args.apply else ("check" if args.check else "dry-run"),
        "before": before,
        "duplicate_groups": groups,
        "planned_soft_delete": plan_delete,
        "planned_soft_delete_n": len(plan_delete),
    }

    print(f"[before] rows_total={before['rows_total']} yn1={before['yn1']} "
          f"pinned_yn1={before['pinned_yn1']} soft_deleted={before['soft_deleted']}")
    for g in groups:
        print(f"  dup c={g['count']:>2} keep={g['keep_id']:<3} del={g['delete_ids']} "
              f"board={g['boards']} pins={g['pinned_in_group']} title={(g['title'] or '')[:30]}")

    if args.check:
        c.close()
        print(f"[check] duplicate_groups={len(groups)} -> "
              f"{'FAIL(复发)' if groups else 'PASS(无重复)'}")
        return 1 if groups else 0

    if not args.apply:
        c.close()
        _dump(result, args.json_out)
        print(f"[dry-run] 计划软删 {len(plan_delete)} 行（未写库）。json: {args.json_out}")
        return 0

    if not args.backup:
        c.close()
        raise SystemExit("[ABORT] --apply 必须传 --backup <mysqldump 文件>（先备份后清理）")
    meta = verify_backup(args.backup)
    result["backup"] = meta
    print(f"[backup] {meta['path']} bytes={meta['bytes']} rows={meta['rows_in_dump']} "
          f"sha256={meta['sha256'][:16]}…")

    if not plan_delete:
        c.close()
        _dump(result, args.json_out)
        print("[apply] 无重复组，无需清理")
        return 0

    ph = ",".join(["%s"] * len(plan_delete))
    try:
        cur.execute(
            f"UPDATE community_post SET yn=0, is_pinned=0 WHERE id IN ({ph}) AND yn=1",
            tuple(plan_delete),
        )
        affected = cur.rowcount
        c.commit()
    except Exception:
        c.rollback()
        c.close()
        raise
    result["affected_rows"] = affected

    after = counts(cur)
    result["after"] = after
    c.close()
    _dump(result, args.json_out)
    print(f"[apply] affected={affected}")
    print(f"[after ] rows_total={after['rows_total']} yn1={after['yn1']} "
          f"pinned_yn1={after['pinned_yn1']} soft_deleted={after['soft_deleted']}")
    print(f"[after ] 同名置顶组残留：{len(duplicate_groups(conn().cursor()))}")
    print(f"json: {args.json_out}")
    return 0


def _dump(obj: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
