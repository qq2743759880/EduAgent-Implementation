# W-NEXT-R01LIVE-001 完工报告：R01 记忆 worker「启动失败注入」live 实证 + 真覆盖收口

- **日期**：2026-09-20
- **分支**：`feature/opt-waves`
- **任务前 HEAD**：`e9a28876b013b0a10f9313d3ff5290a707a67b34`
- **实现提交**：见 §10（先提交实现，报告在后续提交中登记 hash，避免自引用悖论）
- **执行环境**：VM 192.168.85.101 失联（既知环境态）——本任务全程只用本地组件（本地 MySQL 3306 / Redis 6377 / deepseek-flash LLM API），符合任务书约束
- **红线遵守**：零改动 `app/**`、`config.py`、`.env`；共享 8000 进程零接触（全程存活）；8011 用后即杀

---

## 1. 背景与批判承接核对

R01 记忆 worker 通电验收（ac9886a）时登记②：**「worker 启动失败注入 → health 200 + WARN 不阻断」无专项测试**——当时报告称有测试覆盖，系**口径拉伸**。

本任务把该口径变真覆盖，两件套：

1. **live 实证**：隔离实例范式（:8011），注入 `start_memory_worker` 必抛 + 正常 broker 对照，双侧真实 HTTP/日志/DB 实测；
2. **专项契约测试**：`tests/test_contract_r01live_worker_start_failure.py`（3 条），与 live 侧**同一注入点**（`app.ai.memory.service.start_memory_worker` 模块属性 patch，经 main.py lifespan 函数级延迟导入语义生效）。

**承接核对**：R01 登记② → 本任务 §3 注入态三断言全过 + §6 测试 A1~A5 钉死 → **闭环**。

## 2. 方法（隔离实例范式）

- **故障注入择型**：任务书二选一（env 不可达端口 / monkeypatch）。config 无 `MEMORY_BROKER` 键；worker 启动失败的唯一生产启动点是 main.py lifespan 的 `try: await start_memory_worker() except → WARN`，故选**monkeypatch**（最小侵入：patch 只存在于一次性 runner 进程内，`app/**` 零改动）。
- **共享 8000 零接触的关键**：两个 8011 实例均注入 `MEMORY_QUEUE_KEY` 专用键（`edu:mem_queue:r01live_inject` / `edu:mem_queue:r01live_ctrl`），chat 入队/探针入队**不进共享键 `edu:mem_queue`**，避免与共享 8000 worker 产生 BRPOP 竞争。
- DB/Redis 探针均用**专用标记**（user_id=999001 / content 含 `R01LIVE-CTRL`），用后物理清理（对齐 R-MEM 探针清理纪律）。

## 3. 注入态实测（:8011，start_memory_worker 必抛）

启动命令：`MEMORY_QUEUE_KEY=edu:mem_queue:r01live_inject .venv/Scripts/python.exe scripts/eval/_r01live_inject_uvicorn.py`（日志全文：`test-reports/_r01live_8011_inject.txt`）

### 3.1 ① 启动完成 + /health 200

```
HEALTH_STATUS 200
{"status":"ok","app":"EduAgent","version":"0.3.0"}
```
```
INFO:     Application startup complete.          (_r01live_8011_inject.log:44)
INFO:     Uvicorn running on http://127.0.0.1:8011   (:45)
```

### 3.2 ② worker 启动失败 WARN（不阻断主服务）

```
01:47:05 | WARNING | app.main:lifespan:198 |
  记忆 worker 启动失败（记忆写队列本轮无人消费，降级运行，不影响主服务）:
  RuntimeError: R01LIVE-001 注入故障：start_memory_worker 必然抛错（live 演练）
```
（`_r01live_8011_inject.txt:30`；lifespan 未炸，启动照常完成——「WARN 不阻断」坐实）

### 3.3 ③ chat 一轮正常（记忆旁路降级，主链无感）

登录（真实 HTTP，8011）：`POST /api/auth/login` → HTTP 200 `code=0`，role=student。
chat（`POST /api/chat/stream`，body `{query,session_id:null,stream:true}`，AGENTS.md 教训 3 契约）：

```json
{"frames":{"start":1,"retrieval":1,"token":26,"done":1,"error":0},
 "answer_head":"机器学习是指让计算机从数据中自动发现规律、并据此对未知情况做出预测或判断的方法（基于通用知识）。",
 "done":{"code":0,"message":"ok","data":{"latency_ms":9227,
   "degraded_reason":"Milvus 检索超时(8.0s)；Neo4j 未连接（跳过图谱扩展）"}}}
```
（全文：`test-reports/_r01live_inject_sse.json`；token 事件按 `j.delta` 累加 48 字答案，`error=0`）

**记忆旁路降级证据**（worker 已死，入队侧照常毫秒快返，无人消费）：

```
LLEN inject key = 1        # turn 载荷（kind=turn, v=2）滞留专用键
LLEN shared key = 0        # 共享键 edu:mem_queue 全程未被触碰
payload keys = ['kind','messages','retries','threshold','ts','user_id','v'] kind= turn v= 2
```

## 4. 对照态实测（:8011 正常 broker 配置）

启动命令：`MEMORY_QUEUE_KEY=edu:mem_queue:r01live_ctrl .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8011`（日志全文：`test-reports/_r01live_8011_ctrl.txt`）

```
01:50:30 | INFO | app.ai.memory.service:start_memory_worker:102 | [Memory] 记忆写队列消费者已启动
INFO:     Application startup complete.
/health → 200
```

入队 → 真实消费 → 落 `user_memory_event`（AGENTS.md 教训 11 口径：HEAD 判据 `valid_to IS NULL AND event_type <> 'delete'`）：

```
LPUSH done, LLEN = 0                  # LPUSH 后立即查已是 0：worker BRPOP 消费快于一次 Redis 往返
LLEN after consume = 0
CONSUMED_ROW: {"id":200,"entity_id":273,"event_type":"create","valid_to":null,
  "content":"R01LIVE-CTRL 对照探针记忆 标记X7Q9Z3（探针用后物理清理）",
  "importance":5,"operator":"system","created_at":"2026-09-20 01:50:58"}
HEAD_CRITERIA_OK
```
```
01:51:11 | INFO | app.ai.memory.store:write:85 | [Memory] 写入记忆 user=999001 id=273 type=preference imp=5
```

注入态 vs 对照态差异成立：同一契约（lifespan 通电记忆 worker），坏注入=WARN+无人消费；好配置=INFO+真实落库。

## 5. 清理证明（物理清理纪律）

| 对象 | 清理前 | 动作 | 清理后 |
|---|---|---|---|
| user_memory_event 探针行 | 1（id=200, user_id=999001） | `DELETE WHERE user_id=999001 AND content LIKE '%R01LIVE-CTRL%'` → **deleted=1** | **0** |
| Redis `edu:mem_queue:r01live_inject` | 1（注入态滞留 turn） | DEL → 1 | 不存在 |
| Redis `edu:mem_queue:r01live_inject:degraded` / `:r01live_ctrl(:degraded)` | 0 | DEL → 0/0/0 | 不存在 |
| 共享键 `edu:mem_queue` | 0（全程未被触碰） | —（只读核查） | 0 |
| :8011 进程 | 2 个（注入/对照先后） | TaskStop 杀 | 端口 CLOSED（连通性探测证实） |
| 共享 :8000 | OPEN | —（全程零接触） | **OPEN（存活）** |
| chat 探针的会话落库 | done 帧 `session_id=null,message_id=null` | DB 核查近 1h chat_session/chat_message | **本探针 0 行**（近 1h 存在的 6 行属并行任务 user 100003 的 surfaced1_probe/t15-contract，非本任务） |
| 探针 token 文件 | scripts/eval/_r01live_token.txt | 已删除（不入库不入 git） | 不存在 |

已知不可逆微量痕迹（自批判 P0-3）：探针行 INSERT 推进了 `user_memory_event.id` 自增与 `user_memory_entity_seq` 序列，物理删除不回滚序列（id=200 成为空洞）。

## 6. 专项契约测试（口径拉伸 → 真覆盖）

新增 `tests/test_contract_r01live_worker_start_failure.py`（与 live 同一注入点）：

| 用例 | 钉死契约 | 结果 |
|---|---|---|
| A0 `test_a0_function_level_import_picks_patched_attr` | main.py lifespan 的**函数级延迟导入**在 patch 后取到假件（注入点有效性本身成为被钉契约） | PASS |
| A1~A5 `test_a1_a5_worker_start_failure_lifespan_survives_health_200` | 真实 app.main lifespan（TestClient 上下文全链）：启动不炸（A1）+ /health 200 status=ok（A2）+ WARN「记忆 worker 启动失败」落日志（A3）+ `_worker_started` 保持 False 无半启动态（A4）+ 关闭阶段干净（A5）；假件恰好被调 1 次 | PASS |
| A6 `test_a6_stop_after_failed_start_is_noop` | 启动失败后 `stop_memory_worker` 是 no-op，不触碰队列（失败不留烂摊子） | PASS |

```
3 passed, 1 warning in 51.64s
```

## 7. 回归（R-MEM/R01 相关套件全绿）

```
tests/test_contract_rmem1_sanitize_window.py   ┐
tests/test_contract_task_r01.py                │
tests/test_contract_task25.py                  ├─ 73 passed, 1 warning in 56.90s
tests/test_memory_queue_lifecycle.py           │   （含本任务新增 3 条）
tests/test_contract_r01live_worker_start_failure.py ┘
tests/test_contract_task_m1.py                 ── 9 passed, 1 warning in 3.79s（user_memory_event 事件溯源契约）
```

## 8. P0 自批判（≥3）

1. **「旁路降级停写」的语义边界未全测**：注入态 Redis 可用时，chat 记忆入队照常 LPUSH（本轮实测专用键 LLEN=1 滞留）——降级实为「停消费」而非「停入队」。若 Redis 也不可达，入队退进程内 `_memq`（`MemoryWriteQueue._memq` 为**无界** asyncio.Queue），worker 长死 + Redis 长抖动下存在无界堆积的潜在内存风险（P2 级，登记不修：修需改 app/**，越出本任务红线；建议后续 wave 给 `_memq` 加 maxlen 评估）。
2. **A1~A5 是半 live 测试，依赖本地 MySQL/Redis 可达**：lifespan 存储初始化段在 `DEBUG=false` 且存储失败时会 `raise`（与 DEBUG=true 的降级语义不同），故「不阻断」契约的完整命题是「worker 注入失败」单变量——存储全不可达矩阵未覆盖，测试 docstring 已标注口径。若未来 CI 无本地存储，该测试需 skip 标记（当前本仓测试环境成立）。
3. **对照态在共享库留微量不可逆痕迹**：探针行 INSERT 推进自增 id/实体序列，物理删除不回滚序列（§5）。属探针纪律已知代价；若后续要求零痕迹，需改用可清空的影子表（涉 schema，超出本任务红线）。
4. **WARN 断言与 main.py 文案耦合**：A3 用文本「记忆 worker 启动失败」匹配，文案重构会破坏测试。结构化断言（如 JSON 日志字段）需改 app 侧日志形态（红线禁碰），接受耦合并在测试 docstring 标注。
5. **live 侧与测试侧非完全同构**：live 用真实 uvicorn 进程 + runner 进程内 patch；测试用 TestClient 同进程。二者注入点/断言一致，但 uvicorn 信号路径（SIGTERM 优雅退出）仅 live 侧真实走过（TaskStop 强杀），未做 SIGTERM 精确演练——shutdown 契约已由 W-NEXT-LIFECYCLE-001 套件覆盖，此处不重复。

## 9. 资产消费证据

| 具名资产 | 消费方式 |
|---|---|
| `app/ai/memory/queue.py` | 通读——确认 `_push`/`_fetch_one`/`start_consumer`/`stop_consumer` 语义、`MEMORY_QUEUE_KEY` 单一事实源（→专用键防竞争设计依据） |
| `app/main.py` lifespan start/stop_memory_worker 段 | 通读——确认**函数级延迟导入**（:195）→ monkeypatch 注入点设计依据；WARN 文案与位置（:198）→ A3 断言依据 |
| `app/ai/memory/service.py` | 通读——`_worker_started` 门（stop no-op 路径）→ A6 测试依据 |
| `tests/test_contract_rmem1_sanitize_window.py` | 通读——离线夹具范式、HEAD 判据口径（教训 11）、`pump_once`/`_drain` 惯例 → 新测试 docstring 与断言风格对齐 |
| AGENTS.md | 教训 3（chat SSE 契约 `query`/`j.delta`）、教训 8（curl 实测优先）、教训 11（先查 user_memory_event + HEAD 判据）、隔离实例先例（r23-c01-8011-*）→ 全程遵循 |
| 契约权威 `schemas.py`/响应壳 | login/chat 断言按 `{code:0,data}` 壳解包 |

## 10. 提交登记

- **实现提交**：`0ca6f6f61195b0d2d8a570857621760939d7068d`（test(r01live)，含契约测试+注入 runner+双侧证据文件；本报告在此之后的独立提交中登记）
- 本报告随后独立提交登记（避免自引用 hash 悖论）。
- **并行提示（F610 教训沿用）**：任务执行期间 tip 曾由 `e9a2887` 前移至 `6bd79ad`（并行 agent 提交）；本任务全部 `git add` 均为具名路径（无 `-A`），无 index 污染。
- lock：`scripts/eval/r01live.lock` 已于 commit 前删除。
