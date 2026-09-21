"""
RateLimitMiddleware：IP+user_id 双维度滑动窗口限流

交易档限流：
- /api/trade/order: 10/min（T6 后仅精确段命中，不再误伤 /api/trade/orders 列表）
- /api/trade/payment: 30/min
- /api/trade/refund: 5/min（⚠️ 死规则，见 _RATE_LIMIT_RULES 内登记）
- /api/trade/coupon/receive: 30/min
- /api/after_sales/ticket: 20/min（⚠️ 死规则，见 _RATE_LIMIT_RULES 内登记）
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
# T6（AUTO20，2026-09-22）匹配语义收窄：前缀匹配 → 最长前缀优先 + 段边界匹配。
# 根因（实证）：旧 startswith 前缀匹配下 "/api/trade/order" 规则误伤
# GET /api/trade/orders（订单列表）——学生页连拉列表 11 次起 429，
# 且 429 在 CORS 中间件内层返回丢 access-control-allow-origin 头 → 浏览器报
# CORS 错误 → me 页 console-errors 假红。收窄后列表走 default(100/min)。
# ⚠️ 阈值/窗口一律未动；仅改匹配语义。
# ⚠️ 死规则登记（保留不删，不擅自改阈值）：
# - "/api/trade/refund"：实际退款路由是 /api/refunds（openapi.json 权威），
#   原前缀永不命中——但按段边界匹配后 "/api/trade/refunds" 若未来出现会命中，
#   语义无害，保留待后端统一路由命名时一并处置。
# - "/api/after_sales/ticket"：实际工单路由是 /api/trade/after_sales/ticket*，
#   原前缀永不命中；同理保留登记。
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


def _path_in_prefix_scope(path: str, prefix: str) -> bool:
    """T6 段边界匹配：path 落在 prefix 的「本段及子路径」范围内才算命中。

    规则 "/api/trade/order" 命中 /api/trade/order、/api/trade/order/123、
    /api/trade/order/123/cancel；不命中 /api/trade/orders（同前缀不同段，
    旧 startswith 误伤根因）。
    """
    if path == prefix:
        return True
    return path.startswith(prefix + "/")


def _get_limit_for_path(path: str) -> tuple[int, int]:
    """最长前缀优先（收窄误伤面：/api/trade/coupon/receive 优先于更短前缀）。"""
    best: tuple[int, int] | None = None
    best_len = -1
    for prefix, rule in _RATE_LIMIT_RULES.items():
        if prefix == "default":
            continue
        if len(prefix) > best_len and _path_in_prefix_scope(path, prefix):
            best = rule
            best_len = len(prefix)
    return best if best is not None else _RATE_LIMIT_RULES["default"]


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


class RateLimitMiddleware(BaseHTTPMiddleware):
    """IP+user_id 双维度滑动窗口限流。"""

    @staticmethod
    def _cors_headers_for(request: Request) -> dict[str, str]:
        """T6 顺带修：429 短路响应补 CORS 头。

        RateLimitMiddleware 注册在 CORSMiddleware 内层（add_middleware 逆序：
        CORS 在外层），Starlette CORSMiddleware 只在「响应穿过它」时注入
        access-control-* 头；限流短路 429 虽也经外层，但 simple response 的
        ACAO 注入依赖请求 Origin 命中 allowlist —— 这里按同源规则显式回显，
        保证浏览器可读 429 壳（否则报成 CORS 错误 → me 页 console-errors 假红）。
        仅回显 allowlist 命中的 Origin，通配/未命中一律不带，不放宽 CORS 面。
        """
        origin = request.headers.get("origin")
        if not origin:
            return {}
        from app.config import settings

        if settings.DEBUG:
            return {
                "access-control-allow-origin": "*",
                "access-control-allow-credentials": "true",
            }
        allowed = {
            o.strip()
            for o in settings.CORS_ORIGINS.split(",")
            if o.strip()
        } or {"http://localhost:3000", "http://127.0.0.1:3000"}
        if origin in allowed:
            return {
                "access-control-allow-origin": origin,
                "access-control-allow-credentials": "true",
                "vary": "Origin",
            }
        return {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        window_sec, max_requests = _get_limit_for_path(path)

        # H1a（T19-2/L2）：已知 Redis 故障（快断窗/降级保持窗）内直接降级放行
        # （先于 get_redis——连客户端都不必取）。实测 Redis 宕机时单次 incr ~2.03s
        # 才失败（redis-py 重试退避），曾让全站每个 /api/* 请求固定 +2s（series
        # 详情 8~16s 根因之一）。窗口语义见 app/core/redis_outage.py：
        # 窗内毫秒级放行；后台探测自愈（成功清窗恢复限流），请求路径零等待。
        from app.core.redis_outage import ensure_probe, mark_redis_down, mark_redis_up, redis_degrade_active

        if redis_degrade_active():
            ensure_probe()  # 后台探测自愈（探测成本不占用请求路径）
            try:
                from app.monitoring.metrics import record_degraded
                record_degraded("redis", "rate_limit_bypass:outage_window")
            except Exception:  # noqa: BLE001
                pass
            return await call_next(request)

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
        except Exception as exc:
            # 连接级失败 → 顺延进程级快断窗（下个请求起毫秒级放行）
            from redis.exceptions import ConnectionError as _RConn, TimeoutError as _RTimeout

            if isinstance(exc, (_RConn, _RTimeout, ConnectionError, TimeoutError)):
                mark_redis_down()
            logger.warning(f"[RATE_LIMIT] Redis 异常，降级放行: {exc}")
            # task39 GWT②：§6.4 Redis 行「限流放行」的可观测面
            try:
                from app.monitoring.metrics import record_degraded
                record_degraded("redis", f"rate_limit_bypass:{type(exc).__name__}")
            except Exception:  # noqa: BLE001
                pass
            return await call_next(request)
        else:
            # 限流计数成功 → Redis 可用，清除故障窗（自愈）
            mark_redis_up()

        if current > max_requests:
            logger.warning(
                f"[RATE_LIMIT] {client_ip} {path} "
                f"超过限制 {current}/{max_requests}（{window_sec}s）"
            )
            # T6 顺带修：429 短路响应补 CORS 头（旧实现丢头 → 浏览器报 CORS 错误假红）
            headers = {"Retry-After": str(window_sec)}
            headers.update(self._cors_headers_for(request))
            return JSONResponse(
                status_code=429,
                content={
                    "code": "42900",
                    "message": f"请求过于频繁，请 {window_sec} 秒后再试",
                    "data": None,
                },
                headers=headers,
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response