# -*- coding: utf-8 -*-
"""R02 流式主路径 LangGraph 适配层：POST /api/chat/stream 的执行体从
flows/agent.run_agent_turn（普通函数）切换为六节点图 graph.astream（dev-plan-reshape-r W2，
audit P0-2 修复：「前端唯一主路径完全绕过 LangGraph，图能力对真实用户不生效」）。

设计（SSE 契约冻结 contracts/reshape-a.json，前端零改动）：
- 事件序列 start → retrieval → token(n) → done/error 逐字段保持：token 帧 data={"delta": ...}，
  done 帧 data 内嵌统一壳 {code:0, message:"ok", data:{...}}；两段式错误模型不变（建连前同步
  HTTP，建连后 event:error 可区分错误码）；落库失败 error(CHAT_PERSIST_FAIL)+降级 done 兜底。
- token 流：sixnode.answer 经 LangGraph custom stream writer 推增量（configurable.stream_tokens
  逐请求门控，普通 ainvoke 行为零变化）；本层以 stream_mode=["updates","custom"] 双通道消费，
  token 先于 retrieval 到达时缓冲重放（保 start→retrieval→token 帧序契约）。
- retrieval 帧：fan_out 节点更新携带 state.retrieval（R02 检索产物回填）；chitchat 直连
  路径（route→answer）按旧路径口径发空 docs retrieval 帧；MCP 工具摘要与旧路径同样并行预取、
  随 retrieval 帧下发。
- guard 移植（audit P1-4：防过载闸只护非流式）：本层 acquire/release 覆盖主路径，语义对齐
  graph.run_agent（拒绝=友好提示作为答案流出 + degraded_reason，不抛 5xx）；release 挂 finally
  全路径成对（含图执行前异常/客户端断连）。
- thread_id（audit P2-8 / R02-c）：resolve_thread_id——匿名请求每请求独立 anon-{uuid} 线程，
  禁 `task24-{user_id}` 共享；checkpoint 键 `edu:ckpt:{thread_id}` 可 grep 实证。
- 落库/审计/记忆 ingest：复用 service.make_stream_finalize（与旧路径单一事实源，防 P2-23 漂移）。

KB 对标（F-C01-002 LangGraph）：
- 通道语义：AgentState 各字段 LastValue（最新值覆盖）+ messages add_messages（Binop 追加）；
  token 增量经 stream/custom 通道（节点内 StreamWriter）旁路状态通道，不污染 checkpoint。
- checkpointer：PlainRedisSaver 逐线程快照（thread_id 隔离），本层 config.configurable.thread_id
  即其线程键；durable execution 语义保留。
- 流模式：updates（节点更新→驱动 retrieval 帧）+ custom（token 增量），双流交织保序。
"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

from fastapi.responses import StreamingResponse
from loguru import logger
from langgraph.types import Command

from app.ai.graph import _empty_state, _ensure_agent_graph, resolve_thread_id
from app.auth import UserRole
from app.chat.schemas import RagQueryRequest, SseEventType
from app.chat.service import _ensure_session_owner, make_stream_finalize
from app.chat.sse import map_stream_exception, sse_line
from app.common.error_codes import CHAT_PERSIST_FAIL
from app.config import settings


# ============================================================
# R11 HITL（contracts/reshape-r-hitl.json）：挂起/决策 Redis 键 + 读写辅助
#   hitl:pending:{thread_id}        → pending_confirm payload（TTL=timeout_s=300；resume 端点校验存在性）
#   hitl:pending_args:{thread_id}   → pending_confirm 负载中的 args（W-NEXT-CHATFLOW-001 Track A）
#   hitl:decision:{thread_id}       → {"action","reason","created_at"}（TTL=300；续流时一次性消费）
# ============================================================
_HITL_PENDING_PREFIX = "hitl:pending:"
_HITL_PENDING_ARGS_PREFIX = "hitl:pending_args:"
_HITL_DECISION_PREFIX = "hitl:decision:"


def _hitl_resume_ttl() -> int:
    """resume 决策/挂起标记 TTL（秒）。契约 timeout_s=300；测试可注入短 TTL 验超时。"""
    return int(getattr(settings, "HITL_RESUME_TTL", 300))


async def _hitl_redis() -> Any | None:
    try:
        from app.database import get_redis

        return get_redis()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[graph_stream.hitl] Redis 不可用: {type(exc).__name__}: {exc}")
        return None


async def _mark_hitl_pending(thread_id: str, payload: dict) -> None:
    """interrupt 捕获后写挂起标记（resume 端点据此判定 thread_id 有效/未过期）。

    W-NEXT-CHATFLOW-001 Track A（CR-T11b-A 治本）：同时把 payload['args']（=经 _enrich
    的 pending_confirm 负载）写入独立 Redis key `hitl:pending_args:{thread_id}`，
    同 TTL，resume 续流时由 graph_stream 直接读出 → run_chat_tool_calls 经
    pending_args_override 优先覆盖 plan.args → handler 校验 source_files 必通过 →
    真实落 task 行（原 chat 路径默认 task +0 的根因被堵死）。
    """
    r = await _hitl_redis()
    if r is None:
        return
    ttl = _hitl_resume_ttl()
    try:
        await r.set(
            f"{_HITL_PENDING_PREFIX}{thread_id}",
            json.dumps(payload, ensure_ascii=False),
            ex=ttl,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[graph_stream.hitl] 写 pending 标记失败: {type(exc).__name__}: {exc}")
    # Track A：把挂起时的 args 也单独缓存一份（与 pending key 同 TTL），
    # 供 confirm 续流期（MCP 并行预取前）一次性读取。resume 端点会 delete hitl:pending:* ，
    # 但本 args key **不被消费**，允许续流与原 hitl 解耦——多轮 / 跨进程均可读。
    try:
        tool_name = str(payload.get("tool_name") or "")
        args_blob = payload.get("args") or {}
        if tool_name and isinstance(args_blob, dict) and args_blob:
            await r.set(
                f"{_HITL_PENDING_ARGS_PREFIX}{thread_id}",
                json.dumps({"tool_name": tool_name, "args": dict(args_blob)}, ensure_ascii=False),
                ex=ttl,
            )
            logger.info(
                f"[graph_stream.hitl] pending_args 缓存写入 thread_id={thread_id}"
                f" tool={tool_name} keys={list(args_blob.keys())}"
            )
        else:
            logger.info(
                f"[graph_stream.hitl] pending_args 跳过：tool_name={tool_name} args_empty={not args_blob}"
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[graph_stream.hitl] pending_args 缓存写入失败: {type(exc).__name__}: {exc}")


async def _pop_hitl_decision(thread_id: str) -> dict | None:
    """读并删除该 thread_id 的 resume 决策（一次性消费）；无 → None（正常新会话）。"""
    r = await _hitl_redis()
    if r is None:
        return None
    key = f"{_HITL_DECISION_PREFIX}{thread_id}"
    try:
        raw = await r.get(key)
        if not raw:
            return None
        await r.delete(key)
        d = json.loads(raw)
        return d if isinstance(d, dict) else None
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[graph_stream.hitl] 读决策失败: {type(exc).__name__}: {exc}")
        return None


async def _peek_hitl_pending_args(thread_id: str) -> dict | None:
    """W-NEXT-CHATFLOW-001 Track A：续流期（confirm/reject 任意一侧）非破坏性读
    `hitl:pending_args:{thread_id}`，供 run_chat_tool_calls 在 _parse_heuristic 后
    以 pending_args_override 覆盖 plan.args。读失败 / 键不存在 → None（不阻断流）。

    返回 dict：`{"tool_name": str, "args": dict}` 或 None。
    """
    r = await _hitl_redis()
    if r is None:
        return None
    key = f"{_HITL_PENDING_ARGS_PREFIX}{thread_id}"
    try:
        raw = await r.get(key)
        if not raw:
            return None
        d = json.loads(raw)
        if not isinstance(d, dict):
            return None
        return {"tool_name": str(d.get("tool_name") or ""), "args": dict(d.get("args") or {})}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[graph_stream.hitl] pending_args 读失败: {type(exc).__name__}: {exc}")
        return None


async def _drop_hitl_pending_args(thread_id: str) -> None:
    """W-NEXT-CHATFLOW-001 Track A 收尾：confirm 续流成功完成（或 reject 收束后）
    清掉 pending_args 缓存——避免悬挂 + 防同一 thread_id 后续被旧 args 覆盖新 args。
    单写者层（互斥 variant）不强制，掉一次 best-effort；失败仅日志，绝不阻断主路径。
    """
    r = await _hitl_redis()
    if r is None:
        return
    try:
        await r.delete(f"{_HITL_PENDING_ARGS_PREFIX}{thread_id}")
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[graph_stream.hitl] pending_args 收尾失败: {type(exc).__name__}: {exc}")


# ── HITL 口径常量（契约 reshape-r-hitl.json 唯一词表）：confirm=执行 / reject=拒绝执行 ──
# resume 端点 Literal 只允许 confirm|reject（router.py:397），本层必须以同一组词作续流放行
# 判断，禁止 approve/confirm 混用（CR-T11-B：原实现认 "approve"，而契约只发 "confirm"，
# 导致 admin 确认后永不真执行）。把"词表归一"收敛到单一常量 + 单一分类函数，口径一致
# 由构造保证（任何调用方都只能消费同一份词表），并让分类逻辑可被集成测试直接断言。
_RESUME_CONFIRM = "confirm"
_RESUME_REJECT = "reject"


def _classify_hitl_resume(action: str) -> tuple:
    """将 resume action 归一分类为 (kind, notice, degraded_reason)。

    kind  ∈ {"execute", "rejected", "expired"}
      - execute  = confirm：批准执行（mcp_hitl_decision=True 放行写类工具）
      - rejected = reject ：0 执行 + 拒绝上下文收束
      - expired  = 其它   ：该确认已失效（契约只允许 confirm|reject，此为防御分支）
    """
    a = str(action or "").strip().lower()
    if a == _RESUME_CONFIRM:
        return ("execute", None, None)
    if a == _RESUME_REJECT:
        return (
            "rejected",
            "已取消该高风险操作，工具未执行，也没有发生任何数据变更。",
            "hitl_rejected_no_pending",
        )
    return (
        "expired",
        "该确认已失效：待确认的操作已过期或不存在，本次未执行任何写操作。如需继续，请重新发起请求。",
        "hitl_confirm_expired_no_pending",
    )


def _enrich_hitl_pending_payload(payload: dict, thread_id: str) -> dict:
    """把 pending_confirm 负载补全为契约定死的五字段（CR-T11-A）。

    tool_calling._pending_payload 只带 tool_name/args（缺 thread_id/risk_level/timeout_s），
    契约 reshape-r-hitl.json 的 sse_event.payload 要求五字段 {thread_id, tool_name, args,
    risk_level, timeout_s}。此处就地补全：
      - thread_id ：本层已解析的线程键（影响前端能否取到它去调 /resume）；
      - risk_level：与图路径同源用 langgraph_agent._hitl_risk_level 真实分类
                    （写类→high/medium，只读→None），None 兜底 "low" 保契约枚举合法；
      - timeout_s ：契约值 300。
    """
    from app.chat.flows.langgraph_agent import _hitl_risk_level

    _enriched = dict(payload or {})
    _enriched["thread_id"] = thread_id
    _enriched["risk_level"] = _hitl_risk_level(str(_enriched.get("tool_name") or "")) or "low"
    _enriched["timeout_s"] = 300
    return _enriched


class _DictModel(SimpleNamespace):
    """dict → 提供 model_dump() 的适配对象（make_stream_finalize 落库用 d.model_dump()）。"""

    def model_dump(self) -> dict:  # noqa: D102
        return dict(self.__dict__["_raw"])


def _make_lite_bundle(retrieval: dict) -> SimpleNamespace:
    """把 state.retrieval dict 适配为 make_stream_finalize 需要的 bundle 形状（duck typing）。"""
    retrieval = retrieval if isinstance(retrieval, dict) else {}
    return SimpleNamespace(
        docs=[_DictModel(_raw=d) for d in (retrieval.get("docs") or [])],
        graph_entities=[_DictModel(_raw=g) for g in (retrieval.get("graph_entities") or [])],
        raw_retrieved_count=int(retrieval.get("retrieved_count") or 0),
        rewrite_query=retrieval.get("rewrite_query"),
        degraded_reason=retrieval.get("degraded_reason"),
    )


async def graph_stream_sse(
    req: RagQueryRequest,
    *,
    user_id: int,
    role: UserRole,
) -> StreamingResponse:
    """图执行体 SSE 入口。建连前阶段（会话校验）抛异常 → router 转 HTTP 状态码（契约第一段）。"""
    # 建连前：会话归属校验（与旧路径 service.chat_stream 同源语义）
    session = None
    if req.session_id:
        # R11 HITL 续流专线：anon- 前缀是 LangGraph checkpoint 线程 id 而非真实会话
        # （新会话首问即触发中断时 thread_id=anon-{uuid}，契约要求以同 thread_id 重开续跑），
        # 跳过会话归属校验；真实会话照常校验 owner。
        if str(req.session_id).startswith("anon-"):
            session = None
        else:
            session = await _ensure_session_owner(req.session_id, user_id, role)

    # R02-c：thread_id——有 session 用 session；匿名请求每请求独立 uuid（禁 task24-{user_id} 共享）
    thread_id = resolve_thread_id(req.session_id, user_id)

    async def _gen() -> AsyncGenerator[bytes, None]:
        t0 = time.perf_counter()
        session_id_out = session.session_id if session else None

        # CR-1 方案②：resume 决策提前消费（写类挂起由流层承载，不依赖图 interrupt）。
        # 必须在 MCP 并行预取启动前确定 hitl_decision/是否抑制 MCP，
        # 避免「续跑确认」与「挂起/执行」竞态。
        resume_decision = await _pop_hitl_decision(thread_id)
        _resume_action = str((resume_decision or {}).get("action") or "").strip().lower()
        # CR-T11-B（契约对齐）：以 _classify_hitl_resume 单一词表归一 confirm|reject——
        # confirm=批准执行（mcp_hitl_decision=True 放行写类工具），reject=拒绝执行（抑制 MCP）。
        # 原实现认 "approve"，而契约/前端只发 "confirm" → admin 点确认后永不真执行（主链路断裂）。
        _resume_kind, _resume_notice, _resume_deg = _classify_hitl_resume(_resume_action)
        mcp_hitl_decision: bool | None = True if _resume_kind == "execute" else None
        _suppress_mcp = _resume_kind == "rejected"

        # 0) start 帧（先建连先发，与旧路径一致）
        yield sse_line(SseEventType.START.value, {
            "session_id": session_id_out,
            "query": req.query,
        })

        # ── guard 移植（audit P1-4）：主路径准入闸（与 graph.run_agent 同语义）──
        guard_entry: dict | None = None
        try:
            from app.ai.guard import default_guard

            _request_meta = {
                "query": (req.query or "")[:4000],
                "max_tokens": int(settings.LLM_MAX_TOKENS),
            }
            guard_entry = await default_guard().acquire(int(user_id), request_meta=_request_meta)
        except Exception as exc:  # noqa: BLE001 — fail-open（不阻塞主路径）
            logger.warning(f"[graph_stream.guard] 防过载闸异常，fail-open: {type(exc).__name__}: {exc}")
            guard_entry = None
        guard_held = bool(guard_entry and guard_entry.get("ok"))

        # P8 MCP 工具（启发式）并行预取——与旧路径 service.chat_stream 相同编排
        mcp_summaries: list = []
        mcp_context = ""
        mcp_degraded: str | None = None
        # C-W1-③（AUTO20 T8）：六节点图内 fan_out 透传的 MCP 工具凭据条数（见 fan_out update
        # 消费处）。_await_mcp 收口旧 MCP 预取时若把 mcp_summaries 整体替换，需先把图内凭据
        # 摘出来保留（两来源合并：图路径真执行凭据 + 旧启发式预取凭据，二者不重复产生）。
        graph_receipts_count = 0

        # CR-1 方案②：写类挂起流层状态（不依赖图 interrupt）——
        # held_hitl_payload 非 None → 写类工具已挂起（待 confirm/reject），流收束；
        # stream_held 已发 pending_confirm + done，停止消费图。
        held_hitl_payload: dict | None = None
        stream_held = False

        async def _run_mcp():
            from app.chat.tool_calling import run_chat_tool_calls

            nonlocal held_hitl_payload

            async def _hold_for_confirm(payload: dict) -> bool:
                nonlocal held_hitl_payload
                # CR-T11-A（契约补全）：_enrich_hitl_pending_payload 把契约定死的五字段
                # {thread_id, tool_name, args, risk_level, timeout_s} 补全，使 real 发出的
                # pending_confirm 帧与 contract reshape-r-hitl.json 的 sse_event.payload
                # 逐字段对齐——前端确认卡才能取到 thread_id 续流、risk_level 渲染风险级。
                _enriched = _enrich_hitl_pending_payload(payload, thread_id)
                await _mark_hitl_pending(thread_id, _enriched)
                held_hitl_payload = _enriched
                logger.info(
                    f"[graph_stream] 写类工具挂起（方案②）thread_id={thread_id}"
                    f" tool={_enriched.get('tool_name')} role={_enriched.get('role')}"
                )
                return True

            # W-NEXT-CHATFLOW-001 Track A（CR-T11b-A 治本）：HITL confirm 续流期
            # （mcp_hitl_decision=True 即对应 kind=="execute"）→ 主动从 Redis 读 pending_args
            # 缓存 → 构造 pending_args_override（{tool_name: args}）→ 传给
            # run_chat_tool_calls 优先覆盖 plan.args。
            #   - 命中：续流不再依赖 LLM 续流 generate 节点工具调用决策；
            #   - 未命中（首轮 / 无 HITL / args 全空）：传空 dict，启发式兜底仍生效（Track B）。
            #   - reject / expired / Redis 不可达：均 fallback 不阻断主路径。
            _pending_args_override: dict[str, dict] = {}
            if mcp_hitl_decision is True:
                _cached = await _peek_hitl_pending_args(thread_id)
                if _cached and _cached.get("tool_name") and _cached.get("args"):
                    _pending_args_override = {_cached["tool_name"]: _cached["args"]}
                    logger.info(
                        f"[graph_stream] pending_args 命中续流 thread_id={thread_id}"
                        f" tool={_cached['tool_name']} keys={list(_cached['args'].keys())}"
                    )
                else:
                    logger.info(
                        f"[graph_stream] pending_args 未命中（fallback 启发式兜底）thread_id={thread_id}"
                    )

            try:
                return await run_chat_tool_calls(
                    query=req.query,
                    operator_user_id=int(user_id),
                    session_id=session_id_out,
                    use_mcp_flag=bool(req.use_mcp_tools and getattr(settings, "USE_MCP_TOOL_CALLING", True)),
                    hitl_decision=mcp_hitl_decision,
                    on_write_class_pending=_hold_for_confirm,
                    pending_args_override=(_pending_args_override or None),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[graph_stream] MCP 工具阶段异常（跳过）：{type(exc).__name__}: {exc}")
                # degraded_reason 会经 make_stream_finalize 进用户可见的 done 帧 → 只给稳定文案，
                # 不把内部异常类名泄给用户（类名只进 logger，见上行）。
                return [], "", "MCP 工具阶段异常（已跳过）"

        mcp_task = (
            asyncio.ensure_future(_run_mcp())
            if not (guard_entry is not None and not guard_entry.get("ok")) and not _suppress_mcp
            else None
        )

        # ── 共享状态 ──
        retrieval_payload: dict | None = None     # retrieval 帧体（docs/graph_entities/...）
        retrieval_emitted = False
        pending_tokens: list[str] = []            # retrieval 帧未发前到达的 token（保帧序）
        answer_parts: list[str] = []              # token 累加（j.delta 语义：拼接=最终答案）
        final_updates: dict = {}                  # 各节点更新合并（LastValue 覆盖语义）
        ttft_retrieval_ms: int | None = None
        ttft_first_token_ms: int | None = None
        # R02-tail profile：各节点 update 到达时刻（ms since t0，含 checkpoint 保存开销）
        node_arrivals: dict[str, int] = {}

        async def _await_mcp() -> None:
            nonlocal mcp_summaries, mcp_context, mcp_degraded, graph_receipts_count
            if mcp_task is not None:
                # C-W1-③：先摘出图内凭据（fan_out 追加项），防止下方整体替换把真凭据冲掉
                _graph_items = mcp_summaries[len(mcp_summaries) - graph_receipts_count:] \
                    if graph_receipts_count and graph_receipts_count <= len(mcp_summaries) else []
                try:
                    mcp_summaries, mcp_context, mcp_degraded = await mcp_task
                except Exception as exc:  # noqa: BLE001 — MCP 失败不影响主响应
                    mcp_summaries, mcp_context, mcp_degraded = [], "", "MCP 工具阶段异常（已跳过）"
                if _graph_items:
                    mcp_summaries = list(mcp_summaries) + list(_graph_items)

        async def _emit_retrieval() -> AsyncGenerator[bytes, None]:
            """组装并发送 retrieval 帧（等 MCP 并行预取收口，保与旧路径帧内容对齐）。"""
            nonlocal retrieval_emitted, ttft_retrieval_ms, held_hitl_payload, stream_held
            await _await_mcp()
            if held_hitl_payload is not None:
                # CR-1 方案②：写类挂起 → pending_confirm 帧 + done(awaiting_human_confirm)，
                # 流收束待用户 confirm/reject 后同 thread_id 重开续跑（不落库，与图 interrupt 路径一致）。
                yield sse_line("pending_confirm", held_hitl_payload)
                yield sse_line(SseEventType.DONE.value, {"code": 0, "message": "ok", "data": {
                    "session_id": session_id_out, "message_id": None,
                    "retrieved_count": int((retrieval_payload or {}).get("retrieved_count") or 0),
                    "final_count": len((retrieval_payload or {}).get("docs") or []),
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "rewrite_query": (retrieval_payload or {}).get("rewrite_query"),
                    "degraded_reason": "awaiting_human_confirm",
                }})
                retrieval_emitted = True
                stream_held = True
                return
            payload = dict(retrieval_payload or {})
            yield sse_line(SseEventType.RETRIEVAL_DONE.value, {
                "docs": payload.get("docs") or [],
                "graph_entities": payload.get("graph_entities") or [],
                "retrieved_count": int(payload.get("retrieved_count") or 0),
                "final_count": len(payload.get("docs") or []),
                "rewrite_query": payload.get("rewrite_query"),
                "degraded_reason": payload.get("degraded_reason"),
                "mcp_tool_calls": [s.model_dump() for s in mcp_summaries],
            })
            retrieval_emitted = True
            ttft_retrieval_ms = int((time.perf_counter() - t0) * 1000)

        async def _finish(degraded_extra: str | None) -> AsyncGenerator[bytes, None]:
            """收束：finalize（落库+审计+记忆 ingest，与旧路径共用工厂）→ done/降级兜底帧。"""
            answer_text = "".join(answer_parts)
            retrieval = retrieval_payload or {}
            _finalize = make_stream_finalize(
                req=req, user_id=user_id, role=role, session=session,
                bundle=_make_lite_bundle(retrieval),
                mcp_summaries=mcp_summaries, mcp_degraded=mcp_degraded, t0=t0,
            )
            try:
                final_info = await _finalize(answer_text, degraded_extra=degraded_extra)
            except Exception as exc:  # noqa: BLE001
                # 两段式错误模型 · 第三段：落库失败 → error(CHAT_PERSIST_FAIL) + 降级 done 兜底（不静默）
                logger.warning(f"[graph_stream] 落库失败，发 error 事件：{CHAT_PERSIST_FAIL} ({exc})")
                yield sse_line(SseEventType.ERROR.value, {
                    "code": CHAT_PERSIST_FAIL,
                    "message": "答案生成成功但落库失败（内容未保存到会话）",
                    "generated_tokens": len(answer_parts),
                    "session_id": session_id_out,
                    "message_id": None,
                })
                yield sse_line(SseEventType.DONE.value, {
                    "code": 0, "message": "ok",
                    "data": {
                        "session_id": session_id_out, "message_id": None,
                        "retrieved_count": int(retrieval.get("retrieved_count") or 0),
                        "final_count": len(retrieval.get("docs") or []),
                        "latency_ms": 0,
                        "rewrite_query": retrieval.get("rewrite_query"),
                        "degraded_reason": "答案已生成但流式落库失败：未入库",
                    },
                })
                return
            yield sse_line(SseEventType.DONE.value, {"code": 0, "message": "ok", "data": final_info})

        try:
            if guard_entry is not None and not guard_entry.get("ok"):
                # guard 拒绝：与 graph.run_agent 同语义——友好提示作为答案流出 + degraded_reason
                busy_answer = guard_entry.get("message", "服务繁忙，请稍后重试")
                retrieval_payload = {
                    "docs": [], "graph_entities": [], "retrieved_count": 0,
                    "rewrite_query": req.query, "degraded_reason": guard_entry.get("reason"),
                }
                async for frame in _emit_retrieval():
                    yield frame
                for i in range(0, len(busy_answer), 8):
                    chunk = busy_answer[i:i + 8]
                    answer_parts.append(chunk)
                    yield sse_line(SseEventType.TOKEN.value, {"delta": chunk})
                async for frame in _finish(degraded_extra=None):
                    yield frame
                return

            g = await _ensure_agent_graph()
            # R11 续流驱动 + CR-1 方案②：resume 决策已在 `_gen` 顶部提前消费
            # （mcp_hitl_decision 据此在 MCP 预取前确定，避免竞态）。此处只判定
            # 「图 interrupt 挂起」与「流层挂起」两种承载：
            #   图 checkpoint 有 pending interrupt → Command(resume) 交给图续跑（旧 R11 路径）；
            #   无图挂起 → 方案②流层承载：confirm → 正常续跑（MCP 带 hitl_decision 批准执行）；
            #                          reject → 拒绝上下文收束；其它 → 确认失效收束。
            resume_decision_for_graph: dict | None = None
            if resume_decision is not None:
                logger.info(f"[graph_stream] HITL resume 续跑 thread_id={thread_id} decision={_resume_action or 'unknown'}")
                # T8-C2 修复：Redis 有决策 ≠ 图仍挂起。若 checkpoint 已丢失/被其它实例消费/确认已超时，
                # 图本身没有 pending interrupt，此时把 Command(resume=...) 丢进去只会静默按新会话跑完
                # ——用户以为"确认执行了"，实际写类工具零执行且无任何提示（静默吞）。
                # 先探明挂起态，无挂起 → 方案②分流（confirm 正常续跑 / reject 明确收束），绝不假装续跑。
                _probe_cfg = {"configurable": {"thread_id": thread_id}}
                _has_pending = False
                try:
                    _snap = await g.aget_state(_probe_cfg)
                    _has_pending = bool(getattr(_snap, "next", None))
                except Exception as exc:  # noqa: BLE001 — 探测失败按「无挂起」处置（保守：不执行写操作）
                    logger.warning(f"[graph_stream] HITL 挂起态探测失败（按无挂起处置）: {type(exc).__name__}: {exc}")
                if _has_pending:
                    resume_decision_for_graph = resume_decision
                else:
                    # 方案②分流：kind=execute（confirm）→ 正常续跑（mcp_hitl_decision=True 已
                    # 在顶部放行，写类工具经 executor 批准执行）；kind=rejected → 拒绝上下文收束；
                    # kind=expired（防御）→ 确认失效收束。terminology 单一词表，杜绝口径漂移。
                    _notice = _resume_notice
                    _deg = _resume_deg
                if _notice is not None:
                    logger.warning(
                        f"[graph_stream] HITL 决策无可续挂起（action={_resume_action or 'unknown'}）"
                        f" thread_id={thread_id} → {_deg}"
                    )
                    retrieval_payload = {
                        "docs": [], "graph_entities": [], "retrieved_count": 0,
                        "rewrite_query": req.query, "degraded_reason": _deg,
                    }
                    async for frame in _emit_retrieval():
                        yield frame
                    for i in range(0, len(_notice), 8):
                        chunk = _notice[i:i + 8]
                        answer_parts.append(chunk)
                        yield sse_line(SseEventType.TOKEN.value, {"delta": chunk})
                    async for frame in _finish(degraded_extra=None):
                        yield frame
                    return
            state = _empty_state(req.query, user_id=int(user_id), session_id=req.session_id)
            config = {"configurable": {"thread_id": thread_id, "stream_tokens": True}}
            try:
                async for mode, payload in g.astream(
                    Command(resume=resume_decision_for_graph) if resume_decision_for_graph is not None else state,
                    config,
                    stream_mode=["updates", "custom"],
                ):
                    if mode == "updates" and isinstance(payload, dict):
                        for node, update in payload.items():
                            # R11：图内 interrupt() 挂起 → pending_confirm 帧 + Redis 挂起标记
                            # （写类工具未执行；流发完本帧即收束，待用户 confirm/reject 后重开续跑）
                            if node == "__interrupt__":
                                intr_items = update if isinstance(update, (tuple, list)) else (update,)
                                for intr in intr_items:
                                    value = getattr(intr, "value", intr)
                                    if isinstance(value, dict) and value.get("tool_name"):
                                        logger.info(f"[graph_stream] HITL 中断捕获: {value.get('tool_name')}")
                                        await _mark_hitl_pending(thread_id, value)
                                        yield sse_line("pending_confirm", value)
                                yield sse_line(SseEventType.DONE.value, {"code": 0, "message": "ok", "data": {
                                    "session_id": session_id_out, "message_id": None,
                                    "retrieved_count": int((retrieval_payload or {}).get("retrieved_count") or 0),
                                    "final_count": len((retrieval_payload or {}).get("docs") or []),
                                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                                    "rewrite_query": (retrieval_payload or {}).get("rewrite_query"),
                                    "degraded_reason": "awaiting_human_confirm",
                                }})
                                logger.info(f"[graph_stream] HITL 中断，流挂起收束（待 resume）: {thread_id}")
                                return
                            if not isinstance(update, dict):
                                continue
                            if node not in node_arrivals:
                                node_arrivals[node] = int((time.perf_counter() - t0) * 1000)
                            final_updates[node] = update
                            # chitchat 直连（route→answer，无 fan_out）：按旧路径口径发空 docs retrieval 帧
                            if node == "route" and update.get("intent") == "chitchat" and retrieval_payload is None:
                                retrieval_payload = {
                                    "docs": [], "graph_entities": [], "retrieved_count": 0,
                                    "rewrite_query": req.query, "degraded_reason": None,
                                }
                            if node == "fan_out" and isinstance(update.get("retrieval"), dict):
                                retrieval_payload = update["retrieval"]
                            # C-W1-③（AUTO20 T8）：fan_out 节点透传的 MCP 工具执行凭据
                            # （state.tool_receipts）→ 映射 MCPToolCallSummary 追加进
                            # mcp_summaries（复用既有 schema，与旧路径 run_chat_tool_calls 产物
                            # 同构）→ retrieval/done 帧与 T7 护栏 apply_tool_receipt_guard 自动联动
                            # （六节点路径真执行 → 真凭据 → 零误标）。reflect 再 fan_out 多轮累计。
                            if node == "fan_out" and isinstance(update.get("tool_receipts"), list):
                                for _r in update["tool_receipts"]:
                                    if not isinstance(_r, dict) or not str(_r.get("tool_name") or "").strip():
                                        continue
                                    try:
                                        from app.chat.schemas import MCPToolCallSummary as _MCS

                                        mcp_summaries.append(_MCS(
                                            call_id=str(_r.get("call_id") or ""),
                                            tool_name=str(_r.get("tool_name") or ""),
                                            args_summary=str(json.dumps(
                                                _r.get("args") or {}, ensure_ascii=False, default=str))[:200],
                                            status="success" if str(_r.get("status")) == "success" else "error",
                                            latency_ms=int(_r.get("latency_ms") or 0),
                                            result_summary=str(_r.get("result_text") or "")[:400],
                                        ))
                                        graph_receipts_count += 1
                                    except Exception:  # noqa: BLE001 — 单条凭据映射失败不影响主链路
                                        continue
                        if retrieval_payload is not None and not retrieval_emitted:
                            async for frame in _emit_retrieval():
                                yield frame
                            if stream_held:
                                # CR-1 方案②：写类挂起已收束（pending_confirm + done 已发），
                                # 不继续消费图、不落库（_finish 不调用，与图 interrupt 路径一致）。
                                logger.info(f"[graph_stream] 写类挂起，流已收束待 resume: {thread_id}")
                                return
                            for d in pending_tokens:
                                yield sse_line(SseEventType.TOKEN.value, {"delta": d})
                            pending_tokens.clear()
                    elif mode == "custom" and isinstance(payload, dict) and payload.get("type") == "token":
                        delta = str(payload.get("delta") or "")
                        if not delta:
                            continue
                        answer_parts.append(delta)
                        if ttft_first_token_ms is None:
                            ttft_first_token_ms = int((time.perf_counter() - t0) * 1000)
                        if retrieval_emitted:
                            yield sse_line(SseEventType.TOKEN.value, {"delta": delta})
                        else:
                            pending_tokens.append(delta)  # retrieval 帧先行（契约帧序）
            finally:
                # guard release 成对兜底（astream 异常/客户端断连也必须归还闸位/槽位）。
                # 用 safe_release：SSE 断连/超时会令普通 release 的 await 被 CancelledError 打断，
                # safe_release 经 asyncio.shield 保证槽位一定归还（修复 TA5 并发槽泄漏）。
                if guard_held:
                    try:
                        from app.ai.guard import default_guard, safe_release
                        await safe_release(default_guard(), int(user_id))
                    except Exception:  # noqa: BLE001
                        pass
                    guard_held = False

            # CR-1 方案② 兜底：retrieval_payload 始终未置位（如工具意图未走 fan_out 更新）
            # 时，挂起负载可能未在循环内被消费——补发 pending_confirm 并收束，绝不静默吞。
            if held_hitl_payload is not None and not stream_held:
                async for frame in _emit_retrieval():
                    yield frame
                return

            # 图内降级透传：reflect/answer 节点的 degraded_reason（llm_failed/reflect_max_iter）
            deg_updates = [final_updates.get(n, {}).get("degraded_reason") for n in ("reflect", "answer", "fan_out")]
            graph_deg = next((d for d in deg_updates if d), None)
            # 兜底：answer 节点静默回退阻塞生成时（如 custom writer 不可用/流式分支未吐 token），
            # final_answer 只存在于状态更新——补发为 token 帧再收束，保证 done 与用户所见一致
            # （契约不变：token 帧仍是 {"delta": ...}，正常流式路径此分支恒不触发）。
            if not answer_parts:
                final_answer = str(final_updates.get("answer", {}).get("final_answer") or "")
                if final_answer:
                    answer_parts.append(final_answer)
                    yield sse_line(SseEventType.TOKEN.value, {"delta": final_answer})
            async for frame in _finish(degraded_extra=graph_deg):
                yield frame
            logger.info(
                "[graph_stream] 完成"
                f" thread_id={thread_id} ttft_retrieval_ms={ttft_retrieval_ms}"
                f" ttft_first_token_ms={ttft_first_token_ms} tokens={len(answer_parts)}"
                f" docs={len((retrieval_payload or {}).get('docs') or [])}"
                f" node_arrivals_ms={node_arrivals}"
            )
        except Exception as e:
            # 两段式错误模型 · 第二段：建连后生成真失败 → 可区分错误码 error 帧并收束
            code, msg = map_stream_exception(e)
            logger.warning(f"[graph_stream] 图执行异常，发 error 事件：{code} {msg} ({e})")
            yield sse_line(SseEventType.ERROR.value, {"code": code, "message": msg})
        finally:
            # 防御性兜底：图执行前异常（如 _ensure_agent_graph 失败）/ 客户端断连时归还已持有的闸位。
            # safe_release 对 CancelledError 免疫，保证任何退出路径槽位都归还（TA5）。
            if guard_held:
                try:
                    from app.ai.guard import default_guard, safe_release
                    await safe_release(default_guard(), int(user_id))
                except Exception:  # noqa: BLE001
                    pass
            # MCP 并行预取未消费（error/异常路径）→ 取消，不留悬挂任务
            if mcp_task is not None and not mcp_task.done():
                mcp_task.cancel()

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
