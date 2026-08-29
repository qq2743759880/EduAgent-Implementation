# -*- coding: utf-8 -*-
"""
Agent 循环决策层（P2 增强）：从「检索先行」升级为「LLM 意图决策 → 执行 → 生成」。

流程（对应需求「先调 LLM → 检索 RAG / 调 tools/MCP → 结果回传 LLM → 组织回答」）：
  1. decide_agent_plan：用 LLM 判断用户问题意图，输出结构化 JSON：
       {
         "need_search": true/false,     # 是否检索知识库
         "query_rewrite": "改写后的检索词（可空）",
         "tool_plan": [{"tool_name": "...", "args": {...}}],  # 需要调用的 MCP 工具（可空）
         "answer_direct": "无需检索/工具时的直接回答（可空，need_search=false 且有把握时）"
       }
  2. 执行：按 need_search 调 retrieve_three_channel；按 tool_plan 调 MCP executor.call_tool
  3. 生成：检索结果 + 工具结果 + 原始问题 → LLM 组织最终回答（复用 generator.build_messages / generate_*）

设计原则：
  - 决策用「无知识库上下文」的纯 LLM 调用，避免污染判断；生成用「带检索结果」的调用。
  - 决策 LLM 失败/超时 → 回退到原「检索先行」行为（need_search=true），保证不劣化。
  - 工具执行沿用 app.mcp.executor（stdio/SSE 已验证），不引入新依赖。
  - 兼容：原有 run_chat_tool_calls（启发式）保留；本模块作为可选增强由 service 决定启用。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from app.chat.generator import _ChatClient
from app.chat.retriever import RetrievalBundle, retrieve_three_channel
from app.config import settings
from app.ai.decision_validator import decide_plan_with_retry
from app.ai.tool_specs import build_decision_prefix, specs_from_metas
from app.ai.prompt_cache import ensure_min_prefix

# ============================================================
# 1. 决策 LLM 调用（无知识库上下文，仅判断意图）
#    决策 system 前缀（task27）：精简规则 prompt + 稳定排序工具清单，≤300 token，
#    admin_only 工具不入普通用户 prompt（GWT①③）。
# ============================================================

class AgentPlan:
    """LLM 意图决策结果。"""

    __slots__ = ("need_search", "query_rewrite", "tool_plan", "answer_direct", "decision_error")

    def __init__(
        self,
        need_search: bool = True,
        query_rewrite: str = "",
        tool_plan: list[dict] | None = None,
        answer_direct: str = "",
        decision_error: str | None = None,
    ) -> None:
        self.need_search = need_search
        self.query_rewrite = query_rewrite
        self.tool_plan = tool_plan or []
        self.answer_direct = answer_direct
        self.decision_error = decision_error


def _safe_json_extract(raw: str) -> dict | None:
    """从 LLM 输出中稳健提取 JSON（容忍 ```json 包裹 / 首尾噪音）。

    决策校验（GWT②）已迁移到 app.ai.decision_validator：先提取 → Pydantic 校验 →
    失败重试 1 次 → 保守回退。此处保留为导入兼容（历史测试对 decide_agent_plan 的桩）。"""
    from app.ai.decision_validator import _extract_json_obj

    return _extract_json_obj(raw)


async def decide_agent_plan(
    query: str,
    tool_metas: list[Any] | None = None,
    timeout: float = 30.0,
    is_admin: bool = False,
) -> AgentPlan:
    """
    用 LLM 判断意图，Pydantic 校验，非法输出重试 1 次后保守回退（GWT②）。
    决策前缀（task27）：精简规则 + 稳定排序工具清单 ≤300 token；admin_only 不入普通用户。
    """
    if not getattr(settings, "AGENT_DECISION_ENABLED", True):
        return AgentPlan(need_search=True, query_rewrite=query)

    specs = specs_from_metas(tool_metas or [])
    # task-C2：决策前缀默认 deferred 模式（桩只含 name+summary，schema 被选中才展开）→ 前缀字节稳定；
    # ensure_min_prefix 用静态填充注释把前缀撑到 ≥2048 token，跨过火山 ark 缓存门槛（2048 分块实测）。
    # 二者均不改变既有契约结构（tools 仍由 specs_from_metas 注入，执行期走真实 MCP 兜底）。
    base_prefix = build_decision_prefix(specs, is_admin=is_admin, deferred=settings.TOOL_DEFERRED_MODE)
    system_prefix = ensure_min_prefix(base_prefix)

    async def _llm_call(q: str) -> str:
        client = _ChatClient.get()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: client.call_chat_with_retry(
                messages=[
                    {"role": "system", "content": system_prefix},
                    {"role": "user", "content": q},
                ],
                model="fast",
                temperature=0.0,
                max_tokens=300,
                timeout=timeout,
            ),
        )

    try:
        plan_dec, meta = await decide_plan_with_retry(query, _llm_call, max_attempts=2)
    except Exception as exc:
        logger.warning(f"[Agent] 意图决策 LLM 失败，回退检索：{type(exc).__name__}: {exc}")
        return AgentPlan(need_search=True, query_rewrite=query, decision_error=str(exc)[:200])

    if meta["fell_back"]:
        logger.warning(f"[Agent] 意图决策输出非法（重试 {1 if meta['retried'] else 0} 次后）无法解析，保守回退检索。raw={str(meta.get('last_raw'))[:120]}")
        return AgentPlan(need_search=True, query_rewrite=query, decision_error="decision_unparseable")

    tool_plan = [{"tool_name": c.tool_name, "args": c.args} for c in plan_dec.tool_plan]
    rewrite = (plan_dec.query_rewrite or query).strip() or query
    logger.debug(
        f"[Agent] 决策结果：need_search={plan_dec.need_search} rewrite={rewrite[:50]} "
        f"tools={[t['tool_name'] for t in tool_plan]}"
    )
    return AgentPlan(
        need_search=plan_dec.need_search,
        query_rewrite=rewrite,
        tool_plan=tool_plan,
        answer_direct=plan_dec.answer_direct,
    )


# ============================================================
# 2. 工具执行（按 LLM 决策的 tool_plan 调用 MCP executor）
# ============================================================

async def execute_tool_plan(
    tool_plan: list[dict],
    *,
    operator_user_id: int,
    session_id: str | None = None,
) -> tuple[list[dict], str]:
    """
    按决策执行工具。返回 (summaries, context_fragment)。
    summaries 供落库/响应；context_fragment 供生成阶段注入。
    """
    if not tool_plan:
        return [], ""

    try:
        from app.mcp import executor as _mcp_executor
    except Exception as exc:
        logger.warning(f"[Agent] MCP executor 导入失败：{type(exc).__name__}: {exc}")
        return [], ""

    try:
        from app.otel.exporter import get_otel_exporter as _get_otel
    except Exception:
        _get_otel = None

    summaries: list[dict] = []
    parts: list[str] = []
    for item in tool_plan:
        tool_name = str(item.get("tool_name") or "").strip()
        args = item.get("args") if isinstance(item.get("args"), dict) else {}
        if not tool_name:
            continue
        t0 = time.perf_counter()
        try:
            result = await _mcp_executor.call_tool(
                tool_name=tool_name,
                arguments=args,
                operator_user_id=operator_user_id,
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            status = result.get("status", "SUCCESS") if isinstance(result, dict) else "SUCCESS"
            text = ""
            if isinstance(result, dict):
                text = str(result.get("result") or result.get("error_message") or "")
            summaries.append({"tool_name": tool_name, "status": status, "result_summary": text[:500], "latency_ms": latency_ms})
            parts.append(f"- 工具 {tool_name} 结果（{status}）：{text[:300]}")
            if _get_otel is not None:
                try:
                    _get_otel().record_tool_result(status, tool=tool_name, user_id=str(operator_user_id), latency_ms=latency_ms)
                except Exception:
                    pass
        except Exception as exc:
            logger.warning(f"[Agent] 工具 {tool_name} 调用失败：{type(exc).__name__}: {exc}")
            summaries.append({"tool_name": tool_name, "status": "ERROR", "result_summary": str(exc)[:200], "latency_ms": 0})
            parts.append(f"- 工具 {tool_name} 调用失败：{str(exc)[:200]}")
            if _get_otel is not None:
                try:
                    _get_otel().record_tool_result("ERROR", tool=tool_name, user_id=str(operator_user_id))
                except Exception:
                    pass
    fragment = "\n".join(parts)
    return summaries, fragment


# ============================================================
# 3. 编排：单轮 Agent 问答
# ============================================================

async def run_agent_turn(
    query: str,
    *,
    user_id: int,
    role: Any,
    use_hyde: bool = True,
    enable_graph: bool = True,
    top_k: int = 12,
    final_max_k: int = 5,
    cutoff_drop_ratio: float = 0.2,
    tool_metas: list[Any] | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    完整 Agent 单轮：
      1) decide_agent_plan → plan（LLM 判断是否检索）
      2) 按 plan.need_search 检索（重写后）
      3) 返回 plan + bundle（工具执行由调用方走 run_chat_tool_calls 兼容 P8）
    """
    plan = await decide_agent_plan(query, tool_metas=tool_metas)

    bundle: RetrievalBundle | None = None
    if plan.need_search:
        try:
            bundle = await retrieve_three_channel(
                plan.query_rewrite or query,
                user_id=int(user_id),
                role=role,
                use_hyde=use_hyde,
                enable_graph=enable_graph,
                top_k=top_k,
                final_max_k=final_max_k,
                cutoff_drop_ratio=cutoff_drop_ratio,
            )
        except Exception as exc:
            logger.warning(f"[Agent] 检索异常：{type(exc).__name__}: {exc}")
            bundle = RetrievalBundle(
                docs=[], raw_retrieved_count=0, graph_entities=[], rewrite_query=None, degraded_reason=str(exc)[:200],
            )
    else:
        bundle = RetrievalBundle(
            docs=[], raw_retrieved_count=0, graph_entities=[], rewrite_query=plan.query_rewrite or None, degraded_reason=None,
        )

    return {
        "plan": plan,
        "bundle": bundle,
    }
