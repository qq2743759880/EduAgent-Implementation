# -*- coding: utf-8 -*-
"""task26 契约测试：compaction + R4 context editing + artifact 分流 + Redis 防过载（GWT ①②③）。

执行方式：纯内存/纯函数为主（guard 用内存后端；artifact 用注入内存 store），不依赖 MySQL/在线 LLM、
可控测试时长不真等 10s（guard 用短超时注入）。真 Redis 存在时可加测 bigkey（跳过即可）。

GWT：
① 消息流 >6000 token → plan_node 前压缩至 ≤6000；summary 保留结构化决策语义；最近 6 轮原文保留；
   compaction 前优先 context_edit（轻量），仍超才 compaction（重量）。
② 单条 MCP/工具输出 >1500 token → 立即蒸馏：原始 JSON 进 artifact（TTL 1h）、流内仅 1 行结论。
③ LLM 并发闸满 + 第 N 个 → BLPOP 排队；>10s 返回友好提示而非堆积；单用户并发第 3 个被拒(≤2)。
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.ai import compaction as c
from app.ai.artifact import ArtifactShuntStore, distill_tool_output, shunt_tool_outputs
from app.ai.guard import ConcurrencyGuard


# ============================================================
# GWT① compaction：阈值 6000 触发 / 结构化摘要 / 最近 6 轮原文保留
# ============================================================
def _round_msg(ridx: int, big: bool = True) -> list[dict]:
    user = {"role": "user", "content": f"AAA_{ridx} 问题#{ridx}"}
    ans = {"role": "assistant", "content": ("详" * 600 + f"\nBBB_{ridx} 回答 #{ridx}") if big else f"BBB_{ridx} 短回答"}
    return [user, ans]


def _build_rounds(n: int, *, big: bool = True) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": "你是 EduAgent 助手，保持前缀稳定。"}]
    for i in range(1, n + 1):
        msgs.extend(_round_msg(i, big=big))
    return msgs


class TestCompactionTriggerAndBudget:
    def test_estimate_tokens(self):
        assert c.estimate_tokens("中文测试") >= 4
        assert c.estimate_tokens("abcd") >= 1

    def test_no_compaction_below_threshold(self):
        small = _build_rounds(2, big=False)
        r = c.compact_messages(small)
        assert r["applied"] is False

    def test_compaction_applied_over_threshold_and_under_budget(self):
        """GWT①：>6000 token → 压缩后 ≤6000。"""
        big = _build_rounds(20)  # 每轮 ~600 token × 20 ≈ 12000+ > 6000
        before = sum(c.estimate_tokens(m["content"]) for m in big)
        assert before > 6000, f"构造应超阈值: {before}"
        r = c.compact_messages(big)
        assert r["applied"] is True
        assert r["trigger"] == "compaction"
        assert r["after_tokens"] <= 6000, f"压缩后应 ≤6000: {r['after_tokens']}"
        assert r["before_tokens"] == before

    def test_keeps_recent_rounds_original(self):
        """最近 6 轮原文保留（末轮内容在 kept；首轮已进摘要，不在原文）。"""
        big = _build_rounds(20)
        r = c.compact_messages(big, keep_rounds=6)
        kept_blob = json.dumps(r["kept_messages"], ensure_ascii=False)
        assert "AAA_20" in kept_blob, "最近轮原文应保留"
        assert "AAA_15" in kept_blob, "最近 6 轮内原文应保留"
        # AAA_1 是 AAA_1x 的子串，用带空格的完整标记做边界判断，避免把「第 1 轮仅剩摘要」误判
        assert "AAA_1 问题#1" not in kept_blob, "首轮原文已进摘要（不再保留原文）"

    def test_summary_structured_semantics(self):
        """summary 保留结构化决策语义（profile_updates/pending_tasks/decisions/facts 4 键）。"""
        msgs = _build_rounds(20)
        # 注入一条「偏好」信号到早期轮（会被压缩进摘要，而非末尾保留轮），验证结构化抽取有效
        for i, m in enumerate(msgs):
            if m.get("content") == "AAA_3 问题#3":
                msgs[i]["content"] = "记住：我偏好用番茄工作法学习，目标是通过雅思（问题#3）"
        r = c.compact_messages(msgs, keep_rounds=6)
        assert r["summary_json"], "应有结构化摘要"
        obj = json.loads(r["summary_json"])
        assert set(obj.keys()) == {"profile_updates", "pending_tasks", "decisions", "facts"}
        assert obj["profile_updates"], "结构化 profile_updates 应非空"


class TestContextEdit:
    def test_remove_completed_tool_pairs_keep_intent(self):
        """R4 context editing：删除已完成「工具调用+结果」对，保留用户意图/系统消息。"""
        msgs = [
            {"role": "system", "content": "stable prefix"},
            {"role": "user", "content": "帮我算 1+1"},
            {"role": "assistant", "content": '{"tool":"add","args":{"a":1,"b":2}}'},
            {"role": "tool", "content": '[工具 add 返回] {big result json ' + "结" * 1500 + "}"},
            {"role": "assistant", "content": "结果是 3"},
            {"role": "user", "content": "下一个问题"},
        ]
        r = c.context_edit(msgs)
        assert r["edited"] is True
        assert r["removed"] == 2, "应删除工具调用+结果 2 条"
        assert r["removed_tokens"] > 1500, "删除应释放大 token"
        kept = [m["content"] for m in r["messages"]]
        assert "stable prefix" in kept and "下一个问题" in kept and "帮我算 1+1" in kept
        assert "结" * 1500 not in r["messages"][-1]["content"], "工具结果不应残留在最新消息"

    def test_context_edit_preferred_over_compaction(self):
        """GWT③ R4：触发策略 context_edit 优先，仍超才 compaction。"""
        msgs = [{"role": "user", "content": "Q"},
                {"role": "assistant", "content": '{"tool":"x","args":{}}'},
                {"role": "tool", "content": '[工具 x 返回] ' + "大" * 7000}]
        policy = c.compaction_policy(msgs)
        # context_edit 能删掉庞大的工具输出 → 优先轻量
        assert policy in ("none", "context_edit"), f"应优先轻量: {policy}"

    def test_tool_result_clearing_one_line(self):
        """tool result clearing：超出保留轮的工具结果 → 1 行结论（原文表述已 artifact）。"""
        msgs = _build_rounds(10)  # 10 轮
        # 第 1 轮后接一条大工具结果（属最早轮，应被精简为一行）
        old_tool = {"role": "tool", "content": '[工具 probe 返回] ' + "A" * 3000}
        msgs.insert(4, old_tool)
        r = c.tool_result_clearing(msgs, keep_rounds=6)
        assert r["cleared"] >= 1
        assert "\n" not in r["results"][0]["cleared_to"], "结论应单行"


# ============================================================
# GWT② artifact 分流：>1500 token → 蒸馏进 artifact，流内 1 行结论
# ============================================================
class TestArtifactShunting:
    @pytest.mark.asyncio
    async def test_large_output_distilled_to_artifact(self):
        st = ArtifactShuntStore()
        raw = {"data": [{"i": i, "content": "字" * 120} for i in range(50)]}  # ~6000 CJK > 1500
        d = await distill_tool_output("search_knowledge", raw, store=st)
        assert d["distilled"] is True
        assert d["artifact_ref"], "应写入 artifact 引用"
        assert d["tokens"] > 1500
        assert "\n" not in d["conclusion"], "流内仅 1 行结论"
        # artifact 原文可读回（原始 JSON 保留）
        loaded = await st.read(d["artifact_ref"])
        assert loaded is not None
        assert len(loaded["raw"]["data"]) == 50
        assert "artifact" in d["conclusion"], "结论应标注原文已入 artifact"

    @pytest.mark.asyncio
    async def test_small_output_not_distilled(self):
        d = await distill_tool_output("add", '{"result": 3}', store=ArtifactShuntStore())
        assert d["distilled"] is False
        assert d["artifact_ref"] is None

    @pytest.mark.asyncio
    async def test_shunt_batch_distilled_count(self):
        calls = [
            {"tool_name": "a", "result": "ok"},
            {"tool_name": "big", "result": {"raw": "字" * 3000}},
        ]
        out = await shunt_tool_outputs(calls, store=ArtifactShuntStore())
        assert out["distilled_count"] == 1
        flow = {f["tool_name"]: f for f in out["flow"]}
        assert flow["big"]["distilled"] is True
        assert flow["big"]["artifact_ref"]
        assert flow["a"]["distilled"] is False

    @pytest.mark.asyncio
    async def test_large_tool_output_ttl_1h(self):
        """对齐「TTL 1h」（ARTIFACT_TTL=3600）。"""
        from app.config import settings
        assert int(settings.ARTIFACT_TTL) == 3600


# ============================================================
# GWT③ Redis 防过载：全局闸 + 会话并发 ≤2 + BLPOP 排队超时
# ============================================================
class TestConcurrencyGuard:
    def _guard(self, **kw):
        bas = {"redis": None, "global_limit": 8, "user_max": 2, "queue_timeout": 0.3}
        bas.update(kw)
        return ConcurrencyGuard(**bas)

    @pytest.mark.asyncio
    async def test_user_3rd_concurrent_rejected(self):
        """单用户并发第 3 个被拒（≤2）。"""
        g = self._guard()
        assert await g.acquire_user_slot(1) is True
        assert await g.acquire_user_slot(1) is True
        assert await g.acquire_user_slot(1) is False, "第 3 个并发应被拒"
        await g.release_user_slot(1)
        assert await g.acquire_user_slot(1) is True, "释放一个后应可再进"

    @pytest.mark.asyncio
    async def test_acquire_entry_user_over_limit_reason(self):
        g = self._guard()
        await g.acquire_user_slot(5)
        await g.acquire_user_slot(5)
        e = await g.acquire(5)
        assert e["ok"] is False
        assert e["reason"] == "user_concurrent_over_limit"

    @pytest.mark.asyncio
    async def test_global_gate_full_queue_timeout_friendly(self):
        """全局并发闸满 + 无释放 → BLPOP 排队超时，返回友好提示而非堆积。"""
        g = self._guard(global_limit=2)
        # 2 个不同用户占满全局闸
        e1 = await g.acquire(11)
        e2 = await g.acquire(12)
        assert e1["ok"] and e2["ok"] and e1["reason"] == "direct"
        # 第 3 个请求：闸满 → 入队 → 短超时无 worker 释放 → 友好提示
        e3 = await g.acquire(13)
        assert e3["ok"] is False
        assert e3["reason"] == "queue_timeout"
        assert "排队超时" in e3["message"], "应返回友好提示而非堆积"
        # 释放后闸位恢复，新请求直接进入
        await g.release(11)
        e4 = await g.acquire(14)
        assert e4["ok"] is True and e4["reason"] == "direct"
        await g.release(14)
        await g.release(12)

    @pytest.mark.asyncio
    async def test_release_pairs_keeps_gate_consistent(self):
        """acquire/release 成对：释放后并发计数回落不泄漏。"""
        g = self._guard(global_limit=2)
        await g.acquire(21)
        assert await g.global_inflight() == 1
        await g.release(21)
        assert await g.global_inflight() == 0
        assert await g.user_inflight(21) == 0

    @pytest.mark.asyncio
    async def test_queue_primitive_pops_within_timeout(self):
        """队列原语：先入队者 BLPOP 在超时内取出（排队削峰）。"""
        g = self._guard(queue_timeout=1.0)
        await g.enqueue({"k": "v"})
        job = await g.await_queue(timeout=0.5)
        assert job == {"k": "v"}

    @pytest.mark.asyncio
    async def test_zset_sharded_many_entries(self):
        """ZSET 分片：多条目写入后 zrange 合并返回全量（防单 key 大 key）。"""
        g = self._guard()
        for i in range(60):
            await g.zadd_sharded("rank", f"u{i}", float(i))
        rows = await g.zrange_sharded("rank")
        assert len(rows) == 60, "分片后仍应取回全部条目"
        assert rows[0][0] == "u59", "应按分数降序"

    @pytest.mark.asyncio
    async def test_scan_bigkeys_graceful_no_redis(self):
        """bigkey 扫描在无 Redis 时优雅返回空（不抛）。"""
        g = self._guard(redis=None)
        assert await g.scan_bigkeys() == []


def _run(coro):
    return asyncio.run(coro)


# 真 Redis 可选：大 key 治理实证（无 Redis 时跳过）
@pytest.mark.asyncio
async def test_bigkey_scan_on_real_redis():
    try:
        from app.database import get_redis
        r = get_redis()
        await r.ping()
    except Exception:
        pytest.skip("Redis 不可用，跳过真库 bigkey 扫描")
    g = ConcurrencyGuard(redis=r)
    await r.set("task26_bigkey_probe", "x" * (1024 * 1024 + 10))
    big = await g.scan_bigkeys(threshold=1024 * 1024)
    await r.delete("task26_bigkey_probe")
    keys = [b["key"] for b in big]
    assert any("task26_bigkey_probe" in k for k in keys), f"应扫描到超过 1MB 的 key: {keys}"