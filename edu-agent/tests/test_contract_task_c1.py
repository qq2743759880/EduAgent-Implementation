# -*- coding: utf-8 -*-
"""task-C1 契约测试：token 预算分配器 + 锚定闸门 + LLM 动态选片段（P4 上下文压缩固定丢轮）。

AC1 预算守恒（Σ=100%，每类 ≤ 比例×阈值）
AC2 LLM 动态选片段召回（第 3 轮关键数据可召回 + A/B 对比固定 6 轮）
AC3 规则回退等价（4 键 JSON 逐键兼容，≤ threshold）
AC4 锚定保护（闸门前字节零改动，前缀缓存不变）
AC5 回归：本文件另含默认路径（opt-in 关闭）与 task26 行为一致断言；task26/96 全量回归见完工报告。
"""
from __future__ import annotations

import json

from app.ai import compaction as c
from app.ai.compaction import (
    BudgetAllocator,
    anchor_gate,
    llm_select_fragments,
)
from app.ai.context_edit import context_edit

KEY = "KEY_DATA_xyz"


def _build(n: int, key_round: int | None = None, per_answer_tokens: int = 600) -> list[dict]:
    """构造对话：system 前缀 + n 轮 user/assistant；key_round 轮含关键数据。

    关键轮回答同样保持 ~per_answer_tokens 长度（仅把 KEY 嵌入），确保总量稳定超阈值、真正触发压缩。
    """
    filler = "详" * per_answer_tokens
    msgs = [{"role": "system", "content": "SYS_PREFIX_STABLE 不可变前缀"}]
    for i in range(1, n + 1):
        u = {"role": "user", "content": f"Q{i} 问题{i}"}
        if i == key_round:
            u["content"] = f"Q{i} 问题{i} 含关键数据 {KEY}"
        msgs.append(u)
        a = filler if i != key_round else (filler + KEY)
        msgs.append({"role": "assistant", "content": a})
    return msgs


def _blob(msgs) -> str:
    return json.dumps(msgs, ensure_ascii=False)


class TestBudgetAllocator:
    def test_ratios_sum_to_one(self):
        plan = BudgetAllocator.allocate(_build(10), threshold=6000)
        assert abs(plan["sum_budget_ratio"] - 1.0) < 1e-9
        assert plan["valid"] is True

    def test_each_budget_within_ratio(self):
        plan = BudgetAllocator.allocate(_build(10), threshold=6000)
        for k in plan["ratios"]:
            assert plan["budgets"][k] <= plan["ratios"][k] * plan["threshold"] + 1

    def test_custom_ratios_normalized(self):
        plan = BudgetAllocator.allocate(
            _build(8), threshold=4000, ratios={"system": 1, "user_query": 1, "tool_result": 2, "history": 0}
        )
        # system:user:tool:history = 1:1:2:0 → 归一后 sum=1，history 预算=0
        assert abs(plan["sum_budget_ratio"] - 1.0) < 1e-9
        assert plan["budgets"]["history"] == 0
        assert plan["budgets"]["tool_result"] > plan["budgets"]["system"]


class TestAnchorGate:
    def test_anchor_returns_at_least_system_prefix(self):
        msgs = _build(10, key_round=3)
        gate = anchor_gate(msgs, 3)
        # 至少覆盖连续 system 前缀
        assert gate >= 1
        # 闸门前第一条必须是 system
        assert msgs[0]["role"] == "system"

    def test_anchor_covers_first_n_user_rounds(self):
        msgs = _build(10, key_round=3)
        gate = anchor_gate(msgs, 3)
        # 第 3 轮（Q3 含 KEY）应在闸门内被保护
        rendered = c._render(msgs[:gate])
        assert KEY in rendered


def _mock_llm(pick_key: str = KEY):
    """模拟 fast 模型：从决策 prompt 中定位含 key 的轮，返回 keep_round_ids=[该轮]。"""
    def _call(messages: list[dict]) -> str:
        text = messages[-1]["content"]
        target = None
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("[") and pick_key in s:
                idx = s[1:].split("]")[0]
                try:
                    target = int(idx)
                except Exception:
                    target = None
        if target is None:
            return '{"keep_round_ids":[2]}'
        return json.dumps({"keep_round_ids": [target]})
    return _call


class TestLLMDynamicSelection:
    def test_llm_keeps_key_round_via_dynamic_selection(self):
        msgs = _build(10, key_round=3)
        r = c.compact_messages(msgs, llm=_mock_llm(), anchor_round=None)
        assert r["applied"] is True
        assert r["after_tokens"] <= 6000, f"压缩后应 ≤6000: {r['after_tokens']}"
        assert "keep_round_ids" in r
        assert KEY in _blob(r["kept_messages"]), "LLM 选片段应保留第 3 轮关键数据"

    def test_ab_recall_fixed6_vs_dynamic(self):
        """A/B：固定保留最近 6 轮 vs LLM 动态选片段（第 3 轮关键数据召回率）。"""
        msgs = _build(10, key_round=3)
        fixed = c.compact_messages(msgs)                       # 默认 legacy，keep_rounds=6
        dyn = c.compact_messages(msgs, llm=_mock_llm())       # 动态选片段

        fixed_recall = 1 if KEY in _blob(fixed["kept_messages"]) else 0
        dyn_recall = 1 if KEY in _blob(dyn["kept_messages"]) else 0

        # 固定 6 轮：第 3 轮超出最近 6 轮 → 丢；动态：选中第 3 轮 → 召回
        assert fixed_recall == 0, "固定 6 轮基线应丢失第 3 轮关键数据（这正是 P4 批判点）"
        assert dyn_recall == 1, "动态选片段应召回第 3 轮关键数据"
        assert dyn["after_tokens"] <= 6000


class TestRuleFallback:
    def test_rule_fallback_four_key_json(self):
        """AC3：无 LLM（窗口外/注入失败）回退规则，summary 4 键 JSON 逐键兼容，≤ threshold。"""
        msgs = _build(10, key_round=3)
        r = c.compact_messages(msgs, anchor_round=3)  # 无 llm → 规则回退
        assert r["applied"] is True
        assert r["after_tokens"] <= 6000
        obj = json.loads(r["summary_json"])
        assert set(obj.keys()) == {"profile_updates", "pending_tasks", "decisions", "facts"}

    def test_fallback_matches_default_structured_keys(self):
        from app.ai.compaction import _default_structured_summary

        msgs = _build(12, key_round=3)
        r = c.compact_messages(msgs, anchor_round=3)
        obj = json.loads(r["summary_json"])
        ref = _default_structured_summary(msgs)
        assert set(obj.keys()) == set(ref.keys())


class TestAnchorProtection:
    def test_compact_anchor_bytes_unchanged(self):
        msgs = _build(10, key_round=3)
        r = c.compact_messages(msgs, anchor_round=3)
        gate = r["anchor_gate_idx"]
        assert gate >= 1
        before = c._render(msgs[:gate])
        after = c._render(r["kept_messages"][:gate])
        assert before == after, "闸门前消息字节必须零改动（保护前缀缓存）"

    def test_context_edit_anchor_bytes_unchanged(self):
        msgs = _build(10, key_round=3)
        ce = context_edit(msgs, anchor_round=3)
        g = ce["anchor_gate_idx"]
        before = c._render(msgs[:g])
        after = c._render(ce["messages"][:g])
        assert before == after, "context_edit 锚定闸门同样须保证闸门前字节零改动"
        assert ce["prefix_stable"] is True

    def test_anchor_no_effect_when_disabled(self):
        """opt-in 关闭（默认）时不应冻结前轮 → 回到既有 context_edit 行为。"""
        msgs = _build(5, key_round=3)
        ce_off = context_edit(msgs)  # 默认 None
        ce_on = context_edit(msgs, anchor_round=3)
        # 开启锚定后，更少的消息被删除（前 3 轮被冻结保护）
        assert len(ce_on["messages"]) >= len(ce_off["messages"])


class TestDefaultPathRegression:
    def test_default_compact_matches_legacy_keep_recent(self):
        """默认调用（opt-in 全关）行为须与 task26 既有一致：最近轮保留、首轮进摘要。"""
        msgs = _build(20, per_answer_tokens=600)
        r = c.compact_messages(msgs)
        assert r["applied"] is True
        assert r["after_tokens"] <= 6000
        kept = _blob(r["kept_messages"])
        assert "Q20 问题20" in kept, "最近轮原文应保留"
        assert "Q1 问题1" not in kept, "首轮原文应已进摘要（不被保留原文）"

    def test_default_compact_no_anchor_fields_clutter(self):
        msgs = _build(20, per_answer_tokens=600)
        r = c.compact_messages(msgs)
        # 默认路径不携带 task-C1 扩展字段（向后兼容消费方）
        assert "anchor_gate_idx" not in r
        assert "keep_round_ids" not in r
