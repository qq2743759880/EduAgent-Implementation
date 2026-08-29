# -*- coding: utf-8 -*-
"""task-C2 契约测试：缓存前缀达标（1024 门槛 + defer_loading + 填充注释 + 命中率 SEV）。

纯函数 / 纯内存为主，无外部 LLM / Redis 依赖（AC4 命中率计量用 mock usage 验证），
可直接运行：
    pytest tests/test_contract_task_c2.py -q

AC：
① 填充达标：300 token 前缀经 ensure_min_prefix → ≥1024 token，且两次构建字节完全一致。
② defer 前缀稳定：工具增删/描述重写后既有桩字节零变化，project 层不产生整层失效事件。
③ schema 按需展开：决策前缀不含 input_schema；expand_schema 返回完整 schema 进后续请求。
④ 命中率监控：命中率计量与 SEV 触发（纯函数，无需真实 LLM）。
⑤ 回归：task27/task95 既有契约（前缀 ≤300 + 稳定 + admin 隔离 + 三层组织）不回归。
"""
from __future__ import annotations

import json

from app.ai import prompt_cache as pc
from app.ai import tool_specs as ts
from app.ai.prompt_cache import (
    anchor_guard,
    ensure_min_prefix,
    evaluate_cache_sev,
)
from app.ai.tool_specs import (
    ToolSpec,
    build_decision_prefix,
    expand_schema,
    build_tool_expansion_message,
)


# ============================================================
# AC① 填充达标：≥门槛 token（1024→2048，task-P1L 优化G）且逐字节稳定
# ============================================================
class TestEnsureMinPrefix:
    def test_pads_to_at_least_threshold(self):
        from app.config import settings

        threshold = int(settings.PROMPT_CACHE_MIN_TOKENS)
        prefix = build_decision_prefix(ts.BUILTIN_TOOL_SPECS, is_admin=False)  # ~300 token
        before = ts.measure_prefix_tokens(prefix)
        padded = ensure_min_prefix(prefix)
        after = ts.measure_prefix_tokens(padded)
        assert before < threshold, f"前置断言：原始决策前缀应 <{threshold}（实测 {before}）"
        assert after >= threshold, f"填充后前缀应 ≥{threshold} token，实测 {after}"
        # 填充只追加在末尾，原前缀内容不变
        assert padded.startswith(prefix)

    def test_byte_stable_across_calls(self):
        prefix = build_decision_prefix(ts.BUILTIN_TOOL_SPECS, is_admin=True)
        a = ensure_min_prefix(prefix)
        b = ensure_min_prefix(prefix)
        assert a == b, "ensure_min_prefix 两次相同输入应逐字节一致（填充注释必须稳定）"

    def test_noop_when_already_above(self):
        # 门槛动态取 settings（task-P1L 优化G：1024→2048，实测 ark 按 2048-token 分块）；
        # 用英文 x 保守估计 4 字符/token，保证前缀确实超过门槛（避免测试与门槛值耦合）
        from app.config import settings

        threshold = int(settings.PROMPT_CACHE_MIN_TOKENS)
        big = "# " + "x" * (threshold * 4)
        out = ensure_min_prefix(big)
        assert out == big, f"已 ≥{threshold} token 的前缀不应被改动"


# ============================================================
# AC② defer 前缀稳定：工具增删/描述重写不改变既有桩字节
# ============================================================
def _mk(name: str, desc: str, summary: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=desc,
        summary=summary,  # 显式稳定摘要：description 被重写时桩不变
        input_schema={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
    )


class TestDeferredPrefixStable:
    def test_existing_stubs_unchanged_on_add_and_rewrite(self):
        base = [_mk("t1", "工具一 完整描述", "工具一摘要"),
                _mk("t2", "工具二 完整描述", "工具二摘要"),
                _mk("t3", "工具三 完整描述", "工具三摘要")]
        p1 = build_decision_prefix(base, deferred=True)
        # 提取既有桩字节
        stub1 = json.dumps(base[0].to_prompt_entry(deferred=True), ensure_ascii=False)
        stub3 = json.dumps(base[2].to_prompt_entry(deferred=True), ensure_ascii=False)
        assert stub1 in p1 and stub3 in p1

        # 场景：t2 完整描述被体检重写（summary 不变 → 桩不变），并新增 t4
        mutated = [_mk("t1", "工具一 完整描述", "工具一摘要"),
                   _mk("t2", "工具二 描述被大幅重写（schema 调整）", "工具二摘要"),
                   _mk("t3", "工具三 完整描述", "工具三摘要"),
                   _mk("t4", "新增工具四", "新增工具四摘要")]
        p2 = build_decision_prefix(mutated, deferred=True)
        # 既有桩字节零变化
        assert stub1 in p2, "t1 桩字节应零变化"
        assert stub3 in p2, "t3 桩字节应零变化"
        # 仅新增 1 条存根
        assert json.dumps(mutated[3].to_prompt_entry(deferred=True), ensure_ascii=False) in p2
        # 全部工具按 name 升序，桩序稳定
        assert p2.index('"t1"') < p2.index('"t2"') < p2.index('"t3"') < p2.index('"t4"')

    def test_project_layer_no_whole_layer_invalidation(self):
        cache = pc.PromptCache()
        base = [_mk("t1", "d1", "s1"), _mk("t2", "d2", "s2"), _mk("t3", "d3", "s3")]
        stubs1 = {s.name: json.dumps(s.to_prompt_entry(deferred=True), ensure_ascii=False) for s in base}
        cache.set_stubs("project", stubs1)

        # 重写 t2 完整描述（summary 不变 → 桩不变）+ 新增 t4
        mutated = [_mk("t1", "d1", "s1"),
                   _mk("t2", "d2 被重写", "s2"),
                   _mk("t3", "d3", "s3"),
                   _mk("t4", "d4", "s4")]
        stubs2 = {s.name: json.dumps(s.to_prompt_entry(deferred=True), ensure_ascii=False) for s in mutated}
        res = cache.set_stubs("project", stubs2)

        # 既有桩命中（hit），t4 新增（add），无变化工具
        assert res["added"] == ["t4"]
        assert res["changed_tools"] == [], "summary 不变的 description 重写不应产生 changed_tools"
        # 关键：project 层不得产生整层失效事件（whole_layer=True）
        proj_inv = cache.invalidations_list(layer="project")
        assert all(not i.get("whole_layer") for i in proj_inv), \
            "defer_loading 下工具增删/重写不得产生整层失效事件"
        # 显式 invalidate（如模型切换）才产生整层失效
        cache.invalidate("project", reason="model_switch")
        assert any(i.get("whole_layer") for i in cache.invalidations_list(layer="project")), \
            "仅 invalidate() 显式清空才产生整层失效事件"

    def test_pure_schema_rewrite_no_invalidation(self):
        cache = pc.PromptCache()
        s = _mk("t1", "原描述", "稳定摘要")
        cache.set_stubs("project", {s.name: json.dumps(s.to_prompt_entry(deferred=True), ensure_ascii=False)})
        # 仅改 description（input_schema/schema 变更），summary 保留
        s2 = _mk("t1", "schema 被大幅改写后的描述", "稳定摘要")
        res = cache.set_stubs("project", {s2.name: json.dumps(s2.to_prompt_entry(deferred=True), ensure_ascii=False)})
        assert res["changed_tools"] == [] and res["added"] == [], "纯 schema 重写应完全不改变桩"
        assert cache.invalidations_list(layer="project") == [], "纯 schema 重写不得记任何失效"


# ============================================================
# AC③ schema 按需展开：决策前缀不含 schema，expand_schema 返回完整
# ============================================================
class TestExpandSchema:
    def test_deferred_prefix_excludes_input_schema(self):
        prefix = build_decision_prefix(ts.BUILTIN_TOOL_SPECS, is_admin=True, deferred=True)
        assert '"input_schema"' not in prefix, "deferred 决策前缀不得含 input_schema（保前缀稳定）"

    def test_full_mode_includes_input_schema(self):
        # 大 budget 避免 300 token 裁剪把 input_schema 剥掉（裁剪是正确行为，此处验证 full 模式语义）
        prefix = build_decision_prefix(ts.BUILTIN_TOOL_SPECS, is_admin=True, deferred=False, budget=10_000_000)
        assert '"input_schema"' in prefix, "full 模式（A/B）应含 input_schema"

    def test_expand_schema_returns_full(self):
        spec = expand_schema("calculator")
        assert spec is not None
        assert spec.input_schema, "expand_schema 应返回完整 input_schema"
        # 展开消息进后续请求，不进前缀
        msg = build_tool_expansion_message("calculator")
        assert msg is not None and msg["role"] == "system"
        assert '"input_schema"' in msg["content"]

    def test_expand_schema_unknown_returns_none(self):
        assert expand_schema("__no_such_tool__") is None
        assert build_tool_expansion_message("__no_such_tool__") is None


# ============================================================
# AC④ 命中率监控 + SEV 触发（纯函数，无真实 LLM）
# ============================================================
class TestCacheHitRateSev:
    def test_high_hit_rate_no_sev(self):
        # round1 创建缓存(miss)，其后 5 轮高命中
        usage = [{"prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 1500}]
        usage += [{"prompt_cache_hit_tokens": 1400, "prompt_cache_miss_tokens": 100}] * 5
        r = pc.evaluate_hit_rate(usage, model="fast", layer="project")
        assert r["hit_rate"] > 0.5, f"高命中率应 >0.5，实测 {r['hit_rate']}"
        assert r["sev"]["sev"] is False, "高命中率不应触发 SEV"

    def test_low_hit_rate_triggers_sev(self):
        # 每轮都未命中（前缀不稳定 / 未达缓存门槛）
        usage = [{"prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 1500}] * 6
        r = pc.evaluate_hit_rate(usage, model="fast", layer="project")
        assert r["hit_rate"] == 0.0
        assert r["sev"]["sev"] is True, "命中率 <0.5 必须触发 SEV（对齐 Claude 把命中率当 uptime）"

    def test_sev_threshold_configurable(self):
        r = evaluate_cache_sev(0.4, threshold=0.5)
        assert r["sev"] is True
        r2 = evaluate_cache_sev(0.4, threshold=0.3)
        assert r2["sev"] is False, "阈值可配：0.4 在 0.3 阈值下不触发 SEV"


# ============================================================
# AC⑤ 回归：task27/task95 既有契约不回归
# ============================================================
class TestRegressionTask27:
    def test_prefix_budget_under_300(self):
        prefix = build_decision_prefix(ts.BUILTIN_TOOL_SPECS, is_admin=False)
        assert ts.measure_prefix_tokens(prefix) <= 300, "决策前缀应 ≤300 token（task27 GWT①）"

    def test_prefix_stable_byte_identical(self):
        specs = list(ts.BUILTIN_TOOL_SPECS)
        a = build_decision_prefix(list(reversed(specs)), is_admin=False)
        b = build_decision_prefix(specs, is_admin=False)
        assert a == b, "同输入前缀应逐字节一致（task27 GWT① 稳定排序）"

    def test_admin_only_excluded_for_regular(self):
        prefix = build_decision_prefix(ts.BUILTIN_TOOL_SPECS, is_admin=False)
        assert "admin_user_impersonate" not in prefix and "admin_broadcast_message" not in prefix
        admin_prefix = build_decision_prefix(ts.BUILTIN_TOOL_SPECS, is_admin=True)
        assert "admin_user_impersonate" in admin_prefix

    def test_three_layer_cache_and_invalidation(self):
        cache = pc.PromptCache()
        assert set(cache.stats()["layers"]) == {"system", "project", "conversation"}
        cache.set("system", "sys-v1", reason="init")
        assert cache.get("system", "sys-v1")
        cache.set("project", "mcp-v1", reason="init")
        cache.set("project", "mcp-v2", reason="mcp_tool_change")
        inv = cache.invalidations_list(layer="project")
        assert len(inv) == 1 and inv[0]["reason"] == "mcp_tool_change"


# ============================================================
# 锚定闸门（task-C2 ③）
# ============================================================
class TestAnchorGuard:
    def test_anchor_prefix_first_and_dynamic_injected(self):
        dynamic = [{"role": "user", "content": "用户问题"}]
        msgs = anchor_guard("SYS_PREFIX", dynamic)
        assert msgs[0] == {"role": "system", "content": "SYS_PREFIX"}
        assert msgs[1:] == dynamic

    def test_anchor_drift_records_invalidation(self):
        cache = pc.PromptCache()
        anchor_guard("SYS_V2", [], expected_prefix="SYS_V1", cache=cache)
        inv = cache.invalidations_list(layer="system")
        assert any(i["reason"] == "anchor_drift" for i in inv), "前缀漂移应记录 anchor_drift 失效"
