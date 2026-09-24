# -*- coding: utf-8 -*-
"""task-T1 工具调用闭环状态机（纯逻辑，零 IO 依赖，随时可测）。

把"重试 1 次就回退"升级为四步闭环：
  attempt=1 正常执行
  → attempt=2 换参数（LLM 改写 args，或规则跳级兜底）
  → attempt=3 换备用工具（TOOL_FALLBACK_MAP）
  → attempt=4 输出结构化人工操作指南并停止

对齐 Codex orchestrator.rs / auto-review（3 连续拒绝熔断）/ retry telemetry
（production-upgrade-plan.md P6）。

本模块只负责"决定下一步做什么"（状态机）与"人工指南长什么样"（模板），
不触碰网络 / Redis / LLM / DB——这些由 executor.call_tool_with_retry 注入，
从而让闭环逻辑在单测里可被纯函数 + fake executor 完全覆盖（AC1~AC4）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ============================================================
# 单步定义
# ============================================================
@dataclass
class RetryStep:
    """闭环中的一步：执行哪个工具、用什么参数、什么动作语义。"""
    attempt: int
    action: str               # execute_normal | rewrite_args | switch_tool
    tool_name: str
    args: dict
    is_terminal: bool = False  # True=这一步不再执行工具，而是产出人工指南


@dataclass
class AttemptOutcome:
    """单次工具执行的结果（由 executor 注入返回），供状态机决策。"""
    ok: bool                                          # 工具是否成功（status==SUCCESS）
    status: str                                       # ToolCallStatusEnum.value
    tool_name: str
    args: dict
    latency_ms: int = 0
    error_message: str | None = None
    is_rejection: bool = False                        # isError/权限拒绝 → 计入拒绝熔断
    # TA7 D1：业务失败（工具真执行了，但业务结果为失败：ok:false / 非 0 code）。
    # 语义 = 确定性终态：参数/课程名不会因为再试一次就变得存在 → **不重试、不出人工指南**，
    # 直接把如实标注的 ERROR 响应回传（保留 content 里的 need_clarify/candidates 供模型追问）。
    is_business_failure: bool = False
    result: Any = None
    content_text: str | None = None
    resp: Any = None                                  # 原始 MCPToolTestResp（如有）


# ============================================================
# 拒绝计数存储协议（生产用 Redis，测试用内存 fake）
# ============================================================
@runtime_checkable
class RejectStore(Protocol):
    async def get(self, session_id: str) -> int: ...
    async def increment(self, session_id: str) -> int: ...
    async def reset(self, session_id: str) -> None: ...


class MemRejectStore:
    """内存兜底拒绝计数器（无 Redis 时 / 单测注入用）。"""

    def __init__(self, ttl_s: int = 300) -> None:
        self._ttl_s = ttl_s
        self._data: dict[str, int] = {}

    async def get(self, session_id: str) -> int:
        return int(self._data.get(session_id, 0))

    async def increment(self, session_id: str) -> int:
        self._data[session_id] = int(self._data.get(session_id, 0)) + 1
        return self._data[session_id]

    async def reset(self, session_id: str) -> None:
        self._data[session_id] = 0


# ============================================================
# 闭环状态机
# ============================================================
ACTION_NORMAL = "execute_normal"
ACTION_REWRITE = "rewrite_args"
ACTION_SWITCH = "switch_tool"


class ToolRetryStateMachine:
    """决定闭环每一步该做什么。纯逻辑，不执行任何 IO。

    用法（由 executor.call_tool_with_retry 驱动）：
        sm = ToolRetryStateMachine(orig_tool, orig_args, fallback_map=..., max_attempts=4)
        step = sm.plan_first()              # attempt 1
        while step and not step.is_terminal:
            outcome = await executor(step.tool_name, step.args, attempt=step.attempt)
            if outcome.ok: return outcome
            step = sm.plan_next(step.attempt, outcome)   # 2 / 3 / 4(guide)
    """

    def __init__(self, original_tool_name: str, original_args: dict,
                 *, fallback_map: dict | None = None, max_attempts: int = 4) -> None:
        self.original_tool_name = original_tool_name
        self.original_args = dict(original_args or {})
        self.fallback_map = fallback_map or {}
        self.max_attempts = max_attempts if (max_attempts and max_attempts > 0) else 4

    def _fallback_tool(self) -> str | None:
        lst = self.fallback_map.get(self.original_tool_name)
        if lst:
            return lst[0]
        return None

    def plan_first(self) -> RetryStep:
        return RetryStep(
            attempt=1,
            action=ACTION_NORMAL,
            tool_name=self.original_tool_name,
            args=dict(self.original_args),
        )

    def plan_next(self, attempt: int, prev: AttemptOutcome) -> RetryStep | None:
        """给定"刚执行完的第 attempt 步结果"，决定下一步；返回 None 表示进入人工指南（terminal）。

        max_attempts 计的是"总步数"，第 max_attempts 步即为结构化人工指南；
        因此前 (max_attempts-1) 步为工具执行（1 正常 / 2 换参 / 3 换工具）。
        """
        nxt = attempt + 1
        if nxt >= self.max_attempts:
            return None  # 这一步即人工指南（terminal）
        if nxt == 2:
            # 换参数：args 由编排方按 LLM 改写或规则跳级计算（这里给原参，编排方覆盖）
            return RetryStep(attempt=2, action=ACTION_REWRITE,
                            tool_name=self.original_tool_name, args=dict(self.original_args))
        if nxt == 3:
            fb = self._fallback_tool()
            if fb:
                # 换备用工具：参数沿用（编排方可再改写），动作语义 = switch_tool
                return RetryStep(attempt=3, action=ACTION_SWITCH,
                                tool_name=fb, args=dict(self.original_args))
            return None  # 无备用工具 → 直接进入指南
        return None


# ============================================================
# 人工操作指南模板（AC2）
# ============================================================
MANUAL_GUIDE_TEMPLATE = (
    "工具在多次重试（换参数 / 换备用工具）后仍不可用，请按以下人工步骤处理。"
)


def build_manual_guide(*, original_tool_name: str, attempts_trail: list[dict],
                       original_args: dict, last_error: str | None = None,
                       contact_admin: str | None = None) -> dict:
    """生成结构化人工操作指南（AC2）：问题描述 / 已尝试工具 / 用户手动步骤 / 联系管理员。

    attempts_trail 元素形如 {attempt, action, tool_name, args, outcome, latency_ms, error_message}
    """
    attempted = []
    for e in attempts_trail:
        attempted.append({
            "attempt": e.get("attempt"),
            "action": e.get("action"),
            "tool_name": e.get("tool_name"),
            "outcome": e.get("outcome"),
            "error_message": e.get("error_message"),
        })

    problem = (
        f"工具「{original_tool_name}」在闭环（最多 {len(attempts_trail) or '?'} 步："
        f"正常 → 换参数 → 换备用工具）尝试后仍不可用"
        + (f"：{last_error}" if last_error else "。")
    )

    user_steps = [
        "确认网络连通性，以及对应 MCP Server 是否在线（管理端 → MCP 服务 → 健康检查）。",
        f"核对工具「{original_tool_name}」的输入参数是否符合其 schema（参考上方『已尝试工具』中的参数）。",
        "若因权限/鉴权被拒，请确认当前账号是否具备该工具的调用权限。",
        "以上均无异常仍失败，请稍后重试，或改用人工方式完成该操作。",
    ]

    return {
        "problem_description": problem,
        "attempted_tools": attempted,
        "user_manual_steps": user_steps,
        "contact_admin": contact_admin or (
            "如为生产故障，请联系管理员排查 MCP Server 状态，"
            "或查看调用日志表 mcp_tool_call_log 获取完整错误。"
        ),
        "original_args": original_args,
    }
