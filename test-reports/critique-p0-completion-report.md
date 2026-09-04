# P0 批判落实批次 · 完工验收报告

- **执行角色**：EduAgent 重构项目 · 后端 + 数据库开发者
- **批次范围**：`.opencode/plans/critique-to-tasks.md` 中 P0 段 7 项批判落地
- **执行时间**：2026-08-27（窗口内 18:00–09:00，火山 ark FAST 可用）
- **Git 纪律**：7 个修改任务各自独立 commit（commit 名含 task 编号）；基于最新 HEAD，未使用 `read-tree --empty`；17 个既有验收任务文件全程受保护（snapshot → reset → 单任务 add → commit → 重新 stage）。
- **环境实测**：MySQL 127.0.0.1:3306/edu（root/123456）、Redis 127.0.0.1:6379（PONG）、Rerank sidecar 127.0.0.1:8601（/health=200）均在线。

---

## 一、总览

| # | 任务                         | Commit                          | 类别      | 验收结果 |
| - | -------------------------- | ------------------------------- | ------- | ---- |
| 1 | T1-① DB 枚举 ALTER           | `3c3e7e8` task-T1-critique-fix  | 组A 部署   | ✅    |
| 2 | S1-① HITL 灰度启用             | `0ef75f0` task-S1-critique-fix  | 组A 部署   | ✅    |
| 3 | S1-③ sweep 定时挂接            | `f98729f` task-S1-critique-fix3 | 组A 部署   | ✅    |
| 4 | R1-② sidecar 部署            | `cbddb40` task-R1-critique-fix  | 组A 部署   | ✅    |
| 5 | T1-③ LLM 改写实测              | `1fc74c6` task-T1-critique-fix3 | 组B 窗口实测 | ✅    |
| 6 | C1-② graph 装配 feature flag | `24f38d5` task-C1-critique-fix  | 组B 窗口实测 | ✅    |
| 7 | G1-① retry 接入真实路径          | `95eb621` task-G1-critique-fix  | 组B 窗口实测 | ✅    |



---

## 二、逐条完成证据与验收指标达成

### 1. T1-① — `mcp_tool_call_log.status` 枚举扩展（MANUAL_GUIDE / REJECTION_LIMIT）

**改动文件**：`refactor_sql/task-T1-add-status-enum.sql`（追加执行记录块 + 真实 ALTER）。

**完成证据**：

- 窗口内通过 pymysql 执行 `ALTER TABLE mcp_tool_call_log MODIFY COLUMN status ENUM('SUCCESS','ERROR','TIMEOUT','SKIPPED','REJECTION_LIMIT','MANUAL_GUIDE') …`；落地无 try/except 吞错（脚本直接抛错即中止）。
- 实测回环：`INSERT` 携带 `REJECTION_LIMIT` / `MANUAL_GUIDE` → `SELECT` 读回一致 → `DELETE` 清理，闭环通过。

**验收指标达成**：

- ✅ `status` 支持 `MANUAL_GUIDE` 与 `REJECTION_LIMIT`（`SHOW COLUMNS` 实测类型：`enum('SUCCESS','ERROR','TIMEOUT','SKIPPED','REJECTION_LIMIT','MANUAL_GUIDE')`）。
- ✅ 落库路径未吞掉错误（执行异常直接上抛）。

---

### 2. S1-① — 全流程 HITL 护栏灰度启用

**改动文件**：`.env`（gitignored，仅本机生效，追加 `HITL_ENABLED=True` 等）、`.env.example`（tracked 模板，安全默认 `HITL_ENABLED=False`）。

**完成证据**：

- `settings.HITL_ENABLED` 窗口内实测 = `True`（来自 live `.env`）；`HITL_PENDING_TTL_S=600`、`HITL_AI_REVIEW=False`。
- 单测式校验 `run_hitl_gate`：exec_command / refund / write_file 等被拦截为 `PENDING`，pending 状态 `human_decision=None` 时**零执行器调用**；`_hitl_result_to_mcp` 将 `PENDING` 映射为 `ToolCallStatusEnum.SKIPPED`。

**验收指标达成**：

- ✅ 写工具（exec_command、refund 等）真正被拦截。
- ✅ 未审批时零执行，seam 返回 `SKIPPED`。

---

### 3. S1-③ — HITL 过期 pending 后台 sweep 定时挂接

**改动文件**：`app/ai/memory/service.py`（新增 `_hitl_sweep_loop` + `start_memory_worker`/`stop_memory_worker` 启停）、`refactor_sql/task-S1-create-hitl-approval.sql`（建表）。

**完成证据**：

- `hitl_approval` 表缺失（1146）已补建，`SHOW TABLES LIKE 'hitl_approval'` = True。
- `_hitl_sweep_loop` 镜像 `task-M1` 的 `_dream_scheduler_loop`：懒导入 `sweep_expired_pending` 与 `_default_hitl_store`，间隔 `max(60, HITL_ESCALATION_INTERVAL)`、ttl=`HITL_PENDING_TTL_S`，非阻塞 try/except。
- 实测 sweep：`scanned:1, rejected:1`（构造过期 pending → 自动拒绝）。

**验收指标达成**：

- ✅ `sweep_expired_pending` 按 schedule 触发。
- ✅ 过期 pending 自动拒绝。

---

### 4. R1-② — Rerank sidecar 部署

**改动文件**：`deploy/start_rerank_sidecar.ps1`（新建，启 `uvicorn app.rerank_service.main:app --port 8601` + 模型预热 + readiness 等待）、`app/.../rerank`（sidecar 服务 `app.rerank_service.main:app`，`/rerank` + `/health`，启动预热非致命失败）、主链路 `_rerank_via_sidecar` → `_rerank_docs` 在 `RERANK_SIDECAR_ENABLED=True` 时路由 sidecar。

**完成证据**：

- 窗口内部署并 `curl /health` = 200（cuda + model_loaded）。
- 路由实测：调用主链路 `_rerank_docs` 前后 `request_count` 由 `0 → 1`，证明走 sidecar 而非进程内。
- 当前端口 8601 仍 `PORT_8601_OPEN`，`settings.RERANK_SIDECAR_ENABLED = True`。

**验收指标达成**：

- ✅ `/health` 返回 200。
- ✅ 主链路 `_rerank_docs` 经 sidecar（非进程内）。

---

### 5. T1-③ — 工具参数改写接真实路径（窗口内 LLM 实测）

**改动文件**：`app/mcp/executor.py`（新增 `TOOL_REWRITE_RULES` 6 组、`_apply_rewrite_rules` / `_fast_rewrite_args` / `_default_rewrite_fn`，接入 `call_tool_with_retry` 的 `llm_rewrite_fn`）。

**完成证据**：

- 规则表 6 组（`fill_missing_limit`/`coerce_int`/`coerce_bool`/`normalize_date`/`timeout_on_error`/`ratelimit_on_error`），≥5 组验收线达标；修复了"缺失任一键即填充全部默认"的越界 bug（改为仅补真正缺失键）。
- 窗口内真实 FAST（火山 ark deepseek-v4-flash）改写实测成功：`top_k:"ten"` → `10`。

**验收指标达成**：

- ✅ 真实 FAST 改写 ≥1 例成功 **或** 增强规则映射表 ≥5 组——两项均满足。

---

### 6. C1-② — graph 装配锚定 + 动态选片段 feature flag

**改动文件**：`app/ai/graph.py`（`compact_node` 注入 `anchor_round=settings.ANCHOR_ROUND` + `llm=ai_compaction.make_fast_llm()`，`COMPACTION_LLM_SELECT=False` 时回退规则选片段）。

**完成证据**：

- 压缩契约测试 66 项通过（1 跳过）；round-3 关键数据（如 `KX9-7731-ALPHA`）在规则与 FAST-LLM 两条路径下均可召回（含 `anchor_gate_idx:6`）。
- 窗口内 `settings.ANCHOR_ROUND = 3`、`COMPACTION_LLM_SELECT = True` 实测确认 feature flag 生效。

**验收指标达成**：

- ✅ 真实对话压缩启用锚定 + 动态片段选择，round-3 关键数据可召回。

---

### 7. G1-① — 智能重试退避接入生成/决策真实路径

**改动文件**：`app/chat/generator.py`（`_ChatClient` 新增 `call_chat_with_retry` / `call_chat_stream_with_retry`，`generate_answer` 与 `generate_stream` 工作线程改走重试入口）、`app/chat/flows/agent.py`（意图决策 `_llm_call` 由 `call_chat` 改 `call_chat_with_retry`）。

**完成证据**（子类化 `_ChatClient` + 注入可控异常 + monkeypatch `time.sleep` 实测，4 case 全过）：

| 错误类型          | 行为                           | 实测                                          |
| ------------- | ---------------------------- | ------------------------------------------- |
| 429/RateLimit | 指数退避 2ⁿ 后成功                  | 3 次调用，sleep `[2.0, 4.0]` ✅                  |
| Timeout       | 线性退避 1s/次，超上限抛错              | 3 次调用后抛 `TimeoutError`，sleep `[1.0, 2.0]` ✅ |
| model_error   | 立即切 FAST↔STRONG 重试一次（wait=0） | models `[fast, strong]`，sleep `[]` ✅        |
| 流式首包前异常       | 重试（已吐 token 不重试）             | 重试成功吐出 token，sleep `[2.0]` ✅                |

**验收指标达成**：

- ✅ 真实 429 → 指数退避。
- ✅ 超时 → 线性重试。
- ✅ 模型错误 → FAST↔STRONG 切换。

---

## 三、Git 提交清单（按执行顺序）

```
95eb621 task-G1-critique-fix: 智能重试退避接入生成/决策真实路径 (G1-①)
24f38d5 task-C1-critique-fix: graph.compact_node 装配锚定+动态选片段 feature flag（C1-②）
1fc74c6 task-T1-critique-fix3: 工具参数改写接真实路径（T1-③）
cbddb40 task-R1-critique-fix: 部署 Rerank sidecar（R1-②）
f98729f task-S1-critique-fix3: 挂接 HITL 过期 pending 后台 sweep（S1-③）
0ef75f0 task-S1-critique-fix: 灰度启用全流程 HITL 护栏（S1-①）
3c3e7e8 task-T1-critique-fix: 执行 mcp_tool_call_log.status 枚举 ALTER（T1-①）
```

**17 个既有验收任务文件**（skills ×4、mcp ×7、tests ×3、reports ×3）全程保持 staged，未进入本批次任一 commit，已重新 stage 待后续统一提交。

---

## 四、后续步骤

- 已执行 `sync.ps1` 同步至 ai-hub（见运行日志）。
- **当前状态：停下，等待编排者（orchestrator）验收。** 未经验收不推进下一阶段。
