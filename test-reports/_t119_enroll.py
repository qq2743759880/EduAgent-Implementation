# -*- coding: utf-8 -*-
# task119 边界态实验：参数 1=off 删报名, 2=on 恢复报名
import asyncio, asyncmy, sys
CFG = dict(host="127.0.0.1", port=3306, user="root", password="123456", db="edu", autocommit=True)
async def main(mode):
    conn = await asyncmy.connect(**CFG)
    try:
        if mode == "off":
            n = 0
            async with conn.cursor() as cur:
                n = await cur.execute("UPDATE student_cohort_rel SET enroll_status='cancelled' WHERE user_id=1 AND cohort_id=1")
            print("报名置为 cancelled，影响", n, "行")
        elif mode == "on":
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM student_cohort_rel WHERE user_id=1 AND cohort_id=1")
                n = await cur.execute("""INSERT INTO student_cohort_rel (institution_id, user_id, student_id, cohort_id, order_item_id, enroll_status, enroll_at, created_at, updated_at)
                   VALUES (1, 1, 99843, 1, 80256, 'active', NOW(), NOW(), NOW())""")
            print("恢复 active 报名，影响", n, "行")
    finally:
        conn.close()
asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "on"))