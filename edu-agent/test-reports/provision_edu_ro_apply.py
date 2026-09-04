# 应用 test-reports/provision_edu_ro.sql 并验证 edu_ro 账号已存在且仅具 SELECT 权限
import asyncio
import asyncmy


async def main():
    conn = await asyncmy.connect(host="localhost", port=3306, user="root", password="123456", db="mysql", autocommit=True)
    cur = conn.cursor()
    sql_text = open(r"test-reports\provision_edu_ro.sql", encoding="utf-8").read()
    for stmt in sql_text.split(";"):
        stmt = stmt.strip()
        if stmt and not stmt.startswith("--"):
            await cur.execute(stmt)
    await cur.execute("SELECT user, host FROM mysql.user WHERE user='edu_ro'")
    print("edu_ro users:", await cur.fetchall())
    await cur.execute("SELECT CURRENT_USER()")
    print("cur user:", await cur.fetchall())
    # 用只读账号实测连接 edu 库并读一张表
    ro = await asyncmy.connect(host="localhost", port=3306, user="edu_ro", password="edu_ro_pwd_2026", db="edu", autocommit=True)
    rc = ro.cursor()
    await rc.execute("SELECT COUNT(*) FROM coupon")
    print("edu_ro read coupon count:", (await rc.fetchone())[0])
    # 只读账号写应被拒绝（验证仅 SELECT）
    try:
        await rc.execute("DELETE FROM coupon WHERE 1=0")
        print("WARN: edu_ro can WRITE! (DELETE allowed)")
    except Exception as e:
        print("edu_ro write correctly denied:", type(e).__name__, e)
    await rc.close(); ro.close()
    await cur.close(); conn.close()


asyncio.run(main())