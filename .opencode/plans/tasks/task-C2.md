# task-C2 — 缓存前缀达标（1024 token 门槛 + defer_loading + 填充注释）

> 执行工具：**Trae** ｜ 依赖：task27, task95（现状） ｜ 状态：TODO
> 修订来源：`.opencode/plans/production-upgrade-plan.md` P7（缓存前缀稳定 + 填充达标）
> 核心定位：修两件事——①工具清单增删一个 → 全量缓存失效；②system prompt 300 token < 1024 门槛形同虚设。落地 **defer_loading（工具延迟展开）** + **静态填充注释撑到 ≥1024 token** + **锚定策略** + **缓存命中监控**。

## 1. 任务卡片

- **类型/工具**：backend（prompt 层） / Trae
- **依赖**：task27（`prompt_cache.py` 三层组织 + `tool_specs.py` 现状）、task95（R3 MCP 工具延迟加载/描述改写，前缀稳定性基础）
- **并行组**：W1（第一批 P0，与 task-M1 并行——直接影响成本）
- **工作量**：**L**
- **测试窗口纪律**：缓存命中实测量（cache_creation/read 计数）需真实 LLM 调用，仅窗口内；纯函数/计数逻辑随时可测

## 2. 选型依据（竞品实证，引用 production-upgrade-plan.md，关键）

| 竞品 | 做法 | 参考 URL |
|---|---|---|
| **Claude prompt caching** | **最小可缓存前缀 1024 token**；`cache_control` 断点；**工具定义在 system 层，变更即全失效**；defer_loading 工具存根（只名+标记，schema 被选中才展开）保前缀稳定；读缓存 ~10% 费率 | https://platform.claude.com/docs/en/build-with-claude/prompt-caching 、https://code.claude.com/docs/en/prompt-caching |
| **DEV（1024 门槛实证）** | 低于门槛静默不缓存（两计数器为 0）；填充注释撑到阈值可白嫖缓存 | https://dev.to/creeta/claudes-prompt-cache-fails-silently-below-1024-tokens-1ch1 |
| **Glean（Anthropic 工程师）** | 静态优先动态最后；不改 system prompt（用 messages 注入动态信息）；不改工具/模型中途；defer tool loading 保桩序稳定；compaction 复用父会话前缀；缓存命中率当 uptime 监控，低即 SEV | https://glean.smartcoder.ai/en/a/lessons-from-building-claude-code-prompt-caching-is-everythi-sean5e |

## 3. 实现规划要点

### 3.1 工具延迟展开（defer_loading，改造 `app/ai/tool_specs.py`）

- `ToolSpec.to_prompt_entry()` 增加 `deferred` 语义：
  - 前缀只放 `{"tool_name": name, "description": "<一句话摘要>"}`（无 input_schema），对齐 Claude defer_loading 存根；
  - 完整 schema 存 `app/ai/tool_specs.py` 的 `schema_registry`（name → ToolSpec），**仅当 LLM 决策选中该工具**时由执行器 `expand_schema(name)` 展开（进后续请求消息，不进前缀）；
  - 变更影响面：工具增删/描述重写只影响该工具单条，前缀字节不变 → 缓存不失效。
- `build_decision_prefix()` 默认走 deferred 模式（配置 `TOOL_DEFERRED_MODE=True`）；保留 `full` 模式供契约测试 A/B。
- 与 task95 联动：MCP 工具描述体检（`description_reviewer.py`）改写的 description 写入 registry 摘要层，前缀只含摘要。

### 3.2 静态填充注释撑到 ≥1024 token（改造 `app/ai/prompt_cache.py`）

- 新增 `ensure_min_prefix(prefix) -> str`：
  - 测量 `estimate_tokens(prefix)`；不足 `PROMPT_CACHE_MIN_TOKENS=1024` 时追加静态填充注释块（固定文本 + 版本号，如 `# cache-filler v3 ...` 含稳定占位符），补齐到 ≥1024；
  - **填充注释必须逐字节稳定**（不随时间/环境变化），且放 system 层末尾、工具清单后（不改工具桩序，对齐 Glean 静态优先）；
  - 对齐 DEV 实证：低于门槛静默不缓存 → 补齐后跨过 DeepSeek/Claude 缓存门槛。
- 三层组织保持：`system/project/conversation`；`PromptCache.set()` 增加 `min_tokens` 检查与填充后 key 计算。

### 3.3 锚定策略（与 task-C1 共享）

- `prompt_cache.py` 增加 `anchor_guard(prefix, dynamic_messages)`：闸门前 System+工具固定前缀永不改，动态信息（用户问题/记忆/检索上下文）经**新消息注入**（messages 数组追加，不进前缀）。
- 失效原因清单扩充：工具 schema 变更只记该工具级失效（`invalidate(layer="project", reason="tool_schema_change:{tool_name}")`），不整层清空。

### 3.4 缓存命中监控（对齐 Claude SEV / Glean uptime）

- `scripts/eval/cache_meter.py` 扩展（现状已存在）：
  - 计量 `cache_creation / cache_read_input_tokens`（llm_client 返回 usage 已有字段）；
  - 命中率= `cache_read / (cache_read + cache_miss)`，按 `{model, layer}` 维度上报；
  - 告警阈值：`CACHE_HIT_RATE_SEV=0.5`（命中率 <50% 记 SEV，对齐 Claude 把命中率当 uptime 监控）；
  - 指标经 task-O1 的 5 维指标汇出。
- 配置项：

```python
PROMPT_CACHE_MIN_TOKENS = 1024
CACHE_FILLER_VERSION = "v3"
TOOL_DEFERRED_MODE = True
CACHE_HIT_RATE_SEV = 0.5
```

### 3.5 测试

- `tests/test_contract_task_c2.py`：填充后前缀 ≥1024 token 且逐字节稳定（两次构建相等）；deferred 模式下工具变更前缀 hash 不变；命中率计量与 SEV 触发；与旧 full 模式 A/B 命中率对比。

## 4. 验收标准（Given/When/Then）

- **AC1（填充达标）**：Given `build_decision_prefix` 输出 300 token 前缀，When `ensure_min_prefix`，Then 返回前缀 ≥1024 token（实测估算），且两次调用字节完全一致。
- **AC2（defer 前缀稳定）**：Given MCP 工具列表从 3 个增至 4 个（或某工具描述被体检改写），When 重新构建决策前缀，Then 前缀中既有工具桩的字节零变化（仅新增 1 条存根），`PromptCache` project 层不产生整层失效事件。
- **AC3（schema 按需展开）**：Given LLM 决策选中工具 X，When 执行器调用，Then 完整 schema 从 `schema_registry` 展开进入后续请求，决策前缀不含 X 的 input_schema。
- **AC4（命中率监控）**：Given 真实 LLM 调用序列（窗口内），When 观察 `cache_meter`，Then 输出 cache_creation/cache_read 计数与命中率；命中率 <50% 时触发 SEV 告警记录。
- **AC5（回归）**：Given task27/task95 既有契约测试，When 改造后运行，Then 全 PASS（三层组织/失效原因/描述体检不回归）。

## 5. 交接与记忆

- **完工报告**：`test-reports/task-C2-completion-report.md`（填充前后 token 实测、工具变更前缀 diff 校验、命中率窗口实测）。
- **记忆写入**：AI-Hub `trae-projects/EduAgent/project_memory.md` 追加"前缀 ≥1024 token 填充注释 + defer_loading 工具存根"成本优化决策。
- **完成动作**：git commit → sync.ps1。

## 6. 批判承接

- **production-upgrade-plan.md P7**（缓存前缀稳定 + 填充达标）：工具清单增删一个全量失效 + 300 token 形同虚设 → AC1~AC4 落实。
- **critique-backlog-tracker.md**：task32「task29 批判③关联：缓存命中实际落地（真实短前缀<1024 未达缓存门槛）」——本任务 AC1/AC4 正是该批判的根治；task97（R5 缓存监控）的 `cache_read/creation` 指标由本任务承接强化。

## 7. 与其他 task 关联

- **联动**：task-C1（锚定闸门共享前缀稳定语义）；task-O1（缓存命中率指标汇入 5 维指标 + SEV 告警）；task95（MCP 延迟加载的摘要列表是本任务 deferred 数据源）。
- **执行顺序**：W1 第一批（成本大头，立即做）；建议 task95 的摘要列表已就绪后实施，否则 deferred 依赖的摘要层先自建。