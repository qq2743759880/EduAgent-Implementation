import sys, asyncio
sys.path.insert(0, r"E:\stu\project\stu\EduAgent实施手册\edu-agent")
from app.database import init_mysql, close_mysql, get_mysql_pool  # noqa

async def main():
    await init_mysql()
    pool = get_mysql_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id, question_code, yn FROM `question` WHERE id IN (10529,10530,10531,10532) OR question_code LIKE 'T107%'")
            rows = await cur.fetchall()
            print("DB rows (id, question_code, yn) for all T107 temp questions:")
            for r in rows:
                print("  ", r)
            live = [r for r in rows if r[2] == 1]
            print("LIVE(non-deleted yn=1) count:", len(live))
    await close_mysql()

asyncio.run(main())