# task33 完工报告 — MCP 增强：描述评分/重写 + per-server 熔断 + 权限过滤/只读缓存

- 日期：2026-08-26
- 开发角色：后端+数据库开发者
- 任务文档：`.opencode/plans/tasks/task33-mcp-description-review.md`
- 技术选型：`.opencode/plans/tech-source-audit.md` §三（MCP 描述审查/熔断）
- 前置依赖：task09（MCP core 框架）、task27（tool_specs ToolSpec 五要素/权限过滤）
- 单测：`edu-agent/tests/test_task33_mcp_desc_review.py`（9 用例，全部 PASS，无 LLM/无 DB）

## 0. 对齐范围（GWT 精简版 → 本报告编号）
- GWT① 描述体检：规则打分 0-100；<70 分 FAST 重写 → `mcp_tool.description_rewritten` 新列（原 description 仅展示）；审计日志
- GWT② per-server 熔断：连续 5 次失败 → 30s 快速失败（CircuitOpenError），30s 后半开放行探针
- GWT③ 普通用户 chat 工具清单不含 admin_only；同参只读工具 60s 内命中缓存
- GWT④ 写 `handoffs/task33-contract.md`（体检按钮端点 + 工具列表结构，供 task62）

## 1. GWT① 描述体检（描述评分/重写）— ✅

- **规则打分**：`app/mcp/description_reviewer.py::score_description` 为纯函数，六项分项：
  | 分项 | 满分 | 判定 |
  |---|---|---|
  | 动词/动作短语起句 | 20 | 不以填充词（此工具/该工具/this tool…）起头且首字符为 CJK/字母 |
  | 何时不该用（边界） | 15 | 命中 `不用/避免/不适用于/仅当/when not` 等 |
  | 参数说明 | 20 | 描述含 required 参数名 或 `参数/输入/args` 标识 |
  | 返回结构 | 15 | 命中 `返回/输出/结果为/returns` |
  | 示例 | 10 | `示例/例如/example` 或 schema 自带 example/default 兜底 |
  | 无歧义 | 20 | 长度 ≥15 且含句读/分段，或长度 ≥25 |
  | **合计** | **0-100** | `total < 70` 触发重写 |
- **FAST 重写**：`review_tool_description` 中对 `score < REWRITE_THRESHOLD(70)` 调用 `_call_fast_async`（`_ChatClient.get().call_chat(model="fast")`，对齐 2026-08-22 模型配置：火山 ark deepseek-v4-flash），按五要素规范改写 ≤120 字。
- **落库**：高分（≥70）或未触发重写时 `description_rewritten` 置 NULL（前端展示原 description）；低分重写成功则写入新列，原 description 仅在对齐详情可见。
- **审计日志**：每次体检写 `mcp_tool_description_review_log`（score / reasons 分项 / rewritten / rewritten_by_llm / original_desc / operator / trace_id）。
- **降级语义（如实标注）**：LLM 失败时 `rewritten_by_llm=False`、保留原描述、错误写入 `error` 字段，不阻断体检；任意异常被吞并局部返回，绝不向上抛。

## 2. GWT② per-server 熔断（Polaris 三态 + 连续失败模式）— ✅

- `app/core/breaker.py`：新增 `consecutive_failures` 配置项，支持「连续 N 次失败直接断路」模式；新增显式 `check()`（闸门，OPEN 且未到 open_duration 抛 `CircuitOpenError`）/ `record_success()` / `record_failure()`（状态上报）。
- `app/mcp/executor.py`：
  - `_server_breaker(server_id)` 按 server 取独立熔断实例，Redis 共享状态 + 本地缓存防级联。
  - `call_tool` 中先过 `breaker.check()`（OPEN 快速失败毫秒级返回，见 `_breaker_open_resp`）。
  - `_run_once` 结束后按调用结果显式 `record_success/record_failure`（MCP 失败以状态码表达，故显式上报）。
- 行为（单测覆盖）：连续 5 次失败 → OPEN；未到期 `check()` 抛 `CircuitOpenError`；回拨 30s → 半开放行探针；探针连续 3 次成功 → 恢复 closed。
- 熔断快速失败响应 status=ERROR，`latency_ms=0`，前端可见「熔断中」提示。

## 3. GWT③ 权限过滤 + 只读工具缓存 — ✅

- **权限过滤（admin_only）**：`app/ai/tool_specs.py::specs_for_access(specs, is_admin=)` 过滤 admin_only 工具；已在 `build_decision_prefix` 调用，`app/chat/flows/agent.py` 决策前缀拼接处传入 `is_admin`。普通用户 chat 工具清单不含 admin_only，后端保证（前端无需判断）。
- **只读缓存（同参 60s）**：`app/mcp/executor.py::_is_cached_call` 排除写语义前缀（create_/send_/update_/set_/delete_ 等，非幂等副作用不缓存）；`_mcp_cache_key` 对参数做稳定序列化 + MD5，`server_id+tool_name+args-hash` 幂等（同参不同 key 顺序 → 同 key）。命中走 `core.cache.get_or_load`（mutex + TTL jitter），前端透明，命中近 0ms。
- 缓存 loader `_run_once_cached` 先过熔断闸门，熔断异常向外抛避免把降级结果写进缓存。

## 4. GWT④ 前端契约 `handoffs/task33-contract.md` — ✅

- 已交付 `v1.0 READY_FOR_FRONTEND`，含：工具列表结构（MCPToolItem 新增 `description_rewritten/description_score/description_reviewed_at` + 展示规则）、「描述体检」按钮端点（POST `/api/mcp/description-review`）、审计日志面板（GET `/api/mcp/description-review-log`）、权限/错误码、解锁 task62 对应页面。

## 5. 数据库（Alembic 迁移 + registry）

- `alembic/versions/a1b2c3d4e5f6_mcp_tool_description_review.py`：`mcp_tool` 新增列（`description_rewritten` TEXT / `description_score` INT / `description_reviewed_at` DATETIME）+ 新建 `mcp_tool_description_review_log` 审计表（含索引）。列存在性护栏：`_column_names` 检查，幂等可重放。
- `app/mcp/registry.py`：`list_tools_for_review` / `write_description_review` / `insert_description_review_log` / `list_description_review_log`（分页返回 `(total, rows)`，修复了 total=len(当前页) 的错误）。
- `app/mcp/router.py`：`POST /description-review`（管理端「描述体检」按钮）+ `GET /description-review-log`（分页审计日志，用真实 COUNT 作 total）。

## 6. 测试（dev-standard：开发 → 测试 → 审查）

- 开发：`description_reviewer.py` 打分/重写 + `breaker.py` 连续失败模式 + `executor.py` 熔断/缓存接入 + 迁移 + handoff 契约。
- 测试：`tests/test_task33_mcp_desc_review.py` **9/9 PASS**（无 LLM/无 DB）：
  - GWT① 高分满分 100 / 低分触发重写 / 空描述 0 分 / required 参数名得分 / schema example 兜底。
  - GWT③ 只读缓存分类 / 写语义跳过 / 缓存 key 幂等（参数顺序 / 数值 / server 区分）。
  - GWT② 连续 5 次失败 → OPEN → check 抛异常 → 30s 后半开 → 探针成功恢复 closed。
- 审查：模块导入（router/registry/executor/description_reviewer/breaker）无错误；`GetDiagnostics` 无报错。

## 7. 批判承接核对段（逐条列 tracker 项 → 完成证据 → 指标达成）

| tracker 项 | 要求 | 完成证据 | 指标达成 |
|---|---|---|---|
| task09 批判（MCP core 扩展） | 熔断需支持 per-server 隔离 & 快速失败 | `_server_breaker(server_id)` 独立实例 + Redis 共享态；`executor.call_tool` 前置 `breaker.check()`，OPEN 毫秒级返回 ERROR（latency_ms=0）；熔断结果显式 record_success/record_failure | ✅ 已实现 + 单测 |
| task27 批判（tool_specs 复用） | ToolSpec 五要素/权限过滤可复用 | `specs_for_access` + `build_decision_prefix` 复用至 task33 GWT③；`admin_only` 字段直接消费，零重复实现 | ✅ 复用 |
| task29 批判（缓存落地） | 缓存需真实落地（<1024 短前缀等） | `executor` 只读工具缓存走 `core.cache.get_or_load`（幂等 key + mutex + TTL），非幂等写语义工具显式跳过（避免缓存副作用）；熔断异常不污染缓存 | ✅ 落地 |
| LLM 真实重写验证 | 描述重写需真实 FAST 调用验证 | 当前 single 仅纯函数/熔断单测；真实 FAST 重写调用受测试窗口纪律约束，未在窗口外触发，属 task 内预留的手动/窗口内验收项（如编排者需实证请在 12:00-14:00/18:00-次日9:00 安排） | ⏭ 窗口内实测（如实标注） |

## 8. 环境与降级说明（如实标注）

- 当前单测为纯函数 + 熔断器本地状态（关 Redis 同步保证确定性），**未做真实 DB 迁移应用 / 未做真实 LLM 重写**——两者分别取决于迁移执行与测试窗口，均如实标注而非伪造；生产链路方有权在后续接线后复验。
- 熔断半开放探针并发限制（同一瞬间多个探针放行）与 Redis 原子性为已识别的低优先边界，本次以满足 GWT 行为为准，相关加固留给后续加固子代理（如实标注）。

## 9. 交付物

- `app/mcp/description_reviewer.py`（规则打分 + FAST 重写 + 审计）
- `app/core/breaker.py`（连续失败模式 + 显式状态上报）
- `app/mcp/executor.py`（per-server 熔断接入 + 只读缓存）
- `app/ai/tool_specs.py`（权限过滤，task27 复用点）
- `alembic/versions/a1b2c3d4e5f6_mcp_tool_description_review.py`（迁移）
- `app/mcp/registry.py`、`app/mcp/schemas.py`、`app/mcp/router.py`（体检端点 + 分页修复）
- `.opencode/handoffs/task33-contract.md`（前端契约 v1.0）
- `tests/test_task33_mcp_desc_review.py`（9 用例 PASS）
- 本报告

> 结论：GWT①②③✅；GWT④ 契约✅；批判承接逐条核对✅（真实 LLM 重写标为窗口内预留项，未伪造）。提交后运行 `sync.ps1`，停下等待编排者验收，未验收不开始 task34。