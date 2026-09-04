# task-M1 — 记忆事件溯源 + Dream 巩固（P1 事件溯源 + P3 AutoDream）

> 执行工具：**Trae** ｜ 依赖：task25, task92（现状） ｜ 状态：TODO
> 修订来源：`.opencode/plans/production-upgrade-plan.md` P1（事件溯源）+ P3（Dream 巩固）
> 核心定位：把 `user_memory` 从"当前快照"改为"append-only 事件流 + 可重建派生视图"，并加后台巩固子代理，解决"AI 瞎说我说过的话"无法自证与"三条独立记忆无法升维"两个用户投诉。

## 1. 任务卡片

- **类型/工具**：backend（AI 记忆域） / Trae（无 Workflow() API，手动调度 dev-standard.mjs 8 阶段；MySQL 用 RunCommand+mysql CLI，无 mysql MCP）
- **依赖**：task25（三层记忆现状：`persistence.py`/`vector.py`/`service.py`）、task92（子代理 runner，供 Dream fork 子代理）；新任务无前置
- **并行组**：W1（第一批 P0，与 task-C2 并行）
- **工作量**：**XL**（事件表 + 迁移 + 回滚 API + Dream 子代理 + 容量治理）
- **测试窗口纪律**：LLM 相关（Dream 子代理、trace_id 抽取）仅 12:00-14:00 / 18:00-次日 9:00；SQL/纯逻辑契约测试不受限

## 2. 选型依据（竞品实证，引用 production-upgrade-plan.md）

| 竞品 | 做法 | 参考 URL |
|---|---|---|
| **CortexDB** | 事件溯源：WAL append-only + fsync，原始事件为唯一事实源；embedding/摘要/知识图为异步派生可重建视图；每条 Fact 带 `supports: [event_id]` 回溯 | https://cortexdb.ai/docs/concepts/event-sourcing |
| **ChronoMem**（Google ADK） | 每次写提交整个记忆快照 + 版本历史 + 自然语言回滚；append-only 事件日志 `{v_j}` + HEAD 指针 | https://arxiv.org/html/2607.27773 |
| **Ninad Pathak（合规 Agent）** | 禁止 UPDATE/DELETE；每行 `entity_id/memory_content/embedding/timestamp/valid_to/trace_id`；过滤 `valid_to IS NULL` 防召回旧版本 | https://ninadpathak.com/blog/memory-versioning-and-audit-trails/ |
| **Claude AutoDream** | 5 会话 + 24h 后 fork 子代理，4 阶段（orient/gather/consolidate/prune）；mtime 文件锁防多实例并发；回滚靠 mtime 回拨 | https://codewisdom.io/blog/ai-agents-claude-code-memory-system-notes/ 、https://soma.gravicity.ai/blog/the-architecture-of-forgetting |
| **VikingMem**（字节） | LLM_MERGE 增量去重/冲突消解 + TIME_COMPRESS 主题时间线渐进巩固 | https://arxiv.org/html/2605.29640v3 |

## 3. 实现规划要点

### 3.1 事件溯源表（append-only，MySQL）

新增表 `user_memory_event`（DDL 放 `项目文档/` 与重建脚本同目录，`patch_memory_tables.sql` 风格）：

```sql
CREATE TABLE IF NOT EXISTS user_memory_event (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,        -- 事件序号
  event_type    VARCHAR(32)  NOT NULL,                    -- create | update | delete | consolidate | rewind
  entity_id     BIGINT       NOT NULL,                    -- 记忆实体（跨版本同一 entity_id）
  user_id       INT          NOT NULL,
  memory_type   VARCHAR(32),                              -- preference/goal/profile/correction/fact
  topic         VARCHAR(64),
  content       TEXT         NOT NULL,                    -- 本版本内容
  embedding     JSON         NULL,                        -- 可选：向量快照（1024 维 JSON）
  importance    INT,
  score         FLOAT,
  valid_from    DATETIME     NOT NULL,
  valid_to      DATETIME     NULL,                        -- NULL=当前有效；盖章=废弃版本
  trace_id      VARCHAR(64)  NULL,                        -- 触发它的 LLM/工具调用链路
  operator      VARCHAR(64)  NULL,                        -- user/admin/dream
  supports      JSON         NULL,                        -- [event_id] 支持证据（对齐 CortexDB）
  created_at    DATETIME     NOT NULL,
  INDEX idx_event_user (user_id, entity_id, valid_to),
  INDEX idx_event_trace (trace_id)
) ENGINE=InnoDB;
```

- **写路径**：`app/ai/memory/persistence.py` 新增 `EventMemoryPersistence`（或改造 `SqlMemoryPersistence`）：`insert` 改为 **INSERT 新行**（不 UPDATE）；"更新/删除" = 新行 + 旧行 `valid_to` 盖章（`UPDATE user_memory_event SET valid_to=NOW() WHERE entity_id=%s AND valid_to IS NULL` 单条 UPDATE 允许——这是版本盖章，不是改内容）。
- **查询过滤**：所有有效记忆查询强制 `WHERE valid_to IS NULL`（与 `deleted=0` 并存）；`user_memory` 视图保留为兼容层或直接淘汰由 `user_memory_event` 派生。
- **回滚 API**：`POST /api/memory/rewind`（body `{entity_id, target_event_id}`）+ `GET /api/memory/history/{entity_id}`（分页事件流）。回滚 = 在 target 之后插入一条 `event_type=rewind` 的新行（内容=target 内容），HEAD 指针移到该行——**不做物理删除**（ChronoMem 语义）。
- **容量治理**：`app/ai/memory/compactor.py` 新增快照压缩器：按实体生命周期保留近期高保真事件，旧事件懒合成摘要事件（`event_type=consolidate`，内容=结构化摘要，`supports=[旧event_ids]`），对齐 VikingMem TIME_COMPRESS；容量上限从"500 条/用户"改为"有效事件 ≤ N + 压缩事件"，压力下无阻塞。

### 3.2 向量联动（配合 task-M2）

- `app/ai/memory/vector.py` `MemoryVectorStore`：
  - `upsert` 写入事件表的 `embedding` 快照（Milvus 仍为主检索后端）；
  - `search` 时 **Milvus 预过滤 `valid_to IS NULL`**（Milvus filter 增加 `valid_to == null` 或利用 Milvus 动态字段 + `WHERE` 表达式；若 Milvus schema 不便加字段，则检索后在 `memory/service.py` 二次过滤），保证"检索永不返回废弃版本"。
- `app/ai/memory/service.py` `recall_topk` 增加 `valid_only=True` 默认参数，契约测试验证。

### 3.3 Dream 巩固子代理（P3，并入本任务）

- 新增 `app/ai/memory/dream.py`：
  - 触发：每 `DREAM_SESSION_INTERVAL=5` 会话 + `DREAM_MIN_AGE_HOURS=24` 后触发（会话计数存 Redis `memory:session_count:{user_id}`）；
  - 执行：fork task92 子代理（复用 `app/ai/subagents/runner.py` `run_subagents`），4 阶段 prompt（orient/gather/consolidate/prune）读该用户有效记忆 → 去重/合并/升维 → 写回（`event_type=consolidate` 新行 + 旧行盖 `valid_to` + `consolidated_version` 标注）；
  - 升维示例验收："喜欢 Python"+"喜欢 FastAPI"+"讨厌 Java" 三条 → 生成 "Python 后端开发者，适合 FastAPI 不适合 Java" 结构化条目；
  - **mtime 分布式锁**：`app/ai/memory/dream_lock.py` 用 Redis `SET NX EX` 窗口锁（key=`memory:dream:{user_id}`，TTL=`DREAM_LOCK_TTL_S=600`）防多实例并发巩固；Redis 不可达降级进程内锁 + `degraded_reason="dream_lock_unavailable"`。
- 后台调度：`app/ai/memory/service.py` `start_memory_worker()` 扩展启动 Dream 后台任务（同生命周期）；管理接口 `POST /api/admin/memory/dream/run` 手动触发。

### 3.4 配置项（app/config 新增）

```python
MEMORY_EVENT_ENABLED = True          # 事件溯源总开关
MEMORY_EVENT_TTL_DAYS = 180          # 压缩器保留近期高保真天数
DREAM_SESSION_INTERVAL = 5
DREAM_MIN_AGE_HOURS = 24
DREAM_LOCK_TTL_S = 600
DREAM_MAX_ENTITIES_PER_RUN = 200
```

### 3.5 测试

- `tests/test_contract_task_m1.py`：事件写入/版本盖章/回滚/检索过滤/容量压缩/Dream 升维 契约测试（纯逻辑部分可离线，LLM 部分 mock summarizer）。

## 4. 验收标准（Given/When/Then）

- **AC1（事件溯源写路径）**：Given 用户 A 写入一条记忆，When 再次更新该记忆，Then `user_memory_event` 中产生 2 行（原行 `valid_to` 被盖章、新行 `valid_to IS NULL`），无任何内容被 UPDATE 覆盖。
- **AC2（检索过滤）**：Given 用户 A 存在已废弃（`valid_to IS NOT NULL`）与当前有效记忆，When 执行 `recall_topk(user_id=A, query=...)`，Then 返回结果中 `valid_to IS NULL` 占比 100%（废弃版本永不召回）。
- **AC3（回滚正确性）**：Given 用户 A 记忆经过 3 个版本（v1→v2→v3），When `POST /api/memory/rewind {entity_id, target_event_id=v1}`，Then 事件流新增 `event_type=rewind` 行且内容=v1 内容，HEAD 指针指向 v1，检索返回 v1。
- **AC4（审计可查）**：Given 用户 A 全部记忆事件，When `GET /api/memory/history/{entity_id}`，Then 返回分页事件流含每行的 `event_type/operator/trace_id/valid_from/valid_to`，且每条非 consolidate 事件 `trace_id` 非空（指向触发它的 LLM/工具调用）。
- **AC5（容量压力）**：Given 1000 DAU × 20 条/天压力仿真（脚本造数据），When 事件表写入 + 压缩器运行，Then 事件表写入无阻塞、单用户有效事件数收敛 ≤ 配置上限、旧事件被懒合成摘要事件（`supports` 引用原事件 id）。
- **AC6（Dream 升维）**：Given 用户 A 有 "喜欢 Python"+"喜欢 FastAPI"+"讨厌 Java" 三条记忆，When Dream 巩固子代理运行（LLM 测试窗口内），Then 产生一条 consolidate 事件内容含 "Python 后端开发者 / 适合 FastAPI / 不适合 Java" 升维语义，旧三条盖 `valid_to`。
- **AC7（并发锁）**：Given 两个进程同时触发同一用户 Dream，When 运行，Then 只有一个执行成功，另一个因 `SET NX EX` 锁直接跳过（`dream_lock_acquired=false`），无重复 consolidate。

## 5. 交接与记忆

- **完工报告**：`test-reports/task-M1-completion-report.md`（含事件表 DDL diff、回滚 API 实测、Dream 升维示例实测、压测数据）。
- **记忆写入**：AI-Hub `trae-projects/EduAgent/project_memory.md` 追加"user_memory_event 表为记忆唯一事实源；user_memory 降级为兼容视图"工程决策。
- **契约冻结**：`/api/memory/history`、`/api/memory/rewind` 响应壳 `{code,message,data}` 对齐响应壳契约（①）；`memory_type` 枚举沿用 `schemas.py` 的 5 类。
- **完成动作**：git commit → `powershell -File D:\.ai-hub\sync.ps1`。

## 6. 批判承接

- **production-upgrade-plan.md P1**（记忆非事件溯源，最高优先级）：容量 500 条/用户不真实（60 万条/月），用户投诉无法自证 → 本任务 AC1~AC5 逐条落实。
- **production-upgrade-plan.md P3**（无后台巩固 Dream）：三条独立记忆召回只中一条导致推荐乌龙 → 本任务 AC6/AC7 落实。
- **critique-backlog-tracker.md**：task32「记忆召回指标样本不足（仅 5 条）」——本任务完成后 `scripts/eval/eval_dataset.py` 记忆召回评估集可直接消费事件表有效行（≥30 条素材来源）；task37「user_memory 512→1024 历史残留确认」——事件表重建时一并核对 schema 维度，杜绝 512 维脏数据流入事件表。

## 7. 与其他 task 关联

- **联动**：task-M2（Redis 共享向量 backend 复用本任务 `valid_to IS NULL` 过滤语义）；task-O1（memory_event 埋点事件接入 trace 检索面板）；task-S1（rewind 属高风险写操作，需过 HITL-Gate）。
- **执行顺序**：W1 第一批最先做（审计合规）；Dream LLM 部分测试受窗口纪律约束，建议先落地事件溯源（SQL/API）再排 Dream 窗口。