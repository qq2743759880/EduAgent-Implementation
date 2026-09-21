"""
P2 问答 Service：会话/消息持久化 + 检索 + 生成 编排。

设计：
- 所有 SQL 字段与 patch_chat_tables.sql 一致；字段缺失时接口不 500（由 SQL 先补列）
- 会话 session_id / 消息 message_id 都用短 uuid（可前端直接展示）
- 写操作全部走 aiomysql transaction 上下文；读操作 fetch_one/fetch_all 直接用
- 强约束：任何 session/消息都绑定 user_id；跨用户访问会抛 ValidationError，由 router 转 403
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta

from app.admin.rag_admin.service import insert_audit_log as _rag_insert_audit_log
from app.auth import UserRole
from app.chat.generator import generate_answer, generate_stream
from app.chat.retriever import RetrievalBundle, retrieve_three_channel
from app.ai.graph import run_agent as run_langgraph_agent
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
from app.chat.tool_calling import run_chat_tool_calls
from app.chat.flows.agent import run_agent_turn
from app.common.exceptions import NotFoundError, ValidationError
from app.common.logging import logger
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
    async with transaction() as (_conn, cur):
        # 事务内必须用共享 cur 执行，禁止嵌套 execute_write()（独立连接+自动提交，task04 #1 根因）
        await cur.execute(
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
    """会话列表：按 last_message_at 倒序（再 created_at 倒序）。

    [FEAT-WIRE-V2 #8 隔离修复] 旧版 admin 角色返回全库所有用户会话（"admin 全局"），
    用户实测缺陷：管理员对话列表混入他人会话。现一律按当前 user_id 过滤；
    admin 全局审计视图应另立管理端页面（FEAT-WIRE-V2 登记，本单不做）。"""
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


async def delete_session(user_id: int, session_id: str, role: UserRole) -> None:
    """
    软删会话（R-2 补丁，红线约束 12：禁止物理 DELETE）。

    - 归属校验复用 _ensure_session_owner：非 admin 必须是本人（否则 ValidationError(CHAT_SESSION_FORBIDDEN) → 403）；
      会话不存在或已软删（yn=0）→ NotFoundError → 404（重复删除天然 404，幂等语义）。
    - 删除后 list_sessions / get_session_history 均已过滤 yn=1，会话即刻从列表与历史查询消失。
    - 与流式落库竞态（task05 #4，已知接受）：删除与 LLM 回答落库并发时，落库的
      update_session_sql 带 `AND yn = 1` 会空更新 → 已删会话残留孤儿消息行（chat_message 有行、
      计数不 bump）；API 层均按 yn=1 过滤不可见，无数据泄漏，低概率、无用户可见后果，不修复。
    """
    await _ensure_session_owner(session_id, user_id, role)
    await execute_write(
        "UPDATE chat_session SET yn = 0, updated_at = %s WHERE session_id = %s AND yn = 1",
        (datetime.now(), session_id),
    )


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
    # title 回填：如果当前会话 title 还是 create_session 的默认「新会话 xxx」（create_session 默认
    # title = f"新会话 {session_id[-6:]}"，末尾是 uuid hex 字符，永远不含 "s_"，故用前缀「新会话 」匹配），
    # 用第 1 条 question 前 30 字回填（task05 修正轮：原 startswith("新会话 s_") 恒 False，回填永不触发）
    new_title = session.title
    if new_title.startswith("新会话 ") and user_msg.role == "user":
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
    # 竞态说明（task05 #4，已知接受，不修复）：`AND yn = 1` 使「删除会话」与「流式回答落库」
    # 并发时本 UPDATE 空更新（消息已写入 chat_message 但计数不 bump，孤儿消息行）。已删会话在
    # 列表/历史 API 均按 yn=1 过滤不可见，无用户可见后果，仅留脏数据行；低概率，注释说明即可。
    async with transaction() as (_conn, cur):
        # 事务内必须用共享 cur 执行，禁止嵌套 execute_write()（独立连接+自动提交，task04 #1 根因）
        await cur.execute(
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
            await cur.execute(
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
        await cur.execute(
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

    # 3) LangGraph Agent（LLM 决策 → 检索/工具 → 循环 → 生成）
    use_agent = bool(getattr(settings, "USE_AGENT_LOOP", True))
    # P2-9（dev-plan W2 R02 顺带修复）：plan 必须先初始化——USE_AGENT_LOOP=False 或
    # agent 异常回退时，下方 `if plan is None` 原先引用未赋值变量 → UnboundLocalError。
    plan = None
    if use_agent:
        try:
            agent_result = await run_langgraph_agent(
                query=req.query,
                user_id=int(user_id),
                session_id=(session.session_id if session else None),
            )
            answer = agent_result["answer"]
            # task39 GWT②：agent 链路的 degraded_reason（如 answer 节点 llm_failed、
            # reflect 达上限的 reflect_max_iter）此前被硬编码 None 丢弃 →
            # LLM 宕机时用户拿到的是规则兜底答案，却**看不到任何降级标识**，
            # 违反 §6.4「所有降级点写 degraded_reason + 前端展示部分功能降级中」。
            _agent_deg = agent_result.get("degraded_reason") or None
            bundle = RetrievalBundle(
                docs=[RetrievedDoc(**d) for d in agent_result.get("docs", [])],
                raw_retrieved_count=len(agent_result.get("docs", [])),
                graph_entities=[GraphEntity(**g) for g in agent_result.get("graph_entities", [])],
                rewrite_query=req.query,
                degraded_reason=_agent_deg,
            )
            mcp_summaries = agent_result.get("tool_results", [])
            plan = type("Plan", (), {"need_search": True, "query_rewrite": req.query})()
        except Exception as exc:
            logger.warning(f"[P2 chat_answer] LangGraph Agent 异常，回退检索先行：{type(exc).__name__}: {exc}")
            plan = None
    if plan is None:
        bundle = await _retrieve_and_bundle_for_chat(req, user_id=user_id, role=role)
        # 回退路径：用旧版 generate_answer
        answer = None

    # 检索改写后的 query
    gen_query = (plan.query_rewrite if plan and plan.query_rewrite else req.query)

    # LangGraph Agent 已经完成了全部流程（检索+工具+生成），跳过旧版 MCP 和 generate_answer
    if answer is None:
        # 旧版回退路径：MCP 工具调用 → generate_answer
        mcp_summaries: list[MCPToolCallSummary] = []
        mcp_context = ""
        mcp_degraded: str | None = None
        try:
            mcp_summaries, mcp_context, mcp_degraded = await run_chat_tool_calls(
                query=gen_query,
                operator_user_id=int(user_id),
                session_id=(session.session_id if session else None),
                use_mcp_flag=bool(req.use_mcp_tools and getattr(settings, "USE_MCP_TOOL_CALLING", True)),
            )
        except Exception as exc:
            logger.warning(f"[P2 chat_answer] MCP 工具阶段异常（跳过）：{type(exc).__name__}: {exc}")
            # CR-WNEXT2-exc-classname-leak-remaining：degraded_reason 进用户可见文案，去异常类名
            mcp_degraded = "MCP 工具阶段异常，已跳过（详见服务端日志）"

        answer, merged_deg_raw = await generate_answer(
            query=gen_query,
            docs=bundle.docs,
            graph_entities=bundle.graph_entities,
            history_turns=history_turns,
            model=req.model,
            degraded_reason=bundle.degraded_reason,
            mcp_context=mcp_context,
            strict_rag=(plan.need_search if plan else True),
        )
        merged_deg = "；".join([x for x in [merged_deg_raw, mcp_degraded] if x]) or None
    else:
        # LangGraph Agent 已生成答案
        # task39 GWT②：不再硬编码 None —— 透传 agent 的降级原因（llm_failed 等），
        # 使「降级答案」对用户可见，且 edu_degraded_total 与响应体口径一致。
        merged_deg = bundle.degraded_reason or None
        mcp_context = ""
        mcp_summaries = []
    latency_ms = int((time.perf_counter() - t0) * 1000)
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

    # task25 R7 / R01-b：会话结束异步记忆 ingest——R08 起传**完整对话窗**
    # （会话历史轮 + 本轮 query/answer 成对，防上下文缺 assistant 半边），
    # worker 内规则+LLM 抽取（显式触发/纠正/目标偏好 + 助手事实性陈述）。
    # 不 await、不 try-raise：无论如何都不阻塞应答链路（GWT①④ 异步隔离）
    # T9-C3：answer 为空串（LLM 空响应，sixnode.answer 仅异常兜底）→ 调用侧短路，不入记忆窗
    if answer and answer.strip():
        try:
            from app.ai.memory.service import build_turn_window, enqueue_turn
            window = build_turn_window(history_turns, query=req.query, answer=answer)
            asyncio.create_task(enqueue_turn(int(user_id), messages=window))
        except Exception:
            pass

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


def make_stream_finalize(
    *,
    req: RagQueryRequest,
    user_id: int,
    role: UserRole,
    session: ChatSession | None,
    bundle: RetrievalBundle,
    mcp_summaries: list[MCPToolCallSummary],
    mcp_degraded: str | None,
    t0: float,
    memory_history_window: list[tuple[str, str]] | None = None,
):
    """构造流式收束函数 build_finalize(answer_text, *, degraded_extra)（R02 抽取为工厂）。

    职责：拼接降级原因 → 工具摘要前置 → 落库（user+assistant 消息 + 会话计数）→ 审计日志
    → 异步记忆 ingest → 返回 done 帧 data（session_id/message_id/retrieved_count/final_count/
    latency_ms/rewrite_query/degraded_reason/mcp_tool_calls）。
    旧路径（service.chat_stream）与新路径（flows/graph_stream.py）共用本工厂，
    保证两执行体的落库/审计/done 语义单一事实源（audit P2-23 防漂移）。
    函数体 = 原 chat_stream.build_finalize 闭包原样迁移（行为逐字节一致）。
    R08：memory_history_window = 会话历史轮 [(role, content)]（chat_stream 传入）；
    graph_stream 旧调用不传 → None，记忆窗退化为本轮 query+answer 成对（行为兼容）。
    """

    async def build_finalize(answer_text: str, *, degraded_extra: str | None) -> dict:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        merged_deg_parts = [x for x in [bundle.degraded_reason, degraded_extra, mcp_degraded] if x]
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

        # task25 R7 / R01-b：流式会话结束异步记忆 ingest——R08 起传完整对话窗
        # （会话历史轮 + 本轮 query/answer 成对，防上下文缺 assistant 半边，与应答解耦）
        # T9-C3：收束 answer 为空串（模型零 token / 空响应）→ 调用侧短路，不入记忆窗
        memorized: list[str] = []
        if final_answer and final_answer.strip():
            # [REWORK P0-1/P0-2] 同步规则抽取：done 帧前落库（新名字当轮即可跨会话召回，
            # 5 秒内提问可答对——audit 实测异步链路 ~40s 为演示灾难）；LLM 深抽取仍走异步队列。
            try:
                from app.ai.memory.service import sync_extract_and_write
                memorized = await sync_extract_and_write(int(user_id), query=req.query)
            except Exception as exc:
                logger.warning(f"[chat] 同步记忆抽取失败（不影响 done 帧）: {exc}")
                memorized = []
            try:
                from app.ai.memory.service import build_turn_window, enqueue_turn
                window = build_turn_window(memory_history_window, query=req.query, answer=final_answer)
                asyncio.create_task(enqueue_turn(int(user_id), messages=window, skip_rule_extract=bool(memorized)))
            except Exception:
                pass

        return {
            "session_id": sess_id_out,
            "message_id": message_id_assistant,
            "retrieved_count": int(bundle.raw_retrieved_count),
            "final_count": int(len(bundle.docs)),
            "latency_ms": latency_ms,
            "rewrite_query": bundle.rewrite_query,
            "degraded_reason": merged_deg,
            "mcp_tool_calls": [s.model_dump() for s in mcp_summaries],
            "memorized": memorized,
        }

    return build_finalize


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

    # Agent 循环（LLM 意图决策 → 按需检索）——AGENT_LOOP 关闭时回退「检索先行」
    # P1-4：MCP 工具调用与决策并发（两者都基于 query 无数据依赖），省 MCP 串行耗时
    use_agent = bool(getattr(settings, "USE_AGENT_LOOP", True))
    plan = None

    async def _run_mcp() -> tuple[list[MCPToolCallSummary], str, str | None]:
        try:
            return await run_chat_tool_calls(
                query=req.query,  # 用原 query 提前匹配（决策改写只加关键词，启发式匹配不影响）
                operator_user_id=int(user_id),
                session_id=(session.session_id if session else None),
                use_mcp_flag=bool(req.use_mcp_tools and getattr(settings, "USE_MCP_TOOL_CALLING", True)),
            )
        except Exception as exc:
            logger.warning(f"[P2 chat_stream] MCP 工具阶段异常（跳过）：{type(exc).__name__}: {exc}")
            return [], "", "MCP 工具阶段异常，已跳过（详见服务端日志）"

    mcp_future = asyncio.create_task(_run_mcp())

    try:
        if use_agent:
            agent_res = await run_agent_turn(
                req.query,
                user_id=user_id,
                role=role,
                use_hyde=req.use_hyde,
                enable_graph=req.enable_graph,
                top_k=int(req.top_k),
                final_max_k=int(req.final_max_k),
                cutoff_drop_ratio=float(req.cutoff_drop_ratio),
                session_id=(session.session_id if session else None),
            )
            plan = agent_res["plan"]
            bundle = agent_res["bundle"]
        else:
            plan = None
    except Exception as exc:
        logger.warning(f"[P2 chat_stream] Agent 决策层异常，回退检索先行：{type(exc).__name__}: {exc}")
        plan = None
    try:
        if plan is None:
            bundle = await _retrieve_and_bundle_for_chat(req, user_id=user_id, role=role)
    except Exception as exc:
        logger.warning(f"[P2 chat_stream] 检索兜底失败（返回空 bundle）：{type(exc).__name__}: {exc}")
        bundle = RetrievalBundle(
            docs=[], raw_retrieved_count=0, graph_entities=[],
            rewrite_query=req.query, degraded_reason=None,
        )

    # 检索改写后的 query（决策改写 或 原 query）
    gen_query = (plan.query_rewrite if plan and plan.query_rewrite else req.query)

    # 等 MCP 结果（已与决策并行，此处合并）
    mcp_summaries, mcp_context, mcp_degraded_stream = await mcp_future

    token_aiter = generate_stream(
        query=gen_query,
        docs=bundle.docs,
        graph_entities=bundle.graph_entities,
        history_turns=history_turns,
        model=req.model,
        degraded_reason=bundle.degraded_reason,
        mcp_context=mcp_context,
        strict_rag=(plan.need_search if plan else True),
    )

    # R02：finalize 落库逻辑抽取为模块级工厂 make_stream_finalize（与图路径适配层共用同一实现）
    # R08：memory_history_window 传入会话历史轮 → 记忆窗=历史+本轮成对（完整对话窗）
    build_finalize = make_stream_finalize(
        req=req, user_id=user_id, role=role, session=session, bundle=bundle,
        mcp_summaries=mcp_summaries, mcp_degraded=mcp_degraded_stream, t0=t0,
        memory_history_window=history_turns,
    )

    return session, bundle, history_turns, token_aiter, build_finalize, mcp_summaries
