# task39 真 Redis 项补验收 — 完工报告

- 任务：EduAgent task39 性能压测 / P95 治理 —— **真 Redis 项补验收**（限流 / 热度缓存 / 分布式锁 / 不可用降级）

- 执行 agent：task39 真 Redis 补验收执行 agent（独立实证）

- 完成日期：2026-09-04

- 状态：**真 Redis 项 4/4 已独立实证闭环；`core.lock.RedisLock`** **登记「无生产控制器挂载」；发现 2 个治理项（见 §7）**

> 纪律声明：Redis 已真实可用（`127.0.0.1:6379`，容器 edu-redis-standalone）。下列所有指标为对后端 **127.0.0.1:8000 真实 HTTP** + **真实 Redis key 查询**的独立实测，不 mock、不伪造命中。另起 8001 实例（死 Redis 端口）做降级复验（组件 4）。

***

## 1. 资产消费证据

按 tt 工作流 §5.2「资产消费证据」硬约束，如实列出消费资产与实际用途（读了什么 → 自检发现并修掉什么 / 无发现）。

| 资产          | 路径                                                                | 用途 / 实际调用                                                                                                           | 消费证据                                                          |
| ----------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| ponytail    | `C:\Users\Administrator\.agents\skills\ponytail\SKILL.md`         | 最小实证：复用 redis.asyncio + requests + 既有 `get_redis()`/共享 `RedisLock` 类，不新建抽象、不新增大规模压测；逐组件判定「写不写产品代码」→ 结论「实证+登记为准、不强改」 | 实证脚本仅 1 个文件；未新增任何产品代码；发现「死代码」只登记不动（§7-①）                      |
| tt 方法论      | `C:\Users\Administrator\.agents\skills\tt\SKILL.md` **§5.2**      | 验收必须独立实证（真实 HTTP + Redis key）；完工报告回传机制；完工前自查三视角                                                                     | 限流/缓存/锁/降级全部真实 HTTP + 真实 key 取证；报告含资产锚点 + 内核词 `assetConsumed` |
| review 批判内核 | `C:\Users\Administrator\.agents\skills\tt\vendor\review\SKILL.md` | 完工前按 critique 三视角（交互态/边界/错误反馈）过自己的实证设计                                                                              | 见下「逐批判记录」                                                     |
| harden      | `C:\Users\Administrator\.agents\skills\harden\SKILL.md`           | 组件 4「Redis 不可用降级复验」：验证限流/缓存/锁在 Redis 连接失败时按既有设计降级（放行/直通DB），不 500                                                    | 真实起 8001 死 Redis 实例复验（§5），全链路不 500                            |

**自检发现并修掉的问题**：

1. 首版实证脚本 `Redis.from_url(..., decoding_responses=True)` 参数名错误（应 `decode_responses`）→ 崩，已修后重跑出数。
2. 首版按任务给定的 `app/common/rate_limit.py` 的 key 前缀 `rate_limit:*` 扫描 → 扫描结果为空。**追查发现挂载的限流中间件并非该文件**，而是 `app/middleware/rate_limit.py`（key=`rl:ip:*`/`rl:uid:*`）——修正扫描前缀后拿到真实 key 证据。`app/common/rate_limit.py` 实为**死代码**（无任何 import，见 §7-①）。这正是「真实契约为准」纪律的价值：task 指向的文件 ≠ 运行时实际挂载文件。
3. 单测式 `ModuleNotFoundError: No module named 'app'`（脚本位于 test-reports/，sys.path 不含 edu-agent）→ 用 PYTHONPATH/`sys.path.insert` 修正后锁实证通过。

**assetConsumed 锚点**：`ponytail`（最小实证/登记为准）+ `tt §5.2`（真实 HTTP+key 独立实证/回传路径）+ `review`（批判三视角）+ `harden`（降级复验）。

### agent × skill × workflow 矩阵

| agent 角色             | skill / 资产          | workflow                  | 本任务落点                                                |
| -------------------- | ------------------- | ------------------------- | ---------------------------------------------------- |
| 补验收执行 agent（本 agent） | ponytail（最小实证器）     | 真实 HTTP + 真实 Redis key 观察 | `test-reports/task39_redis_real_check.py`（1 个文件，可重跑） |
| 补验收执行 agent          | tt §5.2（独立实证/回传纪律）  | 只传报告路径；验收独立实证             | 本报告 + 4 组件逐条真实证据                                     |
| 补验收执行 agent          | review skill（批判三视角） | 完工前自查                     | 死代码发现/无调用方登记/降级边界（§7）                                |
| 补验收执行 agent          | harden（降级复验）        | 死 Redis 实例复验              | 8001 实例实测限流放行 + 缓存直通 DB（§5）                          |

> 本任务单 agent 独立实证（N=1 模式，tt §5.0）；不派独立子 agent 做二次开发；验收可复跑 `test-reports/task39_redis_real_check.py`。

### 逐批判记录（完工前自查）

1. **批判（交互态/「看似命中实则空断言」）**：不能只报 429 就断言限流走 Redis —— 429 也可能来自内存计数器。→ 补强：不仅看 HTTP 429，还直查 Redis 中 `rl:ip:*` key 的存在 + 计数 ≥11 + TTL>0，三证齐才判定「真实 Redis 限流」。对缓存，不仅报「二次响应一致」，还直查 `course:series:detail:{id}` key 存在 + 值==HTTP data + TTL。对锁，不仅报 acquire/release，还直查 SETNX key 的 token 值 + TTL + 互斥（二次 acquire=False）。
2. **批判（边界/是否覆盖真实负载与真实挂载）**：任务给定 `app/common/rate_limit.py`，但运行时实际挂载哪份？→ 追查 main.py 中间件导入 + Redis 实测 key 命名，证实挂载是 `app/middleware/rate_limit.py`（IP+uid 双维、key=`rl:`），`common/` 份未注册。边界覆盖：缓存取真实在售 `series_id`（2628），非造数。
3. **批判（错误处理/降级是否 500）**：harden 视角 —— Redis 断连时若中间件抛异常会 500。→ 起 8001 死 Redis 实例，实测登录 12 次全 200（放行）且 series 详情 200（直通DB），无 500，且启动日志记录 `redis: 'error'` 但服务不阻断。降级路径实证闭环。
4. **批判（是否有现实安全隐患/再发现）**：运行中的 8000 实例实测**信任 X-Forwarded-For**（制造唯一假 IP 后得到 `rl:ip:<假IP>:<path>` key），而磁盘上的 `app/middleware/rate_limit.py` 是 S3 裁定改为**忽略 XFF**（CWE-348 防暴破稀释）。→ 判定当前运行 uvicorn 进程**早于 S3 修复**（stale 进程），源已修，需重启后端接收 S3 修复（登记见 §7-②）。

***

## 2. 逐组件实测证据

测试基础设施：

- 后端 A：`127.0.0.1:8000`（uvicorn，真实 Redis 可用），`store_status.redis='ok'`。

- 后端 B（仅组件 4）：`127.0.0.1:8001`，`REDIS_URL=redis://127.0.0.1:6999/0`（死端口），`store_status.redis='error'`，服务不阻断。

- Redis 观察：独立客户端直连 `redis://127.0.0.1:6379/0`，真实读 key / 只做测试清理。

### ① 限流（`app/middleware/rate_limit.py`，真实命中）✅

端点 `/api/auth/login`（规则 60s/10 次），连续 12 次 POST（唯一假 IP 隔离窗口，真实登录凭据）：

```
12 次请求 HTTP 状态序列: [200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 429, 429]
X-RateLimit-Limit: 10 | 最后一次 X-RateLimit-Remaining: 0
429 body code: 42900
Redis key / 计数 / TTL: {'rl:ip:203.0.113.55:/api/auth/login': ('12', 56)}
```

**证据**：前 10 次放行（200）→ 第 11 次起 429（code 42900）达成阈值；Redis 中 `rl:ip:<ip>:/api/auth/login` key 计数=12、TTL=56s（窗口 60+1），即 INCR 真实发生且落在 Redis —— **真 Redis 滑动窗口计数 + 超阈值 429**，非降级放行（若假装 429 而在 Redis 不到 key 即造假，此处实际拿到了 key+计数+TTL 三证）。

> 注：`app/middleware/rate_limit.py` 实现为 IP + user\_id 双维度 INCR（key `rl:ip:`/`rl:uid:`），与任务给定的 `app/common/rate_limit.py`（key `rate_limit:...:{window_start}`）命名不同 —— 后者未挂载（死代码，§7-①）。

### ② 热度缓存（`app/core/cache.py::get_or_load`，真实命中）✅

真实在售 `series_id=2628`，清缓存后 2 次 GET `/api/series/2628`：

```
series id: 2628
首请求 status/latency(ms): 200  44.5ms      ← miss，写缓存
二请求 status/latency(ms): 200  26.0ms      ← 命中
请求后 Redis 中全部 course:* key: ['course:series:detail:2628']
目标 key 存在: 1 | TTL: 296（≈300±10% 抖动）
Redis 缓存值与 HTTP 响应 data 一致: True
两次 HTTP 响应完全一致: True
```

**证据**：首请求 miss 后在 Redis 写出 `course:series:detail:2628`（TTL 296 落在 270\~330 抖动区间），缓存值 == 首请求 HTTP `data`；第二请求命中同一 key，两次响应逐字节一致（JSON 排序相等）。**真 Redis 缓存命中 + 写后一致**。TTL 抖动（296≠300）恰为三防「雪崩」参数的真实体现。

> `course_admin` 写操作侧 `invalidate(...)` 精确 DEL（`course:series:detail/cohort:detail/cohort:seats`）链路确认挂在真实 Redis 上（代码路径，未在本项破坏性触发）。

### ③ 分布式锁（`app/core/lock.py::RedisLock`，真 Redis 机制验证 ✅；**无生产控制器挂载 ⚠️ 登记**）

`core.lock.RedisLock` 在真实 Redis 上直接验证（复用共享类，走内部 `get_redis()`）：

```
初始化 Redis 连接池: redis://127.0.0.1:6379/0 | Redis 连接成功
[Lock] 获取锁: lock:_tt39_verify
acquire1: True | key exists: True | value(token): 444c47cc9d4d4ad48aaccdd3d6eadc19 | TTL: 10
acquire2 (should be False, already held): False
after release key exists: False
```

**证据（机制）**：`acquire` 用 SETNX+EX 创建 `lock:<name>`（唯一 token、TTL=10 防死锁）；同一锁第二次 `acquire` 返回 False（**互斥成立**）；`release` 走 Lua 原子「校验 token→DEL」，之后 key 消失。整套 **SETNX + 超时 + 互斥 + Lua 释放**在真实 Redis 上成立。

**无挂载登记（如实）**：`grep` 全库，`core.lock.RedisLock` / `core.lock` **无任何业务调用方**（下单/退款/幂等走的是 `IdempotencyMiddleware`/`middleware/idempotency.py` 的 Redis 幂等，`cache.get_or_load` 内也用另一套 SETNX 互斥锁）。即：锁**组件本身真 Redis 可用**，但**无控制器触发**——按边界要求如实登记，不假装「某下单场景触发了锁」。若要真业务触发，需挂到下单/退款入口后复测（登记待办，§7）。

### ④ Redis 不可用降级复验（harden）✅

8001 实例启动即 `init_redis` 失败（`Error 22 connecting to 127.0.0.1:6999`），`store_status.redis='error'` 但**服务照常启动**（DEBUG 模式非阻断）：

```
8001 12x login statuses: [200,200,200,200,200,200,200,200,200,200,200,200]  → 限流放行，无 429 无 500
8001 series/2628: status 200 | code 0 | data keys [id, institution_id, delivery_mode, ...] → 缓存直通 DB，无 500
```

**证据**：Redis 断连时，限流 `get_redis()` 抛 RuntimeError → 中间件降级「放行」（12 次登录全 200，未被限也**不 500**）；缓存 `get_or_load` 命中 `RuntimeError/熔断` → **毫秒级直通 DB**（系列详情返回真实数据，不 500）。即既有降级设计（放行/穿透 DB）在真实死 Redis 上成立，安全兜底不失灵。

***

## 3. 无挂载 / 未命中相关登记（如实，非假装命中）

| 组件           | 结论           | 说明                                                                          |
| ------------ | ------------ | --------------------------------------------------------------------------- |
| 分布式锁业务触发     | **无生产控制器挂载** | `core.lock.RedisLock` 无私网调用方；真 Redis 机制已验证，业务场景未触发                          |
| 列表读缓存        | **列表读未走缓存**  | `list_series`（`/api/series`）仍每请求直查 MySQL（沿用既有 task39 结论）；详情/班次详情走缓存；本项不强加缓存 |
| 通用列表 / 管理读端点 | 未逐点普查挂载      | 仅按任务聚焦 4 类 Redis 驱动组件取证，不盲目扩大断言                                             |

***

## 4. 结论

**真 Redis 项 4/4 已独立实证闭环**：

- ✅ 限流 —— 真实 HTTP 触发 429 + `rl:ip:*` key 计数/TTL 三证。

- ✅ 热度缓存 —— 首写 `course:series:detail:2628` + 二次命中 + 响应一致 + TTL 抖动。

- ✅ 分布式锁 —— 真 Redis SETNX 建 key + 互斥 + Lua 释放（机制闭环）；业务触发登记「无调用方」。

- ✅ 不可用降级 —— 死 Redis 实例下不 500、限流放行、缓存直通 DB。

task39 tracker「真 Redis / 缓存命中 / 削峰 / 跨实例」项中，**「真 Redis + 缓存命中」已闭环**；「分布式锁业务触发」等待挂载后业务级补测（见待办）；此前「Redis 不可达 gap」**解除**。

## 5. 产物

- 完工报告：`test-reports/task39-redis-real-completion-report.md`（本文件）

- 实证脚本（可重跑）：`test-reports/task39_redis_real_check.py`（组件①②③；④降级需手动 8001 死 Redis 实例）

- 未新增/改动任何产品代码；未 commit。

## 6. 批判承接核对

- 承接既有 task39 报告 §7「待 Redis 就绪后单独验收」—— 本报告即该承接项的落地实证（缓存命中/降级/锁均已真 Redis 验证）。

- 无重叠的既有 C-xx backlog 待办；本报告新增登记项见 §7。

## 7. 新增治理项（登记，供后续任务；不因此改代码）

- **① 死代码：`app/common/rate_limit.py`** —— 与 `app/middleware/rate_limit.py` 功能重叠但**从未被 import**（行为/key 命名也不同，含 `rate_limit:*:{window_start}` 滑动窗口）。task 指向它是个坑。建议后续清理（删除或统一），避免「读了死文件当契约」的重复踩坑。

- **② 运行中 8000 uvicorn 进程为 stale** —— 实测其限流**信任 X-Forwarded-For**（`rl:ip:<伪IP>:`），而磁盘 `app/middleware/rate_limit.py` 的 S3 裁定已改**忽略 XFF**（CWE-348 防 client 换假 IP 稀释限流）。**建议重启后端**以接收 S3 安全修复（AGENTS.md 教训：后端改中间件后须重启 dev server，否则跑旧逻辑）。

- **③ 决策（本轮更新）：`core.lock.RedisLock`** **不挂真实写入口** —— 全库 grep 确认 `RedisLock` 无任何业务调用方；下单/退款/领券/售后全部走 `IdempotencyMiddleware`（中间件幂等，Redis key `idem:resp:*`）+ DB 事务 + 服务层幂等三层纵深，**已足够防重复提交，不缺乏分布式锁**。Redis 分布式锁在此架构里属「机制可行但无必要」；硬挂需改下单/退款 service 逻辑并新增「抢锁失败→提示」错误分支，属真实行为变更 + 回归风险（叠加本轮发现的写后读一致性缺陷，动态更容易翻车）。**按边界纪律：如实登记不挂载、不硬改**。写入口真 Redis 触发证据由本轮 ④ 提供（幂等中间件即为挂在写入口、真 Redis 背书的防重防超发守卫），见 §8。

***

## 8. 本轮补验：全新 Redis 实例复证（① ② ③）+ 写入口真命中（④）+ §7-③ 落地

> 背景：Redis 于本工作流重新连通为**全新实例**（容器 `edu-redis-standalone`，`0.0.0.0:6379→6379`，`edu-redis-standalone-data` 命名卷持久化，启动时仅 `breaker:redis`/`probe:sep04` 两个键）。后端 A（`127.0.0.1:8000`，PID 24312）已与该 Redis 建立真实连接。以下为本轮在**当前全新 Redis** 上重跑复证（前 3 项）+ 本轮补充的写入口/锁触发证据。证据全部为**真实 HTTP + 真实 Redis key/value/TTL 查询**。可重跑脚本：`test-reports/task39_redis_real_check.py`（①②③）+ 本轮新增 `_tt39_write_idem_final.py` / `_tt39_idem_hit_verify.py`。

### 8.1 → 复证 ① 限流（当前新 Redis，真实命中）✅

`app/middleware/rate_limit.py`（`/api/auth/login` 60s/10 次），唯一假 IP 隔离窗口，连续 12 次真实登录：

```
12 次请求 HTTP 状态序列: [200,200,200,200,200,200,200,200,200,200,429,429]
X-RateLimit-Limit: 10 | 最后一次 X-RateLimit-Remaining: 0
429 body code: 42900
Redis 限流 key / 计数 / TTL: {'rl:ip:203.0.113.55:/api/auth/login': ('12', 56)}
```

**三证齐**：HTTP 429（code 42900）+ Redis `rl:ip:<ip>:/api/auth/login` **key 存在** + **计数=12（≥11 阈值边界）** + **TTL=56s（>0）**。INCR 真实落在新 Redis 上，非降级放行。

### 8.2 → 复证 ② 热度缓存（当前新 Redis，真实命中）✅

真实在售 `series_id=2628`，清缓存后 2 次 GET：

```
series id: 2628
首请求 status/latency(ms): 200  49.9ms   ← miss，写缓存
二请求 status/latency(ms): 200  18.9ms   ← 命中（更快）
请求后 Redis 全部 course:* key: ['course:series:detail:2628']
目标 key 存在: 1 | TTL: 311（≈300±10% 抖动）
Redis 缓存值 == HTTP 响应 data: True
两次 HTTP 响应完全一致: True
```

**四证齐**：第二次命中 + Redis `course:series:detail:2628` **key 存在** + 缓存 JSON 值 **== 首请求 HTTP** **`data`** + **TTL=311（抖动区间 270\~330）**。

### 8.3 → 复证 ③ 分布式锁（当前新 Redis，机制真验证）✅

复用共享类 `core.lock.RedisLock`（走内部真实 `get_redis()`）：

```
[Lock] 获取锁: lock:_tt39_verify
acquire 返回: True | Redis key 存在: True | value(唯一 token): e774b3671deb47d496bde9c816c87913
release 后 Redis key 存在: False
```

**真 Redis SETNX 建 key（唯一 token）+ Lua 释放删 key** 成立。**无生产控制器挂载** 结论维持（§7-③ 已更新为「决策：不挂载」）。

### 8.4 → ④ 真实写入口 Redis 命中（本轮补充，优先级高）✅

**写入口**：`POST /api/trade/coupon/receive`（领券=真实写，`IdempotencyMiddleware` 幂等前缀内，Redis key `idem:resp:{key}` ex 86400 缓存 <400 响应）。为**隔离最早误落的两笔 pending 订单**调查，一并验证。

**证据 A —— 写入口真实产生 Redis 幂等 key**：

```
[④] 领券 首次 status: 500 | 二次(同key) status: 200   （首次命中途经缺陷，见 §8-5）
[④] Redis 幂等 key 存在: True | key: idem:resp:5e112f04985e4808a88069f29e8a1f54 | TTL: 86400
[④] Redis 幂等缓存体: {"body":{"code":0,"message":"ok","data":{"coupon_id":51005, ...}}}
[④] DB coupon_receive_record(coupon=68,user=1) 行数: 1  (id 51005, receive_status 'unused')
```

**证据 B —— 幂等中间件缓存命中（同 key 不触达 service/DB）**：复用已落库的同 key 再发一次相同请求：

```
[缓存命中] 第3次同 key 请求 status: 200
[缓存命中] HTTP 响应 == Redis 缓存体: True
[缓存命中] coupon.receive_count 68: 736→736 | receive_record(coupon68,user1): 1→1   （未重新领/未新增）
```

**判定（④）：真实写入口 Redis 命中 == 命中**。领券这一真写入口经 `IdempotencyMiddleware` 在 Redis 上落 `idem:resp:*` key（TTL 86400），同 key 重复请求由 Redis 缓存直接返回、**未重复写库** —— 即写入口确实由 Redis 背书防重（防重复领券/超发）。**注意**：这是 Redis 幂等中间件命中的写入口证据；`RedisLock` 本身仍无人挂载（机制已证，挂载决策见 §7-③）。

### 8.5 → §7-③ / 新发现的治理项（登记，不改产品代码）

- **自检新发现缺陷（清理中保留证据）——「写后读一致性」**：本轮实测下单/领券首个写请求出现「**DB 已落库、接口却报失败**」：

  - 下单 `POST /api/trade/order`（cohort 7883 on\_sale、有余位）两次均返回 `40420「订单创建失败」`，但 DB `order` 表**已真实落两笔 pending 单**（80383/80384，institution 6、2999.00）。根因路径：`create_order` 事务成功 commit 后，`_order_write.get_order()`（走 `fetch_one` 读池）**读不到刚提交的行 →** **`fresh is None`** **→ 抛 40420**（错误地向客户端报失败，但写已生效）。

  - 领券 `POST /api/trade/coupon/receive` 首个写请求返回 `500（data:'coupon_id'）`：`receive_coupon` 事务写入 receive\_record 后 `get_my_coupon()` 读不到 → 进入「极端兜底」分支用 `get_coupon()` 返回的 dict（列 `id` 非 `coupon_id`）拼 `_coupon_from_receive` → `KeyError('coupon_id')`。

  - 取消 `POST /api/trade/order/{no}/cancel`：同一单一次 `404「订单不存在」`、下一次 `200 cancelled`（实测后一次确已写库）——受前者影响，符合「写后读存在瞬时不可见」。

  - **影响面**：写一次后立即读的接口可能瞬时误报失败；**不影响本次 Redis 验收**（② 缓存命中/① 限流/③ 锁/④ 幂等键均不受影响）。疑似与 `init_mysql_ro` 独立只读池/连接快照相关，**未在本任务根因定位/修复**（涉 DB 配置风险，超验收范围）。作为治理项登记，建议独立 issue 跟进（写后读一致性 / read-your-write）。

- **残留清理**：本轮产生的两笔 pending 订单（80383/80384）已置 cancelled、cohort 7883 座位 2→0 恢复；领券记录 51005 已删、coupon 68 receive\_count 736→735 恢复；测试 `idem:resp:*` / `lock:*` / `rl:ip:*` 键已清理。Redis 现仅剩既有 `breaker:redis`/`probe:sep04`。

- **进程仍 stale**：本轮限流复证继续用假 XFF 制造唯一 IP 成功，再次印证运行中 8000 进程仍信任 X-Forwarded-For（磁盘已改 S3 忽略 XFF）。**建议重启后端**接收 S3 修复（同 §7-②）。

### 8.6 本轮结论

- ① 限流 / ② 热度缓存 / ③ 分布式锁在**当前全新 Redis** 上 3/3 复证通过（真实 HTTP + 真实 key/value/TTL）。

- ④ 真实写入口（领券）Redis 幂等键**命中**，并实证同 key 缓存命中不重复写库 —— 写路径 Redis 背书成立。

- §7-③ 决策：**`RedisLock`** **不挂载**（写入口已由幂等中间件 + DB 幂等纵深覆盖，硬挂有回归风险且超验收范围），登记为机制可用的独立件。

- 本轮未改任何产品代码；仅更新本报告；不 commit。

