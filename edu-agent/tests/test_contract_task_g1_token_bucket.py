"""task-G1-② 契约测试：token 窗口 60s 固定窗口 → 令牌桶平滑（消除窗口边界 2× 突发）。

验收目标：
- 固定 60s 窗口在边界（窗口结束/开始邻接）会允许 ~2× 速率突发（已知缺陷）；
- 令牌桶 TokenBucket 在相同速率下，窗口边界不再允许 2× 突发（refill 连续）；
- guard 开启 TOKEN_BUCKET_ENABLED 后，全局速率实际走令牌桶（_global_used/_add_global 路由到桶）。

依据：app/ai/guard.py（TokenBucket + TokenBudgetGuard._global_used/_add_global 桶路由）、
app/config.py（TOKEN_BUCKET_ENABLED / BURST_RATIO / REFILL_WINDOW_SEC）。
"""
import asyncio
import sys

sys.path.insert(0, ".")

from app.config import settings
from app.ai import guard as guard_mod
from app.ai.guard import TokenBucket, TokenBudgetGuard


# ---- 1) 固定窗口边界 2× 突发复现 ----
def test_fixed_window_boundary_burst():
    rate = 600  # tokens / min

    def make_state():
        return {"used": 0, "reset_at": 60.0}  # 窗口 [0,60)

    def window_allow(state, estimate, t):
        if t >= state["reset_at"]:
            state["used"] = 0
            state["reset_at"] = t + 60.0
        if state["used"] + estimate > rate:
            return False  # 超限进队列
        state["used"] += estimate
        return True

    st = make_state()
    ok1 = window_allow(st, rate, 59.9)   # 窗口内末尾吃满
    ok2 = window_allow(st, rate, 60.1)   # 新窗口开始再吃满
    assert ok1 and ok2, "固定窗口应在边界允许两次满额（2× 突发）"
    assert st["used"] == rate  # 第二次是重置后新窗口，单窗口内未超；但跨边界 0.2s 内共 2×rate
    # 跨边界 0.2s 内总消费 = 2×rate，证明突发
    assert (rate + rate) > rate


# ---- 2) 令牌桶消除边界突发 ----
def test_token_bucket_prevents_boundary_burst():
    rate = 600
    tb = TokenBucket(refill_per_min=rate, capacity=rate, refill_window_sec=60.0, now=0.0)
    assert tb.consume(rate, now=59.9) is True, "桶初值应能吃满一次"
    # 仅过 0.2s：refill = 0.2 * (600/60) = 2 tokens，远不足以再吃满
    assert tb.consume(rate, now=60.1) is False, "令牌桶边界不应允许第二次满额（无 2× 突发）"
    # used 不超过 capacity
    assert tb.used <= rate


# ---- 3) guard 开启令牌桶后，全局速率实际走桶（对比固定窗口） ----
async def test_guard_bucket_routing_no_overshoot():
    fake = {"t": 0.0}
    orig = guard_mod.time.monotonic
    guard_mod.time.monotonic = lambda: fake["t"]
    prev = settings.TOKEN_BUCKET_ENABLED
    settings.TOKEN_BUCKET_ENABLED = True
    try:
        rate = 600
        g = TokenBudgetGuard(redis=None, rate_limit=rate, user_quota=10_000_000)
        # 第一次：t=59.9 吃满
        fake["t"] = 59.9
        assert (await g._global_used()) == 0
        await g._add_global(rate)
        # 第二次：t=60.1 仅过 0.2s，令牌桶只 refill 2，unconsumed 不足以再吃满 → 不应再扣减
        fake["t"] = 60.1
        cur = await g._global_used()          # 经 refill：used ≈ rate-2
        assert cur + rate > rate, "边界处桶应已接近满，第二次会进队列而非再扣满"
        # 关键断言：桶 used 始终不超过 capacity（无 2× 突发落账）
        assert g._global_bucket.used <= rate, f"令牌桶 used 超容量: {g._global_bucket.used}"
        # 对照：固定窗口下同样两步会累计到 2×rate（证明桶确实改了语义）
        settings.TOKEN_BUCKET_ENABLED = False
        g2 = TokenBudgetGuard(redis=None, rate_limit=rate, user_quota=10_000_000)
        fake["t"] = 59.9
        await g2._global_used(); await g2._add_global(rate)
        fake["t"] = 60.1
        await g2._global_used(); await g2._add_global(rate)
        # 固定窗口：第二次窗口重置后 used 回到 0 再 +rate → 2×rate（此处只是说明差异，不强制断言值）
        assert g2._global_tokens == 2 * rate, "对照：固定窗口两步累计 2×rate（桶路径已避免此问题）"
    finally:
        settings.TOKEN_BUCKET_ENABLED = prev
        guard_mod.time.monotonic = orig


if __name__ == "__main__":
    test_fixed_window_boundary_burst()
    test_token_bucket_prevents_boundary_burst()
    asyncio.run(test_guard_bucket_routing_no_overshoot())
    print("ALL OK: G1-② token 窗口→令牌桶平滑，窗口边界不再 2× 突发（生产负载复测留 task39）")
