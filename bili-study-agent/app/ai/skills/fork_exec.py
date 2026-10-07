"""Skill 执行：context:fork 走 task92 runner；allowed-tools 该轮预授权。

对齐 Claude Code skills 文档：
- context: fork → skill 在**独立子代理上下文**中执行（复用 task92 R1 的 run_subagent，独立 messages
  + 独立 system prompt + 工具白名单 + 崩溃隔离），符合 self-critique 维度3 上下文隔离。
- allowed-tools → 该轮工具**预授权**（权限门放行，无需逐次 ask），对应「该轮免授权」验收。
- disable-model-invocation=true → 仅手动 /skill 触发（trigger 层已保证），此处 inline 注入 body。

执行模式：
- fork  → 委托 run_subagent，返回摘要 + artifact_ref（原文在 artifact）
- inline → 返回 body 供主上下文注入（body_injected=True）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.ai.skills.runtime import Skill


# ── 权限门：allowed-tools 该轮免授权 ───────────────────────────
class PermissionGate:
    """allowed-tools 预授权门：skill 激活期间，其 allowed_tools 内工具该轮免授权。

    激活是「轮次作用域」：同一轮执行该 skill 时放行；deactivate 后恢复默认权限策略。
    """

    def __init__(self) -> None:
        self._active: dict[str, frozenset[str]] = {}

    def activate(self, skill: Skill, turn: int = 0) -> None:
        if skill.allowed_tools:
            self._active[skill.name] = frozenset(skill.allowed_tools)

    def deactivate(self, skill: Skill) -> None:
        self._active.pop(skill.name, None)

    def is_authorized(self, skill: Skill | None, tool_name: str) -> bool:
        if skill is None:
            return False
        tools = self._active.get(skill.name)
        return bool(tools) and tool_name in tools


def is_preauthorized(skill: Skill, tool_name: str) -> bool:
    """该轮工具免授权判定（纯函数版）：skill 声明了 allowed-tools 且包含 tool_name。"""
    return tool_name in skill.allowed_tools


@dataclass
class SkillExecResult:
    skill: str
    mode: str                 # "fork" | "inline"
    ok: bool = False
    summary: str = ""
    artifact_ref: str = ""
    body_injected: bool = False
    preauthorized: tuple[str, ...] = ()


async def exec_skill(
    skill: Skill,
    *,
    objective: str,
    llm: Callable[[list[dict], str], Awaitable[str]] | None = None,
    tool_services: dict[str, Callable[[dict], Awaitable[Any]]] | None = None,
    user_id: int | None = None,
    thread_id: str | None = None,
    turn: int = 0,
) -> SkillExecResult:
    """执行一个 skill。

    - context: fork → 委托 task92 run_subagent（独立子代理上下文）；body 作为子代理 system prompt。
    - 否则 inline → 返回 body 供主上下文按需注入（body_injected=True）。
    - 执行期间通过 PermissionGate 激活 allowed-tools 预授权（该轮免授权）。
    """
    tool_services = tool_services or {}
    gate = PermissionGate()
    gate.activate(skill, turn)

    if skill.is_fork:
        from app.ai.subagents.runner import SubagentSpec, run_subagent

        spec = SubagentSpec(
            name=f"skill:{skill.name}",
            description=skill.description,
            tools=tuple(tool_services.keys()),
            model="fast",
            maxTurns=4,
            system_prompt=skill.body or skill.description,
        )
        res = await run_subagent(
            spec,
            objective=objective,
            input_text="",
            tool_services=tool_services,
            llm=llm,
            user_id=user_id,
            thread_id=thread_id,
        )
        gate.deactivate(skill)
        return SkillExecResult(
            skill=skill.name,
            mode="fork",
            ok=res.ok,
            summary=res.summary,
            artifact_ref=res.artifact_ref,
            body_injected=False,
            preauthorized=tuple(skill.allowed_tools),
        )

    # inline：body 注入当前轮（不进前缀，动态 context injection）
    gate.deactivate(skill)
    return SkillExecResult(
        skill=skill.name,
        mode="inline",
        ok=True,
        body_injected=True,
        preauthorized=tuple(skill.allowed_tools),
    )
