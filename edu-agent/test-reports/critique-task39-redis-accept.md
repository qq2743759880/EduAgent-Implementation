# task39 三项目实体验收：限流 / 缓存 / 分布式锁（独立实证）

- 验收方式：真实 Redis（`redis://127.0.0.1:6379/0`）+ 真实 HTTP（`http://127.0.0.1:8000`），无 mock、无伪造。
- 验收人：独立验收子代理（tt 工作流实证）
- 日期：2026-09-05
- 可重跑脚本：`test-reports/_t39_redis_real.py`｜完整原始输出：`test-reports/_t39_redis_real.txt`
- 纪律：只验收不改生产代码；测试专用键一律 `accept:t39:` 前缀，测完已清理。

---

## 资产消费证据（实际读取的源文件）

| 模块 | 文件 | 读区 | 关键发现 |
|---|---|---|---|
| 限流 | `app/middleware/rate_limit.py` | 全文件 | IP+user 双维度滑动窗口；`rl:ip:{ip}:{path}` / `rl:uid:{uid}:{path}`；`/api/auth/login→(60,10)`；超限 429 `{code:"42900"}` + `Retry-After` |
| 限流注册 | `app/main.py` | L206–258 | `RateLimitMiddleware` 第 3 层（`app.middleware.rate_limit` 生效版本） |
| 限流配置 | `app/config.py` | L261–287 | `TOKEN_RATE_KEY=ai:llm:token_rate` 等（guard 侧 token 限流）；本报告 HTTP 限流走中间件 |
| 缓存 | `app/core/cache.py` | 全文件 | `get_or_load`：读→miss→`SETNX mutex` 重建→写(含 `__NULL__` 空哨兵)→TTL 抖动 ±10%→Lua 释放互斥锁 |
| 缓存调用 | `app/domains/course/service.py` + `router.py` | L118–192 / L58–83 | `course:series:detail:{id}` TTL 300、`course:cohort:detail:{id}` TTL 300、`course:cohort:seats:{id}` TTL 10 |
| 锁 | `app/core/lock.py` | 全文件 | `RedisLock`：`SET key uuid NX EX timeout` + Lua 校验 token 删除；锁名 `lock:{name}` |
| Redis 连接 | `app/database.py` | L410–455 | `get_redis()` 惰性单例；db0，`decode_responses=True` |

---

## 一、限流真实性 —— PASS

**证据链（真实 HTTP ×15 → 真实 Redis 计数同步增长）：**

| 请求序 | HTTP | 语义 | Redis `rl:ip:127.0.0.1:/api/auth/login` | TTL |
|---|---|---|---|---|
| req#1 | 401 | 放行（账号/密码错误 code=40111） | 1 | 61s |
| req#2–9 | 401 | 放行 | 2…9 | 60→57s |
| req#10 | 401 | 放行（`X-Remain=0`） | 10 | 57s |
| **req#11** | **429** | **限流触发** | **11** | **57s** |
| req#12–15 | 429 | 限流 | 12…15 | 56s |

- **限流阈值**：`/api/auth/login` 规则 `(60s, 10)` → 第 **10** 个请求仍放行、第 **11** 个起拒绝。
- **触发错误码**：`HTTP 429` + body `{"code":"42900","message":"请求过于频繁，请 60 秒后再试","data":null}` + `Retry-After` 头。
- **真实 Redis 计数（分布式而非内存）证明**：15 次请求计数 1→15 单调 `INCR`，TTL ≈ 56–61s（窗口 60s）。删 key 后再次请求即时恢复 401 且计数归 1 → 计数源为真实 Redis，非内存/降级放行。
- 命中端=`app.middleware.rate_limit.py`（main.py 注册生效版本），IP 维度 key 由载入 JWT 为空、未登录，`uid` 维度未计。

## 二、缓存真实性 —— PASS

**2A 直调生产 `get_or_load`（真实 Redis）：**

| 指标 | miss | hit |
|---|---|---|
| 耗时 | 322.6 ms | **5.3 ms** |
| loader执行次数 | 1 | 1（命中不重建） |
| Redis key | `accept:t39:cache:probe:1` | 同左 |
| TTL | — | **310 s**（配置 300 ±10% 抖动，实测 302–322） |

**2B 真实 HTTP `GET /api/series/1`（后端进程写缓存，本脚本读同 db0 命中）：**

- 首次：HTTP 200，29.0 ms → 后端写入 `course:series:detail:1`，TTL=322 s。
- 二次：HTTP 200，14.1 ms，`cache命中(key仍在)=True`。
- key 样例：`course:series:detail:{series_id}`（TTL 300）、`accept:t39:cache:probe:1`。
- 说明：2B 系列详情数据小、DB 快，HTTP miss/hit 差仅 ~15ms（较难单从 HTTP 看出量级）；2A 直调以 322→5ms 的 loader 重建成本清晰证明"命中不重建"，二者互为印证。

## 三、分布式锁真实性 —— PASS

**证据链（真实 Redis、生产 `RedisLock`）：**

- **3A 互斥**：30 并发 `acquire` 仅 **1** 成功；全释放后 `redis.get(key)=None` → 证明 `SETNX` 原子互斥。
- **3B 最大同时持有**：30 worker × 5 轮抢占，`max同时持有=1` → 互斥成立。
- **3C 生命周期**：`acquire=True`，持锁期 `redis.get('lock:accept:t39:test:lock')=0b363612…`（=持有者 token，`SET EX 10`），另一实例 `acquire=False`；Lua 释放后 key=None；再 `acquire=True` 重获成功。

关键 key：`lock:accept:t39:test:lock`（TTL=-ex10）。

---

## 每项结论

- **限流：PASS**（阈值 60s/10、第11个拒绝、42900、Redis 计数 1–15 + TTL、删 key 恢复）
- **缓存：PASS**（miss 322.6ms→hit 5.3ms、loader 仅 miss 执行、key+TTL≈300±10%、HTTP 命中验证）
- **分布式锁：PASS**（SETNX 互斥、max 同时持有=1、持锁值=token、Lua 释放、失效重获）

---

## 遗留 / 未验证（UNAVAILABLE，如实登记）

1. **未逐一覆盖全部限流端点**：仅实测 `login`（代表端点），`register(5/min)`、`refresh(30)`、`chat(20)`、`trade/order(10)`、`payment(30)` 等规则未压测（规则同名，见 `rate_limit.py`，未破坏性攻防验证其他账套）。
2. **锁测试为单进程单 event loop 内并发**：验证的是 Redis `SETNX` 原子互斥语义，未起多 uvicorn worker 做跨进程真分布式压测；分布式健壮性由 Redis 原子性等价成立。
3. **限流 uid 维度未单独验证**：`rl:uid:` 需登录态 Bearer，未专门构造（IP 维度已充分证明走 Redis）。

---

## 批判反哺（竞品对标：SETNX vs Redlock vs Redisson watch dog）

> 背景：本项目 `RedisLock` 采用 **SET `lock:{name}` `NX` `EX` + 随机 token + Lua 校验释放**——这是"单实例 Redis 分布式锁"的标准最小实现，适合当前单 Redis 主实例部署。

- **R1｜无自动续期（watch dog），长任务会提前丢锁**：`RedisLock(timeout=10)` 固定窗口，业务 executor 处理 >10s 时锁过期自动释放，另一节点可抢锁 → 并发写撕裂。Redisson 用 **watch dog 后台自动续期**（默认 lockWatchdogTimeout=30s，过半自动续）解决"锁过期但业务未完"临界窗。建议演示/面试讲解时补充对比，避免在长事务上加锁。参考：Redisson 分布式锁文档（access 2026-09-05）— https://github.com/redisson/redisson/wiki/8.3.-distributed-locks-and-synchronizers
- **R2｜单节点单点 vs Redlock 多节点仲裁**：当前实现依赖单 Redis 主署；主节点故障期间会失去互斥（fencing 竞态，Martin Kleppmann 已论证"简单 SETNX 锁在故障/分区下不可靠"）。若未来拆多节点高可用，需评估 Redlock（antirez 多节点仲裁）或其批判结论。参考：Kleppmann《How to do distributed locking》2016-02-08 — https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html ；Redis 官方 Distributed locks 模式（access 2026-09-05）— https://redis.io/docs/latest/develop/use/patterns/distributed-locks/
- **R3｜可选加固点（轻微）**：`app/core/cache.py` 的 `get_or_load` 互斥重建锁值固定字符串 `"1"`（非随机 token）。极慢重建超 `mutex_timeout` 后被他人抢锁时，前请求 finally 的 Lua 以相同 `"1"` 校验仍可能误删他人锁（概率低）。锁实现 `lock.py` 已用随机 token 规避，建议缓存重建锁类同改造。此项为本验收发现的代码级可见缺口，不改动、仅登记。

---

## 附件

- 可重跑脚本：`e:\stu\project\stu\EduAgent实施手册\edu-agent\test-reports\_t39_redis_real.py`
- 原始输出：`e:\stu\project\stu\EduAgent实施手册\edu-agent\test-reports\_t39_redis_real.txt`