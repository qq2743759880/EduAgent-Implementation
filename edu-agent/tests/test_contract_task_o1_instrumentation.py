# -*- coding: utf-8 -*-
"""O1-① 契约测试：memory / executor / compaction 用 record_* 一行接入 OTel 埋点。

验收点（对应 P1 批判「埋点接入」）：
1. memory：store.recall / store.write 触发 memory_event（recall 带 adopted 标记）。
2. executor：execute_tool_plan 每工具执行触发 tool_result（SUCCESS / ERROR）。
3. compaction：compact_messages 触发 compaction_event（含 before/after tokens + policy）。

实现约定：各模块通过 `get_otel_exporter().record_*(...)` 一行写入；埋点失败不影响主流程。
本测试用 spy 拦截 OtelExporter.record，断言对应 event_type 被发出且携带关键 payload。
直接运行：
    pytest tests/test_contract_task_o1_instrumentation.py -q
"""
from __future__ import annotations

import asyncio

import pytest

from app.otel.exporter import OtelExporter


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """拦截 OtelExporter.record，收集所有事件（event_type + payload）。"""
    events: list[dict] = []
    orig = OtelExporter.record

    def spy(self, *args, **kwargs):
        etype = args[0] if args else kwargs.get("event_type")
        payload = (args[1] if len(args) > 1 else kwargs.get("payload")) or {}
        events.append({"event_type": etype, "payload": payload})
        return orig(self, *args, **kwargs)

    monkeypatch.setattr(OtelExporter, "record", spy)
    return events


def _types(events: list[dict]) -> list[str]:
    return [e["event_type"] for e in events]


# ------------------------------------------------------------
# 1. memory 埋点
# ------------------------------------------------------------
def test_memory_recall_and_write_emit_memory_event(captured):
    from app.ai.memory.store import MemoryStore
    from datetime import datetime

    class FakeMem:
        def __init__(self, mid):
            self.id = mid
            self.access_count = 0
            self.created_at = datetime.now()
            self.last_access_at = datetime.now()
            self.importance = 4

        def to_recall_dict(self):
            return {"id": self.id, "content": "x"}

    class StubPersist:
        async def insert(self, **kw):
            return 1

        async def fetch_by_ids(self, ids):
            return [FakeMem(i) for i in ids]

        async def touch(self, *a, **k):
            return None

    class StubVec:
        async def search(self, user_id, query, top_k):
            return [{"memory_id": 1, "score": 0.9}]

        async def upsert(self, *a, **k):
            return None

    store = MemoryStore(persistence=StubPersist(), vector_store=StubVec())

    async def go():
        await store.write(user_id=1, content="hello world")
        out = await store.recall(user_id=1, query="q")
        return out

    out = asyncio.run(go())
    assert isinstance(out, list) and len(out) >= 1, "recall 应召回至少 1 条"
    assert "memory_event" in _types(captured), "memory 模块应发出 memory_event"
    assert any(
        e["event_type"] == "memory_event" and e["payload"].get("action") == "write" for e in captured
    ), "write 应发出 memory_event"

    # recall 事件应携带 adopted 标记（命中采纳）
    recall_evt = next(
        e for e in captured if e["event_type"] == "memory_event" and e["payload"].get("action") == "recall"
    )
    assert recall_evt["payload"].get("adopted") is True


# ------------------------------------------------------------
# 2. executor 埋点
# ------------------------------------------------------------
def test_executor_emits_tool_result(captured, monkeypatch: pytest.MonkeyPatch):
    from app.chat.flows import agent as agent_mod
    import app.mcp.executor as mcp_executor

    async def fake_call_tool(*, tool_name, arguments, operator_user_id):
        return {"status": "SUCCESS", "result": "ok"}

    async def fake_call_tool_err(*, tool_name, arguments, operator_user_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(mcp_executor, "call_tool", fake_call_tool)
    summaries, _ = asyncio.run(
        agent_mod.execute_tool_plan([{"tool_name": "x", "args": {}}], operator_user_id=1)
    )
    assert summaries and summaries[0]["status"] == "SUCCESS"
    assert "tool_result" in _types(captured), "executor 应发出 tool_result（SUCCESS）"

    # 错误分支也应发出 tool_result（ERROR）
    monkeypatch.setattr(mcp_executor, "call_tool", fake_call_tool_err)
    asyncio.run(
        agent_mod.execute_tool_plan([{"tool_name": "y", "args": {}}], operator_user_id=1)
    )
    tool_results = [e for e in captured if e["event_type"] == "tool_result"]
    assert len(tool_results) >= 2, "executor 错误分支也应发出 tool_result（ERROR）"
    assert tool_results[-1]["payload"].get("outcome") == "ERROR"


# ------------------------------------------------------------
# 3. compaction 埋点
# ------------------------------------------------------------
def test_compaction_emits_compaction_event(captured):
    from app.ai.compaction import compact_messages

    # 构造明显超阈值的消息流（CJK，1 token/字），强制触发 compaction
    big = "上下文压缩" * 200
    msgs = [
        {"role": "user", "content": "请详细解释以下概念：" + big},
        {"role": "assistant", "content": "好的，下面分点说明：" + big},
    ]
    res = compact_messages(msgs, threshold=80)
    assert "compaction_event" in _types(captured), "compaction 模块应发出 compaction_event"

    evt = next(e for e in captured if e["event_type"] == "compaction_event")
    p = evt["payload"]
    # 埋点须携带 before/after tokens 与 policy，供 5 维指标累加
    assert isinstance(p.get("before_tokens"), int) and p["before_tokens"] > 0
    assert isinstance(p.get("after_tokens"), int) and p["after_tokens"] > 0
    assert p.get("policy") in ("context_edit", "compaction", "compact_budget")
    # 返回值也须带 token 测量（与埋点一致）
    assert res["before_tokens"] == p["before_tokens"]
