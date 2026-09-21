# -*- coding: utf-8 -*-
"""REWORK P0-6：演示主账号（user000001, user_id=1）冲突记忆一次性治理（三核闸）。

范围（仅 user_id=1 的 HEAD 行）：
  - 名字槽位冲突：content LIKE '用户名字：%' / '用户姓名%' / '我的名字%' / '我叫%'
  - 空 content 历史脏行
  - 「纠正：改成 999999」等纠错测试残留

三核闸：
  ① 备份：受影响 HEAD 行全量导出 d06-governance-backup.json；
  ② 行数一致：UPDATE ... AND valid_to IS NULL 幂等盖章，更新行数 == 备份行数；
     治理后上述模式 HEAD 行数 == 0；
  ③ 幂等：重跑更新 0 行、无二次变更。

语义红线：只盖 valid_to（事件溯源 update/close 语义），不改任何行内容、不物理删除
（append-only 保持；召回层 fetch_by_ids 强制 HEAD 过滤，盖章即刻生效，无需动向量）。
"""
import asyncio
import io
import json
import re
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ENV = {}
for line in io.open(r"E:\stu\project\stu\EduAgent实施手册\edu-agent\.env", encoding="utf-8"):
    m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
    if m:
        ENV[m.group(1)] = m.group(2)

BACKUP = r"E:\stu\project\stu\EduAgent实施手册\test-reports\feat-wire-v2\d06-governance-backup.json"

NAME_PATTERNS = ("用户名字：%", "用户姓名%", "我的名字%", "我叫%")
HEAD_WHERE = "valid_to IS NULL AND event_type <> 'delete'"
SELECT_FIELDS = ("id, entity_id, user_id, event_type, memory_type, topic, content, "
                 "importance, score, valid_from, valid_to, created_at")


async def main():
    import asyncmy

    conn = await asyncmy.connect(
        host=ENV["MYSQL_HOST"], port=int(ENV["MYSQL_PORT"]),
        user=ENV["MYSQL_USER"], password=ENV["MYSQL_PASSWORD"], db=ENV["MYSQL_DATABASE"],
    )
    cur = conn.cursor()

    # ① 盘点受影响 HEAD 行（全参数化，LIKE 模式不作 SQL 字面量）
    like_sql = " OR ".join(["content LIKE %s"] * (len(NAME_PATTERNS) + 2))
    where = f"user_id = 1 AND ({like_sql}) AND {HEAD_WHERE}"
    args = tuple(NAME_PATTERNS) + ("%999999%", "")
    await cur.execute(f"SELECT {SELECT_FIELDS} FROM user_memory_event WHERE {where}", args)
    rows = await cur.fetchall()
    cols = [c[0] for c in cur.description]
    affected = [dict(zip(cols, r)) for r in rows]
    print(f"① 受影响 HEAD 行：{len(affected)}")
    for r in affected:
        print(f"   id={r['id']} entity={r['entity_id']} type={r['event_type']} content={r['content'][:50]!r}")
    io.open(BACKUP, "w", encoding="utf-8").write(json.dumps(
        {"governed_at": datetime.now().isoformat(), "user_id": 1, "rows": affected},
        ensure_ascii=False, indent=2, default=str))
    print(f"① 备份 → {BACKUP}")

    if not affected:
        print("② 无受影响行（可能已治理过=幂等路径）")
    else:
        ids = [r["id"] for r in affected]
        fmt = ",".join(["%s"] * len(ids))
        await cur.execute(
            f"UPDATE user_memory_event SET valid_to = NOW() "
            f"WHERE id IN ({fmt}) AND valid_to IS NULL",
            tuple(ids),
        )
        await conn.commit()
        updated = cur.rowcount
        print(f"② 盖章关闭 {updated} 行（备份 {len(affected)} 行）")
        assert updated == len(affected), f"行数不一致：updated={updated} backup={len(affected)}"

    # ② 治理后核验：模式 HEAD 必须清零
    await cur.execute(f"SELECT COUNT(*) FROM user_memory_event WHERE {where}", args)
    remain = (await cur.fetchall())[0][0]
    assert remain == 0, f"治理后仍有 {remain} 行残留 HEAD"
    print(f"② 治理后核验：模式 HEAD 残留 = 0 ✓")

    # ③ 幂等重跑：不再有可治理行
    await cur.execute(f"SELECT COUNT(*) FROM user_memory_event WHERE {where}", args)
    assert (await cur.fetchall())[0][0] == 0
    await cur.execute("SELECT COUNT(*) FROM user_memory_event WHERE user_id = 1 AND " + HEAD_WHERE)
    heads = (await cur.fetchall())[0][0]
    print(f"③ 幂等核验通过；user_id=1 剩余有效 HEAD = {heads}")
    conn.close()


asyncio.run(main())
