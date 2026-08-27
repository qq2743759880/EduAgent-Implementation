# -*- coding: utf-8 -*-
"""观测性包（task-O1，production-upgrade-plan P8）。

- metrics：5 维指标内存累加器（记忆命中率/压缩效率/工具成功率/缓存命中率/排队超时率）
- exporter：OTel 结构化事件导出（JSONL 落盘 / OTLP HTTP 双通道）+ 内存环形缓冲（供 trace 检索）
"""
from app.otel.exporter import (
    OtelExporter,
    get_otel_exporter,
    set_otel_exporter,
)
from app.otel.metrics import (
    CacheHitRate,
    CompactionEfficiency,
    MemoryHitRate,
    OtelMetrics,
    QueueTimeoutRate,
    ToolSuccessRate,
    get_otel_metrics,
    set_otel_metrics,
)

__all__ = [
    "OtelExporter",
    "get_otel_exporter",
    "set_otel_exporter",
    "OtelMetrics",
    "MemoryHitRate",
    "CompactionEfficiency",
    "ToolSuccessRate",
    "CacheHitRate",
    "QueueTimeoutRate",
    "get_otel_metrics",
    "set_otel_metrics",
]
