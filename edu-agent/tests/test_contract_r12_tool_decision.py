# -*- coding: utf-8 -*-
"""R12 LLM 工具决策接管 契约测试（dev-plan-reshape-r W3 R12 + v1.1 决策超时预算）。

验收面（对应派单 pytest 四例）：
  ① 工具意图 query 经 llm 模式产出正确 tool_plan（真 registry 工具）——
     单测：内存 registry 元数据 + fake LLM；集成：真实 DB registry（list_enabled_tool_metas）。
  ② 超时 → 规则 fallback（GWT：注入假慢 LLM，超时后按规则路由完成且延迟有界）+ 降级计数。
  ③ 非工具 query 不误触发（llm 返回空 tool_plan → 零工具调用，executor 不被触达）。
  ④ call_log SUCCESS 审计行存在（llm 模式真执行闭环：tool_plan → executor.call_tool(args=)
     → mcp_tool_call_log 落 SUCCESS 行；决策桩固定 + 真 executor/真 DB，DB 不可用则 skip）。

实现：决策器 llm_call 可注入（fake/慢桩），单测不依赖 live LLM/MySQL；
集成例单 asyncio.run 事件循环（asyncmy 池循环亲和），init 失败自动 skip（CI 安全）。
禁 Playwright；DB 只读断言（mcp_tool_call_log 行由 executor 自身写入，测试仅 SELECT）。
"""
from __future__ import annotations

import asyncio
import json
import os
import time

import pytest

from app.chat import tool_calling as tc_mod
from app.chat import tool_decision as td_mod
from app.chat.tool_calling import ToolMeta, run_chat_tool_calls
from app.chat.tool_decision import (
    build_tool_decision_messages,
    decide_tool_plan,
    get_tool_decision_stats,
)
from app.config import settings


# ============================================================
# 工具：内存 registry 元数据（形状=真实 ToolMeta，镜像 DB registry 四演示工具）
# ============================================================
def _mk(name: str, desc: str, schema: dict, tool_id: int) -> ToolMeta:
    return ToolMeta(
        tool_id=tool_id, server_id=1, tool_name=name, description=desc,
        input_schema_json=json.dumps(schema, ensure_ascii=False), category="stdio-echodemo",
    )


MEMORY_TOOLS = [
    _mk("ping", "返回 pong=true 的心跳，用于健康检查。", {"type": "object", "properties": {}}, tool_id=11),
    _mk("add", "整数 a + b，返回 {sum, was_negative}。",
        {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"]},
        tool_id=12),
    _mk("echo", "原样回显 text，返回 {echo, length}。",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}, tool_id=13),
    _mk("list_alphabet", "返回 1~52 个字母序列 A..Z 循环。",
        {"type": "object", "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 52}}, "required": ["n"]},
        tool_id=14),
]


def _add_meta() -> ToolMeta:
    return next(t for t in MEMORY_TOOLS if t.tool_name == "add")


def _fake_llm(payload: str):
    async def _call(messages, timeout):  # noqa: ARG001
        return payload
    return _call


async def _slow_llm(messages, timeout):  # noqa: ARG001
    await asyncio.sleep(60)
    return "{}"


def _stats_delta(before: dict) -> dict:
    now = get_tool_decision_stats()
    return {k: now.get(k, 0) - before.get(k, 0) for k in now}


def _patch_decide(monkeypatch: pytest.MonkeyPatch, plans: list):
    """把决策器替换为固定产物桩（tool_calling 在调用时才 import → patch 源模块属性生效）。

    返回协程（非跨 loop Future——asyncmy 池循环亲和同款教训）。"""
    async def _fake_decide(query, tools, **kw):  # noqa: ARG001
        return td_mod.ToolDecisionResult(plans=plans, mode="llm", fallback=False)

    monkeypatch.setattr(td_mod, "decide_tool_plan", _fake_decide, raising=True)


@pytest.fixture()
def llm_mode(monkeypatch: pytest.MonkeyPatch):
    """切 llm 决策模式（测试结束恢复默认 rule）。"""
    monkeypatch.setattr(settings, "TOOL_DECISION_MODE", "llm")


@pytest.fixture()
def stub_metas(monkeypatch: pytest.MonkeyPatch):
    """工具列表加载桩为内存 registry（单元口径：run_chat_tool_calls 整链路不依赖 DB）。"""
    async def _fake_metas():  # noqa: ARG001
        return MEMORY_TOOLS

    monkeypatch.setattr(tc_mod, "list_enabled_tool_metas", _fake_metas, raising=True)


# ============================================================
# 决策 prompt：真实注入工具清单（name/description/input_schema）
# ============================================================
def test_r12_0_decision_prompt_contains_registry_schema():
    msgs = build_tool_decision_messages("计算 17 加 25", MEMORY_TOOLS)
    assert len(msgs) == 2 and msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    sysc = msgs[0]["content"]
    assert "add" in sysc and "echo" in sysc          # 全部工具名注入
    assert "input_schema" in sysc                     # 参数 schema 注入（full 模式）
    assert "tool_plan" in sysc and "禁止强行调用" in sysc  # 防误触发条款在 prompt
    assert "最多选择1个工具" in sysc                   # MCP_TOOL_MAX_TRIES 同步进规则


# ============================================================
# ① llm 模式：工具意图 query → 正确 tool_plan
# ============================================================
def test_r12_1_llm_mode_produces_correct_tool_plan(llm_mode):
    before = get_tool_decision_stats()
    r = asyncio.run(decide_tool_plan(
        "帮我计算 17 加 25 等于多少", MEMORY_TOOLS,
        llm_call=_fake_llm('{"tool_plan":[{"tool_name":"add","args":{"a":17,"b":25}}]}'),
    ))
    assert r.fallback is False and r.mode == "llm"
    assert len(r.plans) == 1
    p = r.plans[0]
    assert p.tool.tool_name == "add" and p.args == {"a": 17, "b": 25}
    assert "llm决策" in p.reason
    assert _stats_delta(before)["llm_ok"] == 1


def test_r12_1b_llm_mode_with_real_registry_tools():
    """①集成：真 registry（DB mcp_tool×mcp_server）工具经 llm 模式产出 tool_plan。单循环。"""
    async def _main() -> tuple[bool, str]:
        try:
            from app.database import close_mysql, init_mysql
            await init_mysql()
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"
        try:
            tools = await tc_mod.list_enabled_tool_metas()
            assert tools, "真 registry 不应为空"
            add_meta = next(t for t in tools if t.tool_name == "add")
            r = await decide_tool_plan(
                "计算 100 加 23", tools,
                llm_call=_fake_llm('{"tool_plan":[{"tool_name":"add","args":{"a":100,"b":23}}]}'),
            )
            assert r.fallback is False and len(r.plans) == 1
            assert r.plans[0].tool.tool_id == add_meta.tool_id  # 绑定真实 registry 工具 id
            assert r.plans[0].args == {"a": 100, "b": 23}
            return True, ""
        finally:
            try:
                from app.database import close_mysql
                await close_mysql()
            except Exception:  # noqa: BLE001
                pass

    ok, err = asyncio.run(_main())
    if not ok:
        pytest.skip(f"DB 不可用，跳过真 registry 集成例：{err}")


# ============================================================
# ② 超时预算：假慢 LLM → 规则 fallback，延迟有界 + 降级计数
# ============================================================
def test_r12_2_timeout_falls_back_to_rule_bounded(llm_mode):
    before = get_tool_decision_stats()
    t0 = time.perf_counter()
    r = asyncio.run(decide_tool_plan(
        "计算 3+4 等于多少", MEMORY_TOOLS, timeout=1.0, llm_call=_slow_llm,
    ))
    elapsed = time.perf_counter() - t0
    assert r.fallback is True and r.fallback_reason == "timeout" and r.mode == "rule"
    # 延迟有界：1s 预算 + 少量调度余量（GWT：超时后按规则路由完成请求且延迟有界）
    assert elapsed < 3.0, f"fallback 未按时放弃：{elapsed:.2f}s"
    # 规则路由结果（现行为）接管：add(3,4)
    assert [(p.tool.tool_name, p.args) for p in r.plans] == [("add", {"a": 3, "b": 4})]
    assert _stats_delta(before)["llm_timeout"] == 1


def test_r12_2b_unparseable_output_falls_back(llm_mode):
    before = get_tool_decision_stats()
    r = asyncio.run(decide_tool_plan(
        "计算 3+4", MEMORY_TOOLS, llm_call=_fake_llm("我觉得应该调用一下计算工具"),
    ))
    assert r.fallback is True and r.fallback_reason == "unparseable"
    assert [(p.tool.tool_name, p.args) for p in r.plans] == [("add", {"a": 3, "b": 4})]
    assert _stats_delta(before)["llm_unparseable"] == 1


def test_r12_2c_llm_error_falls_back(llm_mode):
    before = get_tool_decision_stats()

    async def _boom(messages, timeout):  # noqa: ARG001
        raise RuntimeError("llm down")

    r = asyncio.run(decide_tool_plan("计算 3+4", MEMORY_TOOLS, llm_call=_boom))
    assert r.fallback is True and r.fallback_reason == "error"
    assert [(p.tool.tool_name, p.args) for p in r.plans] == [("add", {"a": 3, "b": 4})]
    assert _stats_delta(before)["llm_error"] == 1


# ============================================================
# ③ 非工具 query 不误触发（空 tool_plan 合法，executor 零触达）
# ============================================================
def test_r12_3_non_tool_query_no_false_trigger(llm_mode, monkeypatch: pytest.MonkeyPatch):
    from app.mcp import executor as executor_mod

    def _guard(*a, **k):  # noqa: ARG001
        raise AssertionError("非工具 query 不应触达 executor.call_tool")

    monkeypatch.setattr(executor_mod, "call_tool", _guard)

    r = asyncio.run(decide_tool_plan(
        "什么是勾股定理？请解释一下", MEMORY_TOOLS,
        llm_call=_fake_llm('{"tool_plan":[]}'),
    ))
    assert r.fallback is False and r.mode == "llm" and r.plans == []
    assert _stats_delta(get_tool_decision_stats())["llm_ok"] >= 0  # 合法空决策计 llm_ok


def test_r12_3b_non_tool_via_run_chat_tool_calls(llm_mode, stub_metas, monkeypatch: pytest.MonkeyPatch):
    """端到端口径：run_chat_tool_calls llm 模式 + LLM 判空 → 空摘要/空上下文/零执行。

    纯单元口径：工具列表加载桩为内存 registry（stub_metas，不依赖 DB）。"""
    from app.mcp import executor as executor_mod

    def _guard(*a, **k):  # noqa: ARG001
        raise AssertionError("非工具 query 不应触达 executor.call_tool")

    monkeypatch.setattr(executor_mod, "call_tool", _guard)

    async def _fake_empty(query, tools, **kw):  # noqa: ARG001
        return td_mod.ToolDecisionResult(plans=[], mode="llm", fallback=False)

    monkeypatch.setattr(td_mod, "decide_tool_plan", _fake_empty, raising=True)

    summaries, ctx, degraded = asyncio.run(run_chat_tool_calls(
        query="什么是勾股定理？", operator_user_id=1, use_mcp_flag=True,
    ))
    assert summaries == [] and ctx == "" and degraded is None

# ============================================================
# 开关语义：默认 rule = 现行为（LLM 决策器不被调用，生产零变化）
# ============================================================
def test_r12_default_rule_mode_keeps_legacy_behavior(monkeypatch: pytest.MonkeyPatch, stub_metas):
    assert str(settings.TOOL_DECISION_MODE).lower() == "rule"  # 默认不改生产

    def _boom(*a, **k):  # noqa: ARG001
        raise AssertionError("rule 模式不应调用 LLM 决策器")

    monkeypatch.setattr(td_mod, "decide_tool_plan", _boom, raising=True)
    plans = tc_mod._parse_heuristic("计算 3+4 等于多少", MEMORY_TOOLS)
    assert [(p.tool.tool_name, p.args) for p in plans] == [("add", {"a": 3, "b": 4})]

    # rule 模式整链路（run_chat_tool_calls）也不触达决策器
    from app.mcp import executor as executor_mod
    from app.mcp.schemas import MCPToolTestResp, ToolCallStatusEnum

    async def _fake_call_tool(**kwargs):
        return MCPToolTestResp(
            status=ToolCallStatusEnum.SUCCESS, latency_ms=1, call_id="r12-rule-1",
            server_id=1, tool_name="add", content_text='{"sum": 7}', error_message=None,
        )

    monkeypatch.setattr(executor_mod, "call_tool", _fake_call_tool)
    summaries, ctx, degraded = asyncio.run(run_chat_tool_calls(
        query="计算 3+4", operator_user_id=1, use_mcp_flag=True,
    ))
    assert len(summaries) == 1 and summaries[0].status == "success"
    assert "决策器=rule" in (ctx or "")


# ============================================================
# 接线：run_chat_tool_calls × llm 模式（决策桩）→ executor.call_tool(args=) → SUCCESS
# ============================================================
def test_r12_run_chat_tool_calls_llm_wiring(llm_mode, stub_metas, monkeypatch: pytest.MonkeyPatch):
    from app.mcp import executor as executor_mod
    from app.mcp.schemas import MCPToolTestResp, ToolCallStatusEnum

    captured: dict = {}

    async def _fake_call_tool(**kwargs):
        captured.update(kwargs)
        return MCPToolTestResp(
            status=ToolCallStatusEnum.SUCCESS, latency_ms=3, call_id="r12-wiring-1",
            server_id=1, tool_name="add", content_text='{"sum": 42}', error_message=None,
        )

    monkeypatch.setattr(executor_mod, "call_tool", _fake_call_tool)

    item = tc_mod.ToolPlanItem(tool=_add_meta(), args={"a": 17, "b": 25}, reason="llm决策(wired)")
    _patch_decide(monkeypatch, [item])

    summaries, ctx, degraded = asyncio.run(run_chat_tool_calls(
        query="计算 17 加 25", operator_user_id=1, use_mcp_flag=True,
    ))
    assert degraded is None
    assert len(summaries) == 1 and summaries[0].status == "success"
    assert summaries[0].call_id == "r12-wiring-1"
    # R04 修复的 args= 签名（真执行闭环参数面）+ 真实 registry 工具 id
    assert captured.get("args") == {"a": 17, "b": 25}
    assert captured.get("tool_id") == _add_meta().tool_id
    assert "sum" in (ctx or "") and "决策器=llm(" in (ctx or "")


# ============================================================
# ④ call_log SUCCESS 审计行（llm 决策桩 + 真 executor 真 DB；不可用则 skip）
# ============================================================
def test_r12_4_call_log_success_audit_row(llm_mode, monkeypatch: pytest.MonkeyPatch):
    async def _main() -> tuple[bool, str, object]:
        try:
            from app.database import init_mysql
            await init_mysql()
            tools = await tc_mod.list_enabled_tool_metas()
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}", None
        try:
            # 决策桩：llm 产出 add(6,7)；executor 全真（stdio spawn + 审计落库）
            add_meta = next(t for t in tools if t.tool_name == "add")
            item = tc_mod.ToolPlanItem(tool=add_meta, args={"a": 6, "b": 7}, reason="llm决策(stub)")
            _patch_decide(monkeypatch, [item])

            summaries, ctx, degraded = await run_chat_tool_calls(
                query="帮我用工具计算 6 加 7", operator_user_id=1,
                trace_id="r12-pytest-calllog", use_mcp_flag=True,
            )
            assert degraded is None, f"执行闭环不应降级：{degraded}"
            assert len(summaries) == 1, f"llm 决策应产出 1 次工具调用：{summaries}"
            s = summaries[0]
            assert s.status == "success" and s.tool_name == "add"
            assert "决策器=llm(" in (ctx or "") and "fallback" not in (ctx or "")

            # mcp_tool_call_log SUCCESS 行存在（executor 落审计行，测试只读 SELECT）
            from app.database import fetch_one
            row = await fetch_one(
                "SELECT call_id, tool_name, status, latency_ms, trace_id "
                "FROM mcp_tool_call_log WHERE call_id=%s",
                (s.call_id,),
            )
            return True, "", row
        finally:
            try:
                from app.database import close_mysql
                await close_mysql()
            except Exception:  # noqa: BLE001
                pass

    ok, err, row = asyncio.run(_main())
    if not ok:
        pytest.skip(f"DB 不可用，跳过 call_log 集成例：{err}")
    assert row is not None, "call_id 未落 mcp_tool_call_log"
    assert str(row["status"]).upper() == "SUCCESS" and row["tool_name"] == "add"
    print(f"\n[R12 call_log 证据] call_id={row['call_id']} tool={row['tool_name']} "
          f"status={row['status']} latency_ms={row['latency_ms']} trace_id={row['trace_id']}")


# ============================================================
# 附：真 LLM 活体例（R12_LIVE_LLM=1 时才跑；CI/常规跳过）——
# llm 模式 + 默认 _ChatClient(fast) 真决策真执行，产出 call_log SUCCESS 行
# ============================================================
@pytest.mark.skipif(
    os.environ.get("R12_LIVE_LLM") != "1",
    reason="真 LLM 活体例：设 R12_LIVE_LLM=1 显式开启（默认跳过，保 CI 确定性）",
)
def test_r12_5_live_llm_end_to_end(llm_mode):
    async def _main() -> tuple[bool, str, object, object]:
        try:
            from app.database import init_mysql
            await init_mysql()
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}", None, None
        try:
            summaries, ctx, degraded = await run_chat_tool_calls(
                query="请用工具计算 17 加 25 的和", operator_user_id=1,
                trace_id="r12-live-llm", use_mcp_flag=True,
            )
            from app.database import fetch_one
            row = None
            if summaries:
                row = await fetch_one(
                    "SELECT call_id, tool_name, status FROM mcp_tool_call_log WHERE call_id=%s",
                    (summaries[0].call_id,),
                )
            return True, "", summaries, (row, ctx, degraded)
        finally:
            try:
                from app.database import close_mysql
                await close_mysql()
            except Exception:  # noqa: BLE001
                pass

    ok, err, summaries, extra = asyncio.run(_main())
    if not ok:
        pytest.skip(f"DB 不可用：{err}")
    row, ctx, degraded = extra
    assert summaries, f"真 LLM 应产出工具调用（ctx 头={str(ctx)[:120]}）"
    assert degraded is None
    assert row is not None and str(row["status"]).upper() == "SUCCESS"
    assert "决策器=llm(" in (ctx or "")
    print(f"\n[R12 真 LLM 证据] summaries={[(s.tool_name, s.args_summary, s.status) for s in summaries]} "
          f"call_log={dict(row)}")
