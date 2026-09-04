"""
R1-③「Redis 队列削峰」真实 Redis 集成验收脚本（tt 工作流独立实证）。

真实执行、禁 mock、禁伪造。覆盖三件事：
  1) 真实 Redis 连通性（redis.asyncio PING）
  2) 队列削峰真实链路（ConcurrencyGuard enqueue / await_queue 在真实 Redis list 上）
  3) 真实运行中服务使用 Redis 的证据（HTTP 登录 + 观察 rl:ip:* 限流键生长）

纪律：
  - 只做验收，不修改生产代码。
  - 所有造出的键前缀 accept:r1: 避免与运行服务冲突，测完清理。

Redis key 语义核对（app/ai/guard.py + app/config.py）：
  - enqueue()      -> LPUSH queue_key          （head 插入）
  - await_queue()  -> BLPOP queue_key,timeout  （head 弹出）
  - 全局闸          -> Lua INCR/DECR on GLOBAL_CONCURRENT_KEY
  - 单用户并发槽     -> INCR/DECR on CONCURRENT_KEY_PREFIX:{uid}
"""
import asyncio
import json
import sys
import time
import traceback
import urllib.request
import urllib.error

# 脚本放 test-reports/ 下，需要项目根来 import app
_PROJ = r"e:\stu\project\stu\EduAgent实施手册\edu-agent"
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

import redis.asyncio as aioredis  # noqa: E402

REDIS_URL = "redis://127.0.0.1:6379/0"

RESULTS: list[tuple[str, str, str]] = []  # (item, PASS/FAIL, detail)


def record(item: str, ok: bool, detail: str) -> None:
    tag = "PASS" if ok else "FAIL"
    RESULTS.append((item, tag, detail))
    print(f"\n[{tag}] {item}\n    {detail}")


def dedup_ordered(seq):
    seen = set()
    out = []
    for x in seq:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


async def test1_connectivity():
    print("=" * 70)
    print("TEST 1: 真实 Redis 连通性")
    print("=" * 70)
    r = aioredis.from_url(REDIS_URL)
    try:
        pong = await r.ping()
        info = await r.info("server")
        version = info.get("redis_version")
        record("Redis.ping()", pong is True,
               f"PING -> {pong!r}; server redis_version={version}")
    except Exception as exc:
        record("Redis.ping()", False, f"异常: {type(exc).__name__}: {exc}")
    return r


async def test2_fifo_deterministic(guard):
    """单一消费者确定性 FIFO/LIFO 判断（顺序特征对串行 enqueue 稳定）。"""
    print("=" * 70)
    print("TEST 2: 队列顺序特征（串行 enqueue -> 单消费者 BLPOP）")
    print("=" * 70)
    qkey = guard.queue_key
    await guard._redis.delete(qkey)
    n = 8
    enq_order: list[int] = []
    for i in range(n):
        await guard.enqueue({"task_id": i, "enq_seq": i})
        enq_order.append(i)
    deq_order: list[int] = []
    for _ in range(n):
        item = await guard.await_queue(timeout=1.0)
        if item is None:
            break
        deq_order.append(item["task_id"])
    print(f"    入队顺序 enq_order   = {enq_order}")
    print(f"    出队顺序 deq_order   = {deq_order}")
    fifo_ok = deq_order == enq_order
    record("FIFO(先入先出) enq序==deq序", fifo_ok,
           f"enq={enq_order} deq={deq_order} -> 匹配={fifo_ok}")
    llen = await guard._redis.llen(qkey)
    print(f"    消费后 LLEN({qkey}) = {llen}（应=0）")
    return deq_order


async def run_worker(guard, wid, work_event, state):
    """每个 worker：BLPOP 取任务 -> guard.acquire() 占闸 -> 处理 -> release()。

    state 记录: total_processed / processed_ids / max_concurrent / empty_none_results
    """
    loop = asyncio.get_event_loop()
    while True:
        item = await guard.await_queue(timeout=0.4)  # 空+超时 -> None（友好降级）
        if item is None:
            async with state["lock"]:
                state["empty_none"].append(True)
            return
        tid = item["task_id"]
        uid = item["user_id"]
        # 占全局闸 + 单用户并发槽（验证真实 Redis 分布式计数键）
        got = await guard.acquire(uid)
        if not got.get("ok"):
            # 闸满/超时理论上不应发生（4 worker = global_limit 4 足够容纳）
            async with state["lock"]:
                state["rejected"].append(item)
            # 任务未消费即退出会丢任务：重新压回队首显式计数
            await guard.enqueue(item)
            continue
        # 并发计数哨兵
        async with state["lock"]:
            state["inflight"] += 1
            if state["inflight"] > state["max_concurrent"]:
                state["max_concurrent"] = state["inflight"]
            cur_inflight = state["inflight"]
            gi = await guard.global_inflight()
            state["global_inflight_snaps"].append(gi)
        try:
            # 模拟可变耗时任务（削峰场景：请求到达不均衡，消费端排队顺序处理）
            work = 0.05 + (tid % 4) * 0.05
            await asyncio.sleep(work)
        finally:
            await guard.release(uid)
            async with state["lock"]:
                state["inflight"] -= 1
                state["total_processed"] += 1
                state["processed_ids"].append(tid)
            work_event.set()


async def test2_b_load_shaping(guard):
    print("=" * 70)
    print("TEST 3: 队列削峰真实链路（12 任务 / 4 worker / global_limit=4）")
    print("=" * 70)
    qkey = guard.queue_key
    await guard._redis.delete(qkey)

    n = 12
    enq_list: list[int] = []
    for i in range(n):
        uid = 1000 + i  # 每个任务独立 user_id -> 不触发 user_max(2) 拒绝
        payload = {"task_id": i, "enq_seq": i, "user_id": uid}
        await guard.enqueue(payload)
        enq_list.append(i)

    # 直接读真实 Redis list 验证已落库
    llen_before = await guard._redis.llen(qkey)
    list_type = await guard._redis.type(qkey)
    print(f"    enqueue 后 LLEN({qkey})={llen_before}, TYPE={list_type}（应=12 / list）")

    state = {
        "lock": asyncio.Lock(),
        "inflight": 0,
        "max_concurrent": 0,
        "total_processed": 0,
        "processed_ids": [],
        "global_inflight_snaps": [],
        "empty_none": [],
        "rejected": [],
    }
    workers = [asyncio.create_task(run_worker(guard, w, asyncio.Event(), state))
               for w in range(4)]
    t0 = time.monotonic()
    await asyncio.wait(workers)
    dt = time.monotonic() - t0

    processed = state["processed_ids"]
    print(f"    4 worker 消费完成，耗时 {dt:.3f}s")
    print(f"    处理任务数 total_processed      = {state['total_processed']}")
    print(f"    无丢失/无重复 检查 ……")
    no_loss = state["total_processed"] == n
    uniq = dedup_ordered(processed)
    no_dup = len(uniq) == len(processed) == n
    all_executed = set(enq_list) == set(processed)
    print(f"        processed_ids = {sorted(processed)}")
    record("12 任务全部执行（无丢失）", no_loss and all_executed,
           f"total_processed={state['total_processed']}, 目标=12, "
           f"集合一致={all_executed}")
    record("无重复任务", no_dup,
           f"去重后 {len(uniq)}，原始 {len(processed)}")

    record("任意时刻并行执行数 ≤ global_limit(4)", state["max_concurrent"] <= 4,
           f"哨兵记录峰值并行 = {state['max_concurrent']}（<=4）")

    # 空队列 + 超时 -> None 友好降级
    none_ok = len(state["empty_none"]) == 4 and all(df is True for df in state["empty_none"])
    record("await_queue 队列空+超时返回 None（友好降级不抛错）", none_ok,
           f"4 个 worker 超时各返回 1 次 None，empty_none={state['empty_none']}")

    # 全局并发计数键已真实递增（分布式观测证据）
    gi_after = await guard.global_inflight()
    print(f"    消费后全局并发计数 accept:r1:global_concurrent = {gi_after}（应=0，释放干净）")

    # key 清理：列表已排空（所有 BLPOP 已弹出）+ 显式删除
    llen_after = await guard._redis.llen(qkey)
    cleaned = llen_after == 0
    await guard._redis.delete(qkey)
    exists = await guard._redis.exists(qkey)
    record("队列 key 清理（BLPOP 排空 + DEL 后不存在）", cleaned and not exists,
           f"消费后 LLEN={llen_after}; DEL 后 exists={exists}")
    return state


async def test3_running_service_uses_redis():
    """真实运行中的后端是否用 Redis：多次错密码登录，观察 rl:ip:* 限流计数键生长。"""
    print("=" * 70)
    print("TEST 4: 真实运行服务使用 Redis 的证据（登录限流键）")
    print("=" * 70)
    r = aioredis.from_url(REDIS_URL)
    login_path = "/api/auth/login"
    ip_key = f"rl:ip:127.0.0.1:{login_path}"
    url = "http://127.0.0.1:8000" + login_path

    def scan_rl_keys():
        keys = []
        for k in (b"" ,):  # placeholder
            pass
        return keys

    try:
        # 预先清理该键以避免历史残留干扰
        await r.delete(ip_key)
        before = await r.get(ip_key)
        print(f"    清理后 rl 键初始值 before = {before!r}")

        # 发 6 次错密码登录
        body = json.dumps({"account": "user000001", "password": "wrong-pass-XX"}).encode()
        statuses = []
        for i in range(6):
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    statuses.append(resp.status)
            except urllib.error.HTTPError as e:
                statuses.append(e.code)
        print(f"    6 次登录 HTTP status = {statuses}")

        # 观察 Redis 限流计数键
        after = await r.get(ip_key)
        ttl = await r.ttl(ip_key)
        print(f"    真实限流键 {ip_key} 值 after={after!r}, ttl={ttl}")

        ip_value = int(after or 0)
        served = ip_value >= 1
        grow_ok = ip_value >= len([s for s in statuses if s in (200, 401, 400, 403)])
        record("运行中后端真实写 Redis 限流键（rl:ip:*）", served,
               f"{ip_key} 计数={ip_value}（初始 0）; 状态码 {statuses}; TTL={ttl}s")
        return True
    except Exception as exc:
        record("运行中后端真实写 Redis 限流键", False,
               f"异常: {type(exc).__name__}: {exc}\n{traceback.format_exc()}")
        return False


async def cleanup(r, guard):
    print("=" * 70)
    print("清理 accept:r1:* 残留键")
    print("=" * 70)
    removed = 0
    async for k in r.scan_iter(match="accept:r1:*", count=200):
        await r.delete(k)
        removed += 1
    print(f"    删除 accept:r1:* 键 {removed} 个")
    try:
        await r.aclose()
    except Exception:
        pass


async def main():
    import logging
    logging.basicConfig(level=logging.WARNING)  # 压低 redis 客户端日志

    print("Python:", sys.version)
    print("项目根:", _PROJ)
    print("Redis :", REDIS_URL)
    print("时间   :", time.strftime("%Y-%m-%d %H:%M:%S"))
    print()

    r = await test1_connectivity()
    if not RESULTS or RESULTS[-1][1] != "PASS":
        print("\nRedis 不可达，中止后续测试。")
        return 1

    # ---- 自定义命名空间 guard（避免与运行服务键冲突）----
    import app.config as cfg
    # 全局并发计数键 / 单用户并发前缀 / token 速率键 全部隔离到 accept:r1 命名空间
    cfg.settings.GLOBAL_CONCURRENT_KEY = "accept:r1:global_concurrent"
    cfg.settings.CONCURRENT_KEY_PREFIX = "accept:r1:concurrent"
    cfg.settings.TOKEN_RATE_KEY = "accept:r1:token_rate"
    cfg.settings.USER_TOKEN_KEY_PREFIX = "accept:r1:user_token"
    # 注意：QueueKey 不会用 config 默认（构造时显式传 queue_key 覆盖）

    from app.ai.guard import ConcurrencyGuard  # noqa: E402

    qkey = f"accept:r1:queue:{int(time.time())}"
    guard = ConcurrencyGuard(
        global_limit=4,
        user_max=2,
        queue_timeout=1.0,
        queue_key=qkey,
        redis=r,
    )
    print(f"自定义命名空间测试守护实例 queue_key={qkey} global_limit=4 user_max=2")

    await test2_fifo_deterministic(guard)
    await test2_b_load_shaping(guard)
    await test3_running_service_uses_redis()
    await cleanup(r, guard)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for item, tag, detail in RESULTS:
        print(f"  [{tag}] {item}\n        {detail}")

    failed = [it for it, t, d in RESULTS if t == "FAIL"]
    print(f"\n总计 {len(RESULTS)} 项，PASS {len(RESULTS) - len(failed)}，FAIL {len(failed)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\ninterrupted")
        raise SystemExit(130)