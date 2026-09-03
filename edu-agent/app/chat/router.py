"""
P2 问答路由：
- POST /api/chat/sessions             创建会话（登录即可，student 可用）
- GET  /api/chat/sessions             会话列表（当前用户；admin 全局）
- GET  /api/chat/sessions/{id}/history  会话消息历史（正序）
- DELETE /api/chat/sessions/{id}      软删会话（UPDATE chat_session SET yn=0，禁止物理 DELETE）
- POST /api/chat/search               仅检索（不生成，不落库）
- POST /api/chat                      非流式问答
- POST /api/chat/stream               流式问答（SSE：start → retrieval → token → done/error）

权限：
- 所有路由至少 Depends(get_current_user)，无 Token（DEBUG 虚拟管理员除外）直接 401
- 会话访问：非 admin 必须是 session.user_id == current_user.user_id，否则 service 抛 ValidationError(detail=CHAT_SESSION_FORBIDDEN) → 403
"""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from loguru import logger

from app.auth import CurrentUser, get_current_user
from app.core.resp import ok
from app.chat.schemas import (
    ChatSession,
    ChatSessionCreate,
    DeleteSessionResponse,
    RagAnswerResponse,
    RagQueryRequest,
    RagSearchOnlyRequest,
    SseEventType,
)
from app.chat.service import (
    chat_answer as service_chat_answer,
    chat_stream as service_chat_stream,
    create_session as service_create_session,
    delete_session as service_delete_session,
    get_session_history,
    list_sessions,
    search_only,
)
from app.common.exceptions import AppException, NotFoundError, ValidationError
from app.common.error_codes import INTERNAL_ERROR


router = APIRouter(prefix="/api/chat", tags=["P2-知识问答"])


# ============================================================
# 工具：异常统一映射（AppException → HTTP；code=CHAT_SESSION_FORBIDDEN 专门映射为 403）
# ============================================================
def _translate_exception(e: Exception) -> None:
    """把 service 抛的业务异常按 code/detail 映射为更准确的 HTTP 状态码。"""
    # NotFoundError（http_status=404）：若资源名是"会话"，按业务语义补充 CHAT_SESSION_NOT_FOUND
    if isinstance(e, NotFoundError):
        msg = getattr(e, "message", str(e))
        res = getattr(e, "detail", "") or ""
        code_str = "CHAT_SESSION_NOT_FOUND" if ("会话" in msg or "session" in res.lower()) else "NOT_FOUND"
        raise HTTPException(status_code=getattr(e, "http_status", 404), detail={"code": code_str, "message": msg})
    if isinstance(e, ValidationError):
        detail = getattr(e, "detail", None) or ""
        msg = getattr(e, "message", str(e))
        if "CHAT_SESSION_FORBIDDEN" in f"{msg} {detail}":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "CHAT_SESSION_FORBIDDEN", "message": msg})
        # 其他 ValidationError 交给全局 handler（默认 400）
        raise
    if isinstance(e, AppException):
        # 其他业务异常（含带 http_status）：抛给全局 handler
        raise
    # 非预期：记录日志并 500（不把 traceback 暴露）
    logger.exception(f"[P2 router] 未处理异常：{e}")
    raise HTTPException(status_code=500, detail={"code": "CHAT_INTERNAL_ERROR", "message": "问答服务暂不可用，请稍后重试"})


# ============================================================
# 1. 会话管理
# ============================================================
@router.post("/sessions", response_model=dict, status_code=status.HTTP_201_CREATED)
async def sessions_create(
    body: ChatSessionCreate | None = None,
    user: CurrentUser = Depends(get_current_user),
):
    """创建一个新的问答会话。不传 body 也能创建，用默认 title 占位。"""
    try:
        return ok(await service_create_session(user.user_id, body))
    except Exception as e:
        _translate_exception(e)


@router.get("/sessions", response_model=dict)
async def sessions_list(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    user: CurrentUser = Depends(get_current_user),
):
    """列出会话：默认按 last_message_at DESC 倒序。"""
    try:
        return ok(await list_sessions(user.user_id, user.role, limit=limit))
    except Exception as e:
        _translate_exception(e)


@router.get("/sessions/{session_id}/history")
async def sessions_history(
    session_id: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    user: CurrentUser = Depends(get_current_user),
):
    """按时间正序返回该会话的全部消息（user+assistant 对）。"""
    try:
        return ok(await get_session_history(session_id, user.user_id, user.role, limit=limit))
    except Exception as e:
        _translate_exception(e)


@router.delete("/sessions/{session_id}", response_model=dict)
async def sessions_delete(
    session_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """
    软删会话（R-2 补丁）：
    - 200 {ok:true}：本人/管理员软删（UPDATE chat_session SET yn=0，禁止物理 DELETE）
    - 403：跨用户删除（CHAT_SESSION_FORBIDDEN）
    - 404：会话不存在 / 已删除
    """
    try:
        await service_delete_session(user.user_id, session_id, user.role)
        return ok(DeleteSessionResponse(ok=True))
    except Exception as e:
        _translate_exception(e)


# ============================================================
# 2. 仅检索（调试/引用预览用）
# ============================================================
@router.post("/search")
async def search_endpoint(
    req: RagSearchOnlyRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """仅检索（不生成答案，不落库）。返回 docs / graph / raw_count / rewrite / degraded。"""
    try:
        docs, graphs, raw_count, rewrite, degraded = await search_only(
            req, user_id=user.user_id, role=user.role,
        )
        return ok({
            "docs": [d.model_dump() for d in docs],
            "graph_entities": [g.model_dump() for g in graphs],
            "retrieved_count": raw_count,
            "final_count": len(docs),
            "rewrite_query": rewrite,
            "degraded_reason": degraded,
        })
    except Exception as e:
        _translate_exception(e)


# ============================================================
# 3. 非流式问答
# ============================================================
@router.post("", response_model=dict)
async def chat_non_stream(
    req: RagQueryRequest,
    user: CurrentUser = Depends(get_current_user),
    request: Request = None,  # FastAPI 注入 Request 实例（特殊类型，忽略默认值）
):
    """非流式问答（直接返回最终回答 + 引用 + 图谱 + 耗时）。"""
    try:
        # task-O1 AC4：会话级 trace_id —— 同一 session_id 的多次请求复用同一 trace_id，
        # 使本次完整问答（记忆召回 + LLM + 工具 + 压缩）各 span 可整链还原。
        from app.core.trace import set_trace_context

        tid = set_trace_context(session_id=getattr(req, "session_id", None))
        if request is not None:
            request.state.trace_id = tid  # 穿透 BaseHTTPMiddleware context 隔离，写回 X-Trace-Id
        return ok(await service_chat_answer(req, user_id=user.user_id, role=user.role))
    except Exception as e:
        _translate_exception(e)


# ============================================================
# 4. 流式问答（SSE：event: start/retrieval/token/done/error）
# ============================================================
def _sse_line(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


@router.post("/stream")
async def chat_stream_sse(
    req: RagQueryRequest,
    user: CurrentUser = Depends(get_current_user),
    request: Request = None,  # FastAPI 注入 Request 实例（特殊类型，忽略默认值）
):
    """
    SSE 流式问答：
    - start       : { session_id, message_id_pre (占位用) }
    - retrieval   : { docs[], graph_entities[], rewrite_query, retrieved_count, degraded_reason }
    - token       : { delta }
    - done        : { session_id, message_id, retrieved_count, final_count, latency_ms, rewrite_query, degraded_reason }
    - error       : { message }
    """
    try:
        # task-O1 AC4：会话级 trace_id（同 session_id 多请求复用同一 trace_id，span_id 各异）
        from app.core.trace import set_trace_context

        tid = set_trace_context(session_id=getattr(req, "session_id", None))
        if request is not None:
            request.state.trace_id = tid  # 穿透 BaseHTTPMiddleware context 隔离，写回 X-Trace-Id
        session, bundle, history_turns, token_aiter, build_finalize, mcp_summaries = await service_chat_stream(
            req, user_id=user.user_id, role=user.role,
        )
    except Exception as e:
        # 在响应开始前出错：同步返回 4xx/5xx，不发 SSE
        try:
            _translate_exception(e)
        except HTTPException as he:
            raise he
        except Exception as e2:
            logger.exception(f"[P2 stream] 初始化失败：{e2}")
            raise HTTPException(status_code=500, detail={"code": "CHAT_STREAM_INIT_FAIL", "message": "流式初始化失败"})

    async def _gen() -> AsyncGenerator[bytes, None]:
        # 0) 先把 session_id / 临时占位发出去
        session_id_out = session.session_id if session else None
        yield _sse_line(SseEventType.START.value, {
            "session_id": session_id_out,
            "query": req.query,
        })
        # 1) 发检索结果（docs + graph + MCP 工具摘要，前端提前渲染引用 tag / sidebar）
        yield _sse_line(SseEventType.RETRIEVAL_DONE.value, {
            "docs": [d.model_dump() for d in bundle.docs],
            "graph_entities": [g.model_dump() for g in bundle.graph_entities],
            "retrieved_count": int(bundle.raw_retrieved_count),
            "final_count": int(len(bundle.docs)),
            "rewrite_query": bundle.rewrite_query,
            "degraded_reason": bundle.degraded_reason,
            "mcp_tool_calls": [s.model_dump() for s in mcp_summaries],
        })
        # 2) 逐个 token 发送
        buf: list[str] = []
        try:
            async for delta in token_aiter:
                buf.append(delta)
                yield _sse_line(SseEventType.TOKEN.value, {"delta": delta})
        except Exception as e:
            # 两段式错误模型 · 第二段：流已建连，生成真失败（如 LLM key 失效/下游超时）
            # → 发 error 事件并安全收束（返回，关闭连接）。不再静默转 done+degraded_reason，
            # 使前端 error 分支真实可达（audit P1-10 / task115 C-B）。
            code, msg = INTERNAL_ERROR, f"答案生成失败：{type(e).__name__}"
            logger.warning(f"[P2 stream] token 迭代异常，发 error 事件：{code} {msg} ({e})")
            yield _sse_line(SseEventType.ERROR.value, {"code": code, "message": msg})
            return
        # 3) 最终：落库 + done 事件
        answer_text = "".join(buf)
        try:
            final_info = await build_finalize(answer_text, degraded_extra=None)
        except Exception as e:
            # 落库失败：不泄漏到前端，只在 done 的 degraded_reason 里提示
            logger.warning(f"[P2 stream] 落库失败：{type(e).__name__}: {e}")
            final_info = {
                "session_id": session_id_out,
                "message_id": None,
                "retrieved_count": int(bundle.raw_retrieved_count),
                "final_count": int(len(bundle.docs)),
                "latency_ms": 0,
                "rewrite_query": bundle.rewrite_query,
                "degraded_reason": f"流式落库失败({type(e).__name__})",
            }
        # 契约① SSE 例外：done 事件 data 内嵌统一壳 {code:0, message:"ok", data:{...}}
        yield _sse_line(SseEventType.DONE.value, {
            "code": 0,
            "message": "ok",
            "data": final_info,
        })

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
