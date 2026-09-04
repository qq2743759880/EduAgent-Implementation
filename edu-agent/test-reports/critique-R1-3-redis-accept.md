# R1-③「Redis 队列削峰」真实 Redis 集成验收报告（critique-R1-3-redis-accept）

- 日期：2026-09-05 | 方式：独立实证验收（真实 Redis，禁 mock/禁伪造）
- 验收对象：`app/ai/guard.py` `ConcurrencyGuard.enqueue / await_queue`（队列削峰链路）
- 脚本：`test-reports/_r1_redis_queue_real.py`
- 原始输出：`test-reports/_r1_redis_queue_real.txt`（7 PASS / 1 FAIL）

## 一、资产消费证据（实际读取的文件）

| 文件 | 读取用途 | 提取的关键契约 |
|---|---|---|
| `app/ai/guard.py` | ConcurrencyGuard 真实实现 | `enqueue()`→`redis.lpush(queue_key)`；`await_queue()`→`redis.blpop(queue_key, timeout)`；全局闸 `Lua INCR/DECR on settings.GLOBAL_CONCURRENT_KEY`；单用户槽 `INCR/DECR on settings.CONCURRENT_KEY_PREFIX:{uid}`；降级 `redis=None 走内存` |
| `app/database.py` | 服务级 Redis 单例 | `init_redis()` 用 `RedisConnectionPool.from_url(REDIS_URL)`，`decode_responses=True`，PING 探测连通；`get_redis()` 抛 RuntimeException 时 middleware 降级放行 |
| `app/config.py` | Redis key 命名空间 | `QUEUE_KEY="chat:queue"`、`GLOBAL_CONCURRENT_KEY="ai:llm:concurrent"`、`CONCURRENT_KEY_PREFIX="chat:concurrent"`、`REDIS_URL` 归一 127.0.0.1 |
| `app/middleware/rate_limit.py` | 运行服务 Redis 证据 | 登录限流 `rl:ip:{ip}:{path}` INCR + EXPIRE(61s)；Redis 异常降级放行 |

验收脚本未来直接复用项目根 venv + `import app`，连同一套 redis.asyncio 客户端（与运行服务同驱动、同协议栈）。

## 二、三项验收结论与实测数字

### 1) 真实 Redis 连通性 —— **PASS**
```
redis.asyncio.from_url("redis://127.0.0.1:6379/0").ping() -> True
server redis_version=6.2.24
```

### 2) 队列削峰真实链路 —— 4 PASS / 1 FAIL（详见以下逐项）

构造隔离实例：`ConcurrencyGuard(global_limit=4, user_max=2, queue_timeout=1.0, redis=<真实客户端>)`，
键全部放独立命名空间 `accept:r1:*`（全局并发计数量为 `accept:r1:global_concurrent`，单用户槽前缀 `accept:r1:concurrent`），
不触碰运行中服务的 `chat:queue`/`ai:llm:concurrent` 等键。

| 断言 | 结果 | 实测 |
|---|---|---|
| **FIFO 先入先出**（串行 enqueue→单消费者 BLPOP） | **FAIL** | `enq=[0,1,2,3,4,5,6,7]`，`deq=[7,6,5,4,3,2,1,0]`——**呈后进先出（LIFO）** |
| 12 任务全部执行（无丢失） | PASS | `total_processed=12`，集合一致，LLEN 由 12→0 |
| 无重复任务 | PASS | 去重后 12 / 原始 12 |
| 任意时刻并行 ≤ global_limit(4) | PASS | 哨兵峰值并行 `max_concurrent=4`（≤4） |
| await_queue 空+超时返回 None（友好降级不抛错） | PASS | 4 worker 各超时返回 1 次 `None`（`empty_none=[True×4]`），无异常 |
| 队列 key 清理（BLPOP 排空 + DEL） | PASS | 消费后 `LLEN=0`；`DEL` 后 `exists=0`；测完删除 `accept:r1:*` 共 13 键 |

关键时序/键值证据：
- enqueue 后在真实 Redis 侧 `LLEN(accept:r1:queue:{ts})=12`，`TYPE=list`
- 消费期间全局并发计数键 `accept:r1:global_concurrent` 实际递增（4 worker 并行时），消费完回落 `0`（过度释放由 `_RELEASE_LUA` 的 `>0 才 DECR` 保护，无下漂）

### 3) 运行中服务真实使用 Redis 的证据 —— **PASS**
对 `http://127.0.0.1:8000/api/auth/login` 发 6 次错密码（均 401），随后真实 Redis 观察：
```
rl:ip:127.0.0.1:/api/auth/login  after=6（初始 0）  TTL=58s
```
说明线上后端确实走 Redis 限流（`app/middleware/rate_limit.py` 的 `rl:ip:*` INCR+EXPIRE），未降级内存。

## 三、发现的问题（未修改生产代码）

**P0/FIFO 语义违背。** `ConcurrencyGuard.enqueue` 用 `LPUSH`（头插），`await_queue` 用 `BLPOP`（头弹）——单 list 上 `LPUSH+BLPOP` 组合的结果是**后进先出（LIFO）**，实测 deq 序=enq 序完全反转。
- 影响：突发削峰场景下新到达请求会插在队首被优先消费，**最老请求持续饿死**直至 `queue_timeout` 超时返回友好错误；当入队速率持续高于消费速率时，老请求可被无限延后。`TokenBudgetGuard.enqueue_token` 同菜单 list + `await_token`(BLPOP) 存在同样问题。
- 根因：注释写「LPUSH + BLPOP」即假定 FIFO，但 Redis list 上只有 `LPUSH+BRPOP` 或 `RPUSH+BLPOP` 才是 FIFO。
- 建议修复（一行）：`enqueue` 改 `rpush`（尾插）+ 保留 `BLPOP`（头弹）= FIFO；或保留 `LPUSH` 改 `await_queue` 用 `BRPOP`。

## 四、批判反哺建议（≤3 条，含竞品对标）

1. **修复 LIFO→FIFO**（见上）。对标 Redis 官方「Blocking commands」最佳实践：单 key 队列必须 `RPUSH + BLPOP`（或 `LPUSH + BRPOP`）才获得公平先到先服务；现在实现是 LIFO 堆栈，不符合队列削峰语义。修后补一条顺序断言到契约测试。
2. **BLPOP 单 key 队列 vs Celery/Kafka 适用性判断**：当前「单进程/单网关 + Redis list + BLPOP」方案在单消费者组、≤K 级 QPS、幂等可重试场景下够用（本次实测 12 任务/4 worker 削峰正确）；但 BLPOP 是**挂起式长连接**，扩到多 worker 时存在惊吓唤醒/断连后任务滞留与无 ACK 语义——一旦演进到跨实例调度或需「取出但未处理完即失败重投」，应迁移到 Celery(Broker=Redis) 或 Kafka 的分区+offset 语义（Redis Streams `XREADGROUP` + PEL 可靠投递是 Redis 侧更贴近产线且带消费者组 Ack 的中间态）。当前阶段不建议直接上 Kafka（运维成本）。
3. **降级面可观测**：`enqueue/await_queue/acquire` 多处 `except: pass` 静默降级内存。建议在降级点接入 `app/monitoring/metrics.record_degraded("redis", ...)`（middleware 已有先例），使「Redis 不可用→内存队列」在生产可被监控，避免削峰失效无人察觉。

## 五、纪律核对

- 未修改任何生产代码文件（仅新建测试脚本 + 本报告）。
- 全部键加 `accept:r1:` 前缀，与运行服务隔离；测完清空（删除 13 键）。
- 报告如实：FIFO 一项 FAIL，不假装 PASS；Test 4 observability 为真实 HTTP+RDIS 键值生长实证。

## 六、修复确认（编排者 2026-09-05 跟进，FIFO P0 已闭环）

本报告 Section 三/四 的 **P0 FIFO 违背项已由编排者修复并独立复验通过**：

- **修复**：`app/ai/guard.py` `ConcurrencyGuard.enqueue()`（lpush→**rpush**）与 `TokenBudgetGuard.enqueue_token()`（lpush→**rpush**），消费侧保留 `blpop`（头弹）→ 单 list 即 FIFO；同步更新模块 docstring 与注释（LPUSH+BLPOP → RPUSH+BLPOP）。
- **独立复验**：复跑本脚本 `test-reports/_r1_redis_queue_real.py`（独立进程加载已修后模块，真实 Redis）→ **8 PASS / 0 FAIL**，FIFO 断言 `enq=[0..7] deq=[0..7]`（修复前 `deq=[7..0]`）。12 任务无丢失、并行峰值=4、空队超时返回 None、`rl:ip:*` 登录限流键 0→6 证据仍在。
- 批判反哺建议 ① 已落地（顺序断言进测试）；②③（Celery/监控降级点）作为非阻塞待办登记。