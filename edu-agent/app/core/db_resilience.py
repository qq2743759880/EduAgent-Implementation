"""Neo4j / Redis 断连熔断（task-P1C）。

复用 task33 的 CircuitBreaker（app.core.breaker），为「数据链路」依赖加 per-dependency 熔断：
- 连续 N 次失败 → OPEN：后续请求**毫秒级快速失败**（不再傻等连接超时）
- open_duration（默认 30s）后 → HALF_OPEN 放行探针
- 探针连续成功 → CLOSED 恢复；任一失败 → 回到 OPEN

降级埋点复用 task39 的 metrics.record_degraded / clear_degraded：
- 熔断打开 / 依赖失败 → record_degraded(component, reason)（edu_degraded_total{component,reason} + degraded_active=1）
- 依赖恢复（探针成功）→ clear_degraded(component)（degraded_active=0）

竞品对标：
- Codex auto-review 拒绝熔断（连续拒绝中断）：developers.openai.com/codex/concepts/sandboxing/auto-review
- Gremlin Chaos Engineering（最小爆炸半径）：gremlin.com/chaos-engineering
- 复用 core/breaker.py（task33 已实现 per-server 熔断 + CircuitOpenError + 半开）
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from app.core.breaker import BreakerConfig, CircuitBreaker, CircuitOpenError
from app.monitoring import metrics


# 连续失败阈值：task33 per-server 用 5；Neo4j/Redis 数据链路同样 5 次连续失败即断路。
# 可通过 settings.NEO4J_REDIS_BREAKER_FAILURES 覆盖（生产可调）；默认 5。
def _consecutive_failures(default: int) -> int:
    try:
        from app.config import settings

        v = getattr(settings, "NEO4J_REDIS_BREAKER_FAILURES", None)
        if isinstance(v, int) and v > 0:
            return v
    except Exception:
        pass
    return default


# 熔断配置：连续失败开路 + 30s 后半开探针（GWT②）。
# error_rate 分支不启用（consecutive_failures 优先，min_requests/error_rate_threshold 仅占位）。
_NEO4J_CONFIG = BreakerConfig(
    consecutive_failures=_consecutive_failures(5),
    open_duration=30.0,
    min_requests=1,
    error_rate_threshold=1.0,
)
_REDIS_CONFIG = BreakerConfig(
    consecutive_failures=_consecutive_failures(5),
    open_duration=30.0,
    min_requests=1,
    error_rate_threshold=1.0,
)

# 全局熔断器实例（与 task33 get_breaker 同款注册理念；独立实例便于按依赖观测/配置）
neo4j_breaker = CircuitBreaker("neo4j", config=_NEO4J_CONFIG)
redis_breaker = CircuitBreaker("redis", config=_REDIS_CONFIG)


class DependencyUnavailableError(Exception):
    """依赖被熔断/不可用：调用方应走降级路径（返回空结果 / 直通 DB）。"""


async def _run_with_breaker(
    breaker: CircuitBreaker,
    component: str,
    op_name: str,
    coro_fn: Callable[[], Awaitable[Any]],
) -> Any:
    """通用熔断执行：成功/失败自动管理状态；OPEN 时抛 DependencyUnavailableError。

    - 成功 → 清降级态（clear_degraded）
    - 失败（breaker 已记一次失败，可能触发 OPEN）→ record_degraded 并原样抛出
    - 已 OPEN → 抛 CircuitOpenError → 转 DependencyUnavailableError + record_degraded（快速失败，不触达依赖）
    """
    try:
        result = await breaker.call(coro_fn)
    except CircuitOpenError:
        # 熔断中：快速失败（不触达依赖），记录降级
        metrics.record_degraded(component, f"{op_name}:breaker_open")
        raise DependencyUnavailableError(
            f"{component} 熔断中（{op_name}）毫秒级快速失败"
        ) from None
    except Exception as exc:
        # breaker.call 已记失败（可能已 OPEN）；同时计 degraded（失败即降级面）
        metrics.record_degraded(component, f"{op_name}:{type(exc).__name__}")
        raise
    else:
        # 成功（含 half-open 探针成功 → CLOSED）：清降级态
        metrics.clear_degraded(component)
        return result


async def neo4j_run(op_name: str, fn: Callable[[], Any]) -> Any:
    """熔断保护下执行【同步】Neo4j 操作（fn 为同步函数，内部 to_thread 不阻塞事件循环）。

    用法：
        rows = await neo4j_run("graph_expand", lambda: _do_session_run(driver, cypher, kw))
    """
    async def _runner() -> Any:
        return await asyncio.to_thread(fn)

    return await _run_with_breaker(neo4j_breaker, "neo4j", op_name, _runner)


async def redis_run(op_name: str, coro_fn: Callable[[], Awaitable[Any]]) -> Any:
    """熔断保护下执行【异步】Redis 操作（coro_fn 为 async 函数）。

    用法：
        val = await redis_run("cache_get", lambda: get_redis().get(key))
    """
    return await _run_with_breaker(redis_breaker, "redis", op_name, coro_fn)


def get_neo4j_breaker() -> CircuitBreaker:
    """获取 Neo4j 熔断器（观测/测试用）。"""
    return neo4j_breaker


def get_redis_breaker() -> CircuitBreaker:
    """获取 Redis 熔断器（观测/测试用）。"""
    return redis_breaker
