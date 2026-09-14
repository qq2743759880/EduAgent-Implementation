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
import time
from collections.abc import AsyncGenerator
from types import SimpleNamespace

from fastapi.responses import StreamingResponse
from loguru import logger

from app.ai.graph import _empty_state, _ensure_agent_graph, resolve_thread_id
from app.auth import UserRole
from app.chat.schemas import RagQueryRequest, SseEventType
from app.chat.service import _ensure_session_owner, make_stream_finalize
from app.chat.sse import map_stream_exception, sse_line
from app.common.error_codes import CHAT_PERSIST_FAIL
from app.config import settings


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
        session = await _ensure_session_owner(req.session_id, user_id, role)

    # R02-c：thread_id——有 session 用 session；匿名请求每请求独立 uuid（禁 task24-{user_id} 共享）
    thread_id = resolve_thread_id(req.session_id, user_id)

    async def _gen() -> AsyncGenerator[bytes, None]:
        t0 = time.perf_counter()
        session_id_out = session.session_id if session else None

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

        async def _run_mcp():
            from app.chat.tool_calling import run_chat_tool_calls

            try:
                return await run_chat_tool_calls(
                    query=req.query,
                    operator_user_id=int(user_id),
                    session_id=session_id_out,
                    use_mcp_flag=bool(req.use_mcp_tools and getattr(settings, "USE_MCP_TOOL_CALLING", True)),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[graph_stream] MCP 工具阶段异常（跳过）：{type(exc).__name__}: {exc}")
                return [], "", f"MCP 工具阶段异常({type(exc).__name__})"

        mcp_task = (
            asyncio.ensure_future(_run_mcp())
            if not (guard_entry is not None and not guard_entry.get("ok"))
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

        async def _await_mcp() -> None:
            nonlocal mcp_summaries, mcp_context, mcp_degraded
            if mcp_task is not None:
                try:
                    mcp_summaries, mcp_context, mcp_degraded = await mcp_task
                except Exception as exc:  # noqa: BLE001 — MCP 失败不影响主响应
                    mcp_summaries, mcp_context, mcp_degraded = [], "", f"MCP 工具阶段异常({type(exc).__name__})"

        async def _emit_retrieval() -> AsyncGenerator[bytes, None]:
            """组装并发送 retrieval 帧（等 MCP 并行预取收口，保与旧路径帧内容对齐）。"""
            nonlocal retrieval_emitted, ttft_retrieval_ms
            await _await_mcp()
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
                    "message": f"答案生成成功但落库失败：{type(exc).__name__}（内容未保存到会话）",
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
                        "degraded_reason": f"答案已生成但流式落库失败({type(exc).__name__})：未入库",
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
            state = _empty_state(req.query, user_id=int(user_id), session_id=req.session_id)
            config = {"configurable": {"thread_id": thread_id, "stream_tokens": True}}
            try:
                async for mode, payload in g.astream(state, config, stream_mode=["updates", "custom"]):
                    if mode == "updates" and isinstance(payload, dict):
                        for node, update in payload.items():
                            if not isinstance(update, dict):
                                continue
                            final_updates[node] = update
                            # chitchat 直连（route→answer，无 fan_out）：按旧路径口径发空 docs retrieval 帧
                            if node == "route" and update.get("intent") == "chitchat" and retrieval_payload is None:
                                retrieval_payload = {
                                    "docs": [], "graph_entities": [], "retrieved_count": 0,
                                    "rewrite_query": req.query, "degraded_reason": None,
                                }
                            if node == "fan_out" and isinstance(update.get("retrieval"), dict):
                                retrieval_payload = update["retrieval"]
                        if retrieval_payload is not None and not retrieval_emitted:
                            async for frame in _emit_retrieval():
                                yield frame
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
                # guard release 成对兜底（astream 异常/客户端断连也必须归还闸位/槽位）
                if guard_held:
                    try:
                        from app.ai.guard import default_guard
                        await default_guard().release(int(user_id))
                    except Exception:  # noqa: BLE001
                        pass
                    guard_held = False

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
            )
        except Exception as e:
            # 两段式错误模型 · 第二段：建连后生成真失败 → 可区分错误码 error 帧并收束
            code, msg = map_stream_exception(e)
            logger.warning(f"[graph_stream] 图执行异常，发 error 事件：{code} {msg} ({e})")
            yield sse_line(SseEventType.ERROR.value, {"code": code, "message": msg})
        finally:
            # 防御性兜底：图执行前异常（如 _ensure_agent_graph 失败）时归还已持有的闸位
            if guard_held:
                try:
                    from app.ai.guard import default_guard
                    await default_guard().release(int(user_id))
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
