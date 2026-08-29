# -*- coding: utf-8 -*-
"""task39 GWT⑤：令牌桶窗口边界复测（G1-② 复测项，量化版）。

与 tests/test_contract_task_g1_token_bucket.py 的分工：
  契约测试断言「边界不允许第二次满额」这一布尔事实（点测）；
  本脚本做**量化复测**——把 60s 窗口边界的突发放大成可观测的数字：
    · 固定窗口：任取 60s 滑窗，最大放行量 / 额定速率 = 突发倍率（理论 ~2×）
    · 令牌桶  ：同样滑窗统计，突发倍率应 ≈1×（上限 = capacity/rate 的 BURST_RATIO）
  并给出 BURST_RATIO 取不同值时的倍率曲线，供生产调参。

用法：
    .venv\\Scripts\\python scripts/verify_task39_token_bucket_boundary.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.guard import TokenBucket  # noqa: E402
from app.config import settings  # noqa: E402

RATE = 600.0          # tokens/min（与契约测试同量级）
WINDOW = 60.0         # 窗口秒
SIM_SECONDS = 300.0   # 模拟 5 分钟 = 5 个窗口边界
STEP = 0.1            # 事件步长（秒）


class FixedWindow:
    """对照实现：60s 固定窗口（app/middleware/rate_limit.py 的语义）。"""

    def __init__(self, rate: float, window: float = WINDOW) -> None:
        self.rate = rate
        self.window = window
        self.used = 0.0
        self.reset_at = window

    def consume(self, amount: float, now: float) -> bool:
        if now >= self.reset_at:
            self.used = 0.0
            self.reset_at = now + self.window
        if self.used + amount > self.rate:
            return False
        self.used += amount
        return True


def _max_sliding_window(events: list[tuple[float, float]], window: float = WINDOW) -> float:
    """统计任意 60s 滑窗内的最大放行量（双指针）。"""
    best = 0.0
    acc = 0.0
    left = 0
    for right, (t, amt) in enumerate(events):
        acc += amt
        while events[right][0] - events[left][0] >= window:
            acc -= events[left][1]
            left += 1
        best = max(best, acc)
    return best


def _simulate(limiter, label: str) -> tuple[float, float]:
    """两种最坏流量叠加，取更坏的滑窗峰值。

    只跑「每步贪婪吃满」是测不出窗口边界突发的：那种流量会把额度在窗口**开头**
    就吃光，窗口末尾与下一窗口开头之间隔着整整 60s，根本不构成突发。
    真正的固定窗口 2× 突发来自**边界邻接**：临界点前 0.1s 打满 + 临界点后 0.1s 再打满。

      A. 边界攻击：在每个 60s 边界的 ±0.1s 各打满一次额定量
      B. 饱和贪婪：以 3× 速率持续灌，能吃就吃（测长跑稳态是否被削平）
    """
    # A. 边界攻击
    events: list[tuple[float, float]] = []
    k = 1
    while k * WINDOW < SIM_SECONDS:
        boundary = k * WINDOW
        for t in (boundary - 0.1, boundary + 0.1):
            left = RATE
            while left > 0 and limiter.consume(min(20.0, left), now=t):
                events.append((t, min(20.0, left)))
                left -= min(20.0, left)
        k += 1
    peak_a = _max_sliding_window(events)

    # B. 饱和贪婪（独立实例，避免与 A 互相污染额度）
    events_b: list[tuple[float, float]] = []
    t = 0.0
    while t < SIM_SECONDS:
        budget = RATE * 3.0 * STEP / WINDOW * 10  # 3× 速率的每步投放量（放大便于吃满）
        while budget > 0 and limiter.consume(min(20.0, budget), now=t):
            events_b.append((t, min(20.0, budget)))
            budget -= min(20.0, budget)
        t += STEP
    peak_b = _max_sliding_window(events_b)

    peak = max(peak_a, peak_b)
    return peak, peak / RATE


def main() -> int:
    print(f"task39 GWT⑤ 令牌桶窗口边界复测 — rate={RATE}/min window={WINDOW}s sim={SIM_SECONDS}s")
    print(f"配置现状：TOKEN_BUCKET_ENABLED={settings.TOKEN_BUCKET_ENABLED} "
          f"BURST_RATIO={getattr(settings, 'TOKEN_BUCKET_BURST_RATIO', '?')} "
          f"REFILL_WINDOW_SEC={getattr(settings, 'TOKEN_BUCKET_REFILL_WINDOW_SEC', '?')}")

    fw_peak, fw_ratio = _simulate(FixedWindow(RATE), "fixed")
    print(f"\n[固定窗口] 任意 60s 滑窗峰值放行 = {fw_peak:.0f} tokens  突发倍率 = {fw_ratio:.2f}×")

    results = []
    for ratio in (1.0, 1.5, 2.0):
        tb = TokenBucket(
            refill_per_min=RATE,
            capacity=RATE * ratio,
            refill_window_sec=WINDOW,
            now=0.0,
        )
        peak, r = _simulate(tb, f"tb{ratio}")
        results.append((ratio, peak, r))
        print(f"[令牌桶 capacity={ratio:.1f}×rate] 60s 滑窗峰值 = {peak:.0f} tokens  突发倍率 = {r:.2f}×")

    print("\n=== 判定（GWT⑤：边界不超） ===")
    ok = True
    if fw_ratio < 1.8:
        print(f"  [FAIL] 固定窗口未复现 ~2× 突发（{fw_ratio:.2f}×），对照失效")
        ok = False
    else:
        print(f"  [PASS] 固定窗口复现窗口边界 {fw_ratio:.2f}× 突发（对照组有效）")

    base_ratio_val, base_peak, base_ratio = results[0]
    if base_ratio > 1.1:
        print(f"  [FAIL] 令牌桶(BURST_RATIO=1.0) 突发倍率 {base_ratio:.2f}× 超过 1.1×")
        ok = False
    else:
        print(f"  [PASS] 令牌桶(BURST_RATIO=1.0) 突发倍率 {base_ratio:.2f}× ≤1.1×（边界不超）")

    if base_peak >= fw_peak:
        print(f"  [FAIL] 令牌桶峰值 {base_peak:.0f} 未低于固定窗口 {fw_peak:.0f}")
        ok = False
    else:
        print(f"  [PASS] 令牌桶峰值 {base_peak:.0f} 显著低于固定窗口 {fw_peak:.0f}"
              f"（削减 {100*(1-base_peak/fw_peak):.0f}%）")

    print("\n=== BURST_RATIO 调参建议 ===")
    for ratio, peak, r in results:
        print(f"  BURST_RATIO={ratio:.1f} → 峰值 {peak:.0f} tokens（{r:.2f}×）；"
              f"允许首波突发 {peak:.0f} 后按 {RATE/WINDOW:.1f} tokens/s 匀速放行")

    print("\n" + ("✅ GWT⑤ 复测通过" if ok else "❌ GWT⑤ 复测失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
