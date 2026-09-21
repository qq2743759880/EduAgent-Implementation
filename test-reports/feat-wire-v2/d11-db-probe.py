# -*- coding: utf-8 -*-
"""#11 诊断：读 user_memory_event / user_memory 现状（凭据从 .env 读取，不回显）"""
import asyncio
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ENV = {}
for line in io.open(r"E:\stu\project\stu\EduAgent实施手册\edu-agent\.env", encoding="utf-8"):
    m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
    if m:
        ENV[m.group(1)] = m.group(2)

import asyncmy


async def main():
    conn = await asyncmy.connect(
        host=ENV["MYSQL_HOST"], port=int(ENV["MYSQL_PORT"]),
        user=ENV["MYSQL_USER"], password=ENV["MYSQL_PASSWORD"],
        db=ENV["MYSQL_DATABASE"],
    )
    cur = conn.cursor()
    await cur.execute("SELECT COUNT(*) FROM user_memory_event")
    print("user_memory_event total:", (await cur.fetchall())[0][0])
    await cur.execute("SELECT COUNT(*) FROM user_memory_event WHERE valid_to IS NULL AND event_type<>'delete'")
    print("HEAD events:", (await cur.fetchall())[0][0])
    await cur.execute(
        "SELECT id, user_id, entity_type, event_type, LEFT(memory_content,60), created_at "
        "FROM user_memory_event WHERE valid_to IS NULL AND event_type<>'delete' ORDER BY id DESC LIMIT 10"
    )
    for r in await cur.fetchall():
        print("HEAD:", r)
    await cur.execute("SELECT COUNT(*) FROM user_memory")
    print("user_memory snapshot rows:", (await cur.fetchall())[0][0])
    conn.close()


asyncio.run(main())
