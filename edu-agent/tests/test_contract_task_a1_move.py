# -*- coding: utf-8 -*-
"""task-A1-② 真搬迁契约：节点逻辑已迁入 SixNodeHarness，graph.py 退化为薄壳 + 构建器。

AC-A1-②-1 真实逻辑在位：直接调用 SixNodeHarness.route/plan/... 产出正确编排结果
          （逻辑真正搬迁进 harness，而非仅委托 graph.<node>）。
AC-A1-②-2 monkeypatch 红线保留：默认 build_graph 仍接线模块级 graph.<node> 名，
          test_contract_task24 对 graph.answer_node 等的 monkeypatch 继续生效。
AC-A1-②-3 自定义 harness 走闭包：build_graph(harness=mock) 后，graph.<node> 直接调用仍走默认 harness，
          无状态串扰（保证 test_contract_task94/97 直调契约稳定）。
"""
from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import HumanMessage

from app.ai import graph as graph_mod
from app.ai.harness.base import Harness
from app.ai.harness.sixnode import SixNodeHarness


class TestRealMoveLogicInHarness:
    def test_plan_embeds_skill_guidance(self):
        """plan 真实逻辑在 harness 内：tool 意图 + skill_context → L2 + 子代理任务含 skill 指引。"""
        h = SixNodeHarness()
        state = {
            "messages": [HumanMessage(content="q")],
            "intent": "tool",
            "skill_context": "[skill:audit]\n审计步骤：1) 检查输入校验",
            "context_edit": None,
            "nodes_executed": [],
        }
        res = asyncio.run(h.plan(state))
        assert res["effort"] == "L2", "tool 应为 L2"
        assert res["tasks"], "应产出子代理任务"
        for t in res["tasks"]:
            assert "skill 指引" in t["input"] and "审计步骤" in t["input"]
        assert "plan" in res["nodes_executed"]

    def test_route_parses_intent_via_shared_llm(self, monkeypatch):
        """route 真实逻辑在 harness 内，且通过 _graph._llm_call 调用时查表复用 graph 的共享原语
        （monkeypatch graph._llm_call 依然生效）。"""

        async def fake_llm(messages, **kw):
            return '{"intent": "knowledge"}'

        monkeypatch.setattr(graph_mod, "_llm_call", fake_llm)
        h = SixNodeHarness()
        state = {
            "messages": [HumanMessage(content="现在完成时")],
            "nodes_executed": [],
        }
        res = asyncio.run(h.route(state))
        assert res["intent"] == "knowledge"
        assert res["effort"] == "L1"
        assert "route" in res["nodes_executed"]


class TestMonkeypatchRedLine:
    @pytest.mark.asyncio
    async def test_patched_answer_node_fires_in_default_build(self, monkeypatch):
        """红线：默认 build_graph 仍接线模块级 graph.answer_node，monkeypatch 后由 patched 接管。"""
        called = {"n": 0}

        async def patched_answer(state):
            called["n"] += 1
            return {"final_answer": "PATCHED", "degraded_reason": None} | graph_mod._record(state, "answer")

        async def fake_llm(messages, **kw):
            return '{"intent": "chitchat"}'

        # 在 build 之前替换模块级函数 → 编译图必须接线 patched 版本
        monkeypatch.setattr(graph_mod, "answer_node", patched_answer)
        monkeypatch.setattr(graph_mod, "_llm_call", fake_llm)

        g = graph_mod.compile_graph()
        st = graph_mod._empty_state("你好", user_id=42, session_id=None)
        final = await g.ainvoke(st, {"configurable": {"thread_id": "a1-move-redline"}})
        assert called["n"] >= 1, "patched answer_node 必须被编译图调用（红线）"
        assert final["final_answer"] == "PATCHED"
        assert final["intent"] == "chitchat"


class TestCustomHarnessNoPollution:
    def test_custom_harness_does_not_pollute_direct_calls(self, monkeypatch):
        """build_graph(harness=mock) 用闭包捕获 mock；但 graph.<node> 直接调用仍走默认 sixnode。"""

        class _Mock(Harness):
            async def route(self, s):
                return {"intent": "knowledge", "effort": "L1"} | graph_mod._record(s, "route")

            async def plan(self, s):
                return {"tasks": [], "effort": "L1"} | graph_mod._record(s, "plan")

            async def fan_out(self, s):
                return {"subagent_results": [], "degraded_reason": None} | graph_mod._record(s, "fan_out")

            async def merge(self, s):
                return {"merged_context": "(mock)"} | graph_mod._record(s, "merge")

            async def reflect(self, s):
                return {"reflect_count": 1, "sufficient": True, "degraded_reason": None} | graph_mod._record(s, "reflect")

            async def answer(self, s):
                return {"final_answer": "MOCK", "degraded_reason": None} | graph_mod._record(s, "answer")

        monkeypatch.setattr(graph_mod, "skill_node", lambda s: {})
        monkeypatch.setattr(graph_mod, "compact_node", lambda s: {})
        monkeypatch.setattr(graph_mod, "context_edit_node", lambda s: {})

        graph_mod.build_graph(harness=_Mock())

        # 直接调用模块级 graph.plan_node 应仍走默认 sixnode（不污染）
        state = {
            "messages": [HumanMessage(content="q")],
            "intent": "tool",
            "skill_context": "",
            "context_edit": None,
            "nodes_executed": [],
        }
        res = asyncio.run(graph_mod.plan_node(state))
        assert res["effort"] == "L2", "直接调用 graph.plan_node 不应被自定义 mock 污染"
        assert res["tasks"], "应为真实 tool 子代理任务"
