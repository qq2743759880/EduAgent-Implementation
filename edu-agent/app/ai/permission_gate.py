# -*- coding: utf-8 -*-
"""R15b 权限门（CanUseToolFn）：角色×工具矩阵，默认 deny（fail-closed）。

契约：contracts/reshape-r-aci.json（已冻结，禁改）。
- 矩阵：admin=全量已登记工具；manager=只读工具+课程/题库写类；student=仅公开只读工具。
- write_class_tools（契约中文语义）：收藏写 / 积分变更 / 知识库导入 / 订单创建 —— 仅 admin。
- default=deny：未登记工具名 / 未知角色，任意角色一律拒绝。

================================================================
R15b 修订：工具映射表对账实物（消灭虚构工具名）
================================================================
真实工具注册面**只有 7 个**，2026-09-15 逐名核对（证据可复跑）：

  · executor 内置 2 个
      - `calculator`       → app/mcp/executor.py:676 `register_builtin_tool("calculator", ...)`
      - `search_knowledge` → app/mcp/executor.py:677 `register_builtin_tool("search_knowledge", ...)`
      （注册表本体：executor.py:624 `_BUILTIN_TOOL_HANDLERS`；解析点：executor.py:690）
  · DB `mcp_tool` 表（yn=1）5 个
      - `add` / `echo` / `list_alphabet` / `ping` / `sse_health`
      （SQL：`SELECT tool_name FROM mcp_tool WHERE yn=1`）

因此 `TOOL_CLASS_MAP` 只登记上述 7 个**有实物**的工具（R15b-G1：每个名字都能在注册面命中）。

R15 原表里的 10 个写类工具名——`course_create` / `course_update` / `course_delete` /
`question_create` / `question_update` / `question_delete` / `favorite_add` / `points_change` /
`knowledge_import` / `order_create`——在 executor 注册面与 `mcp_tool` 表**零命中**
（DB 反查 `WHERE tool_name IN (...)` 返回空集），是前批从契约中文语义臆译的虚构名。
现移入 `CONTRACT_PENDING_TOOLS`（契约登记、实物未注册 → 映射挂起）：按 fail-closed，
这些名字对任意角色**仍然 deny**（G2 语义不变）。

**补登记流程（工具真实上线时怎么做）**：
  1. 先在 executor / MCP server 侧真实注册该工具名，并取到出处（file:line 或 DB 行）；
  2. 把名字从 `CONTRACT_PENDING_TOOLS` 移入 `TOOL_CLASS_MAP`，同时在 `REGISTRY_EVIDENCE`
     补一行出处，并把名字加入 `REGISTERED_TOOLS` 对应子集（内置 / MCP）；
  3. 跑 `pytest tests/test_permission_gate.py`：`test_registry_reconciliation_*` 会把
     「仍挂在挂起清单但实际已注册」判为 FAIL，防止映射表与实物再次脱节。

纯逻辑模块：无 DB / 无 LLM / 无 Redis 依赖，可脱离 IO 单测；`audit_registry` 只做集合比对，
真实注册面由调用方（测试）以只读方式采集后传入。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal


@dataclass(frozen=True)
class GateDecision:
    """权限门判定结果。allowed=False 时 action_hint 必为非空可执行建议。"""
    allowed: bool
    action_hint: str | None = None


ToolClass = Literal["public_read", "course_write", "admin_write"]


# ==================================================================
# ① 真实工具注册面（唯一事实源；对账出处见 REGISTRY_EVIDENCE）
#    核对日期：2026-09-15 ｜ 核对对象：app/mcp/executor.py + DB mcp_tool（yn=1）
#    ⚠️ 只放「代码/DB 里真实存在」的工具名，禁止臆译契约中文语义后补名进来。
# ==================================================================
REGISTERED_BUILTIN_TOOLS = frozenset({
    "calculator",          # executor.py:676 register_builtin_tool
    "search_knowledge",    # executor.py:677 register_builtin_tool
})

REGISTERED_MCP_TOOLS = frozenset({
    "add",                 # mcp_tool id=2（server stdio-echodemo）
    "echo",                # mcp_tool id=3（server stdio-echodemo）
    "list_alphabet",       # mcp_tool id=4（server stdio-echodemo）
    "ping",                # mcp_tool id=1（server stdio-echodemo）
    "sse_health",          # mcp_tool id=5（server sse-demo-localhost）
})

REGISTERED_TOOLS: frozenset[str] = REGISTERED_BUILTIN_TOOLS | REGISTERED_MCP_TOOLS

# 工具名 → 注册出处（file:line 或 SQL 结果），供报告逐名对账与人工复核
REGISTRY_EVIDENCE: dict[str, str] = {
    "calculator":       "app/mcp/executor.py:676 register_builtin_tool(\"calculator\", _calculator_handler)",
    "search_knowledge": "app/mcp/executor.py:677 register_builtin_tool(\"search_knowledge\", _search_knowledge_handler)",
    "add":              "SQL mcp_tool: id=2 tool_name=add server_id=1(stdio-echodemo) yn=1",
    "echo":             "SQL mcp_tool: id=3 tool_name=echo server_id=1(stdio-echodemo) yn=1",
    "list_alphabet":    "SQL mcp_tool: id=4 tool_name=list_alphabet server_id=1(stdio-echodemo) yn=1",
    "ping":             "SQL mcp_tool: id=1 tool_name=ping server_id=1(stdio-echodemo) yn=1",
    "sse_health":       "SQL mcp_tool: id=5 tool_name=sse_health server_id=2(sse-demo-localhost) yn=1",
}


# ==================================================================
# ② 已注册工具 → 类别（TOOL_CLASS_MAP：全部有实物，逐名可对账）
#    public_read  ：公开只读工具 —— student/manager/admin
#    ⚠️ course_write / admin_write 在真实注册面**当前为空集**：
#       契约语义仍保留在 _CLASS_ALLOWED_ROLES（矩阵不改），但没有实物工具可归类，
#       故 TOOL_CLASS_MAP 里不出现这两个类别的条目（见 ③ 挂起清单）。
# ==================================================================
PUBLIC_READ_TOOLS: frozenset[str] = frozenset(REGISTERED_TOOLS)

TOOL_CLASS_MAP: dict[str, ToolClass] = {
    **{n: "public_read" for n in PUBLIC_READ_TOOLS},
}


# ==================================================================
# ③ 契约登记但实物未注册（映射挂起）—— CONTRACT_PENDING_TOOLS
#    来源：契约 contracts/reshape-r-aci.json 的中文语义条目
#      · write_class_tools = 收藏写 / 积分变更 / 知识库导入 / 订单创建
#      · 矩阵 manager 条 = 「课程/题库写类」
#    状态：2026-09-15 核对，executor 注册面 + mcp_tool 表**零命中** → 无实物工具。
#    行为：不在 TOOL_CLASS_MAP 中 → classify_tool 返回 None → can_use_tool **一律 deny**
#          （fail-closed 自然拦截，无需特判；这正是「契约已登记、实物未上线」的期望态）。
# ==================================================================
CONTRACT_PENDING_TOOLS: dict[str, ToolClass] = {
    # 课程/题库写类（契约矩阵：manager 放行）—— 实物未注册
    "course_create": "course_write",
    "course_update": "course_write",
    "course_delete": "course_write",
    "question_create": "course_write",
    "question_update": "course_write",
    "question_delete": "course_write",
    # 契约 write_class_tools（仅 admin）—— 实物未注册
    "favorite_add": "admin_write",
    "points_change": "admin_write",
    "knowledge_import": "admin_write",
    "order_create": "admin_write",
}

# 挂起集合（派生，勿手工维护）：按契约类别切分
CONTRACT_PENDING_COURSE_WRITE_TOOLS: frozenset[str] = frozenset(
    n for n, c in CONTRACT_PENDING_TOOLS.items() if c == "course_write"
)
CONTRACT_PENDING_ADMIN_WRITE_TOOLS: frozenset[str] = frozenset(
    n for n, c in CONTRACT_PENDING_TOOLS.items() if c == "admin_write"
)

# 兼容别名（既有消费方：app/chat/flows/langgraph_agent.py:272 `_hitl_risk_level`
# 用它做 HITL 风险分级，tests/test_r11_hitl.py:69 也引用）。
# ⚠️ 语义已明确：这两个集合 = **契约挂起集合**，不含任何已注册实物工具，
#    且**不在** TOOL_CLASS_MAP 中 → 权限门对这些名字仍 deny。
#    HITL 分级按「契约意图」保留（上线后开箱即用），与权限门的 fail-closed 互不冲突。
COURSE_WRITE_TOOLS: frozenset[str] = CONTRACT_PENDING_COURSE_WRITE_TOOLS
ADMIN_WRITE_TOOLS: frozenset[str] = CONTRACT_PENDING_ADMIN_WRITE_TOOLS


# ==================================================================
# ④ 契约矩阵（**语义冻结，R15b 不改**）：类别 → 允许角色
#    CR-ACI-teacher-read（2026-09-15 用户签收）：KNOWN_ROLES 补 teacher，
#    teacher = 公开只读（与 student 同档，不给写类/admin 专属）；
#    未知新角色仍 default=deny，进业务前须先走契约变更单登记（流程防线）。
# ==================================================================
KNOWN_ROLES = frozenset({"admin", "manager", "student", "teacher"})

_CLASS_ALLOWED_ROLES: dict[ToolClass, frozenset[str]] = {
    "public_read": frozenset({"student", "manager", "admin", "teacher"}),
    "course_write": frozenset({"manager", "admin"}),
    "admin_write": frozenset({"admin"}),
}


def class_allowed_roles(cls: ToolClass) -> frozenset[str]:
    """契约矩阵：类别 → 允许角色（供测试/报告核对「矩阵语义未变」）。"""
    return _CLASS_ALLOWED_ROLES[cls]


# ==================================================================
# ⑤ 对账审计（R15b-G1 自动化）
# ==================================================================
def audit_registry(registered: Iterable[str] | None = None) -> dict[str, list[str]]:
    """把「真实注册面」与映射表/挂起清单对账，返回三类差异（**全空 = 对账一致**）。

    Args:
        registered: 真实注册面工具名集合；缺省用模块内 REGISTERED_TOOLS（2026-09-15 核对值）。
                    测试可传入刚从 executor 源码 / mcp_tool 表采集的实时集合。

    Returns:
        mapped_but_unregistered : 映射表里有、注册面没有 —— 即「虚构工具名」，必须为空
        registered_but_unmapped : 注册面有、映射表没有 —— 即「漏登记」，必须为空
        pending_now_registered  : 挂在挂起清单、实际已注册 —— 赶紧按补登记流程迁移
    """
    reg = set(REGISTERED_TOOLS if registered is None else registered)
    return {
        "mapped_but_unregistered": sorted(set(TOOL_CLASS_MAP) - reg),
        "registered_but_unmapped": sorted(reg - set(TOOL_CLASS_MAP)),
        "pending_now_registered": sorted(set(CONTRACT_PENDING_TOOLS) & reg),
    }


def classify_tool(tool_name: str) -> ToolClass | None:
    """返回工具类别；未登记（非实物白名单）返回 None —— 含契约挂起工具。"""
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

    # 未登记工具（含契约挂起工具）/ 未知角色 → 一律 deny
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
