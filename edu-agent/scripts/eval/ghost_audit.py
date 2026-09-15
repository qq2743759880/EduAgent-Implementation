# -*- coding: utf-8 -*-
"""GHOST-pin-rootfix 步骤1：community_post 置顶帖只读核查（禁写）。

只读：SELECT / SHOW / information_schema，绝不写库。
用法: .venv\\Scripts\\python.exe scripts/eval/ghost_audit.py
"""
from __future__ import annotations

import json
import os
import sys

import pymysql

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.config import settings  # noqa: E402


def conn():
    return pymysql.connect(
        host=settings.MYSQL_HOST, port=int(settings.MYSQL_PORT),
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DATABASE, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


PIN_TITLE_LIKE = "%欢迎来到%"


def main() -> int:
    out: dict = {}
    c = conn()
    cur = c.cursor()

    cur.execute("SELECT COUNT(*) c FROM community_post")
    out["rows_total_all"] = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM community_post WHERE yn=1")
    out["rows_yn1"] = cur.fetchone()["c"]
    cur.execute("SELECT SUM(yn=1 AND is_pinned=1) c FROM community_post")
    out["pinned_yn1"] = int(cur.fetchone()["c"] or 0)

    cur.execute(
        "SELECT id, board_code, author_id, author_name, is_pinned, is_locked, yn,"
        " view_count, like_count, comment_count, favorite_count, hot_score,"
        " created_at, updated_at"
        " FROM community_post WHERE title LIKE %s AND is_pinned=1 ORDER BY created_at, id",
        (PIN_TITLE_LIKE,),
    )
    out["pinned_same_title"] = [
        {**r, "created_at": str(r["created_at"]), "updated_at": str(r["updated_at"]),
         "hot_score": float(r["hot_score"] or 0)}
        for r in cur.fetchall()
    ]

    cur.execute(
        "SELECT title, COUNT(*) c, SUM(yn=1) yn1, SUM(is_pinned=1) pins,"
        " GROUP_CONCAT(id ORDER BY id) ids"
        " FROM community_post GROUP BY title HAVING c > 1 ORDER BY c DESC, title",
    )
    out["duplicate_titles_all"] = [
        {**r, "ids": r["ids"], "c": int(r["c"]), "yn1": int(r["yn1"] or 0), "pins": int(r["pins"] or 0)}
        for r in cur.fetchall()
    ]

    cur.execute("SHOW CREATE TABLE community_post")
    row = cur.fetchone()
    out["ddl"] = list(row.values())[1]

    cur.execute("SHOW INDEX FROM community_post")
    out["indexes"] = [
        {"key": r["Key_name"], "col": r["Column_name"], "seq": r["Seq_in_index"],
         "unique": int(r["Non_unique"]) == 0}
        for r in cur.fetchall()
    ]

    cur.execute(
        "SELECT id, is_pinned, hot_score, view_count, created_at FROM community_post"
        " WHERE yn=1 ORDER BY is_pinned DESC, hot_score DESC, created_at DESC LIMIT 30",
    )
    tier = cur.fetchall()
    out["order_ties_sample"] = {
        "n": len(tier),
        "tie_hot0": sum(1 for r in tier if float(r["hot_score"] or 0) == 0.0),
        "ids": [r["id"] for r in tier],
    }

    c.close()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
