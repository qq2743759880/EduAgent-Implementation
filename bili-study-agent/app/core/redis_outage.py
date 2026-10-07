"""
进程级 Redis 故障快断窗（热修波 H1a，T19-2/L2 根因修复的一半）。

背景（2026-09-12 实测，Redis 容器未运行）：
- redis-py 对「连接被拒」并不快断：单次操作（incr/get/hgetall…）内部重试退避，
  实测每次 ~2.03s 才抛 ConnectionError（socket_connect_timeout=3s 名义值之外，
  实际由客户端 Retry(backoff) 主导）。
- 请求路径上 RateLimitMiddleware 每请求 1 次 incr、core/breaker 状态同步每次
  call 1 次 hgetall/hset —— 只要 Redis 宕着，全站每个 /api/* 请求固定 +2s，
  课程系列详情这类多 Redis 触点路径 +4s（实测 4.06s；冷启动含池预热 13.6s）。
  这就是 T19-2 批判「GET series/1 8~16s」的根因之一（另一半是多查询聚合，
  已在 app/domains/course/service.get_series_detail 做查询合并）。

方案：
- 进程内记一个「最近一次 Redis 连接失败」的单调时钟窗口（默认 30s，对齐
  db_resilience 里 redis_breaker.open_duration）；
- 窗口激活期内，非必要 Redis 调用方（限流中间件、breaker 状态同步、redis_run 门）
  直接本地快断/降级直通，不触网络；
- 窗口到期后恢复正常探测：Redis 已恢复则首次成功即 mark_redis_up（自愈）；
  仍宕则首笔失败重新 mark_redis_down（每窗口只付一次真实失败成本）。
- 纯本地 monotonic 时钟，本模块自身零 Redis 依赖、零网络调用、线程安全（GIL 下
  浮点赋值原子；asyncio 单线程事件循环内无竞争）。

为什么不用 app.core.cache：本模块不缓存业务数据、不引 Redis 客户端，只是
「已知宕机」的进程内事实，属于 db_resilience/breaker 的公共底座。
"""
from __future__ import annotations

import asyncio
import time

# 快断窗冷却时长（秒）：对齐 app/core/db_resilience._REDIS_CONFIG.open_duration=30。
# 期间全站跳过 Redis 触点；代价是 Redis 真恢复后最多 30s 内仍降级直通（可接受）。
REDIS_OUTAGE_COOLDOWN_DEFAULT = 30.0

# 降级保持窗（秒）：最近一次故障后的这段时间内维持「降级模式」，由后台探测自愈，
# 请求路径不再做内联探测（内联探测=白付一次 ~2s）。探测成功立即全量恢复。
REDIS_DEGRADE_RECENT_WINDOW = 120.0

# 单调时钟状态：
# _down_until    —— 快断窗到期时刻（0=从未故障/已恢复清零）
# _last_down_at  —— 最近一次 mark_redis_down 时刻（mark_redis_up 清零）
# _last_probe_at —— 最近一次后台探测发起时刻（防任务风暴）
_down_until: float = 0.0
_last_down_at: float = 0.0
_last_probe_at: float = 0.0
_probe_task: "asyncio.Task | None" = None


def mark_redis_down(cooldown: float | None = None) -> None:
    """登记一次 Redis 连接级失败：激活/顺延快断窗 + 降级保持窗。"""
    global _down_until, _last_down_at
    cd = float(cooldown) if cooldown is not None else REDIS_OUTAGE_COOLDOWN_DEFAULT
    now = time.monotonic()
    _down_until = now + max(cd, 0.0)
    _last_down_at = now


def mark_redis_up() -> None:
    """Redis 操作成功：立即清除全部故障状态（自愈，无需等冷却到期）。"""
    global _down_until, _last_down_at
    _down_until = 0.0
    _last_down_at = 0.0


def redis_outage_active() -> bool:
    """快断窗是否激活（到期自动失活）。"""
    return _down_until != 0.0 and time.monotonic() < _down_until


def redis_recently_down() -> bool:
    """是否处于「降级保持窗」（最近发生过故障，尚未被成功操作清零）。"""
    return _last_down_at != 0.0 and time.monotonic() < _last_down_at + REDIS_DEGRADE_RECENT_WINDOW


def redis_degrade_active() -> bool:
    """降级模式总闸：快断窗激活 OR 降级保持窗内。

    调用方（限流中间件 / redis_run 门 / breaker 同步）据此毫秒级本地快断，
    并调 ensure_probe() 触发后台自愈探测——请求路径永不内联等待 Redis 失败。
    """
    return redis_outage_active() or redis_recently_down()


def ensure_probe() -> None:
    """调度一次后台 Redis 探测（幂等：单飞行任务 + ≥冷却时长的发起间隔）。

    探测在后台任务里真实触达 Redis：
    - 成功 → mark_redis_up（全站立即恢复限流/缓存）；
    - 失败 → mark_redis_down（顺延快断窗，请求路径继续零等待）。
    探测成本（宕机时 ~2s）完全脱离请求路径。
    """
    global _probe_task, _last_probe_at
    now = time.monotonic()
    if _probe_task is not None and not _probe_task.done():
        return
    if now - _last_probe_at < REDIS_OUTAGE_COOLDOWN_DEFAULT:
        return
    _last_probe_at = now
    _probe_task = asyncio.create_task(_probe_once())


async def _probe_once() -> None:
    global _probe_task
    try:
        from app.database import get_redis

        r = get_redis()
        await r.incr("rl:probe:outage_selfheal")
        mark_redis_up()
    except Exception:
        mark_redis_down()
    finally:
        _probe_task = None


def reset_for_test() -> None:
    """测试隔离用：无条件清窗（生产代码勿调）。"""
    global _down_until, _last_down_at, _last_probe_at, _probe_task
    _down_until = 0.0
    _last_down_at = 0.0
    _last_probe_at = 0.0
    if _probe_task is not None and not _probe_task.done():
        _probe_task.cancel()
    _probe_task = None
