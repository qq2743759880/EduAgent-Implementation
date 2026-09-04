# -*- coding: utf-8 -*-
"""task39 批判 Round3 · 幂等中间件实证（真实 Redis + 真实 ASGI 链路 httpx）

修复对齐 Stripe/AWS Powertools 的三个缺陷（task39 批判 Round3，竞品对标）：
1. 幂等命中：同键同体同身份重放 → 返回首次缓存，业务只执行一次
2. payload 不一致：同键改内容 → 422 {code:"42230"}（复用键被拒，不返回旧缓存）
3. 跨用户复用：同键被别的用户重放 → 422 {code:"42230"}（不泄露首次用户响应）
4. 并发在途：SETNX 锁被占 → 409 {code:"40930"}（already_in_progress）

用 Starlette 原生 ASGI（httpx ASGITransport）实现，真实 Redis 实证
（FastAPI TestClient 对 body 的预读/中间件交互与原生 ASGI 不同，会误报，故不用）。

Redis 不可达时整组 skip（环境依赖，非代码缺陷）。

跨 event loop 处理：每个测试用 `asyncio.run()` 开独立 loop，故 Redis client 一律
在对应 run() 的 loop 内新建（from_url 懒连接，首次命令才建连），杜绝复用已关闭 loop
的共享连接句柄（此前报 "Event loop is closed"）。
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, r"e:/stu/project/stu/EduAgent实施手册/edu-agent")

import pytest
import redis.asyncio as aioredis
import httpx
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

import app.database as db
from app.middleware.idempotency import IdempotencyMiddleware  # noqa: E402

_REDIS_URL = "redis://localhost:6379/0"


def _new_client() -> aioredis.Redis:
    return aioredis.Redis.from_url(_REDIS_URL, socket_connect_timeout=2)


class _UserInject(BaseHTTPMiddleware):
    """模拟 auth 中间件：注入 request.state.user_id（生产由 AuthMiddleware 注入）。"""

    async def dispatch(self, request, call_next):
        request.state.user_id = request.headers.get("X-User-Id", "anon")
        return await call_next(request)


@pytest.fixture
def ctx(monkeypatch):
    """真实 Redis + 幂等中间件 app 的 httpx 客户端。

    get_redis 改为「每次调用在其请求自身的 event loop 内新建 client」，
    规避 fixture/测试跨 `asyncio.run()` 复用共享连接导致的 "Event loop is closed"。
    """
    async def _probe() -> bool:
        c = _new_client()
        try:
            await c.ping()
            return True
        except Exception:
            return False
        finally:
            try:
                await c.aclose()
            except Exception:
                pass

    try:
        reachable = asyncio.run(_probe())
    except Exception:
        reachable = False
    if not reachable:
        pytest.skip("真实 Redis 不可达（环境依赖，非代码缺陷）")

    # 生产 get_redis 返回共享单例；测试改为每请求在其自身 loop 内新建（懒连接），
    # 中间件每次请求只取一次，功能等价且规避跨 loop 连接句柄失效。
    monkeypatch.setattr(db, "get_redis", _new_client)

    calls = {"n": 0}

    async def order(request):
        await request.body()  # 消费 body（真实业务会读）
        calls["n"] += 1
        return JSONResponse({"code": 0, "message": "ok", "data": {"order_no": f"T{calls['n']}"}})

    async def refund(request):
        await request.body()
        calls["n"] += 1
        return JSONResponse({"code": 0, "message": "ok", "data": {"refund_no": f"R{calls['n']}"}})

    app = Starlette(
        routes=[
            Route("/api/trade/order", order, methods=["POST"]),
            Route("/api/trade/refund", refund, methods=["POST"]),
        ]
    )
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(_UserInject)

    yield (app, calls)


async def _clean_all() -> None:
    """在调用方自身 loop 内清理 idem:* 键。"""
    c = _new_client()
    try:
        keys = await c.keys("idem:*")
        if keys:
            await c.delete(*keys)
    finally:
        try:
            await c.aclose()
        except Exception:
            pass


def test_idempotent_miss_then_hit(ctx):
    """同键同体同身份重放 → 命中缓存，业务只执行一次。"""
    app, calls = ctx

    async def run():
        await _clean_all()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
            h = {"Idempotency-Key": "k1", "X-User-Id": "1001", "Content-Type": "application/json"}
            r1 = await ac.post("/api/trade/order", json={"a": 1}, headers=h)
            assert r1.status_code == 200, r1.text
            assert r1.json()["data"]["order_no"] == "T1"
            r2 = await ac.post("/api/trade/order", json={"a": 1}, headers=h)
            assert r2.status_code == 200, r2.text
            assert r2.json()["data"]["order_no"] == "T1", f"应命中缓存返回首次响应, got {r2.json()}"
            assert calls["n"] == 1, f"业务执行 {calls['n']} 次，应为 1"

    asyncio.run(run())


def test_idempotent_payload_mismatch_rejected(ctx):
    """同键但 body 变化 → 422 {code:42230}，业务不二次执行、不返回旧缓存。"""
    app, calls = ctx

    async def run():
        await _clean_all()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
            h = {"Idempotency-Key": "k2", "X-User-Id": "1001", "Content-Type": "application/json"}
            r1 = await ac.post("/api/trade/refund", json={"amount": 10}, headers=h)
            assert r1.status_code == 200
            r2 = await ac.post("/api/trade/refund", json={"amount": 999}, headers=h)
            assert r2.status_code == 422, f"应 422, got {r2.status_code} {r2.text}"
            assert r2.json()["code"] == "42230", r2.json()
            assert calls["n"] == 1, f"业务执行 {calls['n']} 次，应为 1"

    asyncio.run(run())


def test_idempotent_cross_user_rejected(ctx):
    """同键被另一个用户复用 → 422 {code:42230}，不泄露首次用户响应。"""
    app, calls = ctx

    async def run():
        await _clean_all()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
            h1 = {"Idempotency-Key": "k3", "X-User-Id": "1001", "Content-Type": "application/json"}
            r1 = await ac.post("/api/trade/order", json={"a": 1}, headers=h1)
            assert r1.status_code == 200
            h2 = {"Idempotency-Key": "k3", "X-User-Id": "9999", "Content-Type": "application/json"}
            r2 = await ac.post("/api/trade/order", json={"a": 1}, headers=h2)
            assert r2.status_code == 422, f"应 422, got {r2.status_code} {r2.text}"
            assert r2.json()["code"] == "42230", r2.json()

    asyncio.run(run())


def test_idempotent_in_progress_lock(ctx):
    """并发同键在途：预置锁后请求 SETNX 失败 → 409 {code:40930}。"""
    app, calls = ctx

    async def run():
        await _clean_all()
        c = _new_client()
        try:
            # 预置在途锁（模拟另一并发请求已抢锁）
            await c.set("idem:lock:kinflight", "other", nx=True, ex=30)
        finally:
            await c.aclose()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
            h = {"Idempotency-Key": "kinflight", "X-User-Id": "1001", "Content-Type": "application/json"}
            r = await ac.post("/api/trade/order", json={"a": 1}, headers=h)
            assert r.status_code == 409, f"应 409, got {r.status_code} {r.text}"
            assert r.json()["code"] == "40930", r.json()
            assert calls["n"] == 0, "在途请求不应执行业务"

    asyncio.run(run())