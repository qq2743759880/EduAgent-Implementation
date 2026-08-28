"""
task96 / R4（context editing + tool result clearing + 使用率监控 + 阈值策略）契约测试。

全部纯函数 + 进程内 fake，不依赖真实 LLM / 外部 IO（符合测试窗口纪律：
LLM 仅在 12:00–14:00 / 18:00–次日 9:00 调用，此处一律 fake）。

GWT④ 验收（对应 ai-agent-revision-plan.md R4 + task96-ai-revision.md）：
  ① context_edit：精确删除已完成「工具调用+结果」对，保留前缀缓存（前缀签名不变）；
     删 3 条 1500-token 工具调用 → 减少 ≈4.5k token 且 prefix_stable=True。
  ② tool_result_clearing：超出最近 keep_rounds 轮的工具结果 → 一行结论（原文进 artifact）。
  ③ 超阈值策略：context_edit 优先（轻量、保前缀），仍超阈值才 compaction（重量）。

竞品对标（每条结论在 task96-completion-report.md 均附真实 URL）：
  - Claude Code《Manage Claude's context window》：context editing = 最轻量上下文管理，保留前缀缓存。
  - Anthropic cookbook《tool result clearing》：N 轮后工具结果清理为一行，原文落 artifact。
"""
import asyncio
import json

import pytest

import app.ai.compaction as cp
import app.ai.context_edit as ce


# ============================================================
# 测试夹具：token 填充 / 消息构造
# ============================================================
def _tok(n: int) -> str:
    """构造约 n token 的文本（CJK 1 字≈1 token，estimate_tokens 末尾 +1）。"""
    return "中" * (n - 1)


def _sys(text: str = "system prefix") -> dict:
    return {"role": "system", "content": text}


def _user(text: str) -> dict:
    return {"role": "user", "content": text}


def _assistant(text: str) -> dict:
    return {"role": "assistant", "content": text}


def _tool_call(tool_name: str = "t", arg_tokens: int = 1500) -> dict:
    """构造一条「工具调用」消息（role=assistant，content 为含 tool 键的 JSON）。"""
    args = {"q": _tok(max(1, arg_tokens - 24))}
    return {"role": "assistant", "content": json.dumps({"tool": tool_name, "args": args}, ensure_ascii=False)}


def _tool_result(tool_name: str = "t", text: str | None = None) -> dict:
    return {"role": "tool", "content": f"[工具 {tool_name} 返回] {text or 'ok'}"}


def _total(msgs) -> int:
    return sum(ce.msg_tokens(m) for m in msgs)


# ============================================================
# GWT④-①：context_edit 精确删除 + 前缀缓存不变
# ============================================================
class TestGwt4ContextEdit:
    def test_removes_3_tool_pairs_minus_4_5k_and_prefix_stable(self):
        """删 3 条 1500-token 工具调用对 → 减少 ≈4.5k token，且前缀签名不变。"""
        msgs = [
            _sys(),
            _user("q1"), _tool_call("s1", 1500), _tool_result("s1", "ok"),
            _user("q2"), _tool_call("s2", 1500), _tool_result("s2", "ok"),
            _user("q3"), _tool_call("s3", 1500), _tool_result("s3", "ok"),
        ]
        before_sig = ce.prefix_signature(msgs)
        before_total = _total(msgs)
        assert before_total > 4000  # 前置 sanity：确有 ~4.5k 工具 token 量级

        res = ce.context_edit(msgs)

        # 3 对已完成工具消息被精确删除（3 调用 + 3 结果）
        assert res["removed"] == 6, res["removed_details"]
        # 减少量 ≈ 4.5k（3×1500 调用 + 3×tiny 结果）
        assert 4000 <= res["removed_tokens"] <= 5200, res["removed_tokens"]
        # 前缀缓存不变：system 段签名一致
        assert res["prefix_stable"] is True
        assert res["prefix_signature"] == before_sig
        assert res["stable_prefix_len"] >= 1
        # 用户意图（3 条 user）一条不少
        assert sum(1 for m in res["messages"] if m.get("role") == "user") == 3
        # 原列表未被修改（无副作用）
        assert _total(msgs) == before_total

    def test_keeps_unfinished_decision_tool_call_without_result(self):
        """有工具调用但无配套结果（未完成决策）→ 保留；已完成对 → 删除。"""
        msgs = [
            _sys(),
            _user("q1"), _tool_call("s1", 200),            # 无结果 → 保留
            _user("q2"), _tool_call("s2", 200), _tool_result("s2", "ok"),  # 有结果 → 删除对
        ]
        res = ce.context_edit(msgs)
        # s1 的工具调用被保留
        assert any(
            m.get("role") == "assistant" and "s1" in ce.msg_content(m)
            for m in res["messages"]
        )
        # s2 的调用+结果对已被删除
        assert not any(
            m.get("role") == "tool" for m in res["messages"]
        )
        assert res["removed"] == 2

    def test_keep_recent_rounds_protects_tail(self):
        """keep_recent_rounds=1：最近一轮工具对受保护不删，更早的删除。"""
        pol = ce.EditPolicy(keep_recent_rounds=1)
        msgs = [
            _sys(),
            _user("q1"), _tool_call("old", 300), _tool_result("old", "ok"),
            _user("q2"), _tool_call("new", 300), _tool_result("new", "ok"),
        ]
        res = ce.context_edit(msgs, pol)
        # 最近一轮（new）保留
        assert any(
            m.get("role") == "tool" and "new" in ce.msg_content(m)
            for m in res["messages"]
        )
        # 更早一轮（old）删除
        assert not any(
            m.get("role") == "tool" and "old" in ce.msg_content(m)
            for m in res["messages"]
        )

    def test_empty_messages_is_noop(self):
        res = ce.context_edit([])
        assert res["edited"] is False
        assert res["removed"] == 0
        assert res["messages"] == []


# ============================================================
# GWT④-②：tool_result_clearing 超 N 轮 → 一行结论，原文进 artifact
# ============================================================
class TestGwt4ToolResultClearing:
    def test_old_results_to_one_line_recent_kept(self):
        """keep_rounds=1：仅最近一轮工具结果保留原文，更早的精简为一行。"""
        msgs = [
            _sys(),
            _user("q1"), _tool_result("search", _tok(200)),
            _user("q2"), _tool_result("calc", _tok(150)),
            _user("q3"), _tool_result("recent", _tok(100)),
        ]
        res = ce.tool_result_clearing(msgs, keep_rounds=1)
        # 2 条更早结果被清理（q1, q2）
        assert res["cleared"] == 2
        assert res["prefix_stable"] is True
        cleaned = [m for m in res["messages"] if "已入 artifact" in ce.msg_content(m)]
        assert len(cleaned) == 2
        for m in cleaned:
            # 单行：无换行
            assert "\n" not in ce.msg_content(m)
            assert "已入 artifact" in ce.msg_content(m)
        # 最近一轮（recent）原文保留
        recent = [m for m in res["messages"]
                  if m.get("role") == "tool" and "recent" in ce.msg_content(m)]
        assert recent and "最近一轮" not in ce.msg_content(recent[0])  # 未被改写（原文）
        # 幂等：二次清理不应重复改写
        res2 = ce.tool_result_clearing(res["messages"], keep_rounds=1)
        assert res2["cleared"] == 0

    def test_artifact_store_receives_original(self):
        """原文通过 on_original 落 artifact，流内留一行结论 + ref。"""

        class _FakeStore:
            def __init__(self):
                self.written = []

            async def write(self, payload, ttl):
                self.written.append(payload)
                return f"art://{len(self.written)}"

        store = _FakeStore()
        msgs = [
            _sys(),
            _user("q1"), _tool_result("search", _tok(200)),
            _user("q2"), _tool_result("recent", _tok(100)),
        ]
        out = asyncio.run(
            ce.clear_tool_results_to_artifact(msgs, keep_rounds=1, store=store)
        )
        assert out["cleared"] == 1
        assert len(store.written) == 1
        assert store.written[0]["raw"]  # 原文已落 store
        cleaned = [m for m in out["messages"] if "已入 artifact" in ce.msg_content(m)]
        assert len(cleaned) == 1
        assert "art://" in ce.msg_content(cleaned[0])


# ============================================================
# GWT④-③：超阈值 → context_edit 优先，仍超才 compaction
# ============================================================
class TestGwt4ThresholdStrategy:
    def _big_stream(self, edit_threshold: int):
        """构造 总 token > edit_threshold 的消息流：含 1 个已完成工具对 + 大量非工具内容。"""
        return [
            _sys("pref"),
            _user("q1"), _assistant(_tok(800)),
            _user("q2"), _tool_call("s2", 1500), _tool_result("s2", "ok"),
            _user("q3"), _assistant(_tok(800)),
        ]

    def test_over_threshold_context_edit_then_compaction_chain(self):
        strategy = ce.ThresholdStrategy(
            edit_threshold=1000, keep_rounds=1, window_tokens=100000,
            warn_ratio=0.6, order=("context_edit", "compaction"), context_edit_enabled=True,
        )
        msgs = self._big_stream(1000)
        assert _total(msgs) > 1000  # 前置 sanity

        res = ce.apply_context_strategy(msgs, strategy=strategy)

        # 关键：先 context_edit（轻量），仍超阈值才 compaction（重量）
        assert res["chain"] == ["context_edit", "compaction"], res["chain"]
        assert res["action"] == "compaction"
        # 压缩后不超过阈值
        assert res["after_tokens"] <= 1000, res["after_tokens"]
        # compaction 后：最近一轮(q3)原始 user 消息保留；更早的 q1/q2 已压缩进摘要
        surviving_users = [m for m in res["messages"] if m.get("role") == "user"]
        assert any("q3" in ce.msg_content(m) for m in surviving_users)
        assert not any("q1" in ce.msg_content(m) for m in surviving_users)
        assert res["usage_after"].total_tokens <= 1000

    def test_context_edit_sufficient_skips_compaction(self):
        """context_edit 单步即可降到阈值内 → 不触发重量 compaction。"""
        strategy = ce.ThresholdStrategy(
            edit_threshold=2500, keep_rounds=6, window_tokens=100000,
            warn_ratio=0.6, order=("context_edit", "compaction"), context_edit_enabled=True,
        )
        # 仅工具对、context_edit 即可清到阈值内
        msgs = [
            _sys(),
            _user("q1"), _tool_call("s1", 1500), _tool_result("s1", "ok"),
            _user("q2"), _tool_call("s2", 1500), _tool_result("s2", "ok"),
        ]
        res = ce.plan_context_action(msgs, strategy=strategy)
        assert res["action"] == "context_edit", res
        assert res["projected_tokens"] <= 2500

    def test_under_threshold_is_none(self):
        strategy = ce.ThresholdStrategy(
            edit_threshold=100000, keep_rounds=6, window_tokens=100000,
            warn_ratio=0.6, order=("context_edit", "compaction"), context_edit_enabled=True,
        )
        msgs = [_sys(), _user("hi"), _assistant("hello")]
        res = ce.plan_context_action(msgs, strategy=strategy)
        assert res["action"] == "none"
        # compaction 兼容层同样判定 none
        assert cp.compaction_policy(msgs, threshold=100000) == "none"


# ============================================================
# GWT③：使用率监控 + 快照
# ============================================================
class TestContextUsageMonitor:
    def test_measure_usage_fields(self):
        msgs = [
            _sys("pref"),
            _user("q1"), _tool_call("s", 1500), _tool_result("s", "ok"),
        ]
        usage = ce.measure_usage(msgs, window_tokens=32000, edit_threshold=6000)
        assert usage.total_tokens > 0
        assert usage.window_tokens == 32000
        assert usage.edit_threshold == 6000
        assert usage.prefix_tokens > 0           # system 前缀占用
        assert usage.tool_result_tokens > 0      # 工具结果占用
        assert usage.rounds >= 1
        assert 0.0 <= usage.usage_ratio
        assert usage.over_threshold == (usage.total_tokens > 6000)

    def test_monitor_snapshot_and_ring_buffer(self):
        mon = ce.ContextUsageMonitor(maxlen=3, clock=lambda: 1000.0)
        for _ in range(5):
            u = ce.measure_usage([_sys("p"), _user("q"), _assistant("a")],
                                 window_tokens=32000, edit_threshold=6000)
            mon.record(u, action="none")
        snap = mon.snapshot()
        assert snap["samples"] == 3           # 环形缓冲截断到 maxlen
        assert snap["over_warn"] == 0
        assert snap["actions"].get("none", 0) == 3

    def test_monitor_records_over_warn(self):
        mon = ce.ContextUsageMonitor(clock=lambda: 1.0)
        big = ce.measure_usage([_sys("p")] + [_assistant(_tok(20000))],
                               window_tokens=32000, edit_threshold=6000, warn_ratio=0.6)
        assert big.over_warn is True
        rec = mon.record(big, action="compaction")
        assert rec["over_warn"] is True
        assert mon.over_warn_count() == 1


# ============================================================
# 兼容层对称：compaction.* 委派结果须与 context_edit.* 一致
# ============================================================
class TestDelegateSymmetry:
    def test_compaction_delegates_to_context_edit(self):
        msgs = [
            _sys(),
            _user("q1"), _tool_call("s1", 1500), _tool_result("s1", "ok"),
            _user("q2"), _tool_call("s2", 1500), _tool_result("s2", "ok"),
        ]
        a = ce.context_edit(msgs)
        b = cp.context_edit(msgs)
        assert b["removed"] == a["removed"] == 4   # 2 对已完成工具消息
        assert b["removed_tokens"] == a["removed_tokens"]
        assert b["prefix_stable"] == a["prefix_stable"]

    def test_compaction_delegates_tool_result_clearing(self):
        msgs = [
            _sys(),
            _user("q1"), _tool_result("search", _tok(200)),
            _user("q2"), _tool_result("recent", _tok(100)),
        ]
        a = ce.tool_result_clearing(msgs, keep_rounds=1)
        b = cp.tool_result_clearing(msgs, keep_rounds=1)
        assert b["cleared"] == a["cleared"] == 1
        assert b["prefix_stable"] == a["prefix_stable"]
