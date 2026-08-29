"""
RateLimitMiddleware：IP+user_id 双维度滑动窗口限流

交易档限流：
- /api/trade/order: 10/min
- /api/trade/payment: 30/min
- /api/trade/refund: 5/min
- /api/trade/coupon/receive: 30/min
- /api/after_sales/ticket: 20/min
"""
from __future__ import annotations

import os
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.common.logging import logger

# 交易档支付限流可用环境变量覆盖（测试/压测专用，生产勿设）：
#   EDUAGENT_TRADE_PAYMENT_LIMIT = /api/trade/payment 每窗口最大请求数（默认 30；并发攻防测试可放宽）
#   EDUAGENT_TRADE_ORDER_LIMIT     = /api/trade/order 每窗口最大请求数（默认 10）
#   EDUAGENT_RATE_LIMIT_DEFAULT    = 通用默认每窗口最大请求数（默认 100；并发攻防测试可放宽）
#   EDUAGENT_CHAT_LIMIT            = /api/chat(/stream) 每窗口最大请求数（默认 20；
#                                    task39 LLM 压测窗口内必须放宽，否则 20/min 的天花板
#                                    会让「L1~L3 P95」压测退化成限流压测，测不到真实 LLM 延迟）
_TRADE_PAYMENT_LIMIT = int(os.environ.get("EDUAGENT_TRADE_PAYMENT_LIMIT", "30"))
_TRADE_ORDER_LIMIT = int(os.environ.get("EDUAGENT_TRADE_ORDER_LIMIT", "10"))
_DEFAULT_LIMIT = int(os.environ.get("EDUAGENT_RATE_LIMIT_DEFAULT", "100"))
_CHAT_LIMIT = int(os.environ.get("EDUAGENT_CHAT_LIMIT", "20"))

# 限流规则：(窗口秒, 最大请求数)
_RATE_LIMIT_RULES: dict[str, tuple[int, int]] = {
    "/api/auth/login":       (60, 10),
    "/api/auth/register":    (60, 5),
    "/api/auth/refresh":     (60, 30),
    "/api/chat":             (60, _CHAT_LIMIT),
    "/api/admin":            (60, 200),
    # 交易档
    "/api/trade/order":      (60, _TRADE_ORDER_LIMIT),
    "/api/trade/payment":    (60, _TRADE_PAYMENT_LIMIT),
    "/api/trade/refund":     (60, 5),
    "/api/trade/coupon/receive": (60, 30),
    "/api/after_sales/ticket": (60, 20),
    "default":               (60, _DEFAULT_LIMIT),
}

_SKIP_PREFIXES = (
    "/health", "/metrics", "/docs", "/redoc", "/openapi.json",
    "/favicon.ico",
)


def _get_client_ip(request: Request) -> str:
    """
    S3（judge 裁定）：客户端 IP 直接取连接层 request.client.host。

    不再信任 X-Forwarded-For / X-Real-IP（客户端可任意伪造首跳，每请求换
    假 IP 即可稀释 IP 维度限流 → 暴破面，CWE-348）。当前部署形态为本机/
    内网直连无可信反向代理；接入可信代理后，应由代理层清洗 XFF 并在此
    按部署文档恢复解析（取可信代理追加的末跳）。
    """
    return request.client.host if request.client else "unknown"


def _get_user_id(request: Request) -> str:
    """从 JWT token 中提取 user_id（如果有的话）。"""
    try:
        import jwt
        from app.config import settings
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            payload = jwt.decode(auth[7:], settings.JWT_SECRET, algorithms=["HS256"])
            return str(payload.get("sub", ""))
    except Exception:
        pass
    return ""


def _get_limit_for_path(path: str) -> tuple[int, int]:
    for prefix, rule in _RATE_LIMIT_RULES.items():
        if prefix == "default":
            continue
        if path.startswith(prefix):
            return rule
    return _RATE_LIMIT_RULES["default"]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """IP+user_id 双维度滑动窗口限流。"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        window_sec, max_requests = _get_limit_for_path(path)
        client_ip = _get_client_ip(request)
        user_id = _get_user_id(request)

        try:
            from app.database import get_redis
            r = get_redis()
        except RuntimeError:
            return await call_next(request)

        # IP 维度
        ip_key = f"rl:ip:{client_ip}:{path}"
        # user_id 维度（如果已登录）
        uid_key = f"rl:uid:{user_id}:{path}" if user_id else None

        try:
            # IP 限流
            ip_current = await r.incr(ip_key)
            if ip_current == 1:
                await r.expire(ip_key, window_sec + 1)

            # user_id 限流
            uid_current = 0
            if uid_key:
                uid_current = await r.incr(uid_key)
                if uid_current == 1:
                    await r.expire(uid_key, window_sec + 1)

            current = max(ip_current, uid_current)
            remaining = max(0, max_requests - current)

            if current > max_requests:
                logger.warning(
                    f"[RATE_LIMIT] {client_ip} {path} "
                    f"超过限制 {current}/{max_requests}（{window_sec}s）"
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "code": "42900",
                        "message": f"请求过于频繁，请 {window_sec} 秒后再试",
                        "data": None,
                    },
                    headers={"Retry-After": str(window_sec)},
                )
        except Exception as exc:
            logger.warning(f"[RATE_LIMIT] Redis 异常，降级放行: {exc}")
            # task39 GWT②：§6.4 Redis 行「限流放行」的可观测面
            try:
                from app.monitoring.metrics import record_degraded
                record_degraded("redis", f"rate_limit_bypass:{type(exc).__name__}")
            except Exception:  # noqa: BLE001
                pass
            return await call_next(request)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response