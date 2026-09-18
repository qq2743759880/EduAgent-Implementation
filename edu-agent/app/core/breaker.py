"""
Polaris 式熔断器（Phase 重构：task09 core/ 框架层）

对齐腾讯 PolarisMesh 三态模型：closed → open → half_open → closed

增强特性：
- Redis Hash 共享状态（breaker:{name}）：多进程/多实例共享熔断状态
- 100ms 本地缓存：减少 Redis 读开销
- edu_breaker_state Gauge 指标：Prometheus 可观测

面试考点：
- 为什么需要熔断器？防止级联故障——外部依赖不可用时，快速失败比等待超时更好
- 三态转换：closed（正常）→ open（错误率超阈值）→ half_open（探针测试）→ closed（恢复）
- Redis Hash 共享 vs 本地内存：多 worker 部署时，本地内存无法共享状态，Redis Hash 保证一致性

用法：
  from app.core.breaker import CircuitBreaker, CircuitOpenError
  breaker = CircuitBreaker("milvus")
  try:
      result = await breaker.call(lambda: milvus_search(...))
  except CircuitOpenError:
      # 熔断中，返回降级结果
      return degraded_response()
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from loguru import logger


class BreakerState(str, Enum):
    CLOSED = "closed"          # 正常
    OPEN = "open"              # 熔断
    HALF_OPEN = "half_open"    # 半开（探针测试）


@dataclass
class BreakerConfig:
    """熔断器配置。"""
    min_requests: int = 20              # 统计窗口最小样本量
    error_rate_threshold: float = 0.5   # 错误率阈值
    open_duration: float = 30.0         # 熔断持续时间（秒）
    half_open_probes: int = 3           # 半开探针数
    local_cache_ms: int = 100           # 本地缓存时间（毫秒）
    consecutive_failures: int | None = None  # 连续失败 N 次直接断路（如 MCP per-server=5）；None 走错误率模式


class CircuitOpenError(Exception):
    """熔断器打开时抛出的异常。"""
    pass


# ── Prometheus Gauge（可选，不强制依赖 prometheus_client）──
try:
    from prometheus_client import Gauge

    _breaker_gauge = Gauge(
        "edu_breaker_state",
        "熔断器状态（0=closed, 1=open, 2=half_open）",
        ["name"],
    )
except ImportError:
    _breaker_gauge = None


def _state_to_int(state: BreakerState) -> int:
    return {BreakerState.CLOSED: 0, BreakerState.OPEN: 1, BreakerState.HALF_OPEN: 2}[state]


@dataclass
class CircuitBreaker:
    """
    熔断器（Redis Hash 共享 + 本地缓存）。

    状态机：
    - CLOSED：正常调用，统计错误率。错误率 > threshold → OPEN
    - OPEN：快速失败，抛 CircuitOpenError。持续 open_duration 秒 → HALF_OPEN
    - HALF_OPEN：放行探针请求。成功数 ≥ probes → CLOSED；任一失败 → OPEN
    """
    name: str
    config: BreakerConfig = field(default_factory=BreakerConfig)

    # 运行时状态（本地缓存，从 Redis Hash 同步）
    _state: BreakerState = field(default=BreakerState.CLOSED, init=False)
    _requests: int = field(default=0, init=False)
    _errors: int = field(default=0, init=False)
    _consecutive_errors: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)
    _half_open_successes: int = field(default=0, init=False)
    _last_sync: float = field(default=0.0, init=False)

    @property
    def _redis_key(self) -> str:
        return f"breaker:{self.name}"

    async def _get_redis(self):
        try:
            from app.database import get_redis
            return get_redis()
        except RuntimeError:
            return None

    async def _sync_from_redis(self):
        """从 Redis Hash 同步状态到本地缓存（Redis 不可达时静默跳过，仅用本地状态）。"""
        # H1a（T19-2/L2）：已知 Redis 故障（快断窗/降级保持窗）内不做网络同步——
        # hgetall 单次实测 ~2.03s 才失败，会让每个 breaker.call 白付 2s。
        # 退化本地状态（本方法文档语义即允许）。
        from app.core.redis_outage import redis_degrade_active

        if redis_degrade_active():
            self._last_sync = time.time()
            return
        try:
            r = await self._get_redis()
            if r is None:
                return
            data = await r.hgetall(self._redis_key)
            if not data:
                return
            # P0 修复（R-M1 故障注入实测发现，2026-09-18）：共享客户端
            # （app/database.init_redis）是 decode_responses=True，hgetall 返回 str 键值；
            # 旧代码按 bytes 键取值全部 miss → state/consecutive_errors 每次同步被静默
            # 清零 → consecutive_failures 阈值永远达不到（熔断器永不 OPEN）、OPEN 态
            # 同步后即蒸发。改为 str/bytes 双兼容读取（对 bytes 客户端语义不变）。
            def _hget(key: str):
                v = data.get(key, data.get(key.encode("utf-8")))
                if isinstance(v, bytes):
                    return v.decode("utf-8")
                return v

            self._state = BreakerState(_hget("state") or "closed")
            self._requests = int(_hget("requests") or 0)
            self._errors = int(_hget("errors") or 0)
            self._consecutive_errors = int(_hget("consecutive_errors") or 0)
            self._opened_at = float(_hget("opened_at") or 0.0)
            self._half_open_successes = int(_hget("half_open_successes") or 0)
        except Exception:
            # Redis 不可用（含 task-P1C：Redis 自身就是被测依赖）→ 退化本地状态，绝不阻断熔断逻辑
            pass
        finally:
            self._last_sync = time.time()

    async def _sync_to_redis(self):
        """将本地状态同步到 Redis Hash（Redis 不可达时静默跳过）。"""
        # H1a：故障（快断窗/降级保持窗）内同样跳过（hset 单次实测 ~2.03s，纯浪费——
        # 后台探测自愈后下次成功即回写）
        from app.core.redis_outage import redis_degrade_active

        if redis_degrade_active():
            return
        try:
            r = await self._get_redis()
            if r is None:
                return
            await r.hset(self._redis_key, mapping={
                "state": self._state.value,
                "requests": str(self._requests),
                "errors": str(self._errors),
                "consecutive_errors": str(self._consecutive_errors),
                "opened_at": str(self._opened_at),
                "half_open_successes": str(self._half_open_successes),
            })
        except Exception:
            # 同 _sync_from_redis：Redis 不可达时静默跳过，熔断逻辑不依赖本次同步成功
            pass

    def _update_gauge(self):
        """更新 Prometheus Gauge 指标。"""
        if _breaker_gauge is not None:
            try:
                _breaker_gauge.labels(name=self.name).set(_state_to_int(self._state))
            except Exception:
                pass

    async def _maybe_sync(self):
        """按需同步（100ms 本地缓存）。"""
        now = time.time()
        if (now - self._last_sync) * 1000 >= self.config.local_cache_ms:
            await self._sync_from_redis()
            self._last_sync = now

    async def check(self) -> None:
        """熔断闸门：仅做状态检查，不记录调用结果。

        调用方负责在完成调用后显式 `record_success/_failure`，
        适用于「失败以返回值/状态码表达而非抛异常」的场景（task33 MCP per-server 熔断）。

        Raises:
            CircuitOpenError: 熔断打开且未到 open_duration，需快速失败
        """
        await self._maybe_sync()
        if self._state == BreakerState.OPEN:
            if time.time() - self._opened_at >= self.config.open_duration:
                await self._to_half_open()
            else:
                raise CircuitOpenError(f"熔断器 {self.name} 已打开")

    async def record_success(self) -> None:
        """显式记录一次成功（半开探针成功 / 关闭态正常调用）。"""
        self._on_success()
        await self._sync_to_redis()
        self._update_gauge()

    async def record_failure(self) -> None:
        """显式记录一次失败（可能触发 Open → 连续失败/错误率阈值）。"""
        await self._on_error()

    async def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        执行调用，熔断器自动管理状态。

        Args:
            fn: 要执行的函数（同步或异步）
            *args, **kwargs: 函数参数

        Returns:
            函数返回值

        Raises:
            CircuitOpenError: 熔断器打开时
            Exception: 函数本身抛出的异常
        """
        # 熔断闸门（OPEN 且未到 open_duration 则快速失败）
        await self.check()

        # 执行调用
        try:
            if asyncio.iscoroutinefunction(fn):
                result = await fn(*args, **kwargs)
            else:
                result = fn(*args, **kwargs)
                # 兼容「普通函数返回协程」的场景（如 lambda: coro_fn(...)）：
                # asyncio.iscoroutinefunction(lambda) 为 False，但 lambda 返回 coroutine，必须 await
                if asyncio.iscoroutine(result):
                    result = await result
            await self.record_success()
            return result
        except CircuitOpenError:
            raise
        except Exception as exc:
            await self.record_failure()
            raise exc

    def _on_success(self):
        if self._state == BreakerState.HALF_OPEN:
            self._half_open_successes += 1
            if self._half_open_successes >= self.config.half_open_probes:
                self._to_closed()
        elif self._state == BreakerState.CLOSED:
            self._requests += 1
            self._consecutive_errors = 0

    async def _on_error(self):
        if self._state == BreakerState.HALF_OPEN:
            await self._to_open()
        elif self._state == BreakerState.CLOSED:
            self._requests += 1
            self._errors += 1
            self._consecutive_errors += 1
            # 连续失败优先（如 MCP per-server=5）：达到阈值直接断路，无需等待错误率统计窗口
            if self.config.consecutive_failures is not None:
                if self._consecutive_errors >= self.config.consecutive_failures:
                    await self._to_open()
            elif (
                self._requests >= self.config.min_requests
                and self._errors / self._requests >= self.config.error_rate_threshold
            ):
                await self._to_open()
        await self._sync_to_redis()
        self._update_gauge()

    async def _to_open(self):
        self._state = BreakerState.OPEN
        self._opened_at = time.time()
        logger.warning(f"[Breaker] {self.name} 熔断: {self._errors}/{self._requests} errors")
        await self._sync_to_redis()
        self._update_gauge()

    async def _to_half_open(self):
        self._state = BreakerState.HALF_OPEN
        self._half_open_successes = 0
        logger.info(f"[Breaker] {self.name} 进入半开状态")
        await self._sync_to_redis()
        self._update_gauge()

    def _to_closed(self):
        self._state = BreakerState.CLOSED
        self._requests = 0
        self._errors = 0
        self._consecutive_errors = 0
        logger.info(f"[Breaker] {self.name} 恢复关闭")
        self._update_gauge()


# 全局熔断器注册表（按依赖名）
_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(name: str) -> CircuitBreaker:
    """获取或创建熔断器。"""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name=name)
    return _breakers[name]