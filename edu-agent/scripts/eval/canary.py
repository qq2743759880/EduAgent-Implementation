# -*- coding: utf-8 -*-
"""
task-E1 金丝雀发布（AC4）：1% 流量分流 + 3 天观察 + 自动全量/回滚。

- canary_assign(uid)：确定性分流（同一 uid 始终同一桶），默认比例取自 CANARY_RATIO。
- canary_should_rollback(metrics)：任一观察指标（延迟 P95 / 正确性 / 工具成功率）越界即回滚。
- CanaryWindow：3 天观察窗口状态机，decide() 返回 promote / rollback / hold。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.config import settings


def canary_assign(uid, *, ratio: float | None = None) -> bool:
    """确定性分流：ratio<=0 永不进金丝雀；ratio>=1 全进；否则 hash(uid)%100 < ratio*100。"""
    ratio = ratio if ratio is not None else float(getattr(settings, "CANARY_RATIO", 0.01))
    if ratio <= 0.0:
        return False
    if ratio >= 1.0:
        return True
    return (hash(str(uid)) % 100) < int(ratio * 100 + 1e-9)


def canary_should_rollback(metrics: dict, *, thresholds: dict | None = None) -> bool:
    """任一指标异常即判定回滚。thresholds 可注入（测试/调参）。"""
    t = thresholds or {
        "latency_p95_ms": 2000.0,   # 延迟 P95 上限
        "correctness_min": 0.80,    # 正确性抽查下限
        "tool_success_min": 0.90,   # 工具成功率下限
    }
    if float(metrics.get("latency_p95_ms", 0)) > t["latency_p95_ms"]:
        return True
    if float(metrics.get("correctness", 1)) < t["correctness_min"]:
        return True
    if float(metrics.get("tool_success_rate", 1)) < t["tool_success_min"]:
        return True
    return False


@dataclass
class CanaryWindow:
    """3 天观察窗口状态机。started_at 一般为部署时刻。"""

    started_at: datetime
    ratio: float = 0.01
    days: int = 3

    def elapsed_days(self, now: datetime | None = None) -> float:
        now = now or datetime.now()
        return (now - self.started_at).total_seconds() / 86400.0

    def decide(self, metrics: dict, now: datetime | None = None) -> str:
        """返回 promote（到期且达标→全量）/ rollback（任一指标异常）/ hold（观察中）。"""
        if canary_should_rollback(metrics):
            return "rollback"
        if self.elapsed_days(now) >= self.days:
            return "promote"
        return "hold"
