"""三层记忆 - 持久化层（task25 R7）。

对外只暴露统一 `MemoryPersistence` 接口，工厂 `build_persistence()` 按环境选择：

- `SqlMemoryPersistence`：真实 MySQL（user_memory 表），生产/验证用。字段与
  `项目文档/patch_memory_tables.sql` 逐列对齐。
- `MemMemoryPersistence`：in-process dict（测试/降级），保证无 MySQL 时链路可运行。

调用方经 MemoryStore 使用，不直接感知具体 backend。
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from loguru import logger

from app.ai.memory.schemas import UserMemory


class MemoryPersistence(ABC):
    """持久化抽象（记忆的增/查/更新访问痕迹/软删/计数/遍历）。"""

    @abstractmethod
    async def insert(
        self, *, user_id: int, memory_type: str, topic: str, content: str,
        importance: int, score: float,
    ) -> int: ...

    @abstractmethod
    async def fetch_by_ids(self, memory_ids: list[int]) -> list[UserMemory]: ...

    @abstractmethod
    async def list_effective(
        self, user_id: int, *, limit: int | None = None,
    ) -> list[UserMemory]: ...

    @abstractmethod
    async def count_effective(self, user_id: int) -> int: ...

    @abstractmethod
    async def touch(self, memory_id: int, *, access_count: int, score: float,
                    last_access_at: datetime) -> None: ...

    @abstractmethod
    async def soft_delete_ids(self, memory_ids: list[int]) -> int: ...


# ---------------------------------------------------------------------------
# SQL 实现（真实 MySQL）
# ---------------------------------------------------------------------------
_SQL_FIELDS = (
    "id, user_id, memory_type, topic, content, importance, score, "
    "access_count, deleted, created_at, last_access_at, updated_at"
)


class SqlMemoryPersistence(MemoryPersistence):
    """MySQL 持久化：所有操作走 app.database 的 execute_write/fetch_all。

    SQL 字段与 `项目文档/patch_memory_tables.sql` 逐列对齐，禁止表字段漂移。
    """

    def __init__(self, db: Any = None) -> None:
        self._db = db  # 惰性取 app.database 单例（避免 import 顺序问题）

    @property
    def db(self):
        if self._db is None:
            from app import database as _db  # 延迟 import，避免循环
            self._db = _db
        return self._db

    async def insert(self, *, user_id: int, memory_type: str, topic: str,
                     content: str, importance: int, score: float) -> int:
        now = datetime.now()
        sql = """
            INSERT INTO user_memory
            (user_id, memory_type, topic, content, importance, score,
             access_count, deleted, created_at, last_access_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s, 0, 0, %s, NULL, %s)
        """
        return int(
            await self.db.execute_write(
                sql,
                (int(user_id), memory_type, topic, content, int(importance),
                 float(score), now, now),
            )
        )

    async def fetch_by_ids(self, memory_ids: list[int]) -> list[UserMemory]:
        if not memory_ids:
            return []
        fmt = ",".join(["%s"] * len(memory_ids))
        rows = await self.db.fetch_all(
            f"SELECT {_SQL_FIELDS} FROM user_memory "
            f"WHERE id IN ({fmt}) AND deleted = 0",
            tuple(int(i) for i in memory_ids),
        )
        return [UserMemory.from_row(r) for r in rows]

    async def list_effective(self, user_id: int, *, limit: int | None = None) -> list[UserMemory]:
        sql = f"SELECT {_SQL_FIELDS} FROM user_memory WHERE user_id = %s AND deleted = 0"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = await self.db.fetch_all(sql, (int(user_id),))
        return [UserMemory.from_row(r) for r in rows]

    async def count_effective(self, user_id: int) -> int:
        row = await self.db.fetch_one(
            "SELECT COUNT(*) AS c FROM user_memory WHERE user_id = %s AND deleted = 0",
            (int(user_id),),
        )
        return int(row["c"] or 0) if row else 0

    async def touch(self, memory_id: int, *, access_count: int, score: float,
                    last_access_at: datetime) -> None:
        await self.db.execute_write(
            "UPDATE user_memory SET access_count = %s, score = %s, "
            "last_access_at = %s, updated_at = %s WHERE id = %s AND deleted = 0",
            (int(access_count), float(score), last_access_at, datetime.now(), int(memory_id)),
        )

    async def soft_delete_ids(self, memory_ids: list[int]) -> int:
        if not memory_ids:
            return 0
        fmt = ",".join(["%s"] * len(memory_ids))
        return int(
            await self.db.execute_write(
                f"UPDATE user_memory SET deleted = 1, updated_at = %s WHERE id IN ({fmt}) AND deleted = 0",
                (datetime.now(), *tuple(int(i) for i in memory_ids)),
            )
        )


# ---------------------------------------------------------------------------
# 内存实现（测试 / 无 MySQL 降级）
# ---------------------------------------------------------------------------
class MemMemoryPersistence(MemoryPersistence):
    """进程内 dict 持久化（保持 UserMemory 语义，供单测与降级路径）。"""

    def __init__(self) -> None:
        self._rows: dict[int, dict[str, Any]] = {}
        self._seq = 0
        self._lock = asyncio.Lock()

    def _to_um(self, row: dict[str, Any]) -> UserMemory:
        return UserMemory.from_row(row)

    async def insert(self, *, user_id: int, memory_type: str, topic: str,
                     content: str, importance: int, score: float) -> int:
        async with self._lock:
            self._seq += 1
            now = datetime.now()
            self._rows[self._seq] = {
                "id": self._seq, "user_id": int(user_id), "memory_type": memory_type,
                "topic": topic, "content": content, "importance": int(importance),
                "score": float(score), "access_count": 0, "deleted": 0,
                "created_at": now, "last_access_at": None, "updated_at": now,
            }
            return self._seq

    async def fetch_by_ids(self, memory_ids: list[int]) -> list[UserMemory]:
        async with self._lock:
            return [self._to_um(self._rows[i]) for i in memory_ids if i in self._rows and not self._rows[i]["deleted"]]

    async def list_effective(self, user_id: int, *, limit: int | None = None) -> list[UserMemory]:
        async with self._lock:
            rows = [r for r in self._rows.values() if r["user_id"] == int(user_id) and not r["deleted"]]
            if limit:
                rows = rows[: int(limit)]
            return [self._to_um(r) for r in rows]

    async def count_effective(self, user_id: int) -> int:
        async with self._lock:
            return sum(1 for r in self._rows.values() if r["user_id"] == int(user_id) and not r["deleted"])

    async def touch(self, memory_id: int, *, access_count: int, score: float,
                    last_access_at: datetime) -> None:
        async with self._lock:
            r = self._rows.get(int(memory_id))
            if r and not r["deleted"]:
                r["access_count"] = int(access_count)
                r["score"] = float(score)
                r["last_access_at"] = last_access_at
                r["updated_at"] = datetime.now()

    async def soft_delete_ids(self, memory_ids: list[int]) -> int:
        deleted = 0
        async with self._lock:
            for i in memory_ids:
                r = self._rows.get(int(i))
                if r and not r["deleted"]:
                    r["deleted"] = 1
                    r["updated_at"] = datetime.now()
                    deleted += 1
        return deleted


def build_persistence(db: Any = None) -> MemoryPersistence:
    """持久化工厂：默认 SQL（真实 MySQL，依赖 app.database 已 init）；测试传 MemMemoryPersistence。

    task-M1：当 settings.MEMORY_EVENT_ENABLED=True（默认）时返回事件溯源实现
    `SqlEventMemoryPersistence`（user_memory_event 为事实源）；否则回退旧快照实现。
    """
    if db is not None:
        return db
    from app import database as _db
    from app.config import settings

    if getattr(settings, "MEMORY_EVENT_ENABLED", True):
        from app.ai.memory.event_persistence import SqlEventMemoryPersistence

        return SqlEventMemoryPersistence(_db)
    return SqlMemoryPersistence(_db)