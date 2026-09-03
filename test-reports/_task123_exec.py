import pymysql, re

SQL = r"E:\stu\project\stu\EduAgent实施手册\refactor_sql\06_task123_clean_itest.sql"
with open(SQL, encoding='utf-8') as f:
    raw = f.read()

# 去注释行和备份声明头，拆分语句
lines = [l for l in raw.splitlines() if not l.strip().startswith('--') and l.strip()]
body = "\n".join(lines)
# 剔除头部的 mysqldump 命令块（在 -- ═ 注释内，已被注释过滤）
body = body.split('COMMIT;')[0] + 'COMMIT;'

c = pymysql.connect(host='127.0.0.1', user='root', password='123456', database='edu', autocommit=False)
cur = c.cursor()
statements = [s.strip() for s in body.split(';') if s.strip()]
rows_affected = 0
for stmt in statements:
    # 跳过 SET 指令类
    if re.match(r'^(SET|START)', stmt, re.I):
        cur.execute(stmt)
        continue
    cur.execute(stmt)
    rc = cur.rowcount
    rows_affected += max(rc, 0)
    print(f"[{rc}] {stmt[:70]}")
c.commit()
print("TOTAL_AFFECTED=", rows_affected)

# 复验
cur.execute("SELECT COUNT(*) FROM sys_user WHERE account LIKE 'itest-%'")
print("after user =", cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM series WHERE series_code LIKE 'itest-%'")
print("after series =", cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM sys_user_auth WHERE user_id IN (SELECT id FROM sys_user WHERE account LIKE 'itest-%')")
print("after auth =", cur.fetchone()[0])
c.close()