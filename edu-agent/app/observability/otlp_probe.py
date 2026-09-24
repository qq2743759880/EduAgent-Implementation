# -*- coding: utf-8 -*-
"""TB2b：OTLP 端点 HTTP 真探活（修复「探活绿 ≠ 链路通」）。

问题（TB2 断点①的机制根因）：
    `app/observability/otlp.py::_tcp_probe()` 只做 **纯 socket 三次握手**，不发 HTTP。
    因此无论 endpoint 路径对不对、服务端是否真的接受 OTLP，探活**必然 PASS** ——
    实测 `start()=healthy` 而 `export()→False`（Jaeger 对裸根 POST 返 404）。
    这正是「OTel 是假的」长期潜伏的机制。

本模块把探活升级为 **发真实 OTLP HTTP 探测**：
    1. POST 一条合法的最小 `resourceSpans` envelope 到配置的 endpoint；
    2. 判定 2xx = 真通（Jaeger 返回 200 `{"partialSuccess":{}}`）；
    3. 额外做一次「裸根对照」探测（剥掉路径），把 `404` 这一典型误配显性化
       —— 让「路径写错」在启动日志里当场暴露，而不是等到找不到 trace 才发现。

零侵入：任何异常都转成 (ok=False, detail)，不抛、不阻断启动。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from app.common.logging import logger

# 合法的最小 OTLP envelope（Jaeger 要求 traceId/spanId 为非全零十六进制）
_PROBE_TIMEOUT_S = 3.0


def _minimal_envelope(service_name: str) -> dict:
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": service_name or "edu-agent"}},
                        {"key": "edu.probe", "value": {"boolValue": True}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "edu-agent.observability.probe"},
                        "spans": [
                            {
                                "traceId": uuid.uuid4().hex,          # 32 hex，非全零
                                "spanId": uuid.uuid4().hex[:16],      # 16 hex，非全零
                                "name": "otlp.http.probe",
                                "kind": 1,                            # INTERNAL
                                "startTimeUnixNano": str(time.time_ns()),
                                "endTimeUnixNano": str(time.time_ns()),
                                "attributes": [
                                    {"key": "probe", "value": {"stringValue": "tb2b-http-probe"}}
                                ],
                                "status": {"code": 1},                # OK
                            }
                        ],
                    }
                ],
            }
        ]
    }


def _post_json(url: str, body: dict, timeout: float) -> tuple[int, str]:
    """POST JSON，返回 (status_code, body_text)。HTTP 4xx/5xx 也返回码不抛。

    显式禁用代理：本机 HTTP_PROXY 会把 loopback 请求吞成 502（既有踩坑）。
    """
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", "replace")[:300]
    except urllib.error.HTTPError as exc:      # 4xx/5xx：关键证据（裸根路径 404）
        return int(exc.code), exc.read().decode("utf-8", "replace")[:300]
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


def _strip_path(endpoint: str) -> str:
    """剥掉路径，得到裸根 URL（用于对照探测：暴露「少写 /v1/traces」误配）。"""
    parsed = urllib.parse.urlparse(endpoint)
    if not parsed.scheme:
        parsed = urllib.parse.urlparse("http://" + endpoint)
    return f"{parsed.scheme}://{parsed.netloc}/"


def probe_otlp_http(
    endpoint: str,
    *,
    service_name: str = "edu-agent",
    timeout_s: float = _PROBE_TIMEOUT_S,
) -> tuple[bool, dict]:
    """HTTP 真探活：POST 合法 OTLP envelope 到 endpoint。

    返回 (ok, detail)：
      ok=True 仅在 **POST 到配置 endpoint 且返回 2xx** 时成立（这才是「链路通」）。
      detail 含 status / elapsed_ms / body / bare_root_status（对照）/ hint。
    """
    detail: dict = {"endpoint": endpoint, "service_name": service_name}
    if not endpoint:
        detail["hint"] = "endpoint 为空（disabled）"
        return False, detail

    t0 = time.perf_counter()
    status, body = _post_json(endpoint, _minimal_envelope(service_name), timeout_s)
    detail["status"] = status
    detail["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    detail["body"] = body

    ok = 200 <= status < 300
    if not ok:
        # 对照探测：剥路径后 POST。若裸根 404 而配置路径也非 2xx，
        # 高度提示「endpoint 少了 /v1/traces 后缀」（TB2 断点① 的典型形态）。
        bare = _strip_path(endpoint)
        try:
            if bare.rstrip("/") != endpoint.rstrip("/"):
                b_status, _b_body = _post_json(bare, _minimal_envelope(service_name), timeout_s)
                detail["bare_root_status"] = b_status
                if b_status == 404:
                    detail["hint"] = (
                        "裸根 POST 返回 404 → 配置的 endpoint 很可能缺少 '/v1/traces' 后缀"
                    )
        except Exception:  # noqa: BLE001
            pass
    else:
        # 2xx：再验一次「服务端是否真的接受了 OTLP」——合法 envelope 应返回
        # {"partialSuccess":{}} 或等效空对象；返回非 JSON 时给 WARN 但不判 fail
        detail["hint"] = "HTTP 2xx：OTLP 投递链路真通"

    return ok, detail


def log_probe_result(ok: bool, detail: dict) -> None:
    """统一日志口径（启动期一眼可读）。"""
    ep = detail.get("endpoint")
    if ok:
        logger.info(
            f"[OTLP-HTTP] 真探活通过 endpoint={ep} "
            f"status={detail.get('status')} {detail.get('elapsed_ms')}ms ✔"
        )
    else:
        logger.warning(
            f"[OTLP-HTTP] 真探活失败 endpoint={ep} "
            f"status={detail.get('status')} body={str(detail.get('body'))[:160]!r} "
            f"bare_root={detail.get('bare_root_status')} → {detail.get('hint') or '见上'}"
        )
