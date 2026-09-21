# -*- coding: utf-8 -*-
"""REWORK P0-1：记忆槽位 update 语义 + 召回同槽位最新优先 回归测试。

audit P0-1 实证：A 会话自述新名字→B 会话立刻问答旧名（fw2小明1073 而非最新），45s 后又
随机换答。根因：多条名字记忆并存（各自独立 entity），召回按向量相似度随机赢；无 update 语义。
修复：
  ① store.write 落库即关闭同槽位旧 HEAD（valid_to 盖章，append-only：不改内容不追加 delete 事件）
  ② store.recall 同槽位多条命中只留最新（id 最大）
  ③ sync_extract_and_write：done 帧前同步规则落库（5 秒验收）

持久层用内存假件（仿 SqlEventMemoryPersistence 的 HEAD/盖章语义），零外部依赖。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from app.ai.memory import store as store_mod
from app.ai.memory.ingest import detect_memory_slot, detect_memories, slot_like_patterns
from app.ai.memory.schemas import UserMemory
from app.ai.memory.store import MemoryStore
from app.ai.memory.vector import MemoryVectorStore


class FakePersistence:
    """内存事件溯源假件：entity_id 分组、_stamp_head 语义与 SQL 版一致。"""

    def __init__(self):
        self._next_entity = 0
        self._next_event = 0
        self.rows: list[dict[str, Any]] = []  # 每行=一个事件

    async def insert(self, *, user_id, memory_type, topic, content, importance, score):
        self._next_entity += 1
        self._next_event += 1
        now = datetime.now()
        self.rows.append({
            "id": self._next_event, "entity_id": self._next_entity, "user_id": int(user_id),
            "memory_type": memory_type, "topic": topic, "content": content,
            "importance": importance, "score": score, "access_count": 0, "last_access_at": None,
            "valid_from": now, "valid_to": None, "event_type": "create", "created_at": now,
        })
        return self._next_entity

    def _head(self, entity_id):
        heads = [r for r in self.rows if r["entity_id"] == entity_id and r["valid_to"] is None]
        return heads[0] if heads else None

    async def close_slot_heads(self, user_id, *, exclude_entity_id, like_patterns):
        closed = []
        for r in self.rows:
            if (r["user_id"] == int(user_id) and r["entity_id"] != int(exclude_entity_id)
                    and r["valid_to"] is None and r["event_type"] != "delete"
                    and any(r["content"].startswith(p.rstrip("%")) for p in like_patterns)):
                r["valid_to"] = datetime.now()
                closed.append(r["entity_id"])
        return closed

    async def fetch_by_ids(self, memory_ids):
        out = []
        for eid in memory_ids:
            h = self._head(eid)
            if h is not None and h["event_type"] != "delete":
                out.append(self._row_to_mem(h))
        return out

    def _row_to_mem(self, h):
        return UserMemory(id=h["entity_id"], user_id=h["user_id"], memory_type=h["memory_type"],
                          topic=h["topic"], content=h["content"], importance=h["importance"],
                          score=h["score"], access_count=h["access_count"],
                          last_access_at=h["last_access_at"], created_at=h["created_at"])

    async def touch(self, memory_id, *, access_count, score, last_access_at):
        h = self._head(memory_id)
        if h:
            h["access_count"] = access_count
            h["score"] = score
            h["last_access_at"] = last_access_at

    async def count_effective(self, user_id):
        return len({r["entity_id"] for r in self.rows
                    if r["user_id"] == int(user_id) and r["valid_to"] is None and r["event_type"] != "delete"})


class FakeVector(MemoryVectorStore):
    """向量假件：按内容包含关系打分（名字命中即可），支持 delete。"""

    def __init__(self):
        self.items: dict[int, dict] = {}

    async def upsert(self, *, memory_id, user_id, content):
        self.items[int(memory_id)] = {"user_id": int(user_id), "content": content}

    async def delete(self, memory_id):
        self.items.pop(int(memory_id), None)

    async def invalidate(self, memory_id):
        await self.delete(memory_id)

    async def search(self, *, user_id, query, top_k):
        q = (query or "").strip()
        scored = []
        for mid, it in self.items.items():
            if it["user_id"] != int(user_id):
                continue
            # 简单包含相似度：名字查询与名字记忆天然高相似；旧名也相似 → 槽位去重才有意义
            score = 0.9 if ("名字" in q and ("名字" in it["content"] or "我叫" in it["content"])) else 0.1
            scored.append({"memory_id": mid, "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]


def _make_store(monkeypatch) -> MemoryStore:
    p = FakePersistence()
    v = FakeVector()
    s = MemoryStore(persistence=p, vector_store=v, capacity=500)
    return s


def test_slot_detection():
    """槽位识别：规则前缀/整句我叫/旧数据我的名字 → user_name；其他 → None。"""
    assert detect_memory_slot("用户名字：小明") == "user_name"
    assert detect_memory_slot("我叫小明，请记住") == "user_name"
    assert detect_memory_slot("我的名字") == "user_name"
    assert detect_memory_slot("目标：雅思 6.5") is None
    assert detect_memory_slot("用户在学 Python") is None
    assert slot_like_patterns("user_name")  # LIKE 模式非空


def test_write_closes_old_name_heads(monkeypatch):
    """① 新名字落库即关闭旧名字 HEAD（append-only：旧行内容不变、无 delete 事件追加）。"""
    s = _make_store(monkeypatch)

    async def _run():
        e1 = await s.write(user_id=1, content="用户名字：小明", memory_type="profile",
                           topic="preferences", importance=5)
        e2 = await s.write(user_id=1, content="用户名字：小红", memory_type="profile",
                           topic="preferences", importance=5)
        return e1, e2

    e1, e2 = asyncio.run(_run())
    p: FakePersistence = s._persistence
    old_rows = [r for r in p.rows if r["entity_id"] == e1]
    # 旧行：valid_to 已盖章、内容未被修改、没有追加 delete 事件行
    assert all(r["valid_to"] is not None for r in old_rows if r["entity_id"] == e1)
    assert any(r["content"] == "用户名字：小明" and r["valid_to"] is not None for r in old_rows), \
        "旧 HEAD 盖章后内容必须原样保留（append-only）"
    assert not any(r["event_type"] == "delete" and r["entity_id"] == e1 for r in p.rows), \
        "槽位关闭是 update 语义（valid_to 盖章），不得追加 delete 事件"
    # 向量：旧实体已删、新实体在
    assert e1 not in s._vector.items and e2 in s._vector.items
    # HEAD 判据（AGENTS 教训11 原文）：有效记忆只剩新名字
    heads = [r for r in p.rows if r["valid_to"] is None and r["event_type"] != "delete"]
    assert [r["content"] for r in heads] == ["用户名字：小红"]


def test_recall_latest_slot_wins(monkeypatch):
    """② 同槽位多条命中只留最新（id 最大）——旧名不再随机赢。"""
    s = _make_store(monkeypatch)

    async def _run():
        await s.write(user_id=1, content="用户名字：旧名1073", memory_type="profile",
                      topic="preferences", importance=5)
        await s.write(user_id=1, content="用户名字：新名5956", memory_type="profile",
                      topic="preferences", importance=5)
        return await s.recall(user_id=1, query="我叫什么名字", top_k=3)

    rows = asyncio.run(_run())
    contents = [r["content"] for r in rows]
    assert "用户名字：新名5956" in contents
    assert "用户名字：旧名1073" not in contents, f"旧名混入召回：{contents}"


def test_sync_extract_writes_name(monkeypatch):
    """③ sync_extract_and_write：done 帧前同步落库（5 秒验收的机制基础）。"""
    from app.ai.memory import service as mem_service

    s = _make_store(monkeypatch)

    async def _fake_store():
        return s

    monkeypatch.setattr(mem_service, "get_memory_store", _fake_store)

    async def _run():
        return await mem_service.sync_extract_and_write(1, query="我叫演示员001，请记住我的名字")

    written = asyncio.run(_run())
    assert any("演示员001" in c for c in written), f"同步抽取未捕获姓名：{written}"
    heads = [r for r in s._persistence.rows if r["valid_to"] is None and r["event_type"] != "delete"]
    assert any("演示员001" in r["content"] for r in heads), "同步抽取未落库"


def test_sync_extract_disabled_flag(monkeypatch):
    """④ MEMORY_SYNC_EXTRACT_ENABLED=False 时直通空列表（可配置降级）。"""
    from app.ai.memory import service as mem_service
    from app.config import settings

    monkeypatch.setattr(settings, "MEMORY_SYNC_EXTRACT_ENABLED", False, raising=False)

    async def _run():
        return await mem_service.sync_extract_and_write(1, query="我叫演示员002")

    assert asyncio.run(_run()) == []
