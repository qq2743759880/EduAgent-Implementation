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

import pytest

from app.ai import graph as graph_mod
from app.ai.compaction import estimate_tokens
from app.ai.harness.sixnode import SixNodeHarness


def _empty_state(**overrides) -> dict:
    st = graph_mod._empty_state("现在完成时和过去时区别", user_id=42, session_id=None)
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
# ============================================================
class TestRouteRetryPruning:
    @pytest.mark.asyncio
    async def test_route_llm_exception_calls_once_then_degrade(self, monkeypatch):
        """LLM 异常 → 只调 1 次立即降级 knowledge（原实现 3 连败）。"""
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
    async def test_route_system_prefix_ge_1024_tokens(self, monkeypatch):
        """route 的 system 前缀经 ensure_min_prefix ≥1024 token（跨过火山 ark 缓存门槛）。"""
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
        assert estimate_tokens(sys_prompt) >= 1024, f"route 前缀应 ≥1024 token，实测 {estimate_tokens(sys_prompt)}"

    @pytest.mark.asyncio
    async def test_reflect_judge_prefix_ge_1024_tokens(self, monkeypatch):
        """reflect judge 的 system 前缀同样 ≥1024 token（异常路径调用时也能命中缓存）。"""
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
        assert estimate_tokens(sys_prompt) >= 1024, f"judge 前缀应 ≥1024 token，实测 {estimate_tokens(sys_prompt)}"

    @pytest.mark.asyncio
    async def test_route_prefix_deterministic_across_calls(self, monkeypatch):
        """前缀字节确定性：两次调用返回相同前缀（同缓存 key 才能命中）。"""
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
