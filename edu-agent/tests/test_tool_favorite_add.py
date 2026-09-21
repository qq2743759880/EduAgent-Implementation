# -*- coding: utf-8 -*-
"""W-NEXT-WRITE1：favorite_add 写类工具（user_write 首例）单测。

CR-WRITETOOLS-001 第一批（用户 P1-P6 裁定 2026-09-20，docs/时光.md §A3 T1-T6）：
- P1 类别 user_write：student/teacher/admin=allow、manager=deny、guest(未知角色)=deny
- P3 HITL 单一事实源：user_write → _hitl_risk_level=None（免弹卡）；挂起工具语义零回归
- P4 executor 双保险：注册期强属性 write_class=True → executor 收口角色校验，
  但 permission_gate.is_write_class=False（HITL 面）——两属性正交
- 身份安全：user_id 以 _EXEC_CONTEXT 为权威，args 伪造结构性不可达
"""
import asyncio
import inspect
import json
from datetime import datetime

import pytest

from app.ai import permission_gate as pg
from app.mcp import executor as ex
from app.common.exceptions import AppException
from app.domains.market.schemas import FavoriteItem


def _set_exec_ctx(uid: int) -> None:
    """注入执行上下文（模拟 call_tool 入口对 _EXEC_CONTEXT 的服务端设置）。"""
    ex._EXEC_CONTEXT.set({"operator_user_id": uid, "tenant_id": "_test", "trace_id": "t-w1"})


def _fake_item(fid: int = 11, sid: int = 3) -> FavoriteItem:
    return FavoriteItem(
        favorite_id=fid, user_id=42, target_type="series", series_id=sid,
        series_title="测试系列", cover_url=None, created_at=datetime(2026, 9, 20, 12, 0, 0),
    )


# ═══════════════════════════════════════════════════════════
# T1 参数精确校验（exact-pin：仅 series_id:int，多余键/类型错一律拒）
# ═══════════════════════════════════════════════════════════
@pytest.mark.parametrize("bad_args,why", [
    ({}, "缺 series_id"),
    ({"series_id": None}, "series_id 为 None"),
    ({"series_id": "3"}, "series_id 字符串"),
    ({"series_id": 3.5}, "series_id 浮点"),
    ({"series_id": True}, "series_id 布尔（int 子类陷阱）"),
    ({"series_id": 3, "course_id": 3}, "别名字段 course_id 注入"),
    ({"series_id": 3, "user_id": 999}, "伪造 user_id（身份必须走执行上下文）"),
])
def test_t1_schema_exact_pin(bad_args, why):
    _set_exec_ctx(42)
    with pytest.raises(ValueError, match="series_id|favorite_add"):
        asyncio.run(ex._favorite_add_handler(bad_args))


def test_t1_missing_operator_identity():
    """执行上下文无操作者身份 → 拒（user_id 服务端注入缺失时不静默兜底）。"""
    ex._EXEC_CONTEXT.set({})
    with pytest.raises(ValueError, match="操作者身份"):
        asyncio.run(ex._favorite_add_handler({"series_id": 3}))


# ═══════════════════════════════════════════════════════════
# T2 正常收藏（service 被调、ok=True、参数以上下文身份传入）
# ═══════════════════════════════════════════════════════════
def test_t2_normal(monkeypatch):
    calls: list[dict] = []

    async def fake_add(user_id, series_id, favorite_source):
        calls.append({"user_id": user_id, "series_id": series_id, "source": favorite_source})
        return _fake_item()

    monkeypatch.setattr("app.domains.market.service.add_favorite", fake_add)
    _set_exec_ctx(42)
    out = json.loads(asyncio.run(ex._favorite_add_handler({"series_id": 3})))
    assert out["ok"] is True and out["favorite_id"] == 11 and out["series_id"] == 3
    assert calls == [{"user_id": 42, "series_id": 3, "source": "ai_chat"}], (
        "service 必须以执行上下文身份调用（user_id=42），且 series_id 原样传递"
    )


# ═══════════════════════════════════════════════════════════
# T3 幂等语义（同参两次 → 均 ok，不报错；幂等本体由 service 保证 F610）
# ═══════════════════════════════════════════════════════════
def test_t3_idempotent(monkeypatch):
    async def fake_add(user_id, series_id, favorite_source):
        return _fake_item()  # 重复收藏返回原记录

    monkeypatch.setattr("app.domains.market.service.add_favorite", fake_add)
    _set_exec_ctx(42)
    r1 = json.loads(asyncio.run(ex._favorite_add_handler({"series_id": 3})))
    r2 = json.loads(asyncio.run(ex._favorite_add_handler({"series_id": 3})))
    assert r1["ok"] is True and r2["ok"] is True
    assert r1["favorite_id"] == r2["favorite_id"] == 11


# ═══════════════════════════════════════════════════════════
# T4 业务错结构化回传（系列不存在 → ok=False + 后端错误码原文）
# ═══════════════════════════════════════════════════════════
def test_t4_business_error_passthrough(monkeypatch):
    async def fake_add(user_id, series_id, favorite_source):
        raise AppException(code=40400, message="课程系列不存在或已下架", http_status=404)

    monkeypatch.setattr("app.domains.market.service.add_favorite", fake_add)
    _set_exec_ctx(42)
    out = json.loads(asyncio.run(ex._favorite_add_handler({"series_id": 99999})))
    assert out["ok"] is False and out["code"] == 40400
    assert out["message"] == "课程系列不存在或已下架"


# ═══════════════════════════════════════════════════════════
# T5 权限矩阵（P1：student/teacher/admin=allow、manager/guest=deny）+ ACI 信封
# ═══════════════════════════════════════════════════════════
def test_t5_matrix_p1():
    assert pg.can_use_tool("student", "favorite_add").allowed is True
    assert pg.can_use_tool("teacher", "favorite_add").allowed is True
    assert pg.can_use_tool("admin", "favorite_add").allowed is True
    d_mgr = pg.can_use_tool("manager", "favorite_add")
    assert d_mgr.allowed is False and d_mgr.action_hint, "P1 裁定：manager=deny"
    d_guest = pg.can_use_tool("guest", "favorite_add")
    assert d_guest.allowed is False, "未知角色 fail-closed deny"


def test_t5_denied_envelope():
    env = pg.build_denied_envelope("manager", "favorite_add")
    assert env["code"] == pg.DENIED_CODE and env["status"] == "denied"
    assert env["message"] and env["action_hint"]


# ═══════════════════════════════════════════════════════════
# T6 审计（内置执行结果落 mcp_tool_call_log：user_id/tool/args 可查）
# ═══════════════════════════════════════════════════════════
def test_t6_audit_log(monkeypatch):
    logged: list[dict] = []

    async def fake_add(user_id, series_id, favorite_source):
        return _fake_item()

    async def fake_log(**kw):
        logged.append(kw)

    monkeypatch.setattr("app.domains.market.service.add_favorite", fake_add)
    monkeypatch.setattr(ex, "_write_call_log", fake_log)
    resp = asyncio.run(ex._execute_builtin_attempt(
        tool_name="favorite_add", args={"series_id": 3}, call_id="w1-audit-1",
        operator_user_id=42,
    ))
    assert str(getattr(resp.status, "value", resp.status)).lower() == "success"
    assert logged, "内置工具执行必须落审计行（W-NEXT-MCP-001 P0-②）"
    row = logged[0]
    assert row["tool_name"] == "favorite_add" and row["user_id"] == 42
    assert row["args"] == {"series_id": 3}


def test_t6_audit_log_graph_path(monkeypatch):
    """graph/子代理路径（call_tool_with_retry → _default_attempt_executor 内置分支）
    也必须落审计——W-NEXT-WRITE1 实测缺口（真实写库但 0 审计行）修复的回归锁。"""
    logged: list[dict] = []

    async def fake_add(user_id, series_id, favorite_source):
        return _fake_item()

    async def fake_log(**kw):
        logged.append(kw)

    monkeypatch.setattr("app.domains.market.service.add_favorite", fake_add)
    monkeypatch.setattr(ex, "_write_call_log", fake_log)
    _set_exec_ctx(42)
    outcome = asyncio.run(ex._default_attempt_executor(
        "favorite_add", {"series_id": 3}, call_id="w1-graph-audit", attempt=1,
        operator_user_id=42, tenant_id="_test", trace_id="t-w1"))
    assert outcome.ok is True
    assert logged, "graph 路径内置分支必须落审计（T6 不变量）"
    assert logged[0]["tool_name"] == "favorite_add" and logged[0]["user_id"] == 42


# ═══════════════════════════════════════════════════════════
# P3/P4 结构断言（单一事实源 + 双保险正交性）
# ═══════════════════════════════════════════════════════════
def test_p3_hitl_single_source():
    from app.chat.flows.langgraph_agent import _hitl_risk_level

    assert _hitl_risk_level("favorite_add") is None, "user_write 免弹卡（P1/P3）"
    # 挂起/实物工具既有语义零回归（契约面不变）
    # AUTO20 T12（CR-WRITETOOLS-001 第二批 P2）：course_create 迁入 TOOL_CLASS_MAP=admin_write
    # → medium（挂起 course_write 语义）变更为 **high**（admin_write L3），由本断言锁定新语义。
    assert _hitl_risk_level("course_create") == "high"
    assert _hitl_risk_level("course_update") == "medium"
    assert _hitl_risk_level("points_change") == "high"
    assert _hitl_risk_level("order_create") == "high"
    assert _hitl_risk_level("knowledge_import") == "high"
    assert _hitl_risk_level("calculator") is None


def test_p3_no_dual_source_left():
    """_hitl_risk_level 不得再 import/消费 ADMIN_WRITE_TOOLS、COURSE_WRITE_TOOLS 别名
    （注释/文档里提及不算消费；判据=函数源码零别名 import + 必须走 classify_tool_intent）。"""
    from app.chat.flows import langgraph_agent as la

    fs = inspect.getsource(la._hitl_risk_level)
    assert "from app.ai.permission_gate import ADMIN_WRITE_TOOLS" not in fs
    assert "from app.ai.permission_gate import COURSE_WRITE_TOOLS" not in fs
    assert "classify_tool_intent" in fs, "单一事实源=permission_gate.classify_tool_intent"


# ═══════════════════════════════════════════════════════════
# 启发式规划（TOOL_DECISION_MODE=rule 默认态）：明确 series_id 才触发，闲聊不误触
# ═══════════════════════════════════════════════════════════
def _fav_meta():
    from app.chat.tool_calling import ToolMeta

    return ToolMeta(tool_id=0, server_id=0, tool_name="favorite_add",
                    description="收藏课程", input_schema_json=None, category="builtin")


def test_heuristic_plans_favorite_on_explicit_series_id():
    from app.chat.tool_calling import _parse_heuristic

    for q in ("帮我收藏课程 series_id 为 3 的课", "收藏系列 5", "收藏 id=7 的课程"):
        plans = _parse_heuristic(q, [_fav_meta()])
        assert len(plans) == 1 and plans[0].tool.tool_name == "favorite_add", q
        assert isinstance(plans[0].args.get("series_id"), int)


def test_heuristic_no_plan_without_series_id():
    from app.chat.tool_calling import _parse_heuristic

    for q in ("我想收藏点东西", "怎么收藏课程？", "收藏功能好用吗"):
        assert _parse_heuristic(q, [_fav_meta()]) == [], q


def test_p4_orthogonal_attributes():
    """executor 强属性（角色收口）与 HITL 写类（弹卡）正交：
    favorite_add 应只进前者、不进后者。"""
    assert "favorite_add" in ex._BUILTIN_WRITE_CLASS_NAMES, "executor 收口必须激活（注册期强属性）"
    assert pg.is_write_class("favorite_add") is False, "HITL 写类面必须免卡（user_write 不入 WRITE_CLASSES）"
    assert pg.classify_tool("favorite_add") == "user_write"
    assert "favorite_add" not in pg.CONTRACT_PENDING_TOOLS, "已迁出挂起区"
    assert "favorite_add" in pg.REGISTERED_BUILTIN_TOOLS, "真实注册面已登记"
