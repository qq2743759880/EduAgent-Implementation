# -*- coding: utf-8 -*-
"""R12：图内 LLM 工具决策器（dev-plan-reshape-r W3「LLM 工具决策接管」）。

替代对象：tool_calling._parse_heuristic 的玩具正则（audit P1-5：只认 add/ping/echo/
list_alphabet 四个演示工具的字面关键词，真实工具语义零覆盖）。

设计（含 v1.1 增补「决策超时预算」）：
  1. 输入 = 用户 query + 可用工具清单。工具清单真实拉取：mcp_tool×mcp_server DB
     registry（tool_calling.list_enabled_tool_metas），经 tool_specs.specs_from_metas
     映射为五要素 ToolSpec（name/description/input_schema 完整注入决策 prompt，
     stable 排序保前缀字节确定）。
  2. 输出 = 结构化 tool_plan [{tool_name, args}]：LLM 原始输出经 decision_validator
     Pydantic 校验（DecisionPlan/AgentToolCall），再过滤未知工具名 + 按
     MCP_TOOL_MAX_TRIES 截断 → ToolPlanItem（与规则路由同形状，执行闭环零改动）。
  3. 超时预算：asyncio.wait_for(TOOL_DECISION_TIMEOUT，默认 5s，可配)。超时/LLM 异常/
     输出不可解析 → 规则路由 fallback（_parse_heuristic 现行为），降级计数入日志
     （_STATS + logger.warning，GWT：注入假慢 LLM 超时后按规则路由完成且延迟有界）。
  4. 防误触发（GWT③）：决策 prompt 明确「与工具无关的问题 → tool_plan=[]」；
     Pydantic 校验；未知工具名过滤。空 tool_plan 是合法决策（非 fallback）。
  5. 执行闭环不在此模块：plans 交回 run_chat_tool_calls → executor.call_tool(args=)
     → 结果回填 + mcp_tool_call_log 审计（R04 已修签名，单一执行事实源）。
  6. llm_call 可注入：生产默认 _ChatClient(fast 档, temperature=0)；测试注入 fake/慢桩。

本模块不依赖 sixnode.py（R02-tail 领地），不写 DB，不碰 SSE 契约。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from loguru import logger

from app.ai.decision_validator import parse_decision_text
from app.ai.tool_specs import ToolSpec, build_decision_prefix, specs_from_metas
from app.config import settings

# llm 决策前缀 token 预算：full 模式（含 description+input_schema）需要比意图决策前缀
# （300）更大预算；4 个演示工具实测 ~450 token，700 留余量。确定性：同输入逐字节一致。
_TOOL_DECISION_PREFIX_BUDGET = 700
# 单次决策 LLM 输出上限：tool_plan JSON 短输出（超长必是跑偏，省 token 也保延迟）
_TOOL_DECISION_MAX_TOKENS = 200

# 工具决策专用 system prompt（工具接管语义，非 flows/agent 的意图四分法）：
#   规则 2 即 GWT③ 防误触发条款；规则 3 对齐 MCP_TOOL_MAX_TRIES。
TOOL_DECISION_SYSTEM_PROMPT = (
    "你是EduAgent的MCP工具决策器。根据用户问题，从「可用工具清单」中选择需要真实调用的"
    "工具并生成参数。规则："
    "1 只能选用清单中的tool_name，禁止杜撰工具或参数；参数名/类型遵循该工具的input_schema。"
    "2 与工具无关的问题（学科知识问答/闲聊/写作等）→ tool_plan=[]，禁止强行调用工具。"
    "3 最多选择{max_tries}个工具。"
    "输出：只输出一个JSON对象，无markdown无解释："
    '{{"tool_plan":[{{"tool_name":"...","args":{{}}}}]}}'
)


@dataclass
class ToolDecisionResult:
    """决策结果 + 决策过程元数据（审计/测试断言用）。"""
    plans: list[Any] = field(default_factory=list)          # list[ToolPlanItem]（tool_calling 形状）
    mode: str = "rule"                                       # 实际生效决策器："llm" | "rule"(fallback)
    fallback: bool = False                                   # True=LLM 决策失败走了规则兜底
    fallback_reason: str = ""                                # timeout|llm_error|unparseable
    latency_ms: int = 0                                      # LLM 决策耗时（fallback 时为到放弃为止的耗时）
    raw: str = ""                                            # LLM 原始输出（截断，排障用）


# ============================================================
# 降级计数（进程级）：降级计数入日志 —— 每次 fallback 打一条 warning 携带累计值
# ============================================================
_STATS: dict[str, int] = {
    "llm_ok": 0,             # LLM 决策成功（含合法空 plan）
    "llm_timeout": 0,        # 决策超时 → fallback
    "llm_error": 0,          # LLM 调用异常 → fallback
    "llm_unparseable": 0,    # 输出不可解析/校验失败 → fallback
    "rule_mode": 0,          # TOOL_DECISION_MODE=rule 直接走规则（非降级）
}


def get_tool_decision_stats() -> dict[str, int]:
    """只读快照（监控/测试断言用）。"""
    return dict(_STATS)


def _log_fallback(reason: str, detail: str = "") -> None:
    _STATS[f"llm_{reason}"] = _STATS.get(f"llm_{reason}", 0) + 1
    logger.warning(
        f"[TOOL-DECISION] LLM 决策降级→规则路由 fallback reason={reason}"
        f" stats={get_tool_decision_stats()} detail={detail[:160]}"
    )


# ============================================================
# 决策 prompt：query + 工具清单（name/description/input_schema，稳定排序）
# ============================================================
def build_tool_decision_messages(
    query: str,
    tools: list[Any],
    *,
    is_admin: bool = False,
) -> list[dict]:
    """构建决策 messages。工具清单经 specs_from_metas 真实映射（含参数 schema，full 模式注入）。"""
    specs: list[ToolSpec] = specs_from_metas(tools or [])
    max_tries = max(1, int(getattr(settings, "MCP_TOOL_MAX_TRIES", 1) or 1))
    system_prompt = TOOL_DECISION_SYSTEM_PROMPT.format(max_tries=max_tries)
    prefix = build_decision_prefix(
        specs, is_admin=is_admin, budget=_TOOL_DECISION_PREFIX_BUDGET,
        system_prompt=system_prompt, deferred=False,  # full 模式：description+input_schema 全注入
    )
    return [
        {"role": "system", "content": prefix},
        {"role": "user", "content": query or ""},
    ]


def _default_llm_call(messages: list[dict], timeout: float) -> Awaitable[str]:
    """生产 LLM 调用：_ChatClient(fast 档, temperature=0) 线程池执行（requests 同步栈）。"""
    loop = asyncio.get_running_loop()

    def _sync() -> str:
        from app.chat.generator import _ChatClient

        return _ChatClient.get().call_chat_with_retry(
            messages=messages, model="fast", temperature=0.0,
            max_tokens=_TOOL_DECISION_MAX_TOKENS, timeout=timeout,
        )

    return loop.run_in_executor(None, _sync)


# ============================================================
# 主入口：LLM 决策 + 超时预算 + 规则 fallback
# ============================================================
async def decide_tool_plan(
    query: str,
    tools: list[Any],
    *,
    timeout: float | None = None,
    is_admin: bool = False,
    llm_call: Callable[[list[dict], float], Awaitable[str]] | None = None,
) -> ToolDecisionResult:
    """llm 模式决策：query+工具清单 → ToolPlanItem 列表；超时/异常 → 规则路由 fallback。

    llm_call(messages, timeout) → str：可注入桩（测试用假慢 LLM/固定输出）；
    默认生产闭包走 _ChatClient。tools 为 ToolMeta 列表（tool_calling.list_enabled_tool_metas 产物）。
    """
    from app.chat.tool_calling import ToolPlanItem, _parse_heuristic

    budget = float(timeout if timeout is not None else getattr(settings, "TOOL_DECISION_TIMEOUT", 5.0))
    budget = max(0.5, min(30.0, budget))  # 钳制：下限防 0 阻塞，上限防预算失控
    messages = build_tool_decision_messages(query, tools, is_admin=is_admin)
    call = llm_call or _default_llm_call

    t0 = time.perf_counter()
    raw = ""
    try:
        raw = await asyncio.wait_for(call(messages, budget), timeout=budget)
    except asyncio.TimeoutError:
        latency = int((time.perf_counter() - t0) * 1000)
        _log_fallback("timeout", f"budget={budget}s latency_ms={latency}")
        return _fallback(query, tools, "timeout", latency)
    except Exception as exc:
        latency = int((time.perf_counter() - t0) * 1000)
        _log_fallback("error", f"{type(exc).__name__}: {exc}")
        return _fallback(query, tools, "error", latency)

    latency = int((time.perf_counter() - t0) * 1000)

    # Pydantic 校验（decision_validator.parse_decision_text，任何失败返回 None）
    plan_dec = parse_decision_text(raw)
    if plan_dec is None:
        _log_fallback("unparseable", f"raw={raw[:120]}")
        return _fallback(query, tools, "unparseable", latency, raw=raw)

    # 过滤：只保留 registry 真实存在的工具名（防 LLM 杜撰工具）+ 截断到 MCP_TOOL_MAX_TRIES
    known = {str(getattr(t, "tool_name", "") or ""): t for t in (tools or [])}
    max_tries = max(1, int(getattr(settings, "MCP_TOOL_MAX_TRIES", 1) or 1))
    plans: list[ToolPlanItem] = []
    for c in plan_dec.tool_plan:
        meta = known.get(str(c.tool_name))
        if meta is None:
            logger.warning(f"[TOOL-DECISION] 丢弃未知工具名：{c.tool_name!r}（不在启用 registry）")
            continue
        plans.append(ToolPlanItem(
            tool=meta,
            args=dict(c.args or {}),
            reason=f"llm决策({latency}ms)",
        ))
        if len(plans) >= max_tries:
            break

    _STATS["llm_ok"] += 1
    logger.info(
        f"[TOOL-DECISION] llm 决策完成 latency_ms={latency} "
        f"plans={[(p.tool.tool_name, p.args) for p in plans]}"
    )
    return ToolDecisionResult(
        plans=plans, mode="llm", fallback=False,
        fallback_reason="", latency_ms=latency, raw=str(raw)[:300],
    )


def _fallback(
    query: str,
    tools: list[Any],
    reason: str,
    latency_ms: int,
    raw: str = "",
) -> ToolDecisionResult:
    """规则路由 fallback（现行为 _parse_heuristic），保证决策永不阻塞主链路。"""
    from app.chat.tool_calling import ToolPlanItem, _parse_heuristic

    rule_plans: list[ToolPlanItem] = _parse_heuristic(query, tools)
    return ToolDecisionResult(
        plans=rule_plans, mode="rule", fallback=True,
        fallback_reason=reason, latency_ms=latency_ms, raw=raw,
    )
