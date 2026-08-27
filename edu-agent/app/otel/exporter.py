# -*- coding: utf-8 -*-
"""task-O1 OTel 结构化事件导出（production-upgrade-plan P8）。

事件 schema（对齐 Codex OTel log export：user prompt/approval/工具结果/MCP/网络策略事件）：
    {
      ts:          int    # 毫秒时间戳
      trace_id:    str    # 全链路 trace_id（会话级贯穿）
      span_id:     str    # 当前 span_id（嵌套 span 各异）
      event_type:  str    # memory_event | compaction_event | tool_result | cache_event | queue_event | llm_call | retry | sandbox_outcome
      event_id:    str    # 事件唯一 id（溯源用）
      payload:     dict   # 事件结构化数据
      user_id:     str|None
      model:       str|None
      latency_ms:  float|None
    }

导出目标（双通道）：
  - OTEL_EXPORT_ENDPOINT 为空 → 结构化 JSONL 落盘 OTEL_JSONL_DIR（默认 logs/otel/，按日分文件）
  - 配置后 → OTLP HTTP 导出（POST JSON 到该端点；可选依赖 requests 已为运行时常驻，
    缺失/网络失败 → 自动降级 JSONL 不阻塞主流程）

同时：
  ① 内存环形缓冲（默认上限 MAX_MEMORY_EVENTS，供 /api/metrics/trace/{trace_id} 检索）；
  ② 派发到 5 维指标累加器（app.otel.metrics）实现可溯源计数。
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.trace import current_span, get_trace_id
from app.otel.metrics import get_otel_metrics

MAX_MEMORY_EVENTS = 5000


def _now_ms() -> int:
    return int(time.time() * 1000)


class OtelExporter:
    """进程内 OTel 事件导出器（单例）。线程安全。"""

    def __init__(
        self,
        clock=None,
        jsonl_dir: str | None = None,
        endpoint: str | None = None,
        sample_rate: float | None = None,
    ) -> None:
        self._clock = clock or time.time
        self._lock = threading.RLock()
        self._events: list[dict] = []
        self._endpoint = endpoint if endpoint is not None else settings.OTEL_EXPORT_ENDPOINT
        self._jsonl_dir = jsonl_dir if jsonl_dir is not None else settings.OTEL_JSONL_DIR
        self._sample_rate = sample_rate if sample_rate is not None else float(settings.OTEL_SAMPLE_RATE)
        self._metrics = get_otel_metrics()

    # ============================================================
    # 主入口
    # ============================================================
    def record(
        self,
        event_type: str,
        payload: dict | None = None,
        *,
        trace_id: str | None = None,
        span_id: str | None = None,
        user_id: str | None = None,
        model: str | None = None,
        latency_ms: float | None = None,
        event_id: str | None = None,
    ) -> dict | None:
        """记录一条结构化事件：采样式写入内存/落盘/OTLP/指标。

        返回构造的事件 dict（被采样丢弃时返回 None，便于调用方感知）。
        """
        sid = event_id or uuid.uuid4().hex[:16]
        # 稳定采样（依据 sid 哈希），默认 sample_rate=1.0 全量
        if self._sample_rate < 1.0:
            try:
                h = int(sid, 16)
            except ValueError:
                h = int.from_bytes(sid.encode("utf-8"), "big")
            if (h % 1000) / 1000.0 >= self._sample_rate:
                return None

        event = {
            "ts": int(self._clock() * 1000),
            "trace_id": trace_id or get_trace_id() or "",
            "span_id": span_id or current_span() or "",
            "event_type": event_type,
            "event_id": sid,
            "payload": payload or {},
            "user_id": user_id,
            "model": model,
            "latency_ms": latency_ms,
        }

        # ① 内存环形缓冲
        with self._lock:
            self._events.append(event)
            if len(self._events) > MAX_MEMORY_EVENTS:
                self._events.pop(0)

        # ② 导出（OTLP HTTP / JSONL 落盘）
        if self._endpoint:
            self._export_otlp(event)
        else:
            self._write_jsonl(event)

        # ③ 派发到 5 维指标累加器（失败不影响主流程）
        try:
            self._metrics.record(event)
        except Exception:
            pass

        return event

    # ---- 埋点便捷封装（供各模块一行调用）----
    def record_memory_event(self, action: str, *, user_id=None, adopted=None, trace_id=None, **extra) -> dict | None:
        payload: dict[str, Any] = {"action": action, "user_id": user_id, **extra}
        if adopted is not None:
            payload["adopted"] = bool(adopted)
        return self.record("memory_event", payload, user_id=user_id, trace_id=trace_id)

    def record_compaction_event(self, *, before_tokens, after_tokens, dropped_rounds=0, policy="compaction", trace_id=None, **extra) -> dict | None:
        payload = {
            "before_tokens": int(before_tokens),
            "after_tokens": int(after_tokens),
            "dropped_rounds": int(dropped_rounds),
            "policy": policy,
            **extra,
        }
        return self.record("compaction_event", payload, trace_id=trace_id)

    def record_tool_result(self, outcome: str, *, tool=None, attempt=1, trace_id=None, user_id=None, **extra) -> dict | None:
        payload = {"outcome": outcome, "tool": tool, "attempt": int(attempt), **extra}
        return self.record("tool_result", payload, user_id=user_id, trace_id=trace_id)

    def record_cache_event(self, *, cache_read=0, cache_miss=0, model=None, layer="project", trace_id=None, **extra) -> dict | None:
        payload = {
            "cache_read": int(cache_read),
            "cache_miss": int(cache_miss),
            "model": model,
            "layer": layer,
            **extra,
        }
        return self.record("cache_event", payload, model=model, trace_id=trace_id)

    def record_queue_event(self, action: str, *, level="L1", trace_id=None, **extra) -> dict | None:
        payload = {"action": action, "level": level, **extra}
        return self.record("queue_event", payload, trace_id=trace_id)

    def record_llm_call(self, *, model=None, trace_id=None, latency_ms=None, **extra) -> dict | None:
        return self.record("llm_call", dict(extra), model=model, trace_id=trace_id, latency_ms=latency_ms)

    # ============================================================
    # 落盘 / 导出
    # ============================================================
    def _write_jsonl(self, event: dict) -> None:
        try:
            d = Path(self._jsonl_dir)
            d.mkdir(parents=True, exist_ok=True)
            fpath = d / f"otel-{time.strftime('%Y-%m-%d')}.jsonl"
            line = json.dumps(event, ensure_ascii=False, default=str)
            with open(fpath, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            # 落盘失败不阻塞主流程（仅告警级）
            try:
                from app.common.logging import logger
                logger.debug("[otel] JSONL 落盘失败（忽略）")
            except Exception:
                pass

    def _export_otlp(self, event: dict) -> None:
        """OTLP HTTP 导出（JSON 投递；失败降级 JSONL 不阻塞）。"""
        try:
            import requests

            requests.post(self._endpoint, json=event, timeout=2.0)
        except Exception:
            # 网络/依赖失败 → 降级落盘
            self._write_jsonl(event)

    # ============================================================
    # 检索（供 /api/metrics/trace/{trace_id}）
    # ============================================================
    def get_events_by_trace(self, trace_id: str) -> list[dict]:
        with self._lock:
            return [e for e in self._events if e.get("trace_id") == trace_id]

    def get_all_events(self, limit: int = 500) -> list[dict]:
        with self._lock:
            return list(self._events[-limit:])

    def count(self) -> int:
        with self._lock:
            return len(self._events)


# 进程内单例（测试可 set_otel_exporter 注入隔离实例）
_default_exporter = OtelExporter()


def get_otel_exporter() -> OtelExporter:
    return _default_exporter


def set_otel_exporter(e: OtelExporter) -> None:
    global _default_exporter
    _default_exporter = e
