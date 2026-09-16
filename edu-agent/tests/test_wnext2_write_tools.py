# -*- coding: utf-8 -*-
"""W-NEXT-2 写类工具上线 + 四道防线修复的集成测试（吞并批判 T4-C1/C2/C3/C4 + T8-C1/C2）。

对应验收 GWT：
  W2-G1 写类分类单一事实源（10 个写类名 → write_file / 禁缓存）→ 见 test_permission_gate.py
  W2-G2 流式路径接权限门：deny → 零 executor 调用 + ACI 三字段（code/message/action_hint）
  W2-G3 knowledge_import 真实注册（admin_write）+ 审计对账三类差异全空 + 入参校验
  W2-G4 真实 LangGraph 图触发 interrupt（五字段）→ confirm 真执行 / reject 零执行
  W2-G6 幻觉式成功检测：全失败/被拦截 → prompt 注入诚实约束，渲染层不 KeyError
  另：兜底文案不泄异常类名（T4-C2 末段）
  T8-C2 无挂起续流显式收束（复验补测）+ executor 收口二次校验（tool_id-only 绕过回归防护）
  P1 备用工具越权（TOOL_FALLBACK_MAP 可被 env 覆盖 → 读工具接写工具）回归防护

说明：本文件只做「进程内真实调用」（真实权限门 + 真实 tool_node + 真实 LangGraph
interrupt 三件套），真实 HTTP 实证见 test-reports/WNEXT2-completion-report.md。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

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


async def test_w2g3_handler_path_traversal_rejected_no_pipeline(monkeypatch, tmp_path):
    """路径穿越/任意本地文件读取防护（Mimosa 硬门1，对齐 _safe_upload_id 先例）：
    只有 resolve 后仍落在 allowed root（DATA_DIR/knowledge_uploads）内的常规文件才进 local_paths；
    绝对路径逃逸 / `..` / 根外文件一律不入 → 零读取、零 _process_import、零删除。"""
    import app.mcp.executor as ex
    from app.knowledge import task_store

    data_dir = tmp_path / "data"
    root = data_dir / "knowledge_uploads"
    root.mkdir(parents=True)
    monkeypatch.setattr(ex.settings, "DATA_DIR", str(data_dir))

    legit = root / "legit.md"
    legit.write_text("ok")

    outside = tmp_path / "secret.txt"          # 应用数据目录之外的绝对路径
    outside.write_text("secret")

    created: list = []
    started: list = []

    async def fake_create_task(**kw):
        created.append(kw)
        return {"task_id": "t1", "status": "pending", "task_type": "x",
                "tenant_id": "t", "visibility": "private", "created_at": "now"}

    async def fake_process_import(**kw):
        started.append(kw)  # 只应在「全部条目均为 safe in-root 文件」时才被调度

    monkeypatch.setattr(task_store, "create_task", fake_create_task)
    # handler 内部是 `from app.knowledge.routers.upload import _process_import`
    monkeypatch.setattr("app.knowledge.routers.upload._process_import", fake_process_import)

    # ① 合法 in-root 文件 + 逃逸绝对路径 + `..` 混合 → 只有合法路径被接受，管道不启动
    resp = json.loads(await ex._knowledge_import_handler({
        "source_files": [
            {"file_name": "legit.md", "local_path": str(legit)},
            {"file_name": "evil", "local_path": str(outside)},
            {"file_name": "trav", "local_path": "../../../../Windows/win.ini"},
        ],
        "visibility": "private",
    }))
    assert len(created) == 1
    assert resp["pipeline_started"] is False          # 混入逃逸路径 → 整体不启动
    assert started == [], "含根外路径时不得触发 _process_import"

    # ② 纯合法 in-root 文件 → 管道启动且 local_paths 恰为合法路径
    started.clear()
    created.clear()
    resp2 = json.loads(await ex._knowledge_import_handler({
        "source_files": [{"file_name": "legit.md", "local_path": str(legit)}],
        "visibility": "private",
    }))
    import asyncio
    await asyncio.sleep(0)                            # 让 create_task 调度的 fake 执行
    assert resp2["pipeline_started"] is True
    assert started and started[0]["local_paths"] == [str(legit)]


def test_upload_cleanup_paths_only_deletes_within_root(monkeypatch, tmp_path):
    """纵深防御：_cleanup_paths 只删 allowed root 内文件，根外任意路径绝不 os.remove。"""
    from app.knowledge.routers import upload

    data_dir = tmp_path / "data"
    root = data_dir / "knowledge_uploads"
    root.mkdir(parents=True)
    monkeypatch.setattr(upload.settings, "DATA_DIR", str(data_dir))

    inside = root / "tmp.md"
    inside.write_text("in")
    outside = tmp_path / "do_not_delete.txt"
    outside.write_text("out")

    upload._cleanup_paths([str(inside), str(outside), "../../../../Windows/win.ini"])

    assert not inside.exists(), "根内临时文件应被清理"
    assert outside.exists(), "根外文件绝不能被 os.remove"


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


# ============================================================
# T8-C2 续流静默吞修复：Redis 有决策但图已无挂起 → 显式收束（零图执行）
#   复验指出该分支（graph_stream.py:305-329）原为零测试覆盖，此处补齐两条
#   （confirm 失效 / reject 无挂起），核心断言 = 绝不把 Command(resume) 丢进图静默跑完。
# ============================================================
class _NoPendingGraph:
    """无挂起态的图替身：aget_state.next 为空；astream 被调用即计数（= 静默续跑缺陷）。"""

    def __init__(self) -> None:
        self.astream_calls = 0

    async def aget_state(self, _cfg):
        return SimpleNamespace(next=(), values={})

    async def astream(self, *_a, **_kw):
        self.astream_calls += 1
        if False:  # pragma: no cover — 使其为异步生成器且零产出
            yield None


async def _read_sse(resp) -> str:
    chunks: list[bytes] = []
    async for c in resp.body_iterator:
        chunks.append(c if isinstance(c, bytes) else str(c).encode("utf-8"))
    return b"".join(chunks).decode("utf-8")


@pytest.mark.asyncio
@pytest.mark.parametrize("action,marker,notice", [
    ("confirm", "hitl_confirm_expired_no_pending", "该确认已失效"),
    ("reject", "hitl_rejected_no_pending", "工具未执行"),
])
async def test_t8c2_resume_without_pending_never_silently_runs(monkeypatch, action, marker, notice):
    """有决策 + 图无挂起：发显式收束文案与 degraded_reason，图 astream 零调用。"""
    import app.ai.guard as guard_mod
    import app.chat.flows.graph_stream as gs
    import app.chat.tool_calling as tc
    from app.auth import UserRole
    from app.chat.schemas import RagQueryRequest

    captured: dict = {}
    graph = _NoPendingGraph()

    async def fake_pop(_tid):
        return {"action": action, "created_at": 1}

    async def fake_ensure():
        return graph

    async def fake_tools(**_kw):
        return [], "", None

    def fake_factory(**_kw):
        async def _fin(answer_text, *, degraded_extra=None):
            captured["answer"] = answer_text
            captured["degraded_extra"] = degraded_extra
            return {"session_id": None, "message_id": None, "retrieved_count": 0,
                    "final_count": 0, "latency_ms": 1, "rewrite_query": None,
                    "degraded_reason": None}

        return _fin

    class _Guard:
        async def acquire(self, *_a, **_kw):
            return {"ok": True}

        async def release(self, *_a, **_kw):
            return None

    monkeypatch.setattr(gs, "_pop_hitl_decision", fake_pop)
    monkeypatch.setattr(gs, "_ensure_agent_graph", fake_ensure)
    monkeypatch.setattr(gs, "make_stream_finalize", fake_factory)
    monkeypatch.setattr(tc, "run_chat_tool_calls", fake_tools)
    monkeypatch.setattr(guard_mod, "default_guard", lambda: _Guard())

    req = RagQueryRequest(query="确认执行该写操作", session_id="anon-t8c2", stream=True,
                          use_mcp_tools=False)
    resp = await gs.graph_stream_sse(req, user_id=1001, role=UserRole.STUDENT)
    raw = await _read_sse(resp)

    assert graph.astream_calls == 0, "无挂起 → 禁止把 Command(resume) 丢进图静默按新会话跑完"
    assert marker in raw, "degraded_reason 必须显式标注该次续流失效"
    assert notice in raw, "必须给用户显式提示（不得静默）"
    assert notice in captured.get("answer", ""), "收束文案即用户可见答案"
    assert captured.get("degraded_extra") is None


# ============================================================
# executor 收口二次校验（P1 绕过回归防护）
#   复验实测：`call_tool(tool_id=N)` 不传 tool_name → 调用方名校为空 → ① 校验整体跳过
#   → 写类工具真实执行。修复后 ② registry 解析出的真实名再校验一次。
# ============================================================
@pytest.mark.asyncio
async def test_executor_second_gate_blocks_tool_id_only_write_call(monkeypatch):
    """tool_id-only（不传 tool_name）→ registry 解析出写类名 → deny + 零执行。"""
    import app.ai.permission_gate as pg
    import app.mcp.executor as ex
    from app.mcp.executor import ToolCallStatusEnum, call_tool

    called: dict = {}

    async def fake_get_tool_by_ref(tool_id, server_id, tool_name):
        called["ref"] = (tool_id, server_id, tool_name)
        return {"tool_id": 77, "server_id": 5, "tool_name": "knowledge_import"}

    async def fake_resolve_role(_uid):
        return "student"

    async def fake_execute_single_attempt(**_kw):  # pragma: no cover - deny 后不得触达
        called["exec"] = True
        raise AssertionError("deny 后不得执行")

    monkeypatch.setattr("app.mcp.registry.get_tool_by_ref", fake_get_tool_by_ref)
    monkeypatch.setattr(pg, "resolve_role", fake_resolve_role)
    monkeypatch.setattr(ex, "_execute_single_attempt", fake_execute_single_attempt)

    resp = await call_tool(operator_user_id=1001, tool_id=77)

    assert called.get("ref") == (77, None, None), "必须经 registry 解析真实工具名"
    assert called.get("exec") is None, "越权必须在执行前拦截"
    assert resp.tool_name == "knowledge_import"
    assert resp.status == ToolCallStatusEnum.ERROR
    env = json.loads(resp.content_text)
    assert {"code", "message", "action_hint"} <= set(env.keys())
    assert env["code"] == "permission_denied"


@pytest.mark.asyncio
async def test_executor_second_gate_admin_tool_id_only_still_passes(monkeypatch):
    """阳性对照：admin → ② 不得误伤，流程继续到 server 解析（以哨兵异常证明已过门）。"""
    import app.ai.permission_gate as pg
    import app.mcp.executor as ex
    from app.mcp.executor import call_tool

    async def fake_get_tool_by_ref(tool_id, server_id, tool_name):
        return {"tool_id": 77, "server_id": 5, "tool_name": "knowledge_import"}

    async def fake_resolve_role(_uid):
        return "admin"

    async def sentinel_fetch_one(*_a, **_kw):
        raise RuntimeError("reached-server-resolution")

    monkeypatch.setattr("app.mcp.registry.get_tool_by_ref", fake_get_tool_by_ref)
    monkeypatch.setattr(pg, "resolve_role", fake_resolve_role)
    monkeypatch.setattr(ex, "fetch_one", sentinel_fetch_one)

    with pytest.raises(RuntimeError, match="reached-server-resolution"):
        await call_tool(operator_user_id=1, tool_id=77)


# ============================================================
# P1 配置诱导越权（复验发现 → 已修）：重试闭环第 3 步的备用工具
#   `settings.TOOL_FALLBACK_MAP` 可被环境变量 JSON 覆盖 → 注入
#   {"calculator": ["knowledge_import"]} 即把「读工具 → 写工具」接成一条链路。
#   修复前：student 触发 switch_tool → 写类 handler 真实执行（零门、零 HITL）；
#   修复后：备用目标名与原始名同门 → deny + 零执行。
# ============================================================
def _patch_retry_closure(monkeypatch, *, role: str, called: dict, fallback: dict):
    """替身：备用映射注入 + 角色固定 + 步进执行器只记账（不触达任何真实 handler）。"""
    import app.ai.permission_gate as pg
    import app.mcp.executor as ex
    from app.mcp.executor import ToolCallStatusEnum
    from app.mcp.retry_loop import AttemptOutcome, MemRejectStore

    async def fake_attempt(tool_name, args, *, call_id, attempt, operator_user_id, tenant_id, trace_id):
        called.setdefault("tools", []).append(tool_name)
        return AttemptOutcome(
            ok=False, status=ToolCallStatusEnum.ERROR.value, tool_name=tool_name,
            args=args, latency_ms=1, error_message="boom",
        )

    async def fake_llm_rewrite(_args, _err, _name):
        return None

    async def fake_resolve_role(_uid):
        return role

    monkeypatch.setattr(ex.settings, "TOOL_FALLBACK_MAP", fallback)
    monkeypatch.setattr(pg, "resolve_role", fake_resolve_role)
    return fake_attempt, fake_llm_rewrite, MemRejectStore()


@pytest.mark.asyncio
async def test_p1_fallback_write_tool_blocked_for_student(monkeypatch):
    """student + 备用映射指向 knowledge_import → 第 3 步 deny、备用写类工具零执行。"""
    from app.mcp.executor import ToolCallStatusEnum, call_tool_with_retry

    called: dict = {}
    fake_attempt, fake_rewrite, store = _patch_retry_closure(
        monkeypatch, role="student", called=called,
        fallback={"calculator": ["knowledge_import"]},
    )

    resp = await call_tool_with_retry(
        operator_user_id=1001, tool_name="calculator",
        args={"a": 1, "b": 2, "op": "add"},
        llm_rewrite_fn=fake_rewrite, _attempt_executor=fake_attempt, _reject_store=store,
    )

    assert called.get("tools") == ["calculator", "calculator"], (
        "备用写类工具绝不得进入执行器（前两步为原工具的正常/换参）"
    )
    assert resp.status == ToolCallStatusEnum.ERROR
    env = json.loads(resp.content_text)
    assert {"code", "message", "action_hint"} <= set(env.keys())
    assert env["code"] == "permission_denied"
    assert env["message"] and env["action_hint"]


@pytest.mark.asyncio
async def test_p1_fallback_write_tool_allowed_for_admin(monkeypatch):
    """阳性对照：admin 走同一注入映射 → 备用工具正常进入执行器（门不得误伤）。"""
    from app.mcp.executor import call_tool_with_retry

    called: dict = {}
    fake_attempt, fake_rewrite, store = _patch_retry_closure(
        monkeypatch, role="admin", called=called,
        fallback={"calculator": ["knowledge_import"]},
    )

    await call_tool_with_retry(
        operator_user_id=1, tool_name="calculator",
        args={"a": 1, "b": 2, "op": "add"},
        llm_rewrite_fn=fake_rewrite, _attempt_executor=fake_attempt, _reject_store=store,
    )

    assert called.get("tools") == ["calculator", "calculator", "knowledge_import"], (
        "admin 应放行到第 3 步备用工具（全步失败 → 人工指南）"
    )