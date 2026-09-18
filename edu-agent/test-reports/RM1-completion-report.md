# R-M1 完成报告（MongoDB 学习事件流 M-1 + 聚合端点 M-3）

- 任务：R-M1 接手执行（前任两次中断，WIP e6fac1d / 9716f60 / 27421f4 + 外部 TEST-BASE WIP 43e0480）
- 收口 commit：**`1d48fe9`**（fix(core-breaker)/R-M1 熔断共享状态修复，本报告唯一新增代码 commit）
  - R-M1 主体实现由三历任 WIP commit 承载：`e6fac1d`（analytics 6 文件+挂点+契约草案+测试+对账脚本+main.py 通电块+error_codes/config）、`9716f60`（quiz 挂点 None 护栏+payload 键名修正）、`27421f4`（febe 桶登记）
- 日期：2026-09-18　分支：feature/opt-waves　lock：rm1.lock 已删（仅本地文件，从未入库）
- 计划源：.ai-hub/plans/neo4j-mongo-activation-plan.md §M-1/M-3；契约：contracts/reshape-r-analytics.json（draft:true，待用户签字冻结）

## 0. 结论

R-M1 全部验收硬门独立实证通过：① Mongo 断连主链无感（12/12 HTTP 200 + 熔断自愈 + 零丢失）；② 对账一致率 100%（净窗口 3/3）；③ 批量 1k 吞吐 364 events/s 零丢弃；④ 权限矩阵 8/8 全对码。**过程中发现并修复跨域 P0 一枚**（app/core/breaker.py 共享状态失效，见 §3）。

## 1. 历任半成品处置（逐文件判定）

### e6fac1d（14 文件，全部复用，0 重写）

| 文件 | 判定 | 审查结论 |
|---|---|---|
| app/domains/analytics/event_stream.py | 复用 | 旁路纪律完整：emit sync put_nowait 毫秒级快返+永不向主链抛错；worker 单消费者+熔断+重入队+超限丢弃计数；ensure_indexes 幂等含 TTL collMod 热更；启停钩子可测性（reset_event_worker_for_test）齐备 |
| app/domains/analytics/service.py | 复用 | range 白名单+40030；聚合双 pipeline（by_type+overall）；mongo 异常→50301 脱敏（logger.exception 入日志不进响应，detail 恒 None）符合 reshape-b sanitization 条款 |
| app/domains/analytics/router.py | 复用 | summary 三段鉴权（缺省=本人/student 查他人 40320/admin+manager 任意）；stream-stats require_role 范式 |
| app/domains/analytics/schemas.py | 复用 | 裸 DTO 对齐 progress 域口径；range_days le=90 与 RANGE_PRESETS 同源 |
| app/domains/analytics/__init__.py | 复用 | 域声明 |
| app/domains/learning/service.py 挂点 | 复用 | emit 在 MySQL transaction 块**之后**（主链事务零改动），payload 实参全部安全 |
| app/progress/service.py 挂点 | 复用 | tick-batch 请求=1 事件，payload.rows_inserted 供对账 |
| app/interactive/quiz/service.py 挂点 | 复用 | e6fac1d 版有 int(None) 隐患→已由 9716f60 修复（见下） |
| app/main.py worker 通电块 | 复用 | 启动 try/WARN 不阻断 + 关停先于存储关闭 + 残留队列计数；lifespan 同 commit 混入的 kg_router 行属 R-N1 范畴（其 commit 31d623d 已收口，未触碰） |
| app/common/error_codes.py | 复用 | 40030/40320 注册（同 commit 的 KG 段属 R-N1，未触碰） |
| app/config.py | 复用 | MONGO_EVENT_* 6 开关（ENABLED/QUEUE_MAXSIZE/MAX_RETRY/TTL_DAYS/BREAKER_FAILURES/BREAKER_OPEN_S） |
| contracts/reshape-r-analytics.json | 复用 | 与实现逐项核对一致（端点/错误码/计数器键/索引/TTL 时区注记） |
| scripts/eval/mevent_reconcile.py | 复用 | 只读纪律（mongo 仅 find/aggregate、MySQL 仅 SELECT）；三事件类型对账口径含代理列高估注记 |
| tests/test_rm1_analytics.py | 复用后被 TEST-BASE 重写→审查后采纳（见 §1.1） |

### 9716f60（1 文件）——复用
quiz 挂点 `int(q.question_id)` → None 护栏 + `session_id_mongo`→`quiz_answer_session_id` 键名修正（主链帧求值例外，emit 内部 try/except 管不到 payload 实参——前任已识别正确）。

### 27421f4（1 文件）——复用
febe_contract_check.py NEXTJS_UNASSIGNED 桶登记 2 个 analytics 端点（test_febe_contract_check.py 回归绿）。

### 43e0480（TEST-BASE 外部代理改 tests/test_rm1_analytics.py）——审查后采纳
重写实质：① mongo 连通探针 skipif 隔离；② 集成用例切独立库 edu_agent_rm1_test（不污染生产库）；③ 修两处前任 skip 根因（_OkColl.insert_one / _FakeAgg.to_list 必须 async 才能 await）；④ 补 P0 回归护栏用例 test_emit_accepts_none_fields_payload；⑤ 匿名 401 用例改 DEBUG=False monkeypatch（锁生产门禁而非依赖 dev 实例 DEBUG=true 现状）。逐用例核对与实现语义一致，17/17 绿（本机实测两轮）。

## 2. 独立实证（真实 HTTP + 真实 DB，非 mock 叙事）

环境：隔离 uvicorn 实例 :8011（DEBUG=false、独立 JWT_SECRET、MONGO_URI 指向本机 TCP 代理 → 真实 mongo 192.168.85.101:27017），不触碰共享 8000；故障注入 = 杀/启代理进程（连接拒绝级真故障）。

### 2.1 Mongo 断连主链无感 + 熔断自愈（GWT③）
- 断连期主链写 12/12 全 HTTP 200：`POST /api/progress/video/tick-batch` ×6、`POST /api/interactive/quiz/submit` ×6（数据：play_session 525478 / user_id=1）
- 修复后时序：5 连败 → **OPEN**（`[Breaker] mongo_learning_event 熔断: 5/7 errors`，Redis hash consecutive_errors 1→5 可见）→ OPEN 期事件回队保全（breaker_open_requeue=48，**dropped_over_retry=0**）→ open_duration(8s) 到点半开探针（两轮失败重开）→ mongo 恢复 → 探针成功 → **恢复关闭**（23:21:58）→ 积压补写 **written=10/10、队列清零、mongo 集合计数 12/12 全对账（零丢失）**
- 50301：断连期 `GET /api/analytics/learning-events/summary` → HTTP 503 `{code:"50301",message:"依赖服务暂不可用，请稍后重试",data:null}`（原始 ServerSelectionTimeoutError 仅入日志）
- 降级 WARN 证据：修复前 episode 产生 10 条 `[LearningEvent] 写 mongo 失败超限丢弃（主链无感）` WARN（该 episode 损失见 §3.1 定量）

### 2.2 权限矩阵实测（8/8，均带真实 JWT）
| # | 场景 | 实测 |
|---|---|---|
| 1 | student 查本人（缺省 user_id） | 200 `{user_id:1,total:12,by_type:[...]}` |
| 2 | student 查他人 user_id=42 | **403 code=40320** |
| 3 | admin 查任意 user_id=1 | 200 |
| 4 | manager 查任意 user_id=1 | 200 |
| 5 | 非法 range=3h | **400 code=40030** |
| 6 | stream-stats × student | **403 code=40300**（require_role） |
| 7 | stream-stats × manager | 200 |
| 8 | 匿名 summary（DEBUG=false 生产门禁） | **401 code=40101**（AGENTS.md 教训6 场景复验） |

### 2.3 对账一致率（scripts/eval/mevent_reconcile.py 真跑，只读）
- **净窗口（修复后全周期 since=23:16）：一致率 3/3 = 100%**——video_heartbeat mongo_rows=5 vs mysql=5 OK；quiz_submit 5/5 OK；session_complete 0/0 OK
- 全窗口（含修复前 episode）：1/3（vh 6/11、quiz 6/11）——差值恰为 P0 修复前丢失的 5 tick+5 quiz（§3.1），差值逐条定量归因，非管线语义缺陷
- 佐证：聚合端点 total/first_ts/last_ts 与 mongo 集合真实计数一致（total=12）

### 2.4 批量 1k 吞吐（GWT①，独立测试库 edu_agent_rm1_test，跑后 drop）
1000 事件：emit 0.003 ms/条（主链侧开销可忽略）；单 worker 排空 2.75s ≈ **364 events/s**；dropped=0，mongo 计数=1000。

### 2.5 pytest 回归
- `tests/test_rm1_analytics.py` 17/17 绿（独立跑 ×2）
- 定向受影响面（breaker 消费方 test_breaker_db_resilience/test_core/test_redis_outage_fastfail/test_contract_task_r02tail/test_task33_mcp_desc_review/test_contract_task_s1 + RM1 + febe）：**144 passed**
- 全量批测（143 文件，两轮）：1350 passed / 45 failed / 68 skipped——**45 失败与本任务无关的既有批序干扰**：剔除实验（stash 1d48fe9 重跑）失败集合完全一致（45F/1350P）；6 个失败文件（含 rm1）隔离重跑 65 passed 1 skipped 全绿；失败形态=共享 Redis 登录限流（/api/auth/login 60s/10）被批测自身+并行 agent 实况流量打满（中间件用例单独复现、滑窗后自愈）

## 3. P0 自批判（≥3 条）

1. **【已修复·跨域】app/core/breaker.py 共享熔断状态全链路失效（P0，存量缺陷非本任务引入）**：init_redis 共享客户端 decode_responses=True（str 键值），_sync_from_redis 按 bytes 键取值全部 miss → 每次同步（>100ms 间隔的每次 call）把 state/consecutive_errors 静默清零 → consecutive_failures 永不触发、OPEN 态同步即蒸发、跨进程共享熔断死设。故障注入实测：30+ 连败 state 恒 closed、事件白白超限丢弃（10 条，含 kill 进程时在队 4 条，合计损失 mongo 缺 10 条）；单测为什么没拦住=用例进程未 init_redis → _get_redis()=None 纯本地模式。修复=str/bytes 双兼容读取（1d48fe9），探针验证 1→5→OPEN→half_open→CLOSED。**波及面**：全部 CircuitBreaker 消费方（MCP per-server、db_resilience 等）跨进程语义同此修复获益；**⚠️ 共享 8000 实例仍跑旧码，需编排者择窗重启**。
2. **【接受·已登记】进程内队列零跨进程/跨重启持久性**：旁路队列在进程崩溃时在队事件丢失（修复前 episode 实测）。M-1 定位=观测旁路、MySQL 仍是事务事实源，可接受；但对账一致率仅对「干净进程生命周期」成立，若未来把 learning_event 当事实源消费，必须先落持久 spool（契约草案 degradation 段已登记降级语义）。
3. **【薄弱点·已注记】session_complete 对账强度不足**：脚本对账代理列 updated_at 会被 watched_seconds 更新共享 bump（高估风险，脚本注释已登记），且本轮净窗口 complete 0/0（无完成动作），该类型一致率属" vacuous pass"；T-ME 盲测应补真实 complete 动作对账。
4. **【接受·已登记】TTL 时区偏移**：ts 为服务器本地 naive，mongo TTL 按 UTC 解释 → 实际保留期 ≈90d+8h；对 90d 级语义无害，契约草案 ts_tz_note 已登记，冻结时可选统一 UTC。
5. **【环境风险】共享 8000 dev 实例 DEBUG=true**：匿名请求经虚拟管理员后门可直读 analytics 端点（本任务已实测 DEBUG=false 路径 401 正确并有用例锁定）；生产部署 DEBUG=False 红线（AGENTS.md 教训6）是唯一闸门，febe/前端接入前建议 8000 切 DEBUG=false 演练。

## 4. 批判承接核对

critique-tracker-v1.md（C-16..C-24 逐条核对）与 .opencode/plans/critique-backlog-tracker.md：**无任何落点 R-M1/app/domains/analytics 的承接项**。本任务无需承接修复；新增批判仅 §3 自批判第 1 条（已当场闭环）。

## 5. 资产消费证据

- `.ai-hub/plans/neo4j-mongo-activation-plan.md` §M-1（doc schema/写入点三挂点/旁路异步 WARN 不阻断/TTL）、§M-3（summary 端点）逐条落地；验收 GWT 三项全部实测（§2.1/2.3/2.4）；派单表 R-M1 行（文件域 app/domains/analytics/、锁 rm1）遵守
- AGENTS.md：教训1（未动 8000/next，无重启必要）、教训2（无 Playwright，全部 requests/curl/pymysql/pymongo 独立实证）、教训6（DEBUG=false 门禁实测）、教训8（真实契约以实测为准——stream-stats 计数器键以 stats_snapshot 实测输出登记进契约草案）、教训11（先查事件表口径——对账脚本以 mongo 事件流+MySQL 双侧实测）
- 既有范式消费：R01 记忆 worker 降级范式（app/ai/memory/queue.py）、core/breaker 三态熔断、50301 脱敏契约（T19-3/reshape-b）、require_role 工厂、febe 桶登记（27421f4 沿用既有 NEXTJS_UNASSIGNED 结构）
- 测试资产：test_contract_50301_dependency 鉴权桩范式（TEST-BASE 重写沿用，审查确认）

## 6. 移交备注

- 共享 8000 实例需重启加载 1d48fe9（旧码熔断共享状态失效，主链无风险）
- contracts/reshape-r-analytics.json 仍为 draft:true，按流程待用户签字冻结
- T-ME 事件流盲测（吞吐/对账/降级）解锁，可复用本报告 §2 全套 rig（temp 目录代理脚本+隔离实例参数）
- 全量批测的 45 项批序干扰（共享 Redis 限流打满）为独立环境债，建议 TEST-BASE 批测模式改为限流旁路或分片进程
