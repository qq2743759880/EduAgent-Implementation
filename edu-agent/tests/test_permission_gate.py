# -*- coding: utf-8 -*-
"""R15b 权限门 + ACI 错误信封测试（契约 contracts/reshape-r-aci.json 已冻结）。

R15b 变更：映射表对账实物——TOOL_CLASS_MAP 只含真实注册工具（7 个），
契约写类工具名转入 CONTRACT_PENDING_TOOLS（映射挂起，仍 fail-closed deny）。

覆盖：
- G1 对账：TOOL_CLASS_MAP × executor 注册面（源码实采 + mcp_tool 表实采）逐名可比
- G1 矩阵：真实工具 × 三角色 全组合；契约矩阵「类别→角色」语义未变
- G2 fail-closed：契约挂起工具 / 未登记工具 / 空角色 → 一律 deny
- G3 图级 tool_node deny 路径（不经过 LLM，mock executor.call_tool 零调用）
- G4 角色注入：run_agent 经 get_user_info_by_id 注入 user_role（mock DB 层）
- G6 信封质量抽查：message 全中文无 traceback；action_hint 可执行
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.ai.permission_gate import (
    ADMIN_WRITE_TOOLS,
    CONTRACT_PENDING_TOOLS,
    COURSE_WRITE_TOOLS,
    GateDecision,
    REGISTERED_BUILTIN_TOOLS,
    REGISTERED_MCP_TOOLS,
    REGISTERED_TOOLS,
    REGISTRY_EVIDENCE,
    TOOL_CLASS_MAP,
    audit_registry,
    can_use_tool,
    class_allowed_roles,
    classify_tool,
    permission_denied_message,
)
import app.chat.flows.langgraph_agent as lga
from app.chat.flows.langgraph_agent import run_agent, tool_node

_EXECUTOR_SRC = Path(__file__).resolve().parents[1] / "app" / "mcp" / "executor.py"

# 真实注册工具代表（全部 7 个都在 PUBLIC_READ_TOOLS 里）
READ_TOOL = "search_knowledge"
REAL_TOOLS = sorted(REGISTERED_TOOLS)          # 7 个实物工具
# 契约挂起（无实物）代表工具
PENDING_COURSE_TOOL = "course_create"
PENDING_ADMIN_TOOL = "order_create"
ALL_ROLES = ["student", "manager", "admin"]


# ============================================================
# G1 对账（R15b 核心）：映射表 ↔ 真实注册面
# ============================================================
def _executor_registered_builtins() -> set[str]:
    """从 executor.py 源码实采 `register_builtin_tool("name", ...)`。"""
    src = _EXECUTOR_SRC.read_text(encoding="utf-8")
    return set(re.findall(r'register_builtin_tool\(\s*"([^"]+)"', src))


def test_registry_reconciliation_executor_source():
    """G1：TOOL_CLASS_MAP 里的内置工具与 executor 源码注册面完全一致（双向）。"""
    found = _executor_registered_builtins()
    assert found, "executor.py 未采集到任何 register_builtin_tool，采集逻辑或注册面异常"
    assert found == set(REGISTERED_BUILTIN_TOOLS), (
        f"内置注册面与映射表声明不一致: 源码={sorted(found)} 声明={sorted(REGISTERED_BUILTIN_TOOLS)}"
    )
    # 两个内置工具都必须真的在 TOOL_CLASS_MAP 里（不能只在 REGISTERED_* 常量里）
    for name in found:
        assert name in TOOL_CLASS_MAP, f"内置工具 {name} 未进 TOOL_CLASS_MAP"


def test_registry_reconciliation_pending_absent_from_executor():
    """G1：契约挂起工具名不得出现在 executor 源码（防再次臆译补名）。"""
    src = _EXECUTOR_SRC.read_text(encoding="utf-8")
    offenders = sorted(n for n in CONTRACT_PENDING_TOOLS if n in src)
    assert not offenders, f"executor.py 中出现了挂起工具名（需人工复核是否已真实注册）: {offenders}"


def _db_mcp_tool_names() -> set[str]:
    """直连只读采集 mcp_tool（yn=1）工具名集合；不触碰 app 连接池全局状态。"""
    import asyncmy
    from app.config import settings

    async def _run() -> set[str]:
        conn = await asyncmy.connect(
            host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
            db=settings.MYSQL_DATABASE, autocommit=True,
        )
        try:
            async with conn.cursor() as cur:
                await cur.execute("SELECT tool_name FROM mcp_tool WHERE yn=1")
                rows = await cur.fetchall()
            return {str(r[0]) for r in rows}
        finally:
            conn.close()

    return asyncio.run(_run())


def test_registry_reconciliation_mcp_db():
    """G1：mcp_tool 表实采覆盖映射表声明的 MCP 工具；挂起清单不得已在库。"""
    try:
        names = _db_mcp_tool_names()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB 不可用，跳过 mcp_tool 实采对账: {type(exc).__name__}: {exc}")
    missing = sorted(REGISTERED_MCP_TOOLS - names)
    assert not missing, f"映射表声明已注册但 mcp_tool 缺失（虚构？）: {missing}"
    stale = sorted(set(CONTRACT_PENDING_TOOLS) & names)
    assert not stale, f"挂起清单中的工具已真实注册，应按补登记流程移入 TOOL_CLASS_MAP: {stale}"


def test_registry_reconciliation_audit_clean():
    """G1：audit_registry 三类差异全空（缺省口径 = 2026-09-15 核对值）。"""
    rep = audit_registry()
    assert rep["mapped_but_unregistered"] == [], f"映射表含未注册工具（虚构名）: {rep}"
    assert rep["registered_but_unmapped"] == [], f"注册面工具漏登记: {rep}"
    assert rep["pending_now_registered"] == [], f"挂起工具已注册未迁移: {rep}"


def test_registry_evidence_covers_every_mapped_tool():
    """G1：TOOL_CLASS_MAP 每个工具都有出处条目（报告逐名对账表可复现）。"""
    assert set(REGISTRY_EVIDENCE) == set(TOOL_CLASS_MAP)
    for name in TOOL_CLASS_MAP:
        assert REGISTRY_EVIDENCE[name].strip(), f"{name} 缺注册出处"


# ============================================================
# G1 矩阵：真实工具 × 三角色 全组合
# ============================================================
@pytest.mark.parametrize("role", ALL_ROLES)
@pytest.mark.parametrize("tool", REAL_TOOLS)
def test_matrix_real_tools_all_roles_allowed(role, tool):
    """真实注册工具均为公开只读 → student/manager/admin 全放行。"""
    d = can_use_tool(role, tool)
    assert d.allowed is True, f"{role} × {tool} 应放行（public_read）"


def test_contract_matrix_class_semantics_unchanged():
    """G3：契约矩阵「类别→允许角色」语义未变（R15b 只改映射表，不改矩阵）。"""
    assert class_allowed_roles("public_read") == frozenset({"student", "manager", "admin"})
    assert class_allowed_roles("course_write") == frozenset({"manager", "admin"})
    assert class_allowed_roles("admin_write") == frozenset({"admin"})
    assert len(TOOL_CLASS_MAP) == len(REGISTERED_TOOLS) == 7, "真实工具面应为 7 个"


# ============================================================
# G2 fail-closed
# ============================================================
@pytest.mark.parametrize("role", ALL_ROLES)
def test_fail_closed_unregistered_tool(role):
    d = can_use_tool(role, "nonexistent_tool")
    assert d.allowed is False
    assert d.action_hint


@pytest.mark.parametrize("role", ["", "  ", "unknown", "teacher"])
def test_fail_closed_unknown_role(role):
    # 未知角色（含空白/未登录）→ 公开只读也 deny
    assert can_use_tool(role, READ_TOOL).allowed is False


@pytest.mark.parametrize("role", ALL_ROLES)
@pytest.mark.parametrize("tool", sorted(CONTRACT_PENDING_TOOLS))
def test_pending_tools_denied_for_all_roles(role, tool):
    """G2：契约挂起（无实物）工具 —— 任意角色（含 admin）一律 deny，hint 非空。"""
    d = can_use_tool(role, tool)
    assert d.allowed is False, f"{role} × {tool}（无实物工具）必须 fail-closed deny"
    assert isinstance(d, GateDecision)
    assert d.action_hint and d.action_hint.strip()


def test_pending_tools_absent_from_tool_class_map():
    """G2：10 个虚构名已从 TOOL_CLASS_MAP 移除，转入 CONTRACT_PENDING_TOOLS。"""
    assert len(CONTRACT_PENDING_TOOLS) == 10
    assert set(TOOL_CLASS_MAP) & set(CONTRACT_PENDING_TOOLS) == set()
    for name in CONTRACT_PENDING_TOOLS:
        assert classify_tool(name) is None, f"{name} 不应出现在映射表（无实物注册）"
    # 挂起集合与兼容别名一致（HITL 消费方共用同一事实源）
    assert set(COURSE_WRITE_TOOLS) == {n for n, c in CONTRACT_PENDING_TOOLS.items() if c == "course_write"}
    assert set(ADMIN_WRITE_TOOLS) == {n for n, c in CONTRACT_PENDING_TOOLS.items() if c == "admin_write"}
    assert set(COURSE_WRITE_TOOLS) | set(ADMIN_WRITE_TOOLS) == set(CONTRACT_PENDING_TOOLS)


def test_all_mapping_tools_classified():
    # 映射表每个工具都能被 classify（非 None），且全是公开只读
    for name, cls in TOOL_CLASS_MAP.items():
        assert classify_tool(name) == cls
        assert cls in ("public_read", "course_write", "admin_write")


# ============================================================
# G3 图级 tool_node deny 路径（不经 LLM，直调 tool_node）
# ============================================================
async def _build_state(tool_name, role):
    return {
        "tool_name": tool_name,
        "tool_args": {"a": 1},
        "user_role": role,
        "user_id": 1,
        "messages": [],
    }


def _patch_executor(monkeypatch, called: dict):
    async def fake_call_tool(**kw):
        called["n"] += 1
        called["tool"] = kw.get("tool_name")
        return {"status": "success", "result": "should-not-run"}

    monkeypatch.setattr("app.mcp.executor.call_tool", fake_call_tool)


@pytest.mark.asyncio
async def test_tool_node_denied_student_write(monkeypatch):
    called = {"n": 0}
    _patch_executor(monkeypatch, called)
    out = await tool_node(await _build_state(PENDING_COURSE_TOOL, "student"))

    trs = out["tool_results"]
    assert len(trs) == 1
    tr = trs[0]
    assert tr["tool_name"] == PENDING_COURSE_TOOL
    assert tr["status"] == "denied"
    assert tr["code"] == "permission_denied"
    assert tr["message"]
    assert tr["action_hint"]
    assert called["n"] == 0   # deny 零执行


@pytest.mark.asyncio
async def test_tool_node_denied_manager_admin_write(monkeypatch):
    called = {"n": 0}
    _patch_executor(monkeypatch, called)
    out = await tool_node(await _build_state("favorite_add", "manager"))
    assert out["tool_results"][0]["status"] == "denied"
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_tool_node_denied_admin_pending_tool(monkeypatch):
    """admin 也拦：契约挂起工具无实物，管理员同样 fail-closed。"""
    called = {"n": 0}
    _patch_executor(monkeypatch, called)
    out = await tool_node(await _build_state(PENDING_ADMIN_TOOL, "admin"))
    assert out["tool_results"][0]["status"] == "denied"
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_tool_node_denied_unregistered(monkeypatch):
    called = {"n": 0}
    _patch_executor(monkeypatch, called)
    out = await tool_node(await _build_state("nonexistent_tool", "admin"))
    assert out["tool_results"][0]["status"] == "denied"
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_tool_node_allowed_admin_public_read_passes_to_executor(monkeypatch):
    # 阳性对照：admin × 公开只读 → 正常路径最终调用 executor.call_tool
    called = {"n": 0}
    _patch_executor(monkeypatch, called)
    out = await tool_node(await _build_state("search_knowledge", "admin"))
    tr = out["tool_results"][0]
    assert tr["status"] == "success"
    assert called["n"] == 1 and called["tool"] == "search_knowledge"


@pytest.mark.asyncio
async def test_tool_node_allowed_student_real_tool_passes_to_executor(monkeypatch):
    # 阳性对照：student × 真实只读工具（非 search_knowledge）→ 放行并真实调用
    called = {"n": 0}
    _patch_executor(monkeypatch, called)
    out = await tool_node(await _build_state("echo", "student"))
    tr = out["tool_results"][0]
    assert tr["status"] == "success"
    assert called["n"] == 1 and called["tool"] == "echo"


# ============================================================
# G4 角色注入（R15 P0-3 反哺）：run_agent ← get_user_info_by_id
#     mock DB 层，断言 user_role 注入逻辑；真实 DB 冒烟见完成报告
# ============================================================
class _FakeGraph:
    """替身图：捕获 run_agent 传入的 initial_state，不跑 LLM / 不碰 DB。"""

    def __init__(self):
        self.captured: dict | None = None
        self.config: dict | None = None

    async def ainvoke(self, state, config):
        self.captured = dict(state)
        self.config = config
        return {**state, "final_answer": "ok", "loop_count": 0}


def _user_info(role):
    from app.auth.schemas import UserInfo

    return UserInfo(
        user_id=7, account="u000007", username="u000007", nickname="测试用户",
        real_name=None, mobile=None, email=None, gender=None, avatar_url=None, role=role,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("role_value,expected", [
    ("manager", "manager"),
    ("admin", "admin"),
    ("student", "student"),
])
async def test_run_agent_injects_role_from_get_user_info_by_id(monkeypatch, role_value, expected):
    """G4：run_agent 查 get_user_info_by_id → 把 info.role.value 注入 AgentState.user_role。"""
    from app.auth.schemas import UserRole

    seen = {}
    fake = _FakeGraph()
    monkeypatch.setattr(lga, "agent_graph", fake)

    async def fake_get_user_info_by_id(uid):
        seen["uid"] = uid
        return _user_info(UserRole(role_value))

    monkeypatch.setattr("app.auth.service.get_user_info_by_id", fake_get_user_info_by_id)

    out = await run_agent("你好", user_id=7, session_id="s-g4")

    assert seen["uid"] == 7
    assert fake.captured is not None
    assert fake.captured["user_role"] == expected
    assert fake.captured["user_id"] == 7
    assert fake.config == {"configurable": {"thread_id": "s-g4"}}
    assert out["answer"] == "ok"


@pytest.mark.asyncio
async def test_run_agent_role_missing_falls_back_to_student(monkeypatch):
    """G4：用户查不到（None）→ user_role 兜底 student（fail-closed 侧兜底）。"""
    fake = _FakeGraph()
    monkeypatch.setattr(lga, "agent_graph", fake)

    async def fake_none(uid):
        return None

    monkeypatch.setattr("app.auth.service.get_user_info_by_id", fake_none)
    await run_agent("你好", user_id=999999, session_id="s-g4-none")
    assert fake.captured["user_role"] == "student"


@pytest.mark.asyncio
async def test_run_agent_role_lookup_error_falls_back_to_student(monkeypatch):
    """G4：角色查询抛错 → 不冒泡、兜底 student（服务不因角色查询失败而挂）。"""
    fake = _FakeGraph()
    monkeypatch.setattr(lga, "agent_graph", fake)

    async def fake_boom(uid):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.auth.service.get_user_info_by_id", fake_boom)
    await run_agent("你好", user_id=7, session_id="s-g4-err")
    assert fake.captured["user_role"] == "student"


@pytest.mark.asyncio
async def test_injected_role_actually_drives_gate(monkeypatch):
    """G4 闭环：注入的 manager 角色直接决定权限门判定（实物放行 / 挂起写类 deny）。"""
    from app.auth.schemas import UserRole

    fake = _FakeGraph()
    monkeypatch.setattr(lga, "agent_graph", fake)

    async def fake_manager(uid):
        return _user_info(UserRole.MANAGER)

    monkeypatch.setattr("app.auth.service.get_user_info_by_id", fake_manager)
    await run_agent("你好", user_id=7, session_id="s-g4-gate")

    role = fake.captured["user_role"]
    assert can_use_tool(role, "echo").allowed is True            # 真实只读工具放行
    assert can_use_tool(role, PENDING_ADMIN_TOOL).allowed is False  # 无实物写类仍 deny


def test_get_user_info_by_id_symbol_is_real_db_lookup():
    """G4：注入源确实存在且是 async DB 查询（防注入点被改名/移除后测试空转）。"""
    from app.auth.service import get_user_info_by_id

    assert asyncio.iscoroutinefunction(get_user_info_by_id)


# ============================================================
# G6 信封质量抽查
# ============================================================
def test_envelope_quality_chinese_no_traceback():
    for role, tool in [
        ("student", PENDING_ADMIN_TOOL),
        ("manager", PENDING_ADMIN_TOOL),
        ("student", PENDING_COURSE_TOOL),
        ("admin", PENDING_ADMIN_TOOL),
        ("admin", "nonexistent_tool"),
    ]:
        msg = permission_denied_message(role, tool)
        assert msg
        assert "traceback" not in msg.lower()
        assert "Traceback" not in msg
        # 全中文（不含 ASCII 可读字符混杂的错误码堆砌）
        assert any("\u4e00" <= ch <= "\u9fff" for ch in msg)
        # 面向用户：不输出堆栈/对象地址
        assert "0x" not in msg and "File " not in msg
        d = can_use_tool(role, tool)
        if not d.allowed:
            assert d.action_hint and d.action_hint.strip()


def test_denied_action_hint_actionable():
    for role, tool in [("student", "order_create"), ("student", "knowledge_import"),
                       ("admin", "nonexistent_tool")]:
        d = can_use_tool(role, tool)
        assert d.allowed is False
        # 可行动建议：包含请求动词线索（登录 / 联系 / 开通）
        assert any(k in d.action_hint for k in ("登录", "联系", "开通"))
