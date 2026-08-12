"""
P2 知识问答模块公共出口（供其他模块 `from app.chat import ...` 统一引用）。

设计约定：
- 对外暴露 Schemas 与 Service 方法，路由内部实现细节不对外暴露
- 后续接入管理端审计/P4推荐时，可继续从 service 扩展
"""
from app.chat.schemas import (
    ChatMessage,
    ChatSession,
    ChatSessionCreate,
    RetrievedDoc,
    GraphEntity,
    RagQueryRequest,
    RagSearchOnlyRequest,
    RagAnswerResponse,
    SseEventType,
    RagStreamEvent,
)
from app.chat.service import (
    create_session,
    list_sessions,
    get_session_history,
    chat_answer,
    chat_stream,
    search_only,
)

__all__ = [
    # schemas
    "ChatMessage",
    "ChatSession",
    "ChatSessionCreate",
    "RetrievedDoc",
    "GraphEntity",
    "RagQueryRequest",
    "RagSearchOnlyRequest",
    "RagAnswerResponse",
    "SseEventType",
    "RagStreamEvent",
    # service
    "create_session",
    "list_sessions",
    "get_session_history",
    "chat_answer",
    "chat_stream",
    "search_only",
]
