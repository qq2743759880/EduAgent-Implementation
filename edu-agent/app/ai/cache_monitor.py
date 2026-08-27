# -*- coding: utf-8 -*-
"""task97 R5 缓存监控：命中率可验证 + 与 task96 上下文水位联合看板。

竞品对标（code.claude.com/docs/en/prompt-caching）：
- cache_read / cache_creation 指标：Claude Code 把「命中率」当作 uptime 监控 —— 命中率低 = SEV。
  "Treat cache hit rate like an uptime metric: if it drops, something is wrong."
- 三层组织 + TTL：前缀稳定性决定命中率；模型切换 / MCP 工具变更 / compaction / effort 变更
  → 前缀失效 → 命中率骤降。任何影响前缀的操作必须记录失效原因（reason），以便定位根因。

本模块提供进程内 CacheMonitor（观测入口，零外部依赖，可直接单测）：
- record_llm_call：每次 LLM 调用上报 cache_read / cache_creation / prompt_total token + 模型 + 会话。
  模型切换（同一 tier 内模型名变化，如 fast 档 deepseek-v3→v4）→ 记录 model_switch 失效。
- record_invalidation：显式记录前缀失效事件（mcp_change / compaction / context_edit / prefix_change 等）。
- 多轮对话命中率：conversation_id → 累计 cache_read / 未缓存基数；整体命中率同理。
- joint_dashboard：与 task96 ContextUsageMonitor 联合 —— 同时返回
  「上下文水位（usage ratio 峰值 / 越水位次数 / 最近动作）」+「缓存命中（整体 / 分对话 / 失效原因）」。

线程/协程安全：所有累加走 asyncio.Lock。
"""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

from loguru import logger

# task96 观测入口（上下文使用率监控）——联合看板的数据源之一。
try:
    from app.ai.context_edit import get_context_monitor
except Exception:  # pragma: no cover —— 极端导入失败兜底
    get_context_monitor = None  # type: ignore

__all__ = [
    "CacheCallStat",
    "CacheMonitor",
    "get_cache_monitor",
    "set_cache_monitor",
    "record_llm_call",
    "record_invalidation",
]

# 命中率告警阈值（竞品对标：低命中率 = SEV；50% 为本项目可达标线，低于即需告警）。
HIT_RATE_ALERT_THRESHOLD = 0.5


@dataclass
class CacheCallStat:
    """单会话 / 全局累计的缓存调用统计。"""

    cache_read: int = 0
    cache_creation: int = 0
    prompt_total: int = 0  # 总 prompt token（= cache_read + cache_creation + 未缓存）
    calls: int = 0

    def _uncached(self) -> int:
        """未命中缓存、需重新计算的 token 基数 = prompt_total - cache_read - cache_creation（>=0）。"""
        return max(0, self.prompt_total - self.cache_read - self.cache_creation)

    def hit_rate(self) -> float:
        """命中率 = cache_read / (cache_read + 未缓存基数)。分母>0 才有意义。"""
        base = self.cache_read + self._uncached()
        return round(self.cache_read / base, 4) if base > 0 else 0.0

    def add(self, *, cache_read: int, cache_creation: int, prompt_total: int) -> None:
        self.cache_read += int(cache_read)
        self.cache_creation += int(cache_creation)
        self.prompt_total += int(prompt_total)
        self.calls += 1


@dataclass
class InvalidEvent:
    """一次前缀失效事件（task97 核心：记录命中率下降的根因）。"""

    ts: float
    reason: str
    layer: str = "unknown"
    detail: str = ""


class CacheMonitor:
    """进程内缓存命中率监控器（单例）。

    竞品对标 Claude Code prompt-caching：把命中率当 uptime 监控，且为每个前缀失效
    记录 reason（模型切换 / MCP 工具变更 / compaction / context_edit / effort 变更）。
    """

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.time
        # 用 threading.Lock：上报入口常在线程池（generator 的 run_in_executor）中调用，
        # 避免 asyncio.Lock 绑定到错误事件循环导致 "attached to a different loop"。
        self._lock = threading.Lock()
        self._global = CacheCallStat()
        self._by_conversation: dict[str, CacheCallStat] = {}
        self._invalidations: list[InvalidEvent] = []
        # 同 tier 内的模型名跟踪：仅当某 tier 内模型名变化才算 model_switch
        # （fast/strong 两档互切属正常路由，不报 switch，避免误判）。
        self._last_model_by_tier: dict[str, str] = {}

    # ============================================================
    # 主上报入口
    # ============================================================
    def _record_llm_call_core(
        self,
        *,
        cache_read: int = 0,
        cache_creation: int = 0,
        prompt_total: int = 0,
        model: str = "",
        tier: str = "",
        conversation_id: str | None = None,
    ) -> dict:
        """同步核心：累加缓存 token 明细 + 记录 model_switch 失效 + 导出 Prometheus。

        线程池安全（仅用 threading.Lock）。返回本次记录摘要。
        """
        cache_read = int(cache_read)
        cache_creation = int(cache_creation)
        prompt_total = int(prompt_total)

        model_switch = False
        detail = ""

        with self._lock:
            if tier and model and self._last_model_by_tier.get(tier) not in (None, model):
                detail = f"{self._last_model_by_tier.get(tier)}->{model}"
                model_switch = True
                self._invalidations.append(
                    InvalidEvent(ts=self._clock(), reason="model_switch", layer="system", detail=detail)
                )
            if tier and model:
                self._last_model_by_tier[tier] = model
            self._global.add(cache_read=cache_read, cache_creation=cache_creation, prompt_total=prompt_total)
            if conversation_id:
                c = self._by_conversation.setdefault(str(conversation_id), CacheCallStat())
                c.add(cache_read=cache_read, cache_creation=cache_creation, prompt_total=prompt_total)

        # 导出到 Prometheus（命中率当 uptime 指标）
        try:
            self._export_prometheus(cache_read=cache_read, cache_creation=cache_creation,
                                    prompt_total=prompt_total, model_switch=model_switch)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[cache_monitor] prometheus 导出失败（忽略）: {exc}")

        return {
            "cache_read": cache_read,
            "cache_creation": cache_creation,
            "prompt_total": prompt_total,
            "model_switch": model_switch,
            "model_switch_detail": detail,
            "hit_rate_global": self._global.hit_rate(),
            "calls": self._global.calls,
        }

    async def record_llm_call(self, **kwargs: Any) -> dict:
        """异步上报入口（测试 / API 用）；内部为同步核心，无 loop-bound 原语。"""
        return self._record_llm_call_core(**kwargs)

    def record_llm_call_sync(self, **kwargs: Any) -> dict:
        """同步上报入口（供 run_in_executor 工作线程直接调用，无需事件循环）。"""
        return self._record_llm_call_core(**kwargs)

    def record_invalidation(self, reason: str, *, layer: str = "unknown", detail: str = "") -> None:
        """显式记录前缀失效（MCP 工具变更 / compaction / context_edit / effort 变更 等）。"""
        self._invalidations.append(
            InvalidEvent(ts=self._clock(), reason=reason, layer=layer, detail=detail or "")
        )
        try:
            from app.monitoring.metrics import cache_invalidations_total

            cache_invalidations_total.labels(reason=str(reason)).inc()
        except Exception:  # noqa: BLE001
            pass

    # ============================================================
    # 读取 / 统计
    # ============================================================
    def overall_hit_rate(self) -> float:
        return self._global.hit_rate()

    async def conversation_hit_rate(self, conversation_id: str) -> float:
        c = self._by_conversation.get(str(conversation_id))
        return c.hit_rate() if c else 0.0

    def hit_rate_below_threshold(self, threshold: float = HIT_RATE_ALERT_THRESHOLD) -> bool:
        """命中率是否低于告警阈值（竞品对标：低命中率 = SEV）。"""
        return self._global.hit_rate() < threshold

    def invalidation_count(self, reason: str | None = None) -> int:
        if reason is None:
            return len(self._invalidations)
        return sum(1 for e in self._invalidations if e.reason == reason)

    def invalidation_reasons(self) -> list[dict[str, Any]]:
        return [asdict(e) for e in self._invalidations]

    def conversation_ids(self) -> list[str]:
        return list(self._by_conversation.keys())

    def stats(self) -> dict[str, Any]:
        return {
            "overall_hit_rate": self._global.hit_rate(),
            "calls": self._global.calls,
            "cache_read_tokens": self._global.cache_read,
            "cache_creation_tokens": self._global.cache_creation,
            "prompt_total_tokens": self._global.prompt_total,
            "conversations": len(self._by_conversation),
            "invalidations_total": len(self._invalidations),
            "invalidation_reasons": {
                r: self.invalidation_count(r) for r in sorted({e.reason for e in self._invalidations})
            },
            "below_threshold": self.hit_rate_below_threshold(),
        }

    # ============================================================
    # GWT④：与 task96 ContextUsageMonitor 联合看板
    # ============================================================
    async def joint_dashboard(self, session_id: str | None = None) -> dict[str, Any]:
        """上下文水位（task96）+ 缓存命中（task97）联合看板。

        前端观测面板（task-FE-O1）消费此 JSON：一眼看到「上下文是否逼近窗口上限」
        与「缓存命中率是否健康（低 = SEV）」。
        """
        ctx_snap: dict[str, Any] = {}
        try:
            monitor = get_context_monitor()
            if monitor is not None:
                ctx_snap = monitor.snapshot()
                # 把最近一次的 usage ratio 同步到 Prometheus（联合水位指标）
                last = ctx_snap.get("last") or {}
                if "usage_ratio" in last:
                    try:
                        from app.monitoring.metrics import context_usage_ratio

                        context_usage_ratio.set(float(last["usage_ratio"]))
                    except Exception:
                        pass
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[cache_monitor] 取上下文水位失败: {exc}")

        return {
            "ts": self._clock(),
            "session_id": session_id,
            "cache": self.stats(),
            "context": ctx_snap,
        }

    # ============================================================
    # Prometheus 导出（命中率当 uptime 指标）
    # ============================================================
    def _export_prometheus(self, *, cache_read: int, cache_creation: int,
                           prompt_total: int, model_switch: bool) -> None:
        from app.monitoring.metrics import (
            cache_creation_tokens_total,
            cache_hit_rate,
            cache_invalidations_total,
            cache_prompt_tokens_total,
            cache_read_tokens_total,
        )

        if cache_read:
            cache_read_tokens_total.inc(cache_read)
        if cache_creation:
            cache_creation_tokens_total.inc(cache_creation)
        if prompt_total:
            cache_prompt_tokens_total.inc(prompt_total)
        cache_hit_rate.set(self._global.hit_rate())
        if model_switch:
            cache_invalidations_total.labels(reason="model_switch").inc()


# ============================================================
# 进程内单例（测试可 set_cache_monitor 注入）
# ============================================================
_default_monitor = CacheMonitor()


def get_cache_monitor() -> CacheMonitor:
    """返回进程内默认缓存监控器（观测端点 / generator 共用）。"""
    return _default_monitor


def set_cache_monitor(m: CacheMonitor) -> None:
    """注入监控器（测试 / 嵌入场景用，避免串扰）。"""
    global _default_monitor
    _default_monitor = m


# 便捷函数（供 generator 直接调用，惰性取单例）
async def record_llm_call(**kwargs: Any) -> dict:
    return await get_cache_monitor().record_llm_call(**kwargs)


def record_invalidation(reason: str, *, layer: str = "unknown", detail: str = "") -> None:
    get_cache_monitor().record_invalidation(reason, layer=layer, detail=detail)
