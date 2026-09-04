"""
IdempotencyMiddleware：幂等拦截中间件

拦截前缀：
- /api/trade/order
- /api/trade/payment
- /api/trade/refund
- /api/trade/coupon/receive
- /api/after_sales/ticket

工作机制：
1. 从请求头取 Idempotency-Key
2. 查 Redis 是否已有缓存响应
3. 有 → 直接返回缓存
4. 无 → 放行，响应后缓存（SET NX EX 86400）
"""
from __future__ import annotations

import json
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.common.logging import logger

# 幂等拦截的路径前缀
_IDEMPOTENT_PREFIXES = (
    "/api/trade/order",
    "/api/trade/payment",
    "/api/trade/refund",
    "/api/trade/coupon/receive",
    "/api/after_sales/ticket",
)

# hop-by-hop / 长度相关头：缓存命中重建 body 后长度会变，
# 必须剔除让 JSONResponse 重新计算 Content-Length，否则 IncompleteRead（P1 修复）
_HOP_BY_HOP = {"content-length", "transfer-encoding", "content-encoding", "connection"}


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """幂等中间件：Idempotency-Key 防重复提交。"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # 仅拦截 POST/PUT/PATCH 且匹配前缀
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        if not any(path.startswith(p) for p in _IDEMPOTENT_PREFIXES):
            return await call_next(request)

        idem_key = request.headers.get("Idempotency-Key") or request.headers.get("X-Idempotency-Key")
        if not idem_key:
            return await call_next(request)

        try:
            from app.database import get_redis
            r = get_redis()
        except RuntimeError:
            return await call_next(request)

        redis_key = f"idem:resp:{idem_key}"

        # 检查是否已有缓存
        try:
            cached = await r.get(redis_key)
            if cached is not None:
                logger.info(f"[Idempotency] 命中缓存: {idem_key}")
                data = json.loads(cached)
                # P1 修复：剔除长度/编码 hop-by-hop 头，让 JSONResponse 重新计算 Content-Length，
                # 避免重建 body 后长度与原 Content-Length 不匹配导致 IncompleteRead
                headers = {
                    k: v for k, v in data.get("headers", {}).items()
                    if k.lower() not in _HOP_BY_HOP
                }
                return JSONResponse(
                    content=data["body"],
                    status_code=data["status"],
                    headers=headers,
                )
        except Exception:
            pass

        # 放行，执行实际请求
        response = await call_next(request)

        # 缓存响应（仅成功响应）；缓存失败/Redis 不可达时仍须保留响应体，
        # 否则 body_iterator 已被消费会致下游拿到空响应（task37 根因修复）
        if response.status_code < 400:
            # BaseHTTPMiddleware 下 response.body 为空（流已被下游消费），
            # 须从 body_iterator 捕获真实响应体（同 RespWrapMiddleware 模式）
            body = b""
            body_iter = response.body_iterator
            if hasattr(body_iter, "__aiter__"):
                async for chunk in body_iter:
                    body += chunk
            else:
                for chunk in body_iter:
                    body += chunk

            # 缓存动作本身失败（如 Redis 不可达）不影响返回体
            try:
                try:
                    body_data = json.loads(body) if body else {"code": 0, "message": "ok", "data": None}
                except (ValueError, TypeError):
                    body_data = {"code": 0, "message": "ok", "data": None}

                cache_data = {
                    "body": body_data,
                    "status": response.status_code,
                    "headers": dict(response.headers),
                }
                await r.set(redis_key, json.dumps(cache_data, default=str), ex=86400)
            except Exception as exc:
                logger.warning(f"[Idempotency] 缓存响应失败: {exc}")

            # 重建响应返回给客户端（body_iterator 已消费），剔除长度/编码头让长度重算
            rebuilt_headers = {
                k: v for k, v in response.headers.items()
                if k.lower() not in _HOP_BY_HOP
            }
            return Response(
                content=body,
                status_code=response.status_code,
                headers=rebuilt_headers,
                media_type=response.headers.get("content-type", "application/json"),
            )

        return response