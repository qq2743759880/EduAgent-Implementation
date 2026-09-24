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

TB2b 修复（断点②：导出体不是 OTLP）：
    原实现把**私有事件 dict**（`{ts, trace_id, span_id, event_type, payload, ...}`）
    直接 POST 给 OTLP 端点，其 docstring 自述「OTLP HTTP 导出」在 Jaeger 上**不成立**
    —— Jaeger 只认 OTLP `resourceSpans` 信封，收私有 dict 一律 400 reject。
    现改为：把事件**映射**为合法 OTLP span 后再投递（`_event_to_span`），
    事件原有字段完整保留为 span attributes（零信息丢失），落盘 JSONL 路径不变
    （JSONL 侧仍是原始事件行，不受影响）。
    保留开关 `OTEL_EXPORT_ENVELOPE`：`otlp`（默认，标准信封）| `legacy`（旧私有 dict，
    仅供排障对比，生产不应启用）。

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

# TB2b：失败判定词表（payload 命中即 span status=ERROR，供 Jaeger 上直观看失败路径）
_FAILURE_TOKENS = ("fail", "failed", "error", "timeout", "exception", "denied", "rejected", "unavailable")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _norm_hex(value: Any, width: int) -> str:
    """把任意 id 归一为 width 位小写 hex；非法/全零返回空串（调用方自行兜底生成）。"""
    s = "".join(ch for ch in str(value or "").lower() if ch in "0123456789abcdef")
    if not s:
        return ""
    s = (s + "0" * width)[:width]
    return "" if set(s) == {"0"} else s


def _event_is_failure(event: dict) -> bool:
    """事件是否表示失败（payload 内 outcome/status/error 命中失败词表）。"""
    payload = event.get("payload") or {}
    if not isinstance(payload, dict):
        return False
    for key in ("outcome", "status", "error", "result", "reason"):
        val = payload.get(key)
        if val is None:
            continue
        if isinstance(val, bool):
            if key == "ok" and not val:
                return True
            continue
        text = str(val).lower()
        if any(tok in text for tok in _FAILURE_TOKENS):
            return True
    return False


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
        """OTLP HTTP 导出（TB2b：标准 resourceSpans 信封；失败降级 JSONL 不阻塞）。

        `OTEL_EXPORT_ENVELOPE=legacy` 时退回旧的私有 dict 投递（排障对比用）——
        注意该形态会被 Jaeger 400 reject，生产/演示不应启用。
        """
        try:
            import requests

            if str(getattr(settings, "OTEL_EXPORT_ENVELOPE", "otlp") or "otlp").lower() == "legacy":
                payload: dict = event
            else:
                payload = self._event_to_envelope(event)
            requests.post(self._endpoint, json=payload, timeout=2.0)
        except Exception:
            # 网络/依赖失败 → 降级落盘
            self._write_jsonl(event)

    # ---- TB2b：私有事件 → 标准 OTLP span 映射 ----
    def _event_to_envelope(self, event: dict) -> dict:
        """把一条私有事件映射为合法 OTLP `resourceSpans` 信封。

        - traceId：沿用事件 trace_id（32 位 hex；不足右补 0，全零则随机生成，Jaeger 拒全零）
        - spanId ：沿用事件 span_id（16 位 hex；不足右补 0，全零则随机生成）
        - 时间戳 ：startTimeUnixNano / endTimeUnixNano 由 `ts`(ms) ± latency_ms 推出
        - status ：payload.outcome/status 命中失败词表 → ERROR，否则 OK
        - 其余字段（event_type/event_id/user_id/model/latency_ms/payload.*）全部落到
          span attributes，保证 OTLP 与 JSONL 两条通道的信息量一致
        """
        trace_id = _norm_hex(event.get("trace_id"), 32) or uuid.uuid4().hex
        span_id = _norm_hex(event.get("span_id"), 16) or uuid.uuid4().hex[:16]

        ts_ms = int(event.get("ts") or (_now_ms()))
        latency_ms = event.get("latency_ms")
        try:
            latency_ms_f = float(latency_ms) if latency_ms is not None else 0.0
        except (TypeError, ValueError):
            latency_ms_f = 0.0
        start_ns = ts_ms * 1_000_000
        end_ns = start_ns + int(max(0.0, latency_ms_f) * 1_000_000)

        attrs: list[dict] = [
            {"key": "event_type", "value": {"stringValue": str(event.get("event_type") or "")}},
            {"key": "event_id", "value": {"stringValue": str(event.get("event_id") or "")}},
        ]
        if event.get("user_id") is not None:
            attrs.append({"key": "user_id", "value": {"stringValue": str(event["user_id"])}})
        if event.get("model") is not None:
            attrs.append({"key": "model", "value": {"stringValue": str(event["model"])}})
        if latency_ms is not None:
            attrs.append({"key": "latency_ms", "value": {"doubleValue": latency_ms_f}})
        payload = event.get("payload") or {}
        if isinstance(payload, dict):
            for k, v in payload.items():
                if v is None:
                    continue
                if isinstance(v, bool):
                    attrs.append({"key": f"payload.{k}", "value": {"boolValue": v}})
                elif isinstance(v, (int, float)):
                    attrs.append({"key": f"payload.{k}", "value": {"doubleValue": float(v)}})
                else:
                    attrs.append({"key": f"payload.{k}", "value": {"stringValue": str(v)[:512]}})

        failed = _event_is_failure(event)
        status = {"code": 2, "message": "event reported failure"} if failed else {"code": 1}

        span = {
            "traceId": trace_id,
            "spanId": span_id,
            "name": f"otel.{event.get('event_type') or 'event'}",
            "kind": 1,  # INTERNAL
            "startTimeUnixNano": str(start_ns),
            "endTimeUnixNano": str(end_ns),
            "attributes": attrs,
            "status": status,
        }
        return {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": {"stringValue": self._service_name()},
                            }
                        ]
                    },
                    "scopeSpans": [
                        {"scope": {"name": "edu-agent.otel"}, "spans": [span]}
                    ],
                }
            ]
        }

    def _service_name(self) -> str:
        return (getattr(settings, "OTEL_SERVICE_NAME", "") or "edu-agent").strip() or "edu-agent"

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
