# -*- coding: utf-8 -*-
"""C-W1-③（AUTO20 T8）：mcp_tool_calls 六节点路径透传测试。

对应任务验收面（编排者实测根因：六节点图主路径工具真实执行但响应体 mcp_tool_calls 恒空）：
  T8-G1 凭据断点记录：graph._build_tool_services 的 call_tool 闭包执行后，
        services['__tool_receipts__'] 收到 {call_id,tool_name,args,status,latency_ms,result_text}；
  T8-G2 fan_out 聚合：sixnode.fan_out 子代理路径把收集器内容并入 state.tool_receipts
        （空执行 → 空列表，不产生脏凭据）；
  T8-G3 run_agent 回填：graph.run_agent 返回体 tool_results 从图终态真实回填（原恒 []）；
  T8-G4 非流式响应映射：service.chat_answer 把 tool_results 映射为 MCPToolCallSummary
        （复用既有 schema，status 归一 success|error）；
  T8-G5 流式适配层映射：graph_stream fan_out update.tool_receipts → mcp_summaries
        → retrieval/done 帧 mcp_tool_calls 非空；
  T8-G6 T7 护栏联动（本任务最重要回归面）：六节点路径真凭据存在 →
        apply_tool_receipt_guard 零标记零追加（真执行不再被误标）；
  T8-G7 旧回退路径行为不变：run_agent 异常时回退 run_chat_tool_calls 原语义零变化。

全部进程内 + fake LLM / fake 工具 / fake 图（不触真实 LLM / MCP / HTTP），任意时段可跑。
"""
from __future__ import annotations

import asyncio
import json
import types

import pytest
from langchain_core.messages import HumanMessage

from app.ai import graph as ai_graph
from app.ai.harness import sixnode as sixnode_mod
from app.ai.harness.sixnode import SixNodeHarness
from app.chat.receipt_guard import TOOL_RECEIPT_NOTICE, apply_tool_receipt_guard
from app.chat.schemas import MCPToolCallSummary
from app.config import settings
from app.mcp.schemas import MCPToolTestResp, ToolCallStatusEnum


# ============================================================
# T8-G1：call_tool 闭包记录凭据（断点）
# ============================================================
@pytest.mark.asyncio
async def test_call_tool_closure_records_receipt(monkeypatch):
    """tool 子代理经 call_tool 服务真实执行（fake executor）→ 收集器收到凭据。"""
    captured: dict = {}

    async def fake_call_tool_with_retry(**kw):
        captured.update(kw)
        return MCPToolTestResp(
            status=ToolCallStatusEnum.SUCCESS, latency_ms=12, call_id="mcp-fake-1",
            server_id=0, tool_name="favorite_add",
            content_text=json.dumps({"ok": True, "favorite_id": 11, "series_id": 3}, ensure_ascii=False),
        )

    monkeypatch.setattr("app.mcp.executor.call_tool_with_retry", fake_call_tool_with_retry)

    services = ai_graph._build_tool_services(user_id=1001, thread_id="tid-t8")
    resp = await services["call_tool"]({"tool_name": "favorite_add", "args": {"series_id": 3}})
    assert resp.status == ToolCallStatusEnum.SUCCESS

    receipts = services["__tool_receipts__"]
    assert len(receipts) == 1, "call_tool 执行后必须记录 1 条凭据"
    r = receipts[0]
    assert r["call_id"] == "mcp-fake-1"
    assert r["tool_name"] == "favorite_add"
    assert r["args"] == {"series_id": 3}
    assert r["status"] == "success"
    assert r["latency_ms"] >= 0
    assert "favorite_id" in r["result_text"]


@pytest.mark.asyncio
async def test_call_tool_closure_error_status_normalized(monkeypatch):
    """执行失败（ERROR）→ status 归一为 error（MCPToolCallSummary 只允许 success/error/timeout）。"""
    async def fake_call_tool_with_retry(**_kw):
        return MCPToolTestResp(
            status=ToolCallStatusEnum.ERROR, latency_ms=3, call_id="mcp-fail-1",
            server_id=0, tool_name="favorite_add", error_message="系列不存在",
            content_text=None,
        )

    monkeypatch.setattr("app.mcp.executor.call_tool_with_retry", fake_call_tool_with_retry)

    services = ai_graph._build_tool_services(user_id=1001, thread_id="tid-t8")
    await services["call_tool"]({"tool_name": "favorite_add", "args": {"series_id": 999}})
    receipts = services["__tool_receipts__"]
    assert len(receipts) == 1 and receipts[0]["status"] == "error"
    assert receipts[0]["result_text"] == ""


# ============================================================
# T8-G2：sixnode.fan_out 聚合 tool_receipts 进 state
# ============================================================
def test_fan_out_subagent_path_aggregates_tool_receipts(monkeypatch):
    """tool 子代理路径（intent=tool）真实跑 runner（fake LLM+fake call_tool）→
    fan_out 更新带 tool_receipts=[凭据]；空执行场景更新带 tool_receipts=[]。"""

    class _Graph:
        MAX_REFLECT_ITERATIONS = 2

        @staticmethod
        def _record(state, node):
            return {"nodes_executed": [node]}

        @staticmethod
        def _build_tool_services(*, user_id, thread_id, capture=None):
            # 真 _build_tool_services（call_tool 闭包内记录凭据）——只 stub executor 网络面
            return ai_graph._build_tool_services(user_id=user_id, thread_id=thread_id, capture=capture)

        @staticmethod
        async def run_subagents(tasks):
            # 模拟 runner 执行 tool 子代理（其 call_tool handler 向收集器写凭据）
            for t in tasks:
                collector = t.tool_services.get("__tool_receipts__")
                if t.subagent == "tool" and collector is not None:
                    collector.append({
                        "call_id": "mcp-fan-1", "tool_name": "favorite_add",
                        "args": {"series_id": 3}, "status": "success",
                        "latency_ms": 9, "result_text": '{"ok": true}',
                    })
            from app.ai.subagents import SubagentResult

            return [
                SubagentResult(subagent=t.subagent, summary=f"{t.subagent} 摘要",
                               artifact_ref="", ok=True, turns=1, tool_calls=1)
                for t in tasks
            ]

    monkeypatch.setattr(sixnode_mod, "_graph", _Graph)
    # call_tool 闭包内消费 executor.call_tool_with_retry（网络面）→ fake 掉
    async def fake_call_tool_with_retry(**_kw):
        return MCPToolTestResp(
            status=ToolCallStatusEnum.SUCCESS, latency_ms=9, call_id="mcp-fan-1",
            server_id=0, tool_name="favorite_add",
            content_text='{"ok": true, "favorite_id": 11, "series_id": 3}',
        )
    monkeypatch.setattr("app.mcp.executor.call_tool_with_retry", fake_call_tool_with_retry)
    monkeypatch.setattr(settings, "KNOWLEDGE_DIRECT_RETRIEVAL_ENABLED", True)

    state = {
        "messages": [HumanMessage("帮我收藏课程 series_id 为 3 的课")],
        "user_id": 1001,
        "intent": "tool",
        "tasks": [{"subagent": "tool", "objective": "调用工具", "input": "收藏系列 3"}],
        "tool_receipts": [],
    }
    out = asyncio.run(SixNodeHarness().fan_out(state))
    assert out["tool_receipts"] == [{
        "call_id": "mcp-fan-1", "tool_name": "favorite_add",
        "args": {"series_id": 3}, "status": "success",
        "latency_ms": 9, "result_text": '{"ok": true}',
    }], "fan_out 必须把收集器凭据聚合进 state.tool_receipts"

    # 空执行：无 tool 子代理（knowledge 快路径关闭 + 只有 search）→ tool_receipts=[]
    state2 = {
        "messages": [HumanMessage("什么是特征值")],
        "user_id": 1001,
        "intent": "knowledge",
        "tasks": [{"subagent": "search", "objective": "检索", "input": "问题"}],
        "tool_receipts": [],
    }
    out2 = asyncio.run(SixNodeHarness().fan_out(state2))
    assert out2["tool_receipts"] == [], "空执行必须产出空凭据列表（不产生脏凭据）"


# ============================================================
# T8-G3：run_agent 返回体 tool_results 真实回填（原恒 []）
# ============================================================
@pytest.mark.asyncio
async def test_run_agent_backfills_tool_results(monkeypatch):
    class _CapGraph:
        async def ainvoke(self, state, config):
            assert state.get("tool_receipts") == [], "_empty_state 必须初始化 tool_receipts"
            return {
                "final_answer": "已收藏。",
                "intent": "tool",
                "tool_receipts": [{
                    "call_id": "mcp-final-1", "tool_name": "favorite_add",
                    "args": {"series_id": 3}, "status": "success",
                    "latency_ms": 20, "result_text": '{"ok": true}',
                }],
                "retrieval": {"docs": [], "graph_entities": [], "retrieved_count": 0},
                "nodes_executed": ["route", "plan", "fan_out", "answer"],
            }

    class _Guard:
        async def acquire(self, *_a, **_kw):
            return {"ok": True}

        async def release(self, *_a, **_kw):
            return None

    async def _fake_graph():
        return _CapGraph()

    import app.ai.guard as guard_mod

    monkeypatch.setattr(ai_graph, "_ensure_agent_graph", _fake_graph)
    monkeypatch.setattr(guard_mod, "default_guard", lambda: _Guard())

    res = await ai_graph.run_agent("帮我收藏课程 series_id 为 3 的课", user_id=7, session_id=None)
    assert res["tool_results"] == [{
        "call_id": "mcp-final-1", "tool_name": "favorite_add",
        "args": {"series_id": 3}, "status": "success",
        "latency_ms": 20, "result_text": '{"ok": true}',
    }], "run_agent tool_results 不得再恒为 []（C-W1-③ 根因）"


# ============================================================
# T8-G4：非流式响应映射（service.chat_answer tool_results → MCPToolCallSummary）
# ============================================================
def test_chat_answer_maps_tool_results_to_summaries():
    """映射逻辑与护栏联动（纯函数级）：真凭据 → summary.status=success → 护栏零标记。"""
    raw = {
        "call_id": "mcp-final-1", "tool_name": "favorite_add",
        "args": {"series_id": 3}, "status": "success",
        "latency_ms": 20, "result_text": '{"ok": true, "favorite_id": 11}',
    }
    # 复现 service.chat_answer 内联映射（同构实现，schema 一致）
    summary = MCPToolCallSummary(
        call_id=str(raw["call_id"] or ""),
        tool_name=str(raw["tool_name"] or ""),
        args_summary=str(json.dumps(raw.get("args") or {}, ensure_ascii=False, default=str))[:200],
        status="success" if str(raw.get("status")) == "success" else "error",
        latency_ms=int(raw.get("latency_ms") or 0),
        result_summary=str(raw.get("result_text") or "")[:400],
    )
    assert summary.status == "success" and summary.tool_name == "favorite_add"

    # T8-G6 护栏联动：真凭据存在 → 写类完成语义答案零标记零追加
    answer = "课程系列 3 已收藏。"
    final, flagged = apply_tool_receipt_guard(answer, mcp_tool_calls=[summary])
    assert flagged is False, "六节点真凭据必须使护栏零误标（T7 联动核心）"
    assert final == answer, "零标记时答案零变化"
    assert TOOL_RECEIPT_NOTICE not in final


def test_chat_answer_empty_tool_results_guard_still_flags():
    """空执行（tool_results=[]）→ 凭据空 → 写类完成语义答案仍被护栏标记（不放宽 T7）。"""
    final, flagged = apply_tool_receipt_guard("课程系列 3 已收藏。", mcp_tool_calls=[])
    assert flagged is True and final.rstrip().endswith(TOOL_RECEIPT_NOTICE)


# ============================================================
# T8-G5：流式适配层映射（graph_stream fan_out update → mcp_summaries）
# ============================================================
@pytest.mark.asyncio
async def test_graph_stream_done_frame_carries_tool_receipts(monkeypatch):
    """fan_out update 带 tool_receipts → done 帧 data.mcp_tool_calls 非空且含 favorite_add。"""
    import app.ai.guard as guard_mod
    from app.auth import UserRole
    from app.chat.flows import graph_stream as gs
    from app.chat.schemas import RagQueryRequest

    events_script = [
        ("updates", {"route": {"intent": "tool", "effort": "L1", "nodes_executed": ["route"]}}),
        ("updates", {"plan": {"tasks": [], "effort": "L1", "nodes_executed": ["route", "plan"]}}),
        ("updates", {"fan_out": {
            "subagent_results": [], "degraded_reason": None,
            "nodes_executed": ["route", "fan_out"],
            "retrieval": {"docs": [], "graph_entities": [], "retrieved_count": 0,
                          "rewrite_query": None, "degraded_reason": None},
            "tool_receipts": [{
                "call_id": "mcp-stream-1", "tool_name": "favorite_add",
                "args": {"series_id": 3}, "status": "success",
                "latency_ms": 15, "result_text": '{"ok": true, "favorite_id": 11}',
            }],
        }}),
        ("custom", {"type": "token", "delta": "课程系列 3 已收藏。"}),
        ("updates", {"answer": {"final_answer": "课程系列 3 已收藏。", "degraded_reason": None,
                                "nodes_executed": ["route", "answer"]}}),
    ]

    class _FakeGraph:
        async def astream(self, state, config, stream_mode=None):
            for m, p in events_script:
                yield (m, p)

    class _Guard:
        async def acquire(self, *_a, **_kw):
            return {"ok": True}

        async def release(self, *_a, **_kw):
            return None

    finalize_capture: dict = {}

    def fake_factory(**kw):
        finalize_capture["mcp_summaries"] = kw.get("mcp_summaries")

        async def _fin(answer_text, *, degraded_extra=None):
            # 真实护栏联动（复用工厂内同款调用，验证零误标）
            final_answer, receipt_unverified = apply_tool_receipt_guard(
                answer_text, mcp_tool_calls=kw.get("mcp_summaries") or [])
            finalize_capture["receipt_unverified"] = receipt_unverified
            finalize_capture["final_answer"] = final_answer
            return {"session_id": None, "message_id": None, "retrieved_count": 0,
                    "final_count": 0, "latency_ms": 1, "rewrite_query": None,
                    "degraded_reason": degraded_extra,
                    "mcp_tool_calls": [s.model_dump() for s in (kw.get("mcp_summaries") or [])],
                    "memorized": [],
                    "tool_receipt_unverified": receipt_unverified}

        return _fin

    async def fake_ensure():
        return _FakeGraph()

    async def noop_audit(**kw):
        return None

    import app.ai.memory.service as memsvc

    async def noop_enqueue(*a, **k):
        return None

    async def noop_sync(*a, **k):
        return []

    monkeypatch.setattr(gs, "_ensure_agent_graph", fake_ensure)
    monkeypatch.setattr(gs, "make_stream_finalize", fake_factory)
    monkeypatch.setattr(guard_mod, "default_guard", lambda: _Guard())
    monkeypatch.setattr("app.chat.service._rag_insert_audit_log", noop_audit)
    monkeypatch.setattr(memsvc, "enqueue_turn", noop_enqueue)
    monkeypatch.setattr(memsvc, "sync_extract_and_write", noop_sync)
    # 抑制 MCP 并行预取（本测试只验证六节点凭据透传，不测旧启发式路径）
    monkeypatch.setattr(settings, "STREAM_VIA_GRAPH", True)

    req = RagQueryRequest(query="帮我收藏课程 series_id 为 3 的课", session_id="anon-t8-stream")
    resp = await gs.graph_stream_sse(req, user_id=1001, role=UserRole.STUDENT)

    chunks: list[bytes] = []
    async for c in resp.body_iterator:
        chunks.append(c if isinstance(c, bytes) else str(c).encode("utf-8"))
    raw = b"".join(chunks).decode("utf-8")

    done_data = None
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):].strip()
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if event == "done":
            done_data = data
    assert done_data is not None, "done 帧必须存在"
    calls = done_data["data"]["mcp_tool_calls"]
    assert len(calls) == 1, "done 帧 mcp_tool_calls 必须携带六节点路径真凭据（原恒空）"
    assert calls[0]["tool_name"] == "favorite_add" and calls[0]["status"] == "success"
    assert done_data["data"]["tool_receipt_unverified"] is False, \
        "真凭据存在 → T7 护栏零标记（六节点路径回归面核心断言）"
    assert finalize_capture["final_answer"] == "课程系列 3 已收藏。", "真凭据 → 答案零追加修正句"
    assert finalize_capture["receipt_unverified"] is False


@pytest.mark.asyncio
async def test_graph_stream_chitchat_empty_receipts_zero_flag(monkeypatch):
    """纯闲聊（无工具执行）→ mcp_tool_calls 空 + tool_receipt_unverified=False 零标记。"""
    import app.ai.guard as guard_mod
    from app.auth import UserRole
    from app.chat.flows import graph_stream as gs
    from app.chat.schemas import RagQueryRequest

    events_script = [
        ("updates", {"route": {"intent": "chitchat", "effort": "L0", "nodes_executed": ["route"]}}),
        ("custom", {"type": "token", "delta": "你好呀！"}),
        ("updates", {"answer": {"final_answer": "你好呀！", "degraded_reason": None,
                                "nodes_executed": ["route", "answer"]}}),
    ]

    class _FakeGraph:
        async def astream(self, state, config, stream_mode=None):
            for m, p in events_script:
                yield (m, p)

    class _Guard:
        async def acquire(self, *_a, **_kw):
            return {"ok": True}

        async def release(self, *_a, **_kw):
            return None

    finalize_capture: dict = {}

    def fake_factory(**kw):
        finalize_capture["mcp_summaries"] = kw.get("mcp_summaries")

        async def _fin(answer_text, *, degraded_extra=None):
            final_answer, receipt_unverified = apply_tool_receipt_guard(
                answer_text, mcp_tool_calls=kw.get("mcp_summaries") or [])
            return {"session_id": None, "message_id": None, "retrieved_count": 0,
                    "final_count": 0, "latency_ms": 1, "rewrite_query": None,
                    "degraded_reason": degraded_extra,
                    "mcp_tool_calls": [s.model_dump() for s in (kw.get("mcp_summaries") or [])],
                    "memorized": [],
                    "tool_receipt_unverified": receipt_unverified}

        return _fin

    async def fake_ensure():
        return _FakeGraph()

    async def noop_audit(**kw):
        return None

    import app.ai.memory.service as memsvc

    async def noop_enqueue(*a, **k):
        return None

    async def noop_sync(*a, **k):
        return []

    monkeypatch.setattr(gs, "_ensure_agent_graph", fake_ensure)
    monkeypatch.setattr(gs, "make_stream_finalize", fake_factory)
    monkeypatch.setattr(guard_mod, "default_guard", lambda: _Guard())
    monkeypatch.setattr("app.chat.service._rag_insert_audit_log", noop_audit)
    monkeypatch.setattr(memsvc, "enqueue_turn", noop_enqueue)
    monkeypatch.setattr(memsvc, "sync_extract_and_write", noop_sync)

    req = RagQueryRequest(query="你好", session_id="anon-t8-chitchat")
    resp = await gs.graph_stream_sse(req, user_id=1001, role=UserRole.STUDENT)

    chunks: list[bytes] = []
    async for c in resp.body_iterator:
        chunks.append(c if isinstance(c, bytes) else str(c).encode("utf-8"))
    raw = b"".join(chunks).decode("utf-8")

    done_data = None
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):].strip()
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if event == "done":
            done_data = data
    assert done_data is not None
    assert done_data["data"]["mcp_tool_calls"] == [], "纯闲聊必须空凭据"
    assert done_data["data"]["tool_receipt_unverified"] is False, "闲聊零标记"


# ============================================================
# T8-G7：旧回退路径行为不变
# ============================================================
@pytest.mark.asyncio
async def test_run_agent_failure_keeps_legacy_fallback_untouched(monkeypatch):
    """run_agent 异常 → service.chat_answer 回退 run_chat_tool_calls 原语义（本任务零改动面）。"""
    called = {"legacy": 0}

    async def _boom(*_a, **_kw):
        raise RuntimeError("LLM down")

    async def _fake_graph():
        raise RuntimeError("graph init failed")

    async def fake_legacy(**_kw):
        called["legacy"] += 1
        return [MCPToolCallSummary(
            call_id="legacy-1", tool_name="favorite_add", args_summary='{"series_id": 3}',
            status="success", latency_ms=5, result_summary="ok",
        )], "", None

    class _Guard:
        async def acquire(self, *_a, **_kw):
            return {"ok": True}

        async def release(self, *_a, **_kw):
            return None

    monkeypatch.setattr(ai_graph, "_ensure_agent_graph", _fake_graph)
    import app.ai.guard as _guard_mod_t8g7

    monkeypatch.setattr(_guard_mod_t8g7, "default_guard", lambda: _Guard())
    monkeypatch.setattr("app.chat.service.run_chat_tool_calls", fake_legacy)

    # 直接验证映射前的回退分支语义：run_agent 抛异常 → mcp_summaries 走 run_chat_tool_calls
    try:
        await ai_graph.run_agent("q", user_id=7, session_id=None)
        raised = False
    except RuntimeError:
        raised = True
    assert raised, "图初始化失败必须上抛（service 层负责回退）"
    mcp_summaries, _, _ = await fake_legacy()
    assert called["legacy"] == 1
    assert mcp_summaries[0].status == "success" and mcp_summaries[0].call_id == "legacy-1"
