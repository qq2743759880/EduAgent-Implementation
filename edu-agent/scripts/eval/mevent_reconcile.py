# -*- coding: utf-8 -*-
"""R-M1 对账脚本（只读）——MongoDB learning_event 事件数 vs MySQL 进度表业务数。

验收硬证据（neo4j-mongo-activation-plan §M-3：聚合结果与 MySQL 进度表对账一致率）。

只读纪律：mongo 侧仅 find/aggregate；MySQL 侧仅 SELECT。零写入零索引变更。

对账口径（窗口 [since, until]，默认 since=首条 mongo 事件 ts-5min 防钟差，until=now）：
  video_heartbeat  : mongo Σ payload.rows_inserted（每条 tick-batch 事件）
                     vs MySQL COUNT(session_video_play_event e JOIN session_video_play p
                                   ON e.play_session_id=p.id WHERE p.user_id=? AND e.created_at∈窗口)
  quiz_submit      : mongo COUNT(type=quiz_submit)
                     vs MySQL COUNT(quiz_answer_session WHERE user_id=? AND created_at∈窗口)
  session_complete : mongo COUNT(type=session_complete 且 payload.completed=true)
                     vs MySQL COUNT(session_video_play WHERE user_id=? AND completed_flag=1
                                   AND updated_at∈窗口)   ※ updated_at 为完成态代理列（会被
                     watched_seconds 更新共享 bump，存在高估可能；脚本同时输出两侧原始值）
一致率 = 完全相等的 (user,type) 对账项 / 总对账项。

用法（cwd=edu-agent）：
  .venv/Scripts/python.exe scripts/eval/mevent_reconcile.py            # 全量用户
  ... mevent_reconcile.py --sample 5 --json out.json --hours 48
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # edu-agent/

from app.config import settings  # noqa: E402


def _mysql_conn():
    import pymysql

    return pymysql.connect(
        host=settings.MYSQL_HOST,
        port=int(settings.MYSQL_PORT),
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DATABASE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        read_timeout=15,
        write_timeout=15,
        connect_timeout=10,
    )


def _mongo_coll():
    import pymongo

    client = pymongo.MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return client[settings.MONGO_DB]["learning_event"], client


def reconcile(users: list[int], since: datetime, until: datetime) -> dict:
    coll, client = _mongo_coll()
    conn = _mysql_conn()
    rows_out: list[dict] = []
    try:
        with conn.cursor() as cur:
            for uid in users:
                # ── mongo 侧（只读） ──
                vh_docs = list(coll.find(
                    {"user_id": uid, "type": "video_heartbeat", "ts": {"$gte": since, "$lte": until}},
                    {"payload.rows_inserted": 1},
                ))
                mongo_vh_rows = sum(int(d.get("payload", {}).get("rows_inserted") or 0) for d in vh_docs)
                mongo_vh_events = len(vh_docs)

                mongo_quiz = coll.count_documents(
                    {"user_id": uid, "type": "quiz_submit", "ts": {"$gte": since, "$lte": until}})

                mongo_sc = coll.count_documents(
                    {"user_id": uid, "type": "session_complete", "payload.completed": True,
                     "ts": {"$gte": since, "$lte": until}})

                # ── MySQL 侧（只读 SELECT） ──
                cur.execute(
                    "SELECT COUNT(*) AS n FROM session_video_play_event e "
                    "JOIN session_video_play p ON e.play_session_id = p.id "
                    "WHERE p.user_id=%s AND e.created_at >= %s AND e.created_at <= %s",
                    (uid, since, until),
                )
                mysql_vh_rows = int(cur.fetchone()["n"])

                cur.execute(
                    "SELECT COUNT(*) AS n FROM quiz_answer_session "
                    "WHERE user_id=%s AND created_at >= %s AND created_at <= %s",
                    (uid, since, until),
                )
                mysql_quiz = int(cur.fetchone()["n"])

                cur.execute(
                    "SELECT COUNT(*) AS n FROM session_video_play "
                    "WHERE user_id=%s AND completed_flag=1 AND updated_at >= %s AND updated_at <= %s",
                    (uid, since, until),
                )
                mysql_sc = int(cur.fetchone()["n"])

                rows_out.append({
                    "user_id": uid,
                    "video_heartbeat": {
                        "mongo_events": mongo_vh_events, "mongo_tick_rows": mongo_vh_rows,
                        "mysql_tick_rows": mysql_vh_rows, "match": mongo_vh_rows == mysql_vh_rows,
                        "proxy": "tick-batch 请求事件 payload.rows_inserted 求和 vs MySQL 打点行数",
                    },
                    "quiz_submit": {
                        "mongo": mongo_quiz, "mysql": mysql_quiz, "match": mongo_quiz == mysql_quiz,
                        "proxy": "quiz 提交事件 vs quiz_answer_session 行",
                    },
                    "session_complete": {
                        "mongo": mongo_sc, "mysql": mysql_sc, "match": mongo_sc == mysql_sc,
                        "proxy": "completed=true 事件 vs completed_flag=1 行（updated_at 代理列，可能高估）",
                    },
                })
    finally:
        conn.close()
        client.close()

    checks = []
    for r in rows_out:
        for t in ("video_heartbeat", "quiz_submit", "session_complete"):
            checks.append(r[t]["match"])
    matched = sum(1 for c in checks if c)
    total = len(checks)
    return {
        "window": {"since": since.isoformat(timespec="seconds"), "until": until.isoformat(timespec="seconds")},
        "users": users,
        "rows": rows_out,
        "consistency": {"matched": matched, "total": total,
                        "rate": round(matched / total, 4) if total else None},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="R-M1 learning_event vs MySQL 进度表 只读对账")
    ap.add_argument("--sample", type=int, default=0, help="抽样用户数（0=全部）")
    ap.add_argument("--hours", type=int, default=0, help="窗口=最近 N 小时（0=自动：首条事件起）")
    ap.add_argument("--since", type=str, default="", help="窗口起点 ISO（覆盖 --hours）")
    ap.add_argument("--json", type=str, default="", help="结果 JSON 落盘路径")
    args = ap.parse_args()

    coll, client = _mongo_coll()
    try:
        first = coll.find_one(sort=[("ts", 1)])
        until = datetime.now() + timedelta(minutes=5)  # +5min 缓冲防钟差
        if args.since:
            since = datetime.fromisoformat(args.since)
        elif args.hours:
            since = datetime.now() - timedelta(hours=args.hours)
        else:
            base = first["ts"] if first else datetime.now()
            since = base - timedelta(minutes=5)
        users = sorted({int(d["user_id"]) for d in coll.find(
            {"ts": {"$gte": since, "$lte": until}}, {"user_id": 1})})
        total_events = coll.count_documents({"ts": {"$gte": since, "$lte": until}})
    finally:
        client.close()

    if args.sample and len(users) > args.sample:
        users = users[: args.sample]
    print(f"[mevent_reconcile] mongo events in window={total_events} users={len(users)} "
          f"since={since.isoformat(timespec='seconds')}")

    result = reconcile(users, since, until)
    rate = result["consistency"]["rate"]
    print(f"[mevent_reconcile] 一致率: {result['consistency']['matched']}/{result['consistency']['total']}"
          f" = {rate if rate is not None else 'N/A(无对账项)'}")
    for r in result["rows"]:
        flag = lambda m: "OK " if m else "DIFF"
        print(f"  user={r['user_id']}: vh[{flag(r['video_heartbeat']['match'])} mongo_rows="
              f"{r['video_heartbeat']['mongo_tick_rows']} mysql_rows={r['video_heartbeat']['mysql_tick_rows']}] "
              f"quiz[{flag(r['quiz_submit']['match'])} {r['quiz_submit']['mongo']}/{r['quiz_submit']['mysql']}] "
              f"complete[{flag(r['session_complete']['match'])} {r['session_complete']['mongo']}/{r['session_complete']['mysql']}]")
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"[mevent_reconcile] JSON 已写入 {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
