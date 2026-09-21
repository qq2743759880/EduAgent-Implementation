# -*- coding: utf-8 -*-
"""FEAT-WIRE-V2 缺陷#11：跨会话记忆召回注入回归测试。

背景（用户实测）：会话A说「我叫X」→ 新会话B问「我叫什么」AI 答不出。
根因：意图路由中 chitchat 直达 answer（零子代理）、兜底计划 L1=[search] 均无 memory
子代理 → 用户记忆从未被召回注入 prompt。修复：answer() 在 plan 未跑 memory 子代理时
补一次确定性轻量召回（recall_topk）注入「## 用户记忆」上下文；已跑则不重复。

零数据库/零 LLM 依赖：recall 与 LLM 全打桩，捕获 answer 实际下发的 system prompt 断言。
"""
from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage

from app.ai.harness import sixnode
from app.ai.harness.sixnode import SixNodeHarness

_MEM_TEXT = "用户记忆：[M1] 用户名叫小明"


def _state(**kw):
    base = {
        "messages": [HumanMessage("我叫什么名字")],
        "user_id": 1,
        "merged_context": "",
        "skill_context": "",
        "subagent_results": [],
    }
    base.update(kw)
    return base


def _patch_llm_capture(monkeypatch, captured):
    async def _fake_llm_call(messages, **kw):
        captured.append(messages)
        return "你叫小明。"

    monkeypatch.setattr(sixnode._graph, "_llm_call", _fake_llm_call)


def _patch_recall(monkeypatch, hits=1):
    async def _fake_recall(user_id, query, top_k=3, **kw):
        assert user_id == 1
        return [{"memory_id": 1, "content": "用户名叫小明"}] if hits else []

    def _fake_format(rows, header="用户记忆"):
        return (_MEM_TEXT, {1: 1}) if rows else ("", {})

    from app.ai.memory import service as mem_service

    monkeypatch.setattr(mem_service, "recall_topk", _fake_recall)
    monkeypatch.setattr(mem_service, "format_memories_for_prompt", _fake_format)


def test_chitchat_answer_injects_memory(monkeypatch):
    """① chitchat 直答（无 memory 子代理）→ answer 注入用户记忆。"""
    captured = []
    _patch_llm_capture(monkeypatch, captured)
    _patch_recall(monkeypatch)

    async def _run():
        return await SixNodeHarness().answer(_state())

    out = asyncio.run(_run())
    assert out["final_answer"] == "你叫小明。"
    system = captured[0][0]["content"]
    assert "## 用户记忆" in system and "小明" in system, "chitchat 路径记忆未注入（#11 根因未修）"


def test_memory_subagent_ran_no_double_recall(monkeypatch):
    """② plan 已跑 memory 子代理 → 不重复召回。"""
    captured = []
    _patch_llm_capture(monkeypatch, captured)
    calls = {"n": 0}

    async def _fake_recall(user_id, query, top_k=3, **kw):
        calls["n"] += 1
        return []

    from app.ai.memory import service as mem_service

    monkeypatch.setattr(mem_service, "recall_topk", _fake_recall)

    state = _state(subagent_results=[{"subagent": "memory", "summary": "用户名叫小明", "artifact_ref": "", "summary_tokens": 10}],
                   merged_context="## 记忆\n用户名叫小明")

    async def _run():
        return await SixNodeHarness().answer(state)

    asyncio.run(_run())
    assert calls["n"] == 0, "已跑 memory 子代理时不应重复召回"
    system = captured[0][0]["content"]
    assert "小明" in system  # 来自已有 merged_context


def test_recall_miss_answer_still_works(monkeypatch):
    """③ 记忆空召回 → 注入跳过，回答正常（不注入空标题）。"""
    captured = []
    _patch_llm_capture(monkeypatch, captured)
    _patch_recall(monkeypatch, hits=0)

    async def _run():
        return await SixNodeHarness().answer(_state())

    asyncio.run(_run())
    system = captured[0][0]["content"]
    assert "## 用户记忆" not in system


def test_recall_failure_does_not_break_answer(monkeypatch):
    """④ 召回抛异常 → 降级跳过，回答主链不受影响。"""
    captured = []
    _patch_llm_capture(monkeypatch, captured)

    async def _boom(user_id, query, top_k=3, **kw):
        raise RuntimeError("vector store down")

    from app.ai.memory import service as mem_service

    monkeypatch.setattr(mem_service, "recall_topk", _boom)

    async def _run():
        return await SixNodeHarness().answer(_state())

    out = asyncio.run(_run())
    assert out["final_answer"] == "你叫小明。"
