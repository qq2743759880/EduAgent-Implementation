# -*- coding: utf-8 -*-
"""task-M1 契约测试：记忆事件溯源 + Dream 巩固（生产级改造第一批 P0）。

全 in-process（Mem 变体零外部依赖），Dream 用 mock llm 验证升维逻辑，
压缩器用确定性规则摘要。可直接运行（落在测试窗口外亦安全）：
    cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_contract_task_m1.py -q

AC 覆盖：
① 写路径双行 + valid_to 盖章（append-only，不 UPDATE 内容）
② 检索强制 valid_to IS NULL（废弃/删除版本永不召回）
③ rewind 正确性（HEAD 回到目标版本，旧版本不物理删除）
④ history 审计含 trace_id（缺省自动生成 mem- 前缀）
⑤ 容量治理：压测收敛到容量上限 + 懒合成摘要（supports 引用源事件）
⑥ Dream 升维：mock llm 合并多条为结构化条目 + 源实体盖章废弃
⑦ 并发锁：SET NX EX 仅一个实例获锁成功（AC7）
 plus：API 层契约（/api/memory/* 纯增量，所有权 + 角色校验 403/200）
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.ai.memory.compactor import compact_user, _rule_summarize
from app.ai.memory.dream import run_dream
from app.ai.memory.dream_lock import DreamLock
from app.ai.memory.event_persistence import MemEventMemoryPersistence
from app.ai.memory.store import MemoryStore
from app.ai.memory.vector import MemoryVectorStore
from app.auth import get_current_user as _auth_gcu
from app.auth.dependencies import get_current_user as _dep_gcu
from app.auth.schemas import UserRole, UserInfo


@pytest.fixture(autouse=True)
def _restore_memory_service_state():
    """W-NEXT-R-MEM-001：隔离 service 模块级单例状态，防测试间污染。

    本文件 `_make_client` 会直接覆盖 `svc._ensure_instances`（fake 返回 (store, None)）
    且历史上不恢复——同进程后续文件（r01/rmem1 的 service 层用例）会拿到 None queue，
    以 "'NoneType' object has no attribute 'enqueue_turn_window'" 失败。此处 autouse
    快照/恢复四项模块级状态（既修污染外溢，也不影响本文件内用例语义）。
    """
    import app.ai.memory.service as svc

    saved = (svc._ensure_instances, svc._store, svc._queue, svc._worker_started)
    yield
    (svc._ensure_instances, svc._store, svc._queue, svc._worker_started) = saved


# ---------------------------------------------------------------------------
# 测试夹具
# ---------------------------------------------------------------------------
class _TestEmbedder:
    """零依赖测试 embedder（避免触发 BGE-M3 2.2GB 模型加载）。"""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim
        self.degraded_reason: str | None = None

    def embed_batch(self, texts):
        return [[0.0] * self.dim for _ in texts]

    def embed(self, text):
        return self.embed_batch([text])[0]


def make_store(capacity: int = 500) -> MemoryStore:
    persist = MemEventMemoryPersistence()
    vector = MemoryVectorStore(milvus_uri="", embedder=_TestEmbedder())
    return MemoryStore(persist, vector, capacity=capacity)


def _user(user_id: int, role: UserRole, nickname: str = "u") -> UserInfo:
    return UserInfo(
        user_id=user_id, nickname=nickname, real_name=None, mobile=None,
        email=None, gender=None, avatar_url=None, role=role,
    )


class FakeRedis:
    """极简 Redis 替身：实现 SET NX EX + DELETE（acquire 仅首次成功）。"""

    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    async def set(self, key, value, *, nx: bool = False, ex: int | None = None):
        if key in self._d:
            return None  # NX 失败
        self._d[key] = value
        return True

    async def delete(self, key):
        self._d.pop(key, None)


# ---------------------------------------------------------------------------
# AC① 写路径双行 + valid_to 盖章
# ---------------------------------------------------------------------------
def test_ac1_write_path_dual_row_stamp():
    async def run():
        store = make_store()
        eid = await store.write(
            user_id=1, content="v1 爱好 Python", memory_type="preference", topic="tech", importance=4
        )
        h0 = await store.history(entity_id=eid)
        assert len(h0) == 1 and h0[0]["event_type"] == "create"

        await store.update_memory(entity_id=eid, content="v2 爱好 Python/FastAPI",
                                  operator="user", trace_id="tr-u1")

        h1 = await store.history(entity_id=eid)
        assert len(h1) == 2, "更新应产生第 2 行事件（append-only，非 UPDATE 内容）"

        heads = [e for e in h1 if e["valid_to"] is None]
        assert len(heads) == 1, "更新后仅 1 个 valid_to IS NULL 的 HEAD"
        assert heads[0]["event_type"] == "update"
        assert heads[0]["content"] == "v2 爱好 Python/FastAPI"

        create_row = next(e for e in h1 if e["event_type"] == "create")
        assert create_row["valid_to"] is not None, "旧版本必须被 valid_to 盖章（不 UPDATE 内容）"

        head = await store._persistence.fetch_entity(eid)
        assert head.content == "v2 爱好 Python/FastAPI"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# AC② 检索强制 valid_to IS NULL（废弃/删除版本永不召回）
# ---------------------------------------------------------------------------
def test_ac2_retrieval_valid_only():
    async def run():
        store = make_store()
        eids = [await store.write(user_id=1, content=f"mem {i}", importance=4) for i in range(5)]

        # entity0 更新到 v2
        await store.update_memory(entity_id=eids[0], content="mem 0 v2")
        # entity1 回滚到其 create 版本
        h1 = await store.history(entity_id=eids[1])
        await store.rewind(entity_id=eids[1], target_event_id=h1[0]["event_id"])
        # entity2 软删
        await store.delete_memory(entity_id=eids[2])

        eff = await store._persistence.list_effective(1)
        eff_eids = sorted(m.id for m in eff)
        assert eff_eids == sorted([eids[0], eids[1], eids[3], eids[4]]), \
            "被删除的实体不得出现在有效集合"

        # 每个返回项均为唯一 HEAD，且 fetch_entity 与之完全一致
        seen = set()
        for m in eff:
            head = await store._persistence.fetch_entity(m.id)
            assert head is not None and head.content == m.content
            assert m.id not in seen
            seen.add(m.id)

        # 删除实体的 fetch_by_ids 必须返回 []
        assert await store._persistence.fetch_by_ids([eids[2]]) == []

        # recall 不返回已删除内容，且每条有效实体至多出现一次
        rec = await store.recall(user_id=1, query="mem", top_k=10)
        contents = [r["content"] for r in rec]
        assert "mem 2" not in contents
        assert len(set(contents)) == len(contents)

    asyncio.run(run())


# ---------------------------------------------------------------------------
# AC③ rewind 正确性（HEAD 回到目标版本，旧版本不物理删除）
# ---------------------------------------------------------------------------
def test_ac3_rewind_correctness():
    async def run():
        store = make_store()
        eid = await store.write(user_id=7, content="原始偏好：喜欢 Python", importance=5)
        h0 = await store.history(entity_id=eid)
        v1_event_id = h0[0]["event_id"]

        await store.update_memory(entity_id=eid, content="更新偏好：喜欢 Python+Go",
                                  operator="user", trace_id="t-upd")

        res = await store.rewind(entity_id=eid, target_event_id=v1_event_id,
                                 operator="user", trace_id="t-rw")
        assert res == eid

        head = await store._persistence.fetch_entity(eid)
        assert head.content == "原始偏好：喜欢 Python", "回滚后 HEAD 应等于目标版本内容"

        h = await store.history(entity_id=eid)
        types = [e["event_type"] for e in h]
        assert types[0] == "rewind" and "update" in types and "create" in types

        # 旧 update 事件仍保留（append-only，未物理删除）
        assert any(e["event_type"] == "update" and e["content"] == "更新偏好：喜欢 Python+Go" for e in h)
        # create 事件原文保留（审计可回溯）
        assert any(e["event_type"] == "create" and e["content"] == "原始偏好：喜欢 Python" for e in h)

        heads = [e for e in h if e["valid_to"] is None]
        assert len(heads) == 1 and heads[0]["event_type"] == "rewind"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# AC④ history 审计含 trace_id（缺省自动生成 mem- 前缀）
# ---------------------------------------------------------------------------
def test_ac4_history_audit_trace_id():
    async def run():
        store = make_store()
        eid = await store.write(user_id=3, content="无 trace 自动生成", importance=4)
        await store.update_memory(entity_id=eid, content="带 trace 更新",
                                  operator="user", trace_id="trace-xyz-123")

        h = await store.history(entity_id=eid)
        assert len(h) == 2
        for e in h:
            assert e["trace_id"], "每条事件必须有 trace_id（审计溯源）"

        upd = next(e for e in h if e["event_type"] == "update")
        assert upd["trace_id"] == "trace-xyz-123", "显式 trace_id 应原样保留"
        create_ev = next(e for e in h if e["event_type"] == "create")
        assert create_ev["trace_id"].startswith("mem-"), "缺省 trace_id 应自动生成 mem- 前缀"
        assert create_ev["operator"] == "system"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# AC⑤ 容量治理：压测收敛 + 懒合成摘要（supports 引用源事件）
# ---------------------------------------------------------------------------
def test_ac5_capacity_compaction_converges():
    async def run():
        store = make_store(capacity=10)
        uid = 555
        for i in range(40):
            await store.write(user_id=uid, content=f"低频记忆 {i}", importance=4,
                              memory_type="fact", topic="t")

        before = await store._persistence.count_effective(uid)
        assert before == 40

        result = await compact_user(store, uid, summarizer=_rule_summarize, capacity=10)
        assert result["compacted"] > 0

        after = await store._persistence.count_effective(uid)
        assert after <= 10, f"压缩后有效数必须收敛到容量上限 10，实际 {after}"
        assert result["remaining"] == after

        # 懒合成摘要：合并事件内容以 [合并 开头，且 supports 引用源事件 id
        for ceid in result["consolidated_ids"]:
            ch = await store.history(entity_id=ceid)
            assert ch and ch[0]["event_type"] == "consolidate"
            assert ch[0]["content"].startswith("[合并"), "压缩应生成懒合成摘要"
            assert ch[0]["supports"], "consolidate 事件应引用被合并源事件 id（审计可回溯）"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# AC⑥ Dream 升维：mock llm 合并多条为结构化条目 + 源实体盖章废弃
# ---------------------------------------------------------------------------
def test_ac6_dream_consolidation_mock_llm():
    async def run():
        store = make_store()
        uid = 777
        e1 = await store.write(user_id=uid, content="喜欢 Python", importance=4)
        e2 = await store.write(user_id=uid, content="喜欢 FastAPI", importance=4)
        e3 = await store.write(user_id=uid, content="讨厌 Java", importance=4)

        entries = [{
            "content": "技术栈画像：偏好 Python/FastAPI，排斥 Java",
            "memory_type": "preference", "topic": "tech", "importance": 5,
            "source_entity_ids": [e1, e2, e3],
        }]

        async def fake_llm(messages, model=None):
            await asyncio.sleep(0.01)
            return json.dumps(entries)

        res = await run_dream(uid, llm=fake_llm, redis=FakeRedis(), store=store)
        assert res["acquired"] is True
        assert res["consolidated"] == 1, "应合并为 1 条升维记忆"
        assert len(res["consolidated_ids"]) == 1

        new_eid = res["consolidated_ids"][0]
        head = await store._persistence.fetch_entity(new_eid)
        assert head.content == "技术栈画像：偏好 Python/FastAPI，排斥 Java"

        for e in (e1, e2, e3):
            assert await store._persistence.fetch_entity(e) is None, \
                "源实体应被 consolidate 盖章（不再为 HEAD）"

        eff = await store._persistence.list_effective(uid)
        assert len(eff) == 1 and eff[0].id == new_eid

    asyncio.run(run())


# ---------------------------------------------------------------------------
# AC⑦ 并发锁：SET NX EX 仅一个实例获锁成功
# ---------------------------------------------------------------------------
def test_ac7_dream_lock_nx_ex():
    async def run():
        lock = DreamLock(ttl_s=60)
        r = FakeRedis()
        res = await asyncio.gather(lock.acquire(1, redis=r), lock.acquire(1, redis=r))
        assert sum(1 for x in res if x) == 1, "并发 acquire 仅一个应成功（SET NX 语义）"
        await lock.release(1, redis=r)
        assert await lock.acquire(1, redis=r) is True

    asyncio.run(run())


def test_ac7_dream_run_only_one_instance():
    async def run():
        store = make_store()
        uid = 888
        await store.write(user_id=uid, content="占位记忆", importance=4)

        async def fake_llm(messages, model=None):
            await asyncio.sleep(0.02)
            return "[]"

        r = FakeRedis()
        t1 = run_dream(uid, llm=fake_llm, redis=r, store=store)
        t2 = run_dream(uid, llm=fake_llm, redis=r, store=store)
        results = await asyncio.gather(t1, t2)
        acquired = [x["acquired"] for x in results]
        assert sum(acquired) == 1, "并发巩固仅一个实例应获锁成功（SET NX EX 语义）"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# API 层契约：/api/memory/* 纯增量 + 所有权/角色校验
# ---------------------------------------------------------------------------
def _make_client(store: MemoryStore):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.ai.memory.router import router as memory_router
    import app.ai.memory.service as svc

    app = FastAPI()
    app.include_router(memory_router)

    # 注入 in-process store，避免触碰真实 DB / Milvus
    async def fake_ensure():
        return store, None

    svc._ensure_instances = fake_ensure

    state = {"user": _user(2, UserRole.STUDENT, "u2")}

    async def fake_gcu():
        return state["user"]

    app.dependency_overrides[_auth_gcu] = fake_gcu
    app.dependency_overrides[_dep_gcu] = fake_gcu
    return TestClient(app), state


def test_api_contract_owner_admin_rewind_history():
    store = make_store()
    eid = asyncio.run(store.write(user_id=2, content="API 记忆 v1", importance=4))
    client, state = _make_client(store)

    # 属主（user_id=2）读取历史 → 200
    r = client.get(f"/api/memory/history/{eid}")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0 and body["data"]["count"] >= 1

    # 属主回滚到 create 版本 → 200
    v1_event = body["data"]["events"][-1]["event_id"]  # desc：create 在末尾
    r2 = client.post("/api/memory/rewind", json={"entity_id": eid, "target_event_id": v1_event})
    assert r2.status_code == 200 and r2.json()["code"] == 0

    # 非属主（student, user_id=3）→ 403
    state["user"] = _user(3, UserRole.STUDENT, "u3")
    r3 = client.get(f"/api/memory/history/{eid}")
    assert r3.status_code == 403, "非属主且无管理员角色必须 403"

    # 管理员 → 200
    state["user"] = _user(1, UserRole.ADMIN, "admin")
    r4 = client.get(f"/api/memory/history/{eid}")
    assert r4.status_code == 200

    # 管理员手动触发 Dream（uid=999 无记忆 → 200，不触真实 LLM）
    r5 = client.post("/api/memory/admin/dream/run", json={"user_id": 999})
    assert r5.status_code == 200 and r5.json()["code"] == 0

    # 普通学生触发 admin 端点 → 403
    state["user"] = _user(3, UserRole.STUDENT, "u3")
    r6 = client.post("/api/memory/admin/dream/run", json={"user_id": 999})
    assert r6.status_code == 403
