# -*- coding: utf-8 -*-
"""task27 契约测试：tool_specs 规范 + CoT/token 优化（prompt caching + 双模型）GWT①②③④。

纯内存 / 纯函数为主，无外部 LLM / Redis 依赖，可直接运行：
    pytest tests/test_contract_task27.py -q

GWT：
① ToolSpec 五要素齐全；system+工具前缀 ≤300 token、按 name 稳定排序、同输入前缀逐字节一致。
② 非法 JSON 经 Pydantic 校验失败后只重试 1 次，仍失败则保守回退（need_search=true），不抛 500。
③ 两个 parallel_safe 且无依赖工具并发执行（总耗时 < 串行）；admin_only 工具不进入普通用户决策 prompt。
④ 缓存按 system/project/对话 三层组织，失效原因可记录。
"""
from __future__ import annotations

import asyncio
import time

import pytest

from app.ai import decision_validator as dv
from app.ai import prompt_cache as pc
from app.ai import tool_specs as ts


# ============================================================
# GWT① ToolSpec 五要素 + 前缀 ≤300 + 稳定排序 + 逐字节一致
# ============================================================
class TestToolSpecAndPrefix:
    def test_toolspec_five_elements_plus_fields(self):
        s = ts.BUILTIN_TOOL_SPECS[0]
        # 五要素 + 增强字段齐全
        assert s.name and s.description
        assert isinstance(s.input_schema, dict)
        assert s.risk in ("read", "write")
        assert isinstance(s.parallel_safe, bool)
        assert isinstance(s.timeout_s, float)
        assert isinstance(s.admin_only, bool)

    def test_prefix_token_budget_under_300(self):
        prefix = ts.build_decision_prefix(ts.BUILTIN_TOOL_SPECS, is_admin=False)
        n = ts.measure_prefix_tokens(prefix)
        assert n <= 300, f"前缀应 ≤300 token，实测 {n}"

    def test_prefix_stable_sorted_and_byte_identical(self):
        specs = list(ts.BUILTIN_TOOL_SPECS)
        # 打乱输入顺序，两次构建仍逐字节一致（稳定排序）
        a = ts.build_decision_prefix(list(reversed(specs)), is_admin=False)
        b = ts.build_decision_prefix(specs, is_admin=False)
        assert a == b, "同输入前缀应逐字节一致"
        # 明确校验工具列表已按 name 升序
        visible = ts.specs_for_access(ts.stable_sorted_specs(specs), is_admin=False)
        names = [s.name for s in visible]
        assert names == sorted(names)

    def test_admin_only_excluded_for_regular_user(self):
        prefix = ts.build_decision_prefix(ts.BUILTIN_TOOL_SPECS, is_admin=False)
        assert "admin_user_impersonate" not in prefix, "普通用户前缀不应含 admin_only 工具"
        assert "admin_broadcast_message" not in prefix
        # 无内置可并行工具时仍保留普通工具
        assert "calculator" in prefix
        # admin 视角包含
        admin_prefix = ts.build_decision_prefix(ts.BUILTIN_TOOL_SPECS, is_admin=True)
        assert "admin_user_impersonate" in admin_prefix


# ============================================================
# GWT② Pydantic 校验失败 → 重试 1 次 → 保守回退，不抛 500
# ============================================================
class _SeqLLM:
    """注入 fake LLM：按次序返回 raw，直到耗尽则返回末尾值。record 记录每次调用入参。"""

    def __init__(self, raws):
        self.raws = list(raws)
        self.calls = []

    async def __call__(self, query):
        self.calls.append(query)
        return self.raws[min(len(self.calls) - 1, len(self.raws) - 1)]


class TestDecisionValidator:
    def test_valid_json_no_fallback_no_extra_retry(self):
        llm = _SeqLLM(['{"need_search": false, "query_rewrite": "", "tool_plan": [], "answer_direct": "你好"}'])
        plan, meta = asyncio.run(dv.decide_plan_with_retry("你好", llm))
        assert meta["fell_back"] is False
        assert meta["retried"] is False
        assert len(llm.calls) == 1, "合法输出不应重试"
        assert plan.need_search is False

    def test_invalid_json_retried_once_then_conservative(self):
        # 首次非法、第二次也非法 → 重试恰好 1 次 → 保守回退
        llm = _SeqLLM(["抱歉，无法理解", "still not json"])
        plan, meta = asyncio.run(dv.decide_plan_with_retry("任意问题", llm))
        assert meta["retried"] is True, "非法输出应重试一次"
        assert meta["fell_back"] is True
        assert len(llm.calls) == 2, "最多 2 次调用（原始 + 1 次重试）"
        assert plan.need_search is True, "保守回退应为检索兜底"
        assert plan.query_rewrite == "任意问题"

    def test_valid_after_one_retry_recovers(self):
        # 首次非法、第二次合法 → 重试 1 次后成功，不回退
        good = '{"need_search": true, "query_rewrite": "英语 语法", "tool_plan": [], "answer_direct": ""}'
        llm = _SeqLLM(["nonsense", good])
        plan, meta = asyncio.run(dv.decide_plan_with_retry("英语", llm))
        assert meta["retried"] is True
        assert meta["fell_back"] is False
        assert plan.need_search is True and plan.query_rewrite == "英语 语法"

    def test_pydantic_typed_tool_plan(self):
        raw = '{"need_search": false, "query_rewrite": "", "tool_plan": [{"tool_name": "calculator", "args": {"a": 1, "b": 2, "op": "add"}}], "answer_direct": ""}'
        plan = dv.parse_decision_text(raw)
        assert plan is not None
        assert plan.tool_plan[0].tool_name == "calculator"
        assert plan.tool_plan[0].args["op"] == "add"

    def test_malformed_tool_plan_returns_none(self):
        # 结构非法（tool_plan 项缺 tool_name）→ Pydantic 校验失败 → None → 走重试/回退
        raw = '{"need_search": false, "tool_plan": [{"args": {"a": 1}}], "answer_direct": ""}'
        assert dv.parse_decision_text(raw) is None


# ============================================================
# GWT③ 并行（parallel_safe）并发执行 + 串行兜底
# ============================================================
async def _fake_delayed_call(tool_name: str, args: dict, delay: float):
    await asyncio.sleep(delay)
    return {"status": "SUCCESS", "result": {"tool_name": tool_name}}


class TestParallelTools:
    def test_two_parallel_safe_tools_run_concurrently(self):
        spec_map = {
            "calculator": ts.make_spec("calculator", parallel_safe=True),
            "web_search": ts.make_spec("web_search", parallel_safe=True),
            "code_runner": ts.make_spec("code_runner", parallel_safe=False),
        }
        plan = [
            {"tool_name": "calculator", "args": {"a": 1, "b": 2, "op": "add"}},
            {"tool_name": "web_search", "args": {"q": "x"}},
        ]  # 两个 parallel_safe 且无依赖

        async def call(name, args):
            return await _fake_delayed_call(name, args, 0.3)

        async def _run():
            t0 = time.perf_counter()
            res = await ts.run_parallel_tools(plan, lambda n: spec_map.get(n), call)
            return res, time.perf_counter() - t0

        res, elapsed = asyncio.run(_run())
        assert elapsed < 0.5, f"并发执行应接近单次延迟(0.3s)，实测 {elapsed:.2f}s（串行会是 0.6s+）"
        assert [r["tool_name"] for r in res] == ["calculator", "web_search"]
        assert all(r["parallel"] for r in res)

    def test_serial_for_non_parallel_safe(self):
        spec_map = {"code_runner": ts.make_spec("code_runner", parallel_safe=False)}
        plan = [{"tool_name": "code_runner", "args": {"code": "print(1)"}}]

        async def call(name, args):
            return await _fake_delayed_call(name, args, 0.1)

        async def _run():
            return await ts.run_parallel_tools(plan, lambda n: spec_map.get(n), call)

        res = asyncio.run(_run())
        assert res[0]["parallel"] is False, "非 parallel_safe 工具应串行标记"


# ============================================================
# GWT④ 缓存三层组织（system/project/对话）+ 失效原因记录
# ============================================================
class TestPromptCacheLayers:
    def test_three_layers_and_hit(self):
        cache = pc.PromptCache()
        assert set(cache.stats()["layers"]) == {"system", "project", "conversation"}
        cache.set("system", "sys-v1", reason="init")
        key = cache.get("system", "sys-v1")
        assert key, "同内容应命中并返回 key"
        stats = cache.stats()
        assert stats["hits"]["system"] == 1 and stats["misses"]["system"] == 1

    def test_invalidation_reason_recorded_on_change(self):
        cache = pc.PromptCache()
        cache.set("project", "mcp-v1", reason="init")
        cache.set("project", "mcp-v2", reason="mcp_tool_change")
        cache.set("project", "mcp-v3", reason="mcp_tool_change")
        inv = cache.invalidations_list(layer="project")
        # 首次 set：miss 非失效；后续内容变化记录 2 条失效，reason 正确
        assert len(inv) == 2
        assert all(i["reason"] == "mcp_tool_change" for i in inv)
        assert inv[0]["prev_key"] != inv[0]["new_key"]

    def test_explicit_invalidate_records_reason(self):
        cache = pc.PromptCache()
        cache.set("conversation", "ctx-v1", reason="init")
        cache.invalidate("conversation", reason="compaction")
        inv = cache.invalidations_list(layer="conversation")
        assert any(i["reason"] == "compaction" for i in inv)
        # 显式失效后，同内容不再命中
        assert cache.get("conversation", "ctx-v1") is None

    def test_unknown_layer_raises(self):
        cache = pc.PromptCache()
        with pytest.raises(ValueError):
            cache.set("bogus", "x")
        with pytest.raises(ValueError):
            cache.get("bogus", "x")