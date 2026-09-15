# -*- coding: utf-8 -*-
"""R15 权限门 + ACI 错误信封测试（契约 contracts/reshape-r-aci.json 已冻结）。

覆盖：
- G1 角色×工具 矩阵全组合（can_use_tool）
- G2 fail-closed：未登记工具 / 空角色 → 一律 deny
- G3 图级 tool_node deny 路径（不经过 LLM，mock executor.call_tool 零调用）
- G6 信封质量抽查：message 全中文无 traceback；action_hint 可执行
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.ai.permission_gate import (
    GateDecision,
    TOOL_CLASS_MAP,
    can_use_tool,
    classify_tool,
    permission_denied_message,
)
from app.chat.flows.langgraph_agent import tool_node

# 每类别挑代表工具
READ_TOOL = "search_knowledge"
COURSE_WRITE_TOOL = "course_create"
ADMIN_WRITE_TOOL = "order_create"   # 契约 write_class_tools：订单创建


# ============================================================
# G1 矩阵全组合
# ============================================================
@pytest.mark.parametrize("role,tool,expected", [
    # student：公开只读放行；写类（课程/题库 + 收藏/积分/导入/订单）全部 deny
    ("student", READ_TOOL, True),
    ("student", "calculator", True),
    ("student", COURSE_WRITE_TOOL, False),
    ("student", "question_update", False),
    ("student", ADMIN_WRITE_TOOL, False),
    ("student", "favorite_add", False),
    ("student", "points_change", False),
    ("student", "knowledge_import", False),
    # manager：只读 + 课程/题库写类放行；admin 专属写类 deny
    ("manager", READ_TOOL, True),
    ("manager", "add", True),
    ("manager", COURSE_WRITE_TOOL, True),
    ("manager", "question_update", True),
    ("manager", ADMIN_WRITE_TOOL, False),
    ("manager", "favorite_add", False),
    ("manager", "knowledge_import", False),
    # admin：全量已登记工具放行
    ("admin", READ_TOOL, True),
    ("admin", "echo", True),
    ("admin", COURSE_WRITE_TOOL, True),
    ("admin", "question_delete", True),
    ("admin", ADMIN_WRITE_TOOL, True),
    ("admin", "points_change", True),
    ("admin", "order_create", True),
])
def test_matrix_full(role, tool, expected):
    d = can_use_tool(role, tool)
    assert d.allowed is expected
    if not expected:  # deny 时 action_hint 必非空
        assert isinstance(d, GateDecision)
        assert d.action_hint and d.action_hint.strip()


# ============================================================
# G2 fail-closed
# ============================================================
@pytest.mark.parametrize("role", ["admin", "manager", "student"])
def test_fail_closed_unregistered_tool(role):
    d = can_use_tool(role, "nonexistent_tool")
    assert d.allowed is False
    assert d.action_hint


@pytest.mark.parametrize("role", ["", "  ", "unknown", "teacher"])
def test_fail_closed_unknown_role(role):
    # 未知角色（含空白/未登录）→ 公开只读也 deny
    assert can_use_tool(role, READ_TOOL).allowed is False


def test_all_mapping_tools_classified():
    # 映射表每个工具都能被 classify（非 None）
    assert len(TOOL_CLASS_MAP) >= 7
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


@pytest.mark.asyncio
async def test_tool_node_denied_student_write(monkeypatch):
    called = {"n": 0}

    async def fake_call_tool(**kw):
        called["n"] += 1
        return {"status": "success", "result": "should-not-run"}

    monkeypatch.setattr("app.mcp.executor.call_tool", fake_call_tool)
    out = await tool_node(await _build_state(ADMIN_WRITE_TOOL, "student"))

    trs = out["tool_results"]
    assert len(trs) == 1
    tr = trs[0]
    assert tr["tool_name"] == ADMIN_WRITE_TOOL
    assert tr["status"] == "denied"
    assert tr["code"] == "permission_denied"
    assert tr["message"]
    assert tr["action_hint"]
    # deny 零执行：executor.call_tool 未被调用
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_tool_node_denied_manager_admin_write(monkeypatch):
    called = {"n": 0}

    async def fake_call_tool(**kw):
        called["n"] += 1
        return {"status": "success", "result": "x"}

    monkeypatch.setattr("app.mcp.executor.call_tool", fake_call_tool)
    out = await tool_node(await _build_state("favorite_add", "manager"))
    assert out["tool_results"][0]["status"] == "denied"
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_tool_node_denied_unregistered(monkeypatch):
    called = {"n": 0}

    async def fake_call_tool(**kw):
        called["n"] += 1
        return {"status": "success", "result": "x"}

    monkeypatch.setattr("app.mcp.executor.call_tool", fake_call_tool)
    out = await tool_node(await _build_state("nonexistent_tool", "admin"))
    assert out["tool_results"][0]["status"] == "denied"
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_tool_node_allowed_admin_public_read_passes_to_executor(monkeypatch):
    # 阳性对照：admin × 公开只读 → 正常路径最终调用 executor.call_tool
    seen = {}

    async def fake_call_tool(**kw):
        seen["tool"] = kw.get("tool_name")
        return {"status": "success", "result": "ok"}

    monkeypatch.setattr("app.mcp.executor.call_tool", fake_call_tool)
    out = await tool_node(await _build_state("search_knowledge", "admin"))
    tr = out["tool_results"][0]
    assert tr["status"] == "success"
    assert seen.get("tool") == "search_knowledge"   # call_tool 确实被调用，正常路径未破坏


# ============================================================
# G6 信封质量抽查
# ============================================================
def test_envelope_quality_chinese_no_traceback():
    for role, tool in [
        ("student", ADMIN_WRITE_TOOL),
        ("manager", ADMIN_WRITE_TOOL),
        ("student", COURSE_WRITE_TOOL),
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