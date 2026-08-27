# -*- coding: utf-8 -*-
"""task-S1 全流程 HITL 护栏契约测试（AC1~AC5）。

设计：护栏核心（app.ai.hitl_gate）纯逻辑、零 IO，测试注入 MemHitlStore + 假 reviewer +
假 executor，零 DB / 零 LLM / 零 Redis 依赖，纯逻辑可随时跑（对齐测试窗口纪律）。
执行器 seam（app.mcp.executor._run_hitl_seam）同样注入内存 store，验证写工具被拦截、
非写工具放行，默认 HITL_ENABLED=False 时不改变既有路径（AC5）。

AC5 回归另跑 task28 退款 HITL 契约（test_contract_task28.py）+ task33（test_task33_*.py）+
task-T1（test_contract_task_t1.py），见 runner。
"""
from __future__ import annotations

import pytest

from app.ai.hitl_gate import (
    run_hitl_gate, force_approve, sweep_expired_pending, MemHitlStore,
    HitlAction, HitlActionType, HitlConfig, HitlStatus,
)
from app.mcp import executor as executor_mod
from app.mcp.executor import _run_hitl_seam, _classify_hitl_action, _execute_single_attempt
from app.mcp.schemas import ToolCallStatusEnum, MCPToolTestResp


# ============================================================
# 假 reviewer / executor
# ============================================================
async def _reviewer_reject(action_type, propose_text, params):
    return {"verdict": "reject", "reason": "risky", "confidence": 0.9}


async def _reviewer_approve(action_type, propose_text, params):
    return {"verdict": "approve", "reason": "ok", "confidence": 0.9}


# ============================================================
# AC1 闭环：未批准零执行；批准后执行
# ============================================================
@pytest.mark.asyncio
async def test_s1_ac1_pending_zero_execution():
    calls = {"n": 0}

    async def _exec(action):
        calls["n"] += 1
        return {"ok": True}

    store = MemHitlStore()
    r = await run_hitl_gate(
        HitlAction(HitlActionType.WRITE_FILE, "file.txt", {"x": 1}),
        store=store, executor_fn=_exec, human_decision=None,
    )
    assert r.status == "pending"
    assert calls["n"] == 0, "未批准前执行器绝不可被调用（AC1）"


@pytest.mark.asyncio
async def test_s1_ac1_approve_then_execute():
    calls = {"n": 0}

    async def _exec(action):
        calls["n"] += 1
        return {"ok": True}

    store = MemHitlStore()
    r = await run_hitl_gate(
        HitlAction(HitlActionType.WRITE_FILE, "file.txt", {"x": 1}),
        store=store, executor_fn=_exec, human_decision=True, trace_id="t1",
    )
    assert r.status == "executed"
    assert calls["n"] == 1


# ============================================================
# AC2 四步审计：explain_text / propose_text / operator / trace_id 用户可见
# ============================================================
@pytest.mark.asyncio
async def test_s1_ac2_four_audit_fields():
    store = MemHitlStore()
    r = await run_hitl_gate(
        HitlAction(HitlActionType.REFUND, "order/1", {"amt": 10}, operator="op-7", trace_id="tr-9"),
        store=store, human_decision=None,
    )
    rec = r.record
    assert rec["explain_text"], "缺少 explain_text"
    assert rec["propose_text"], "缺少 propose_text"
    assert rec["operator"] == "op-7", "operator 未落库"
    assert rec["trace_id"] == "tr-9", "trace_id 未落库"


# ============================================================
# AC3 超时拒绝：background sweep + resume 超时
# ============================================================
@pytest.mark.asyncio
async def test_s1_ac3_sweep_expired():
    cfg = HitlConfig(pending_ttl_s=600)
    store = MemHitlStore()
    await run_hitl_gate(
        HitlAction(HitlActionType.REFUND, "order/1", {"amt": 10}),
        store=store, config=cfg, human_decision=None, now=lambda: 0.0,
    )
    res = await sweep_expired_pending(store=store, now=lambda: 99999.0, ttl_s=600)
    assert res["rejected"] == 1


@pytest.mark.asyncio
async def test_s1_ac3_resume_after_ttl_rejected():
    cfg = HitlConfig(pending_ttl_s=600)
    store = MemHitlStore()
    rp = await run_hitl_gate(
        HitlAction(HitlActionType.REFUND, "order/2", {"amt": 5}),
        store=store, config=cfg, human_decision=None, now=lambda: 1000.0,
    )
    # resume 同一 action_id，now 远超 TTL
    r = await run_hitl_gate(
        HitlAction(HitlActionType.REFUND, "order/2", {"amt": 5}, action_id=rp.action_id),
        store=store, config=cfg, human_decision=True, now=lambda: 1000.0 + 9999,
    )
    assert r.status == "rejected", "resume 超时应自动拒绝（AC3）"


# ============================================================
# AC4 AI 审查 AI：reject→escalated；3 连拒→第 4 次熔断；approve→人工 gate
# ============================================================
@pytest.mark.asyncio
async def test_s1_ac4_ai_reject_escalated():
    cfg = HitlConfig(ai_review=True, reject_breaker=3)
    store = MemHitlStore()
    r = await run_hitl_gate(
        HitlAction(HitlActionType.EXEC_COMMAND, "rm -rf", {}),
        store=store, reviewer_fn=_reviewer_reject, config=cfg, human_decision=None,
    )
    assert r.status == "escalated" and r.needs_admin, "AI 拒绝应升级人工（需管理员）"
    assert await store.get_reject_count("exec_command") == 1
    # 升级记录同样含 AC2 四字段
    assert r.record["explain_text"] and r.record["propose_text"] and "operator" in r.record


@pytest.mark.asyncio
async def test_s1_ac4_breaker_after_three_rejects():
    cfg = HitlConfig(ai_review=True, reject_breaker=3)
    store = MemHitlStore()
    calls = {"n": 0}

    async def _reviewer_count(action_type, propose_text, params):
        calls["n"] += 1
        return {"verdict": "reject", "reason": "r", "confidence": 0.8}

    for _ in range(3):
        rr = await run_hitl_gate(
            HitlAction(HitlActionType.NETWORK_ACCESS, "http://x", {}),
            store=store, reviewer_fn=_reviewer_count, config=cfg, human_decision=None,
        )
        assert rr.status == "escalated"
    assert await store.get_reject_count("network_access") == 3
    r5 = await run_hitl_gate(
        HitlAction(HitlActionType.NETWORK_ACCESS, "http://x", {}),
        store=store, reviewer_fn=_reviewer_count, config=cfg, human_decision=None,
    )
    assert r5.status == "escalated" and r5.ai_verdict == "breaker", "第 4 次应熔断升级"
    assert calls["n"] == 3, "熔断后不应再调用 reviewer（第 4 次 0 调用）"


@pytest.mark.asyncio
async def test_s1_ac4_ai_approve_falls_to_human_gate():
    cfg = HitlConfig(ai_review=True, reject_breaker=3)
    store = MemHitlStore()
    r = await run_hitl_gate(
        HitlAction(HitlActionType.WRITE_FILE, "f2", {}),
        store=store, reviewer_fn=_reviewer_approve, config=cfg, human_decision=None,
    )
    assert r.status == "pending", "AI 批准应继续走人工 gate（pending 等待批准）"


@pytest.mark.asyncio
async def test_s1_force_approve_escalated():
    cfg = HitlConfig(ai_review=True, reject_breaker=3)
    store = MemHitlStore()
    r4 = await run_hitl_gate(
        HitlAction(HitlActionType.EXEC_COMMAND, "rm -rf", {}),
        store=store, reviewer_fn=_reviewer_reject, config=cfg, human_decision=None,
    )
    assert r4.status == "escalated"
    calls = {"n": 0}

    async def _exec(action):
        calls["n"] += 1
        return {"done": True}

    r6 = await force_approve(r4.action_id, store=store, executor_fn=_exec, admin="admin1")
    assert r6.status == "executed" and calls["n"] == 1


@pytest.mark.asyncio
async def test_s1_resume_idempotent_terminal():
    """已为终态的 action 续审时幂等返回，不重复执行/建单（避免重复副作用）。"""
    store = MemHitlStore()
    r = await run_hitl_gate(
        HitlAction(HitlActionType.WRITE_FILE, "f", {}),
        store=store, executor_fn=(lambda a: _noop()), human_decision=True,
    )
    assert r.status == "executed"
    # 再次用同一 action_id（终态）续审 → 仍 executed，不报错
    r2 = await run_hitl_gate(
        HitlAction(HitlActionType.WRITE_FILE, "f", {}, action_id=r.action_id),
        store=store, human_decision=True,
    )
    assert r2.status == "executed"


async def _noop():
    return {"ok": True}


# ============================================================
# 执行器 seam：分类 + 拦截/放行
# ============================================================
def test_s1_classify_write_tools():
    assert _classify_hitl_action("write_file") == "write_file"
    assert _classify_hitl_action("create_doc") == "write_file"
    assert _classify_hitl_action("delete_row") == "write_file"
    assert _classify_hitl_action("send_mail") == "write_file"
    assert _classify_hitl_action("upload_img") == "write_file"


def test_s1_classify_exec_network_refund():
    assert _classify_hitl_action("run_shell") == "exec_command"
    assert _classify_hitl_action("exec_cmd") == "exec_command"
    assert _classify_hitl_action("web_fetch") == "network_access"
    assert _classify_hitl_action("http_request") == "network_access"
    assert _classify_hitl_action("download_file") == "network_access"
    assert _classify_hitl_action("refund_order") == "refund"
    assert _classify_hitl_action("chargeback_x") == "refund"


def test_s1_classify_read_tools_not_gated():
    # 只读/查询类工具不进 Gate，避免误伤 task-T1 回退工具
    assert _classify_hitl_action("web_search") is None
    assert _classify_hitl_action("search_knowledge") is None
    assert _classify_hitl_action("get_weather") is None


@pytest.mark.asyncio
async def test_s1_seam_pending_skips_execution(monkeypatch):
    """写工具 + 无决策 → SKIPPED（pending），执行器绝不调用（AC1 在 executor 层）。"""
    called = []

    async def _fake_exec(server, tool_name, args, call_id, operator_user_id, tenant_id, trace_id):
        called.append(1)
        return MCPToolTestResp(status=ToolCallStatusEnum.SUCCESS, call_id=call_id,
                               server_id=int(server.get("id") if isinstance(server, dict) else 1),
                               tool_name=tool_name)

    monkeypatch.setattr(executor_mod, "_execute_single_attempt", _fake_exec)
    store = MemHitlStore()
    r = await _run_hitl_seam(
        action_type="write_file", target="write_file", params={"path": "x"},
        operator_user_id=1, tenant_id="", trace_id="t", server_id=1,
        call_id="c1", human_decision=None, action_id="",
        server={"id": 1, "enabled": 1, "yn": 1}, store=store,
    )
    assert r is not None
    assert r.status == ToolCallStatusEnum.SKIPPED
    assert r.manual_guide["hitl_action_id"], "pending 必须带回 action_id 供 UI 续审"
    assert called == [], "未批准前执行器被调用了！"


@pytest.mark.asyncio
async def test_s1_seam_approve_executes(monkeypatch):
    """续审（action_id + 决策=True）→ 执行并返回 SUCCESS。"""
    called = []

    async def _fake_exec(server, tool_name, args, call_id, operator_user_id, tenant_id, trace_id):
        called.append(1)
        return MCPToolTestResp(status=ToolCallStatusEnum.SUCCESS, call_id=call_id,
                               server_id=int(server.get("id") if isinstance(server, dict) else 1),
                               tool_name=tool_name)

    monkeypatch.setattr(executor_mod, "_execute_single_attempt", _fake_exec)
    store = MemHitlStore()
    # 第一次：挂起拿 action_id
    r0 = await _run_hitl_seam(
        action_type="write_file", target="write_file", params={"path": "x"},
        operator_user_id=1, tenant_id="", trace_id="t", server_id=1,
        call_id="c1", human_decision=None, action_id="",
        server={"id": 1, "enabled": 1, "yn": 1}, store=store,
    )
    aid = r0.manual_guide["hitl_action_id"]
    # 第二次：带决策续审
    r1 = await _run_hitl_seam(
        action_type="write_file", target="write_file", params={"path": "x"},
        operator_user_id=1, tenant_id="", trace_id="t", server_id=1,
        call_id="c2", human_decision=True, action_id=aid,
        server={"id": 1, "enabled": 1, "yn": 1}, store=store,
    )
    assert r1.status == ToolCallStatusEnum.SUCCESS
    assert called == [1], "批准后应恰好执行一次"


@pytest.mark.asyncio
async def test_s1_seam_ai_review_escalates(monkeypatch):
    """HITL_AI_REVIEW=True 时，reviewer 拒绝 → 执行器返回 ERROR + needs_admin。"""
    monkeypatch.setattr(executor_mod.settings, "HITL_AI_REVIEW", True)
    monkeypatch.setattr(executor_mod.settings, "HITL_REJECT_BREAKER", 3)
    called = []

    async def _fake_exec(server, tool_name, args, call_id, operator_user_id, tenant_id, trace_id):
        called.append(1)
        return MCPToolTestResp(status=ToolCallStatusEnum.SUCCESS, call_id=call_id,
                               server_id=int(server.get("id") if isinstance(server, dict) else 1),
                               tool_name=tool_name)

    monkeypatch.setattr(executor_mod, "_execute_single_attempt", _fake_exec)
    store = MemHitlStore()
    r = await _run_hitl_seam(
        action_type="exec_command", target="run_shell", params={"cmd": "rm -rf"},
        operator_user_id=1, tenant_id="", trace_id="t", server_id=1,
        call_id="c1", human_decision=None, action_id="",
        server={"id": 1, "enabled": 1, "yn": 1}, store=store, reviewer_fn=_reviewer_reject,
    )
    assert r.status == ToolCallStatusEnum.ERROR
    assert r.manual_guide["needs_admin"] is True
    assert r.manual_guide["ai_verdict"] == "reject"
    assert called == [], "AI 拒绝不应执行"
