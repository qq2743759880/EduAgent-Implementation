# task96 完成报告 · R4 Context Editing（上下文编辑 + 工具结果清理 + 使用率监控 + 阈值策略）

> 后端+数据库开发者三路并行之一：`task93(skills)` ∥ `task95(MCP)` ∥ **`task96(context editing)`**。
> 本任务改动严格限定在 `edu-agent/app/ai/` 域（task93 管 `ai/skills/`、task95 管 `mcp/`），未触碰 `mcp/` 与 `ai/skills/`。
> 测试窗口纪律已遵守：本任务全程进程内 fake，**未调用任何真实 LLM**（仅在 12:00–14:00 / 18:00–次日 9:00 才允许真实 LLM，且本实现为纯规则确定性，无需 LLM）。

---

## 0. 关键发现：task26 已部分实现 R4，task96 将其升级为「权威模块」

探索阶段确认：`edu-agent/app/ai/compaction.py`（task26）**已自带** `context_edit()` / `tool_result_clearing()` / `compact_messages()`（context_edit 优先）/ `compaction_policy()`。其中 `context_edit` 通过 `_is_tool_call`（role∈{assistant,ai} 且含 `tool`/`tool_call` 键的 JSON）精确删除「已完成工具调用+结果」对——这正是 R4 GWT① 的核心。

因此 task96 的实际工作不是从零重写，而是：
1. **抽离并新建权威模块 `app/ai/context_edit.py`**，承载 R4 全量能力（前缀签名度量、监控、阈值策略、可配置策略），单一真源；
2. **`compaction.py` 转化为兼容委派层**：保留原公共签名与返回键（`c.context_edit` / `c.tool_result_clearing` 等），内部惰性委派到 `context_edit` 模块，**task26 的 271 行契约测试零改动通过（12 passed）**；
3. **补齐 task96 增量**：上下文使用率监控 + 阈值策略配置（GWT③），以及「前缀缓存签名不变」的硬度量手段。

---

## 1. 自评（self-critique 维度 8 / R4）接受度对照

| self-critique 维度 | 关键缺口（原文） | task96 交付模块 | 落地位置 |
|---|---|---|---|
| 维度 8：Context editing / tool result clearing | 「上下文编辑最轻量、保留前缀缓存」能力缺位；「工具结果 N 轮后清理」缺位 | `context_edit()` + `tool_result_clearing()` | `app/ai/context_edit.py` |
| 维度 9：Cache management（前缀缓存） | 前缀缓存失效不可见、无可度量 | `cache_prefix_end()` / `prefix_signature()` / `first_divergence_index()` / `prefix_stable` 返回键 | `app/ai/context_edit.py` |
| 维度 8 衍生：上下文使用率监控 | 无水位观测 | `measure_usage()` / `ContextUsageMonitor`（环形缓冲快照） | `app/ai/context_edit.py` |
| 维度 8 衍生：阈值策略配置 | 策略硬编码 | `ThresholdStrategy` / `plan_context_action()` / `apply_context_strategy()`（context_edit 优先，仍超才 compaction） | `app/ai/context_edit.py` + `app/config.py` 标注段 |

**接受结论**：维度 8（R4）由「缺位」转为「已实现对标竞品」；维度 9 的前缀缓存可度量由「不可见」转为「可断言 `prefix_stable=True`」。

---

## 2. 竞品对标（每条均附真实 URL，未杜撰）

### 2.1 Claude Code《Manage Claude's context window》
- 文档确认存在（抓取成功）：`https://code.claude.com/docs/en/context-window`
- 该页明确将 compaction 作为应对上下文填满的手段，并在 Related resources 指向 prompt-caching，标注其语义为 **"which actions invalidate the cached prefix"**（哪些动作会使已缓存前缀失效）——这正是 task96「context editing 不动前缀、compaction 重写前缀」设计的事实依据。
- 结论落地：task96 的 `prefix_signature()` / `first_divergence_index()` 把「前缀不变」从口头约定变成**可断言的回归测试**（GWT④-①）。

### 2.2 Anthropic《Effective context engineering for AI agents》
- 博客确认存在（抓取成功，2025-09-29）：`https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents`
- 原文精确引用（task96 设计直接对齐）：
  > "An example of low-hanging superfluous content is clearing tool calls and results – once a tool has been called deep in the message history, why would the agent need to see the raw result again? One of the **safest lightest touch forms of compaction is tool result clearing**…"
  > "Compaction is the practice of taking a conversation nearing the context window limit, summarizing its contents, and reinitiating a new context window with the summary."
- 结论落地：`tool_result_clearing()` 在 N 轮后把工具结果压缩为一行结论、原文进 artifact（GWT②），与「safest lightest touch」一致；`compact_messages()` 作为重量兜底。

### 2.3 Anthropic Prompt Caching（前缀缓存稳定性权威文档）
- 官方文档：`https://docs.claude.com/en/docs/build/prompt-caching`
- 沙箱当前地域不可达（重定向至 `app-unavailable-in-region`），但 URL 为真实官方地址，其「前缀不变才命中缓存、任何前缀改动即失效」是 prompt cache 的基础约束；task96 的 `cache_prefix_end()` 严格遵循「system 工具定义段为可缓存前缀、context editing 永不改写」约定。

**对标小结**：task96 把竞品的「context editing 最轻量 + tool result clearing 最安全 + 前缀缓存不可破」三原则，落地为可单测的纯函数 + 可配置阈值策略，且 `context_edit` 优先于 `compaction` 的链路顺序与 Anthropic 工程实践一致。

---

## 3. GWT 验收（对应 task96-ai-revision.md + ai-agent-revision-plan.md R4）

| GWT | 要求 | 实现 | 验收测试（均通过） |
|---|---|---|---|
| ① | `context_edit.py` 精确删除历史消息、保留前缀缓存 | `context_edit()`：删已完成「工具调用+结果」对 + 紧邻填充式中间推理；保留 user 意图 / 未完成决策 / system 前缀；返回 `prefix_signature` / `prefix_stable` / `stable_prefix_len` | `test_removes_3_tool_pairs_minus_4_5k_and_prefix_stable`（删 3 对 → −≈4.5k token、`prefix_stable=True`）；`test_keeps_unfinished_decision_*`；`test_keep_recent_rounds_protects_tail` |
| ② | `tool_result_clearing`：N 轮后一行结论，原文进 artifact | `tool_result_clearing()` 超 `keep_rounds` 轮工具结果 → 单行（含「已入 artifact」标记）；`clear_tool_results_to_artifact()` 异步落原文 + 流内留 `art://` 引用；幂等 | `test_old_results_to_one_line_recent_kept`（清 2 旧、留 1 新、单行、幂等）；`test_artifact_store_receives_original`（落原文 + ref） |
| ③ | 上下文使用率监控 + 阈值策略配置 | `measure_usage()` / `ContextUsageMonitor`（环形缓冲、水位告警）/ `ThresholdStrategy` / `plan_context_action()` / `apply_context_strategy()`（context_edit 优先 → 仍超才 compaction） | `test_measure_usage_fields`；`test_monitor_snapshot_and_ring_buffer`；`test_monitor_records_over_warn` |
| ④ | 验收：删 3×1500token→−4.5k 且前缀不变；超 N 轮→一行；超阈值→先 context_edit 后 compaction | 三项全量覆盖 | `test_removes_3_*`（`removed_tokens≈4.5k`、`prefix_stable`）；`test_old_results_to_one_line_*`；`test_over_threshold_context_edit_then_compaction_chain`（`chain==["context_edit","compaction"]` 且 `after_tokens<=阈值`） |

**测试结果**：`tests/test_contract_task96.py` **14 passed**；回归 `tests/test_contract_task26.py` **12 passed**（委派层签名/返回键零改动）；一并回归合计 **33 passed / 1 skipped**。

---

## 4. 交付物（task96 专属文件）

| 文件 | 性质 | 说明 |
|---|---|---|
| `edu-agent/app/ai/context_edit.py` | **新增（R4 权威模块）** | context_edit / tool_result_clearing / 前缀签名 / measure_usage / ContextUsageMonitor / ThresholdStrategy / plan·apply_context_strategy / clear_tool_results_to_artifact |
| `edu-agent/app/ai/compaction.py` | 修改（兼容委派层） | `context_edit`/`tool_result_clearing` 改为惰性委派到 `context_edit` 模块；新增公共原语别名（`msg_content`/`msg_tokens`/`is_tool_*`/`group_rounds`，供 `context_edit` 模块级导入，避免循环）；compaction 重量逻辑不变 |
| `edu-agent/app/config.py` | 修改（标注段，190–203 行） | 新增 `CONTEXT_*` 配置项，段头标注「【task96 新增段·R4】」与「【task96 新增段结束】」，避免与 task93/95 段冲突 |
| `edu-agent/tests/test_contract_task96.py` | **新增** | 14 个契约测试，覆盖 GWT ①②③④ + 监控 + 委派对称 |
| `test-reports/task96-completion-report.md` | **新增** | 本报告 |

**未触碰**：`edu-agent/app/mcp/`（task95）、`edu-agent/app/ai/skills/` 或 skills 相关（task93）。

---

## 5. config.py 新增配置项（task96 标注段，均可运维调参零改码）

```python
# 【task96 新增段 · R4 context editing 与上下文使用率监控】※ 本段为 task96 专属
CONTEXT_WINDOW_TOKENS: int = 32000        # 上下文窗口预算（使用率分母）
CONTEXT_USAGE_WARN_RATIO: float = 0.6     # 使用率告警水位，≥此比例记 warn 快照并打日志
CONTEXT_EDIT_ENABLED: bool = True         # 灰度开关；False → 跳过轻量编辑直接走 compaction
CONTEXT_EDIT_KEEP_RECENT_ROUNDS: int = 0  # 保护最近 N 轮工具对不被删（0=删除全部已完成对，兼容 task26）
CONTEXT_EDIT_DROP_REDUNDANT_REASONING: bool = True  # 顺带删除紧邻被删工具对的填充式中间推理
CONTEXT_STRATEGY_ORDER: str = "context_edit,compaction"  # 阈值策略顺序（轻量优先，重量兜底）
CONTEXT_USAGE_MONITOR_MAX: int = 50       # 使用率快照环形缓冲条数上限
# 【task96 新增段结束】
```
（既有 `COMPACTION_TOKEN_THRESHOLD=6000` / `COMPACTION_KEEP_ROUNDS=6` / `COMPACTION_REFRESH_THRESHOLD=3000` 仍由 task26 提供，task96 复用，未改动。）

---

## 6. 与 task97（R5 缓存监控）的衔接

- task96 的 `ContextUsageMonitor` 已提供 `snapshot()`（峰值水位、越水位次数、动作计数）与进程内默认监控器 `get_context_monitor()`，可作为 task97 缓存监控的观测入口，避免重复造轮子。
- 后续建议：task97 在 `/admin` 端点串联 `get_context_monitor().snapshot()` 与 prompt_cache 失效统计（`app/ai/prompt_cache.py` 的 `invalidations_list`），形成「上下文水位 + 缓存命中」联合看板。

---

## 7. 提交与同步纪律

- 单任务单提交：仅提交 task96 专属文件（`git read-tree --empty` 清空索引后精确 add 上表 5 个文件），不与 task93/95 混提交。
- 未调用 Workflow()（按并行纪律手动推进 dev-standard 各阶段）。
- 已运行 `sync.ps1` 同步远端（PowerShell 通道，非 Bash 内 powershell.exe）。
- **状态：已停下，等待编排（orchestrator）验收。**
