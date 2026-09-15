# -*- coding: utf-8 -*-
"""R15 权限门（CanUseToolFn）：角色×工具矩阵，默认 deny（fail-closed）。

契约：contracts/reshape-r-aci.json（已冻结）。
- 矩阵：admin=全量已登记工具；manager=只读工具+课程/题库写类；student=仅公开只读工具。
- write_class_tools（契约）：收藏写 / 积分变更 / 知识库导入 / 订单创建 —— 仅 admin。
- default=deny：未登记工具名 / 未知角色，任意角色一律拒绝。

纯逻辑模块：无 DB / 无 LLM / 无 Redis 依赖，可脱离 IO 单测。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class GateDecision:
    """权限门判定结果。allowed=False 时 action_hint 必为非空可执行建议。"""
    allowed: bool
    action_hint: str | None = None


ToolClass = Literal["public_read", "course_write", "admin_write"]


# ------------------------------------------------------------------
# 工具名 → 类别 集中映射表（唯一事实源，编排者验收重点）
#   public_read  ：公开只读工具 —— student/manager/admin
#   course_write ：课程/题库写类 —— manager/admin
#   admin_write  ：契约 write_class_tools（收藏写/积分变更/知识库导入/订单创建）—— 仅 admin
# ------------------------------------------------------------------
PUBLIC_READ_TOOLS = frozenset({
    "add",                 # MCP 演示工具（实际注册，无写语义）
    "echo",                # MCP 演示工具（实际注册，无写语义）
    "list_alphabet",       # MCP 演示工具（实际注册，只读查询）
    "ping",                # MCP 演示工具（实际注册，健康类）
    "sse_health",          # MCP 演示工具（实际注册，健康类）
    "calculator",          # executor 内置工具（纯计算，无副作用）
    "search_knowledge",    # executor 内置工具（知识库检索，只读）
})

COURSE_WRITE_TOOLS = frozenset({
    "course_create",       # 课程写类：创建课程
    "course_update",       # 课程写类：更新课程
    "course_delete",       # 课程写类：删除课程
    "question_create",     # 题库写类：创建题目
    "question_update",     # 题库写类：更新题目
    "question_delete",     # 题库写类：删除题目
})

ADMIN_WRITE_TOOLS = frozenset({
    "favorite_add",        # 收藏写（write_class_tools）
    "points_change",       # 积分变更（write_class_tools）
    "knowledge_import",    # 知识库导入（write_class_tools）
    "order_create",        # 订单创建（write_class_tools）
})


# 工具名 → 类别 映射（供测试 / 报告全量枚举）
TOOL_CLASS_MAP: dict[str, ToolClass] = {
    **{n: "public_read" for n in PUBLIC_READ_TOOLS},
    **{n: "course_write" for n in COURSE_WRITE_TOOLS},
    **{n: "admin_write" for n in ADMIN_WRITE_TOOLS},
}

# 契约矩阵中登记的合法角色（未知角色一律 deny，fail-closed）
KNOWN_ROLES = frozenset({"admin", "manager", "student"})

# 类别 → 允许角色（契约矩阵）
_CLASS_ALLOWED_ROLES: dict[ToolClass, frozenset[str]] = {
    "public_read": frozenset({"student", "manager", "admin"}),
    "course_write": frozenset({"manager", "admin"}),
    "admin_write": frozenset({"admin"}),
}


def classify_tool(tool_name: str) -> ToolClass | None:
    """返回工具类别；未登记（非白名单）返回 None。"""
    return TOOL_CLASS_MAP.get(tool_name or "")


def _action_hint(role: str, cls: ToolClass | None) -> str:
    if role not in KNOWN_ROLES:
        return "请先登录后再试。"
    if cls is None:
        return "该工具未登记或不在权限范围内，请联系管理员开通后重试。"
    return "此操作需更高权限，请联系管理员（admin）开通后重试。"


def can_use_tool(role: str, tool_name: str) -> GateDecision:
    """CanUseToolFn：判定角色是否可使用某工具。默认 deny（fail-closed）。"""
    role_n = (role or "").strip().lower()
    cls = classify_tool(tool_name)

    # 未登记工具 / 未知角色 → 一律 deny
    if cls is None or role_n not in KNOWN_ROLES:
        return GateDecision(allowed=False, action_hint=_action_hint(role_n, cls))

    # admin = 全量工具
    if role_n == "admin":
        return GateDecision(allowed=True)

    # 其余角色按 类别→允许角色 矩阵判定
    if role_n in _CLASS_ALLOWED_ROLES[cls]:
        return GateDecision(allowed=True)
    return GateDecision(allowed=False, action_hint=_action_hint(role_n, cls))


def permission_denied_message(role: str, tool_name: str) -> str:
    """权限拦截的 ACI 错误信封 message（面向用户中文，无错误码堆砌/无堆栈泄出）。"""
    cls = classify_tool(tool_name)
    if (role or "").strip().lower() not in KNOWN_ROLES:
        return "当前登录状态无效，无法执行该操作。"
    if cls is None:
        return "您要使用的工具未登记或在当前权限范围内不可用，无法执行。"
    return "您的当前角色没有执行该操作的权限，该操作已被安全拦截。"