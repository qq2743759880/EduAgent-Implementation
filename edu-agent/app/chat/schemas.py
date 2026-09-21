"""
P2 问答 Schemas：会话/消息/RAG 请求与响应/SSE 事件。

原则：
- 数据库返回体（ChatSession / ChatMessage）字段与 SQL DDL 一一对应
- RAG 相关字段尽量通用，避免把 Milvus 细节暴露给前端（RetrievedDoc 只含业务语义字段：score/chunk/source/series 等）
- 流式输出定义为 SSE 事件枚举 + TypedDict，方便 router 转成 EventSourceResponse
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, TypedDict

from pydantic import BaseModel, Field


# ============================================================
# 1. 会话 / 消息 持久化对象（与 chat_session / chat_message 表一一对应）
# ============================================================
class ChatSession(BaseModel):
    """会话元数据（一个用户可同时拥有多个会话）。"""
    session_id: str = Field(..., description="会话唯一 ID，前端持久化用于继续对话")
    user_id: int = Field(..., description="所属用户 ID，RBAC 权限校验依据")
    title: str = Field(..., max_length=128, description="会话标题（默认取首条问题前 30 字）")
    visibility: Literal["private", "shared"] = Field("private", description="预留后续协作问答场景")
    message_count: int = Field(0, description="会话总消息数（含 user/assistant），可用作排序")
    last_message_at: datetime | None = Field(None, description="最后对话时间，用于会话列表排序")
    created_at: datetime
    updated_at: datetime
    yn: int = Field(1, description="逻辑删除：1 正常，0 删除")


class ChatSessionCreate(BaseModel):
    """创建会话请求体（全部可选）。"""
    title: str | None = Field(None, max_length=128, description="会话标题；空串/不传 = 用首条问题前 30 字自动生成")
    visibility: Literal["private", "shared"] = "private"


class DeleteSessionResponse(BaseModel):
    """删除会话响应（软删：UPDATE chat_session SET yn=0，禁止物理 DELETE）。"""
    ok: bool = True


class ChatMessage(BaseModel):
    """单轮消息（user 提问 / assistant 回答 成对落库）。"""
    message_id: str = Field(..., description="消息唯一 ID（前端可用来做局部更新/重试幂等）")
    session_id: str
    user_id: int
    role: Literal["user", "assistant", "system"]
    content: str = Field(..., description="原文内容（assistant：最终合并后的回答）")
    # --- RAG 侧补充字段（仅 assistant 有，其余为 None）---
    rag_query_rewrite: str | None = Field(None, max_length=1024, description="HyDE 改写/扩展后的查询（调试/审计）")
    rag_retrieved_count: int | None = Field(None, description="本次检索召回 doc 数量（断崖前）")
    rag_final_count: int | None = Field(None, description="重排+断崖后实际喂给 LLM 的 doc 数量")
    rag_docs_json: str | None = Field(None, description="RetrievedDoc 列表 JSON 序列化（便于前端点击引用）")
    rag_error: str | None = Field(None, max_length=1024, description="检索/生成降级错误（不影响返回，但用于审计）")
    latency_ms: int | None = Field(None, description="整轮耗时（毫秒），后续统计看板用")
    # --- P8 MCP 工具调用补充字段（仅 assistant 有，其余为 None）---
    mcp_tool_calls_json: str | None = Field(None, description="P8：本轮触发的 MCP 工具调用 [{call_id,tool_name,args_summary,status,latency_ms,result_summary}] JSON")
    mcp_called_count: int | None = Field(None, description="P8：本轮触发的 MCP 工具数量")
    created_at: datetime


# ============================================================
# 2. RAG 检索相关
# ============================================================
class RetrievedDoc(BaseModel):
    """检索结果文档（给前端展示/引用），屏蔽 Milvus/MySQL 实现细节。"""
    doc_id: str = Field(..., description="chunk_id，可用于后续高亮/跳回原文")
    score: float = Field(..., description="融合分数（0-1 左右，越大越相关）", ge=0.0)
    content: str = Field(..., description="chunk 正文")
    source_file: str | None = Field(None, description="源文件名")
    content_type: str | None = Field(None, description="内容类型：course/question/generic")
    series_code: str | None = Field(None, description="课程系列编码（前端可点回分级课）")
    series_name: str | None = Field(None)
    module_codes: list[str] = Field(default_factory=list, description="所属模块编码列表")
    keywords: list[str] = Field(default_factory=list, description="chunk 关键词，便于前端做 tag 展示")
    tenant_id: str | None = Field(None, description="租户信息（仅管理员界面会用到）")
    visibility: str | None = Field(None)
    source_channel: Literal["dense", "sparse", "bm25", "graph", "hybrid"] = Field(
        "hybrid",
        description="召回来源通道，调试用",
    )


class GraphEntity(BaseModel):
    """图谱命中实体（三通道之一：Neo4j 扩展上下文）。"""
    entity_type: Literal["Series", "Module", "Keyword", "Prerequisite"]
    entity_name: str
    related: list[str] = Field(default_factory=list, description="关联节点展示，前端 tag 渲染")
    hop: int = Field(1, ge=1, le=3, description="图扩展跳数")


# ============================================================
# 3. 请求体
# ============================================================
class _BaseRagRequest(BaseModel):
    """RAG 请求公共字段，chat/search 复用。"""
    query: str = Field(..., min_length=1, max_length=2000, description="用户提问")
    session_id: str | None = Field(
        None,
        description="可选；传入会自动关联会话并写入历史。不传 = 临时问答不落库",
    )
    use_hyde: bool = Field(True, description="是否启用 HyDE 假设答案扩展（LLM 失败会自动降级关闭）")
    top_k: int = Field(12, ge=1, le=100, description="召回上限（断崖前）")
    final_max_k: int = Field(5, ge=1, le=30, description="重排+断崖后送入 LLM 的最多 doc 数")
    cutoff_drop_ratio: float = Field(
        0.40,
        ge=0.0,
        le=0.99,
        description="断崖阈值：相邻分数跌幅 > ratio 即截断（默认 40%）",
    )
    enable_graph: bool = Field(True, description="是否启用 Neo4j 图谱通道（连不上自动跳过）")
    use_mcp_tools: bool = Field(True, description="P8：是否启用 MCP 工具调用（默认 True；False 时完全不触发工具）")


class RagQueryRequest(_BaseRagRequest):
    """问答请求（生成答案）。"""
    stream: bool = Field(False, description="是否流式；非流式 POST /chat 直接出最终回答")
    model: Literal["fast", "strong"] = Field(
        "fast",
        description="模型档位：fast=LLM_MODEL_FAST（默认）/strong=LLM_MODEL_STRONG（更贵更慢）",
    )
    include_history: int = Field(
        6,
        ge=0,
        le=40,
        description="会话内带入上下文历史轮数（每轮 user+assistant 算 2 条）",
    )


class RagSearchOnlyRequest(_BaseRagRequest):
    """仅检索（不生成答案）。"""
    format_docs: bool = Field(True, description="是否把 RetrievedDoc JSON 片段拼进返回值里；False 只返回元数据")


# ============================================================
# 4. 响应体
# ============================================================
class MCPToolCallSummary(BaseModel):
    """P8：返回给前端的工具调用摘要（不暴露详细敏感参数）。"""
    call_id: str = Field(..., description="对应 mcp_tool_call_log.call_id")
    tool_name: str
    args_summary: str = Field("", description="参数字典的前 200 字符摘要（保护隐私）")
    status: Literal["success", "error", "timeout"]
    latency_ms: int = 0
    result_summary: str = Field("", description="结果的前 400 字符摘要")


class RagAnswerResponse(BaseModel):
    """非流式问答响应：答案 + 引用 + 图谱扩展 + 耗时。"""
    session_id: str | None = Field(None, description="如果传了 session_id 或自动创建了会话则返回")
    message_id: str | None = Field(None, description="落库后 assistant 消息 ID，前端可点回看")
    answer: str = Field(..., description="最终回答")
    docs: list[RetrievedDoc] = Field(default_factory=list, description="喂给 LLM 的最终文档（断崖后）")
    graph_entities: list[GraphEntity] = Field(default_factory=list, description="图谱扩展实体")
    rewrite_query: str | None = Field(None, description="HyDE/改写后的查询（前端 debug 用）")
    retrieved_count: int
    final_count: int
    latency_ms: int
    degraded_reason: str | None = Field(
        None,
        description="降级提示：比如 Milvus/LLM 挂了，返回的是无检索兜底答案，让前端做 UI 提示",
    )
    # --- P8 MCP 工具调用 ---
    mcp_tool_calls: list[MCPToolCallSummary] = Field(
        default_factory=list,
        description="P8：本轮实际调用的工具摘要列表（空 = 未触发任何工具）",
    )
    # --- F-W1-GUARD（AUTO20 T7，C-W1-②）答案层写类回执机检护栏 ---
    tool_receipt_unverified: bool = Field(
        False,
        description="F-W1-GUARD：答案提及写类完成语义但无真实工具执行凭据 → True（答案尾部已追加诚实修正句）",
    )


# ============================================================
# 5. SSE 流式事件定义
# ============================================================
class SseEventType(str, Enum):
    START = "start"                 # 开始：返回会话/消息 ID
    RETRIEVAL_DONE = "retrieval"    # 检索完成：附带 docs / graph_entities（给前端提前渲染引用区）
    TOKEN = "token"                 # 增量 token：data=字符串增量
    DONE = "done"                   # 结束：附带最终汇总（final_count / latency_ms / degraded_reason）
    ERROR = "error"                 # 异常：非 200 级业务错误（如参数错），会关闭连接


class RagStreamEvent(TypedDict, total=False):
    """SSE 事件统一结构，序列化为 event: {event}\ndata: {json}\n\n"""
    event: str
    data: dict
