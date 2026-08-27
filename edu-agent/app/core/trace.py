"""
链路追踪工具（Phase 重构：task09 core/ 框架层）

面试考点：
- ContextVar：Python 协程安全的上下文变量，每个请求独立一份
- trace_id vs span_id：trace_id 全链路不变，span_id 每层调用生成新的
- 为什么不用 OpenTelemetry？单体场景 OTel Agent/Collector 运维成本 > 收益

用法：
  from app.core.trace import trace_id_var, get_trace_id, start_span
  tid = get_trace_id()
  with start_span("milvus_search"):
      results = milvus.search(...)
"""
from __future__ import annotations

import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

from app.config import settings

# 全局上下文变量
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
span_id_var: ContextVar[str] = ContextVar("span_id", default="")


def get_trace_id() -> str:
    """获取当前请求的 trace_id。"""
    return trace_id_var.get("")


def generate_trace_id() -> str:
    """生成新的 trace_id（16 位 hex）。"""
    return uuid.uuid4().hex[:16]


@contextmanager
def start_span(name: str):
    """
    开始一个 span（用于 LLM/MCP/Milvus/Redis/MySQL 调用点）。

    用法：
      with start_span("llm_call"):
          answer = llm.generate(...)
    """
    parent_span = span_id_var.get("")
    span_id = uuid.uuid4().hex[:8]
    span_id_var.set(span_id)
    t0 = time.perf_counter()

    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - t0) * 1000
        span_id_var.set(parent_span)
        # 结构化日志（供 ELK/Grafana 聚合）
        from app.common.logging import logger
        logger.debug(
            f"[Trace] span={name} duration={duration_ms:.1f}ms",
            trace_id=get_trace_id(),
            span_id=span_id,
            span_name=name,
            span_duration_ms=round(duration_ms, 1),
        )


# ============================================================
# 3. 嵌套 span 栈（task-O1：支持嵌套 span 记 duration + parent 链路）
# ============================================================
_span_stack: ContextVar[list] = ContextVar("span_stack", default=[])


def current_span() -> str:
    """返回当前最内层 span_id（无 span 时为空字符串）。"""
    stack = _span_stack.get()
    return stack[-1]["span_id"] if stack else ""


@contextmanager
def child_span(name: str):
    """嵌套 span：进入时压栈新 span_id，退出时弹栈并结构化日志（含 parent 与 duration）。

    用法：
      with child_span("memory_recall"):
          docs = recall(...)
      with child_span("llm_call"):
          answer = llm.generate(...)
    """
    parent = current_span()
    span_id = uuid.uuid4().hex[:8]
    stack = _span_stack.get().copy()
    stack.append({"span_id": span_id, "name": name, "parent": parent})
    token = _span_stack.set(stack)
    t0 = time.perf_counter()
    try:
        yield span_id
    finally:
        duration_ms = (time.perf_counter() - t0) * 1000
        _span_stack.reset(token)
        try:
            from app.common.logging import logger
            logger.debug(
                f"[Trace] span={name} duration={duration_ms:.1f}ms",
                trace_id=get_trace_id(),
                span_id=span_id,
                span_name=name,
                parent_span_id=parent,
                span_duration_ms=round(duration_ms, 1),
            )
        except Exception:
            pass


# ============================================================
# 4. 会话级 trace_id（task-O1 AC4：一次会话内多次请求复用同一 trace_id）
# ============================================================
_session_trace_ids: dict[str, str] = {}
_session_lock = threading.Lock()


def session_trace_id(session_id: str | None = None) -> str:
    """返回会话级 trace_id：同一 session_id 多次请求复用同一 trace_id（span_id 各自不同）。

    - session_id 为 None，或 settings.TRACE_SESSION_LEVEL=False → 回退请求级
      （取当前 trace_id_var，无则新生成）。
    - 否则按 session_id 在进程内稳定映射到一个 trace_id。
    """
    if not session_id or not getattr(settings, "TRACE_SESSION_LEVEL", True):
        return get_trace_id() or generate_trace_id()
    with _session_lock:
        tid = _session_trace_ids.get(session_id)
        if tid is None:
            tid = generate_trace_id()
            _session_trace_ids[session_id] = tid
        return tid


def set_trace_context(*, session_id: str | None = None) -> str:
    """为当前请求建立 trace 上下文：会话级优先，否则沿用/新生成请求级 trace_id。

    返回生效的 trace_id（已写入 trace_id_var）。供 chat 会话入口调用，使一次完整问答
    （记忆召回 + LLM + 工具 + 压缩）各 span 共用同一 trace_id，可整链还原。
    """
    tid = session_trace_id(session_id)
    trace_id_var.set(tid)
    return tid


def reset_session_traces() -> None:
    """清空会话级 trace_id 映射（测试用）。"""
    with _session_lock:
        _session_trace_ids.clear()