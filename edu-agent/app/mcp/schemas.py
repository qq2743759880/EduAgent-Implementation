# -*- coding: utf-8 -*-
"""P8 MCP：Pydantic schemas。传输类型、请求 & 响应模型。"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator


# ---------- 枚举 ----------
class TransportEnum(str, Enum):
    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


class ToolCallStatusEnum(str, Enum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    SKIPPED = "SKIPPED"
    # task-T1 闭环新增：连续被拒达到上限后中断回合（对齐 Codex auto-review 3 连续拒绝熔断）
    REJECTION_LIMIT = "REJECTION_LIMIT"
    # task-T1 闭环新增：所有可用工具均失败/熔断后，输出结构化人工操作指南并停止
    MANUAL_GUIDE = "MANUAL_GUIDE"


# ---------- 分页公共 ----------
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _norm_page(page: int) -> int:
    return max(DEFAULT_PAGE, int(page or DEFAULT_PAGE))


def _norm_page_size(ps: int) -> int:
    ps = int(ps or DEFAULT_PAGE_SIZE)
    return max(1, min(MAX_PAGE_SIZE, ps))


# ============================================================
# 1. MCP Server 注册 & 列表
# ============================================================
class MCPServerBase(BaseModel):
    server_code: str = Field(..., min_length=2, max_length=64,
                             pattern=r"^[A-Za-z0-9_\-]+$",
                             description="服务器唯一编码，英文 URL-safe")
    display_name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = Field(default="", max_length=512)
    provider: Optional[str] = Field(default="self", max_length=64)
    transport: TransportEnum = Field(default=TransportEnum.STDIO)
    # stdio
    run_command: Optional[str] = Field(default=None, max_length=512)
    run_args: Optional[list[str]] = Field(default=None, description="子进程参数数组")
    working_dir: Optional[str] = Field(default=None, max_length=512)
    # sse / http
    base_url: Optional[str] = Field(default=None, max_length=512)
    http_headers: Optional[dict[str, str]] = Field(default=None)
    # 通用
    env: Optional[dict[str, str]] = Field(default=None, description="stdio 子进程环境变量；SSE 端留空")
    connect_timeout_ms: int = Field(default=5000, ge=100, le=600_000)
    call_timeout_ms: int = Field(default=30_000, ge=1000, le=3_600_000)
    enabled: int = Field(default=1, ge=0, le=1)

    @model_validator(mode="after")
    def _transport_required_fields(self):
        t = self.transport
        if t == TransportEnum.STDIO:
            if not self.run_command:
                raise HTTPException(status_code=422, detail="stdio 传输必须提供 run_command（如 python / npx）")
        elif t in (TransportEnum.SSE, TransportEnum.HTTP):
            if not self.base_url:
                raise HTTPException(status_code=422, detail=f"{t.value} 传输必须提供 base_url")
        return self


class MCPServerCreate(MCPServerBase):
    pass


class MCPServerUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = Field(default=None, max_length=512)
    provider: Optional[str] = Field(default=None, max_length=64)
    transport: Optional[TransportEnum] = None
    run_command: Optional[str] = Field(default=None, max_length=512)
    run_args: Optional[list[str]] = None
    working_dir: Optional[str] = Field(default=None, max_length=512)
    base_url: Optional[str] = Field(default=None, max_length=512)
    http_headers: Optional[dict[str, str]] = None
    env: Optional[dict[str, str]] = None
    connect_timeout_ms: Optional[int] = Field(default=None, ge=100, le=600_000)
    call_timeout_ms: Optional[int] = Field(default=None, ge=1000, le=3_600_000)
    enabled: Optional[int] = Field(default=None, ge=0, le=1)


class MCPServerItem(BaseModel):
    id: int
    server_code: str
    display_name: str
    description: str
    provider: str
    transport: str
    enabled: int
    yn: int
    created_by: int
    created_at: datetime
    updated_at: datetime
    # 健康检查结果（list 接口在内存中补充）
    last_health_at: Optional[datetime] = None
    last_health_ok: Optional[int] = None
    last_error: Optional[str] = None
    tool_count: int = 0

    @field_validator("created_at", "updated_at", "last_health_at", mode="before")
    @classmethod
    def _dt(cls, v: Any) -> Any:
        if isinstance(v, datetime) or v is None:
            return v
        try:
            return datetime.fromisoformat(str(v))
        except Exception:
            return v


class MCPServerDetail(MCPServerItem):
    run_command: Optional[str] = None
    run_args: Optional[list[str]] = None
    working_dir: Optional[str] = None
    base_url: Optional[str] = None
    http_headers: Optional[dict[str, str]] = None
    env: Optional[dict[str, str]] = None
    connect_timeout_ms: int = 0
    call_timeout_ms: int = 0


class MCPServerListResp(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[MCPServerItem]


# ============================================================
# 2. MCP Tool 列表
# ============================================================
class MCPToolItem(BaseModel):
    id: int
    server_id: int
    server_code: Optional[str] = None
    tool_name: str
    display_name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    category: str
    yn: int
    discovered_at: datetime
    # --- task33 描述体检字段（原 description 仅展示，重写结果放 description_rewritten）---
    description_rewritten: Optional[str] = None
    description_score: Optional[int] = None
    description_reviewed_at: Optional[datetime] = None

    @field_validator("discovered_at", mode="before")
    @classmethod
    def _dt(cls, v: Any) -> Any:
        if isinstance(v, datetime) or v is None:
            return v
        try:
            return datetime.fromisoformat(str(v))
        except Exception:
            return v


class MCPToolListResp(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[MCPToolItem]


# ============================================================
# 3. Tool 调用测试 & 结果
# ============================================================
class MCPToolTestReq(BaseModel):
    # 二选一：by tool_id（推荐）或 by (server_id, tool_name)
    tool_id: Optional[int] = None
    server_id: Optional[int] = None
    tool_name: Optional[str] = Field(default=None, max_length=128)
    args: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _at_least_one_ref(self):
        # 注意：不要抛 ValueError —— 其异常对象会进 422 handler 的 errors ctx 导致 json.dumps 崩溃（task04 #4）。
        # 直接抛 HTTPException，走全局 http_exception_handler，稳定返回 {code, message, detail}。
        if self.tool_id is None and not (self.server_id and self.tool_name):
            raise HTTPException(status_code=422, detail="必须提供 tool_id 或 (server_id, tool_name)")
        return self


class MCPToolTestResp(BaseModel):
    status: ToolCallStatusEnum
    result: Any = None               # 解析后的 result（成功时非 None）
    error_message: Optional[str] = None
    latency_ms: int = 0
    call_id: str
    server_id: int
    tool_name: str
    content_text: Optional[str] = None   # 原始 content text（MCP spec 里返回的 text 字段）
    # ---- task-T1 工具调用闭环扩展（均为可选，向后兼容旧调用方，AC5 回归安全）----
    attempt: int = 1                       # 闭环第几步（1 正常 / 2 换参 / 3 换工具 / 4 人工指南）
    actions: list[dict] = Field(default_factory=list)   # 每一步事件 {attempt,action,tool_name,args,outcome,latency_ms}
    manual_guide: Optional[dict] = None    # 第 4 步结构化人工操作指南（AC2）
    rejection_limited: bool = False        # 因会话连续被拒达上限而中断（AC3）


# ============================================================
# 4. 一键 import-url 请求
# ============================================================
class MCPImportUrlReq(BaseModel):
    url: str = Field(..., min_length=6, max_length=512,
                     description="公开可访问的 MCP 配置 JSON 或 SSE URL，本实现允许以 http(s):// 或 data://test-stdio 形式进行打靶")
    preset_name: Optional[str] = Field(default=None, max_length=128)
    skip_health_check: bool = False


class MCPImportResp(BaseModel):
    imported: bool
    server_id: Optional[int] = None
    server_code: str
    display_name: str
    transport: str
    discovered_tool_count: int = 0
    warning: Optional[str] = None


# ============================================================
# 5. 调用日志查询
# ============================================================
class MCPLogItem(BaseModel):
    id: int
    call_id: str
    server_id: int
    tool_name: str
    status: str
    latency_ms: int
    user_id: int
    trace_id: str
    error_message: Optional[str] = None
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _dt(cls, v: Any) -> Any:
        if isinstance(v, datetime) or v is None:
            return v
        try:
            return datetime.fromisoformat(str(v))
        except Exception:
            return v


class MCPLogDetail(MCPLogItem):
    """单条详情：返回 args_json / result_json / error_json 完整解析（列表项为省流量不传）。"""
    tenant_id: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    error_info: dict[str, Any] = Field(default_factory=dict)


class MCPLogListResp(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[MCPLogItem]


# ============================================================
# 6. MCP 管理端调试面板专用
# ============================================================
class MCPLiveToolItem(BaseModel):
    """live discover：直接从 Server tools/list 拿到，不经过 DB 落库"""
    tool_name: str
    display_name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    category: str = ""


class MCPLiveDiscoverResp(BaseModel):
    server_id: int
    ok: bool
    tool_count: int
    tools: list[MCPLiveToolItem]
    reason: Optional[str] = None
    latency_ms: int = 0


class MCPRawRpcReq(BaseModel):
    """管理员直连 Server 发任意 JSON-RPC 方法（debug 用）。"""
    method: str = Field(..., min_length=1, max_length=128,
                        description="JSON-RPC 方法名：tools/list / ping / initialize / resources/list 等")
    params: dict[str, Any] = Field(default_factory=dict)
    call_timeout_ms: Optional[int] = Field(default=None, ge=100, le=3_600_000)
    session_id: Optional[str] = Field(default=None, max_length=64,
                                       description="stdio checkpoint：复用已保留的子进程会话 id；不传则一次性拉起")


class MCPRawRpcResp(BaseModel):
    server_id: int
    ok: bool
    method: str
    result: Any = None              # 成功时非 None
    error: Optional[dict[str, Any]] = None   # 失败时 JSON-RPC error 对象
    latency_ms: int = 0
    session_id: Optional[str] = Field(default=None, description="若本次调用走/复用会话池，返回会话 id")


class MCPHealthScanItem(BaseModel):
    server_id: int
    server_code: str
    display_name: str
    ok: bool
    latency_ms: int
    reason: Optional[str] = None
    last_health_at: Optional[datetime] = None


class MCPHealthScanResp(BaseModel):
    scanned: int
    ok_count: int
    error_count: int
    items: list[MCPHealthScanItem]
    elapsed_ms: int = 0


# ============================================================
# 7. stdio 长连接会话（Checkpoint）：保留子进程免重复 initialize
# ============================================================
class MCPSessionCreateReq(BaseModel):
    server_id: int = Field(..., ge=1)
    ttl_seconds: int = Field(default=180, ge=30, le=1800, description="会话 GC 空闲 TTL（秒）；到期 idle 自动收")
    keep_raw_session: bool = Field(default=True, description="True=复用已 initialize 的子进程，False=每次新建")


class MCPSessionItem(BaseModel):
    session_id: str
    server_id: int
    server_code: str = ""
    pid: int = 0
    created_ms: int = 0
    last_used_ms: int = 0
    idle_gc_ttl_s: int = 180
    call_count: int = 0
    state: str = Field(default="active", description="active | closing | closed")
    hc: bool = Field(default=False, description="B1：健康检查专用会话（与调试会话隔离）")
    hc_busy: bool = Field(default=False, description="B1：健康检查交换中（GC 豁免窗口）")
    last_error: Optional[str] = None


class MCPSessionResp(BaseModel):
    ok: bool
    message: str = ""
    session: Optional[MCPSessionItem] = None


class MCPSessionListResp(BaseModel):
    total: int
    items: list[MCPSessionItem]


# ============================================================
# 8. 描述体检（task33）：触发结果 + 审计日志
# ============================================================
class MCPReviewToolItem(BaseModel):
    """单个工具描述体检结果（『描述体检』按钮 / discover 后自动体检共享）。"""
    tool_id: int
    tool_name: str
    score: int
    breaches: list[str] = Field(default_factory=list)
    rewritten: str = ""
    rewritten_by_llm: bool = False
    error: Optional[str] = None


class MCPDescriptionReviewResp(BaseModel):
    """一次描述体检批次的汇总 + 明细。"""
    scanned: int
    low_score: int
    rewritten_by_llm: int
    items: list[MCPReviewToolItem]
    elapsed_ms: int = 0


class MCPReviewLogItem(BaseModel):
    """描述体检审计日志条目。"""
    id: int
    server_id: int
    tool_id: int
    tool_name: str
    score: int
    reasons: dict[str, Any] = Field(default_factory=dict)
    rewritten: Optional[str] = None
    rewritten_by_llm: int = 0
    operator_user_id: Optional[int] = None
    created_at: Optional[datetime] = None

    @field_validator("created_at", mode="before")
    @classmethod
    def _dt(cls, v: Any) -> Any:
        if isinstance(v, datetime) or v is None:
            return v
        try:
            return datetime.fromisoformat(str(v))
        except Exception:
            return v


class MCPReviewLogListResp(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[MCPReviewLogItem]
