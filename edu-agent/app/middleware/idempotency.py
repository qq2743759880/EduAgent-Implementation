"""
IdempotencyMiddleware：幂等拦截中间件

拦截前缀：
- /api/trade/order
- /api/trade/payment
- /api/trade/refund
- /api/trade/coupon/receive
- /api/after_sales/ticket

工作机制（对齐 Stripe Idempotency-Key / AWS Powertools，task39 批判 Round3）：
1. 从请求头取 Idempotency-Key
2. 读请求 body 派生 payload_hash（含 user_id 指纹，防跨用户/借键改内容重放）
3. 查 Redis 是否已有缓存响应：
   - 有且 user_id+payload_hash 一致 → 直接返回缓存（幂等命中）
   - 有但不一致 → 返回 42230 拒绝（键被复用改内容）
4. 无缓存 → SETNX 在途锁（NX，短 TTL）：
   - 拿不到锁（另一请求同键在途）→ 返回 40930 already_in_progress
   - 拿到锁 → 放行执行业务，响应后写缓存并释放锁
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.common.error_codes import (
    TRADE_IDEMPOTENCY_IN_PROGRESS,
    TRADE_IDEMPOTENCY_PAYLOAD_MISMATCH,
)
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

# 在途锁 TTL（秒）：锁必须短于任何真实业务执行时间，防死锁残留。
# 执行超期后锁自动过期，后续请求可重新抢锁执行（对齐 AWS in_progress_expiry_timestamp）。
_LOCK_TTL = 30
# 完成缓存 TTL（秒），对齐 Stripe"24 小时剪除"
_CACHE_TTL = 86400


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """幂等中间件：Idempotency-Key 防重复提交（含并发在途去重 + payload 一致性校验）。"""

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

        # 读取请求体派生标识：user_id + payload 指纹，作为"键是否被复用"的校验依据
        user_id = getattr(request.state, "user_id", None) or "anon"
        try:
            body_bytes = await request.body()
        except Exception:
            body_bytes = b""
        payload_hash = hashlib.sha256(body_bytes).hexdigest()

        resp_key = f"idem:resp:{idem_key}"
        lock_key = f"idem:lock:{idem_key}"

        # 1) 读缓存：命中且身份+payload 一致 → 直接返回（幂等命中）；不一致 → 拒绝重放
        try:
            cached = await r.get(resp_key)
            if cached is not None:
                data = json.loads(cached)
                cached_uid = data.get("uid")
                cached_ph = data.get("ph")
                if cached_uid == user_id and cached_ph == payload_hash:
                    logger.info(f"[Idempotency] 命中缓存: {idem_key}")
                    headers = {
                        k: v for k, v in data.get("headers", {}).items()
                        if k.lower() not in _HOP_BY_HOP
                    }
                    return JSONResponse(
                        content=data["body"],
                        status_code=data["status"],
                        headers=headers,
                    )
                # 同键但参数不一致：借键改内容/跨用户重放 → 拒绝（对齐 Stripe 参数一致性校验）
                logger.warning(f"[Idempotency] 键被复用但参数不一致，拒绝: {idem_key}")
                return JSONResponse(
                    status_code=422,
                    content={
                        "code": TRADE_IDEMPOTENCY_PAYLOAD_MISMATCH,
                        "message": "Idempotency-Key 已被其它参数占用",
                        "data": None,
                    },
                )
        except Exception:
            pass

        # 2) 未缓存 → SETNX 在途锁，防并发同键双执行
        lock_token = uuid.uuid4().hex
        try:
            acquired = await r.set(lock_key, lock_token, nx=True, ex=_LOCK_TTL)
        except Exception:
            acquired = True  # Redis 异常时放行（降级），不阻断业务
        if not acquired:
            # 已有同键请求在途执行：语义为"稍后重试"，返回 40930（对齐 Stripe/AWS IdempotencyAlreadyInProgress）
            logger.info(f"[Idempotency] 同键在途执行，返回 in_progress: {idem_key}")
            return JSONResponse(
                status_code=409,
                content={
                    "code": TRADE_IDEMPOTENCY_IN_PROGRESS,
                    "message": "该幂等请求正在处理中，请稍后重试",
                    "data": None,
                },
            )

        # 3) 拿到锁 → 放行执行业务
        try:
            response = await call_next(request)
            if response.status_code < 400:
                body = b""
                body_iter = response.body_iterator
                if hasattr(body_iter, "__aiter__"):
                    async for chunk in body_iter:
                        body += chunk
                else:
                    for chunk in body_iter:
                        body += chunk

                try:
                    body_data = json.loads(body) if body else {"code": 0, "message": "ok", "data": None}
                except (ValueError, TypeError):
                    body_data = {"code": 0, "message": "ok", "data": None}

                try:
                    cache_data = {
                        "body": body_data,
                        "status": response.status_code,
                        "headers": dict(response.headers),
                        "uid": user_id,
                        "ph": payload_hash,
                    }
                    await r.set(resp_key, json.dumps(cache_data, default=str), ex=_CACHE_TTL)
                except Exception as exc:
                    logger.warning(f"[Idempotency] 缓存响应失败: {exc}")

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
        finally:
            # 释放锁（仅在锁仍属于本次请求时，用 token 比对，防误删他人已重获的锁）
            try:
                await r.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
                    1, lock_key, lock_token,
                )
            except Exception:
                pass