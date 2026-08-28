# -*- coding: utf-8 -*-
"""task-A1 契约测试：可插拔 Harness 抽象（替代硬编码 6 节点图）。

AC1 接口抽象：Harness 含 route/plan/fan_out/merge/reflect/answer 六抽象方法，签名一致。
AC2 默认实现等价：HARNESS_IMPL=sixnode，行为与重构前零差异（路由 + 并行 fan-out + 真实 user_id）。
AC3 可插拔：注册自定义 mock harness，HARNESS_IMPL 切换编译图，拓扑不变、节点走新实现。
AC4 R8 裁定保留：默认仍为 6 节点 DAG（keep_sixnode），拓扑锁定。
AC5 回归：scripts/eval/harnesses.py 三套 harness（sixnode/baseline/loop）接口不因 A1 断裂。

注：task24 全量契约回归（含 durable execution）在本文件外单独运行，见完工报告。
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from app.ai import graph as graph_mod
from app.ai.harness.base import Harness
from app.ai.harness.registry import (
    HARNESS_IMPLEMENTATIONS,
    build_harness,
    register_harness,
)


# ============================================================
# 拓扑签名工具（节点名 + 显式边；条件边在 branches 单独校验）
# ============================================================
def _topo_sig(g):
    nodes = tuple(sorted(g.nodes.keys()))
    edges = []
    for e in g.edges:
        if isinstance(e, tuple) and len(e) >= 2:
            edges.append((e[0], e[1]))
        else:
            edges.append((getattr(e, "source"), getattr(e, "target")))
    return (nodes, tuple(sorted(edges)))


# ============================================================
# AC1 接口抽象
# ============================================================
class TestAC1Interface:
    def test_six_abstract_methods_present(self):
        for m in ("route", "plan", "fan_out", "merge", "reflect", "answer"):
            assert hasattr(Harness, m), f"Harness 缺抽象方法 {m}"
            assert getattr(Harness, m).__isabstractmethod__, f"{m} 必须是 @abstractmethod"

    def test_signatures_consistent_with_nodes(self):
        # 与现有 graph.py 节点函数一致：(state) -> dict，且为 async
        for m in ("route", "plan", "fan_out", "merge", "reflect", "answer"):
            fn = getattr(Harness, m)
            sig = inspect.signature(fn)
            assert list(sig.parameters.keys()) == ["self", "state"], f"{m} 签名应为 (self, state)：{sig}"
            assert inspect.iscoroutinefunction(fn), f"{m} 必须是 async 方法（对齐现有节点）"

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            Harness()


# ============================================================
# AC4 R8 裁定保留：默认仍 6 节点 DAG（keep_sixnode）
# ============================================================
class TestAC4KeepSixnode:
    def test_default_impl_is_sixnode(self):
        from app.config import settings

        assert settings.HARNESS_IMPL == "sixnode"
        assert HARNESS_IMPLEMENTATIONS.get("sixnode") is not None

    def test_default_topology_locked(self):
        g = graph_mod.build_graph()  # 默认 harness，未编译
        nodes, edges = _topo_sig(g)
        expected_nodes = (
            "answer", "compact", "context_edit", "fan_out",
            "merge", "plan", "reflect", "route", "skill",
        )
        assert nodes == expected_nodes, f"默认节点集应为 keep_sixnode 9 节点：{nodes}"
        expected_edges = (
            ("__start__", "route"),
            ("answer", "__end__"),
            ("compact", "context_edit"),
            ("context_edit", "plan"),
            ("fan_out", "merge"),
            ("merge", "reflect"),
            ("plan", "fan_out"),
            ("skill", "compact"),
        )
        assert edges == expected_edges, f"默认边集应为 keep_sixnode 拓扑：{edges}"
        # 条件边：route_gate / reflect_gate 两条分支保留
        assert set(g.branches.keys()) == {"route", "reflect"}, f"条件分支应仅 route/reflect：{set(g.branches.keys())}"


# ============================================================
# AC2 默认实现等价（与重构前零差异）
# ============================================================
def _install_fake_llm(monkeypatch, *, intent="knowledge", answer="现在完成时详解"):
    async def fake_llm(messages, *, model, temperature=0.0, max_tokens=500, timeout=60.0):
        sys_p = messages[0]["content"] if messages else ""
        user = messages[-1]["content"] if messages else ""
        if "意图路由器" in sys_p:
            return f'{{"intent": "{intent}"}}'
        if "质检员" in sys_p:
            return '{"sufficient": true}'
        if "现在完成时" in user:
            return answer
        return "兜底最终回答"

    monkeypatch.setattr(graph_mod, "_llm_call", fake_llm)


def _install_fake_run_subagents(monkeypatch, captured=None):
    class _FakeResult:
        def __init__(self, task):
            self.task = task
            self.ok = True
            self.turns = 1
            self.tool_calls = 0
            self.summary_tokens = 3

        def as_distilled(self):
            return {
                "subagent": self.task.subagent,
                "summary": f"{self.task.subagent} 结果",
                "artifact_ref": "art:x",
                "summary_tokens": 3,
            }

    async def fake_run(tasks, *, llm=None, summary_budget=None):
        if captured is not None:
            for t in tasks:
                captured.append({"user_id": t.user_id, "thread_id": t.thread_id, "subagent": t.subagent})

        async def _one(t):
            return _FakeResult(t)

        return list(await asyncio.gather(*[_one(t) for t in tasks]))

    monkeypatch.setattr(graph_mod, "run_subagents", fake_run)


class TestAC2DefaultEquivalent:
    @pytest.mark.asyncio
    async def test_knowledge_full_pipeline_zero_diff(self, monkeypatch):
        _install_fake_llm(monkeypatch, intent="knowledge", answer="现在完成时详解")
        captured: list = []
        _install_fake_run_subagents(monkeypatch, captured=captured)

        g = graph_mod.compile_graph()  # 默认 sixnode harness
        st = graph_mod._empty_state("现在完成时和过去时区别", user_id=42, session_id=None)
        final = await g.ainvoke(st, {"configurable": {"thread_id": "a1-ac2-k1"}})

        executed = final["nodes_executed"]
        for exp in ("route", "plan", "fan_out", "merge", "reflect", "answer"):
            assert exp in executed, f"knowledge 应经过 {exp}: {executed}"
        assert final["intent"] == "knowledge"
        assert final["effort"] in ("L1", "L2")
        assert final["subagent_results"], "knowledge 应产出子代理摘要"
        assert final["final_answer"] == "现在完成时详解"

    @pytest.mark.asyncio
    async def test_real_user_id_in_subagents(self, monkeypatch):
        _install_fake_llm(monkeypatch, intent="knowledge")
        captured: list = []
        _install_fake_run_subagents(monkeypatch, captured=captured)

        g = graph_mod.compile_graph()
        st = graph_mod._empty_state("现在完成时", user_id=5555, session_id="sess-9")
        final = await g.ainvoke(st, {"configurable": {"thread_id": "a1-ac2-u1"}})
        assert final["intent"] == "knowledge"
        assert captured, "fan_out 应构建 SubagentTask"
        for c in captured:
            assert c["user_id"] == 5555, f"子代理 user_id 应=5555，实得 {c['user_id']}"
            assert c["thread_id"] == "sess-9", f"子代理 thread_id 应=sess-9，实得 {c['thread_id']}"

    @pytest.mark.asyncio
    async def test_chitchat_direct_answer(self, monkeypatch):
        _install_fake_llm(monkeypatch, intent="chitchat", answer="闲聊回答")
        _install_fake_run_subagents(monkeypatch)

        g = graph_mod.compile_graph()
        st = graph_mod._empty_state("你好，你是谁", user_id=42, session_id=None)
        final = await g.ainvoke(st, {"configurable": {"thread_id": "a1-ac2-c1"}})
        executed = final["nodes_executed"]
        assert final["intent"] == "chitchat"
        assert "route" in executed and "answer" in executed
        assert "plan" not in executed and "fan_out" not in executed, f"chitchat 不应走 plan/fan_out: {executed}"


# ============================================================
# AC3 可插拔：注册 mock harness → 切换编译 → 拓扑不变 + 节点走新实现
# ============================================================
class _MockHarness(Harness):
    def __init__(self):
        self.calls: list[str] = []

    async def route(self, state):
        self.calls.append("route")
        return {"intent": "knowledge", "effort": "L1"} | graph_mod._record(state, "route")

    async def plan(self, state):
        self.calls.append("plan")
        return {"tasks": [], "effort": "L1"} | graph_mod._record(state, "plan")

    async def fan_out(self, state):
        self.calls.append("fan_out")
        return {"subagent_results": [], "degraded_reason": None} | graph_mod._record(state, "fan_out")

    async def merge(self, state):
        self.calls.append("merge")
        return {"merged_context": "(mock)"} | graph_mod._record(state, "merge")

    async def reflect(self, state):
        self.calls.append("reflect")
        rc = int(state.get("reflect_count", 0)) + 1
        return {"reflect_count": rc, "sufficient": True, "degraded_reason": None} | graph_mod._record(state, "reflect")

    async def answer(self, state):
        self.calls.append("answer")
        return {"final_answer": "MOCK", "degraded_reason": None} | graph_mod._record(state, "answer")


def _noop_node(state):
    return {}


class TestAC3Pluggable:
    @pytest.mark.asyncio
    async def test_mock_topology_unchanged_and_wired(self, monkeypatch):
        # 隔离支持节点（skill/compact/context_edit），专注验证六核心走 mock
        monkeypatch.setattr(graph_mod, "skill_node", _noop_node)
        monkeypatch.setattr(graph_mod, "compact_node", _noop_node)
        monkeypatch.setattr(graph_mod, "context_edit_node", _noop_node)

        g_default_sg = graph_mod.build_graph()  # 默认 sixnode（未编译，用于拓扑比对）
        mock = _MockHarness()
        g_mock_sg = graph_mod.build_graph(harness=mock)

        # 拓扑不变（节点名 + 边完全一致）
        assert _topo_sig(g_default_sg) == _topo_sig(g_mock_sg), "切换 harness 后图拓扑必须不变"

        g_mock = g_mock_sg.compile()
        st = graph_mod._empty_state("任意问题", user_id=7, session_id=None)
        final = await g_mock.ainvoke(st, {"configurable": {"thread_id": "a1-ac3-1"}})

        assert set(mock.calls) == {"route", "plan", "fan_out", "merge", "reflect", "answer"}, \
            f"六核心应全被 mock 执行：{mock.calls}"
        assert final["final_answer"] == "MOCK"

    @pytest.mark.asyncio
    async def test_registry_switch_via_build_harness(self, monkeypatch):
        monkeypatch.setattr(graph_mod, "skill_node", _noop_node)
        monkeypatch.setattr(graph_mod, "compact_node", _noop_node)
        monkeypatch.setattr(graph_mod, "context_edit_node", _noop_node)

        register_harness("mock_a1", _MockHarness)
        assert "mock_a1" in HARNESS_IMPLEMENTATIONS

        h = build_harness("mock_a1")
        assert isinstance(h, _MockHarness)

        g_default_sg = graph_mod.build_graph()
        g_sg = graph_mod.build_graph(harness=h)
        assert _topo_sig(g_sg) == _topo_sig(g_default_sg), "registry 切换后拓扑不变"

        g = g_sg.compile()
        st = graph_mod._empty_state("x", user_id=1, session_id=None)
        final = await g.ainvoke(st, {"configurable": {"thread_id": "a1-ac3-2"}})
        assert final["final_answer"] == "MOCK"


# ============================================================
# AC5 回归：scripts/eval/harnesses.py 三套 harness 接口不因 A1 断裂
# ============================================================
class TestAC5EvalHarness:
    @pytest.mark.asyncio
    async def test_run_sixnode_still_works(self, monkeypatch):
        # 注意：scripts/eval/harnesses.run_sixnode 内部用 LLMRecorder 包裹 graph._llm_call
        # → 真实调用 scripts.eval.llm_client.call。因此伪造 llm_client.call（而非 graph._llm_call）。
        def fake_call(messages, *, model, temperature=0.0, max_tokens=500, timeout=60.0):
            sys_p = messages[0]["content"] if messages else ""
            user = messages[-1]["content"] if messages else ""
            if "意图路由器" in sys_p:
                text = '{"intent": "knowledge"}'
            elif "质检员" in sys_p:
                text = '{"sufficient": true}'
            elif "现在完成时" in user:
                text = "现在完成时详解"
            else:
                text = "兜底"
            return {
                "text": text,
                "usage": {
                    "prompt_tokens": 1, "completion_tokens": 1,
                    "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 1,
                },
            }

        monkeypatch.setattr("scripts.eval.llm_client.call", fake_call)
        # 子代理 runner 也走伪造，避免真实子代理 LLM 调用
        async def fake_run(tasks, *, llm=None, summary_budget=None):
            class _R:
                def __init__(self, t):
                    self.task = t
                    self.ok = True
                    self.turns = 1
                    self.tool_calls = 0
                    self.summary_tokens = 3

                def as_distilled(self):
                    return {"subagent": self.task.subagent, "summary": f"{self.task.subagent} 结果",
                            "artifact_ref": "art:x", "summary_tokens": 3}

            async def _one(t):
                return _R(t)

            return list(await asyncio.gather(*[_one(t) for t in tasks]))

        monkeypatch.setattr(graph_mod, "run_subagents", fake_run)
        # 隔离 Redis（环境不可达时避免 10s 超时），降级不影响 eval harness 接口验证
        async def _noop_init_redis(*a, **k):
            return None

        monkeypatch.setattr("app.database.init_redis", _noop_init_redis)
        monkeypatch.setattr(graph_mod, "_make_checkpointer", lambda: None)
        # 重置 graph 单例缓存，确保用默认 sixnode harness 重新编译
        graph_mod._agent_graph = None

        from scripts.eval import harnesses

        class _Sample:
            id = "a1-ac5"
            query = "现在完成时和过去时区别"

        res = await harnesses.run_sixnode(_Sample())
        assert isinstance(res, harnesses.HarnessResult)
        assert res.answer == "现在完成时详解", f"eval sixnode 应产出答案：{res.answer!r}"
        assert res.intent == "knowledge"
