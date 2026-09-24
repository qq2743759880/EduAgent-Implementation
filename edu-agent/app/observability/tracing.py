# -*- coding: utf-8 -*-
"""TB2b：chat 链路分层 Span 埋点（真 OTel SDK → Jaeger 瀑布）。
背景（TB2 已定因的断点③）：
    全仓 `child_span` / `start_span` 生产调用点 = 0 —— 「脚手架齐备、链路未接」。
    现有 span 只有 2 个粗粒度入口（chat.router / tool_calling），且**无 parentSpanId**，
    在 Jaeger 上退化成互不相干的孤立点，构不成 retrieval→LLM→响应 的瀑布。

本模块的定位：
    用 **真 OTel SDK**（TracerProvider + OTLPSpanExporter）承接 span 生命周期，
    kind / parentSpanId / 时间戳 / status 全齐，导出到 Jaeger 形成分层瀑布。
    与 `app/observability/otlp.py`（手写 envelope、粗粒度入口）的区别是：
    本模块的 span 由 SDK 生成 spanId，天然带父子关系；otlp.py 的裸 POST 入口保留
    兼容，但不再是瀑布主体。

设计约束：
  1. **零侵入**：所有 API 失败即 no-op（返回 None / 空上下文），绝不抛出、绝不阻塞主链路。
  2. **sync/async 双友好**：`span()` 是 @contextmanager，可在 async 函数内 `with` 使用
     （退出时同步 `span.end()`，SimpleSpanProcessor 的 export 是同步 HTTP；
     超时默认 2s，与既有 OTLP 口径一致）。
  3. **配置驱动**：端点沿用 settings.OTEL_EXPORTER_OTLP_ENDPOINT（须含 /v1/traces 后缀）；
     为空 = disabled（零开销 no-op）。
  4. **trace_id 对齐**：沿用 app.core.trace.trace_id_var（会话级），使同一 session 的多次
     请求在 Jaeger 上 traceId 一致、便于整链还原。
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from app.common.logging import logger
from app.config import settings

# ============================================================
# 惰性单例（首次使用时才建 TracerProvider，避免 import 期副作用）
# ============================================================
_lock = threading.RLock()
_provider: Any = None
_tracer: Any = None
_state: str = "uninitialized"   # uninitialized | disabled | ready | failed
_last_error: str = ""


def _build_provider() -> Any:
    """建 TracerProvider + OTLPSpanExporter（module 级私有，失败返回 None）。"""
    endpoint = (getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "") or "").strip()
    if not endpoint:
        return None

    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

    service_name = (getattr(settings, "OTEL_SERVICE_NAME", "") or "edu-agent").strip() or "edu-agent"
    timeout_s = float(getattr(settings, "OTEL_EXPORTER_OTLP_TIMEOUT_S", 2.0) or 2.0)

    resource = Resource.create({"service.name": service_name})

    # headers 与 otlp.py 同一解析口径（`k1=v1,k2=v2`），密钥零硬编码
    headers: dict[str, str] = {}
    raw_headers = (getattr(settings, "OTEL_EXPORTER_OTLP_HEADERS", "") or "").strip()
    if raw_headers:
        for kv in raw_headers.split(","):
            if "=" in kv:
                k, v = kv.split("=", 1)
                if k.strip():
                    headers[k.strip()] = v.strip()

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    # 注意：OTLPSpanExporter 的 endpoint 必须**整条**给（含 /v1/traces 后缀），
    # 它不会再拼路径——这与本项目 .env 的写法一致（TB2 断点① 正是裸 POST 导致 404）。
    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        headers=headers or None,
        timeout=timeout_s,
    )
    provider = TracerProvider(resource=resource)
    # 处理器选择（TB2b 实测结论）：
    #   SimpleSpanProcessor = 同步导出，`span.end()` 当帧就 POST，**可预测性最高**，但每次
    #   导出会阻塞调用线程约 5~15ms（本机实测 /v1/traces 往返 6~7ms）。
    #   BatchSpanProcessor = 后台线程批量导出，主链路零阻塞，但有两处代价：
    #     ① 尾延迟 —— 发问结束后要等 schedule_delay 才可见，破坏「发问后立即在 Jaeger 查到」；
    #     ② **关闭顺序风险** —— 进程/生成器收尾早于导出线程 flush 时会丢尾帧
    #        （实测 4 个 span 中 3 个子 span 丢失，只剩 root）。
    #   默认取 Simple（demo 验收优先）；量大/生产可用 OTEL_TRACING_PROCESSOR=batch,
    #   或设 OTEL_TRACING_FORCE_SIMPLE=1 强制同步。失败一律降级 simple，绝不抛。
    _proc = (os.environ.get("OTEL_TRACING_PROCESSOR", "") or "").strip().lower()
    _force_simple = (os.environ.get("OTEL_TRACING_FORCE_SIMPLE", "") or "").strip() in ("1", "true", "yes")
    if _proc == "batch" and not _force_simple:
        try:
            from opentelemetry.sdk.trace.export import BatchSpanProcessor as _BSP

            provider.add_span_processor(
                _BSP(exporter, schedule_delay_millis=500, max_export_batch_size=64)
            )
            logger.info("[OTel] span 处理器=BatchSpanProcessor（后台批量导出，schedule_delay=500ms）")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[OTel] BatchSpanProcessor 装配失败 → 降级 Simple: {type(exc).__name__}: {exc}")
            provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


def get_tracer() -> Any | None:
    """返回进程内 Tracer（未配置/失败返回 None，调用方需容忍）。"""
    global _provider, _tracer, _state, _last_error
    if _state in ("ready", "disabled", "failed"):
        return _tracer
    with _lock:
        if _state in ("ready", "disabled", "failed"):
            return _tracer
        try:
            _provider = _build_provider()
            if _provider is None:
                _state = "disabled"
                _tracer = None
                logger.info("[OTel] OTEL_EXPORTER_OTLP_ENDPOINT 为空 → 分层 span 埋点 disabled（no-op）")
                return None
            _tracer = _provider.get_tracer("edu-agent.chat")
            _state = "ready"
            _last_error = ""
            logger.info(
                f"[OTel] 分层 span 埋点已启用 service="
                f"{getattr(settings, 'OTEL_SERVICE_NAME', 'edu-agent')} "
                f"endpoint={(getattr(settings, 'OTEL_EXPORTER_OTLP_ENDPOINT', '') or '').strip()}"
            )
        except Exception as exc:  # noqa: BLE001 — 埋点永不拖垮主链路
            _state = "failed"
            _tracer = None
            _last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(f"[OTel] 分层 span 埋点初始化失败（降级 no-op）: {_last_error}")
        return _tracer


def _otel_context_for(handle: Any) -> Any:
    """由 span handle 构造 OTel 上下文（供子 span 显式挂父）。"""
    if handle is None:
        return None
    try:
        from opentelemetry.trace import set_span_in_context

        return set_span_in_context(handle)
    except Exception:  # noqa: BLE001
        return None


class SpanHandle:
    """span 句柄：包装 SDK Span，失败安全（所有属性访问都不抛）。

    `span_id`：SDK 生成的 16 位 hex spanId（Jaeger 的 parentSpanId 就是它）；
    业务侧 `app.core.trace.child_span` 的 8 位 hex 是**另一套**（日志用），两者并存不冲突。
    """

    __slots__ = ("_span", "name", "span_id", "trace_id", "_ctx_token")

    def __init__(self, span: Any, name: str) -> None:
        self._span = span
        self.name = name
        self._ctx_token: Any = None
        try:
            ctx = span.get_span_context()
            self.span_id = format(ctx.span_id, "016x")
            self.trace_id = format(ctx.trace_id, "032x")
        except Exception:  # noqa: BLE001
            self.span_id = ""
            self.trace_id = ""

    def set_attribute(self, key: str, value: Any) -> None:
        try:
            if value is None:
                return
            self._span.set_attribute(key, value if isinstance(value, (bool, int, float)) else str(value)[:1024])
        except Exception:  # noqa: BLE001
            pass

    def set_attributes(self, attrs: dict | None) -> None:
        if not attrs:
            return
        for k, v in attrs.items():
            self.set_attribute(k, v)

    def record_exception(self, exc: BaseException) -> None:
        try:
            self._span.record_exception(exc)
        except Exception:  # noqa: BLE001
            pass

    def mark_error(self, message: str = "") -> None:
        """标 status=ERROR（失败路径验收要求：Jaeger 上显示错误状态）。"""
        try:
            from opentelemetry.trace import Status, StatusCode

            self._span.set_status(Status(StatusCode.ERROR, str(message)[:512] or None))
        except Exception:  # noqa: BLE001
            pass

    def mark_ok(self) -> None:
        try:
            from opentelemetry.trace import Status, StatusCode

            self._span.set_status(Status(StatusCode.OK))
        except Exception:  # noqa: BLE001
            pass


@contextmanager
def span(
    name: str,
    *,
    kind: str = "internal",
    parent: Any = None,
    attributes: dict | None = None,
) -> Iterator[SpanHandle | None]:
    """开一个真 OTel span（失败 → 产出 None，调用方用 `if h:` 守卫即可）。

    kind: "internal" | "server" | "client" | "producer" | "consumer"
    parent: 父 SpanHandle（显式挂父，保 parentSpanId 正确）；None 则继承当前 OTel 上下文。

    用法（async 内同样可用）：
        with span("chat.request", kind="server", attributes={"user_id": uid}) as h:
            if h:
                h.set_attribute("docs", 12)
    """
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    # 注意：SDK 的 tracer.start_as_current_span(context=...) 不会把 `context` 设为 current
    # 上下文（只当作新 span 的父），导致嵌套 span 只能挂到最外层。故这里改名避开歧义，
    # 并统一走 start_span + use_span 手工管理（见下）。
    name_ = name
    handle: SpanHandle | None = None
    try:
        from opentelemetry.trace import SpanKind as _SK
        from opentelemetry import context as _otel_ctx
        from opentelemetry.trace import set_span_in_context
        from opentelemetry.trace import use_span

        _kinds = {
            "internal": _SK.INTERNAL,
            "server": _SK.SERVER,
            "client": _SK.CLIENT,
            "producer": _SK.PRODUCER,
            "consumer": _SK.CONSUMER,
        }
        # ⚠️ 关键（实测踩两次）：
        # ① SDK 的 `start_as_current_span(context=...)` **不会**把 context 设为 current
        #    （只当作新 span 的父），导致嵌套只能挂到最外层 → 改用 start_span + use_span 手工管理。
        # ② `use_span` 的 `end_on_exit` **默认 False** → span 永不 end、永不导出
        #    （内存导出器 finished_spans=0，Jaeger 一条都看不到）→ 必须显式 True。
        # ③ **异步生成器会丢 current span**：SSE 的 body_iterator 是在别的 Task 里跑的，
        #    ContextVar 不跨 Task 继承，故父 span 上下文可能取不到 → 子 span 变独立根（无 parentSpanID）。
        #    因此这里**手工把父的 SpanContext 直接放进新 context**（显式 parent > 隐式 current），
        #    保证跨 Task 也挂得上父。
        if parent is not None:
            base_ctx = set_span_in_context(parent._span)
        else:
            base_ctx = _otel_ctx.get_current()
        sdk_span = tracer.start_span(name_, context=base_ctx, kind=_kinds.get(kind, _SK.INTERNAL))
        cm = use_span(sdk_span, end_on_exit=True)
        cm.__enter__()
        handle = SpanHandle(sdk_span, name_)
        handle.set_attributes(attributes)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[OTel] span({name_}) 开启失败（no-op）: {type(exc).__name__}: {exc}")
        yield None
        return

    try:
        yield handle
    except GeneratorExit:
        # GeneratorExit = 异步生成器正常关闭（客户端读完/断开后 aclose()），**不是业务失败**。
        # 若不特判，每个正常收尾的 SSE 请求都会把 root span 标成 ERROR（实测 chat.request
        # 显示 `GeneratorExit:` 红条），使 Jaeger 上「错误」失去判别力。仅记属性不置 status。
        try:
            if handle is not None:
                handle.set_attribute("otel.generator_closed", True)
        except Exception:  # noqa: BLE001
            pass
        raise
    except BaseException as exc:  # noqa: BLE001 — 真实失败路径要留痕（status=ERROR）
        try:
            handle.record_exception(exc)
            handle.mark_error(f"{type(exc).__name__}: {exc}")
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        try:
            cm.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass


def tracing_status() -> dict:
    """供探针/健康检查读取（含真实连通性由 probe_otlp_http 单独判定）。"""
    tracer = get_tracer()
    return {
        "state": _state if tracer is not None else _state,
        "endpoint": (getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "") or "").strip(),
        "service_name": (getattr(settings, "OTEL_SERVICE_NAME", "") or "edu-agent").strip(),
        "last_error": _last_error,
    }


def shutdown() -> None:
    """进程退出/测试清理：flush + 释放 provider。"""
    global _provider, _tracer, _state
    with _lock:
        try:
            if _provider is not None:
                _provider.shutdown()
        except Exception:  # noqa: BLE001
            pass
        _provider = None
        _tracer = None
        _state = "uninitialized"
