# task-M1 完工报告：记忆事件溯源 + Dream 巩固（生产级改造第一批 P0）

- **分配**：AI 主线 R2~R5 收尾后，生产级改造第一批 P0（对标 `production-upgrade-plan.md` P1 事件溯源 + P3 Dream）
- **执行者**：后端 + 数据库开发者
- **测试窗口纪律**：Dream LLM 调用受 12:00–14:00 / 18:00–9:00 约束；当前执行于窗口外，契约测试以 **mock llm** 验证升维逻辑，真实 LLM 实测留待窗口内（见「风险/下一步」）
- **契约红线**：所有新增端点均为 `/api/memory/*` 纯增量，**未改动** `/me`、`/learning` 响应结构，前端个人中心零影响
- **git 纪律**：基于最新 HEAD `056fa1b`，单 commit，仅提交 task-M1 文件，**未触碰** prior-task 已 staged 文件；未使用 `read-tree --empty`

---

## 1. 改动文件清单（DDL diff / 源码）

### 1.1 新增 DDL — `项目文档/patch_memory_event.sql`
新增两张表，作为长时记忆「唯一事实源」：

```sql
CREATE TABLE user_memory_event (
    id            BIGINT      NOT NULL AUTO_INCREMENT,
    event_type    VARCHAR(32) NOT NULL,   -- create/update/rewind/delete/consolidate
    entity_id     BIGINT      NOT NULL,   -- 跨版本稳定身份（=向量主键）
    user_id       BIGINT      NOT NULL,
    memory_type   VARCHAR(32) NULL,
    topic         VARCHAR(64) NULL,
    content       TEXT        NOT NULL,
    embedding     JSON        NULL,
    importance    INT         NULL,
    score         FLOAT       NULL,
    access_count  INT         NOT NULL DEFAULT 0,
    last_access_at DATETIME   NULL,
    valid_from    DATETIME    NOT NULL,
    valid_to      DATETIME    NULL,        -- 唯一 HEAD = valid_to IS NULL 且 event_type<>'delete'
    trace_id      VARCHAR(64) NULL,        -- 审计溯源（每事件必填，缺省自动生成 mem- 前缀）
    operator      VARCHAR(64) NULL,
    supports      JSON        NULL,        -- consolidate 引用被合并源事件 id
    created_at    DATETIME    NOT NULL,
    INDEX idx_event_user   (user_id, entity_id, valid_to),
    INDEX idx_event_trace  (trace_id),
    INDEX idx_event_entity (entity_id, valid_to),
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE user_memory_entity_seq (
    id BIGINT NOT NULL AUTO_INCREMENT,      -- 独立自增分配器，避免事件表自引用 UPDATE
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 1.2 配置 — `app/config.py`（MODIFIED）
追加 task-M1 配置段：`MEMORY_EVENT_ENABLED / MEMORY_EVENT_TTL_DAYS / DREAM_SESSION_INTERVAL / DREAM_MIN_AGE_HOURS / DREAM_LOCK_TTL_S / DREAM_MAX_ENTITIES_PER_RUN / DREAM_MODEL`。

### 1.3 事件溯源持久化 — `app/ai/memory/event_persistence.py`（NEW）
`EventMemoryPersistenceBase` + `SqlEventMemoryPersistence`（生产 MySQL，幂等建表）+ `MemEventMemoryPersistence`（in-process 零依赖，契约测试用）。核心语义：
- 写 = INSERT；更新/删除 = **新行 + 旧行 `valid_to` 盖章**（单条 UPDATE 仅用于版本盖章，绝不覆盖 content）；
- 每个 entity_id 恒有唯一 `valid_to IS NULL` 行 = HEAD；检索强制 `WHERE valid_to IS NULL AND event_type<>'delete'`；
- `trace_id` 缺省自动生成 `mem-{uuid}`；`entity_id` 经 `user_memory_entity_seq` 分配，等于向量主键。

### 1.4 持久化工厂 — `app/ai/memory/persistence.py`（MODIFIED）
`build_persistence()` 按 `settings.MEMORY_EVENT_ENABLED` 切换：True→`SqlEventMemoryPersistence`，False→旧 `SqlMemoryPersistence`（降级，契约不变）。

### 1.5 记忆门面 — `app/ai/memory/store.py`（MODIFIED）
`recall` 增加 `valid_only` 形参（实际过滤在 `fetch_by_ids` 内强制）；新增 `_sync_vector`（主键值=entity_id，版本变更同步 upsert/delete）；包装层 `update_memory/rewind/delete_memory/consolidate/history`。

### 1.6 服务包装 — `app/ai/memory/service.py`（MODIFIED）
新增 `rewind_entity / entity_history / trigger_dream / compact_user_memory`；`_dream_scheduler_loop` 后台 SCAN `memory:session_count:*` 触发巩固；`start/stop_memory_worker` 启停调度（**已修复**：原函数体引用未导入的 `settings`，补 `from app.config import settings`）。

### 1.7 容量治理压缩器 — `app/ai/memory/compactor.py`（NEW）
`compact_user(store, user_id, *, summarizer, batch_size, capacity)`：有效数 ≤ 容量上限不压缩；超出则按 score 升序取低价值批次 consolidate，源 HEAD 盖章、`supports` 引用源事件 id，有效数收敛到上限（对齐 VikingMem TIME_COMPRESS）。默认 `summarizer=_rule_summarize`（确定性规则摘要，零 LLM）。

### 1.8 分布式锁 — `app/ai/memory/dream_lock.py`（NEW）
`DreamLock(ttl_s)`：优先 Redis `SET key 1 NX EX {ttl}`（AC7）；Redis 不可达降级进程内单调时钟锁。

### 1.9 Dream 巩固子代理 — `app/ai/memory/dream.py`（NEW）
4 阶段 orient/gather/consolidate/prune，要求 LLM 输出 JSON 数组 `[{content, memory_type, topic, importance, source_entity_ids}]`；`_extract_json_array` 稳健抽取；`run_dream(user_id, *, llm, redis, dry_run, store)` 加锁→取有效记忆→调 LLM→逐条 `store.consolidate`→释放锁。**已修复**：`router.py` 中 `_check_owner` 与 `rewind_memory` 误用 `user.id`（UserInfo 无此字段，正确为 `user.user_id`），否则 `/api/memory/*` 会 500。

### 1.10 契约端点 — `app/ai/memory/router.py`（NEW）+ `app/main.py`（MODIFIED）
纯增量端点：
- `POST /api/memory/rewind` `{entity_id, target_event_id}`
- `GET  /api/memory/history/{entity_id}`（分页事件流，含 trace_id）
- `POST /api/admin/memory/dream/run` `{user_id}`（仅 ADMIN/MANAGER）
响应壳 `{code, message, data}`；所有权校验：回滚/历史仅属主或管理员可访问（403/404）。

---

## 2. 契约测试实测（`tests/test_contract_task_m1.py`）

运行：`cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_contract_task_m1.py -q`
**结果：9 passed（AC1–AC7 + API 契约）**，全 in-process（Mem 变体零外部依赖），Dream 用 mock llm。

| AC | 验收点 | 实测结论 |
|----|--------|----------|
| AC1 | 写路径双行 + valid_to 盖章 | write→1 行(create)；update→2 行，仅 1 个 HEAD(valid_to IS NULL)，旧 create 被盖章，HEAD 内容=v2 ✅ |
| AC2 | 检索强制 valid_to IS NULL | 5 实体经 update/rewind/delete 后 list_effective 仅含非删除 HEAD；fetch_by_ids(删除实体)=[]；recall 不返回已删内容，每条实体至多出现一次 ✅ |
| AC3 | rewind 正确性 | 回滚后 HEAD 内容=目标版本；history 保留 [rewind,update,create]，旧版本未物理删除；HEAD 唯一 ✅ |
| AC4 | history 审计含 trace_id | 每条事件 trace_id 非空；显式 trace 原样保留；缺省自动生成 `mem-` 前缀；create operator=system ✅ |
| AC5 | 容量治理收敛 + 懒合成摘要 | 40 条 → 压缩至 ≤10（上限），compacted>0；合并事件内容以 `[合并` 开头，`supports` 引用源事件 id（可回溯）✅ |
| AC6 | Dream 升维（mock llm） | 3 条同类记忆合并为 1 条结构化条目；源实体被盖章废弃；list_effective 收敛为 1 条升维记忆 ✅ |
| AC7 | 并发锁 SET NX EX 仅一实例 | 并发 `run_dream`/`DreamLock.acquire` 经 FakeRedis：恰好 1 个获锁成功；释放后可再次获取 ✅ |
| API | 契约红线 + 鉴权 | 属主 history/rewind→200；非属主→403；管理员→200；学生触发 admin 端点→403 ✅ |

### 2.1 压测明细（AC5）
- 输入：单用户 40 条有效记忆，容量上限 10。
- 结果：压缩后有效数 = 10（=上限），consolidated 批次数 8，每批 `supports` 均引用源事件 id，`history` 仍可回溯源原文。

### 2.2 回滚实测（AC3）
- 链路：`write(v1) → update(v2) → rewind(v1 的 event_id)`。
- 断言：回滚后 `fetch_entity` 内容 == v1；`history` 同时包含 rewind/update/create 三事件，旧 update 行内容保留（append-only，非物理删除）。

### 2.3 Dream 升维实测（AC6，mock llm）
- 输入：3 条同类记忆（喜欢 Python / 喜欢 FastAPI / 讨厌 Java）。
- mock LLM 返回：`[{"content":"技术栈画像：偏好 Python/FastAPI，排斥 Java","source_entity_ids":[e1,e2,e3],...}]`。
- 结果：`consolidated=1`，新 consolidate 实体内容精确等于升维结论；e1/e2/e3 均被盖章（fetch_entity=None）；有效集合收敛为 1 条。

---

## 3. 竞品对标落实
- **CortexDB（WAL append-only）**：`user_memory_event` 为唯一事实源，更新=新行+盖章。
- **ChronoMem（Google ADK 版本控制）**：rewind=追加 rewind 事件、HEAD 指针移动，不物理删除。
- **Claude AutoDream（5会话+24h+mtime锁）**：`DREAM_SESSION_INTERVAL`/`DREAM_MIN_AGE_HOURS` + Redis SET NX EX 锁。
- **Ninad（禁 UPDATE/DELETE + trace_id）**：检索强制 `valid_to IS NULL`，trace_id 审计溯源。
- **VikingMem（TIME_COMPRESS）**：压缩器近期高保真 + 旧事件懒合成摘要。

---

## 4. 风险 / 下一步
1. **真实 Dream LLM 升维实测**：需在测试窗口（18:00–9:00）内跑一次真实 `run_dream`（干掉 mock），确认 LLM 输出 JSON 解析与升维质量；当前以 mock 验证逻辑链路。
2. **SQL 端到端**：Mem 变体已全绿；生产 `SqlEventMemoryPersistence` 需在 MySQL 环境执行 `patch_memory_event.sql` 后跑一次冒烟（建表幂等已保证）。
3. **前端 task-FE-M1（记忆历史/回滚页）**：依赖本任务契约冻结，可基于 `GET /history/{id}` + `POST /rewind` 开发。
4. **未提交 prior-task staged 文件**：本次仅提交 task-M1 文件，仓库中 prior-task 已 `A` 的文件保持原状，交由各自验收流程处理。

---

## 5. 提交与同步
- 提交对象：task-M1 相关 12 个文件（config/persistence/store/service/compactor/dream_lock/dream/router/main + event_persistence + tests + patch SQL）。
- 单 commit，基于 `056fa1b`，禁 `read-tree --empty`。
- 后续：`sync.ps1` → 停下等待验收。
