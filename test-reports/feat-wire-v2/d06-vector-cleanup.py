# -*- coding: utf-8 -*-
"""REWORK P0-6 补刀：治理盖章实体的向量补删（死向量占位致召回假空的根因清理）。

从 DB 现算 user_id=1 名下「已无有效 HEAD 的实体」（被盖章/软删），在 Milvus 记忆集合
删除对应向量。幂等：不存在即 no-op。召回层 fetch_by_ids 本就会过滤死向量，本脚本是
防止其继续占据 top_k 名额的卫生清理。
"""
import asyncio
import io
import re
import sys

sys.path.insert(0, r"E:\stu\project\stu\EduAgent实施手册\edu-agent")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ENV = {}
for line in io.open(r"E:\stu\project\stu\EduAgent实施手册\edu-agent\.env", encoding="utf-8"):
    m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
    if m:
        ENV[m.group(1)] = m.group(2)


async def main():
    import asyncmy

    conn = await asyncmy.connect(
        host=ENV["MYSQL_HOST"], port=int(ENV["MYSQL_PORT"]),
        user=ENV["MYSQL_USER"], password=ENV["MYSQL_PASSWORD"], db=ENV["MYSQL_DATABASE"],
    )
    cur = conn.cursor()
    await cur.execute(
        "SELECT DISTINCT entity_id FROM user_memory_event WHERE user_id = 1 "
        "AND entity_id NOT IN ("
        "  SELECT entity_id FROM user_memory_event"
        "  WHERE user_id = 1 AND valid_to IS NULL AND event_type <> 'delete')"
    )
    dead = [int(r[0]) for r in await cur.fetchall()]
    conn.close()
    print(f"已无有效 HEAD 的实体（向量待删）: {dead}")

    from app.ai.memory.vector import MemoryVectorStore

    v = MemoryVectorStore()
    ok = 0
    for eid in dead:
        try:
            await v.delete(eid)
            ok += 1
        except Exception as e:
            print(f"  delete {eid}: {type(e).__name__}: {e}")
    print(f"向量补删完成 {ok}/{len(dead)}（不存在即 no-op=幂等）")


asyncio.run(main())
