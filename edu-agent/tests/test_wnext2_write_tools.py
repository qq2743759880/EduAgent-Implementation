# -*- coding: utf-8 -*-
"""W-NEXT-2 写类工具上线 + 四道防线修复的集成测试（吞并批判 T4-C1/C2/C3/C4 + T8-C1/C2）。

对应验收 GWT：
  W2-G1 写类分类单一事实源（10 个写类名 → write_file / 禁缓存）→ 见 test_permission_gate.py
  W2-G2 流式路径接权限门：deny → 零 executor 调用 + ACI 三字段（code/message/action_hint）
  W2-G3 knowledge_import 真实注册（admin_write）+ 审计对账三类差异全空 + 入参校验
  W2-G4 真实 LangGraph 图触发 interrupt（五字段）→ confirm 真执行 / reject 零执行
  W2-G6 幻觉式成功检测：全失败/被拦截 → prompt 注入诚实约束，渲染层不 KeyError
  另：兜底文案不泄异常类名（T4-C2 末段）

说明：本文件只做「进程内真实调用」（真实权限门 + 真实 tool_node + 真实 LangGraph
interrupt 三件套），真实 HTTP 实证见 test-reports/WNEXT2-completion-report.md。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

import app.chat.flows.langgraph_agent as lga
from app.chat.flows.langgraph_agent import AgentState, _tool_result_text, generate_node, tool_node
from app.config import settings as _real_settings


# ============================================================
# W2-G2 流式路径（tool_calling.run_chat_tool_calls）接权限门
# ============================================================
def _tool_meta(name: str):
    from app.chat.tool_calling import ToolMeta

    return ToolMeta(
        tool_id=999, server_id=0, tool_name=name,
        description="wnext2 测试用", input_schema_json=None, category="builtin",
        keywords=[name],
    )


def _patch_stream_deps(monkeypatch, *, role: str, called: dict):
    """替身：工具清单只含 knowledge_import；角色固定；executor.call_tool 计数。"""
    import app.ai.permission_gate as pg
    import app.chat.tool_calling as tc
    from app.mcp.executor import MCPToolTestResp, ToolCallStatusEnum

    async def fake_list():
        return [_tool_meta("knowledge_import"), _tool_meta("search_knowledge")]

    async def fake_resolve_role(_uid):
        called["role_queries"] = called.get("role_queries", 0) + 1
        return role

    async def fake_call_tool(**kw):
        called["n"] = called.get("n", 0) + 1
        # 流式路径按 tool_id 调用（与 DB 工具清单同源），工具名由 executor 侧 registry 解析
        called["tool_id"] = kw.get("tool_id")
        return MCPToolTestResp(
            status=ToolCallStatusEnum.SUCCESS, latency_ms=1, call_id="fake-call",
            server_id=0, tool_name="knowledge_import",
            content_text='{"task_id": "task_fake", "status": "pending"}',
        )

    monkeypatch.setattr(tc, "list_enabled_tool_metas", fake_list)
    monkeypatch.setattr(pg, "resolve_role", fake_resolve_role)
    monkeypatch.setattr("app.mcp.executor.call_tool", fake_call_tool)


@pytest.mark.asyncio
async def test_w2g2_stream_write_deny_zero_call_and_aci_envelope(monkeypatch):
    """student × knowledge_import：deny → executor 零调用；summary 内嵌 ACI 三字段；
    上下文含「拦截」+ 诚实性约束（W2-G6）。"""
    called: dict = {}
    _patch_stream_deps(monkeypatch, role="student", called=called)
    from app.chat.tool_calling import run_chat_tool_calls

    summaries, ctx, degraded = await run_chat_tool_calls(
        query="请调用 knowledge_import 把文件导入知识库",
        operator_user_id=1001,
    )

    assert len(summaries) == 1
    s = summaries[0]
    assert s.tool_name == "knowledge_import"
    assert s.status == "error"                       # Literal 只允许 success/error/timeout
    env = json.loads(s.result_summary)               # ACI 信封原样承载
    assert {"code", "message", "action_hint"} <= set(env.keys()), "契约三字段必须齐"
    assert env["code"] == "permission_denied"
    assert env["message"] and env["action_hint"]
    assert called.get("n", 0) == 0, "deny 必须零 executor 调用"
    assert "权限门拦截" in ctx and "action_hint" in ctx
    assert "没有发生任何数据变更" in ctx, "W2-G6 诚实约束必须注入"
    assert degraded is None


@pytest.mark.asyncio
async def test_w2g2_stream_write_admin_allowed_calls_executor(monkeypatch):
    """admin × knowledge_import：放行 → 真实调用 executor 一次（阳性对照）。"""
    called: dict = {}
    _patch_stream_deps(monkeypatch, role="admin", called=called)
    from app.chat.tool_calling import run_chat_tool_calls

    summaries, ctx, _ = await run_chat_tool_calls(
        query="请调用 knowledge_import 把文件导入知识库",
        operator_user_id=1,
    )
    assert called.get("n", 0) == 1, "admin 放行 → 真实调用 executor 一次"
    assert summaries[0].status == "success"
    assert "没有发生任何数据变更" not in ctx, "成功轮不得注入「未执行」约束"


@pytest.mark.asyncio
async def test_w2g2_read_tool_path_does_not_resolve_role(monkeypatch):
    """只读工具路径零额外角色查询（惰性 role 只对写类触发，生产行为不变）。"""
    called: dict = {}
    _patch_stream_deps(monkeypatch, role="student", called=called)
    import app.chat.tool_calling as tc
    from app.chat.tool_calling import run_chat_tool_calls

    async def fake_list_read_only():
        return [_tool_meta("search_knowledge")]

    monkeypatch.setattr(tc, "list_enabled_tool_metas", fake_list_read_only)
    summaries, _, _ = await run_chat_tool_calls(query="search_knowledge 查询课程", operator_user_id=1001)

    assert called.get("role_queries", 0) == 0, "只读路径不应触发角色查询"
    assert called.get("n", 0) == 1


# ============================================================
# W2-G3 knowledge_import 真实注册 + 对账 + 入参校验
# ============================================================
def test_w2g3_knowledge_import_registered_admin_write():
    from app.ai.permission_gate import (
        CONTRACT_PENDING_TOOLS, REGISTERED_BUILTIN_TOOLS, TOOL_CLASS_MAP,
        audit_registry, can_use_tool,
    )
    from app.mcp.executor import _resolve_builtin_name

    assert "knowledge_import" in REGISTERED_BUILTIN_TOOLS
    assert TOOL_CLASS_MAP.get("knowledge_import") == "admin_write"
    assert "knowledge_import" not in CONTRACT_PENDING_TOOLS
    # 真实注册（executor 内置 handler 可解析）而非仅常量声明
    assert _resolve_builtin_name(None, None, "knowledge_import") == "knowledge_import"
    # 对账三类差异全空
    rep = audit_registry()
    assert rep == {"mapped_but_unregistered": [], "registered_but_unmapped": [], "pending_now_registered": []}
    # 角色矩阵
    assert can_use_tool("admin", "knowledge_import").allowed is True
    for role in ("student", "manager", "teacher"):
        d = can_use_tool(role, "knowledge_import")
        assert d.allowed is False and d.action_hint


@pytest.mark.asyncio
async def test_w2g3_handler_argument_validation_no_write(monkeypatch):
    """入参非法 → 抛错且**零落库**（校验先于 task_store.create_task）。"""
    import app.mcp.executor as ex
    from app.knowledge import task_store

    created: list = []

    async def fake_create_task(**kw):
        created.append(kw)
        return {}

    monkeypatch.setattr(task_store, "create_task", fake_create_task)
    monkeypatch.setattr(ex, "_EXEC_CONTEXT", ex._EXEC_CONTEXT)

    with pytest.raises(ValueError):
        await ex._knowledge_import_handler({})                       # 缺 source_files
    with pytest.raises(ValueError):
        await ex._knowledge_import_handler(
            {"source_files": [{"file_name": "a.md"}], "visibility": "secret"}   # 非法可见性
        )
    assert created == [], "入参非法时不得落任务行"


# ============================================================
# W2-G4 真实 LangGraph 图触发 interrupt（五字段）→ confirm/reject
# ============================================================
class _SettingsShim:
    """HITL_ENABLED=True 的最小替身（其余属性透传真实 settings）。"""

    HITL_ENABLED = True

    def __getattr__(self, name):
        return getattr(_real_settings, name)


def _compile_tool_graph():
    """真实 tool_node + 真实 checkpointer 的最小图（入口直连 tool 节点，绕开 LLM 决策）。"""
    g = StateGraph(AgentState)
    g.add_node("tool", tool_node)
    g.add_edge(START, "tool")
    g.add_edge("tool", END)
    return g.compile(checkpointer=InMemorySaver())


def _state(tool_name: str, role: str, args: dict | None = None) -> dict:
    return {
        "messages": [HumanMessage(content="q")],
        "docs": [], "graph_entities": [], "tool_results": [],
        "loop_count": 0, "next_action": "call_tool", "final_answer": "",
        "tool_name": tool_name, "tool_args": args or {"source_files": [{"file_name": "a.md"}]},
        "user_id": 1, "user_role": role,
    }


def _patch_executor_counter(monkeypatch, called: dict, *, status="SUCCESS"):
    from app.mcp.executor import MCPToolTestResp, ToolCallStatusEnum

    async def fake_call_tool(**kw):
        called["n"] = called.get("n", 0) + 1
        called["hitl_decision"] = kw.get("hitl_decision")
        called["args_kw"] = "args" in kw
        return MCPToolTestResp(
            status=getattr(ToolCallStatusEnum, status), latency_ms=2, call_id="c1",
            server_id=0, tool_name=str(kw.get("tool_name") or ""), content_text='{"task_id": "t1"}',
        )

    monkeypatch.setattr("app.mcp.executor.call_tool", fake_call_tool)


@pytest.mark.asyncio
async def test_w2g4_real_graph_interrupt_confirm_executes(monkeypatch):
    """admin × knowledge_import：真实图 interrupt 挂起（五字段齐、零执行）→
    Command(resume=confirm) → 真实调用 executor（hitl_decision=True，避免双重挂起）。"""
    called: dict = {}
    _patch_executor_counter(monkeypatch, called)
    monkeypatch.setattr(lga, "settings", _SettingsShim())

    graph = _compile_tool_graph()
    cfg = {"configurable": {"thread_id": "w2g4-confirm"}}
    r1 = await graph.ainvoke(_state("knowledge_import", "admin"), cfg)

    intr = r1.get("__interrupt__")
    assert intr is not None, "写类工具（admin_write，HITL 开启）必须真实挂起"
    v = getattr(intr[0], "value", intr[0])
    assert set(v.keys()) == {"thread_id", "tool_name", "args", "risk_level", "timeout_s"}
    assert v["tool_name"] == "knowledge_import"
    assert v["risk_level"] == "high"          # admin_write → L3
    assert v["timeout_s"] == 300
    assert called.get("n", 0) == 0, "挂起阶段必须零执行"

    r2 = await graph.ainvoke(Command(resume={"action": "confirm"}), cfg)
    assert called.get("n", 0) == 1, "confirm 后必须真实执行一次"
    assert called.get("args_kw") is True, "call_tool 必须以 args= 关键字传参（原 arguments= 为错参）"
    assert called.get("hitl_decision") is True, "已人工确认 → 不得二次挂起"
    assert r2["tool_results"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_w2g4_real_graph_interrupt_reject_zero_exec(monkeypatch):
    """reject 分支：工具零执行 + 拒绝上下文（status=rejected，渲染层可读）。"""
    called: dict = {}
    _patch_executor_counter(monkeypatch, called)
    monkeypatch.setattr(lga, "settings", _SettingsShim())

    graph = _compile_tool_graph()
    cfg = {"configurable": {"thread_id": "w2g4-reject"}}
    await graph.ainvoke(_state("knowledge_import", "admin"), cfg)
    r2 = await graph.ainvoke(Command(resume={"action": "reject", "reason": "no"}), cfg)

    assert called.get("n", 0) == 0, "reject 必须零执行"
    tr = r2["tool_results"][0]
    assert tr["status"] == "rejected"
    assert tr["action_hint"]
    assert "[已拒绝]" in _tool_result_text(tr)      # T4-C2：无 result 键也不 KeyError


@pytest.mark.asyncio
async def test_w2g4_real_graph_student_denied_no_interrupt(monkeypatch):
    """student × knowledge_import：权限门先于 HITL —— deny、零执行、无 interrupt。"""
    called: dict = {}
    _patch_executor_counter(monkeypatch, called)
    monkeypatch.setattr(lga, "settings", _SettingsShim())

    graph = _compile_tool_graph()
    cfg = {"configurable": {"thread_id": "w2g4-deny"}}
    r = await graph.ainvoke(_state("knowledge_import", "student"), cfg)

    assert r.get("__interrupt__") is None, "未授权操作不应占用人工审批资源"
    assert called.get("n", 0) == 0
    tr = r["tool_results"][0]
    assert tr["status"] == "denied"
    assert tr["code"] == "permission_denied" and tr["message"] and tr["action_hint"]


# ============================================================
# W2-G6 幻觉式成功检测 + T4-C2 渲染断链
# ============================================================
@pytest.mark.parametrize("record", [
    {"tool_name": "knowledge_import", "status": "denied", "code": "permission_denied",
     "message": "权限不足", "action_hint": "联系管理员"},
    {"tool_name": "knowledge_import", "status": "rejected", "code": "hitl_rejected",
     "message": "您拒绝了该高风险操作，工具未执行。", "action_hint": "如需执行可重新提问并确认。"},
    {"tool_name": "knowledge_import", "status": "error"},      # 极端：连 message 都没有
])
def test_w2g6_tool_result_text_never_keyerror(record):
    txt = _tool_result_text(record)
    assert isinstance(txt, str)
    if record["status"] in ("denied", "rejected"):
        assert txt, "拒绝/拦截记录必须有可读文本（否则生成层无拒绝上下文）"


class _FakeChatClient:
    captured: list = []

    @classmethod
    def get(cls):
        return cls()

    def call_chat(self, *, messages, **kw):
        _FakeChatClient.captured.append(messages)
        return "fake-answer"


@pytest.mark.asyncio
async def test_w2g6_generate_node_injects_honesty_constraint(monkeypatch):
    """全未成功（denied）→ generate 的 system prompt 必须含「没有发生任何数据变更」+ 禁用完成态。"""
    _FakeChatClient.captured = []
    monkeypatch.setattr(lga, "_ChatClient", _FakeChatClient)

    state = _state("knowledge_import", "student")
    state["tool_results"] = [{
        "tool_name": "knowledge_import", "status": "denied", "code": "permission_denied",
        "message": "权限不足，操作被拦截。", "action_hint": "请联系管理员开通。",
    }]
    out = await generate_node(state)

    assert out["final_answer"] == "fake-answer"
    sys_prompt = _FakeChatClient.captured[0][0]["content"]
    assert "没有发生任何数据变更" in sys_prompt
    assert "严禁" in sys_prompt and "已完成" in sys_prompt
    assert "[已拦截] 权限不足，操作被拦截。" in sys_prompt, "deny 上下文必须进 generate prompt"


@pytest.mark.asyncio
async def test_t4c2_run_agent_fallback_no_exception_class_leak(monkeypatch):
    """兜底文案不得泄异常类名（本地逻辑缺陷不应伪装成下游故障细节）。"""

    class _Boom:
        async def ainvoke(self, state, config):
            raise KeyError("result")

    monkeypatch.setattr(lga, "agent_graph", _Boom())
    monkeypatch.setattr(lga, "settings", _SettingsShim())
    out = await lga.run_agent("你好", user_id=1, session_id="t4c2")
    assert "KeyError" not in out["answer"]
    assert out["answer"] == "AI 服务异常，请稍后重试"