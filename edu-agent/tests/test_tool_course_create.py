# -*- coding: utf-8 -*-
"""AUTO20 T12：course_create 写类工具（admin_write 高危首例，强制 HITL）单测。

CR-WRITETOOLS-001 第二批（用户 P2/P4 已批裁定，docs/时光.md §四 B1-B5）：
- P2 类别 admin_write：仅 admin=allow、manager/student/teacher=deny、guest(未知角色)=deny
- P4 executor 双保险：handler 首行校验执行上下文 `hitl_confirmed`（服务端在 resume confirm
  批准时注入），未确认 → 42201 拒（service 零调用）
- 闸3 HITL 链：`_hitl_risk_level("course_create")="high"`（P2 medium→high 语义变更锁定）；
  pending_confirm 五字段帧（thread_id/tool_name/args/risk_level=high/timeout_s）全链回归
- 参数 exact-pin：仅 title(str 非空)/series_code(str ^[a-z0-9_]+$)/modules(list[str] 可选)
- T7 诱导盲测：student 发「帮我创建课程」→ permission deny + ACI 信封，不出现确认卡
- T8 审计：confirm 执行后 mcp_tool_call_log 行含 operator/tool/args
"""
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.ai import permission_gate as pg
from app.mcp import executor as ex
from app.common.exceptions import AppException


def _set_exec_ctx(uid: int, *, hitl_confirmed: bool | None = None) -> None:
    """注入执行上下文（模拟 call_tool 入口对 _EXEC_CONTEXT 的服务端设置）。"""
    ctx: dict = {"operator_user_id": uid, "tenant_id": "_test", "trace_id": "t-t12"}
    if hitl_confirmed is not None:
        ctx["hitl_confirmed"] = hitl_confirmed
    ex._EXEC_CONTEXT.set(ctx)


# ═══════════════════════════════════════════════════════════
# P4 双保险：未确认 → 42201 拒（service 零调用）——时光.md §B4 T4
# ═══════════════════════════════════════════════════════════
def test_t4_unconfirmed_rejected_42201_service_never_called(monkeypatch):
    """ctx 无 hitl_confirmed（首轮挂起场景）→ 42201 AppException；service 零调用。"""
    called: list = []

    async def fake_create(_data):
        called.append(_data)  # pragma: no cover —— 被调即 FAIL

    monkeypatch.setattr("app.domains.course_admin.service.create_series", fake_create)
    _set_exec_ctx(1)  # 未注入 hitl_confirmed
    with pytest.raises(AppException) as ei:
        asyncio.run(ex._course_create_handler(
            {"title": "HITL实弹测试课", "series_code": "hitl_test_001"}))
    assert str(ei.value.code) == "42201", f"未确认必须 42201 拒：got {ei.value.code}"
    assert "未确认" in ei.value.message
    assert called == [], "P4：未确认时 service 必须零调用（零副作用）"


def test_t4_hitl_confirmed_false_rejected(monkeypatch):
    """hitl_decision=False（reject 路）→ ctx['hitl_confirmed']=False → 同样 42201 拒。"""
    monkeypatch.setattr(
        "app.domains.course_admin.service.create_series",
        lambda d: (_ for _ in ()).throw(AssertionError("service 被调即 FAIL")))
    _set_exec_ctx(1, hitl_confirmed=False)
    with pytest.raises(AppException) as ei:
        asyncio.run(ex._course_create_handler(
            {"title": "X", "series_code": "x_1"}))
    assert str(ei.value.code) == "42201"


# ═══════════════════════════════════════════════════════════
# T1-T3 schema 三态（exact-pin：title/series_code/modules/多余键）——时光.md §B4 T1-T3
# ═══════════════════════════════════════════════════════════
@pytest.mark.parametrize("bad_args,why", [
    ({"series_code": "hitl_test_001"}, "缺 title"),
    ({"title": "", "series_code": "hitl_test_001"}, "title 空串"),
    ({"title": "   ", "series_code": "hitl_test_001"}, "title 全空白"),
    ({"title": 3, "series_code": "hitl_test_001"}, "title 非字符串"),
    ({"title": "X", "series_code": "Hitl-001"}, "series_code 大写/连字符（^[a-z0-9_]+$ 拒）"),
    ({"title": "X", "series_code": "hitl 001"}, "series_code 含空格"),
    ({"title": "X", "series_code": "hitl_test_001", "institution_id": 1}, "伪造 institution_id（服务端权威）"),
    ({"title": "X", "series_code": "hitl_test_001", "created_by": 9}, "伪造 created_by（身份必须走执行上下文）"),
    ({"title": "X", "series_code": "hitl_test_001", "modules": "m1"}, "modules 非列表"),
    ({"title": "X", "series_code": "hitl_test_001", "modules": [1]}, "modules 元素非字符串"),
    ({"title": "X", "series_code": "hitl_test_001", "user_id": 999}, "多余键注入"),
])
def test_t1_t3_schema_exact_pin(bad_args, why):
    _set_exec_ctx(1, hitl_confirmed=True)
    with pytest.raises(ValueError, match="course_create|title|series_code|modules"):
        asyncio.run(ex._course_create_handler(bad_args)), why


def test_t1_title_over_128_rejected():
    _set_exec_ctx(1, hitl_confirmed=True)
    with pytest.raises(ValueError, match="title 过长"):
        asyncio.run(ex._course_create_handler(
            {"title": "长" * 129, "series_code": "x_1"}))


def test_t1_missing_operator_identity():
    """执行上下文无操作者身份 → 拒（即使 hitl_confirmed=True）。"""
    ex._EXEC_CONTEXT.set({"hitl_confirmed": True})
    with pytest.raises(ValueError, match="操作者身份"):
        asyncio.run(ex._course_create_handler(
            {"title": "X", "series_code": "x_1"}))


# ═══════════════════════════════════════════════════════════
# T5 确认后执行（confirm 流 → service 调用 → 回执含创建成功）
# ═══════════════════════════════════════════════════════════
class _FakeSeries:
    def __init__(self):
        self.id = 9999
        self.series_code = "hitl_test_001"
        self.series_name = "HITL实弹测试课"
        self.institution_id = 1
        self.delivery_mode = "online_recorded"
        self.sale_status = "draft"


def test_t5_confirmed_executes_service(monkeypatch):
    """hitl_confirmed=True → service 以执行上下文身份调用，回执 ok=True + created=True。"""
    calls: list = []

    async def fake_create(data):
        calls.append(data)
        return _FakeSeries()

    async def fake_inst(_q, _p=None):
        return {"min_id": 1}

    monkeypatch.setattr("app.domains.course_admin.service.create_series", fake_create)
    monkeypatch.setattr("app.database.fetch_one", lambda q, p=None: _fake_await({"min_id": 1}))
    _set_exec_ctx(1, hitl_confirmed=True)
    out = json.loads(asyncio.run(ex._course_create_handler(
        {"title": "HITL实弹测试课", "series_code": "hitl_test_001", "modules": ["模块一"]})))
    assert out["ok"] is True and out["created"] is True
    assert out["series_id"] == 9999 and out["series_code"] == "hitl_test_001"
    assert out["modules_requested"] == ["模块一"]
    assert "modules" not in out or out.get("modules_note"), "modules 未落库必须如实标注（不谎报）"
    assert len(calls) == 1 and calls[0].series_code == "hitl_test_001"
    assert calls[0].created_by == 1, "service 必须以执行上下文身份调用（created_by=1）"


class _FakeAwait:
    """asyncmy 风格最小 awaitable（fetch_one 替身）。"""

    def __init__(self, value):
        self._v = value

    def __await__(self):
        if False:
            yield
        return self._v


def _fake_await(value):
    return _FakeAwait(value)


def test_t5_business_error_passthrough_40901(monkeypatch):
    """系列编码冲突（40901 SERIES_CODE_CONFLICT）→ 结构化回传 ok=False，严禁伪装成功。"""
    async def fake_create(_data):
        raise AppException(code="40901", message="系列编码 'hitl_test_001' 已存在", http_status=409)

    monkeypatch.setattr("app.domains.course_admin.service.create_series", fake_create)
    monkeypatch.setattr("app.database.fetch_one", lambda q, p=None: _fake_await({"min_id": 1}))
    _set_exec_ctx(1, hitl_confirmed=True)
    out = json.loads(asyncio.run(ex._course_create_handler(
        {"title": "X", "series_code": "hitl_test_001"})))
    assert out["ok"] is False and out["code"] == "40901"
    assert "已存在" in out["message"]


# ═══════════════════════════════════════════════════════════
# T6 五字段帧（pending_confirm 契约冻结面回归：risk_level=high）——时光.md §B4 T6
# ═══════════════════════════════════════════════════════════
def test_t6_hitl_risk_level_high():
    """闸3：`_hitl_risk_level("course_create")` = high（P2 medium→high 语义变更锁定）。"""
    from app.chat.flows.langgraph_agent import _hitl_risk_level

    assert _hitl_risk_level("course_create") == "high"


def test_t6_pending_confirm_five_fields_frame():
    """流层挂起链：enriched 负载含契约五字段，risk_level=high、timeout_s=300。"""
    from app.chat.flows.graph_stream import _enrich_hitl_pending_payload

    raw = {
        "tool_name": "course_create",
        "tool_key": "course_create",
        "role": "admin",
        "args": {"title": "HITL实弹测试课", "series_code": "hitl_test_001"},
        "session_id": "s-t12",
        "status": "awaiting_confirm",
    }
    enriched = _enrich_hitl_pending_payload(raw, thread_id="s-t12")
    for f in ("thread_id", "tool_name", "args", "risk_level", "timeout_s"):
        assert f in enriched, f"缺失契约字段: {f}"
    assert enriched["risk_level"] == "high", "course_create（admin_write）必须 high"
    assert enriched["timeout_s"] == 300
    assert enriched["thread_id"] == "s-t12"
    assert enriched["args"]["series_code"] == "hitl_test_001"


def test_t6_pending_confirm_sse_frame_bytes():
    """SSE 帧字节级：event: pending_confirm + data 行 JSON 可解析、五字段齐。"""
    from app.chat.flows.graph_stream import _enrich_hitl_pending_payload
    from app.chat.sse import sse_line

    payload = _enrich_hitl_pending_payload(
        {"tool_name": "course_create", "args": {"title": "T", "series_code": "t_1"}},
        thread_id="anon-t12",
    )
    raw = sse_line("pending_confirm", payload).decode("utf-8")
    lines = raw.strip().splitlines()
    assert lines[0] == "event: pending_confirm"
    assert lines[1].startswith("data: ")
    data = json.loads(lines[1][len("data: "):])
    assert data["tool_name"] == "course_create" and data["risk_level"] == "high"


# ═══════════════════════════════════════════════════════════
# T7 诱导盲测：student/manager 触发 → permission deny + ACI 信封（不出现确认卡）
# ═══════════════════════════════════════════════════════════
def test_t7_matrix_p2_deny_no_confirm_card():
    """P2 矩阵：admin=allow；manager/student/teacher=deny；guest(未知角色)=deny。"""
    assert pg.can_use_tool("admin", "course_create").allowed is True
    for role in ("manager", "student", "teacher", "guest"):
        d = pg.can_use_tool(role, "course_create")
        assert d.allowed is False, f"P2：{role} × course_create 必须 deny"
        assert d.action_hint and d.action_hint.strip()


def test_t7_student_induction_denied_envelope_zero_hold(monkeypatch):
    """student 发「帮我创建课程」：流式路径 → 权限门 deny（ACI 信封），
    **不触发挂起回调**（未授权者连确认卡都看不到），executor 零调用。"""
    calls: dict = {}

    async def fake_list():
        return [_cc_meta()]

    async def fake_resolve_role(_uid):
        return "student"

    async def fake_call_tool(**kw):
        calls["n"] = calls.get("n", 0) + 1
        return None

    async def hold_cb(_payload):  # pragma: no cover —— 被调即 FAIL
        calls["held"] = True
        return True

    monkeypatch.setattr("app.chat.tool_calling.list_enabled_tool_metas", fake_list)
    monkeypatch.setattr("app.ai.permission_gate.resolve_role", fake_resolve_role)
    monkeypatch.setattr("app.mcp.executor.call_tool", fake_call_tool)

    from app.config import settings as _real_settings

    class _Shim:
        """HITL_ENABLED=True 的最小替身（其余属性透传真实 settings）。"""
        HITL_ENABLED = True

        def __getattr__(self, name):
            return getattr(_real_settings, name)

    monkeypatch.setattr("app.chat.tool_calling.settings", _Shim())
    import app.chat.tool_calling as tc
    # 诱导语句带全参数（标题+系列码）：启发式产出计划 → student 权限门 deny。
    # 裸「帮我创建课程」（无参数）由 _parse_heuristic 零计划兜住（另测）。
    summaries, ctx, _ = asyncio.run(tc.run_chat_tool_calls(
        query="帮我创建课程，标题'测试课'，系列码 t7_deny_001",
        operator_user_id=7,
        on_write_class_pending=hold_cb,
    ))
    assert calls.get("n", 0) == 0, "deny 后 executor 必须零调用"
    assert "held" not in calls, "T7：未授权者不得触发挂起回调（无确认卡）"
    assert len(summaries) == 1 and summaries[0].status == "error"
    env = json.loads(summaries[0].result_summary)
    assert env["code"] == pg.DENIED_CODE and env["status"] == "denied"
    assert env["message"] and env["action_hint"], "ACI 三字段信封"


def _cc_meta():
    from app.chat.tool_calling import ToolMeta

    return ToolMeta(tool_id=0, server_id=0, tool_name="course_create",
                    description="创建课程系列", input_schema_json=None, category="builtin",
                    keywords=["course_create", "创建", "建课", "新课"])


# ═══════════════════════════════════════════════════════════
# T8 审计：confirm 执行后 mcp_tool_call_log 行含 operator/tool/args
# ═══════════════════════════════════════════════════════════
def test_t8_audit_log_builtin_attempt(monkeypatch):
    """内置执行路径（_execute_builtin_attempt）：成功也落审计行（user_id/tool/args 可查）。"""
    logged: list = []

    async def fake_create(_data):
        return _FakeSeries()

    async def fake_log(**kw):
        logged.append(kw)

    monkeypatch.setattr("app.domains.course_admin.service.create_series", fake_create)
    monkeypatch.setattr("app.database.fetch_one", lambda q, p=None: _fake_await({"min_id": 1}))
    monkeypatch.setattr(ex, "_write_call_log", fake_log)
    _set_exec_ctx(1, hitl_confirmed=True)
    resp = asyncio.run(ex._execute_builtin_attempt(
        tool_name="course_create",
        args={"title": "HITL实弹测试课", "series_code": "hitl_test_001"},
        call_id="t12-audit-1", operator_user_id=1,
    ))
    assert str(getattr(resp.status, "value", resp.status)).lower() == "success"
    assert logged, "内置工具执行必须落审计行"
    row = logged[0]
    assert row["tool_name"] == "course_create" and row["user_id"] == 1
    assert row["args"] == {"title": "HITL实弹测试课", "series_code": "hitl_test_001"}


def test_t8_audit_log_graph_path(monkeypatch):
    """graph/子代理路径（call_tool_with_retry → _default_attempt_executor 内置分支）也必须落审计。"""
    logged: list = []

    async def fake_create(_data):
        return _FakeSeries()

    async def fake_log(**kw):
        logged.append(kw)

    monkeypatch.setattr("app.domains.course_admin.service.create_series", fake_create)
    monkeypatch.setattr("app.database.fetch_one", lambda q, p=None: _fake_await({"min_id": 1}))
    monkeypatch.setattr(ex, "_write_call_log", fake_log)
    _set_exec_ctx(1, hitl_confirmed=True)
    outcome = asyncio.run(ex._default_attempt_executor(
        "course_create", {"title": "T", "series_code": "t_1"}, call_id="t12-graph-audit",
        attempt=1, operator_user_id=1, tenant_id="_test", trace_id="t-t12"))
    assert outcome.ok is True
    assert logged and logged[0]["tool_name"] == "course_create" and logged[0]["user_id"] == 1


# ═══════════════════════════════════════════════════════════
# 注册期强属性 + 挂起区迁移 + 决策拒缓存（不变量锁定）
# ═══════════════════════════════════════════════════════════
def test_registration_strong_property_and_migration():
    """write_class=True 强属性 + permission_gate 迁移（挂起 7、注册面 10）+ audit 对账全空。"""
    assert "course_create" in ex._BUILTIN_TOOL_HANDLERS
    assert "course_create" in ex._BUILTIN_WRITE_CLASS_NAMES, "注册期强属性必须激活（executor 收口）"
    assert pg.classify_tool("course_create") == "admin_write"
    assert pg.is_write_class("course_create") is True, "HITL 写类面必须弹卡（admin_write ∈ WRITE_CLASSES）"
    assert "course_create" not in pg.CONTRACT_PENDING_TOOLS, "已迁出挂起区"
    assert "course_create" in pg.REGISTERED_BUILTIN_TOOLS, "真实注册面已登记"
    assert pg.audit_registry() == {
        "mapped_but_unregistered": [], "registered_but_unmapped": [], "pending_now_registered": [],
    }
    assert ex._classify_hitl_action("course_create") == "write_file"
    assert ex._is_cached_call("course_create", {"any": 1}) is False, "写类严禁走缓存"


def test_arg_schema_declaration_matches_exact_pin():
    """COURSE_CREATE_ARG_SCHEMA 声明面与 handler exact-pin 语义一致（对账锚）。

    TA6：series_code 由「必填」放宽为「可选」——不传时服务端按 title 自动派生合法编码，
    显式传入仍走 exact-pin 校验（保留用户值）。故 required 仅 title。
    """
    sch = ex.COURSE_CREATE_ARG_SCHEMA
    assert sch["required"] == ["title"]
    assert sch["additionalProperties"] is False
    assert sch["properties"]["series_code"]["pattern"] == "^[a-z0-9_]+$"
    assert sch["properties"]["title"]["minLength"] == 1


def test_t1_series_code_optional_autoderive(monkeypatch):
    """TA6：series_code 改可选——不传时服务端按 title 自动派生合法编码（用户零 ID 输入）。"""
    captured: dict = {}

    class _F:
        id = 9001
        series_code = "auto_x"
        series_name = "X"
        institution_id = 1
        delivery_mode = "online_recorded"
        sale_status = "draft"

    async def fake_create(data):
        captured["data"] = data
        _F.series_code = data.series_code
        return _F()

    monkeypatch.setattr("app.domains.course_admin.service.create_series", fake_create)
    monkeypatch.setattr("app.database.fetch_one", lambda q, p=None: _fake_await({"min_id": 1}))
    _set_exec_ctx(1, hitl_confirmed=True)
    out = json.loads(asyncio.run(ex._course_create_handler({"title": "X"})))
    assert out["ok"] is True and out["created"] is True
    assert out["series_code_source"] == "auto_derived", "未传 series_code 必须服务端自动派生"
    assert re.fullmatch(r"[a-z0-9_]+", out["series_code"]) and len(out["series_code"]) <= 64
    assert out["series_code"] == captured["data"].series_code


# ═══════════════════════════════════════════════════════════
# 启发式规划（TOOL_DECISION_MODE=rule 默认态）：标题+系列码同现才触发，闲聊不误触
# ═══════════════════════════════════════════════════════════
def test_heuristic_plans_course_create_on_title_and_code():
    from app.chat.tool_calling import _parse_heuristic

    for q in ("帮我创建一门新课，标题'HITL实弹测试课'，系列码 hitl_test_001",
              "创建课程，标题为\"趣味算法\"，编码 fun_algo_101",
              "建课：标题'测试A' 系列码 test_a_01"):
        plans = _parse_heuristic(q, [_cc_meta()])
        assert len(plans) == 1 and plans[0].tool.tool_name == "course_create", q
        assert plans[0].args.get("title") and plans[0].args.get("series_code"), q


def test_heuristic_no_plan_without_params():
    from app.chat.tool_calling import _parse_heuristic

    for q in ("怎么创建课程？", "我想建课", "新课什么时候上线", "创建课程需要什么权限"):
        assert _parse_heuristic(q, [_cc_meta()]) == [], q


def test_heuristic_series_code_extraction_avoids_chinese_pinyin_trap():
    """系列码提取必须命中 [a-z][a-z0-9_]+ 记号串，不误取中文拼音化片段（lesson 9：禁瞎 match）。"""
    from app.chat.tool_calling import _parse_heuristic

    plans = _parse_heuristic("帮我创建一门新课，标题'数学课'，系列码 math_101", [_cc_meta()])
    assert len(plans) == 1 and plans[0].args["series_code"] == "math_101"
