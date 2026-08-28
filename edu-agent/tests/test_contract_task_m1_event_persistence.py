"""task-M1-② 契约测试：user_memory_event / user_memory_entity_seq 真实读写冒烟。

验收目标：通过生产路径 SqlEventMemoryPersistence 对两张表做真实读写：
- user_memory_event（事件溯源 append-only）：insert 写入、fetch_entity 读回一致；
- user_memory_entity_seq（entity_id 分配器）：_next_entity_id 连续分配且自增。

依据：app/ai/memory/event_persistence.py
- _DDL_STATEMENTS 含两表 IF NOT EXISTS 建表
- _ensure 幂等懒建
- _next_entity_id 向 user_memory_entity_seq 插空行返回 lastrowid
- insert / fetch_entity 对 user_memory_event 读写
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, ".")

# 本地 MySQL 默认口令；若环境已注入 MYSQL_PASSWORD 则不覆盖
os.environ.setdefault("MYSQL_PASSWORD", "123456")

from app.database import init_mysql, close_mysql, execute_write
from app.ai.memory.event_persistence import SqlEventMemoryPersistence


async def _exercise() -> tuple[int, int]:
    await init_mysql()
    try:
        store = SqlEventMemoryPersistence()
        # _ensure 幂等建表（若表不存在则建；存在则 no-op）
        await store._ensure()

        # entity_seq 分配器：连续两次应单调递增
        e1 = await store._next_entity_id()
        e2 = await store._next_entity_id()
        assert e2 > e1, f"entity_seq 未自增: e1={e1} e2={e2}"

        # user_memory_event 写入 + 读回一致
        uid = 990000 + (uuid.uuid4().int % 9000)
        content = f"M1_冒烟_偏好_网络攻防_{uuid.uuid4().hex[:8]}"
        entity_id = await store.insert(
            user_id=uid, memory_type="preference", topic="security",
            content=content, importance=4, score=0.87,
        )
        # insert 内部会再分配一次 entity_id（第 3 次），应等于 e2+1，证明 seq 单调分配被真实使用
        assert entity_id == e2 + 1, f"insert 返回的 entity_id 与 seq 不一致: {entity_id} vs {e2}+1"

        got = await store.fetch_entity(entity_id)
        assert got is not None, "insert 后 fetch_entity 读不到"
        assert got.content == content, f"user_memory_event 内容未真实落库: {got.content!r}"
        assert got.user_id == uid, f"user_id 未落库: {got.user_id}"
        assert got.importance == 4 and abs(got.score - 0.87) < 1e-6, "importance/score 未落库"

        # 事件溯源：update 产生新 HEAD（valid_to 盖章旧行）
        new_content = f"M1_冒烟_更新_偏好_{uuid.uuid4().hex[:8]}"
        await store.update_memory(entity_id, content=new_content, operator="crit-test")
        updated = await store.fetch_entity(entity_id)
        assert updated.content == new_content, f"update 后 HEAD 未刷新: {updated.content!r}"

        # 清理（按测试 user_id 删除事件行，避免污染审计表；entity_seq 单调自增可留）
        await execute_write("DELETE FROM user_memory_event WHERE user_id=%s", (uid,))
        return e1, e2
    finally:
        await close_mysql()


def test_event_tables_real_read_write():
    e1, e2 = asyncio.run(_exercise())
    assert e2 > e1


if __name__ == "__main__":
    e1, e2 = asyncio.run(_exercise())
    print(f"ALL OK: M1-② user_memory_event / user_memory_entity_seq 真实读写冒烟通过 (seq {e1}->{e2})")
