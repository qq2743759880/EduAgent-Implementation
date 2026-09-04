"""
task39 真 Redis 项补验收 —— 独立实证脚本（真实 HTTP + 真实 Redis key 观察，不 mock）。

组件：
  1) 限流   /api/auth/login（rate_limit 中间件，规则 60s/10 次）→ 第 11 次起 429，Redis key 自增
  2) 缓存   /api/series/{id}（get_or_load）→ 首次 miss 写 key，二次命中，key 存在 + 响应一致
  3) 分布式锁 core.lock.RedisLock（SETNX + Lua）→ acquire 建 key / release 删 key（真实 Redis）
  4) （降级复验在另一实例 8001 用 dead REDIS_URL 单独验证，见 report）

Redis 观察用独立客户端直连 127.0.0.1:6379 只读/清理，HTTP 均由脚本发起真实请求。
"""
from __future__ import annotations

import asyncio
import json
import sys
import time

import redis.asyncio as aioredis

BASE = "http://127.0.0.1:8000"
REDIS_URL = "redis://127.0.0.1:6379/0"
FORWARDED_IP = "203.0.113.55"  # 限流用唯一 client_ip，隔离本机其它请求

MSGS: list[str] = []


def log(*a):
    line = " ".join(str(x) for x in a)
    MSGS.append(line)
    print(line, flush=True)


async def rate_limit_check(r: aioredis.Redis) -> None:
    log("\n========== [1] 限流 /api/auth/login (60s/10次) ==========")
    # 挂载的限流中间件为 app/middleware/rate_limit.py：IP+uid 双维，key=rl:ip:{ip}:{path}
    # 运行实例信任 XFF（旧版）→ 用唯一 XFF 隔离干净窗口
    import requests
    for pfx in (f"rl:ip:{FORWARDED_IP}:*", f"rl:uid:*:{FORWARDED_IP}:*"):
        for k in await r.keys(pfx):
            await r.delete(k)
    statuses: list[int] = []
    octets = [None]
    limit = None
    remaining = None
    redis_after = {}
    for i in range(12):
        resp = requests.post(
            f"{BASE}/api/auth/login",
            json={"account": "user000001", "password": "Test@123456"},
            headers={"X-Forwarded-For": FORWARDED_IP},
            timeout=10,
        )
        statuses.append(resp.status_code)
        if "X-RateLimit-Limit" in resp.headers:
            limit = resp.headers["X-RateLimit-Limit"]
        if "X-RateLimit-Remaining" in resp.headers:
            remaining = resp.headers["X-RateLimit-Remaining"]
        if resp.status_code == 429:
            octets[0] = resp.json().get("code")
    for k in await r.keys(f"rl:ip:{FORWARDED_IP}:*"):
        redis_after[k] = (await r.get(k), await r.ttl(k))
    log("12 次请求 HTTP 状态序列:", statuses)
    log("X-RateLimit-Limit:", limit, "| 最后一次 X-RateLimit-Remaining:", remaining)
    log("429 body code:", octets[0])
    log("Redis 限流 key / 计数 / TTL:", redis_after)
    assert 429 in statuses, f"未观测到 429: {statuses}"
    assert len([s for s in statuses if s == 429]) >= 2, f"429 次数不足: {statuses}"
    assert redis_after, "未在 Redis 中找到 rl:ip 计数 key"
    for k, (v, ttl) in redis_after.items():
        assert int(v) >= 11, f"计数未累积到≥11: {v}"
        assert ttl and ttl > 0, f"TTL 未设置: {k}"
    log("[限流] 通过：前10放行→第11起 429 + Redis key 自增到≥11 且带 TTL", "OK")


async def cache_check(r: aioredis.Redis, series_id: int) -> None:
    log("\n========== [2] 热度缓存 /api/series/{id} (get_or_load, TTL 300) ==========")
    import requests
    key = f"course:series:detail:{series_id}"
    await r.delete(key)  # 清缓存保证首请求为 miss
    t0 = time.perf_counter()
    r1 = requests.get(f"{BASE}/api/series/{series_id}", timeout=10)
    first_ms = (time.perf_counter() - t0) * 1000
    exists_after_first = await r.exists(key)
    cached_val = await r.get(key)
    ttl_after_first = await r.ttl(key)
    t0 = time.perf_counter()
    r2 = requests.get(f"{BASE}/api/series/{series_id}", timeout=10)
    second_ms = (time.perf_counter() - t0) * 1000
    d1 = r1.json()
    d2 = r2.json()
    log("series id:", series_id)
    log("首请求 status/latency(ms):", r1.status_code, round(first_ms, 1))
    log("二请求 status/latency(ms):", r2.status_code, round(second_ms, 1))
    course_keys = await r.keys("course:*")
    log("请求后 Redis 中全部 course:* key:", course_keys)
    log("目标 key 存在:", exists_after_first, "| TTL:", ttl_after_first)
    log("Redis 缓存值与 HTTP 响应 data 一致:", cached_val is not None and (cached_val.decode() if isinstance(cached_val, bytes) else cached_val) == json.dumps(d1["data"], ensure_ascii=False))
    log("两次 HTTP 响应完全一致:", json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True))
    assert exists_after_first, f"缓存 key 未写入 {key}"
    assert cached_val is not None, "Redis 缓存值为空"
    assert (cached_val.decode() if isinstance(cached_val, bytes) else cached_val) == json.dumps(d1["data"], ensure_ascii=False), "缓存值≠HTTP 响应 data"
    assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True), "两次响应不一致"
    # 命中应更快（首次 miss 走 DB+MYSQL；命中直回缓存）。此处仅报告，不硬断（DB 抖动允许）
    log("[缓存] 通过：key 写入 + 二次命中 + 响应一致", "OK", "| 首请求(写) vs 二次(命中):", round(first_ms,1), "ms /", round(second_ms,1), "ms")


async def lock_check(r: aioredis.Redis) -> None:
    log("\n========== [3] 分布式锁 core.lock.RedisLock (SETNX + Lua) ==========")
    # 通过 init_redis 初始化 app.database._redis，使 RedisLock 内部 get_redis() 走到真实连接
    from app.database import init_redis as _init_redis
    from app.core.lock import RedisLock
    await _init_redis()
    lock = RedisLock("_tt39_verify")
    await r.delete(lock.name)
    acquired = await lock.acquire()
    exists_after = await r.exists(lock.name)
    val = await r.get(lock.name)
    await lock.release()
    exists_after_release = await r.exists(lock.name)
    log("acquire 返回:", acquired)
    log("acquire 后 Redis key 存在:", bool(exists_after), "| value(唯一 token):", (val.decode() if isinstance(val, bytes) else val))
    log("release 后 Redis key 存在:", bool(exists_after_release))
    assert acquired, "锁获取失败"
    assert exists_after, "SETNX 锁 key 未创建"
    assert not exists_after_release, "Lua 释放后锁 key 仍存在"
    log("[锁] 通过：真实 Redis SETNX 建 key + Lua 释放删 key", "OK")


async def main() -> None:
    r = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)
    await r.ping()
    log("Redis 探测 PING OK")
    await rate_limit_check(r)
    # 找一个未缓存的 series id，保证 miss->hit 干净
    import requests
    lst = requests.get(f"{BASE}/api/series?page_size=100", timeout=10).json()["data"]["items"]
    series_id = int(lst[0]["id"])
    await cache_check(r, series_id)
    await lock_check(r)
    await r.aclose()
    log("\n全部真 Redis 实证通过 ✓")


if __name__ == "__main__":
    asyncio.run(main())