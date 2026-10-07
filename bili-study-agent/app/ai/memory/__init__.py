"""AI 助手三层记忆 + 遗忘机制（task25 R7）。

三层记忆模型（对齐 Anthropic Effective Context Engineering）：
- Working   = LangGraph state（当前推理上下文）
- Short-term = Redis session:{sid}:history + chat_message（会话历史）
- Long-term = MySQL user_memory（事实源）+ Milvus/in-memory 向量（vector recall 用户分区）

遗忘：score = importance×exp(-0.01·Δt_days) + recency_bonus（Ebbinghaus 指数衰减）；
score<0.1 软删，每用户超 MEMORY_CAPACITY_PER_USER 淘汰综合分最低者（高重要久未访问按时间衰减非误删）。

Milvus/外部 embedding 不可达时自动降级 in-process 内存向量（task 环境下 VM 192.168.85.101 可能不可达），
满足 vector recall 语义且链路恒可用。详细说明见各子模块 docstring。
"""
from app.ai.memory.schemas import MemoryCandidate, UserMemory
from app.ai.memory.score import (
    memory_score,
    recency_bonus,
    time_decay_factor,
)
from app.ai.memory.schemas import MEMORY_TYPES, MEMORY_TOPICS

# 仅 re-export 核心类型，避免 __init__ 触发重型 import（Milvus/engine 延迟加载）
__all__ = [
    "MemoryCandidate",
    "UserMemory",
    "memory_score",
    "recency_bonus",
    "time_decay_factor",
    "MEMORY_TYPES",
    "MEMORY_TOPICS",
]