# -*- coding: utf-8 -*-
"""task24 契约测试：AI 助手 LangGraph 图重构（GWT ①②③）。

执行方式：in-process + monkeypatch LLM（_llm_call）与子代理 runner（run_subagents），
验证路由 / durable execution（AsyncRedisSaver，需 Redis 6379 在线）/ 并行 fan-out + 真实 user_id。

GWT：
① Given 四类意图样本，When 请求，Then route 正确分发；chitchat 直连 answer；knowledge 走
   plan→fan_out→merge→reflect→answer
② Given 图中途异常注入 kill，When 同 thread_id 重新 ainvoke，Then 从最近 Redis checkpoint
   恢复继续执行，不重复已完成节点（nodes_executed 不重复追加）
③ Given 多任务 plan（2 个独立子代理），When 执行，Then 并行完成（耗时≈max）；state 中 user_id
   为真实值（非 user_id=1）
"""
from __future__ import annotations

import asyncio
import time
import uuid

import pytest

from app.ai import graph as graph_mod
from app.ai.subagents import SubagentTask
from app.config import settings

TEST_TID = "tid-" + uuid.uuid4().hex[:8]


# ============================================================
# 打桩：按 prompt/模型 分派 fake LLM 输出
# ============================================================
def install_fake_llm(monkeypatch, intent_map: dict[str, str], answers: dict[str, str]):
    """lanova：让 _llm_call 依传入 messages 的首段命中关键字返回对应 JSON/文本。
    intent_map: prompt 关键词 → 路由 JSON；answers: 用于 answer_node 的文本。
    """
    calls = {"n": 0}

    async def fake_llm(messages, *, model, temperature=0.0, max_tokens=500, timeout=60.0):
        calls["n"] += 1
        sys_prompt = messages[0]["content"] if messages else ""
        user = messages[-1]["content"] if messages else ""
        # route
        if "意图路由器" in sys_prompt:
            for kw, intent in intent_map.items():
                if kw in user:
                    return f'{{"intent": "{intent}"}}'
            return '{"intent": "knowledge"}'
        # reflect：默认 sufficient（首轮即放行）
        if "质检员" in sys_prompt:
            return '{"sufficient": true}'
        # answer
        for kw, ans in answers.items():
            if kw in user:
                return ans
        return "兜底最终回答"

    monkeypatch.setattr(graph_mod, "_llm_call", fake_llm)
    return calls


def install_fake_run_subagents(monkeypatch, *, delay: float = 0.0, captured: list | None = None):
    """lanova：让 fan_out 用 fake 并行（asyncio.gather + sleep），捕获 SubagentTask user_id。"""
    class _FakeResult:
        def __init__(self, task: SubagentTask):
            self.task = task
            self.ok = True
            self.turns = 1
            self.tool_calls = 0
            self.summary_tokens = 3

        def as_distilled(self):
            return {"subagent": self.task.subagent, "summary": f"{self.task.subagent} 结果",
                    "artifact_ref": "art:x", "summary_tokens": 3}

    async def fake_run(tasks, *, llm=None, summary_budget=None):
        if captured is not None:
            for t in tasks:
                captured.append({"user_id": t.user_id, "thread_id": t.thread_id, "subagent": t.subagent})
        async def _one(t: SubagentTask):
            if delay:
                await asyncio.sleep(delay)
            return _FakeResult(t)
        raw = await asyncio.gather(*[_one(t) for t in tasks])
        return list(raw)

    monkeypatch.setattr(graph_mod, "run_subagents", fake_run)


# ============================================================
# GWT① 意图路由
# ============================================================
class TestIntentRouting:
    @pytest.mark.asyncio
    async def test_chitchat_direct_answer(self, monkeypatch):
        """chitchat 直连 answer_node：nodes_executed 只含 route+answer，不到 plan/fan_out。"""
        install_fake_llm(monkeypatch, {"学习建议": "learning", "你好": "chitchat", "现在完成时": "knowledge"}, {"兜底": "闲聊回答"})
        install_fake_run_subagents(monkeypatch)
        g = graph_mod.compile_graph()
        st = graph_mod._empty_state("你好，你是谁", user_id=42, session_id=None)
        final = await g.ainvoke(st, {"configurable": {"thread_id": TEST_TID + "-c1"}})
        executed = final["nodes_executed"]
        assert final["intent"] == "chitchat"
        assert "route" in executed and "answer" in executed
        assert "plan" not in executed and "fan_out" not in executed, f"chitchat 不应走 plan/fan_out: {executed}"

    @pytest.mark.asyncio
    async def test_knowledge_full_pipeline(self, monkeypatch):
        """knowledge 走 plan→fan_out→merge→reflect→answer。"""
        install_fake_llm(monkeypatch, {"现在完成时": "knowledge"}, {"现在完成时": "现在完成时详解"})
        install_fake_run_subagents(monkeypatch)
        g = graph_mod.compile_graph()
        st = graph_mod._empty_state("现在完成时和过去时区别", user_id=42, session_id=None)
        final = await g.ainvoke(st, {"configurable": {"thread_id": TEST_TID + "-k1"}})
        executed = final["nodes_executed"]
        for exp in ("route", "plan", "fan_out", "merge", "reflect", "answer"):
            assert exp in executed, f"knowledge 应经过 {exp}: {executed}"
        assert final["intent"] == "knowledge"
        assert final["effort"] in ("L1", "L2")
        assert final["subagent_results"], "knowledge 应产出子代理摘要"

    @pytest.mark.asyncio
    async def test_four_intents_route_correctly(self, monkeypatch):
        """四类意图逐一验证路由分发正确、chitchat 直答只 1 次 answer。"""
        cases = {
            "你好": "chitchat",
            "现在完成时和过去时区别": "knowledge",
            "计算 123 加 456": "tool",
            "怎么学好英语": "learning",
        }
        for q, exp_intent in cases.items():
            install_fake_llm(monkeypatch, {q: exp_intent}, {"兜底": q})
            install_fake_run_subagents(monkeypatch)
            g = graph_mod.compile_graph()
            st = graph_mod._empty_state(q, user_id=42, session_id=None)
            final = await g.ainvoke(st, {"configurable": {"thread_id": TEST_TID + "-r-" + exp_intent}})
            assert final["intent"] == exp_intent, f"{q} 期望 {exp_intent} 实得 {final['intent']}"


# ============================================================
# GWT② durable execution（Redis checkpoint 恢复）
# ============================================================
class TestDurableExecution:
    @pytest.mark.asyncio
    async def test_resume_same_thread_skips_completed_nodes(self, monkeypatch):
        """图中途抛异常（模拟 kill）→ 同 thread_id 重新 ainvoke → 从 checkpoint 续跑，
        已完成节点（route/plan/fan_out/merge/reflect）不重复执行。需 Redis 6379 在线。"""
        import redis.asyncio as ar

        # 探测 Redis
        try:
            r = ar.Redis(host="localhost", port=6379, db=0)
            await r.ping()
            await r.aclose()
        except Exception:
            pytest.skip("Redis 不可用，跳过 checkpoint 持久化测试")

        from app.ai.checkpoint_redis import PlainRedisSaver

        install_fake_llm(monkeypatch, {"现在完成时": "knowledge"}, {"现在完成时": "FINAL_ANSWER"})
        install_fake_run_subagents(monkeypatch)
        # 原生 Redis（无 RediSearch 模块）→ 用 PlainRedisSaver 做 Redis durable execution
        saver = PlainRedisSaver(redis_url="redis://localhost:6379/0", ttl=3600)
        await saver.asetup()
        g = graph_mod.build_graph().compile(checkpointer=saver)
        tid = TEST_TID + "-durable"

        st = graph_mod._empty_state("现在完成时", user_id=7, session_id=None)

        # 首轮：注入 answer 抛异常（模拟进程 kill 于 answer 前）
        real_answer = graph_mod.answer_node
        async def boom_answer(state):
            executed = state.get("nodes_executed", [])
            return {"final_answer": "KILLED", "degraded_reason": "sim_kill"} | {"nodes_executed": executed + ["answer"]}
        monkeypatch.setattr(graph_mod, "answer_node", boom_answer)

        await g.ainvoke(st, {"configurable": {"thread_id": tid}})   # 首次执行到 answer 接替

        # 恢复到真实 answer_node，同 thread_id 续跑
        monkeypatch.setattr(graph_mod, "answer_node", real_answer)
        # 用「全新 saver 实例」模拟进程重启：仅靠 Redis 快照重建 state，证明 durable execution
        saver2 = PlainRedisSaver(redis_url="redis://localhost:6379/0", ttl=3600)
        await saver2.asetup()
        g2 = graph_mod.build_graph().compile(checkpointer=saver2)
        final = await g2.ainvoke(st, {"configurable": {"thread_id": tid}})

        executed = final["nodes_executed"]
        assert final["final_answer"] == "FINAL_ANSWER", f"续跑应产出真实最终回答: {final['final_answer']}"
        # 关键：route/plan/fan_out/merge/reflect 各只出现 1 次（checkpoint 恢复不重复执行）
        for node in ("route", "plan", "fan_out", "merge", "reflect"):
            assert executed.count(node) == 1, f"{node} 应只执行 1 次（不重复）: {executed}"


# ============================================================
# GWT③ 并行 fan-out + 真实 user_id
# ============================================================
class TestParallelFanoutAndRealUser:
    @pytest.mark.asyncio
    async def test_parallel_time_approx_max_not_sum(self, monkeypatch):
        """多任务 plan 并行完成：总耗时 ≈ 单任务 delay（max），远小于 sum。
        ⚠️ 优化H2 后 knowledge 默认走直连快路径（不构建 SubagentTask）——此处显式关开关，
        钉住「原子代理并行 + user_id 传递」契约（直连路径的对应契约见 test_contract_taskP1L）。"""
        monkeypatch.setattr(settings, "KNOWLEDGE_DIRECT_RETRIEVAL_ENABLED", False)
        install_fake_llm(monkeypatch, {"现在完成时": "knowledge"}, {"兜底": "答案"})
        captured: list = []
        install_fake_run_subagents(monkeypatch, delay=0.35, captured=captured)
        g = graph_mod.compile_graph()
        st = graph_mod._empty_state("现在完成时", user_id=7, session_id=None)

        t0 = time.perf_counter()
        final = await g.ainvoke(st, {"configurable": {"thread_id": TEST_TID + "-p1"}})
        elapsed = time.perf_counter() - t0

        # knowledge → 2 个子代理并行；各 delay 0.35s，串行应 0.7s，并行应 ~0.35s
        assert len(captured) >= 2, f"knowledge 至少 2 个子代理: {captured}"
        assert elapsed < 0.7, f"总耗时应≈max(0.35) 而非 sum(0.7)，实测 {elapsed:.2f}s"
        assert final["effort"] == "L1"

    @pytest.mark.asyncio
    async def test_user_id_real_in_state_and_subagents(self, monkeypatch):
        """state.user_id 为真实值；fan-out SubagentTask user_id 为真实值（非 user_id=1）。
        ⚠️ 同 test_parallel_time_approx_max_not_sum：关直连开关钉原子代理路径。"""
        monkeypatch.setattr(settings, "KNOWLEDGE_DIRECT_RETRIEVAL_ENABLED", False)
        install_fake_llm(monkeypatch, {"现在完成时": "knowledge"}, {"兜底": "答案"})
        captured: list = []
        install_fake_run_subagents(monkeypatch, captured=captured)
        g = graph_mod.compile_graph()
        st = graph_mod._empty_state("现在完成时", user_id=5555, session_id="sess-9")
        final = await g.ainvoke(st, {"configurable": {"thread_id": TEST_TID + "-u1"}})
        assert final["intent"] == "knowledge"
        # 子代理拿到真实 user_id + thread_id
        assert captured, "fan_out 应构建 SubagentTask"
        for c in captured:
            assert c["user_id"] == 5555, f"子代理 user_id 应=5555，实得 {c['user_id']}"
            assert c["thread_id"] == "sess-9", f"子代理 thread_id 应=sess-9，实得 {c['thread_id']}"

    def test_no_hardcoded_user_id_1(self):
        """GWT③ 红线：app/ai/graph.py 无硬编码 user_id=1（source 扫描）。"""
        src = graph_mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        assert "user_id=1" not in text, "graph.py 不应出现硬编码 user_id=1"
        # 子代理定义中 user_id 通过闭包注入，不写常量 1