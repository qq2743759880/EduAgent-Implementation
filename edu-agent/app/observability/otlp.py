# -*- coding: utf-8 -*-
"""W-NEXT-OTLP-001：标准 OTLP HTTP 导出器 + lifespan 探针 hook。

设计原则（与编排者 CSP/T12 全量检测结论一致）：
1. 配置驱动（settings.OTEL_EXPORTER_OTLP_ENDPOINT）：
   - 空 = disabled（init_otlp() 走 SKIP，仅打 INFO）
   - 非空 = 启动期做 1 次 SSRF 白名单守门 + 1 次探活，失败仅 WARN 不阻断
2. SSRF 守门强制（数据安全）：
   - 端点 host 必须 ∈ app.security.ssrf_guard 默认白名单（127.0.0.1 / localhost
     / 192.168.85.101 / 10.0.0.1）；命中 BLOCKED_HOSTS（IMDS 等）即拒
   - headers 仅从 settings 读取，零硬编码密钥（Mimosa ③）
3. 导出语义：
   - 进程内单例（OtlpExporter）；线程安全锁；环形缓冲（默认 1000 条）
   - 标准 OTLP/HTTP 形态：`POST <endpoint>` + `Content-Type: application/json`
     + body 为单条 resource_metrics 风格的 envelope（生产 OTLP collector
     可识别 resource.service_name）
   - 导出失败 → 不抛异常（fire-and-forget），仅记日志（不拖死主链路）
4. 应用代码接入（不破坏现有 sync 流程）：
   - trace_chat_entry / trace_executor_entry：2 处便捷封装，构造最小
     OTLP span（trace_id 沿用 app.core.trace.current_trace_id）；
     调用方包在 try/except 内即可
5. 测试与门禁：
   - otlp_health_probe.py 走 SSRF 白名单 127.0.0.1 探活 + endpoint 解析
   - check-demo ⑳ 段消费 [OTLP] JSON 判定 PASS/FAIL
"""
from __future__ import annotations

import json
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.common.logging import logger
from app.config import settings
from app.security.ssrf_guard import validate_url, SSRFBlockedError

OTLP_DISABLED = "disabled"          # OTEL_EXPORTER_OTLP_ENDPOINT 为空
OTLP_HEALTHY = "healthy"            # 启动期探活通过
OTLP_SSRF_REJECTED = "ssrf_rejected"  # host 不在白名单
OTLP_PROBE_FAILED = "probe_failed"  # 探活失败（连接拒绝/超时等）
OTLP_DISABLED_PROBE = "probe_skipped"  # 配置要求跳过启动探活

OTLP_DEFAULT_BUFFER = 1000           # 内存环形缓冲上限


@dataclass
class OtlpExporter:
    """进程内 OTLP HTTP 导出器（单例）。线程安全。

    - endpoint 为空 → 全部 API 退化为 no-op（disabled 模式），便于测试与安全缺省
    - 任何 HTTP POST 失败：捕获并 logger.warning，不抛（不阻断主流程）
    """

    endpoint: str = ""
    service_name: str = "edu-agent"
    timeout_s: float = 2.0
    headers: dict[str, str] = field(default_factory=dict)
    buffer_max: int = OTLP_DEFAULT_BUFFER

    _state: str = OTLP_DISABLED
    _last_error: str = ""
    _buffer: list[dict] = field(default_factory=list)
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _probe_ms: int = 0
    # TB2b：HTTP 真探活明细（status / body / bare_root_status / hint），供健康检查与验收取证
    _last_probe_detail: dict = field(default_factory=dict)

    @classmethod
    def from_settings(cls) -> "OtlpExporter":
        ep = (settings.OTEL_EXPORTER_OTLP_ENDPOINT or "").strip()
        headers_raw = (settings.OTEL_EXPORTER_OTLP_HEADERS or "").strip()
        headers: dict[str, str] = {}
        if headers_raw:
            for kv in headers_raw.split(","):
                if "=" not in kv:
                    continue
                k, v = kv.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k:
                    headers[k] = v
        return cls(
            endpoint=ep,
            service_name=(settings.OTEL_SERVICE_NAME or "edu-agent").strip() or "edu-agent",
            timeout_s=float(settings.OTEL_EXPORTER_OTLP_TIMEOUT_S or 2.0),
            headers=headers,
        )

    # ============================================================
    # 启停
    # ============================================================
    def start(self, *, do_probe: bool | None = None, endpoint: str | None = None,
              service_name: str | None = None, timeout_s: float | None = None,
              headers: dict | None = None) -> str:
        """启动期初始化：解析 endpoint + SSRF 守门 + 可选 1 次探活。

        返回 state（OTLP_DISABLED / OTLP_HEALTHY / OTLP_SSRF_REJECTED / OTLP_PROBE_FAILED / OTLP_DISABLED_PROBE）。
        任何失败不抛异常，由调用方按 state 决定后续动作。

        参数优先级：函数参数 > self.* > settings.*（仅当函数参数 + self.* 都缺时回退 settings）。
        """
        # 1) endpoint 解析：参数 > self > settings
        if endpoint is not None:
            self.endpoint = endpoint.strip()
        elif not self.endpoint:
            self.endpoint = (settings.OTEL_EXPORTER_OTLP_ENDPOINT or "").strip()
        # 2) service_name / timeout_s / headers 同步
        if service_name is not None:
            self.service_name = (service_name or "edu-agent").strip() or "edu-agent"
        elif self.service_name == "edu-agent" and (settings.OTEL_SERVICE_NAME or "edu-agent") != "edu-agent":
            self.service_name = (settings.OTEL_SERVICE_NAME or "edu-agent").strip() or "edu-agent"
        if timeout_s is not None:
            self.timeout_s = float(timeout_s)
        elif self.timeout_s == 2.0:
            self.timeout_s = float(settings.OTEL_EXPORTER_OTLP_TIMEOUT_S or 2.0)
        if headers is not None:
            self.headers = dict(headers)
        elif not self.headers:
            self.headers = self._parse_headers(settings.OTEL_EXPORTER_OTLP_HEADERS or "")
        # 3) 探活开关
        if do_probe is None:
            do_probe = bool(settings.OTEL_EXPORTER_OTLP_PROBE_ON_START)

        if not self.endpoint:
            self._state = OTLP_DISABLED
            self._last_error = ""
            logger.info("[OTLP] OTEL_EXPORTER_OTLP_ENDPOINT 未配置，OTLP 导出 disabled（安全缺省）")
            return self._state

        # SSRF 守门
        try:
            validate_url(self.endpoint)
        except SSRFBlockedError as exc:
            self._state = OTLP_SSRF_REJECTED
            self._last_error = str(exc)
            logger.warning(
                f"[OTLP] 端点 host 不在 SSRF 白名单，拒绝启用: {self.endpoint} "
                f"({exc})——按 OTLP_DISABLED 处理（仅 settings 已正确才生效）"
            )
            return self._state

        # 探活（默认 HTTP 真探测；TB2b 前是纯 socket 握手 → 必然 PASS，掩盖路径误配）
        if not do_probe:
            self._state = OTLP_DISABLED_PROBE
            self._last_error = ""
            logger.info(
                f"[OTLP] OTEL_EXPORTER_OTLP_PROBE_ON_START=False，跳过启动探活。"
                f"endpoint={self.endpoint} service={self.service_name}（首次导出时才探活）"
            )
            return self._state

        # TB2b：默认发真实 OTLP HTTP POST 探测（"绿=真通"）；socket 模式保留供排障对比。
        _mode = str(getattr(settings, "OTEL_EXPORTER_OTLP_PROBE_MODE", "http") or "http").lower()
        if _mode == "http":
            return self._http_probe_start()

        # ---- legacy：socket TCP 探活（不真发 HTTP POST）----
        t0 = time.time()
        try:
            ok, msg = self._tcp_probe(self.endpoint, self.timeout_s)
        except Exception as exc:  # noqa: BLE001 — 探活兜底
            ok, msg = False, f"{type(exc).__name__}: {exc}"
        self._probe_ms = int((time.time() - t0) * 1000)

        if not ok:
            self._state = OTLP_PROBE_FAILED
            self._last_error = msg
            logger.warning(
                f"[OTLP] 端点 {self.endpoint} 启动探活失败（{msg}, {self._probe_ms}ms）"
                "——OTLP 仍启用（disabled-probe 形态），首次 POST 失败时降级为 silent warn"
            )
            # 即便探活失败，仍保留 endpoint（OTel collector 晚启动场景），导出失败时
            # 单独处理；不在此阻断主服务
            self._state = OTLP_DISABLED_PROBE
            return self._state

        self._state = OTLP_HEALTHY
        self._last_error = ""
        logger.info(
            f"[OTLP] 启用 endpoint={self.endpoint} service={self.service_name} "
            f"timeout={self.timeout_s}s headers={len(self.headers)}条 探活{self._probe_ms}ms ✔"
            f"（probe_mode=socket：仅 TCP 握手，不证明导出链路可用）"
        )
        return self._state

    def _http_probe_start(self) -> str:
        """TB2b：HTTP 真探活分支——POST 合法 OTLP envelope，2xx 才算「链路真通」。

        ⚠️ 这是对「探活绿 ≠ 链路通」的正面修复：旧 socket 探活无论 endpoint 路径
        对错都 PASS（实测 start()=healthy 而 export()→False）。
        """
        t0 = time.time()
        try:
            from app.observability.otlp_probe import log_probe_result, probe_otlp_http

            ok, detail = probe_otlp_http(
                self.endpoint,
                service_name=self.service_name,
                timeout_s=max(3.0, self.timeout_s),
            )
            log_probe_result(ok, detail)
        except Exception as exc:  # noqa: BLE001 — 探活本身出错也算不通过
            ok, detail = False, {"endpoint": self.endpoint, "hint": f"探活异常: {type(exc).__name__}: {exc}"}
        self._probe_ms = int((time.time() - t0) * 1000)
        self._last_probe_detail = detail

        if not ok:
            self._state = OTLP_DISABLED_PROBE
            self._last_error = str(detail.get("hint") or detail.get("status") or "http probe failed")
            return self._state

        self._state = OTLP_HEALTHY
        self._last_error = ""
        logger.info(
            f"[OTLP] 启用 endpoint={self.endpoint} service={self.service_name} "
            f"timeout={self.timeout_s}s headers={len(self.headers)}条 "
            f"HTTP 真探活{self._probe_ms}ms ✔（POST /v1/traces 2xx = 导出链路真通）"
        )
        return self._state

    def shutdown(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._state = OTLP_DISABLED
            self._last_error = ""

    # ============================================================
    # 导出（fire-and-forget）
    # ============================================================
    def export(self, span: dict[str, Any]) -> bool:
        """导出一条 OTLP span。失败静默（logger.warning），不抛、不阻塞。

        返回 True = 实际发出（HTTP 2xx）；False = 没发（disabled / 失败 / 缓冲）。
        """
        if self._state in (OTLP_DISABLED, OTLP_SSRF_REJECTED):
            return False
        if not self.endpoint:
            return False
        # 拼装标准 OTLP envelope（resource_metrics 风格；生产 OTLP collector 解析）
        envelope = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": self.service_name}},
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "edu-agent.observability"},
                            "spans": [span],
                        }
                    ],
                }
            ]
        }
        with self._lock:
            self._buffer.append(envelope)
            if len(self._buffer) > self.buffer_max:
                self._buffer.pop(0)
        # fire-and-forget POST
        try:
            import requests  # 运行时常驻；缺则降级
            resp = requests.post(
                self.endpoint,
                data=json.dumps(envelope, ensure_ascii=False, default=str).encode("utf-8"),
                headers={"Content-Type": "application/json", **self.headers},
                timeout=self.timeout_s,
            )
            return 200 <= resp.status_code < 300
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"[OTLP] 导出失败（endpoint={self.endpoint}, span={span.get('name','?')}, "
                f"{type(exc).__name__}: {exc}）——降级为环形缓冲保留，不阻断主流程"
            )
            return False

    # ============================================================
    # 便捷封装（应用代码接入用，sync 友好）
    # ============================================================
    def trace_chat_entry(self, *, user_id: str | None = None, query: str = "",
                         session_id: str | None = None, extra: dict | None = None) -> dict | None:
        """chat 入口 span（不抛，sync 流程友好）。"""
        return self._span("chat.entry", user_id=user_id, query=query,
                          session_id=session_id, extra=extra)

    def trace_executor_entry(self, *, tool: str = "", user_id: str | None = None,
                             session_id: str | None = None, extra: dict | None = None) -> dict | None:
        """executor 入口 span（不抛，sync 流程友好）。"""
        return self._span("executor.entry", tool=tool, user_id=user_id,
                          session_id=session_id, extra=extra)

    def _span(self, name: str, *, user_id=None, session_id=None, query="", tool="",
              extra=None) -> dict | None:
        if self._state in (OTLP_DISABLED, OTLP_SSRF_REJECTED) and not self.endpoint:
            return None  # disabled 模式：直接 no-op，零开销
        now_ms = int(time.time() * 1000)
        span = {
            "name": name,
            "traceId": _trace_id_now(),
            "spanId": uuid.uuid4().hex[:16],
            "startTimeUnixNano": str(now_ms * 1_000_000),
            "endTimeUnixNano": str(now_ms * 1_000_000),
            "attributes": _build_attrs(
                user_id=user_id, session_id=session_id, query=query, tool=tool, extra=extra
            ),
            "status": {"code": 1},  # 1=OK
        }
        self.export(span)
        return span

    # ============================================================
    # 探活 / 缓冲
    # ============================================================
    def _tcp_probe(self, endpoint: str, timeout_s: float) -> tuple[bool, str]:
        """TCP 探活（host:port 形式；不真发 HTTP POST）。

        返回 (ok, msg)：ok=True 表示 TCP 三次握手成功；msg 含耗时或错误码。
        """
        from urllib.parse import urlparse
        parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
        host = parsed.hostname or ""
        port = parsed.port or (443 if (parsed.scheme or "http") == "https" else 80)
        if not host:
            return False, "endpoint 缺 host"
        # 强制 IPv4 解析（host 写死 127.0.0.1 时不走 getaddrinfo）
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            return False, f"DNS 解析失败: {exc}"
        last_err = ""
        for family, socktype, _proto, _canon, sockaddr in infos:
            try:
                s = socket.socket(family, socktype)
                s.settimeout(timeout_s)
                s.connect(sockaddr)
                s.close()
                return True, f"tcp ok rtt<={int(timeout_s * 1000)}ms"
            except OSError as exc:
                last_err = f"{exc.__class__.__name__}: {exc}"
                continue
        return False, last_err or "无可用地址族"

    def status(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "endpoint": self.endpoint,
                "service_name": self.service_name,
                "timeout_s": self.timeout_s,
                "headers_count": len(self.headers),
                "buffer_len": len(self._buffer),
                "buffer_max": self.buffer_max,
                "probe_ms": self._probe_ms,
                "probe_mode": str(getattr(settings, "OTEL_EXPORTER_OTLP_PROBE_MODE", "http") or "http"),
                "probe_detail": dict(self._last_probe_detail),
                "last_error": self._last_error,
            }

    def get_buffer_snapshot(self, limit: int = 50) -> list[dict]:
        """取环形缓冲快照（最近 limit 条），供探针/调试观察。"""
        with self._lock:
            return list(self._buffer[-limit:])

    @staticmethod
    def _parse_headers(raw: str) -> dict[str, str]:
        out: dict[str, str] = {}
        if not raw:
            return out
        for kv in raw.split(","):
            if "=" not in kv:
                continue
            k, v = kv.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k:
                out[k] = v
        return out


# ============================================================
# 进程内单例 + lifespan hook
# ============================================================
_default_exporter = OtlpExporter()


def get_otlp_exporter() -> OtlpExporter:
    return _default_exporter


def set_otlp_exporter(exp: OtlpExporter) -> None:
    """测试可注入隔离实例。"""
    global _default_exporter
    _default_exporter = exp


def init_otlp() -> str:
    """lifespan hook：调用 start()，按 settings 启/停 OTLP exporter。

    返回 state 字符串供 lifespan 阶段日志消费；任何异常/失败仅 WARN 不抛。
    """
    try:
        exp = _default_exporter
        # 已 start 过则跳过（幂等；防 lifespan 反复调用）
        if exp._state != OTLP_DISABLED or exp.endpoint:
            return exp._state
        # 重新从 settings 加载（防测试 monkeypatch 后状态没刷新）
        fresh = OtlpExporter.from_settings()
        # 替换 endpoint/headers 等设置但保留单例身份（便于 set_otlp_exporter 注入测试）
        exp.endpoint = fresh.endpoint
        exp.service_name = fresh.service_name
        exp.timeout_s = fresh.timeout_s
        exp.headers = fresh.headers
        return exp.start()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"[OTLP] init_otlp() 兜底异常（不阻断启动）: {type(exc).__name__}: {exc}"
        )
        return OTLP_PROBE_FAILED


def shutdown_otlp() -> None:
    """lifespan 关闭 hook：清空缓冲、置 disabled。"""
    try:
        _default_exporter.shutdown()
    except Exception:  # noqa: BLE001
        pass


# ============================================================
# 模块级便捷封装（供 chat/executor 模块一行调用，不破坏 sync）
# ============================================================
def trace_chat_entry(*, user_id=None, query: str = "", session_id=None,
                     extra: dict | None = None) -> dict | None:
    """chat 入口 span（模块级便捷封装，不抛）。"""
    try:
        return _default_exporter.trace_chat_entry(user_id=user_id, query=query,
                                                  session_id=session_id, extra=extra)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[OTLP] trace_chat_entry 兜底: {type(exc).__name__}: {exc}")
        return None


def trace_executor_entry(*, tool: str = "", user_id=None, session_id=None,
                         extra: dict | None = None) -> dict | None:
    """executor 入口 span（模块级便捷封装，不抛）。"""
    try:
        return _default_exporter.trace_executor_entry(tool=tool, user_id=user_id,
                                                      session_id=session_id, extra=extra)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[OTLP] trace_executor_entry 兜底: {type(exc).__name__}: {exc}")
        return None


# ============================================================
# 内部 helpers
# ============================================================
def _trace_id_now() -> str:
    """取当前 trace_id（沿用 app.core.trace；缺失则生成 32 位 hex 兜底）。"""
    try:
        from app.core.trace import get_trace_id
        tid = get_trace_id() or ""
        if tid and len(tid) >= 16:
            return tid[:32].ljust(32, "0")
    except Exception:  # noqa: BLE001
        pass
    return uuid.uuid4().hex[:32]


def _build_attrs(*, user_id, session_id, query, tool, extra) -> list[dict]:
    attrs: list[dict] = []
    if user_id is not None:
        attrs.append({"key": "user_id", "value": {"stringValue": str(user_id)}})
    if session_id is not None:
        attrs.append({"key": "session_id", "value": {"stringValue": str(session_id)}})
    if query:
        attrs.append({"key": "query", "value": {"stringValue": str(query)[:256]}})
    if tool:
        attrs.append({"key": "tool", "value": {"stringValue": str(tool)}})
    if extra:
        for k, v in extra.items():
            if v is None:
                continue
            attrs.append({"key": str(k), "value": {"stringValue": str(v)[:256]}})
    return attrs
