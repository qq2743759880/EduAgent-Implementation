"""T3B B-G4 探针：检查 community_post 置顶帖重复形态（只读）"""
import pymysql

conn = pymysql.connect(host="localhost", port=3306, user="root", password="123456",
                       database="edu", charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
cur = conn.cursor()

cur.execute("SELECT id, title, board_code, is_pinned, created_at FROM community_post WHERE yn=1 AND is_pinned=1 ORDER BY id")
rows = cur.fetchall()
print("pinned count:", len(rows))
for r in rows:
    print(r["id"], "|", r["board_code"], "|", str(r["created_at"])[:10], "|", (r["title"] or "")[:32])

cur.execute("""
  SELECT title, COUNT(*) c, GROUP_CONCAT(id) ids
  FROM community_post WHERE yn=1 AND is_pinned=1
  GROUP BY title HAVING c > 1 ORDER BY c DESC
""")
print("--- duplicate pinned titles ---")
for r in cur.fetchall():
    print(r["c"], "x", (r["title"] or "")[:40], "ids=", r["ids"])

cur.execute("SELECT COUNT(*) c FROM community_post WHERE yn=1")
print("total yn=1 posts:", cur.fetchone()["c"])
conn.close()
