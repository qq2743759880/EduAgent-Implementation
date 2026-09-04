# task26 完工报告：AI 助手 compaction + R4 context editing + artifact 分流 + Redis 防过载

> 后端｜阶段 P4.5｜类型 agent+infra｜执行 Trae 手动调度（dev-standard.mjs 8 阶段）
> 前置：task24（LangGraph 图重构）、task25（三层记忆，已验收）｜后置：task29（联调评估）
> 交付物：`app/ai/compaction.py` + `app/ai/artifact.py` + `app/ai/guard.py` + graph/runner/config 接线 + 契约测试（见 §6）

---

## 1. 背景与核心决策

task25 已验收 → 本任务按 tech-source-audit §二/§四 落地 **AI 助手上下文管理 + 分布式防过载**：

- **compaction**：对齐 Anthropic《Effective Context Engineering》，采用「轻量优先」分级——`context_edit`（精确删已完成工具对，保留前缀缓存）→ 仍超才 `compaction`（重量，summary + 最近 K=6 轮原文）。
- **artifact 分流**：单条工具输出 >1500 token → 原文进 Redis artifact（TTL 1h），流内仅 1 行结论（tool result clearing / R4）。
- **Redis 防过载**：全局 LLM 并发闸 8 + 单用户并发 ≤2 + 队列削峰（等待放行 10s 超时友好提示）+ ZSET 分片（防大 key）+ bigkey 扫描 + checkpoint TTL 7 天。

**关键设计（本轮修正）**：

1. **闸位等待不「自取队头」**：内存后端初版 `acquire()` 采用「入队后 BLPOP」会自消费刚入队任务 → 排队请求自我放行（错误）。改用**进程内权威计数 + Redis 原子计数双闸**，闸满时请求注册 waiter `Future`，`release` 让位唤醒最老 waiter；超时移除并返回友好提示。契约测试即排队攻防。
2. **进程内计数为准入（权威）**，Redis Lua(INCR 带上限/DECR) 为分布式观测与兜底，`release` 让位放行时**同步补一次 INCR**，避免 Redis 计数下漂、多 worker 突破上限（review R3 修正）。
3. **compact_node 真正暴露精简流**：压缩后写入 `state.compaction["messages"]`（summary + 最近 K 轮），供下游消费而非仅观测快照（review R3 修正）。
4. **`_is_tool_call` 严格化**：仅当 assistant/ai 消息 content 为含 `tool`/`tool_call` 键的 JSON 才判为工具调用，避免把普通回答+紧随工具结果误删为「已完成工具对」（review R3 修正）。

**环境说明**：本机 Redis 6379 **不可达**（连接拒绝）。与 task25/Milvus 同理，guard/artifact 全链路**契约内降级内存后端**，内存语义经契约测试实证；Redis 分布式路径（LUA/BLPOP/分片/bigkey）代码就绪，真库 bigkey 测试按契约 skip，见 §5 说明。

---

## 2. 验收标准逐条核验（GWT 精简版，全文见任务文档）

### ① 消息流 >6000 token → plan_node 前压缩至 ≤6000，summary 保留结构化语义，最近 6 轮原文保留
**判定：✅ PASS**

- `compact_messages`（compaction.py）：`before_tokens > 6000` 才触发；先 `context_edit`（轻量），仍超才 compaction。间环收缩 keep（逐轮把最老保留原文并入摘要）保证 `after_tokens ≤ threshold`；兜底收紧 summary。
- summary 为**结构化 JSON** 4 稳定键：`profile_updates / pending_tasks / decisions / facts`（`build_structured_summary` + 规则默认抽取，可注入 LLM summarizer）。
- 最近 K=6 轮**原文保留**，新消息流 = summary + K 轮原文。
- 契约测试 `test_compaction_applied_over_threshold_and_under_budget`（>6000→after=3702≤6000）、`test_keeps_recent_rounds_original`（末 6 轮 "AAA_15/AAA_20" 在 kept、首轮 "AAA_1 问题#1" 不在）、`test_summary_structured_semantics`（4 键 + profile_updates 非空）、`test_no_compaction_below_threshold`。
- graph 接线：`route → compact → plan`（非 chitchat）、`reflect → compact → plan`（迭代增长压缩，≤MAX_REFLECT）。smoke：20 轮大流 `compact_node` → applied=True、after=3702≤6000、4 键、精简流 12 条。

### ② 单条工具输出 >1500 token → 立即蒸馏：原文进 artifact(TTL 1h)，流内仅 1 行结论
**判定：✅ PASS**

- `distill_tool_output`（artifact.py）：`estimate_tokens` 超 `COMPACTION_TOOL_OUTPUT_THRESHOLD(1500)` → 原文写 `ArtifactShuntStore`（Redis TTL 3600=1h，本地 JSON/内存兜底），返回 `{distilled:True, conclusion(1行+artifact:/1行), artifact_ref}`；不超阈值原样返回。
- `one_line_conclusion` 将多级结构捏平成**单行**（`\n`→空格），`distilled` 分支流内仅 1 行。
- runner 接线（tool result clearing）：子代理完整工具输出整体进 `full_tool_outputs`（外层 artifact），`messages` 内 txt 截断 + 超阈值蒸馏为 1 行（`artifact:` 标注），LLM 上下文体量受控。
- 契约测试：`test_large_output_distilled_to_artifact`（>1500→distilled、artifact_ref、原文 raw.data len=50 可读回、conclusion 单行含 "artifact"）、`test_small_output_not_distilled`、`test_shunt_batch_distilled_count`、`test_large_tool_output_ttl_1h`（settings.ARTIFACT_TTL==3600）。

### ③ LLM 并发闸满(8) + 第 9 个 → 排队；>10s 返回友好提示；单用户并发第 3 个被拒(≤2)
**判定：✅ PASS**

- `ConcurrencyGuard`：`acquire_user_slot`（`chat:concurrent:{uid}` INCR，第 3 个被拒）→ `_try_gate_locked`（进程内权威计数 + Redis Lua 上限）→ 闸满则 `_wait_gate_slot(queue_timeout=10s)` 排队，`release` 让位唤醒最老 waiter；超时 `release_user_slot` 并返回 `queue_timeout` 友好提示「当前服务繁忙，排队超时（>10s），请稍后重试。」
- ZSET 分片（`zadd_sharded` 按 member 哈希分桶 `{key}:{idx}`）+ `scan_bigkeys`（>1MB 告警）就绪。
- 契约测试：`test_user_3rd_concurrent_rejected`、`test_acquire_entry_user_over_limit_reason`、`test_global_gate_full_queue_timeout_friendly`（第 3 个排队超时→友好提示；release 后新请求 direct）、`test_release_pairs_keeps_gate_consistent`、`test_queue_primitive_pops_within_timeout`、`test_zset_sharded_many_entries`（60 条取回全量）、`test_scan_bigkeys_graceful_no_redis`。

**环境承载说明**：③全部经**内存后端**契约测试实证（guard 统一 `redis=None→内存`）；真 Redis 分布式闸/BLPOP/ZSET 大 key 本机不可达，按契约 skip（§5）。

---

## 3. 独立子代理红线审查（R1-R5）

独立子代理（general_purpose_task）实跑 `pytest tests/test_contract_task26.py -q`（19 passed,1 skipped）并逐一读取 5 模块 + test，判定：

| 项 | 判定 | 核心证据 |
|----|------|------|
| R1 数据一致 | ✅ PASS | summary 4 键结构化保留、最近 6 轮原文保留、artifact 原文 JSON 可读回不截断（raw.data len=50） |
| R2 安全 | ✅ PASS | 守卫 fail-open 不阻塞本地；fan_out 用 `int(state["user_id"])` 缺失即报错（不越权兜底默认 1）；子代理工具先白名单后调用；artifact 不落敏感日志 |
| R3 正确性 | ✅ PASS | 初审指出并已修复 3 处：①`_is_tool_call` 过度匹配普通 assistant → 严格化（仅含 tool/tool_call 键 JSON）；②Redis 让位未补 INCR → 已补；③compact_node 仅快照未真实落地 → 已写入 `state.compaction["messages"]` 压缩流 |
| R4 健壮性 | ✅ PASS | 无 Redis 时各操作 try/except 优雅降级内存；acquire/release 在 run_agent finally 成对不泄漏 |
| R5 契约冻结 | ✅ PASS | 配置 8 项与测试/实现一致（6000/3000/6/1500/3600/604800/8/2/10.0）；GWT①②③ 测试真实输入非 mock |

**采纳的修复（本报告修正清单，对应 review R3）**：
- `app/ai/compaction.py`: `_is_tool_call` 由「role 一刀切」改为「role∈{assistant,ai} ∧ content 为含 tool/tool_call 键 JSON」。
- `app/ai/guard.py`: `_release_gate_locked` 让位放行时对 Redis 分布式计数补 INCR，防多 worker 计数下漂；`_try_gate_locked` 进程内计数为准入权威、Redis 为观测/兜底。
- `app/ai/graph.py`: `compact_node` 压缩生效时把精简流暴露为 `state.compaction["messages"]`，供下游真正使用。

**留档（非阻断，契约内）**：ZSET 分片按 member 哈希分桶，条目增长时不重平衡（单桶可能超 50，属防大 key 的最佳尽力）；真 Redis 分布式闸/BLPOP/ZSET/bigkey 全链路待存储机可达时补实跑（本机 Redis 6379 不可达）。

---

## 4. 测试与工程质量

- `tests/test_contract_task26.py`：**19/19 通过**（GWT① 5 + R4 context_edit/tool_result_clearing 3 + GWT② 4 + GWT③ 7），**1 skipped**＝真 Redis bigkey（本机 Redis 不可达，契约内跳过）。
- 相邻回归：task24/task25/task92 契约测试 32/32 通过（graph.py/runner.py/config.py 改动未破坏）。`test_agent_loop.py` 4 失败为**既有、与本任务无关**（`app/chat/flows/agent.py:161 AGENT_DECISION_PROMPT.format` KeyError，agent.py 不在本任务改动范围，独立审查已确认）。
- 图级 smoke（RunCommand + Python）：`build_graph()` 含 compact 节点；`compact_node` 对 20 轮大流 → applied=True、after=3702≤6000、4 键、精简流 12 条。
- 独立子代理（§3）已按红线复核并采纳修复，修复后 19/19 复测全绿。
- 依赖基线：本任务未新增第三方依赖；测试用 venv `.venv\Scripts\python.exe` 执行。

---

## 5. 数据库校验（RunCommand + mysql CLI / Python 脚本）

- **本任务无 DDL/无表结构变更**（artifact 存 Redis TTL、无新 MySQL 表；config 常量化）。
- **Redis 实况**：本机 `redis://localhost:6379` 连接拒绝（`ConnectionError: 远程计算机拒绝网络连接`）。与 task25/Milvus 同策略——**契约内走内存后端降级**：guard 的 `redis=None→内存`、artifact 的 `ArtifactShuntStore` 内存桶，内存语义经契约测试（§2/§4）实证；`scripts` 级真库验证在 Redis/Milvus 可达前不强制。
- `zadd_sharded/zrange_sharded/scan_bigkeys` 真 Redis 路径代码就绪；真库 bigkey 用例在 Redis 可达时自动生效（skip 已注明）。

> **Redis 降级说明（契约内）**：本环境 Redis 6379 不可达。guard/artifact 的防过载、排队、分流语义由**内存后端契约测试**保证；Redis Lua 分布式计数 / BLPOP / ZSET 分片 / 大 key 扫描全链路已实现，待 Redis 可达时自动启用（无需改调用侧），届时补真库实跑与实测数据。

---

## 6. 交付物清单

| 产物 | 路径 |
|------|------|
| compaction + R4 context editing + tool result clearing + 触发策略 | `edu-agent/app/ai/compaction.py` |
| 工具输出蒸馏分流（>1500 token 进 artifact TTL 1h，流内 1 行结论） | `edu-agent/app/ai/artifact.py` |
| Redis 防过载（全局闸 8 + 会话并发 ≤2 + 排队 10s + ZSET 分片 + bigkey + checkpoint TTL） | `edu-agent/app/ai/guard.py` |
| LangGraph 接线（compact_node 在 plan_node 前 + checkpoint TTL 7 天） | `edu-agent/app/ai/graph.py` |
| 大工具输出流内蒸馏（子代理上下文隔离） | `edu-agent/app/ai/subagents/runner.py` |
| 配置项（6000/3000/6/1500/3600/604800/8/2/10.0） | `edu-agent/app/config.py` |
| 契约测试（19 用例 + 排队攻防） | `edu-agent/tests/test_contract_task26.py` |

---

## 7. 交接与记忆

- 看板 task26 → sync.ps1 后**停等编排者验收**（未验收不进入 task27）。
- **固化纪律（写回项目记忆）**：
  - AI 助手上下文管理走「轻量优先」：`context_edit` 优先、仍超才 `compaction`（summary 结构化 + K=6 原文），避免全量压缩伤前缀缓存。
  - 大工具输出一律 >1500 token 即蒸馏进 artifact（TTL 1h），流内只留 1 行结论，控 LLM 体量。
  - 防过载必须 `acquire`/`release` 在 finally 成对，防闸泄漏；进程内计数为准入权威、Redis 为分布式观测兜底；闸位让位放行补 Redis INCR 防计数下漂。
  - 凡依赖外部存储（Redis/Milvus/…）先探测可达性，不可达按契约走内存降级并在报告注明；`test_agent_loop.py` 4 失败为既有 Agent 决策 prompt bug，属 task29 联调评估范围，非 task26 引入。