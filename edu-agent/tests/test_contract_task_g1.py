# -*- coding: utf-8 -*-
"""task-G1 契约测试：token 级并发预算 + 用户分级队列 + 智能重试退避（AC1~AC4）。

执行方式：纯内存后端（redis=None），无需 Redis/在线 LLM；token 预估与排队行为随时可测。
GWT：
① token 速率闸：预估 token 累计超 LLM_TOKEN_RATE_LIMIT_PER_MIN → 排队不拒绝（进队列，非硬拒）。
② L3 优先队列：L1×5 与 L3×1 同队，消费者轮询 L3 先出队（QUEUE_PRIORITY_ORDER 生效）。
③ 用户配额：用户 X 单分钟 token 超 USER_TOKEN_QUOTA_PER_MIN → reason="user_token_quota_exceeded" 友好拒绝。
④ 智能退避：429→指数(2/4/8…≤30)；超时→线性(1s)最多2次；模型错误→切备用模型(FAST↔STRONG)。
⑤ 兼容回归：请求数并发闸保留为第二道防线（global_limit 仍生效）；task26 既有 guard 契约全 PASS。
"""
from __future__ import annotations

import asyncio

import pytest

from app.ai.compaction import estimate_tokens
from app.ai.guard import ConcurrencyGuard, TokenBudgetGuard
from app.core import retry as R


def _tb(**kw):
    """构造内存后端 TokenBudgetGuard，默认放开请求数/配额闸以隔离 token 维度。"""
    base = dict(
        redis=None,
        rate_limit=600_000,
        user_quota=10_000_000,
        global_limit=100,
        user_max=100,
        queue_timeout=2.0,
        l3_timeout=2.0,
    )
    base.update(kw)
    return TokenBudgetGuard(**base)


# ============================================================
# 预备：token 预估四段求和正确
# ============================================================
class TestEstimateTokens:
    def test_default_when_no_meta(self):
        g = _tb()
        assert g.estimate_request_tokens(None) == 2000

    def test_single_segment(self):
        g = _tb()
        assert g.estimate_request_tokens({"max_tokens": 1500}) == 1500

    def test_four_segments_sum(self):
        g = _tb()
        q = "中文问题"  # estimate_tokens -> 4 CJK + 1 = 5
        expected = 100 + 200 + estimate_tokens(q) + 500
        got = g.estimate_request_tokens(
            {"system_tokens": 100, "history_tokens": 200, "query": q, "max_tokens": 500}
        )
        assert got == expected

    def test_query_string_estimated(self):
        g = _tb()
        # 仅给 query 字符串，无 query_tokens → 用 compaction.estimate_tokens 估算
        assert g.estimate_request_tokens({"query": "hello 世界"}) > 0

    def test_all_zero_falls_back_to_default(self):
        g = _tb(default_tokens=2000)
        assert g.estimate_request_tokens({"system_tokens": 0, "max_tokens": 0}) == 2000


# ============================================================
# AC1：token 速率闸（超限排队不拒绝）
# ============================================================
class TestTokenRateGate:
    @pytest.mark.asyncio
    async def test_over_rate_queues_not_rejects(self):
        """8 个 L1 闲聊（1500tok/个）累计超速率 → 后续进队列，不直接拒绝。"""
        g = _tb(rate_limit=5000)  # 3 个即达上限（4500），第 4 个起超限
        meta = {"max_tokens": 1500}
        r1 = await g.acquire(1, request_meta=meta)
        r2 = await g.acquire(2, request_meta=meta)
        r3 = await g.acquire(3, request_meta=meta)
        assert r1["ok"] and r2["ok"] and r3["ok"]
        assert r1["reason"] == "direct"
        # 第 4 个触发速率超限 → 排队等候（不拒绝）
        t4 = asyncio.create_task(g.acquire(4, request_meta=meta))
        await asyncio.sleep(0.05)
        assert not t4.done(), "速率超限应入队等候而非立即返回"
        # 释放一个 → 预算释放 → 唤醒排队者（按优先级）
        await g.release(1)
        r4 = await t4
        assert r4["ok"] is True
        assert r4["reason"] == "queued_token_rate", "应标记为排队准入（非拒绝）"
        # 全程无硬拒绝
        for r in (r1, r2, r3, r4):
            assert r["ok"] is True

    @pytest.mark.asyncio
    async def test_light_traffic_not_rejected_by_token_gate(self):
        """token 预算宽松时，8 个轻请求全部准入（不占满请求数闸而硬拒）；L3 亦可并行。"""
        g = _tb(rate_limit=1_000_000, global_limit=100)
        meta_l1 = {"max_tokens": 1500}
        meta_l3 = {"max_tokens": 8000}
        results = []
        for i in range(8):
            results.append(await g.acquire(i + 1, request_meta=meta_l1, effort="L1"))
        r_l3 = await g.acquire(99, request_meta=meta_l3, effort="L3")
        assert all(r["ok"] for r in results), "8 个轻请求应全部准入"
        assert r_l3["ok"] is True, "L3 大请求在 token 预算内应可并行"


# ============================================================
# AC2：L3 优先队列（L3 先于所有 L1 出队）
# ============================================================
class TestPriorityQueue:
    @pytest.mark.asyncio
    async def test_l3_before_l1(self):
        g = _tb()
        for i in range(5):
            await g.enqueue_token({"id": f"L1_{i}"}, priority="L1")
        await g.enqueue_token({"id": "L3_0"}, priority="L3")
        order = []
        for _ in range(6):
            item = await g.await_token(timeout=0.5)
            if item is None:
                break
            order.append(item["id"])
        assert order[0] == "L3_0", f"L3 应最先出队: {order}"
        # 全部 6 个都被消费，且 L3 唯一
        assert order.count("L3_0") == 1
        assert len(order) == 6

    @pytest.mark.asyncio
    async def test_priority_order_l3_l2_l1(self):
        g = _tb()
        await g.enqueue_token({"id": "L1"}, priority="L1")
        await g.enqueue_token({"id": "L2"}, priority="L2")
        await g.enqueue_token({"id": "L3"}, priority="L3")
        first = await g.await_token(timeout=0.5)
        second = await g.await_token(timeout=0.5)
        third = await g.await_token(timeout=0.5)
        assert [first["id"], second["id"], third["id"]] == ["L3", "L2", "L1"]


# ============================================================
# AC3：用户配额（超配额友好拒绝）
# ============================================================
class TestUserQuota:
    @pytest.mark.asyncio
    async def test_user_quota_exceeded_rejected_friendly(self):
        """用户 X 单分钟 token 超 USER_TOKEN_QUOTA_PER_MIN → reason=user_token_quota_exceeded。"""
        g = _tb(user_quota=3000, rate_limit=10_000_000)
        meta = {"max_tokens": 1500}
        r1 = await g.acquire(1, request_meta=meta)  # 1500
        r2 = await g.acquire(1, request_meta=meta)  # 累计 3000
        assert r1["ok"] and r2["ok"]
        r3 = await g.acquire(1, request_meta=meta)  # 3000+1500=4500 > 3000
        assert r3["ok"] is False
        assert r3["reason"] == "user_token_quota_exceeded"
        assert r3["message"], "应返回友好中文提示而非 500"
        assert "额度" in r3["message"]


# ============================================================
# AC4：智能重试退避（按错误类型动态）
# ============================================================
class TestSmartBackoff:
    def test_classify_error(self):
        assert R.classify_error(Exception("429 Too Many Requests")) == R.ErrorCategory.RATE_LIMIT
        assert R.classify_error(Exception("RateLimitError")) == R.ErrorCategory.RATE_LIMIT
        assert R.classify_error(Exception("asyncio.TimeoutError: timed out")) == R.ErrorCategory.TIMEOUT
        assert R.classify_error(Exception("invalid_request model_error")) == R.ErrorCategory.MODEL_ERROR
        assert R.classify_error(Exception("some unknown boom")) == R.ErrorCategory.UNKNOWN
        assert R.classify_error("rate_limit") == R.ErrorCategory.RATE_LIMIT
        assert R.classify_error(R.ErrorCategory.TIMEOUT) == R.ErrorCategory.TIMEOUT

    def test_rate_limit_exponential(self):
        # 429 → 指数 2^n 秒（n=重试次数），封顶 30 + jitter=0 确定性
        assert R.next_backoff("rate_limit", 1, jitter=0) == 2.0
        assert R.next_backoff("rate_limit", 2, jitter=0) == 4.0
        assert R.next_backoff("rate_limit", 3, jitter=0) == 8.0
        assert R.next_backoff("rate_limit", 10, jitter=0) == 30.0  # 封顶 30

    def test_timeout_linear_max2(self):
        # 超时 → 线性 1s/次
        assert R.next_backoff("timeout", 1, jitter=0) == 1.0
        assert R.next_backoff("timeout", 2, jitter=0) == 2.0
        assert R.next_backoff("timeout", 3, jitter=0) == 3.0  # 但 max_retries=2 → should_retry False

    def test_model_error_switch_no_wait(self):
        # 模型错误 → 立即切备用模型，不等待（wait=0）
        assert R.next_backoff("model_error", 1, jitter=0) == 0.0
        assert R.should_switch_model("model_error") is True
        assert R.should_switch_model("rate_limit") is False
        assert R.switch_model_source("fast") == "strong"
        assert R.switch_model_source("strong") == "fast"

    def test_should_retry_bounds(self):
        assert R.should_retry("rate_limit", 5) is True
        assert R.should_retry("rate_limit", 6) is False
        assert R.should_retry("timeout", 2) is True
        assert R.should_retry("timeout", 3) is False
        assert R.should_retry("model_error", 1) is False  # 不重试同模型

    def test_plan_retry_shape(self):
        pr = R.plan_retry("rate_limit", 1)
        assert pr["category"] == "rate_limit"
        assert pr["wait"] == 2.0
        assert pr["switch_model"] is False
        assert pr["retry"] is True
        assert pr["max_retries"] == 5


# ============================================================
# AC5：请求数并发闸保留为第二道防线（兼容回归）
# ============================================================
class TestRequestCountGatePreserved:
    @pytest.mark.asyncio
    async def test_global_gate_still_enforced(self):
        """token 预算宽松时，请求数并发闸（global_limit=2）仍生效 → 闸满排队。"""
        g = _tb(rate_limit=10_000_000, user_quota=10_000_000, global_limit=2, user_max=100)
        e1 = await g.acquire(11)
        e2 = await g.acquire(12)
        assert e1["ok"] and e2["ok"]
        t3 = asyncio.create_task(g.acquire(13))
        await asyncio.sleep(0.05)
        assert not t3.done(), "请求数闸满应排队"
        await g.release(11)
        r3 = await t3
        assert r3["ok"] is True

    @pytest.mark.asyncio
    async def test_base_concurrency_guard_unchanged(self):
        """基类 ConcurrencyGuard 行为未被破坏（task26 契约依赖）。"""
        g = ConcurrencyGuard(redis=None, global_limit=8, user_max=2, queue_timeout=0.3)
        assert await g.acquire_user_slot(1) is True
        assert await g.acquire_user_slot(1) is True
        assert await g.acquire_user_slot(1) is False, "第 3 并发应被拒"
        await g.release_user_slot(1)
        assert await g.acquire_user_slot(1) is True
