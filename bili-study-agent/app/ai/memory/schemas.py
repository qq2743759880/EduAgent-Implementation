"""三层记忆 - 数据结构与枚举（task25 R7）。

纯数据契约，零外部依赖，可安全被 `__init__` 导入（不触发 Milvus/engine 等重型初始化）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# memory_type 合法枚举（对齐 DDL COMMENT / 前端契约）
MEMORY_TYPES = ("preference", "goal", "profile", "correction", "fact")

# 默认 topic 分组（用于 MEMORY.md 索引聚合 / 分类检索）
MEMORY_TOPICS = ("learning-goals", "preferences", "profile", "corrections", "general")


@dataclass
class MemoryCandidate:
    """从一轮对话/会话中提取出的「待写入长时记忆」候选。

    importance∈[1,5]；只有 importance ≥ settings.MEMORY_IMPORTANCE_THRESHOLD 才写长时记忆
    （对齐「用户修正/明确偏好这类高价值信号才值得占用长时记忆容量」）。
    触发来源 source：explicit（用户明确要求记住）/ preference（明确偏好）/ correction（纠正）/
    goal（目标）/ session_end（会话结束补充，R7）。
    """
    content: str
    memory_type: str = "preference"
    topic: str = "general"
    importance: int = 4
    source: str = "session_end"
    source_user_id: int | None = None


@dataclass
class UserMemory:
    """长时记忆记录（映射 user_memory 一行）。"""
    id: int
    user_id: int
    memory_type: str = "preference"
    topic: str = "general"
    content: str = ""
    importance: int = 3
    score: float = 0.0
    access_count: int = 0
    deleted: int = 0
    created_at: datetime | str | None = None
    last_access_at: datetime | str | None = None
    updated_at: datetime | str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "UserMemory":
        def _v(r: dict[str, Any], k: str):
            v = r.get(k)
            return v if v is not None else None
        return cls(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            memory_type=_v(row, "memory_type") or "preference",
            topic=_v(row, "topic") or "general",
            content=row.get("content") or "",
            importance=int(row.get("importance") or 3),
            score=float(row.get("score") or 0.0),
            access_count=int(row.get("access_count") or 0),
            deleted=int(row.get("deleted") or 0),
            created_at=_v(row, "created_at"),
            last_access_at=_v(row, "last_access_at"),
            updated_at=_v(row, "updated_at"),
        )

    def to_recall_dict(self) -> dict[str, Any]:
        """召回结果载荷（进子代理/plan prompt 的最小可读结构）。"""
        return {
            "memory_type": self.memory_type,
            "topic": self.topic,
            "content": self.content,
            "importance": self.importance,
            "score": round(self.score, 4),
            "access_count": self.access_count,
            "created_at": str(self.created_at) if self.created_at else None,
            "last_access_at": str(self.last_access_at) if self.last_access_at else None,
        }


def now_utc() -> datetime:
    """统一时间源：datetime.now（进程本地，供计算天数差；与 DB DATETIME 语义一致）。"""
    return datetime.now()