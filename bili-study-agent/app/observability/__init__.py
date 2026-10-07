"""app.observability —— OTLP 导出器探针与可插拔观测性接入（W-NEXT-OTLP-001）。

- otlp：init_otlp() lifespan hook，按 settings.OTEL_EXPORTER_OTLP_ENDPOINT
  启/停标准 OTLP HTTP 导出；启动期做 SSRF 白名单守门 + 一次性探活，失败仅
  WARN 不阻断主服务（与 app/main.py 6 存储 init 同语义）。

本包不替代 app/otel/exporter.py（JSONL 落盘 + 非标 OTLP 投递）：二者并存，
本包聚焦「标准 OTLP HTTP 端到 OTel Collector 的健康门 + 可选导出」。
"""
from app.observability.otlp import (
    OtlpExporter,
    get_otlp_exporter,
    init_otlp,
    shutdown_otlp,
    trace_chat_entry,
    trace_executor_entry,
)

__all__ = [
    "OtlpExporter",
    "get_otlp_exporter",
    "init_otlp",
    "shutdown_otlp",
    "trace_chat_entry",
    "trace_executor_entry",
]
