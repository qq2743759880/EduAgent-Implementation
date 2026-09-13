# -*- coding: utf-8 -*-
# task119 探针10：新建一条测试 order_item，再建报名+play_session
import asyncio, asyncmy
CFG = dict(host="127.0.0.1", port=3306, user="root", password="123456", db="edu", autocommit=True)
async def q(conn, sql, *args):
    async with conn.cursor() as cur:
        await cur.execute(sql, args)
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, await cur.fetchall()
async def w(conn, sql, *args):
    async with conn.cursor() as cur:
        return await cur.execute(sql, args)

async def main():
    conn = await asyncmy.connect(**CFG)
    try:
        c, r = await q(conn, "SHOW COLUMNS FROM order_item")
        print("order_item cols:[", ", ".join([f"{x[0]}:{x[1]}:null={x[3]}:key={x[4]}:def={x[5]}" for x in r]), "]")
        # 一条既有样例的值分布
        c, r = await q(conn, "SELECT * FROM order_item ORDER BY id DESC LIMIT 1")
        print("sample:", r)

        # 幂等清理
        await w(conn, "DELETE FROM student_cohort_rel WHERE user_id=1 AND cohort_id=1")
        n = await w(conn,
            """INSERT INTO student_cohort_rel (institution_id, user_id, student_id, cohort_id, order_item_id, enroll_status, enroll_at, created_at, updated_at)
               VALUES (1, 1, 99843, 1, 80256, 'active', NOW(), NOW(), NOW())""")
        print("insert rel:", n)

        c, r = await q(conn, "SELECT id, user_id, video_id FROM session_video_play WHERE user_id=1 AND video_id=5")
        if r:
            print("已有 play_session:", r)
        else:
            n = await w(conn,
                """INSERT INTO session_video_play
                   (institution_id, video_id, user_id, student_id, play_session_no,
                    device_type, client_type, device_os, started_at, created_at, updated_at)
                   VALUES (1, 5, 1, 99843, CONCAT('t119-', UNIX_TIMESTAMP(NOW())),
                           'WEB','browser','windows', NOW(), NOW(), NOW())""")
            c, r = await q(conn, "SELECT id, user_id, video_id FROM session_video_play WHERE user_id=1 AND video_id=5")
            print("insert play:", n, "->", r)
    finally:
        conn.close()
asyncio.run(main())