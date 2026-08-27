# -*- coding: utf-8 -*-
"""task-T1 闭环契约测试：换参 → 换工具 → 熔断 → 人工指南（AC1~AC4）。

设计：闭环编排逻辑（call_tool_with_retry）与执行器（IO）解耦——测试注入假执行器与
内存拒绝计数，零 DB / 零 LLM / 零 Redis 依赖，纯逻辑可随时跑（对齐测试窗口纪律）。
AC5 回归另跑 task33 既有契约（见 test_task33_mcp_desc_review.py）。
"""
from __future__ import annotations

import pytest

from app.mcp import executor as executor_mod
from app.mcp.executor import call_tool_with_retry
from app.mcp.retry_loop import (
    ToolRetryStateMachine, MemRejectStore, build_manual_guide,
    AttemptOutcome, ACTION_NORMAL, ACTION_REWRITE, ACTION_SWITCH,
)
from app.mcp.schemas import ToolCallStatusEnum


# ============================================================
# 公共假件
# ============================================================
@pytest.fixture
def patch_registry(monkeypatch):
    """让 call_tool_with_retry 跳过真实 DB 解析（registry.fetch_one）。"""
    async def _fake_get_tool_by_ref(tool_id, server_id, tool_name):
        return {"server_id": 1, "tool_name": tool_name or "web_search"}
    async def _fake_fetch_one(sql, params=None):
        return {"id": 1, "server_code": "fake", "enabled": 1, "yn": 1}
    monkeypatch.setattr(executor_mod.registry, "get_tool_by_ref", _fake_get_tool_by_ref)
    monkeypatch.setattr(executor_mod, "fetch_one", _fake_fetch_one)


def _mk_outcome(*, ok, tool_name, status="SUCCESS", is_rejection=True, error="boom", latency=1):
    return AttemptOutcome(
        ok=ok, status=status, tool_name=tool_name, args={},
        latency_ms=latency, error_message=(None if ok else error),
        is_rejection=(not ok and is_rejection), result={"ok": ok},
    )


# ============================================================
# 纯状态机（无 IO）
# ============================================================
def test_state_machine_normal_rewrite_switch_guide():
    sm = ToolRetryStateMachine("web_search", {"q": 1}, fallback_map={"web_search": ["calculator"]})
    s1 = sm.plan_first()
    assert s1.attempt == 1 and s1.action == ACTION_NORMAL and s1.tool_name == "web_search"
    s2 = sm.plan_next(1, _mk_outcome(ok=False, tool_name="web_search"))
    assert s2.attempt == 2 and s2.action == ACTION_REWRITE and s2.tool_name == "web_search"
    s3 = sm.plan_next(2, _mk_outcome(ok=False, tool_name="web_search"))
    assert s3.attempt == 3 and s3.action == ACTION_SWITCH and s3.tool_name == "calculator"
    s4 = sm.plan_next(3, _mk_outcome(ok=False, tool_name="calculator"))
    assert s4 is None  # 进入人工指南


def test_state_machine_no_fallback_goes_to_guide():
    sm = ToolRetryStateMachine("code_runner", {"x": 1}, fallback_map={})
    s1 = sm.plan_first()
    assert s1.action == ACTION_NORMAL
    s2 = sm.plan_next(1, _mk_outcome(ok=False, tool_name="code_runner"))
    assert s2.action == ACTION_REWRITE
    # 无备用工具 → 第 3 步直接指南
    s3 = sm.plan_next(2, _mk_outcome(ok=False, tool_name="code_runner"))
    assert s3 is None


def test_state_machine_max_attempts_bound():
    sm = ToolRetryStateMachine("t", {}, fallback_map={"t": ["a", "b"]}, max_attempts=3)
    assert sm.plan_first().attempt == 1
    assert sm.plan_next(1, _mk_outcome(ok=False, tool_name="t")).attempt == 2
    # max_attempts=3 → 第 3 步即指南（无 switch）
    assert sm.plan_next(2, _mk_outcome(ok=False, tool_name="t")) is None


def test_build_manual_guide_structure():
    trail = [
        {"attempt": 1, "action": "execute_normal", "tool_name": "web_search",
         "outcome": "ERROR", "error_message": "e1", "latency_ms": 1},
        {"attempt": 2, "action": "rewrite_args", "tool_name": "web_search",
         "outcome": "ERROR", "error_message": "e2", "latency_ms": 1},
        {"attempt": 3, "action": "switch_tool", "tool_name": "calculator",
         "outcome": "ERROR", "error_message": "e3", "latency_ms": 1},
    ]
    g = build_manual_guide(original_tool_name="web_search", attempts_trail=trail,
                           original_args={"q": 1}, last_error="e3")
    assert set(g) >= {"problem_description", "attempted_tools", "user_manual_steps", "contact_admin"}
    assert g["attempted_tools"][0]["tool_name"] == "web_search"
    assert g["attempted_tools"][2]["tool_name"] == "calculator"
    assert len(g["user_manual_steps"]) >= 1


# ============================================================
# AC1：闭环升级路径（1→2→3→4，第 3 步换备用工具成功）
# ============================================================
@pytest.mark.asyncio
async def test_ac1_switch_tool_succeeds(patch_registry):
    calls = []

    async def fake_exec(tool_name, args, *, call_id, attempt, operator_user_id, tenant_id, trace_id):
        calls.append({"attempt": attempt, "tool": tool_name, "args": dict(args)})
        if tool_name == "calculator":
            return _mk_outcome(ok=True, tool_name="calculator", status="SUCCESS", is_rejection=False)
        return _mk_outcome(ok=False, tool_name=tool_name, status="ERROR", is_rejection=True)

    resp = await call_tool_with_retry(
        operator_user_id=1, tool_name="web_search", args={"q": 1},
        session_id="", _attempt_executor=fake_exec, _reject_store=MemRejectStore(),
    )
    assert resp.status == ToolCallStatusEnum.SUCCESS
    assert resp.attempt == 3
    assert [c["tool"] for c in calls] == ["web_search", "web_search", "calculator"]
    assert [c["attempt"] for c in calls] == [1, 2, 3]
    assert resp.actions[0]["action"] == ACTION_NORMAL
    assert resp.actions[1]["action"] == ACTION_REWRITE
    assert resp.actions[2]["action"] == ACTION_SWITCH
    assert resp.manual_guide is None


@pytest.mark.asyncio
async def test_ac1_rewrite_uses_llm(patch_registry):
    calls = []

    async def fake_exec(tool_name, args, *, call_id, attempt, operator_user_id, tenant_id, trace_id):
        calls.append({"attempt": attempt, "args": dict(args)})
        return _mk_outcome(ok=False, tool_name=tool_name, status="ERROR", is_rejection=True)

    async def llm_rewrite(original_args, last_error, tool_name):
        return {**original_args, "rewritten": True}

    resp = await call_tool_with_retry(
        operator_user_id=1, tool_name="web_search", args={"q": 1},
        session_id="", llm_rewrite_fn=llm_rewrite,
        _attempt_executor=fake_exec, _reject_store=MemRejectStore(),
    )
    # 走到指南（全失败），但第 2 步 args 应被 LLM 改写
    assert resp.status == ToolCallStatusEnum.MANUAL_GUIDE
    assert calls[1]["args"].get("rewritten") is True
    assert calls[0]["args"].get("rewritten") is None


# ============================================================
# AC2：所有工具失败 → 结构化人工指南
# ============================================================
@pytest.mark.asyncio
async def test_ac2_manual_guide_on_total_failure(patch_registry):
    async def always_fail(tool_name, args, *, call_id, attempt, operator_user_id, tenant_id, trace_id):
        return _mk_outcome(ok=False, tool_name=tool_name, status="ERROR", is_rejection=True)

    resp = await call_tool_with_retry(
        operator_user_id=1, tool_name="web_search", args={"q": 1},
        session_id="", _attempt_executor=always_fail, _reject_store=MemRejectStore(),
    )
    assert resp.status == ToolCallStatusEnum.MANUAL_GUIDE
    assert resp.rejection_limited is False
    assert isinstance(resp.manual_guide, dict)
    assert set(resp.manual_guide) >= {"problem_description", "attempted_tools",
                                      "user_manual_steps", "contact_admin"}
    # 闭环执行了 3 步（正常/换参/换工具）后才转指南
    assert len(resp.actions) == 3
    assert "人工操作指南" in (resp.content_text or "")


# ============================================================
# AC3：拒绝计数熔断（同会话连续被拒 → 中断）
# ============================================================
@pytest.mark.asyncio
async def test_ac3_rejection_interrupts_fourth_attempt(patch_registry):
    store = MemRejectStore()
    call_count = {"n": 0}

    async def always_fail(tool_name, args, *, call_id, attempt, operator_user_id, tenant_id, trace_id):
        call_count["n"] += 1
        return _mk_outcome(ok=False, tool_name=tool_name, status="ERROR", is_rejection=True)

    # 第一次：3 步全拒 → 指南，计数累加到 3
    r1 = await call_tool_with_retry(
        operator_user_id=1, tool_name="web_search", args={"q": 1},
        session_id="sess-1", _attempt_executor=always_fail, _reject_store=store,
    )
    assert r1.status == ToolCallStatusEnum.MANUAL_GUIDE
    assert await store.get("sess-1") == 3

    # 第二次（同会话）：第 4 次尝试前计数已=3 → 直接 REJECTION_LIMIT 中断，不再执行工具
    call_count["n"] = 0
    r2 = await call_tool_with_retry(
        operator_user_id=1, tool_name="web_search", args={"q": 1},
        session_id="sess-1", _attempt_executor=always_fail, _reject_store=store,
    )
    assert r2.status == ToolCallStatusEnum.REJECTION_LIMIT
    assert r2.rejection_limited is True
    assert call_count["n"] == 0  # 未执行任何工具调用
    assert isinstance(r2.manual_guide, dict)


@pytest.mark.asyncio
async def test_ac3_success_resets_counter(patch_registry):
    store = MemRejectStore()

    async def succeed_first(tool_name, args, *, call_id, attempt, operator_user_id, tenant_id, trace_id):
        return _mk_outcome(ok=True, tool_name=tool_name, status="SUCCESS", is_rejection=False)

    await call_tool_with_retry(
        operator_user_id=1, tool_name="web_search", args={"q": 1},
        session_id="sess-2", _attempt_executor=succeed_first, _reject_store=store,
    )
    assert await store.get("sess-2") == 0  # 成功 → 重置


@pytest.mark.asyncio
async def test_ac3_no_session_id_still_bounded(patch_registry):
    call_count = {"n": 0}

    async def always_fail(tool_name, args, *, call_id, attempt, operator_user_id, tenant_id, trace_id):
        call_count["n"] += 1
        return _mk_outcome(ok=False, tool_name=tool_name, status="ERROR", is_rejection=True)

    resp = await call_tool_with_retry(
        operator_user_id=1, tool_name="web_search", args={"q": 1},
        session_id="", _attempt_executor=always_fail, _reject_store=MemRejectStore(),
    )
    assert resp.status == ToolCallStatusEnum.MANUAL_GUIDE
    assert call_count["n"] == 3  # 仅闭环内 3 步，不无限重试


# ============================================================
# AC4：事件埋点 payload 结构 + trace_id
# ============================================================
@pytest.mark.asyncio
async def test_ac4_event_payload_and_trace_id(patch_registry, monkeypatch):
    captured = []

    def fake_emit(payload, *, trace_id, user_id):
        captured.append({"payload": payload, "trace_id": trace_id})

    monkeypatch.setattr(executor_mod, "_emit_retry_event", fake_emit)

    async def always_fail(tool_name, args, *, call_id, attempt, operator_user_id, tenant_id, trace_id):
        return _mk_outcome(ok=False, tool_name=tool_name, status="ERROR", is_rejection=True)

    await call_tool_with_retry(
        operator_user_id=7, tool_name="web_search", args={"q": 1}, trace_id="trace-xyz",
        session_id="", _attempt_executor=always_fail, _reject_store=MemRejectStore(),
    )
    assert len(captured) == 3
    for c in captured:
        p = c["payload"]
        assert {"attempt", "action", "tool_name", "args", "outcome", "latency_ms"} <= set(p)
        assert c["trace_id"] == "trace-xyz"
    assert captured[0]["payload"]["attempt"] == 1
    assert captured[2]["payload"]["action"] == ACTION_SWITCH
