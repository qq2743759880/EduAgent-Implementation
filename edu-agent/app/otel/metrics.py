# -*- coding: utf-8 -*-
"""task-O1 5 维指标内存累加器（production-upgrade-plan P8）。

每项指标为进程内线程安全累加器，可 `snapshot()` 导出；同时保留「溯源」信息
（贡献该指标的事件 trace_id / event_id 列表），满足 AC2「数据来源可溯源到事件」。

事件 → 指标映射（event_type）：
- memory_event    → MemoryHitRate        （记忆命中率 = 召回被采纳 / 召回总数，按 user 维度）
- compaction_event → CompactionEfficiency （压缩效率 = 压缩前后 token 差 / 丢轮数 / 触发策略分布）
- tool_result     → ToolSuccessRate       （工具成功率 = SUCCESS / (SUCCESS+ERROR+TIMEOUT+REJECTION_LIMIT)）
- cache_event     → CacheHitRate          （缓存命中率 = cache_read / (cache_read + cache_miss)，模型×层维度）
- queue_event     → QueueTimeoutRate      （排队超时率 = queue_timeout / acquire 总数，分级 L1~L3）

注：本模块与 task97 CacheMonitor 各司其职——CacheMonitor 负责 provider 侧命中率 + 联合看板
（Prometheus）；本模块负责 O1 五维指标的统一可溯源快照，供 /api/metrics/trace/{trace_id} 与
观测面板消费。二者互不依赖，CacheHitRate 由 O1 exporter 的 record_cache_event 独立喂入。
"""
from __future__ import annotations

import threading
from typing import Any


class _BaseMetric:
    """指标基类：线程安全 + 溯源事件列表（有界）。"""

    def __init__(self, name: str, max_sources: int = 50) -> None:
        self.name = name
        self._lock = threading.Lock()
        self._sources: list[dict] = []
        self._max_sources = max_sources

    def _add_source(self, event: dict) -> None:
        tid = event.get("trace_id")
        eid = event.get("event_id")
        if tid or eid:
            self._sources.append({"trace_id": tid, "event_id": eid})
            if len(self._sources) > self._max_sources:
                self._sources.pop(0)

    def snapshot(self) -> dict:
        raise NotImplementedError


class MemoryHitRate(_BaseMetric):
    """记忆命中率 = 召回被采纳 / 召回总数（按 user 维度）。

    事件约定（memory_event payload）：
      - {action:"recall", adopted: bool}                一次召回，adopted=True 计为已采纳
      - {action:"recall_accepted", user_id}             等价于 recall + adopted=True
      - {action:"write"|"recall_rejected"|...}          其他动作，不计入命中率分母/分子
    """

    def __init__(self) -> None:
        super().__init__("memory_hit_rate")
        self.recall_total = 0
        self.recall_accepted = 0
        self.by_user: dict[str, dict] = {}

    def record(self, event: dict) -> None:
        p = event.get("payload") or {}
        action = p.get("action")
        user = str(p.get("user_id") or "unknown")
        with self._lock:
            if action == "recall":
                self.recall_total += 1
                self._add_source(event)
                b = self.by_user.setdefault(user, {"recall_total": 0, "recall_accepted": 0})
                b["recall_total"] += 1
                if p.get("adopted"):
                    self.recall_accepted += 1
                    b["recall_accepted"] += 1
            elif action == "recall_accepted":
                self.recall_total += 1
                self.recall_accepted += 1
                self._add_source(event)
                b = self.by_user.setdefault(user, {"recall_total": 0, "recall_accepted": 0})
                b["recall_total"] += 1
                b["recall_accepted"] += 1

    def snapshot(self) -> dict:
        total = self.recall_total
        accepted = self.recall_accepted
        ratio = round(accepted / total, 4) if total else 0.0
        return {
            "name": self.name,
            "recall_total": total,
            "recall_accepted": accepted,
            "hit_rate": ratio,
            "by_user": {
                u: {
                    "recall_total": v["recall_total"],
                    "recall_accepted": v["recall_accepted"],
                    "hit_rate": round(v["recall_accepted"] / v["recall_total"], 4) if v["recall_total"] else 0.0,
                }
                for u, v in self.by_user.items()
            },
            "sources": list(self._sources),
        }


class CompactionEfficiency(_BaseMetric):
    """压缩效率 = 压缩后 token / 压缩前 token（越低越省）；并记录丢轮数与触发策略分布。"""

    def __init__(self) -> None:
        super().__init__("compaction_efficiency")
        self.times = 0
        self.before_total = 0
        self.after_total = 0
        self.dropped_rounds_total = 0
        self.policy_dist: dict[str, int] = {}

    def record(self, event: dict) -> None:
        p = event.get("payload") or {}
        if p.get("before_tokens") is None or p.get("after_tokens") is None:
            return
        with self._lock:
            self.times += 1
            self._add_source(event)
            self.before_total += int(p["before_tokens"])
            self.after_total += int(p["after_tokens"])
            self.dropped_rounds_total += int(p.get("dropped_rounds") or 0)
            pol = str(p.get("policy") or "unknown")
            self.policy_dist[pol] = self.policy_dist.get(pol, 0) + 1

    def snapshot(self) -> dict:
        saved = self.before_total - self.after_total
        ratio = round(self.after_total / self.before_total, 4) if self.before_total else 0.0
        return {
            "name": self.name,
            "compactions": self.times,
            "before_tokens_total": self.before_total,
            "after_tokens_total": self.after_total,
            "tokens_saved_total": saved,
            "compression_ratio": ratio,  # 压缩后/压缩前（越小越省）
            "avg_dropped_rounds": round(self.dropped_rounds_total / self.times, 2) if self.times else 0.0,
            "policy_distribution": dict(self.policy_dist),
            "sources": list(self._sources),
        }


class ToolSuccessRate(_BaseMetric):
    """工具成功率 = SUCCESS / (SUCCESS+ERROR+TIMEOUT+REJECTION_LIMIT)。"""

    OUTCOMES = ("SUCCESS", "ERROR", "TIMEOUT", "REJECTION_LIMIT")

    def __init__(self) -> None:
        super().__init__("tool_success_rate")
        self.counts = {o: 0 for o in self.OUTCOMES}

    def record(self, event: dict) -> None:
        p = event.get("payload") or {}
        oc = p.get("outcome")
        if oc in self.counts:
            with self._lock:
                self.counts[oc] += 1
                self._add_source(event)

    def snapshot(self) -> dict:
        total = sum(self.counts.values())
        success = self.counts["SUCCESS"]
        rate = round(success / total, 4) if total else 0.0
        return {
            "name": self.name,
            "total": total,
            "counts": dict(self.counts),
            "success_rate": rate,
            "sources": list(self._sources),
        }


class CacheHitRate(_BaseMetric):
    """缓存命中率 = cache_read / (cache_read + cache_miss)（模型 × 层维度）。

    事件约定（cache_event payload）：{cache_read, cache_miss, model, layer}
    miss 基数由调用方按 provider 口径给出（如 prompt_total - cache_read - cache_creation）。
    """

    def __init__(self) -> None:
        super().__init__("cache_hit_rate")
        self.cache_read = 0
        self.cache_miss = 0
        self.by_model: dict[str, dict] = {}
        self.by_layer: dict[str, dict] = {}

    def record(self, event: dict) -> None:
        p = event.get("payload") or {}
        r = p.get("cache_read")
        m = p.get("cache_miss")
        if r is None and m is None:
            return
        r = int(r or 0)
        m = int(m or 0)
        model = str(p.get("model") or "unknown")
        layer = str(p.get("layer") or "unknown")
        with self._lock:
            self.cache_read += r
            self.cache_miss += m
            self._add_source(event)
            bm = self.by_model.setdefault(model, {"cache_read": 0, "cache_miss": 0})
            bm["cache_read"] += r
            bm["cache_miss"] += m
            bl = self.by_layer.setdefault(layer, {"cache_read": 0, "cache_miss": 0})
            bl["cache_read"] += r
            bl["cache_miss"] += m

    def snapshot(self) -> dict:
        base = self.cache_read + self.cache_miss
        rate = round(self.cache_read / base, 4) if base else 0.0

        def _rate(v: dict) -> float:
            b = v["cache_read"] + v["cache_miss"]
            return round(v["cache_read"] / b, 4) if b else 0.0

        return {
            "name": self.name,
            "cache_read": self.cache_read,
            "cache_miss": self.cache_miss,
            "hit_rate": rate,
            "by_model": {k: {"cache_read": v["cache_read"], "cache_miss": v["cache_miss"], "hit_rate": _rate(v)} for k, v in self.by_model.items()},
            "by_layer": {k: {"cache_read": v["cache_read"], "cache_miss": v["cache_miss"], "hit_rate": _rate(v)} for k, v in self.by_layer.items()},
            "sources": list(self._sources),
        }


class QueueTimeoutRate(_BaseMetric):
    """并发排队超时率 = queue_timeout / acquire 总数（分级 L1~L3）。

    事件约定（queue_event payload）：{action:"acquire"|"timeout", level:"L1"|"L2"|"L3"}
    """

    LEVELS = ("L1", "L2", "L3")

    def __init__(self) -> None:
        super().__init__("queue_timeout_rate")
        self.acquire = 0
        self.timeout = 0
        self.by_level: dict[str, dict] = {}

    def record(self, event: dict) -> None:
        p = event.get("payload") or {}
        action = p.get("action")
        if action not in ("acquire", "timeout"):
            return
        level = str(p.get("level") or "L1")
        with self._lock:
            if action == "acquire":
                self.acquire += 1
            else:
                self.timeout += 1
            self._add_source(event)
            b = self.by_level.setdefault(level, {"acquire": 0, "timeout": 0})
            b[action] += 1

    def snapshot(self) -> dict:
        total = self.acquire
        rate = round(self.timeout / total, 4) if total else 0.0
        return {
            "name": self.name,
            "acquire_total": total,
            "timeout_total": self.timeout,
            "timeout_rate": rate,
            "by_level": {
                k: {
                    "acquire": v["acquire"],
                    "timeout": v["timeout"],
                    "timeout_rate": round(v["timeout"] / v["acquire"], 4) if v["acquire"] else 0.0,
                }
                for k, v in self.by_level.items()
            },
            "sources": list(self._sources),
        }


class OtelMetrics:
    """5 维指标聚合器：按 event_type 派发到对应指标；snapshot() 输出全部维度。"""

    def __init__(self) -> None:
        self.memory = MemoryHitRate()
        self.compaction = CompactionEfficiency()
        self.tool = ToolSuccessRate()
        self.cache = CacheHitRate()
        self.queue = QueueTimeoutRate()
        self._dispatch = {
            "memory_event": self.memory,
            "compaction_event": self.compaction,
            "tool_result": self.tool,
            "cache_event": self.cache,
            "queue_event": self.queue,
        }

    def record(self, event: dict) -> None:
        handler = self._dispatch.get(event.get("event_type"))
        if handler is not None:
            handler.record(event)

    def snapshot(self) -> dict:
        return {
            "memory_hit_rate": self.memory.snapshot(),
            "compaction_efficiency": self.compaction.snapshot(),
            "tool_success_rate": self.tool.snapshot(),
            "cache_hit_rate": self.cache.snapshot(),
            "queue_timeout_rate": self.queue.snapshot(),
        }


# 进程内单例（测试可 set_otel_metrics 注入）
_default_metrics = OtelMetrics()


def get_otel_metrics() -> OtelMetrics:
    return _default_metrics


def set_otel_metrics(m: OtelMetrics) -> None:
    global _default_metrics
    _default_metrics = m
