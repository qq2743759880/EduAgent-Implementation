# -*- coding: utf-8 -*-
"""
task27 决策 JSON 校验（GWT②）：非法 JSON 经 Pydantic 校验失败后只重试 1 次，
仍失败则保守回退（现状 _safe_json_extract 语义 — need_search=true 检索兜底），不抛 500。

设计：
  - DecisionPlan / AgentToolCall 为 Pydantic 模型（强类型，参数类型/结构由 Pydantic 强制）。
  - parse_decision_text：稳健提取 JSON（容忍 ```json 包裹/首尾噪音）→ Pydantic 校验。
  - decide_plan_with_retry：首次解析失败 → 重试 1 次（注入 llm_call 取第二份 raw）→
    仍失败 → 返回保守决策 DecisionPlan(need_search=True, query_rewrite=query)。
  - meta 暴露 retried / fell_back，供契约测试与监控断言「只重试一次」。
"""
from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

__all__ = [
    "AgentToolCall",
    "DecisionPlan",
    "parse_decision_text",
    "_extract_json_obj",
    "decide_plan_with_retry",
    "conservative_fallback",
]


class AgentToolCall(BaseModel):
    """干净的工具调用（Pydantic 强类型；非法项被拒绝 → 触发重试/回退）。"""

    tool_name: str = Field(..., min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)


class DecisionPlan(BaseModel):
    """LLM 意图决策结构化输出（Pydantic 校验）。"""

    need_search: bool = True
    query_rewrite: str = ""
    tool_plan: list[AgentToolCall] = Field(default_factory=list)
    answer_direct: str = ""


def _extract_json_obj(raw: str) -> dict | None:
    """从 LLM 输出稳健提取 JSON 对象（容忍 ```json 包裹 / 首尾噪音），与历史语义一致。"""
    if not raw:
        return None
    text = raw.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    else:
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 and b > a:
            text = text[a : b + 1]
    try:
        obj = json.loads(text)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def parse_decision_text(raw: str) -> DecisionPlan | None:
    """提取 JSON → Pydantic 校验 → DecisionPlan。任何失败返回 None（不抛异常）。"""
    obj = _extract_json_obj(raw)
    if not obj:
        return None
    try:
        # 宽松：仅保留合法键；need_search/rewrite/answer_direct 由 Pydantic 默认/强转
        payload: dict[str, Any] = {
            "need_search": obj.get("need_search", True),
            "query_rewrite": obj.get("query_rewrite", ""),
            "answer_direct": obj.get("answer_direct", ""),
        }
        tool_plan = obj.get("tool_plan")
        if tool_plan is not None:
            if not isinstance(tool_plan, list):
                return None
            calls: list[AgentToolCall] = []
            for it in tool_plan:
                if not isinstance(it, dict):
                    return None  # 结构非法 → 视为校验失败（允许重试）
                tn = it.get("tool_name")
                if not tn:
                    return None
                calls.append(AgentToolCall(tool_name=str(tn), args=it.get("args") if isinstance(it.get("args"), dict) else {}))
            payload["tool_plan"] = calls
        return DecisionPlan(**payload)
    except Exception:
        # Pydantic 校验失败（类型不匹配等）→ 视为失败，走重试/回退
        return None


def conservative_fallback(query: str) -> DecisionPlan:
    """保守回退：need_search=true（检索兜底），保证不劣化、不抛 500。"""
    return DecisionPlan(need_search=True, query_rewrite=query or "")


async def decide_plan_with_retry(
    query: str,
    llm_call: Callable[[str], Awaitable[str]],
    *,
    max_attempts: int = 2,
) -> tuple[DecisionPlan, dict]:
    """决策：Pydantic 校验 + 重试至多 1 次 + 保守回退。

    llm_call(query_attempt) → 返回 LLM 原始字符串。测试注入 fake；生产/agent 层注入
    _ChatClient 调用闭包。
    返回 (plan, meta)：meta = {"attempts":..., "retried":bool, "fell_back":bool, "last_raw":...}。
    """
    attempts = 0
    retried = False
    last_raw: str | None = None
    for attempt in range(max(1, max_attempts)):
        attempts += 1
        raw = await llm_call(query)
        last_raw = raw
        plan = parse_decision_text(raw)
        if plan is not None:
            return plan, {"attempts": attempts, "retried": retried, "fell_back": False, "last_raw": last_raw}
        if attempt < max_attempts - 1:
            retried = True  # 首次失败 → 重试一次
    return conservative_fallback(query), {"attempts": attempts, "retried": retried, "fell_back": True, "last_raw": last_raw}