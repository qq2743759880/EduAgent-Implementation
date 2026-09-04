"""
task26 Redis 防过载：LLM 全局并发闸 + 单用户会话并发 + 队列削峰 + ZSET 分片 + 大 key 治理。

对齐 tech-source-audit §四（Redis 多角色：队列削峰 / 大 key 治理）：
- 全局 LLM 并发闸：上限 LLM_GLOBAL_CONCURRENCY(8)。进程内信号量（快） + Redis 分布式原子计数
  （Lua INCR/DECR 带上限）双闸；任一闸满 → 请求进队列。
- 队列削峰：`chat:queue` Redis list（RPUSH + BLPOP），BLPOP 阻塞上限 QUEUE_POP_TIMEOUT(10s)，
  超时返回友好提示而非无限堆积。
- 单用户会话并发：`chat:concurrent:{user_id}` INCR/DECR，第 3 个并发被拒（≤ USER_MAX_CONCURRENT）。
- ZSET 分片：单分片容量 ZSET_SHARD_SIZE(50)，按 member 哈希分桶写 `{key}:{idx}`，避免大 key。
- 大 key 治理：SCAN 扫描，strings 超 BIGKEY_THRESHOLD_BYTES(1MB) → 告警清单。
- 降级：Redis 不可用时全链路回退内存实现（本地/学中玩不阻塞）；checkpoint TTL 7 天由 config 提供。

设计说明：guard 是请求级短生命周期组件；`acquire`/`release` 必须在 finally 成对，防泄漏导致闸失效。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

from loguru import logger

from app.config import settings


class TokenBucket:
    """令牌桶（G1-②）：以恒定速率 refill，替代固定 60s 窗口，消除窗口边界 2× 突发。

    与 ``TokenBudgetGuard`` 的「已用 token」抽象对接：``used = capacity - tokens``，
    因此接入后既有的 ``acquire`` / ``_admit_token_waiters`` 速率比较逻辑无需改动。
    """

    def __init__(self, refill_per_min: float, capacity: float | None = None,
                 *, refill_window_sec: float = 60.0, now: float | None = None) -> None:
        self.refill_per_min = float(refill_per_min)
        self.refill_window_sec = float(refill_window_sec)
        self.capacity = float(capacity if capacity is not None else refill_per_min)
        self.tokens = self.capacity
        self._t = float(now if now is not None else time.monotonic())

    def _refill(self, now: float) -> None:
        if now > self._t:
            per_sec = self.refill_per_min / max(1e-6, self.refill_window_sec)
            self.tokens = min(self.capacity, self.tokens + (now - self._t) * per_sec)
            self._t = now

    def consume(self, amount: float, *, now: float | None = None) -> bool:
        now = float(now if now is not None else time.monotonic())
        self._refill(now)
        if self.tokens >= amount:
            self.tokens = max(0.0, self.tokens - amount)
            return True
        return False

    def refund(self, amount: float, *, now: float | None = None) -> None:
        now = float(now if now is not None else time.monotonic())
        self._refill(now)
        self.tokens = min(self.capacity, self.tokens + amount)

    @property
    def used(self) -> float:
        return self.capacity - self.tokens


# Lua：原子 INCR 带上限，超限则回滚返回 -1（避免多 worker 竞态超超卖）
_ACQUIRE_LUA = """
local v = redis.call('INCR', KEYS[1])
if v > tonumber(ARGV[1]) then
  redis.call('DECR', KEYS[1])
  return -1
end
return v
"""
_RELEASE_LUA = """
local v = tonumber(redis.call('GET', KEYS[1]) or '0')
if v > 0 then
  return redis.call('DECR', KEYS[1])
end
return 0
"""


class ConcurrencyGuard:
    """AI 助手防过载守护。Redis 可用走分布式；不可用降级内存，保证本地/无库可跑。"""

    def __init__(
        self,
        *,
        global_limit: int | None = None,
        user_max: int | None = None,
        queue_timeout: float | None = None,
        queue_key: str | None = None,
        redis: Any | None = None,
    ) -> None:
        self.global_limit = int(global_limit if global_limit is not None else settings.LLM_GLOBAL_CONCURRENCY)
        self.user_max = int(user_max if user_max is not None else settings.USER_MAX_CONCURRENT)
        self.queue_timeout = float(queue_timeout if queue_timeout is not None else settings.QUEUE_POP_TIMEOUT)
        self.queue_key = queue_key or str(settings.QUEUE_KEY)
        self._redis = redis  # None → 内存后端
        # 内存后端状态
        self._gate_inflight = 0
        self._gate_lock = asyncio.Lock()
        self._gate_waiters: list["asyncio.Future"] = []  # 闸满时的排队请求（release 时唤醒最老者）
        self._user_conc: dict[int, int] = {}
        self._mem_queue: asyncio.Queue = asyncio.Queue()
        self._lock = asyncio.Lock()

    # ──────────────────────────────────────────────
    # 底层：单用户并发槽（第 3 个并发被拒）
    # ──────────────────────────────────────────────
    async def acquire_user_slot(self, user_id: int) -> bool:
        key = f"{settings.CONCURRENT_KEY_PREFIX}:{int(user_id)}"
        try:
            uid = int(user_id)
        except Exception:
            uid = 0
        if self._redis is not None:
            try:
                v = await self._redis.incr(key)
                if v > self.user_max:
                    await self._redis.decr(key)
                    return False
                return True
            except Exception:
                pass  # fallthrough 内存
        async with self._lock:
            cur = self._user_conc.get(uid, 0) + 1
            if cur > self.user_max:
                return False
            self._user_conc[uid] = cur
            return True

    async def release_user_slot(self, user_id: int) -> None:
        key = f"{settings.CONCURRENT_KEY_PREFIX}:{int(user_id)}"
        try:
            uid = int(user_id)
        except Exception:
            uid = 0
        if self._redis is not None:
            try:
                await self._redis.decr(key)
                return
            except Exception:
                pass
        async with self._lock:
            cur = self._user_conc.get(uid, 0) - 1
            if cur <= 0:
                self._user_conc.pop(uid, None)
            else:
                self._user_conc[uid] = cur

    async def user_inflight(self, user_id: int) -> int:
        try:
            uid = int(user_id)
        except Exception:
            uid = 0
        if self._redis is not None:
            try:
                return int(await self._redis.get(f"{settings.CONCURRENT_KEY_PREFIX}:{uid}") or 0)
            except Exception:
                pass
        async with self._lock:
            return self._user_conc.get(uid, 0)

    # ──────────────────────────────────────────────
    # 全局 LLM 并发闸（进程内信号量 + Redis 原子计数）
    # ──────────────────────────────────────────────
    async def _try_gate_locked(self) -> bool:
        """尝试占用一个闸位。进程内计数为准入（权威），Redis 原子计数为分布式观测/兜底。

        Redis 可用时先原子 INCR（带上限，超限回滚）；进程内闸满则回滚 Redis 并返回 False（→排队）。
        """
        if self._redis is not None:
            try:
                v = await self._redis.eval(_ACQUIRE_LUA, 1, settings.GLOBAL_CONCURRENT_KEY, self.global_limit)
                if int(v) < 0:
                    return False
            except Exception:
                pass  # Redis 不可用 → 忽略，仅用进程内闸
        async with self._gate_lock:
            if self._gate_inflight >= self.global_limit:
                if self._redis is not None:
                    try:
                        await self._redis.eval(_RELEASE_LUA, 1, settings.GLOBAL_CONCURRENT_KEY)
                    except Exception:
                        pass
                return False
            self._gate_inflight += 1
            return True

    async def _release_gate_locked(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.eval(_RELEASE_LUA, 1, settings.GLOBAL_CONCURRENT_KEY)
            except Exception:
                pass
        fut_to_set: Any = None
        async with self._gate_lock:
            if self._gate_inflight > 0:
                self._gate_inflight -= 1
            if self._gate_waiters:
                # 有排队请求 → 空出的闸位移交给最老排队者（保持 inflight = 活动持有数不变）
                fut_to_set = self._gate_waiters.pop(0)
                self._gate_inflight += 1
        if fut_to_set is not None:
            # 让位放行：Redis 分布式计数同步补一次 INCR，避免下漂、多 worker 突破上限
            if self._redis is not None:
                try:
                    await self._redis.eval(_ACQUIRE_LUA, 1, settings.GLOBAL_CONCURRENT_KEY, self.global_limit)
                except Exception:
                    pass
            if not fut_to_set.done():
                fut_to_set.set_result(True)

    async def _wait_gate_slot(self, timeout: float) -> bool:
        """闸满排队：注册 waiter，`release` 唤醒最老排队者即获得闸位；超时则移除并返回 False。

        (内存后端的等价 BLPOP：避免「入队后自取队头」导致的自我放行错误）
        """
        loop = asyncio.get_event_loop()
        fut: Any = loop.create_future()
        async with self._gate_lock:
            self._gate_waiters.append(fut)
        try:
            await asyncio.wait_for(fut, timeout)
            return True
        except asyncio.TimeoutError:
            async with self._gate_lock:
                if fut in self._gate_waiters:
                    self._gate_waiters.remove(fut)
            return False

    async def global_inflight(self) -> int:
        if self._redis is not None:
            try:
                return int(await self._redis.get(settings.GLOBAL_CONCURRENT_KEY) or 0)
            except Exception:
                pass
        async with self._gate_lock:
            return self._gate_inflight

    # ──────────────────────────────────────────────
    # 队列削峰（RPUSH + BLPOP(timeout=10)：尾插 + 头弹 = FIFO）
    # ──────────────────────────────────────────────
    async def enqueue(self, payload: Any) -> None:
        if self._redis is not None:
            try:
                await self._redis.rpush(self.queue_key, json.dumps(payload, ensure_ascii=False, default=str))
                return
            except Exception:
                pass
        self._mem_queue.put_nowait(payload)

    async def await_queue(self, timeout: float | None = None, *, as_worker: bool = True) -> dict | None:
        """阻塞取队头：BLPOP（或内存 queue.get）。返回队列任务；>timeout 未取到返回 None（友好提示）。"""
        timeout = float(timeout if timeout is not None else self.queue_timeout)
        if self._redis is not None:
            try:
                raw = await asyncio.wait_for(
                    self._redis.blpop(self.queue_key, timeout=max(1, int(timeout))),
                    timeout=timeout + 1.0,
                )
                if raw is not None:
                    return json.loads(raw[1])
                return None
            except asyncio.TimeoutError:
                return None
            except Exception:
                pass  # fallthrough 内存
        try:
            return await asyncio.wait_for(self._mem_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    # ──────────────────────────────────────────────
    # 高层：acquire/release（会话闸 + 全局闸 + 队列）
    # ──────────────────────────────────────────────
    async def acquire(self, user_id: int) -> dict:
        """请求准入。返回 {ok: True} 或 {ok: False, reason, message}。

        流程：
          1) 单用户并发槽（第 3 个并发被拒）→ reject_user_concurrent
          2) 全局闸非阻塞尝试 → 成功进入
          3) 全局闸满 → 排队等闸位（等价 BLPOP；`release` 唤醒最老排队者）；在时限内获得闸位
             则进入，否则 → reject_queue_timeout（友好提示）
        """
        if not await self.acquire_user_slot(user_id):
            return {
                "ok": False,
                "reason": "user_concurrent_over_limit",
                "message": "您当前的并发会话已达上限（≤2），请先结束其他问答再试。",
            }
        gate_ok = await self._try_gate_locked()
        if gate_ok:
            return {"ok": True, "reason": "direct"}
        # 全局闸满 → 排队等闸位（有其余请求 release 空出闸位则放行）
        admitted = await self._wait_gate_slot(self.queue_timeout)
        if not admitted:
            await self.release_user_slot(user_id)
            return {
                "ok": False,
                "reason": "queue_timeout",
                "message": "当前服务繁忙，排队超时（>10s），请稍后重试。",
            }
        return {"ok": True, "reason": "queued"}

    async def release(self, user_id: int) -> None:
        """释放：先减全局闸位，再减用户并发槽（与 acquire 成对，finally 中调用）。"""
        await self._release_gate_locked()
        await self.release_user_slot(user_id)

    # ──────────────────────────────────────────────
    # ZSET 分片（单分片 ≤ ZSET_SHARD_SIZE，member 哈希分桶）
    # ──────────────────────────────────────────────
    async def zadd_sharded(self, key: str, member: str, score: float) -> None:
        """写 ZSET（自动分片：member 哈希 % 分片数，单分片 ≤ ZSET_SHARD_SIZE，防大 key）。"""
        if self._redis is not None:
            try:
                # 分片数 = ceil(当前总条目 / 每片容量)，保证单片 ≤ 50
                idx = 0
                try:
                    total = 0
                    while True:
                        cur = int(await self._redis.zcard(f"{key}:{idx}"))
                        if cur == 0:
                            break
                        total += cur
                        idx += 1
                    nb = max(1, (total // settings.ZSET_SHARD_SIZE) + (1 if total % settings.ZSET_SHARD_SIZE else 0)) or 1
                except Exception:
                    nb = 1
                h = int(hashlib.md5(member.encode("utf-8")).hexdigest()[:8], 16)
                await self._redis.zadd(f"{key}:{h % nb}", {member: score})
                return
            except Exception:
                pass
        if not hasattr(self, "_mem_buckets"):
            self._mem_buckets: dict[str, dict[str, float]] = {}
        self._mem_buckets.setdefault(key, {})[member] = score

    async def zrange_sharded(self, key: str, start: int = 0, end: int = -1) -> list[tuple[str, float]]:
        """读全部分片（排序后合并，供评测/排行消费；分片防的是单 key 超大）。"""
        out: list[tuple[str, float]] = []
        if self._redis is not None:
            try:
                idx = 0
                while True:
                    if not await self._redis.exists(f"{key}:{idx}"):
                        # 桶不连续时继续探测；连续空桶则终止
                        if not await self._redis.exists(f"{key}:{idx + 1}"):
                            break
                        idx += 1
                        continue
                    rows = await self._redis.zrange(f"{key}:{idx}", start, end, withscores=True)
                    for m, s in rows:
                        out.append((m, float(s)))
                    idx += 1
            except Exception:
                pass
        if hasattr(self, "_mem_buckets") and key in self._mem_buckets:
            for m, s in self._mem_buckets[key].items():
                out.append((m, float(s)))
        out.sort(key=lambda x: -x[1])
        return out

    # ──────────────────────────────────────────────
    # 大 key 治理（SCAN 扫描 >1MB 告警）
    # ──────────────────────────────────────────────
    async def scan_bigkeys(self, threshold: int | None = None) -> list[dict]:
        """扫描全库，返回超过阈值的大 key 清单（strings 按 STRLEN，lists/sets 按长度）。"""
        threshold = int(threshold if threshold is not None else settings.BIGKEY_THRESHOLD_BYTES)
        big: list[dict] = []
        if self._redis is None:
            return big
        try:
            async for key in self._redis.scan_iter(match="*", count=200):
                try:
                    t = await self._redis.type(key)
                    if isinstance(t, bytes):
                        t = t.decode()
                except Exception:
                    continue
                try:
                    if t == "string":
                        size = await self._redis.strlen(key)
                        if size and int(size) > threshold:
                            big.append({"key": key, "type": t, "size_bytes": int(size)})
                    elif t == "list":
                        ln = await self._redis.llen(key)
                        if ln and int(ln) > threshold // 8:
                            big.append({"key": key, "type": t, "entries": int(ln)})
                except Exception:
                    continue
        except Exception as exc:
            logger.warning(f"[guard] bigkey 扫描失败: {type(exc).__name__}: {exc}")
        return big


# 全局单例（默认连接 get_redis 惰性解析；测试可注入 redis/None）
_guard: ConcurrencyGuard | None = None


class TokenBudgetGuard(ConcurrencyGuard):
    """token 级并发预算 + 用户分级队列（task-G1，production-upgrade-plan P5）。

    在 ``ConcurrencyGuard`` 之上叠加两层 token 维度治理，保留既有 ``acquire/release`` 接口：
    - **第一道（token 速率预算）**：按预估 token（system+history+query+max_tokens）做全局速率闸
      （``LLM_TOKEN_RATE_LIMIT_PER_MIN``）与单用户配额（``USER_TOKEN_QUOTA_PER_MIN``）。
      全局速率超限 → **进队列（按优先级）不拒绝**；单用户配额超限 → 友好拒绝（reason=``user_token_quota_exceeded``）。
    - **第二道（请求数并发闸）**：保留原 ``LLM_GLOBAL_CONCURRENCY``，防单请求异常大 token 挤占。
    - **分级队列**：L1~L3 优先级队列（L3 大请求优先于 L1 闲聊），消费者按 ``QUEUE_PRIORITY_ORDER`` 轮询。

    竞品实证：DeepSeek-V3 用户分级队列（arxiv 2412.19437）；通用云 LLM token 速率限制 + 配额 + 预估排队。
    """

    PRIORITY_LEVELS = ("L1", "L2", "L3")

    def __init__(
        self,
        *,
        rate_limit: int | None = None,
        user_quota: int | None = None,
        default_tokens: int | None = None,
        l3_timeout: float | None = None,
        priority_order: list[str] | None = None,
        redis: Any | None = None,
        **kw: Any,
    ) -> None:
        super().__init__(redis=redis, **kw)
        self.rate_limit = int(rate_limit if rate_limit is not None else settings.LLM_TOKEN_RATE_LIMIT_PER_MIN)
        self.user_quota = int(user_quota if user_quota is not None else settings.USER_TOKEN_QUOTA_PER_MIN)
        self.default_tokens = int(default_tokens if default_tokens is not None else settings.ESTIMATE_DEFAULT_TOKENS)
        self.l3_timeout = float(l3_timeout if l3_timeout is not None else settings.QUEUE_POP_TIMEOUT_L3)
        self.priority_order = list(priority_order or settings.QUEUE_PRIORITY_ORDER)
        # 令牌桶平滑（G1-②，默认关闭）：开启后全局速率走令牌桶，消除固定 60s 窗口边界 2× 突发
        self._bucket_enabled = bool(settings.TOKEN_BUCKET_ENABLED) and self.rate_limit > 0
        self._global_bucket: "TokenBucket | None" = None
        if self._bucket_enabled:
            cap = self.rate_limit * float(settings.TOKEN_BUCKET_BURST_RATIO)
            self._global_bucket = TokenBucket(
                refill_per_min=self.rate_limit,
                capacity=cap,
                refill_window_sec=settings.TOKEN_BUCKET_REFILL_WINDOW_SEC,
            )
        # token 计数内存后端（窗口 60s）
        self._global_tokens = 0
        self._global_reset_at = 0.0
        self._user_tokens: dict[int, tuple[int, float]] = {}  # uid -> (used, reset_at)
        self._token_lock = asyncio.Lock()
        # 预留（已准入）token 的 FIFO 登记，release 时按份额回退以释放预算
        self._global_reservations: list[int] = []
        self._user_reservations: dict[int, list[int]] = {}
        # token 速率超限时的有序 waiter（按优先级排序，release 时唤醒最高优先级）
        self._token_waiters: list[dict] = []
        self._token_waiters_lock = asyncio.Lock()
        # L1~L3 分级队列（独立消费原语，供 worker 轮询；BLPOP 按优先级顺序）
        self._prio_items: list[dict] = []
        self._prio_lock = asyncio.Lock()

    # ──────────────────────────────────────────────
    # token 预估（复用 compaction.estimate_tokens 估 query）
    # ──────────────────────────────────────────────
    def estimate_request_tokens(self, request_meta: dict | None) -> int:
        """预估一次请求消耗 token：system + history + query + max_tokens 四段求和。

        request_meta 键：system_tokens / history_tokens / query(str) / query_tokens / max_tokens。
        全部为 0 或缺失 → 兜底 ESTIMATE_DEFAULT_TOKENS。
        """
        if not request_meta:
            logger.warning(
                f"[guard] estimate_request_tokens 无 request_meta，回退默认粗估 "
                f"ESTIMATE_DEFAULT_TOKENS={self.default_tokens}（建议调用方传入 request_meta 以提升精度）"
            )
            return self.default_tokens
        system = int(request_meta.get("system_tokens", 0) or 0)
        history = int(request_meta.get("history_tokens", 0) or 0)
        max_tokens = int(request_meta.get("max_tokens", 0) or 0)
        q = request_meta.get("query")
        if q:
            from app.ai.compaction import estimate_tokens as _et
            query_tokens = max(int(request_meta.get("query_tokens", 0) or 0), _et(str(q)))
        else:
            query_tokens = int(request_meta.get("query_tokens", 0) or 0)
        total = system + history + query_tokens + max_tokens
        return total if total > 0 else self.default_tokens

    # ──────────────────────────────────────────────
    # token 计数（Redis INCRBY+EXPIRE；内存后端 60s 窗口）
    # ──────────────────────────────────────────────
    async def _global_used(self) -> int:
        if self._bucket_enabled and self._global_bucket is not None:
            self._global_bucket._refill(time.monotonic())
            return int(self._global_bucket.used)
        if self._redis is not None:
            try:
                return int(await self._redis.get(settings.TOKEN_RATE_KEY) or 0)
            except Exception:
                pass
        now = time.monotonic()
        if now >= self._global_reset_at:
            self._global_tokens = 0
            self._global_reset_at = now + 60.0
        return self._global_tokens

    async def _add_global(self, delta: int) -> int:
        if self._bucket_enabled and self._global_bucket is not None:
            now = time.monotonic()
            self._global_bucket._refill(now)
            if delta >= 0:
                self._global_bucket.tokens = max(0.0, self._global_bucket.tokens - delta)
            else:
                self._global_bucket.refund(-delta, now=now)
            return int(self._global_bucket.used)
        if self._redis is not None:
            try:
                v = await self._redis.incrby(settings.TOKEN_RATE_KEY, delta)
                await self._redis.expire(settings.TOKEN_RATE_KEY, 60)
                return int(v)
            except Exception:
                pass
        now = time.monotonic()
        if now >= self._global_reset_at:
            self._global_tokens = 0
            self._global_reset_at = now + 60.0
        self._global_tokens += delta
        return self._global_tokens

    async def _user_used(self, uid: int) -> int:
        if self._redis is not None:
            try:
                return int(await self._redis.get(f"{settings.USER_TOKEN_KEY_PREFIX}:{uid}") or 0)
            except Exception:
                pass
        now = time.monotonic()
        rec = self._user_tokens.get(uid)
        if rec is None or now >= rec[1]:
            self._user_tokens[uid] = (0, now + 60.0)
        return self._user_tokens[uid][0]

    async def _add_user(self, uid: int, delta: int) -> int:
        if self._redis is not None:
            try:
                key = f"{settings.USER_TOKEN_KEY_PREFIX}:{uid}"
                v = await self._redis.incrby(key, delta)
                await self._redis.expire(key, 60)
                return int(v)
            except Exception:
                pass
        now = time.monotonic()
        rec = self._user_tokens.get(uid)
        if rec is None or now >= rec[1]:
            self._user_tokens[uid] = (0, now + 60.0)
            rec = self._user_tokens[uid]
        rec = (rec[0] + delta, rec[1])
        self._user_tokens[uid] = rec
        return rec[0]

    def _prio_rank(self, effort: str) -> int:
        """L3=0, L2=1, L1=2（rank 越小越优先）。未知 effort 视为 L1。"""
        try:
            return self.priority_order.index(effort)
        except ValueError:
            return len(self.priority_order)  # 最末

    # ──────────────────────────────────────────────
    # 预留 token 回退（release 时调用，按 FIFO 退一份）
    # ──────────────────────────────────────────────
    async def _refund_one(self, uid: int) -> None:
        amt = self._user_reservations.get(uid)
        if amt:
            v = amt.pop(0)
            if not amt:
                self._user_reservations.pop(uid, None)
            await self._add_user(uid, -v)
        if self._global_reservations:
            g = self._global_reservations.pop(0)
            await self._add_global(-g)

    # ──────────────────────────────────────────────
    # 高层：acquire/release（token 预算第一道 + 请求数闸第二道）
    # ──────────────────────────────────────────────
    async def acquire(self, user_id: int, *, request_meta: dict | None = None, effort: str = "L1") -> dict:
        """请求准入（token 级）。返回 {ok} 或 {ok:False, reason, message}。

        流程（token 预算为第一道，请求数并发闸为第二道）：
          1) 单用户 token 配额：project > 配额 → 拒绝(user_token_quota_exceeded)
          2) 全局 token 速率：project > 上限 → 进队列（按优先级，不拒绝）
          3) 预留 token 后，走请求数并发闸（acquire_user_slot + 全局闸），闸满排队
        """
        estimate = self.estimate_request_tokens(request_meta)
        uid = int(user_id)

        # 1) 单用户 token 配额
        try:
            cur_user = await self._user_used(uid)
        except Exception:
            cur_user = 0
        if cur_user + estimate > self.user_quota:
            return {
                "ok": False,
                "reason": "user_token_quota_exceeded",
                "message": "您本分钟的使用额度已用尽，请稍后再试。",
                "used": cur_user,
                "quota": self.user_quota,
                "estimate": estimate,
            }

        # 2) 全局 token 速率：超限 → 排队（不拒绝）
        try:
            cur_global = await self._global_used()
        except Exception:
            cur_global = 0
        if cur_global + estimate > self.rate_limit:
            return await self._enqueue_token_wait(uid, estimate, effort, request_meta)

        # 预留 token
        await self._add_global(estimate)
        await self._add_user(uid, estimate)
        self._global_reservations.append(estimate)
        self._user_reservations.setdefault(uid, []).append(estimate)

        # 3) 第二道：请求数并发闸（保留原并发闸行为）
        if not await self.acquire_user_slot(uid):
            await self._refund_one(uid)
            return {
                "ok": False,
                "reason": "user_concurrent_over_limit",
                "message": "您当前的并发会话已达上限（≤2），请先结束其他问答再试。",
            }
        gate_ok = await self._try_gate_locked()
        if gate_ok:
            return {"ok": True, "reason": "direct", "estimate": estimate}
        admitted = await self._wait_gate_slot(self.queue_timeout)
        if not admitted:
            await self.release_user_slot(uid)
            await self._refund_one(uid)
            return {
                "ok": False,
                "reason": "queue_timeout",
                "message": "当前服务繁忙，排队超时，请稍后重试。",
            }
        return {"ok": True, "reason": "queued", "estimate": estimate}

    async def release(self, user_id: int) -> None:
        """释放（与 acquire 成对，finally 中调用）：退 token 预留 + 释放请求数闸 + 唤醒优先级 waiter。"""
        uid = int(user_id)
        await self._refund_one(uid)
        await self._release_gate_locked()
        await self.release_user_slot(uid)
        # 释放预算后，按优先级唤醒排队中的 token waiter
        await self._admit_token_waiters()

    async def _enqueue_token_wait(self, uid: int, estimate: int, effort: str, request_meta: dict | None) -> dict:
        """token 速率超限时入队等候（不拒绝）；release 释放预算后由 _admit_token_waiters 唤醒。"""
        loop = asyncio.get_running_loop()
        fut: Any = loop.create_future()
        item = {"uid": uid, "estimate": estimate, "effort": effort, "request_meta": request_meta, "fut": fut}
        async with self._token_waiters_lock:
            self._token_waiters.append(item)
            self._token_waiters.sort(key=lambda x: self._prio_rank(x["effort"]))
        timeout = self.l3_timeout if effort == "L3" else self.queue_timeout
        try:
            await asyncio.wait_for(fut, timeout)
            return {"ok": True, "reason": "queued_token_rate", "estimate": estimate}
        except asyncio.TimeoutError:
            async with self._token_waiters_lock:
                if item in self._token_waiters:
                    self._token_waiters.remove(item)
            return {
                "ok": False,
                "reason": "queue_timeout",
                "message": "当前服务繁忙，token 速率排队超时，请稍后重试。",
            }

    async def _admit_token_waiters(self) -> None:
        """release 后按优先级唤醒排队 waiter：预算允许则准入并预留 token。"""
        async with self._token_waiters_lock:
            if not self._token_waiters:
                return
            cur = await self._global_used()
            admitted: list[dict] = []
            remaining: list[dict] = []
            for item in self._token_waiters:  # 已按优先级排序
                if cur + item["estimate"] <= self.rate_limit:
                    cur += item["estimate"]
                    admitted.append(item)
                else:
                    remaining.append(item)
            self._token_waiters = remaining
        for item in admitted:
            await self._add_global(item["estimate"])
            await self._add_user(item["uid"], item["estimate"])
            self._global_reservations.append(item["estimate"])
            self._user_reservations.setdefault(item["uid"], []).append(item["estimate"])
            if not item["fut"].done():
                item["fut"].set_result(True)

    # ──────────────────────────────────────────────
    # L1~L3 分级队列原语（独立 worker 消费；BLPOP 按优先级顺序）
    # ──────────────────────────────────────────────
    async def enqueue_token(self, payload: Any, priority: str = "L1") -> None:
        """按优先级入队（L1/L2/L3）。Redis 走 `chat:queue:{priority}` list；内存走 _prio_items。"""
        priority = priority if priority in self.PRIORITY_LEVELS else "L1"
        if self._redis is not None:
            try:
                key = f"{settings.QUEUE_KEY}:{priority}"
                await self._redis.rpush(key, json.dumps(payload, ensure_ascii=False, default=str))
                return
            except Exception:
                pass
        async with self._prio_lock:
            self._prio_items.append({"p": priority, "payload": payload})

    async def await_token(self, timeout: float | None = None, *, as_worker: bool = True) -> dict | None:
        """阻塞取队头：按 ``QUEUE_PRIORITY_ORDER``（L3→L2→L1）优先级轮询。超时返回 None。"""
        timeout = float(timeout if timeout is not None else self.queue_timeout)
        order = self.priority_order
        if self._redis is not None:
            try:
                keys = [f"{settings.QUEUE_KEY}:{p}" for p in order]
                raw = await asyncio.wait_for(
                    self._redis.blpop(keys, timeout=max(1, int(timeout))),
                    timeout=timeout + 1.0,
                )
                if raw is not None:
                    return json.loads(raw[1])
                return None
            except asyncio.TimeoutError:
                return None
            except Exception:
                pass
        deadline = time.monotonic() + timeout
        while True:
            async with self._prio_lock:
                if self._prio_items:
                    for p in order:
                        for idx, it in enumerate(self._prio_items):
                            if it["p"] == p:
                                self._prio_items.pop(idx)
                                return it["payload"]
            remain = deadline - time.monotonic()
            if remain <= 0:
                return None
            await asyncio.sleep(min(0.02, remain))


def default_guard() -> ConcurrencyGuard:
    global _guard
    if _guard is None:
        try:
            from app.database import get_redis
            r = get_redis()
            try:
                _guard = TokenBudgetGuard(redis=r)
            except Exception:
                _guard = ConcurrencyGuard(redis=r)
        except Exception:
            try:
                _guard = TokenBudgetGuard(redis=None)
            except Exception:
                _guard = ConcurrencyGuard(redis=None)
    return _guard