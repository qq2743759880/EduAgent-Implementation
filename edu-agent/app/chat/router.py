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
import time
from collections.abc import AsyncGenerator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from app.auth import CurrentUser, get_current_user
from app.config import settings
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
from app.common.error_codes import CHAT_PERSIST_FAIL, DEPENDENCY_UNAVAILABLE
from app.knowledge.importer.loader import (
    reset_internal_visibility,
    role_allows_internal,
    set_internal_visibility,
)


router = APIRouter(prefix="/api/chat", tags=["P2-知识问答"])


# ============================================================
# WNEXT10 F5-a：RAG internal 文档可见性（按当前用户角色注入检索上下文）
# ------------------------------------------------------------
# `_default` 分区混着内部工程/运维文档，student 检索不得命中（批判 T4-C4 / F5-a）。
# 检索链路（service → retriever → loader.hybrid_search）不改签名即可感知角色：
# 这里按 user.role 设置请求级 ContextVar，请求结束（finally）恢复。
# SSE 场景响应体在端点返回后才被迭代，故流式路径额外用 _guard_stream_internal 包住迭代器。
# ============================================================
def _internal_visibility_token(user: CurrentUser):
    """按角色设置 internal 可见性，返回 reset token（调用方负责 finally 恢复）。"""
    return set_internal_visibility(role_allows_internal(getattr(user, "role", None)))


async def _guard_stream_internal(agen, allowed: bool):
    """在流式响应体迭代期间维持 internal 可见性（端点 return 后 finally 已 reset，需重建）。"""
    token = set_internal_visibility(allowed)
    try:
        async for chunk in agen:
            yield chunk
    finally:
        reset_internal_visibility(token)


async def _tb2b_close_root_span(agen, root_cm, root_handle):
    """TB2b：包裹 SSE 响应体迭代器，负责 chat.request root span 的收口。

    必须在响应体迭代结束（或被取消）时才 __exit__——root span 的 duration 才等于
    用户真实感知的端到端耗时。异常/断连路径标 status=ERROR，保证 Jaeger 上失败可见。
    """
    err: BaseException | None = None
    try:
        async for chunk in agen:
            yield chunk
    except GeneratorExit:
        # 生成器正常关闭（客户端读完即 aclose）——不是失败，不得标 ERROR
        # （否则每个正常 SSE 请求的 chat.request 都会在 Jaeger 上显示红条，噪声淹没真错误）。
        # AsyncGenerator 语义：GeneratorExit 不要 re-raise（会触发 RuntimeError）。
        err = None
    except BaseException as exc:  # noqa: BLE001 — 含客户端断连的 CancelledError
        err = exc
        try:
            if root_handle is not None:
                root_handle.record_exception(exc)
                root_handle.mark_error(f"{type(exc).__name__}: {exc}")
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        try:
            if root_cm is not None:
                root_cm.__exit__(type(err), err, getattr(err, "__traceback__", None))
        except Exception:  # noqa: BLE001
            pass


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
# 工具：流式"建连后"异常 → 可区分错误码 映射（W2 批判 C3 落地）
# R02：实现已抽取至 app/chat/sse.py（map_stream_exception），顶部 import 同名绑定，
# 供本模块与 graph_stream 适配层共用；下方原函数体删除以保单一事实源。
# ============================================================


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
    """仅检索（不生成答案，不落库）。返回 docs / graph / raw_count / rewrite / degraded。

    WNEXT10 F5-a：按角色限制 internal 文档可见性（student 命中不到内部工程/运维文档）。
    """
    _internal_token = _internal_visibility_token(user)
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
    finally:
        reset_internal_visibility(_internal_token)


# ============================================================
# 3. 非流式问答
# ============================================================
@router.post("", response_model=dict)
async def chat_non_stream(
    req: RagQueryRequest,
    user: CurrentUser = Depends(get_current_user),
    request: Request = None,  # FastAPI 注入 Request 实例（特殊类型，忽略默认值）
):
    """非流式问答（直接返回最终回答 + 引用 + 图谱 + 耗时）。

    WNEXT10 F5-a：检索期间按角色限制 internal 文档可见性（student 检索不到内部工程/运维文档）。
    """
    _internal_token = _internal_visibility_token(user)
    # W-NEXT-OTLP-001：chat 入口 span（lifespan OTLP 探针启用时发到 OTel Collector；
    # disabled 模式 no-op 零开销，sync 友好不抛）。
    try:
        from app.observability.otlp import trace_chat_entry
        trace_chat_entry(
            user_id=str(getattr(user, "user_id", "")),
            query=getattr(req, "query", "") or "",
            session_id=getattr(req, "session_id", None),
        )
    except Exception:
        pass
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
    finally:
        reset_internal_visibility(_internal_token)


# ============================================================
# 4. 流式问答（SSE：event: start/retrieval/token/done/error）
# ============================================================
# R02：SSE 帧序列化与错误码映射抽取至 app/chat/sse.py 单一实现（新旧路径共用，防漂移）；
# 此处保留同名绑定（历史测试 chat_router._map_stream_exception / _sse_line 契约不变）。
from app.chat.sse import map_stream_exception as _map_stream_exception
from app.chat.sse import sse_line as _sse_line


@router.post("/stream")
async def chat_stream_sse(
    req: RagQueryRequest,
    user: CurrentUser = Depends(get_current_user),
    request: Request = None,  # FastAPI 注入 Request 实例（特殊类型，忽略默认值）
):
    """
    SSE 流式问答（帧形状由 tests/test_sse_envelope_contract.py 钉死，改动=破坏性变更）：
    - start       : { session_id, query }                                          # 裸帧
    - retrieval   : { docs[], graph_entities[], retrieved_count, final_count,     # 裸帧
                      rewrite_query, degraded_reason, mcp_tool_calls[] }
    - token       : { delta }                                                     # 裸帧，逐字累加
    - done        : { code:0, message:"ok",                                       # 唯一带统一壳
                      data:{ session_id, message_id, retrieved_count, final_count,
                             latency_ms, rewrite_query, degraded_reason } }
    - error       : { code, message }（落库失败额外带 generated_tokens/session_id/message_id）  # 裸帧

    R02：settings.STREAM_VIA_GRAPH=True（默认）→ 走 graph.astream 适配层（flows/graph_stream.py，
    同一 SSE 契约）；False → 一键回旧路径 service_chat_stream（行为与本函数历史版本逐字节等同）。
    """
    # W-NEXT-OTLP-001：chat 入口 span（disabled 模式 no-op 零开销）
    try:
        from app.observability.otlp import trace_chat_entry
        trace_chat_entry(
            user_id=str(getattr(user, "user_id", "")),
            query=getattr(req, "query", "") or "",
            session_id=getattr(req, "session_id", None),
            extra={"path": "/api/chat/stream"},
        )
    except Exception:
        pass
    try:
        # WNEXT10 F5-a：检索期间按角色限制 internal 文档可见性（建连前检索走这段上下文）
        _internal_token = _internal_visibility_token(user)
        # task-O1 AC4：会话级 trace_id（同 session_id 多请求复用同一 trace_id，span_id 各异）
        from app.core.trace import set_trace_context

        tid = set_trace_context(session_id=getattr(req, "session_id", None))
        if request is not None:
            request.state.trace_id = tid  # 穿透 BaseHTTPMiddleware context 隔离，写回 X-Trace-Id

        # R02 执行体开关：默认走 LangGraph 图；False 回退旧路径（契约同构，前端零改动）
        if getattr(settings, "STREAM_VIA_GRAPH", True):
            from app.chat.flows.graph_stream import graph_stream_sse

            # TB2b（断点③修复）：chat 链路分层 span 的 **root** —— `chat.request`。
            # 必须在 router 层开、并包裹整个流生命周期（含 body_iterator 异步迭代），
            # 否则 root 会在 handler return 时就 end，子 span 挂不上去（实测变成孤立 trace）。
            # 故 root 的 span 上下文挂在响应体迭代器上，由包装后的 aiter 负责 end。
            from app.observability.tracing import span as _otel_span

            _root_cm = _otel_span(
                "chat.request",
                kind="server",
                attributes={
                    "user_id": str(getattr(user, "user_id", "")),
                    "role": str(getattr(user, "role", "")),
                    "session_id": str(getattr(req, "session_id", "") or ""),
                    "query": (getattr(req, "query", "") or "")[:256],
                    "query_len": len(getattr(req, "query", "") or ""),
                    "channel": "sse",
                    "trace_id": tid,
                },
            )
            _root_handle = _root_cm.__enter__()
            try:
                resp = await graph_stream_sse(
                    req, user_id=user.user_id, role=user.role, otel_parent=_root_handle,
                )
            except BaseException as _exc:
                # 建连/建图失败：root span 标错收口后原样上抛（保 HTTP 状态码契约）
                try:
                    if _root_handle is not None:
                        _root_handle.record_exception(_exc)
                        _root_handle.mark_error(f"{type(_exc).__name__}: {_exc}")
                except Exception:  # noqa: BLE001
                    pass
                _root_cm.__exit__(type(_exc), _exc, _exc.__traceback__)
                raise
            # WNEXT10 F5-a：响应体在 return 之后才被迭代 → 迭代期间重建 internal 可见性
            if hasattr(resp, "body_iterator"):
                _body = _guard_stream_internal(
                    resp.body_iterator, role_allows_internal(getattr(user, "role", None))
                )
                resp.body_iterator = _tb2b_close_root_span(_body, _root_cm, _root_handle)
            else:
                # 无 body_iterator（非预期形态）：root 立即收口，避免悬挂
                _root_cm.__exit__(None, None, None)
            return resp

        session, bundle, history_turns, token_aiter, build_finalize, mcp_summaries = await service_chat_stream(
            req, user_id=user.user_id, role=user.role,
        )
    except Exception as e:
        # 两段式错误模型 · 第一段：**建连前失败**（service_chat_stream 检索/初始化抛错）。
        # 此刻 SSE 连接尚未建立，无法发流内事件，故「同步返回 HTTP 4xx/5xx」，不发 SSE——
        # 这是批判 C3.1 认可的双通道取舍：
        #   「连接前 → 同步 HTTP；建连后（token 迭代 / build_finalize 落库）→ 流内 event: error」
        # 请勿把此处改成发 SSE，否则会破坏「响应体开始前即失败复用 HTTP 状态码」的契约。
        try:
            _translate_exception(e)
        except HTTPException as he:
            raise he
        except Exception as e2:
            logger.exception(f"[P2 stream] 初始化失败：{e2}")
            raise HTTPException(status_code=500, detail={"code": "CHAT_STREAM_INIT_FAIL", "message": "流式初始化失败"})
    finally:
        # 建连前的检索已结束（响应体迭代期间的可见性由 _guard_stream_internal 重建）
        reset_internal_visibility(_internal_token)

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
            # 两段式错误模型 · 第二段：流已建连，生成真失败（如 LLM key 失效/下游超时/限流）
            # → 发 `event: error` 并安全收束（return，关闭连接）。错误码从固定 50000 提升为
            # 可区分下游码（LLM_AUTH/LLM_TIMEOUT/LLM_RATE_LIMIT/LLM_UNAVAILABLE/SERVICE_DOWNSTREAM，
            # 见 _map_stream_exception），使前端 error 分支真实可达且可区分（audit P1-10 /
            # task115 C-B / W2 批判 C3）。此时 START/RETRIEVAL 帧已先行发出，未丢帧。
            code, msg = _map_stream_exception(e)
            logger.warning(f"[P2 stream] token 迭代异常，发 error 事件：{code} {msg} ({e})")
            yield _sse_line(SseEventType.ERROR.value, {"code": code, "message": msg})
            return
        # 3) 最终：落库 + done 事件
        answer_text = "".join(buf)
        try:
            final_info = await build_finalize(answer_text, degraded_extra=None)
        except Exception as e:
            # 两段式错误模型 · 第三段：落库失败（build_finalize 抛错）。
            # 不再静默只写 degraded_reason（W2 批判 C3.1）——显式发 `event: error` 且
            # code=CHAT_PERSIST_FAIL，并回传已生成 token 数 / 占位 message_id，让前端明确知道
            # 「答案已生成但未入库」。随后补一个带 degraded 提示的 done 做正常收束兜底（不静默）。
            generated_tokens = len(buf)
            logger.warning(f"[P2 stream] 落库失败，发 error 事件：{CHAT_PERSIST_FAIL} ({e})")
            yield _sse_line(SseEventType.ERROR.value, {
                "code": CHAT_PERSIST_FAIL,
                "message": f"答案生成成功但落库失败：{type(e).__name__}（内容未保存到会话）",
                "generated_tokens": generated_tokens,
                "session_id": session_id_out,
                "message_id": None,
            })
            yield _sse_line(SseEventType.DONE.value, {
                "code": 0,
                "message": "ok",
                "data": {
                    "session_id": session_id_out,
                    "message_id": None,
                    "retrieved_count": int(bundle.raw_retrieved_count),
                    "final_count": int(len(bundle.docs)),
                    "latency_ms": 0,
                    "rewrite_query": bundle.rewrite_query,
                    "degraded_reason": f"答案已生成但流式落库失败({type(e).__name__})：未入库",
                },
            })
            return

        # 契约① SSE 例外：done 事件 data 内嵌统一壳 {code:0, message:"ok", data:{...}}
        yield _sse_line(SseEventType.DONE.value, {
            "code": 0,
            "message": "ok",
            "data": final_info,
        })

    # WNEXT10 F5-a：旧路径（STREAM_VIA_GRAPH=False）同样在迭代期间维持 internal 可见性
    return StreamingResponse(
        _guard_stream_internal(_gen(), role_allows_internal(getattr(user, "role", None))),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================
# 5. HITL 中断恢复（R11，contracts/reshape-r-hitl.json 冻结）
# ============================================================
class ChatResumeRequest(BaseModel):
    """resume 请求体：thread_id（pending_confirm 帧携带）+ confirm/reject + 可选 reason。"""

    thread_id: str
    action: Literal["confirm", "reject"]
    reason: str | None = None


@router.post("/resume")
async def chat_resume(
    body: ChatResumeRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """HITL 中断恢复决策端点（契约 reshape-r-hitl.json）：
    - 校验该 thread_id 存在挂起中的确认（Redis hitl:pending: 标记，TTL=timeout_s=300 内有效）；
    - 决策写 Redis hitl:decision:{thread_id}（TTL=300），供客户端以同 thread_id 重开
      POST /api/chat/stream 时由 graph_stream 适配层以 Command(resume=决策) 续跑挂起图；
    - 未知/过期 thread_id → 40450（CHAT_HITL_THREAD_NOT_FOUND，HTTP 404，语义「确认已超时」）；
    - Redis 不可达 → 50301 DEPENDENCY_UNAVAILABLE（脱敏，T19-3 契约）。
    """
    from app.common.error_codes import CHAT_HITL_THREAD_NOT_FOUND
    from app.common.exceptions import AppException as _AppException
    from app.database import get_redis

    try:
        r = get_redis()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[P2 resume] Redis 不可用: {type(exc).__name__}: {exc}")
        raise _AppException(DEPENDENCY_UNAVAILABLE, "依赖服务暂不可用，请稍后重试", http_status=503) from exc

    pending_key = f"hitl:pending:{body.thread_id}"
    decision_key = f"hitl:decision:{body.thread_id}"
    ttl = int(getattr(settings, "HITL_RESUME_TTL", 300))
    try:
        raw = await r.get(pending_key)
        if not raw:
            # 未知 / TTL 过期 → 契约 40450（「确认已超时」）
            logger.info(f"[P2 resume] thread_id 无挂起确认（未知或已超时）: {body.thread_id}")
            raise _AppException(
                CHAT_HITL_THREAD_NOT_FOUND,
                "确认请求已超时或不存在，无法继续执行，请重新提问。",
            )
        decision = {"action": body.action, "reason": body.reason or "", "created_at": time.time()}
        await r.set(decision_key, json.dumps(decision, ensure_ascii=False), ex=ttl)
        await r.delete(pending_key)
    except _AppException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[P2 resume] 决策写入失败: {type(exc).__name__}: {exc}")
        raise _AppException(DEPENDENCY_UNAVAILABLE, "依赖服务暂不可用，请稍后重试", http_status=503) from exc

    status_val = "resumed" if body.action == "confirm" else "rejected"
    logger.info(f"[P2 resume] thread_id={body.thread_id} action={body.action} → {status_val}")
    return ok({"status": status_val})
