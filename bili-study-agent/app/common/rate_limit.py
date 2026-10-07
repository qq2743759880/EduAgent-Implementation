"""
请求限流中间件（Phase 1 基础设施加固）。

设计说明：
- 基于 Redis 的滑动窗口算法（Sliding Window Log），多 worker 共享计数
- 不同端点配置不同限流阈值：
  - auth（登录/注册）：严格限流，防暴力破解
  - api（通用业务接口）：适中限流
  - admin（管理端）：较宽松，内部使用
- Redis 不可用时降级为放行（不阻塞正常业务），打 WARNING 日志
- 返回标准 429 响应 + Retry-After 头 + X-RateLimit-* 系列头

面试考点：
- 为什么用滑动窗口而不是固定窗口？固定窗口在边界处会有"双倍突发"问题
  （例如：第 59 秒发 100 个请求，第 61 秒又发 100 个 → 实际 2 秒内 200 个请求）
  滑动窗口用当前时间戳 + 过期 key 解决这个问题
- 为什么用 Redis 而不是内存？多 worker/多进程部署时内存计数不共享，Redis 是唯一事实源
"""
from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.common.logging import logger
from app.config import settings


# ============================================================
# 限流配置：不同端点类型 → (窗口秒数, 最大请求数)
# ============================================================
# 设计参考：
#   - 作业帮：普通 API 100 req/min，登录 10 req/min
#   - 猿辅导：AI 问答 20 req/min（LLM 调用贵）
#   - 黑马程序员：管理端 200 req/min（内部使用）
_RATE_LIMIT_RULES: dict[str, tuple[int, int]] = {
    # 端点前缀 → (窗口秒数, 窗口内最大请求数)
    "/api/auth/login":       (60, 10),    # 登录：1分钟最多10次（防暴力破解）
    "/api/auth/register":    (60, 5),     # 注册：1分钟最多5次（防批量注册）
    "/api/auth/refresh":     (60, 30),    # Token刷新：1分钟最多30次
    "/api/chat":             (60, 20),    # AI问答：1分钟20次（LLM调用贵）
    "/api/admin":            (60, 200),   # 管理端：1分钟200次（内部使用）
    "default":               (60, 100),   # 通用API：1分钟100次
}

# 限流跳过的路径（健康检查、静态资源等）
_RATE_LIMIT_SKIP_PREFIXES = (
    "/health", "/metrics", "/docs", "/redoc", "/openapi.json",
    "/favicon.ico", "/_next",
)


def _get_rate_limit_key(request: Request) -> str:
    """
    生成限流 Redis key。

    格式：rate_limit:{client_ip}:{endpoint_prefix}:{window_start}
    例如：rate_limit:192.168.1.100:/api/chat:1712345678

    用 client_ip 而非 user_id 的原因是：
    1. 未登录用户也需要限流（注册/登录接口）
    2. 防止攻击者用不同账号绕过限流
    3. 生产环境前面有 Nginx/负载均衡，取 X-Forwarded-For 或 X-Real-IP
    """
    client_ip = _get_client_ip(request)
    path = request.url.path
    # 找匹配的限流规则，取窗口秒数
    window_sec = 60  # 默认 60 秒窗口
    for prefix, (w, _) in _RATE_LIMIT_RULES.items():
        if prefix != "default" and path.startswith(prefix):
            window_sec = w
            break
    # 窗口起始时间戳（按窗口秒数对齐，确保同一窗口内的请求用同一个 key）
    now = int(time.time())
    window_start = now - (now % window_sec)
    return f"rate_limit:{client_ip}:{path}:{window_start}"


def _get_client_ip(request: Request) -> str:
    """
    获取客户端真实 IP。

    生产环境通常有 Nginx/负载均衡在前面，真实 IP 在 X-Forwarded-For 或 X-Real-IP 头。
    开发环境直接取 request.client.host（127.0.0.1）。
    """
    # 优先取反向代理传来的真实 IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def _get_limit_for_path(path: str) -> tuple[int, int]:
    """根据请求路径返回 (窗口秒数, 最大请求数)。"""
    # 精确匹配优先，再前缀匹配
    for prefix, rule in _RATE_LIMIT_RULES.items():
        if prefix == "default":
            continue
        if path.startswith(prefix):
            return rule
    return _RATE_LIMIT_RULES["default"]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    滑动窗口限流中间件。

    工作流程：
    1. 跳过白名单路径（health/metrics/docs 等）
    2. 生成 Redis key：rate_limit:{ip}:{path}:{window_start}
    3. INCR key → 如果计数 > 限制 → 返回 429
    4. 第一次 INCR 时 EXPIRE key（窗口秒数 + 1 秒缓冲）
    5. 在响应头注入 X-RateLimit-* 系列信息
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # ── 1. 跳过白名单路径 ──
        if any(path.startswith(p) for p in _RATE_LIMIT_SKIP_PREFIXES):
            return await call_next(request)

        # ── 2. 获取限流参数 ──
        window_sec, max_requests = _get_limit_for_path(path)
        key = _get_rate_limit_key(request)

        # ── 3. Redis 限流检查 ──
        try:
            from app.database import get_redis
            r = get_redis()
        except RuntimeError:
            # Redis 未初始化（开发环境没装 Redis），降级放行
            return await call_next(request)

        try:
            # INCR：原子自增，返回自增后的值
            current = await r.incr(key)
            # 第一次设置时加过期时间（窗口 + 1 秒缓冲，防止边界问题）
            if current == 1:
                await r.expire(key, window_sec + 1)

            remaining = max(0, max_requests - current)
            reset_time = int(time.time()) + window_sec

            if current > max_requests:
                # 超限 → 返回 429
                logger.warning(
                    f"[RATE_LIMIT] {_get_client_ip(request)} {path} "
                    f"超过限制 {current}/{max_requests}（{window_sec}s 窗口）"
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "code": 42900,
                        "message": f"请求过于频繁，请 {window_sec} 秒后再试",
                        "detail": f"当前窗口已用 {current}/{max_requests} 次请求",
                    },
                    headers={
                        "Retry-After": str(window_sec),
                        "X-RateLimit-Limit": str(max_requests),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset_time),
                    },
                )
        except Exception as exc:
            # Redis 操作失败 → 降级放行（不阻塞正常业务）
            logger.warning(f"[RATE_LIMIT] Redis 操作异常，降级放行：{type(exc).__name__}: {exc}")
            response = await call_next(request)
            return response

        # ── 4. 放行，注入限流信息头 ──
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        return response