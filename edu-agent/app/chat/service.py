"""
P2 问答 Service：会话/消息持久化 + 检索 + 生成 编排。

设计：
- 所有 SQL 字段与 patch_chat_tables.sql 一致；字段缺失时接口不 500（由 SQL 先补列）
- 会话 session_id / 消息 message_id 都用短 uuid（可前端直接展示）
- 写操作全部走 aiomysql transaction 上下文；读操作 fetch_one/fetch_all 直接用
- 强约束：任何 session/消息都绑定 user_id；跨用户访问会抛 ValidationError，由 router 转 403
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Literal

from app.admin.rag_admin.service import insert_audit_log as _rag_insert_audit_log
from app.auth import UserRole
from app.chat.generator import generate_answer, generate_stream
from app.chat.retriever import RetrievalBundle, retrieve_three_channel
from app.chat.schemas import (
    ChatMessage,
    ChatSession,
    ChatSessionCreate,
    GraphEntity,
    MCPToolCallSummary,
    RagAnswerResponse,
    RagQueryRequest,
    RagSearchOnlyRequest,
    RetrievedDoc,
)
from app.chat.tool_calling import inject_mcp_into_system_prompt, run_chat_tool_calls
from app.common.exceptions import NotFoundError, ValidationError
from app.config import settings
from app.database import execute_write, fetch_all, fetch_one, transaction


# ============================================================
# 1. 会话：创建 / 列表 / 历史
# ============================================================
def _new_session_id() -> str:
    return "s_" + uuid.uuid4().hex[:12]


def _new_message_id() -> str:
    return "m_" + uuid.uuid4().hex[:12]


_MICROSECOND_STEP = timedelta(milliseconds=1)


async def create_session(user_id: int, req: ChatSessionCreate | None = None) -> ChatSession:
    """创建会话：title 默认用空串（等第 1 条 question 自动回填）。"""
    req = req or ChatSessionCreate()
    session_id = _new_session_id()
    title = (req.title or "").strip() or f"新会话 {session_id[-6:]}"
    now = datetime.now()
    insert_sql = """
        INSERT INTO chat_session
        (session_id, user_id, title, visibility, message_count, last_message_at, created_at, updated_at, yn)
        VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s, 1)
    """
    async with transaction():
        await execute_write(
            insert_sql,
            (
                session_id,
                int(user_id),
                title,
                req.visibility,
                0,
                None,
                now,
                now,
            ),
        )
    return ChatSession(
        session_id=session_id,
        user_id=int(user_id),
        title=title,
        visibility=req.visibility,
        message_count=0,
        last_message_at=None,
        created_at=now,
        updated_at=now,
        yn=1,
    )


async def _ensure_session_owner(session_id: str, user_id: int, role: UserRole) -> ChatSession:
    """管理员可以看所有人（打靶简单实现）；其他必须是自己。返回会话。"""
    row = await fetch_one(
        "SELECT * FROM chat_session WHERE session_id = %s AND yn = 1 LIMIT 1",
        (session_id,),
    )
    if row is None:
        raise NotFoundError("会话", session_id)
    owner_uid = int(row["user_id"])
    if role is not UserRole.ADMIN and role.value != UserRole.ADMIN.value and owner_uid != int(user_id):
        raise ValidationError("无权限访问该会话", detail="CHAT_SESSION_FORBIDDEN")
    return ChatSession(
        session_id=row["session_id"],
        user_id=owner_uid,
        title=row["title"],
        visibility=row["visibility"],
        message_count=int(row["message_count"] or 0),
        last_message_at=row["last_message_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        yn=int(row["yn"] or 1),
    )


async def list_sessions(user_id: int, role: UserRole, *, limit: int = 50) -> list[ChatSession]:
    """会话列表：按 last_message_at 倒序（再 created_at 倒序）。"""
    if role is UserRole.ADMIN or role.value == UserRole.ADMIN.value:
        rows = await fetch_all(
            "SELECT * FROM chat_session WHERE yn = 1 ORDER BY last_message_at DESC, created_at DESC LIMIT %s",
            (limit,),
        )
    else:
        rows = await fetch_all(
            "SELECT * FROM chat_session WHERE yn = 1 AND user_id = %s ORDER BY last_message_at DESC, created_at DESC LIMIT %s",
            (int(user_id), limit),
        )
    return [
        ChatSession(
            session_id=r["session_id"],
            user_id=int(r["user_id"]),
            title=r["title"],
            visibility=r["visibility"],
            message_count=int(r["message_count"] or 0),
            last_message_at=r["last_message_at"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            yn=int(r["yn"] or 1),
        )
        for r in rows
    ]


async def get_session_history(
    session_id: str,
    user_id: int,
    role: UserRole,
    *,
    limit: int = 200,
) -> list[ChatMessage]:
    """按时间正序返回会话消息（前端渲染整个会话用）。"""
    await _ensure_session_owner(session_id, user_id, role)
    rows = await fetch_all(
        "SELECT * FROM chat_message WHERE session_id = %s ORDER BY created_at ASC, message_id ASC LIMIT %s",
        (session_id, limit),
    )
    return [_row_to_message(r) for r in rows]


def _row_to_message(r: dict) -> ChatMessage:
    return ChatMessage(
        message_id=r["message_id"],
        session_id=r["session_id"],
        user_id=int(r["user_id"]),
        role=r["role"],
        content=r["content"] or "",
        rag_query_rewrite=r.get("rag_query_rewrite"),
        rag_retrieved_count=int(r["rag_retrieved_count"]) if r.get("rag_retrieved_count") is not None else None,
        rag_final_count=int(r["rag_final_count"]) if r.get("rag_final_count") is not None else None,
        rag_docs_json=r.get("rag_docs_json"),
        rag_error=r.get("rag_error"),
        latency_ms=int(r["latency_ms"]) if r.get("latency_ms") is not None else None,
        # --- P8 MCP ---
        mcp_tool_calls_json=r.get("mcp_tool_calls_json"),
        mcp_called_count=int(r["mcp_called_count"]) if r.get("mcp_called_count") is not None else None,
        created_at=r["created_at"],
    )


# ============================================================
# 2. 历史窗口：给 generator 提示词用（最近 N 轮 user+assistant 对）
# ============================================================
async def _history_window(
    session_id: str | None,
    user_id: int,
    role: UserRole,
    *,
    include_history: int,
) -> list[tuple[str, str]]:
    """include_history = 轮数，每轮 2 条消息。返回正序 [(role, content)]。"""
    if not session_id or include_history <= 0:
        return []
    all_msgs = await get_session_history(session_id, user_id, role, limit=include_history * 4)
    # 只取最近的 N 对（最后 2*N 条内，去除 system）
    filtered = [(m.role, m.content) for m in all_msgs if m.role in ("user", "assistant")]
    return filtered[-include_history * 2 :]


# ============================================================
# 3. 写入消息 & 更新会话计数
# ============================================================
async def _append_messages_and_bump_session(
    session: ChatSession,
    *,
    user_msg: ChatMessage,
    assistant_msg: ChatMessage | None,
) -> None:
    now = datetime.now()
    # title 回填：如果当前会话 title 是默认的「新会话 xxx」，用第 1 条 question 前 30 字
    new_title = session.title
    if new_title.startswith("新会话 s_") and user_msg.role == "user":
        new_title = (user_msg.content.strip() or new_title).replace("\n", " ")[:30].strip() or new_title

    inc = 1 if assistant_msg is None else 2
    new_count = int(session.message_count) + inc

    insert_user_sql = """
        INSERT INTO chat_message
        (message_id, session_id, user_id, role, content,
         rag_query_rewrite, rag_retrieved_count, rag_final_count, rag_docs_json, rag_error, latency_ms,
         mcp_tool_calls_json, mcp_called_count,
         created_at)
        VALUES
        (%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s, %s,%s, %s)
    """
    insert_assistant_sql = insert_user_sql
    update_session_sql = """
        UPDATE chat_session
        SET title = %s, message_count = %s, last_message_at = %s, updated_at = %s
        WHERE session_id = %s AND yn = 1
    """
    async with transaction():
        await execute_write(
            insert_user_sql,
            (
                user_msg.message_id, user_msg.session_id, int(user_msg.user_id), user_msg.role, user_msg.content,
                user_msg.rag_query_rewrite, user_msg.rag_retrieved_count, user_msg.rag_final_count,
                user_msg.rag_docs_json, user_msg.rag_error, user_msg.latency_ms,
                # P8 MCP：user 侧始终为空
                None, None,
                user_msg.created_at,
            ),
        )
        if assistant_msg is not None:
            await execute_write(
                insert_assistant_sql,
                (
                    assistant_msg.message_id, assistant_msg.session_id, int(assistant_msg.user_id), assistant_msg.role, assistant_msg.content,
                    assistant_msg.rag_query_rewrite, assistant_msg.rag_retrieved_count, assistant_msg.rag_final_count,
                    assistant_msg.rag_docs_json, assistant_msg.rag_error, assistant_msg.latency_ms,
                    # P8 MCP
                    assistant_msg.mcp_tool_calls_json, assistant_msg.mcp_called_count,
                    assistant_msg.created_at,
                ),
            )
        await execute_write(
            update_session_sql,
            (new_title, new_count, now, now, session.session_id),
        )


# ============================================================
# 4. 主编排：search_only / chat_answer / chat_stream
# ============================================================
async def search_only(
    req: RagSearchOnlyRequest,
    *,
    user_id: int,
    role: UserRole,
) -> tuple[list[RetrievedDoc], list[GraphEntity], int, str | None, str | None]:
    """仅检索，不落库。返回 (final_docs, graph, raw_count, rewrite, degraded)。"""
    bundle: RetrievalBundle = await retrieve_three_channel(
        req.query,
        user_id=int(user_id),
        role=role,
        use_hyde=req.use_hyde,
        enable_graph=req.enable_graph,
        top_k=int(req.top_k),
        final_max_k=int(req.final_max_k),
        cutoff_drop_ratio=float(req.cutoff_drop_ratio),
    )
    return bundle.docs, bundle.graph_entities, bundle.raw_retrieved_count, bundle.rewrite_query, bundle.degraded_reason


async def _retrieve_and_bundle_for_chat(
    req: RagQueryRequest,
    *,
    user_id: int,
    role: UserRole,
) -> RetrievalBundle:
    return await retrieve_three_channel(
        req.query,
        user_id=int(user_id),
        role=role,
        use_hyde=req.use_hyde,
        enable_graph=req.enable_graph,
        top_k=int(req.top_k),
        final_max_k=int(req.final_max_k),
        cutoff_drop_ratio=float(req.cutoff_drop_ratio),
    )


async def chat_answer(
    req: RagQueryRequest,
    *,
    user_id: int,
    role: UserRole,
) -> RagAnswerResponse:
    """非流式问答：检索（await）→ MCP 工具调用(可选) → 生成 → 落库 → 组装响应。"""
    t0 = time.perf_counter()
    # 1) 会话：若传了 session_id 则校验 owner；否则临时会话不落库
    session: ChatSession | None = None
    if req.session_id:
        session = await _ensure_session_owner(req.session_id, user_id, role)

    # 2) 历史窗口
    history_turns = await _history_window(
        req.session_id, user_id, role, include_history=int(req.include_history),
    )

    # 3) 检索
    bundle = await _retrieve_and_bundle_for_chat(req, user_id=user_id, role=role)

    # 3.5) P8 MCP 工具调用（可选）→ 得到 summaries、注入片段、降级原因
    mcp_summaries: list[MCPToolCallSummary] = []
    mcp_context = ""
    mcp_degraded: str | None = None
    try:
        mcp_summaries, mcp_context, mcp_degraded = await run_chat_tool_calls(
            query=req.query,
            operator_user_id=int(user_id),
            session_id=(session.session_id if session else None),
            use_mcp_flag=bool(req.use_mcp_tools and getattr(settings, "USE_MCP_TOOL_CALLING", True)),
        )
    except Exception as exc:
        logger.warning(f"[P2 chat_answer] MCP 工具阶段异常（跳过）：{type(exc).__name__}: {exc}")
        mcp_degraded = f"MCP 工具阶段异常({type(exc).__name__})"

    # 4) 生成（带 MCP 上下文注入）
    answer, merged_deg_raw = await generate_answer(
        query=req.query,
        docs=bundle.docs,
        graph_entities=bundle.graph_entities,
        history_turns=history_turns,
        model=req.model,
        degraded_reason=bundle.degraded_reason,
        mcp_context=mcp_context,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    # 合并 MCP 降级原因（若有）
    deg_parts = [x for x in [merged_deg_raw, mcp_degraded] if x]
    merged_deg = "；".join(deg_parts) or None
    # 如果工具成功调用且结果存在，把 answer 开头补一段（本地规则兜底时 LLM 看不到 MCP 片段会被降级，这里显式拼接摘要）
    if mcp_summaries and "fallback_rule" in (merged_deg or ""):
        success_lines = [f"- 工具 {s.tool_name}：{s.result_summary}" for s in mcp_summaries if s.status == "success"]
        if success_lines:
            answer = "【工具调用摘要】\n" + "\n".join(success_lines) + "\n\n" + answer

    # 4.1) 推断 llm_model_used（简化：降级理由里 LLM 调用失败/本地规则兜底 → fallback_rule；否则用 req.model）
    llm_model_used = "fallback_rule" if (merged_deg and ("LLM 调用失败" in merged_deg or "规则兜底" in merged_deg)) else str(req.model or "fast")

    # 5) 落库（若有会话）
    message_id_user: str | None = None
    message_id_assistant: str | None = None
    mcp_json_s: str | None = None
    mcp_called_count_val: int | None = None
    if mcp_summaries:
        try:
            mcp_json_s = json.dumps([s.model_dump() for s in mcp_summaries], ensure_ascii=False)
        except Exception:
            mcp_json_s = None
        mcp_called_count_val = len(mcp_summaries)

    if session is not None:
        now = datetime.now()
        user_created_at = now
        try:
            asst_created_at = now + _MICROSECOND_STEP
        except Exception:
            asst_created_at = now
        user_msg = ChatMessage(
            message_id=_new_message_id(),
            session_id=session.session_id,
            user_id=int(user_id),
            role="user",
            content=req.query,
            created_at=user_created_at,
        )
        message_id_user = user_msg.message_id
        asst_msg = ChatMessage(
            message_id=_new_message_id(),
            session_id=session.session_id,
            user_id=int(user_id),
            role="assistant",
            content=answer,
            rag_query_rewrite=bundle.rewrite_query,
            rag_retrieved_count=int(bundle.raw_retrieved_count),
            rag_final_count=int(len(bundle.docs)),
            rag_docs_json=json.dumps([d.model_dump() for d in bundle.docs], ensure_ascii=False),
            rag_error=merged_deg,
            latency_ms=latency_ms,
            # P8 MCP
            mcp_tool_calls_json=mcp_json_s,
            mcp_called_count=mcp_called_count_val,
            created_at=asst_created_at,
        )
        await _append_messages_and_bump_session(session, user_msg=user_msg, assistant_msg=asst_msg)
        message_id_assistant = asst_msg.message_id

    # 6) 审计日志：任何会话/非会话、失败/降级情况都要写；失败不影响问答返回（insert_audit_log 内部已兜底告警）
    await _rag_insert_audit_log(
        user_id=int(user_id),
        role=role,
        query=req.query,
        rewrite_query=bundle.rewrite_query,
        retrieved_count=int(bundle.raw_retrieved_count),
        final_count=int(len(bundle.docs)),
        llm_model=llm_model_used,
        latency_ms=int(latency_ms),
        degraded_reason=merged_deg,
        is_stream=False,
        session_id=(session.session_id if session else None),
        user_message_id=message_id_user,
        assistant_message_id=message_id_assistant,
    )

    return RagAnswerResponse(
        session_id=(session.session_id if session else None),
        message_id=message_id_assistant,
        answer=answer,
        docs=bundle.docs,
        graph_entities=bundle.graph_entities,
        rewrite_query=bundle.rewrite_query,
        retrieved_count=int(bundle.raw_retrieved_count),
        final_count=int(len(bundle.docs)),
        latency_ms=latency_ms,
        degraded_reason=merged_deg,
        mcp_tool_calls=mcp_summaries,
    )


async def chat_stream(
    req: RagQueryRequest,
    *,
    user_id: int,
    role: UserRole,
):
    """
    流式问答：返回 (session, bundle, history_turns, token_aiter, build_finalize, mcp_summaries)。
    router 负责发送 SSE 事件；build_finalize(answer_text, latency_ms, degraded_extra, mcp_summaries) 会落库并返回汇总 dict。
    """
    t0 = time.perf_counter()

    session: ChatSession | None = None
    if req.session_id:
        session = await _ensure_session_owner(req.session_id, user_id, role)

    history_turns = await _history_window(
        req.session_id, user_id, role, include_history=int(req.include_history),
    )
    bundle = await _retrieve_and_bundle_for_chat(req, user_id=user_id, role=role)

    # P8 MCP 工具调用（流式前先同步完成）
    mcp_summaries: list[MCPToolCallSummary] = []
    mcp_context = ""
    mcp_degraded_stream: str | None = None
    try:
        mcp_summaries, mcp_context, mcp_degraded_stream = await run_chat_tool_calls(
            query=req.query,
            operator_user_id=int(user_id),
            session_id=(session.session_id if session else None),
            use_mcp_flag=bool(req.use_mcp_tools and getattr(settings, "USE_MCP_TOOL_CALLING", True)),
        )
    except Exception as exc:
        logger.warning(f"[P2 chat_stream] MCP 工具阶段异常（跳过）：{type(exc).__name__}: {exc}")
        mcp_degraded_stream = f"MCP 工具阶段异常({type(exc).__name__})"

    token_aiter = generate_stream(
        query=req.query,
        docs=bundle.docs,
        graph_entities=bundle.graph_entities,
        history_turns=history_turns,
        model=req.model,
        degraded_reason=bundle.degraded_reason,
        mcp_context=mcp_context,
    )

    async def build_finalize(answer_text: str, *, degraded_extra: str | None) -> dict:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        merged_deg_parts = [x for x in [bundle.degraded_reason, degraded_extra, mcp_degraded_stream] if x]
        merged_deg = "；".join(merged_deg_parts) or None

        # 工具结果前置（fallback_rule 时拼接）
        final_answer = answer_text
        if mcp_summaries and "fallback_rule" in (merged_deg or ""):
            succ_lines = [f"- 工具 {s.tool_name}：{s.result_summary}" for s in mcp_summaries if s.status == "success"]
            if succ_lines:
                final_answer = "【工具调用摘要】\n" + "\n".join(succ_lines) + "\n\n" + final_answer

        # 推断 llm_model_used（同非流式逻辑）
        llm_model_used = "fallback_rule" if (merged_deg and ("LLM 调用失败" in merged_deg or "规则兜底" in merged_deg)) else str(req.model or "fast")

        message_id_user: str | None = None
        message_id_assistant: str | None = None
        sess_id_out: str | None = None
        mcp_json_s: str | None = None
        mcp_called_count_val: int | None = None
        if mcp_summaries:
            try:
                mcp_json_s = json.dumps([s.model_dump() for s in mcp_summaries], ensure_ascii=False)
            except Exception:
                mcp_json_s = None
            mcp_called_count_val = len(mcp_summaries)

        if session is not None:
            now = datetime.now()
            user_created_at = now
            try:
                asst_created_at = now + _MICROSECOND_STEP
            except Exception:
                asst_created_at = now
            user_msg = ChatMessage(
                message_id=_new_message_id(),
                session_id=session.session_id,
                user_id=int(user_id),
                role="user",
                content=req.query,
                created_at=user_created_at,
            )
            message_id_user = user_msg.message_id
            asst_msg = ChatMessage(
                message_id=_new_message_id(),
                session_id=session.session_id,
                user_id=int(user_id),
                role="assistant",
                content=final_answer,
                rag_query_rewrite=bundle.rewrite_query,
                rag_retrieved_count=int(bundle.raw_retrieved_count),
                rag_final_count=int(len(bundle.docs)),
                rag_docs_json=json.dumps([d.model_dump() for d in bundle.docs], ensure_ascii=False),
                rag_error=merged_deg,
                latency_ms=latency_ms,
                mcp_tool_calls_json=mcp_json_s,
                mcp_called_count=mcp_called_count_val,
                created_at=asst_created_at,
            )
            await _append_messages_and_bump_session(session, user_msg=user_msg, assistant_msg=asst_msg)
            message_id_assistant = asst_msg.message_id
            sess_id_out = session.session_id

        # 写审计日志（失败不影响 SSE 返回）
        await _rag_insert_audit_log(
            user_id=int(user_id),
            role=role,
            query=req.query,
            rewrite_query=bundle.rewrite_query,
            retrieved_count=int(bundle.raw_retrieved_count),
            final_count=int(len(bundle.docs)),
            llm_model=llm_model_used,
            latency_ms=int(latency_ms),
            degraded_reason=merged_deg,
            is_stream=True,
            session_id=sess_id_out,
            user_message_id=message_id_user,
            assistant_message_id=message_id_assistant,
        )

        return {
            "session_id": sess_id_out,
            "message_id": message_id_assistant,
            "retrieved_count": int(bundle.raw_retrieved_count),
            "final_count": int(len(bundle.docs)),
            "latency_ms": latency_ms,
            "rewrite_query": bundle.rewrite_query,
            "degraded_reason": merged_deg,
            "mcp_tool_calls": [s.model_dump() for s in mcp_summaries],
        }

    return session, bundle, history_turns, token_aiter, build_finalize, mcp_summaries
