# -*- coding: utf-8 -*-
"""task-P1L 契约测试：LLM 档位延迟治理的三处优化（route 重试剪枝 / reflect 启发式先行 / 前缀填充）。

钉住的优化行为（相对 task39 基线的可验证差异）：
① route：LLM 异常 → 立即降级 knowledge **不再 3 连败**（原 for _ in range(3)，LLM 抖动 = 3 倍串行延迟）；
         输出不可解析 → 最多重试 1 次（共 2 次）。
② reflect：所有子代理均产出非空摘要 + 综合上下文非空 → 启发式 sufficient=true，**跳过 judge LLM**；
          上下文不足（空摘要/占位兜底）→ 才走 judge LLM 二次确认（保留「不足回 plan 补检索」能力）。
③ route / reflect judge 的 system 前缀经 ensure_min_prefix 撑到 ≥1024 token（火山 ark prompt cache 命中门槛）。

红线校验：节点拓扑不变（EXPECTED_SIXNODE_*）、chitchat 仍直连 answer、knowledge 仍走六节点全链路
（这些由 test_contract_task24 继续保证——本文件专注钉住三处**延迟行为**本身）。

执行方式：in-process + monkeypatch graph._llm_call 计数，不依赖 Redis/MySQL/Milvus。
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.ai import graph as graph_mod
from app.ai.compaction import estimate_tokens
from app.ai.harness.sixnode import SixNodeHarness
from app.config import settings


def _empty_state(**overrides) -> dict:
    q = overrides.pop("query", "现在完成时和过去时区别")
    st = graph_mod._empty_state(q, user_id=42, session_id=None)
    st.update(overrides)
    return st


class _CountingLLM:
    """按 prompt 分派的计数 fake：记录每次调用 (model, sys_prompt 首 20 字, user 首 30 字)。"""

    def __init__(self, monkeypatch):
        self.calls: list[dict] = []
        self.intent = "knowledge"
        self.sufficient = True
        self.fail_route = False  # route 调用直接抛异常

        async def fake(messages, *, model, temperature=0.0, max_tokens=500, timeout=60.0):
            sys_prompt = messages[0]["content"] if messages else ""
            user = messages[-1]["content"] if messages else ""
            self.calls.append({"model": model, "sys": sys_prompt[:20], "user": user[:30]})
            if "意图路由器" in sys_prompt:
                if self.fail_route:
                    raise RuntimeError("route LLM 宕机（sim）")
                return f'{{"intent": "{self.intent}"}}'
            if "质检员" in sys_prompt:
                return f'{{"sufficient": {"true" if self.sufficient else "false"}}}'
            return "最终回答"

        monkeypatch.setattr(graph_mod, "_llm_call", fake)


def _fake_run_subagents(monkeypatch, *, summaries: list[str] | None = None):
    """fan_out 打桩：返回指定摘要列表（None → 空列表）。"""
    from app.ai.subagents import SubagentTask

    summaries = summaries if summaries is not None else ["search 结果", "memory 结果"]

    class _FakeResult:
        def __init__(self, subagent: str, summary: str):
            self._s = subagent
            self._sm = summary
            self.ok = bool(summary.strip())

        def as_distilled(self):
            return {"subagent": self._s, "summary": self._sm, "artifact_ref": "art:x", "summary_tokens": 3}

    async def fake_run(tasks, *, llm=None, summary_budget=None):
        out = []
        for i, t in enumerate(tasks):
            sm = summaries[i] if i < len(summaries) else ""
            out.append(_FakeResult(t.subagent, sm))
        return out

    monkeypatch.setattr(graph_mod, "run_subagents", fake_run)


# ============================================================
# GWT① route 重试剪枝
#   ⚠️ 规则路由（优化H1）开启后 route 0-LLM 定档，不再触发 LLM —— 这些测试钉住的
#   「LLM 路由的鲁棒行为」现在只在 RULE_ROUTING_ENABLED=False 时生效，故显式关开关。
# ============================================================
class TestRouteRetryPruning:
    @pytest.mark.asyncio
    async def test_route_llm_exception_calls_once_then_degrade(self, monkeypatch):
        """LLM 异常 → 只调 1 次立即降级 knowledge（原实现 3 连败）。"""
        monkeypatch.setattr(settings, "RULE_ROUTING_ENABLED", False)  # 钉 LLM 路由兜底路径
        llm = _CountingLLM(monkeypatch)
        llm.fail_route = True
        h = SixNodeHarness()
        final = await h.route(_empty_state())
        assert final["intent"] == "knowledge"
        assert llm.calls, "route 至少调用 1 次"
        assert len(llm.calls) == 1, f"LLM 异常时不应重试（3 连败 → 3 倍串行延迟），实际 {len(llm.calls)} 次"

    @pytest.mark.asyncio
    async def test_route_unparseable_retries_at_most_once(self, monkeypatch):
        """输出不可解析 → 最多 2 次（重试 1 次）；解析成功即停。"""
        monkeypatch.setattr(settings, "RULE_ROUTING_ENABLED", False)  # 钉 LLM 路由兜底路径
        llm = _CountingLLM(monkeypatch)
        orig = graph_mod._extract_json

        def bad_extract(raw):
            return None  # 永远解析失败 → 触发重试

        monkeypatch.setattr(graph_mod, "_extract_json", bad_extract)
        h = SixNodeHarness()
        await h.route(_empty_state())
        # 解析失败 → 走满 attempts=2，不 3 连败
        assert len(llm.calls) == 2, f"不可解析最多重试 1 次（共 2 次），实际 {len(llm.calls)}"
        monkeypatch.setattr(graph_mod, "_extract_json", orig)

    @pytest.mark.asyncio
    async def test_route_success_single_call(self, monkeypatch):
        """正常解析 → 恰好 1 次调用（无多余重试）。"""
        monkeypatch.setattr(settings, "RULE_ROUTING_ENABLED", False)  # 钉 LLM 路由兜底路径
        llm = _CountingLLM(monkeypatch)
        h = SixNodeHarness()
        final = await h.route(_empty_state())
        assert final["intent"] == "knowledge"
        assert len(llm.calls) == 1, f"成功路径应恰好 1 次调用，实际 {len(llm.calls)}"


# ============================================================
# GWT② reflect 启发式先行
# ============================================================
class TestReflectHeuristicFirst:
    @pytest.mark.asyncio
    async def test_reflect_skips_judge_when_context_ready(self, monkeypatch):
        """子代理全部有摘要 + 上下文非空 → sufficient=true 且**不调 judge LLM**（主链路省 1 次串行调用）。"""
        llm = _CountingLLM(monkeypatch)
        _fake_run_subagents(monkeypatch, summaries=["search 结果", "memory 结果"])
        st = _empty_state(
            subagent_results=[
                {"subagent": "search", "summary": "search 结果", "artifact_ref": "a", "summary_tokens": 3},
                {"subagent": "memory", "summary": "memory 结果", "artifact_ref": "b", "summary_tokens": 3},
            ],
            merged_context="- [search] search 结果\n- [memory] memory 结果",
        )
        h = SixNodeHarness()
        final = await h.reflect(st)
        assert final["sufficient"] is True
        assert final["reflect_count"] == 1
        assert "reflect" in final["nodes_executed"], "reflect 节点仍须记录（契约 test_contract_task24 红线）"
        # judge 被跳过 → 只有 route 的调用（reflect 测试前无 route，此处 0 次）
        assert llm.calls == [], f"上下文充足时不应调 judge LLM，实际调用 {len(llm.calls)}"

    @pytest.mark.asyncio
    async def test_reflect_calls_judge_when_summary_missing(self, monkeypatch):
        """子代理空摘要 → 走 judge LLM 二次确认（保留补检索能力）。"""
        llm = _CountingLLM(monkeypatch)
        _fake_run_subagents(monkeypatch, summaries=["", "memory 结果"])
        st = _empty_state(
            subagent_results=[
                {"subagent": "search", "summary": "", "artifact_ref": "a", "summary_tokens": 0},
                {"subagent": "memory", "summary": "memory 结果", "artifact_ref": "b", "summary_tokens": 3},
            ],
            merged_context="- [memory] memory 结果",
        )
        h = SixNodeHarness()
        final = await h.reflect(st)
        assert final["sufficient"] is True  # fake judge 默认 true → 放行
        assert any("质检员" in c["sys"] for c in llm.calls), f"上下文不足时应调 judge，实际 {llm.calls}"

    @pytest.mark.asyncio
    async def test_reflect_calls_judge_when_placeholder_context(self, monkeypatch):
        """merged_context 为兜底占位 → 判定上下文不足 → 走 judge。"""
        llm = _CountingLLM(monkeypatch)
        st = _empty_state(
            subagent_results=[{"subagent": "search", "summary": "x", "artifact_ref": "a", "summary_tokens": 3}],
            merged_context="（子代理未产出有效摘要）",
        )
        h = SixNodeHarness()
        await h.reflect(st)
        assert any("质检员" in c["sys"] for c in llm.calls), "占位上下文应触发 judge 兜底"

    @pytest.mark.asyncio
    async def test_reflect_judge_false_still_returns_false(self, monkeypatch):
        """judge 返回 false → 仍可回 plan（sufficient=false 传播），质量兜底未被启发式短路。"""
        llm = _CountingLLM(monkeypatch)
        llm.sufficient = False
        st = _empty_state(
            subagent_results=[{"subagent": "search", "summary": "", "artifact_ref": "a", "summary_tokens": 0}],
            merged_context="",
        )
        h = SixNodeHarness()
        final = await h.reflect(st)
        assert final["sufficient"] is False, "judge false 必须传播（可触发 reflect→plan 补检索）"


# ============================================================
# GWT③ 前缀填充（prompt cache 门槛）
# ============================================================
class TestRoutePrefixCache:
    @pytest.mark.asyncio
    async def test_route_system_prefix_ge_2048_tokens(self, monkeypatch):
        """route 的 system 前缀经 ensure_min_prefix ≥2048 token（火山 ark 缓存按 2048 分块，
        2026-08-29 实测：1024 前缀 cached_tokens 恒为 0、2812 前缀命中 2048）。
        注：规则路由开启时 route 0-LLM 不触 LLM，此处钉「LLM 兜底路径」的前缀行为。"""
        monkeypatch.setattr(settings, "RULE_ROUTING_ENABLED", False)  # 钉 LLM 路由兜底路径
        captured: dict = {}

        async def fake(messages, *, model, temperature=0.0, max_tokens=500, timeout=60.0):
            captured["sys"] = messages[0]["content"]
            return '{"intent": "chitchat"}'

        monkeypatch.setattr(graph_mod, "_llm_call", fake)
        h = SixNodeHarness()
        final = await h.route(_empty_state())
        assert final["intent"] == "chitchat"
        sys_prompt = captured["sys"]
        assert "意图路由器" in sys_prompt, "填充不得改动原系统提示词（仅追加静态填充块）"
        assert estimate_tokens(sys_prompt) >= 2048, f"route 前缀应 ≥2048 token，实测 {estimate_tokens(sys_prompt)}"

    @pytest.mark.asyncio
    async def test_reflect_judge_prefix_ge_2048_tokens(self, monkeypatch):
        """reflect judge 的 system 前缀同样 ≥2048 token（异常路径调用时也能命中缓存）。"""
        captured: dict = {}

        async def fake(messages, *, model, temperature=0.0, max_tokens=500, timeout=60.0):
            captured["sys"] = messages[0]["content"]
            return '{"sufficient": true}'

        monkeypatch.setattr(graph_mod, "_llm_call", fake)
        st = _empty_state(
            subagent_results=[{"subagent": "search", "summary": "", "artifact_ref": "a", "summary_tokens": 0}],
            merged_context="",
        )
        h = SixNodeHarness()
        await h.reflect(st)
        sys_prompt = captured["sys"]
        assert "质检员" in sys_prompt
        assert estimate_tokens(sys_prompt) >= 2048, f"judge 前缀应 ≥2048 token，实测 {estimate_tokens(sys_prompt)}"

    @pytest.mark.asyncio
    async def test_route_prefix_deterministic_across_calls(self, monkeypatch):
        """前缀字节确定性：两次调用返回相同前缀（同缓存 key 才能命中）。"""
        monkeypatch.setattr(settings, "RULE_ROUTING_ENABLED", False)  # 钉 LLM 路由兜底路径
        seen: list[str] = []

        async def fake(messages, *, model, temperature=0.0, max_tokens=500, timeout=60.0):
            seen.append(messages[0]["content"])
            return '{"intent": "knowledge"}'

        monkeypatch.setattr(graph_mod, "_llm_call", fake)
        h = SixNodeHarness()
        await h.route(_empty_state())
        await h.route(_empty_state(query="另一个问题"))
        assert seen[0] == seen[1], "route 前缀必须逐字节一致（否则缓存永远 miss）"


# ============================================================
# GWT④ 拓扑锁定回归（改动不得触碰 task-A1 拓扑常量）
# ============================================================
class TestTopologyLocked:
    def test_sixnode_topology_constants_unchanged(self):
        """节点集 / 边集 / 分支集与 task-A1 锁定一致（优化只改节点内部行为，不改图结构）。"""
        assert graph_mod.EXPECTED_SIXNODE_NODES == (
            "answer", "compact", "context_edit", "fan_out",
            "merge", "plan", "reflect", "route", "skill",
        )
        # route→skill 是条件边（route_gate 的 plan 分支），只出现在 BRANCHES；静态 EDGES 不含
        assert ("route", "skill") not in graph_mod.EXPECTED_SIXNODE_EDGES
        assert set(graph_mod.EXPECTED_SIXNODE_BRANCHES) == {"route", "reflect"}


# ============================================================
# GWT⑤ 流式 agent 决策层导入回归（task39 遗留 NameError）
# ============================================================
class TestStreamAgentDecisionImport:
    def test_chat_stream_run_agent_turn_resolvable(self):
        """chat_stream 的 use_agent 分支调用 run_agent_turn —— 该符号必须可从
        app.chat.flows.agent 解析（task39 提交漏 import 导致每次流式请求抛
        NameError 回退检索先行，是 TTFT 基线虚高的直接原因）。"""
        import app.chat.service as svc
        from app.chat.flows.agent import run_agent_turn

        assert hasattr(svc, "run_agent_turn"), "service 命名空间缺少 run_agent_turn（NameError 回归）"
        assert svc.run_agent_turn is run_agent_turn, "run_agent_turn 必须来自 flows.agent（语义一致）"

    def test_chat_stream_agent_branch_references_resolvable_name(self):
        """chat_stream 源码中 use_agent 分支引用的全局名都必须在模块命名空间可解析——
        用 compile 静态扫描 Names 集合，钉住「调用存在但符号缺失」这一类缺陷。"""
        import app.chat.service as svc

        src = open(svc.__file__, encoding="utf-8").read()
        tree = compile(src, svc.__file__, "exec")
        ns = set(getattr(tree, "co_names", ()))
        # 仅检查 agent 决策分支使用的关键符号
        assert "run_agent_turn" in ns, "chat_stream 源码仍引用 run_agent_turn（NameError 回归）"
        assert hasattr(svc, "run_agent_turn")


# ============================================================
# GWT⑥ 优化H1：规则路由先行（0-LLM 决策）
# ============================================================
class TestRuleRoutingZeroLLM:
    """规则路由命中即 0 次 LLM 调用定档；未覆盖 → knowledge 0-LLM 兜底；
    RULE_ROUTING_ENABLED=False 才回退 LLM 路由（契约测试/异常回退开关）。"""

    @pytest.mark.asyncio
    async def test_rule_learning_zero_llm(self, monkeypatch):
        llm = _CountingLLM(monkeypatch)
        h = SixNodeHarness()
        final = await h.route(_empty_state(query="帮我制定一个 Python 学习计划"))
        assert final["intent"] == "learning"
        assert llm.calls == [], f"learning 规则命中应 0 LLM 调用，实际 {len(llm.calls)}"

    @pytest.mark.asyncio
    async def test_rule_tool_zero_llm(self, monkeypatch):
        llm = _CountingLLM(monkeypatch)
        h = SixNodeHarness()
        final = await h.route(_empty_state(query="帮我算一下 2+2"))
        assert final["intent"] == "tool"
        assert llm.calls == [], f"tool 规则命中应 0 LLM 调用，实际 {len(llm.calls)}"

    @pytest.mark.asyncio
    async def test_rule_chitchat_zero_llm_and_l0(self, monkeypatch):
        llm = _CountingLLM(monkeypatch)
        h = SixNodeHarness()
        final = await h.route(_empty_state(query="谢谢你"))
        assert final["intent"] == "chitchat"
        assert final["effort"] == "L0", "chitchat 规则命中应定档 L0（直连 answer）"
        assert llm.calls == [], f"chitchat 规则命中应 0 LLM 调用，实际 {len(llm.calls)}"

    @pytest.mark.asyncio
    async def test_rule_uncovered_defaults_knowledge_zero_llm(self, monkeypatch):
        """规则未覆盖样本（普通学科提问）→ knowledge 0-LLM 兜底（不做 LLM 路由）。"""
        llm = _CountingLLM(monkeypatch)
        h = SixNodeHarness()
        final = await h.route(_empty_state(query="什么是机器学习"))
        assert final["intent"] == "knowledge"
        assert final["effort"] == "L1"
        assert llm.calls == [], f"未覆盖样本应 knowledge 0-LLM 兜底，实际 {len(llm.calls)}"

    @pytest.mark.asyncio
    async def test_rule_disabled_falls_back_to_llm_routing(self, monkeypatch):
        """RULE_ROUTING_ENABLED=False → 回退 LLM 路由（覆盖缺失时的质量兜底）。"""
        monkeypatch.setattr(settings, "RULE_ROUTING_ENABLED", False)
        llm = _CountingLLM(monkeypatch)
        llm.intent = "tool"
        h = SixNodeHarness()
        final = await h.route(_empty_state(query="任意问题"))
        assert final["intent"] == "tool", "开关关闭后应走 LLM 路由"
        assert len(llm.calls) == 1

    def test_rule_router_four_intent_samples(self):
        """规则分类器四意图确定性（纯函数，无副作用）。"""
        from app.ai.rule_router import classify_intent

        assert classify_intent("怎么学好英语") == "learning"
        assert classify_intent("帮我算一下 1+1") == "tool"
        assert classify_intent("你好，你是谁") == "chitchat"
        # 未覆盖 → None（route 层兜底 knowledge），不误判为 chitchat
        assert classify_intent("你好，什么是机器学习？") is None
        assert classify_intent("什么是机器学习") is None


# ============================================================
# GWT⑦ 优化H2：knowledge 直连检索快路径（fan_out 0 子代理 LLM）
# ============================================================
class TestKnowledgeDirectRetrieval:
    """intent=knowledge + 开关开 → fan_out 直接三通道检索 + 记忆召回，构造 2 条蒸馏摘要，
    不构建 SubagentTask/不调 run_subagents；失败回退原子代理路径。"""

    @pytest.mark.asyncio
    async def test_fanout_direct_retrieval_builds_two_results(self, monkeypatch):
        from app.chat.retriever import RetrievalBundle, RetrievedDoc

        async def fake_retrieve(query, *, user_id, role, use_hyde, enable_graph, top_k, final_max_k, cutoff_drop_ratio):
            assert user_id == 42, "直连检索必须使用真实 user_id（R4 红线）"
            return RetrievalBundle(
                docs=[
                    RetrievedDoc(doc_id="d1", score=0.9, content="现在完成时结构 have+过去分词", source_file="grammar.md"),
                    RetrievedDoc(doc_id="d2", score=0.8, content="过去时标志词 yesterday", source_file="grammar.md"),
                ],
                raw_retrieved_count=2, graph_entities=[], rewrite_query=None,
            )

        async def fake_recall(user_id, query, top_k=3, **kw):
            assert user_id == 42
            return [{"content": "用户正在学 Python 基础"}]

        called: list = []

        async def fake_run_subagents(tasks, *, llm=None, summary_budget=None):
            called.append(len(tasks))  # 不应被调用
            return []

        monkeypatch.setattr("app.chat.retriever.retrieve_three_channel", fake_retrieve)
        monkeypatch.setattr(graph_mod, "run_subagents", fake_run_subagents)
        monkeypatch.setattr("app.ai.memory.service.recall_topk", fake_recall)
        h = SixNodeHarness()
        st = _empty_state(intent="knowledge")
        final = await h.fan_out(st)
        assert called == [], "直连快路径不应调 run_subagents"
        results = final["subagent_results"]
        assert len(results) == 2, f"直连应产出 search+memory 2 条结果，实际 {len(results)}"
        assert {r["subagent"] for r in results} == {"search", "memory"}
        search_summary = next(r["summary"] for r in results if r["subagent"] == "search")
        memory_summary = next(r["summary"] for r in results if r["subagent"] == "memory")
        assert "have+过去分词" in search_summary, "search 摘要应含检索内容"
        assert "Python 基础" in memory_summary, "memory 摘要应含召回记忆"
        assert final["degraded_reason"] is None

    @pytest.mark.asyncio
    async def test_fanout_falls_back_when_retrieve_fails(self, monkeypatch):
        async def boom(query, **kw):
            raise RuntimeError("Milvus 不可用（sim）")

        captured: list = []

        async def fake_run_subagents(tasks, *, llm=None, summary_budget=None):
            captured.append(len(tasks))
            from app.ai.subagents import SubagentResult

            return [SubagentResult(subagent="search", summary="回退摘要", artifact_ref="", ok=True)]

        monkeypatch.setattr("app.chat.retriever.retrieve_three_channel", boom)
        monkeypatch.setattr(graph_mod, "run_subagents", fake_run_subagents)
        h = SixNodeHarness()
        st = _empty_state(intent="knowledge")
        final = await h.fan_out(st)
        assert captured, "直连检索异常必须回退原子代理路径"
        assert final["subagent_results"][0]["summary"] == "回退摘要"

    @pytest.mark.asyncio
    async def test_fanout_uses_subagents_when_disabled(self, monkeypatch):
        monkeypatch.setattr(settings, "KNOWLEDGE_DIRECT_RETRIEVAL_ENABLED", False)
        captured: list = []

        async def fake_run_subagents(tasks, *, llm=None, summary_budget=None):
            captured.append(len(tasks))
            from app.ai.subagents import SubagentResult

            return [SubagentResult(subagent="search", summary="s", artifact_ref="", ok=True) for _ in tasks]

        monkeypatch.setattr(graph_mod, "run_subagents", fake_run_subagents)
        h = SixNodeHarness()
        st = _empty_state(intent="knowledge")
        final = await h.fan_out(st)
        assert captured, "开关关闭后应走原子代理路径"


# ============================================================
# GWT⑧ 优化H3：单工具确定性子代理 turn-1 预执行（runner 0 决策 LLM）
# ============================================================
class TestSubagentDirectPrefetch:
    """search/memory/learning 单工具子代理：turn-1 预执行唯一工具并把结果注入首轮 prompt，
    LLM 只做总结轮（2 次 → 1 次）；tool 子代理（call_tool 入参开放）不预执行。"""

    def test_search_subagent_prefetch_single_llm_turn(self):
        from app.ai.subagents.runner import run_subagent, get_subagent_spec

        spec = get_subagent_spec("search")
        seen_llm: list = []
        handler_calls: list = []

        async def handler(args=None):
            handler_calls.append(args)
            return {"docs": [{"id": 1, "content": "PREFETCHED_DOC"}]}

        async def llm(messages, model):
            seen_llm.append([dict(m) for m in messages])
            return json.dumps({"tool": None, "final": "预执行摘要"})

        async def go():
            return await run_subagent(
                spec, objective="检索目标", input_text="基于问题给出检索要点（问题：什么是机器学习）",
                tool_services={"search_knowledge": handler}, llm=llm,
            )

        r = asyncio.run(go())
        assert r.summary == "预执行摘要"
        assert len(seen_llm) == 1, f"预执行后 LLM 应只 1 次总结轮，实际 {len(seen_llm)}"
        assert len(handler_calls) == 1, f"工具应预执行 1 次，实际 {len(handler_calls)}"
        assert handler_calls[0] == {"q": "什么是机器学习"}, f"预执行入参应为查询词，实际 {handler_calls[0]}"
        # 首轮 prompt 含工具结果 → LLM 不必再决策
        first_user = "".join(m["content"] for m in seen_llm[0] if m["role"] == "user")
        assert "已确定性预执行" in first_user and "PREFETCHED_DOC" in first_user

    def test_tool_subagent_not_prefetched(self):
        """tool 子代理（call_tool）不预执行：LLM 决策轮正常（2 次：决策+总结）。"""
        from app.ai.subagents.runner import run_subagent, get_subagent_spec

        spec = get_subagent_spec("tool")
        n = {"v": 0}
        seen_llm: list = []

        async def handler(args=None):
            return {"status": "SUCCESS", "result": "42"}

        async def llm(messages, model):
            n["v"] += 1
            seen_llm.append([dict(m) for m in messages])
            if n["v"] == 1:
                return json.dumps({"tool": "call_tool", "args": {"tool_name": "calc", "args": {"expr": "1+1"}}})
            return json.dumps({"tool": None, "final": "计算结果 2"})

        async def go():
            return await run_subagent(
                spec, objective="计算", input_text="计算 1+1（问题：计算 1+1）",
                tool_services={"call_tool": handler}, llm=llm,
            )

        r = asyncio.run(go())
        assert r.summary == "计算结果 2"
        assert n["v"] == 2, f"tool 子代理应保留 2 次 LLM（决策+总结），实际 {n['v']}"

    def test_prefetch_disabled_keeps_llm_decision(self, monkeypatch):
        from app.ai.subagents.runner import run_subagent, get_subagent_spec

        monkeypatch.setattr(settings, "SUBAGENT_DIRECT_TOOL_ENABLED", False)
        spec = get_subagent_spec("search")
        n = {"v": 0}

        async def handler(args=None):
            return {"docs": [{"id": 1, "content": "x"}]}

        async def llm(messages, model):
            n["v"] += 1
            if n["v"] == 1:
                return json.dumps({"tool": "search_knowledge", "args": {"q": "q"}})
            return json.dumps({"tool": None, "final": "决策摘要"})

        async def go():
            return await run_subagent(
                spec, objective="目标", input_text="查询（问题：查询）",
                tool_services={"search_knowledge": handler}, llm=llm,
            )

        r = asyncio.run(go())
        assert r.summary == "决策摘要"
        assert n["v"] == 2, f"开关关闭后应保留 LLM 决策轮（2 次），实际 {n['v']}"


# ============================================================
# GWT⑨ 优化H4：流式链路 decide_agent_plan 规则优先（0-LLM 决策）
# ============================================================
class TestAgentPlanRuleFirst:
    """decide_agent_plan：规则命中即 0 LLM 决策（chitchat → need_search=False；其余 → True），
    不触 specs_from_metas / LLM 决策；RULE_ROUTING_ENABLED=False 才回退 LLM。"""

    @pytest.mark.asyncio
    async def test_chitchat_no_search_no_llm(self, monkeypatch):
        import app.chat.flows.agent as agent_mod

        def boom(*a, **k):
            raise AssertionError("规则路径不应触 specs_from_metas")

        monkeypatch.setattr(agent_mod, "specs_from_metas", boom)
        plan = await agent_mod.decide_agent_plan("谢谢你")
        assert plan.need_search is False, "chitchat 应无需检索"
        assert plan.query_rewrite == "谢谢你"

    @pytest.mark.asyncio
    async def test_knowledge_need_search_rule_default(self, monkeypatch):
        import app.chat.flows.agent as agent_mod

        monkeypatch.setattr(agent_mod, "specs_from_metas", lambda m: [])
        plan = await agent_mod.decide_agent_plan("什么是机器学习")
        assert plan.need_search is True, "knowledge 应需检索"
        assert plan.query_rewrite == "什么是机器学习"

    @pytest.mark.asyncio
    async def test_disabled_falls_back_to_llm_decision(self, monkeypatch):
        import app.chat.flows.agent as agent_mod

        monkeypatch.setattr(settings, "RULE_ROUTING_ENABLED", False)
        called = {"specs": False}

        def fake_specs(metas):
            called["specs"] = True
            return []

        async def fake_decide(query, llm, max_attempts=2):
            from app.chat.flows.agent import AgentPlan

            return AgentPlan(need_search=True, query_rewrite=query), {"fell_back": False, "retried": False}

        monkeypatch.setattr(agent_mod, "specs_from_metas", fake_specs)
        monkeypatch.setattr(agent_mod, "decide_plan_with_retry", fake_decide)
        plan = await agent_mod.decide_agent_plan("任意问题")
        assert called["specs"], "开关关闭后应走 LLM 决策路径（含 specs 构建）"
        assert plan.need_search is True
