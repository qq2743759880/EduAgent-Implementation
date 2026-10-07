"""
CircuitGuardMiddleware：轻量熔断打标中间件

不拦截请求，仅在 request.state 注入熔断器状态标记，
供路由层按需读取（如：retriever 发现 milvus 熔断直接走降级）。
"""
from __future__ import annotations

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class CircuitGuardMiddleware(BaseHTTPMiddleware):
    """
    轻量熔断打标中间件。

    职责：在 request.state 注入熔断器状态（不拦截请求）。
    路由层通过 `request.state.breaker_states` 获取各依赖的熔断状态。
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request.state.breaker_states = {}
        response = await call_next(request)
        return response