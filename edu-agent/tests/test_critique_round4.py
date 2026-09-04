# -*- coding: utf-8 -*-
"""critique round4（竞品对标复批）：支付对账金额精度 + LLM Retry-After 尊重。

对标对象：
- 支付对账 vs 支付宝/微信「金额以分为单位」对账口径（规避浮点尾差误报）
- LLM 重试退避 vs OpenAI/Anthropic 官方 SDK「必读 Retry-After 响应头」

本文件全部为可独立运行的单元/契约测试，无真实后端依赖。
"""
from __future__ import annotations

from app.core import retry as retry_mod
from app.domains.trade.payment import repository as pay_repo


# ════════════════════════════════════════════════════════════
# 一、支付对账金额精度（分单位整数比较，防浮点尾差误报）
# ════════════════════════════════════════════════════════════
class TestReconcileAmountPrecision:
    """run_reconcile 的 AMOUNT_MISMATCH 判定必须用分单位整数比较。"""

    def _run(self, monkeypatch, paid_rows):
        async def fake_fetch_all(sql, *args, **kws):
            return paid_rows

        monkeypatch.setattr(pay_repo, "fetch_all", fake_fetch_all)
        return pay_repo.PaymentReconcileRepo().run_reconcile(institution_id=0)

    def test_float_sum_equal_payable_no_mismatch(self, monkeypatch):
        """amount=0.1+0.05（浮点 0.15000000000000002）vs payable=0.15：
        旧实现 `!=` 会误报 AMOUNT_MISMATCH；分单位整数比较后不误报。"""
        import asyncio

        paid = [{
            "payment_no": "P1", "order_id": 1, "amount": 0.1 + 0.05,
            "order_no": "O1", "payable_amount": 0.15, "order_status": "paid",
        }]
        result = asyncio.run(self._run(monkeypatch, paid))
        types = [a["type"] for a in result["anomalies"]]
        assert "AMOUNT_MISMATCH" not in types, (
            f"浮点尾差被误报为金额不一致：anomalies={result['anomalies']}"
        )
        assert result["total_paid_payments"] == 1
        assert result["reconciled_amount"] == round(0.15, 2)

    def test_real_mismatch_still_detected(self, monkeypatch):
        """amount=0.20 vs payable=0.15 的真实不一致必须仍被检出（不因改整数比较而漏报）。"""
        import asyncio

        paid = [{
            "payment_no": "P2", "order_id": 2, "amount": 0.20,
            "order_no": "O2", "payable_amount": 0.15, "order_status": "paid",
        }]
        result = asyncio.run(self._run(monkeypatch, paid))
        types = [a["type"] for a in result["anomalies"]]
        assert "AMOUNT_MISMATCH" in types
        assert result["ok"] is False

    def test_refund_status_exempt(self, monkeypatch):
        """退款单（partial_refunded/refunded）金额差异属预期，不应计入 AMOUNT_MISMATCH。"""
        import asyncio

        paid = [{
            "payment_no": "P3", "order_id": 3, "amount": 0.10,
            "order_no": "O3", "payable_amount": 0.15, "order_status": "refunded",
        }]
        result = asyncio.run(self._run(monkeypatch, paid))
        types = [a["type"] for a in result["anomalies"]]
        assert "AMOUNT_MISMATCH" not in types


# ════════════════════════════════════════════════════════════
# 二、LLM 重试退避尊重 Retry-After（对标 OpenAI/Anthropic 官方 SDK）
# ════════════════════════════════════════════════════════════
class TestRetryAfterBackoff:
    def test_next_backoff_rate_limit_respects_retry_after(self):
        for attempt in (1, 2, 3):
            wait = retry_mod.next_backoff("429", attempt, retry_after=5.0)
            assert wait == 5.0, f"attempt={attempt}: 应尊重 Retry-After=5s，实得 {wait}"
            # 仍叠加 jitter（若开启）
            wait_j = retry_mod.next_backoff("429", attempt, retry_after=5.0, jitter=1.0)
            assert 5.0 <= wait_j <= 6.0

    def test_next_backoff_caps_retry_after(self):
        """Retry-After 超上限仍封顶，防死等。"""
        wait = retry_mod.next_backoff("429", 1, cap=30.0, retry_after=999.0)
        assert wait == 30.0

    def test_next_backoff_timeout_respects_retry_after(self):
        """非限流（如 503 超时）带 Retry-After 同样尊重。"""
        wait = retry_mod.next_backoff("timeout", 2, retry_after=3.0)
        assert wait == 3.0

    def test_no_retry_after_falls_back(self):
        """缺 Retry-After 时回退默认指数（2^attempt 封顶 30）。"""
        wait = retry_mod.next_backoff("429", 1)
        assert wait == 2.0
        wait5 = retry_mod.next_backoff("429", 5)
        assert wait5 == 30.0

    def test_plan_retry_passes_retry_after(self):
        plan = retry_mod.plan_retry("429", 1, retry_after=4.0)
        assert plan["wait"] == 4.0
        assert plan["category"] == "rate_limit"
        assert plan["retry"] is True


class TestRetryAfterParse:
    def test_retry_after_from_header(self):
        from app.chat.generator import _retry_after_from

        class R:
            headers = {"Retry-After": "7"}

        assert _retry_after_from(R()) == 7.0

    def test_retry_after_missing(self):
        from app.chat.generator import _retry_after_from

        class R:
            headers = {}

        assert _retry_after_from(R()) is None

    def test_retry_after_invalid(self):
        from app.chat.generator import _retry_after_from

        class R:
            headers = {"Retry-After": "HTTP-date-ish"}

        assert _retry_after_from(R()) is None


class TestCallChatRetryAfterWired:
    def test_call_chat_with_retry_sleeps_retry_after(self, monkeypatch):
        from types import SimpleNamespace

        from app.chat import generator as gen_mod
        from app.chat.generator import _ChatClient

        sleeps = []
        # generator.py 顶部 `import time`，用带 .sleep 的假模块替换，捕获 sleep 实参。
        monkeypatch.setattr(
            gen_mod, "time", SimpleNamespace(sleep=lambda s: sleeps.append(s)),
        )

        client = _ChatClient.__new__(_ChatClient)
        calls = {"n": 0}

        def fake_call(**kw):
            calls["n"] += 1
            if calls["n"] == 1:
                exc = RuntimeError("LLM HTTP 429: rate limited")
                exc.retry_after = 7.0  # 模拟响应携带 Retry-After 头
                raise exc
            return "ok"

        monkeypatch.setattr(client, "call_chat", fake_call)

        out = client.call_chat_with_retry(
            messages=[], model="fast", temperature=0.0, max_tokens=1, timeout=5.0,
        )
        assert out == "ok"
        assert calls["n"] == 2, "触发一次 429 重试后成功"
        assert sleeps and sleeps[0] == 7.0, f"重试前应 sleep(7)（尊重 Retry-After），实得 {sleeps}"