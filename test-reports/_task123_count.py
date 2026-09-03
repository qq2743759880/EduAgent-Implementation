import pymysql
c = pymysql.connect(host='127.0.0.1', user='root', password='123456', database='edu')
cur = c.cursor()
q = [
    ("itest user", "SELECT COUNT(*) FROM sys_user WHERE account LIKE 'itest-%'"),
    ("itest series", "SELECT COUNT(*) FROM series WHERE series_code LIKE 'itest-%'"),
    ("itest auth", "SELECT COUNT(*) FROM sys_user_auth WHERE user_id IN (SELECT id FROM sys_user WHERE account LIKE 'itest-%')"),
    ("itest cohort", "SELECT COUNT(*) FROM series_cohort WHERE series_id IN (SELECT id FROM series WHERE series_code LIKE 'itest-%')"),
]
for name, sql in q:
    cur.execute(sql)
    print(name, "=", cur.fetchone()[0])
c.close()