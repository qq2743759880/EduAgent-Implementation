"""task-M1-③ 契约测试：记忆容量按用户活跃度分档配置化（去 500 硬编码兜底）。

验收目标：
- memory_capacity_for(user_id, tier) 按 MEMORY_CAPACITY_TIERS 分档返回不同容量（非硬编码单值）；
- 用户级 OVERRIDE 可精调；
- MemoryStore 的 _capacity 来自配置分档（非字面量 500）；
- compact_user 接受显式 capacity 时按该容量压缩（真正按用户/调用动态），且默认路径回退到配置解析值。

依据：app/config.py（MEMORY_CAPACITY_TIERS / DEFAULT_TIER / USER_OVERRIDE / memory_capacity_for）、
app/ai/memory/store.py（_capacity 走 memory_capacity_for）、
app/ai/memory/compactor.py（cap 走 resolver，去掉字面量 500）。
"""
import asyncio
import sys

sys.path.insert(0, ".")

from app.config import settings, memory_capacity_for
from app.ai.memory.store import MemoryStore
from app.ai.memory.event_persistence import MemEventMemoryPersistence
from app.ai.memory.compactor import compact_user


def test_resolver_tiers_and_override():
    # 分档返回不同容量（来自配置 dict，非硬编码）
    assert memory_capacity_for(1, tier="inactive") == settings.MEMORY_CAPACITY_TIERS["inactive"]
    assert memory_capacity_for(1, tier="power") == settings.MEMORY_CAPACITY_TIERS["power"]
    assert settings.MEMORY_CAPACITY_TIERS["power"] != settings.MEMORY_CAPACITY_TIERS["normal"]
    # 默认档
    assert memory_capacity_for(1) == settings.MEMORY_CAPACITY_TIERS[settings.MEMORY_CAPACITY_DEFAULT_TIER]
    # 用户级覆盖优先于分档
    uid = 777777
    settings.MEMORY_CAPACITY_USER_OVERRIDE[uid] = 123
    try:
        assert memory_capacity_for(uid) == 123
        # 覆盖值优先于任何 tier
        assert memory_capacity_for(uid, tier="power") == 123
    finally:
        settings.MEMORY_CAPACITY_USER_OVERRIDE.pop(uid, None)


def test_store_capacity_from_tier_not_hardcoded():
    # store._capacity 来自配置分档，而非字面量 500
    normal_store = MemoryStore(MemEventMemoryPersistence(), vector_store=None,
                               capacity_tier=settings.MEMORY_CAPACITY_DEFAULT_TIER)
    assert normal_store._capacity == settings.MEMORY_CAPACITY_TIERS["normal"]
    power_store = MemoryStore(MemEventMemoryPersistence(), vector_store=None,
                             capacity_tier="power")
    assert power_store._capacity == settings.MEMORY_CAPACITY_TIERS["power"]
    # 显式 capacity 仍优先
    exp_store = MemoryStore(MemEventMemoryPersistence(), vector_store=None, capacity=42)
    assert exp_store._capacity == 42


def _build_store_with_n(n: int, capacity: int):
    store = MemoryStore(MemEventMemoryPersistence(), vector_store=None, capacity=capacity)
    for i in range(n):
        asyncio.run(store.write(user_id=1001, content=f"mem-{i}", importance=3))
    return store


def test_compact_user_honors_dynamic_capacity():
    # 小容量 → 触发压缩；大容量 → 不压缩（证明容量是动态传入，非硬编码）
    small = _build_store_with_n(10, capacity=3)
    r_small = asyncio.run(compact_user(small, 1001, capacity=3))
    assert r_small["compacted"] > 0, "小容量应触发压缩"

    big = _build_store_with_n(10, capacity=100)
    r_big = asyncio.run(compact_user(big, 1001, capacity=100))
    assert r_big["compacted"] == 0, "大容量不应触发压缩"


if __name__ == "__main__":
    test_resolver_tiers_and_override()
    test_store_capacity_from_tier_not_hardcoded()
    test_compact_user_honors_dynamic_capacity()
    print("ALL OK: M1-③ 记忆容量按用户活跃度分档配置化（去 500 硬编码）")
