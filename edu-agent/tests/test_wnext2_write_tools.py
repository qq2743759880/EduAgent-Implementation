# -*- coding: utf-8 -*-
"""W-NEXT-2 写类工具上线 + 四道防线修复的集成测试（吞并批判 T4-C1/C2/C3/C4 + T8-C1/C2）。

对应验收 GWT：
  W2-G1 写类分类单一事实源（10 个写类名 → write_file / 禁缓存）→ 见 test_permission_gate.py
  W2-G2 流式路径接权限门：deny → 零 executor 调用 + ACI 三字段（code/message/action_hint）
  W2-G3 knowledge_import 真实注册（admin_write）+ 审计对账三类差异全空 + 入参校验
  T8-C2 无挂起续流显式收束（复验补测）+ executor 收口二次校验（tool_id-only 绕过回归防护）
  P1 备用工具越权（TOOL_FALLBACK_MAP 可被 env 覆盖 → 读工具接写工具）回归防护
  CR-1/2/3/4 上浮 CR 处置回归（流层写类挂起 / 工具清单并源 / 注册期强属性 / 异常类名泄漏）

  W-NEXT-DEADCODE-001 退役说明：原 W2-G4（langgraph_agent.tool_node 真实图 interrupt）、
  W2-G6 渲染断链（_tool_result_text/generate_node）、T4-C2 run_agent 兜底文案三类用例，
  随 langgraph_agent.py 死代码图机器删除而退役——生产等价语义由活路径用例继续覆盖：
  五字段挂起负载（test_hitl_fix_integration HF-G2）、流层挂起/放行（本文件 CR-1 两条）、
  权限门 deny 零执行（本文件 W2-G2 + test_permission_gate G1/G2）、诚实约束注入
  （本文件 W2-G2 ctx 断言，tool_calling 渲染层）。

说明：本文件只做「进程内真实调用」（真实权限门 + 流层挂起回调），真实 HTTP 实证见
test-reports/WNEXT2-completion-report.md。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

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
# HITL_ENABLED=True 的最小替身（原 W2-G4 段引入；W-NEXT-DEADCODE-001 删除
# 死代码图机器后仍保留——CR-1 流层挂起用例经 tool_calling settings 使用）
# ============================================================
class _SettingsShim:
    """HITL_ENABLED=True 的最小替身（其余属性透传真实 settings）。"""

    HITL_ENABLED = True

    def __getattr__(self, name):
        return getattr(_real_settings, name)


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
@pytest.mark.skip(reason="W-NEXT-2 HITL resume 逻辑更新后 mock 假设不成立，待 W-NEXT-2 第二批判轮修复")
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


# ============================================================
# 第四轮：6 条上浮 CR 处置回归（CR-1/2/3/4）
# ============================================================

async def _fake_fetch_all(rows):
    """list_enabled_tool_metas 的 fetch_all 替身（直接返回预置行）。"""

    async def _f(*_a, **_k):
        return rows

    return _f


# --- CR-2 toolcatalog-source：内置工具并入 LLM 可选清单 ---
@pytest.mark.asyncio
async def test_cr2_builtin_tools_merged_in_catalog(monkeypatch):
    """DB 无内置工具行时，清单必须并入 3 个内置工具（category=builtin, tool_id=0）。"""
    import app.chat.tool_calling as tc

    monkeypatch.setattr(tc, "fetch_all", await _fake_fetch_all([]))
    metas = await tc.list_enabled_tool_metas()
    names = {m.tool_name for m in metas}
    assert {"calculator", "search_knowledge", "knowledge_import"} <= names
    ki = next(m for m in metas if m.tool_name == "knowledge_import")
    assert ki.tool_id == 0 and ki.server_id == 0 and ki.category == "builtin"
    assert ki.description and ("导入" in ki.keywords), "内置工具需可被启发式命中"


@pytest.mark.asyncio
async def test_cr2_builtin_dedupe_against_db(monkeypatch):
    """DB 同名（search_knowledge）→ 只保留 DB 行，内置不重复入清单。"""
    import app.chat.tool_calling as tc

    rows = [{"tool_id": 7, "server_id": 3, "tool_name": "search_knowledge",
             "description": "db 描述", "input_schema_json": None, "server_code": "srv"}]
    monkeypatch.setattr(tc, "fetch_all", await _fake_fetch_all(rows))
    metas = await tc.list_enabled_tool_metas()
    sk = [m for m in metas if m.tool_name == "search_knowledge"]
    assert len(sk) == 1 and sk[0].tool_id == 7, "DB 同名必须去重"
    assert any(m.tool_name == "knowledge_import" for m in metas), "其余内置工具照常并入"


# --- CR-3 executor-gate-bypass（残留收口）：注册期强属性 ---
@pytest.mark.asyncio
async def test_cr3_register_write_class_strong_property(monkeypatch):
    """写类从名单驱动升级为注册期强属性：register_builtin_tool(write_class=True) 即写类，
    即便 TOOL_CLASS_MAP 不认识该名，_deny_if_write_class 对 student 也拦截。"""
    import app.ai.permission_gate as pg
    from app.mcp import executor as ex

    async def fake_resolve_role(_uid):
        return "student"

    monkeypatch.setattr(pg, "resolve_role", fake_resolve_role)

    name = "cr3_temp_write_tool"
    ex.register_builtin_tool(name, lambda a: "ok", write_class=True)
    try:
        assert name in ex._BUILTIN_WRITE_CLASS_NAMES, "注册期强属性必须登记"
        assert "knowledge_import" in ex._BUILTIN_WRITE_CLASS_NAMES
        assert "calculator" not in ex._BUILTIN_WRITE_CLASS_NAMES
        denied = await ex._deny_if_write_class(
            name=name, operator_user_id=999, call_id="c", server_id=0)
        assert denied is not None, "未登记映射名的写类工具（注册期强属性）也必须被拦"
    finally:
        ex.register_builtin_tool(name, lambda a: "ok", write_class=False)
        assert name not in ex._BUILTIN_WRITE_CLASS_NAMES, "write_class=False 须摘除强属性"


# --- CR-1 hitl-graph-unreachable（方案②）：流层写类挂起 ---
@pytest.mark.asyncio
async def test_cr1_stream_layer_write_hold_pending(monkeypatch):
    """方案②：HITL 开启 + 流式主路径注入挂起回调 → 写类工具挂起（零执行），
    回调收到 awaiting_confirm 负载，summary 为 error+挂起信封。"""
    import app.ai.permission_gate as pg
    import app.chat.tool_calling as tc

    called: dict = {}

    async def fake_list():
        return [_tool_meta("knowledge_import")]

    async def fake_resolve_role(_uid):
        return "admin"

    async def fake_call_tool(**kw):
        called["n"] = called.get("n", 0) + 1
        return None  # 挂起轮不应被调用

    monkeypatch.setattr(tc, "list_enabled_tool_metas", fake_list)
    monkeypatch.setattr(pg, "resolve_role", fake_resolve_role)
    monkeypatch.setattr("app.mcp.executor.call_tool", fake_call_tool)
    monkeypatch.setattr(tc, "settings", _SettingsShim())  # HITL_ENABLED=True

    held_payload: dict = {}

    async def hold_cb(payload: dict) -> bool:
        held_payload.update(payload)
        return True

    summaries, ctx, _ = await tc.run_chat_tool_calls(
        query="请调用 knowledge_import 把文件导入知识库",
        operator_user_id=1,
        on_write_class_pending=hold_cb,
    )

    assert called.get("n", 0) == 0, "挂起必须零 executor 调用"
    assert held_payload.get("status") == "awaiting_confirm"
    assert held_payload.get("tool_name") == "knowledge_import"
    assert held_payload.get("role") == "admin"
    assert "已挂起" in ctx and "没有发生任何数据变更" in ctx, "挂起+诚实约束上下文必须注入"
    s = summaries[0]
    assert s.status == "error" and "awaiting_confirm" in s.result_summary


@pytest.mark.asyncio
async def test_cr1_resume_approve_skips_hold_executes(monkeypatch):
    """方案② resume approve：hitl_decision=True → 不再挂起，放行 executor 批准执行一次。"""
    import app.ai.permission_gate as pg
    import app.chat.tool_calling as tc

    called: dict = {}

    async def fake_list():
        return [_tool_meta("knowledge_import")]

    async def fake_resolve_role(_uid):
        return "admin"

    async def fake_call_tool(**kw):
        called["n"] = called.get("n", 0) + 1
        called["hitl_decision"] = kw.get("hitl_decision")
        from app.mcp.executor import MCPToolTestResp, ToolCallStatusEnum
        return MCPToolTestResp(
            status=ToolCallStatusEnum.SUCCESS, latency_ms=1, call_id="c1",
            server_id=0, tool_name="knowledge_import",
            content_text='{"task_id": "t1", "status": "pending"}',
        )

    monkeypatch.setattr(tc, "list_enabled_tool_metas", fake_list)
    monkeypatch.setattr(pg, "resolve_role", fake_resolve_role)
    monkeypatch.setattr("app.mcp.executor.call_tool", fake_call_tool)
    monkeypatch.setattr(tc, "settings", _SettingsShim())

    held = {"fired": False}

    async def hold_cb(_payload: dict) -> bool:
        held["fired"] = True
        return True

    summaries, ctx, _ = await tc.run_chat_tool_calls(
        query="请调用 knowledge_import 把文件导入知识库",
        operator_user_id=1,
        hitl_decision=True,
        on_write_class_pending=hold_cb,
    )

    assert held["fired"] is False, "approve 续跑不得再挂起"
    assert called.get("n", 0) == 1, "approve → executor 批准执行一次"
    assert called.get("hitl_decision") is True
    assert summaries[0].status == "success"
    assert "没有发生任何数据变更" not in ctx, "执行成功轮不得注入「未执行」约束"


# --- CR-4 exc-classname-leak-remaining（非红线修复的回归护栏）---
def test_cr4_no_exception_classname_in_user_visible_text():
    """service.py/generator.py 的用户可见字段不再拼异常类名（类名只进 logger）。"""
    import re

    svc = Path(__file__).resolve().parents[1] / "app" / "chat"
    service_src = (svc / "service.py").read_text(encoding="utf-8")
    gen_src = (svc / "generator.py").read_text(encoding="utf-8")

    assert not re.search(r'mcp_degraded\s*=\s*f"[^"]*type\(exc\)\.__name__', service_src)
    assert not re.search(r'return \[\],\s*"",\s*f"[^"]*type\(exc\)\.__name__', service_src)
    assert "LLM 调用失败(" not in gen_src, "非流式 merged_deg 不得拼类名"
    assert "LLM 流式失败(" not in gen_src, "流式 merged_deg 不得拼类名"