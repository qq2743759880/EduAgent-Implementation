# -*- coding: utf-8 -*-
"""SURFACED-1 修复的单元测试（HITL 第 4 道防线闭环 P0）。

对应验收 GWT：
  SF-G1 tool_calling.py:417 修复后单测过；流式 confirm 真闭环（knowledge_import_task +1）
        —— 本文件用进程内真实调用 + mock executor 断言「内置工具必须传 tool_name」，
           复现 HITL-FIX 批判的 42200 阻断根因已被消除。
  SF-G2 executor._resolve_builtin_name 缺 tool_name → 42200 AppException（不静默吞）

说明：全部为进程内测试（mock executor / 不触 DB / 不触 LLM），可在任意时段跑；
真实 HTTP 端到端（confirm → knowledge_import_task 落行）见 check-demo.mjs ⑫ + T11 重测脚本，
受测试窗口(12-14/18-next9) + 8000 门禁。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import app.chat.tool_calling as tc
from app.chat.tool_calling import ToolMeta
from app.common.exceptions import AppException
from app.mcp.executor import MCPToolTestResp, ToolCallStatusEnum, _resolve_builtin_name


# ============================================================
# SF-G1：内置工具经 chat 流式触发必须同时传 tool_id=0 与 tool_name
# ============================================================
@pytest.mark.asyncio
async def test_builtin_must_pass_tool_name(monkeypatch):
    """只读内置工具 calculator（tool_id=0）经 run_chat_tool_calls 触发时，
    调 executor.call_tool 必须同时带 tool_id==0 与 tool_name 非空 ——
    这是 SURFACED-1 的根因修复（旧代码只传 tool_id 不传 tool_name → executor 拒收 42200）。"""
    captured: dict = {}

    async def fake_list():
        return [ToolMeta(
            tool_id=0, server_id=0, tool_name="calculator",
            description="本地四则运算计算器", input_schema_json=None, category="builtin",
            keywords=["calculator", "计算", "calc"],
        )]

    async def fake_call_tool(**kw):
        captured.update(kw)
        return MCPToolTestResp(
            status=ToolCallStatusEnum.SUCCESS, latency_ms=1, call_id="fake-call",
            server_id=0, tool_name="calculator", content_text="2",
        )

    monkeypatch.setattr(tc, "list_enabled_tool_metas", fake_list)
    monkeypatch.setattr("app.mcp.executor.call_tool", fake_call_tool)

    summaries, _, _ = await tc.run_chat_tool_calls(query="计算 1+1 等于多少", operator_user_id=1)

    assert captured.get("tool_id") == 0, "内置工具必须传 tool_id=0"
    assert captured.get("tool_name") == "calculator", (
        "SURFACED-1 回归：内置工具必须同时传 tool_name，否则 executor 拒收「必须提供 tool_id 或 server_id+tool_name」"
    )
    assert summaries and summaries[0].status == "success"


@pytest.mark.asyncio
async def test_write_builtin_passes_tool_name(monkeypatch):
    """写类内置工具 knowledge_import（admin 放行后）调 executor.call_tool 必须带 tool_name，
    而非仅 tool_id=0 —— 直接堵死 HITL-FIX 后 admin confirm 零落库的同源缺口。"""
    captured: dict = {}
    from app.ai.permission_gate import resolve_role

    async def fake_list():
        return [ToolMeta(
            tool_id=0, server_id=0, tool_name="knowledge_import",
            description="知识库导入（写类，管理员专用）", input_schema_json=None, category="builtin",
            keywords=["knowledge_import", "导入", "import"],
        )]

    async def fake_resolve_role(_uid):
        return "admin"

    async def fake_call_tool(**kw):
        captured.update(kw)
        return MCPToolTestResp(
            status=ToolCallStatusEnum.SUCCESS, latency_ms=1, call_id="fake-call",
            server_id=0, tool_name="knowledge_import",
            content_text='{"task_id": "task_fake", "status": "pending"}',
        )

    monkeypatch.setattr(tc, "list_enabled_tool_metas", fake_list)
    monkeypatch.setattr("app.ai.permission_gate.resolve_role", fake_resolve_role)
    monkeypatch.setattr("app.mcp.executor.call_tool", fake_call_tool)

    summaries, ctx, _ = await tc.run_chat_tool_calls(
        query="请调用 knowledge_import 把文件导入知识库", operator_user_id=1,
    )

    assert captured.get("tool_id") == 0
    assert captured.get("tool_name") == "knowledge_import", "写类内置工具必须传 tool_name"
    assert summaries and summaries[0].status == "success"
    assert "没有发生任何数据变更" not in ctx, "成功轮不得注入「未执行」约束"


# ============================================================
# SF-G2：_resolve_builtin_name 缺 tool_name（内置哨兵 tool_id=0）必须 fail-fast 抛 42200
# ============================================================
def test_resolve_builtin_name_raises_on_missing_tool_name():
    """仅传 tool_id=0 不传 tool_name → 42200 AppException（不再静默返回空串让上层吞）。"""
    with pytest.raises(AppException) as exc:
        _resolve_builtin_name(0, None, None)
    assert exc.value.code == 42200
    assert "tool_name" in exc.value.message


def test_resolve_builtin_name_real_tool_no_false_positive():
    """真实 DB 工具（tool_id>0）与按 tool_name 直传的非内置工具不受影响（返回空串）。"""
    # 真实 DB 工具：tool_id=5, 无 tool_name
    assert _resolve_builtin_name(5, None, None) == ""
    # 按名字直传的非内置工具（如 add）：仍不是内置 → 返回空串
    assert _resolve_builtin_name(None, None, "add") == ""
    # 内置工具按名字直传：正常解析
    assert _resolve_builtin_name(None, None, "knowledge_import") == "knowledge_import"
    # 内置工具 tool_id=0 + 名字：正常解析（修复后路径）
    assert _resolve_builtin_name(0, None, "calculator") == "calculator"


@pytest.mark.asyncio
async def test_call_tool_builtin_requires_tool_name_surfaced1_regression(monkeypatch):
    """SURFACED-1 回归实锤：executor.call_tool 仅收 tool_id=0 / tool_name=None（旧 tool_calling 行为）
    必须抛 42200 —— 证明 HITL-FIX 后 admin confirm 写类工具零落库的根因已被守卫挡住。"""
    import app.mcp.executor as ex

    # 避免任何 DB/registry 副作用：守卫在 _resolve_builtin_name 第一步即触发，无需后续 IO
    with pytest.raises(AppException) as exc:
        await ex.call_tool(
            operator_user_id=1, tenant_id="", trace_id="",
            tool_id=0, tool_name=None, args={},
        )
    assert exc.value.code == 42200
    assert "tool_name" in exc.value.message
