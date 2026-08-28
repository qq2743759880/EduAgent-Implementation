"""task-G1-③ 契约测试：estimate_request_tokens 强制 request_meta（无则告警）+ 接入调用点。

验收目标：
- 无 request_meta 时 estimate_request_tokens 发出告警（不再静默回退默认 2000）；
- 有 request_meta 时按 system+history+query+max_tokens 精确预估；
- acquire 实际消费 request_meta（调用点已接入），estimate 不再恒等于默认兜底值。

依据：app/ai/guard.py（estimate_request_tokens 增加告警 + acquire 透传 request_meta）、
app/ai/graph.py（run_agent 入口 acquire 传入 request_meta）、
app/config.py（LLM_MAX_TOKENS 作为 max_tokens 来源）。
"""
import asyncio
import sys

sys.path.insert(0, ".")

from app.config import settings
from app.ai import guard as guard_mod
from app.ai.guard import TokenBudgetGuard
from app.ai.compaction import estimate_tokens


def test_estimate_warns_without_request_meta():
    g = TokenBudgetGuard(redis=None, default_tokens=2000)
    recorded = []
    orig = guard_mod.logger.warning
    guard_mod.logger.warning = lambda *a, **k: recorded.append(a)
    try:
        est = g.estimate_request_tokens(None)
    finally:
        guard_mod.logger.warning = orig
    assert est == 2000, "无 meta 应回退默认 2000"
    assert len(recorded) >= 1, "无 request_meta 必须发出告警"


def test_estimate_precise_with_request_meta():
    g = TokenBudgetGuard(redis=None, default_tokens=2000)
    q = "什么是 XSS 跨站脚本攻击"
    q_tokens = estimate_tokens(q)
    # 全字段精确
    est = g.estimate_request_tokens({
        "system_tokens": 120, "history_tokens": 60,
        "query": q, "max_tokens": int(settings.LLM_MAX_TOKENS),
    })
    assert est == 120 + 60 + q_tokens + int(settings.LLM_MAX_TOKENS), f"精确预估不符: {est}"
    # 仅 query + max_tokens 也应 > 默认兜底（证明不再恒等于 2000）
    est2 = g.estimate_request_tokens({"query": q, "max_tokens": int(settings.LLM_MAX_TOKENS)})
    assert est2 > 2000, "带 query 的预估应大于默认兜底 2000"
    # 全 0 → 回退默认（但不告警，因为传了 meta）
    est3 = g.estimate_request_tokens({})
    assert est3 == 2000


async def test_acquire_uses_request_meta():
    g = TokenBudgetGuard(redis=None, default_tokens=2000, user_quota=10_000_000)
    res = await g.acquire(1, request_meta={"query": "请解释 CSRF 原理", "max_tokens": int(settings.LLM_MAX_TOKENS)})
    assert res.get("ok") is True, f"acquire 应准入: {res}"
    # estimate 来自 request_meta（query+max_tokens），不是裸默认 2000
    assert res.get("estimate", 0) > 2000, "acquire 应消费 request_meta 做精确预估"


if __name__ == "__main__":
    test_estimate_warns_without_request_meta()
    test_estimate_precise_with_request_meta()
    asyncio.run(test_acquire_uses_request_meta())
    print("ALL OK: G1-③ estimate_request_tokens 强制 request_meta（无则告警）+ 调用点接入")
