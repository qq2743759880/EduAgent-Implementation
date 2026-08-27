"""记忆事件溯源持久化层（task-M1：production-upgrade-plan P1）。

设计要点（对齐 CortexDB / ChronoMem / Ninad Pathak）：
- `user_memory_event` 为长时记忆「唯一事实源」，append-only，绝不 UPDATE 内容。
- 写 = INSERT 新行；更新/删除 = 新行 + 旧行 `valid_to` 盖章（单条 UPDATE **仅用于版本盖章**）。
- 每个 `entity_id` 恒有且仅有一条 `valid_to IS NULL` 的行 = 当前 HEAD。
- 检索强制 `valid_to IS NULL AND event_type <> 'delete'`，保证绝不召回废弃版本。
- `trace_id` 每条非 consolidate 事件必填（自动生成兜底），指向触发它的 LLM/工具调用（审计自证）。
- 向量主键 = `entity_id`（跨版本稳定）；版本变更同步 re-upsert 向量。

两个实现：
- `SqlEventMemoryPersistence`：生产 MySQL（app.database 单例，建表幂等）。
- `MemEventMemoryPersistence`：in-process（测试/降级，无外部依赖）。
两者语义完全一致，契约测试用 Mem 变体（全 in-process，零外部依赖）。
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any

from loguru import logger

from app.ai.memory.schemas import UserMemory

_DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS user_memory_event (
        id            BIGINT          NOT NULL AUTO_INCREMENT,
        event_type    VARCHAR(32)     NOT NULL,
        entity_id     BIGINT          NOT NULL,
        user_id       BIGINT          NOT NULL,
        memory_type   VARCHAR(32)     NULL,
        topic         VARCHAR(64)     NULL,
        content       TEXT            NOT NULL,
        embedding     JSON            NULL,
        importance    INT             NULL,
        score         FLOAT           NULL,
        access_count  INT             NOT NULL DEFAULT 0,
        last_access_at DATETIME       NULL,
        valid_from    DATETIME        NOT NULL,
        valid_to      DATETIME        NULL,
        trace_id      VARCHAR(64)     NULL,
        operator      VARCHAR(64)     NULL,
        supports      JSON            NULL,
        created_at    DATETIME        NOT NULL,
        INDEX idx_event_user   (user_id, entity_id, valid_to),
        INDEX idx_event_trace  (trace_id),
        INDEX idx_event_entity (entity_id, valid_to),
        PRIMARY KEY (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS user_memory_entity_seq (
        id BIGINT NOT NULL AUTO_INCREMENT,
        PRIMARY KEY (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]

# 模块级幂等建表守卫（每进程一次）
_EVENT_TABLES_LOCK = asyncio.Lock()
_EVENT_TABLES_READY = False

# 当前有效记忆查询（HEAD = 唯一 valid_to IS NULL 且非 delete 行）
_HEAD_WHERE = "valid_to IS NULL AND event_type <> 'delete'"
_FIELDS = (
    "id, entity_id, user_id, memory_type, topic, content, importance, score, "
    "access_count, last_access_at, valid_from, valid_to, event_type, operator, trace_id, created_at"
)


def _trace(trace_id: str | None) -> str:
    """非 consolidate 事件必须有 trace_id（审计溯源）；缺省自动生成。"""
    if trace_id:
        return str(trace_id)
    return f"mem-{uuid.uuid4().hex[:16]}"


def _json_dumps(value: Any) -> Any:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def _json_loads(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


def _row_to_user_memory(row: dict[str, Any]) -> UserMemory:
    """事件行 → UserMemory（id 用 entity_id，作为跨版本稳定身份）。"""
    return UserMemory(
        id=int(row["entity_id"]),
        user_id=int(row["user_id"]),
        memory_type=row.get("memory_type") or "preference",
        topic=row.get("topic") or "general",
        content=row.get("content") or "",
        importance=int(row.get("importance") or 3),
        score=float(row.get("score") or 0.0),
        access_count=int(row.get("access_count") or 0),
        deleted=0,
        created_at=row.get("valid_from"),
        last_access_at=row.get("last_access_at"),
        updated_at=row.get("created_at"),
    )


def _fmt_in(ids: list[int]) -> tuple[str, tuple]:
    placeholders = ",".join(["%s"] * len(ids))
    return f"({placeholders})", tuple(int(i) for i in ids)


class EventMemoryPersistenceBase:
    """事件溯源持久化的共享契约（不依赖具体存储）。"""

    async def insert(self, *, user_id: int, memory_type: str, topic: str,
                     content: str, importance: int, score: float) -> int:
        raise NotImplementedError

    async def fetch_by_ids(self, memory_ids: list[int]) -> list[UserMemory]:
        raise NotImplementedError

    async def list_effective(self, user_id: int, *, limit: int | None = None) -> list[UserMemory]:
        raise NotImplementedError

    async def count_effective(self, user_id: int) -> int:
        raise NotImplementedError

    async def fetch_entity(self, entity_id: int) -> UserMemory | None:
        raise NotImplementedError

    async def touch(self, memory_id: int, *, access_count: int, score: float,
                    last_access_at: datetime) -> None:
        raise NotImplementedError

    async def soft_delete_ids(self, memory_ids: list[int]) -> int:
        raise NotImplementedError

    # —— 事件源语（task-M1 新增）——
    async def update_memory(self, entity_id: int, *, content: str,
                            memory_type: str | None = None, topic: str | None = None,
                            importance: int | None = None, score: float | None = None,
                            operator: str = "user", trace_id: str | None = None) -> int:
        raise NotImplementedError

    async def rewind(self, entity_id: int, target_event_id: int, *,
                     operator: str = "user", trace_id: str | None = None) -> int:
        raise NotImplementedError

    async def invalidate(self, entity_id: int, *, operator: str = "user",
                         trace_id: str | None = None) -> None:
        raise NotImplementedError

    async def consolidate(self, source_entity_ids: list[int], *, user_id: int,
                          summary_content: str, memory_type: str = "profile", topic: str = "general",
                          importance: int = 4, score: float | None = None,
                          operator: str = "dream", trace_id: str | None = None,
                          supports: list[int] | None = None) -> int:
        raise NotImplementedError

    async def history(self, entity_id: int, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        raise NotImplementedError


# ===========================================================================
# SQL 实现（生产 MySQL）
# ===========================================================================
class SqlEventMemoryPersistence(EventMemoryPersistenceBase):
    def __init__(self, db: Any = None) -> None:
        self._db = db  # 惰性取 app.database 单例（避免 import 顺序问题）

    @property
    def db(self):
        if self._db is None:
            from app import database as _db
            self._db = _db
        return self._db

    async def _ensure(self) -> None:
        global _EVENT_TABLES_READY
        async with _EVENT_TABLES_LOCK:
            if _EVENT_TABLES_READY:
                return
            for stmt in _DDL_STATEMENTS:
                try:
                    await self.db.execute_write(stmt)
                except Exception as exc:  # 幂等建表失败可重试（表可能已存在）
                    logger.warning(f"[EventMem] ensure DDL 跳过/重试: {type(exc).__name__}: {exc}")
            _EVENT_TABLES_READY = True

    async def _next_entity_id(self) -> int:
        return int(await self.db.execute_write("INSERT INTO user_memory_entity_seq () VALUES ()"))

    async def insert(self, *, user_id: int, memory_type: str, topic: str,
                     content: str, importance: int, score: float) -> int:
        await self._ensure()
        entity_id = await self._next_entity_id()
        now = datetime.now()
        await self.db.execute_write(
            f"INSERT INTO user_memory_event "
            f"(event_type, entity_id, user_id, memory_type, topic, content, importance, score, "
            f" valid_from, valid_to, operator, trace_id, created_at) "
            f"VALUES ('create', %s, %s, %s, %s, %s, %s, %s, %s, NULL, 'system', %s, %s)",
            (entity_id, int(user_id), memory_type[:32], topic[:64], content[:2000],
             int(importance), float(score), now, _trace(None), now),
        )
        return entity_id

    async def _head_rows(self, where: str, args: tuple, *, limit: int | None = None) -> list[dict]:
        sql = f"SELECT {_FIELDS} FROM user_memory_event WHERE {where}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return await self.db.fetch_all(sql, args)

    async def fetch_by_ids(self, memory_ids: list[int]) -> list[UserMemory]:
        if not memory_ids:
            return []
        await self._ensure()
        fmt, args = _fmt_in(memory_ids)
        rows = await self._head_rows(f"entity_id IN {fmt} AND {_HEAD_WHERE}", args)
        return [_row_to_user_memory(r) for r in rows]

    async def fetch_entity(self, entity_id: int) -> UserMemory | None:
        await self._ensure()
        rows = await self._head_rows("entity_id = %s AND " + _HEAD_WHERE, (int(entity_id),), limit=1)
        return _row_to_user_memory(rows[0]) if rows else None

    async def list_effective(self, user_id: int, *, limit: int | None = None) -> list[UserMemory]:
        await self._ensure()
        rows = await self._head_rows("user_id = %s AND " + _HEAD_WHERE, (int(user_id),), limit=limit)
        return [_row_to_user_memory(r) for r in rows]

    async def count_effective(self, user_id: int) -> int:
        await self._ensure()
        row = await self.db.fetch_one(
            f"SELECT COUNT(*) AS c FROM user_memory_event WHERE user_id = %s AND {_HEAD_WHERE}",
            (int(user_id),),
        )
        return int(row["c"] or 0) if row else 0

    async def touch(self, memory_id: int, *, access_count: int, score: float,
                    last_access_at: datetime) -> None:
        await self._ensure()
        # 元数据更新（访问遥测，非记忆内容）—— 仅作用于当前 HEAD
        await self.db.execute_write(
            "UPDATE user_memory_event SET access_count = %s, score = %s, last_access_at = %s "
            "WHERE entity_id = %s AND valid_to IS NULL",
            (int(access_count), float(score), last_access_at, int(memory_id)),
        )

    async def _stamp_head(self, entity_id: int) -> None:
        """版本盖章：把当前 HEAD 置为废弃（唯一允许的 UPDATE）。"""
        await self.db.execute_write(
            "UPDATE user_memory_event SET valid_to = %s WHERE entity_id = %s AND valid_to IS NULL",
            (datetime.now(), int(entity_id)),
        )

    async def update_memory(self, entity_id: int, *, content: str,
                            memory_type: str | None = None, topic: str | None = None,
                            importance: int | None = None, score: float | None = None,
                            operator: str = "user", trace_id: str | None = None) -> int:
        await self._ensure()
        head = await self.fetch_entity(int(entity_id))
        if head is None:
            raise ValueError(f"entity_id={entity_id} 不存在或无有效 HEAD")
        mt = (memory_type or head.memory_type)[:32]
        tp = (topic or head.topic)[:64]
        imp = int(importance if importance is not None else head.importance)
        sc = float(score) if score is not None else head.score
        await self._stamp_head(int(entity_id))
        now = datetime.now()
        await self.db.execute_write(
            "INSERT INTO user_memory_event "
            "(event_type, entity_id, user_id, memory_type, topic, content, importance, score, "
            " valid_from, valid_to, operator, trace_id, created_at) "
            "VALUES ('update', %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s)",
            (int(entity_id), int(head.user_id), mt, tp, content[:2000], imp, sc,
             now, operator, _trace(trace_id), now),
        )
        return int(entity_id)

    async def rewind(self, entity_id: int, target_event_id: int, *,
                     operator: str = "user", trace_id: str | None = None) -> int:
        await self._ensure()
        target = await self.db.fetch_one(
            f"SELECT {_FIELDS} FROM user_memory_event WHERE id = %s AND entity_id = %s",
            (int(target_event_id), int(entity_id)),
        )
        if target is None:
            raise ValueError(f"target_event_id={target_event_id} 不属于 entity_id={entity_id}")
        await self._stamp_head(int(entity_id))
        now = datetime.now()
        await self.db.execute_write(
            "INSERT INTO user_memory_event "
            "(event_type, entity_id, user_id, memory_type, topic, content, importance, score, "
            " valid_from, valid_to, operator, trace_id, created_at) "
            "VALUES ('rewind', %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s)",
            (int(entity_id), int(target["user_id"]), target.get("memory_type") or "preference",
             target.get("topic") or "general", (target.get("content") or "")[:2000],
             int(target.get("importance") or 3), float(target.get("score") or 0.0),
             now, operator, _trace(trace_id), now),
        )
        return int(entity_id)

    async def invalidate(self, entity_id: int, *, operator: str = "user",
                         trace_id: str | None = None) -> None:
        await self._ensure()
        head = await self.fetch_entity(int(entity_id))
        if head is None:
            return
        await self._stamp_head(int(entity_id))
        now = datetime.now()
        await self.db.execute_write(
            "INSERT INTO user_memory_event "
            "(event_type, entity_id, user_id, memory_type, topic, content, importance, score, "
            " valid_from, valid_to, operator, trace_id, created_at) "
            "VALUES ('delete', %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s)",
            (int(entity_id), int(head.user_id), head.memory_type[:32], head.topic[:64],
             "", head.importance, head.score, now, operator, _trace(trace_id), now),
        )

    async def consolidate(self, source_entity_ids: list[int], *, user_id: int,
                          summary_content: str, memory_type: str = "profile", topic: str = "general",
                          importance: int = 4, score: float | None = None,
                          operator: str = "dream", trace_id: str | None = None,
                          supports: list[int] | None = None) -> int:
        await self._ensure()
        entity_id = await self._next_entity_id()
        now = datetime.now()
        # 源实体 HEAD 全部盖章废弃，并记录被合并的「事件 id」（supports 引用原事件，对齐 CortexDB）
        src_event_ids: list[int] = []
        for src in source_entity_ids:
            head = await self.db.fetch_one(
                "SELECT id FROM user_memory_event WHERE entity_id = %s AND valid_to IS NULL", (int(src),)
            )
            if head:
                src_event_ids.append(int(head["id"]))
            await self._stamp_head(int(src))
        supports_ids = supports if supports is not None else src_event_ids
        await self.db.execute_write(
            "INSERT INTO user_memory_event "
            "(event_type, entity_id, user_id, memory_type, topic, content, importance, score, "
            " valid_from, valid_to, operator, trace_id, supports, created_at) "
            "VALUES ('consolidate', %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s)",
            (entity_id, int(user_id), memory_type[:32], topic[:64], summary_content[:4000], int(importance),
             float(score if score is not None else 0.0), now, operator, _trace(trace_id),
             _json_dumps(supports_ids), now),
        )
        return entity_id

    async def soft_delete_ids(self, memory_ids: list[int]) -> int:
        if not memory_ids:
            return 0
        n = 0
        for eid in memory_ids:
            try:
                await self.invalidate(int(eid))
                n += 1
            except Exception as exc:
                logger.warning(f"[EventMem] soft_delete entity={eid} 失败: {exc}")
        return n

    async def history(self, entity_id: int, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        await self._ensure()
        rows = await self.db.fetch_all(
            f"SELECT {_FIELDS} FROM user_memory_event WHERE entity_id = %s "
            f"ORDER BY id DESC LIMIT %s OFFSET %s",
            (int(entity_id), int(limit), int(offset)),
        )
        out = []
        for r in rows:
            out.append({
                "event_id": int(r["id"]),
                "event_type": r.get("event_type"),
                "entity_id": int(r["entity_id"]),
                "memory_type": r.get("memory_type"),
                "topic": r.get("topic"),
                "content": r.get("content"),
                "importance": r.get("importance"),
                "operator": r.get("operator"),
                "trace_id": r.get("trace_id"),
                "valid_from": str(r.get("valid_from")) if r.get("valid_from") else None,
                "valid_to": str(r.get("valid_to")) if r.get("valid_to") else None,
                "supports": _json_loads(r.get("supports")),
                "created_at": str(r.get("created_at")) if r.get("created_at") else None,
            })
        return out


# ===========================================================================
# 内存实现（测试 / 无 MySQL 降级）—— 语义与 SQL 完全一致
# ===========================================================================
class MemEventMemoryPersistence(EventMemoryPersistenceBase):
    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []   # append-only 事件流
        self._seq = 0                              # 事件 id 自增
        self._entity_seq = 0                       # entity_id 分配器
        self._lock = asyncio.Lock()

    def _new_event_id(self) -> int:
        self._seq += 1
        return self._seq

    def _new_entity_id(self) -> int:
        self._entity_seq += 1
        return self._entity_seq

    def _now(self) -> datetime:
        return datetime.now()

    def _head(self, entity_id: int) -> dict | None:
        cur = None
        for e in self._events:
            if e["entity_id"] == int(entity_id) and e["valid_to"] is None:
                if cur is None or e["id"] > cur["id"]:
                    cur = e
        return cur

    async def insert(self, *, user_id: int, memory_type: str, topic: str,
                     content: str, importance: int, score: float) -> int:
        async with self._lock:
            entity_id = self._new_entity_id()
            now = self._now()
            self._events.append({
                "id": self._new_event_id(), "event_type": "create", "entity_id": entity_id,
                "user_id": int(user_id), "memory_type": memory_type[:32], "topic": topic[:64],
                "content": content[:2000], "embedding": None, "importance": int(importance),
                "score": float(score), "access_count": 0, "last_access_at": None,
                "valid_from": now, "valid_to": None, "trace_id": _trace(None),
                "operator": "system", "supports": None, "created_at": now,
            })
            return entity_id

    async def fetch_by_ids(self, memory_ids: list[int]) -> list[UserMemory]:
        out = []
        for eid in memory_ids:
            h = self._head(int(eid))
            if h and h["event_type"] != "delete":
                out.append(_row_to_user_memory(h))
        return out

    async def fetch_entity(self, entity_id: int) -> UserMemory | None:
        h = self._head(int(entity_id))
        if h and h["event_type"] != "delete":
            return _row_to_user_memory(h)
        return None

    async def list_effective(self, user_id: int, *, limit: int | None = None) -> list[UserMemory]:
        seen: dict[int, dict] = {}
        for e in self._events:
            if e["user_id"] != int(user_id):
                continue
            if e["valid_to"] is not None or e["event_type"] == "delete":
                continue
            seen[e["entity_id"]] = e  # 同一 entity 仅保留最新 HEAD（事件流有序追加）
        rows = list(seen.values())
        if limit:
            rows = rows[: int(limit)]
        return [_row_to_user_memory(r) for r in rows]

    async def count_effective(self, user_id: int) -> int:
        return len(await self.list_effective(int(user_id)))

    async def touch(self, memory_id: int, *, access_count: int, score: float,
                    last_access_at: datetime) -> None:
        h = self._head(int(memory_id))
        if h:
            h["access_count"] = int(access_count)
            h["score"] = float(score)
            h["last_access_at"] = last_access_at

    async def update_memory(self, entity_id: int, *, content: str,
                            memory_type: str | None = None, topic: str | None = None,
                            importance: int | None = None, score: float | None = None,
                            operator: str = "user", trace_id: str | None = None) -> int:
        async with self._lock:
            head = self._head(int(entity_id))
            if head is None:
                raise ValueError(f"entity_id={entity_id} 不存在或无有效 HEAD")
            head["valid_to"] = self._now()
            now = self._now()
            self._events.append({
                "id": self._new_event_id(), "event_type": "update", "entity_id": int(entity_id),
                "user_id": head["user_id"], "memory_type": (memory_type or head["memory_type"])[:32],
                "topic": (topic or head["topic"])[:64], "content": content[:2000],
                "embedding": None, "importance": int(importance if importance is not None else head["importance"]),
                "score": float(score if score is not None else head["score"]),
                "access_count": head["access_count"], "last_access_at": head["last_access_at"],
                "valid_from": now, "valid_to": None, "trace_id": _trace(trace_id),
                "operator": operator, "supports": None, "created_at": now,
            })
            return int(entity_id)

    async def rewind(self, entity_id: int, target_event_id: int, *,
                     operator: str = "user", trace_id: str | None = None) -> int:
        async with self._lock:
            target = next((e for e in self._events
                           if e["id"] == int(target_event_id) and e["entity_id"] == int(entity_id)), None)
            if target is None:
                raise ValueError(f"target_event_id={target_event_id} 不属于 entity_id={entity_id}")
            head = self._head(int(entity_id))
            if head:
                head["valid_to"] = self._now()
            now = self._now()
            self._events.append({
                "id": self._new_event_id(), "event_type": "rewind", "entity_id": int(entity_id),
                "user_id": target["user_id"], "memory_type": target["memory_type"],
                "topic": target["topic"], "content": target["content"][:2000],
                "embedding": None, "importance": target["importance"], "score": target["score"],
                "access_count": 0, "last_access_at": None,
                "valid_from": now, "valid_to": None, "trace_id": _trace(trace_id),
                "operator": operator, "supports": None, "created_at": now,
            })
            return int(entity_id)

    async def invalidate(self, entity_id: int, *, operator: str = "user",
                         trace_id: str | None = None) -> None:
        async with self._lock:
            head = self._head(int(entity_id))
            if head is None:
                return
            head["valid_to"] = self._now()
            now = self._now()
            self._events.append({
                "id": self._new_event_id(), "event_type": "delete", "entity_id": int(entity_id),
                "user_id": head["user_id"], "memory_type": head["memory_type"], "topic": head["topic"],
                "content": "", "embedding": None, "importance": head["importance"], "score": head["score"],
                "access_count": head["access_count"], "last_access_at": head["last_access_at"],
                "valid_from": now, "valid_to": None, "trace_id": _trace(trace_id),
                "operator": operator, "supports": None, "created_at": now,
            })

    async def consolidate(self, source_entity_ids: list[int], *, user_id: int,
                          summary_content: str, memory_type: str = "profile", topic: str = "general",
                          importance: int = 4, score: float | None = None,
                          operator: str = "dream", trace_id: str | None = None,
                          supports: list[int] | None = None) -> int:
        async with self._lock:
            entity_id = self._new_entity_id()
            src_event_ids: list[int] = []
            for src in source_entity_ids:
                h = self._head(int(src))
                if h:
                    src_event_ids.append(h["id"])
                    h["valid_to"] = self._now()
            supports_ids = supports if supports is not None else src_event_ids
            now = self._now()
            self._events.append({
                "id": self._new_event_id(), "event_type": "consolidate", "entity_id": entity_id,
                "user_id": int(user_id), "memory_type": memory_type[:32], "topic": topic[:64],
                "content": summary_content[:4000], "embedding": None, "importance": int(importance),
                "score": float(score if score is not None else 0.0), "access_count": 0,
                "last_access_at": None, "valid_from": now, "valid_to": None,
                "trace_id": _trace(trace_id), "operator": operator,
                "supports": list(supports_ids), "created_at": now,
            })
            return entity_id

    async def soft_delete_ids(self, memory_ids: list[int]) -> int:
        n = 0
        for eid in memory_ids:
            try:
                await self.invalidate(int(eid))
                n += 1
            except Exception:
                pass
        return n

    async def history(self, entity_id: int, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        rows = [e for e in self._events if e["entity_id"] == int(entity_id)]
        rows.sort(key=lambda r: r["id"], reverse=True)
        rows = rows[int(offset): int(offset) + int(limit)]
        return [
            {
                "event_id": e["id"], "event_type": e["event_type"], "entity_id": e["entity_id"],
                "memory_type": e["memory_type"], "topic": e["topic"], "content": e["content"],
                "importance": e["importance"], "operator": e["operator"], "trace_id": e["trace_id"],
                "valid_from": str(e["valid_from"]), "valid_to": str(e["valid_to"]) if e["valid_to"] else None,
                "supports": e["supports"], "created_at": str(e["created_at"]),
            }
            for e in rows
        ]
