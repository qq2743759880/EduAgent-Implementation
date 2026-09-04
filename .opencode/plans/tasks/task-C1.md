# task-C1 — 上下文动态压缩（token 预算分配器 + 锚定闸门）

> 执行工具：**Trae** ｜ 依赖：task26, task96（现状） ｜ 状态：TODO
> 修订来源：`.opencode/plans/production-upgrade-plan.md` P4（上下文压缩固定丢轮）
> 核心定位：把 `compaction.py` 从"固定保留最近 6 轮"改为 **token 预算分配器 + LLM 动态选片段**，加 **锚定闸门** 保护前缀缓存——用户第 7 轮问"第 3 轮数据"不再被压掉。

## 1. 任务卡片

- **类型/工具**：backend（AI 上下文管理） / Trae
- **依赖**：task26（`compaction.py` 现状：context_edit + tool_result_clearing + compact_messages）、task96（R4 context editing 已落地）
- **并行组**：W2（第二批 P1，与 task-G1/O1 并行）
- **工作量**：**L**
- **测试窗口纪律**：LLM 决策片段（预算分配器选片段）仅窗口内跑；规则回退路径随时可测

## 2. 选型依据（竞品实证，引用 production-upgrade-plan.md）

| 竞品 | 做法 | 参考 URL |
|---|---|---|
| **Codex** | token 预算分配器：系统 10%/用户问题 20%/工具结果 30%/历史 40%，LLM 动态决定保留哪些历史片段 | production-upgrade-plan.md P4 引述 + Codex 压缩（SQLite 会话持久化） |
| **Claude compaction** | 服务端 compaction 阈值触发（≥50K token），保留架构决策/未决问题/关键事实，丢弃冗余；支持自定义 compaction prompt；min 50K token | https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools |
| **Claude 锚定策略** | System+工具固定前缀永久缓存；只删闸门后的工具调用日志（tool-result clearing） | https://code.claude.com/docs/en/prompt-caching |

## 3. 实现规划要点

### 3.1 token 预算分配器（改造 `app/ai/compaction.py`）

- 新增 `BudgetAllocator`（纯函数，确定性可测）：
  - 默认预算比例对齐 Codex：`SYSTEM=10% / USER_QUERY=20% / TOOL_RESULT=30% / HISTORY=40%`（配置 `COMPACTION_BUDGET_RATIOS`）；
  - 输入：消息流（按 `_group_rounds` 分组）+ 总预算阈值 `COMPACTION_TOKEN_THRESHOLD`；
  - 输出：每轮保留预算上限 dict + 候选片段清单；
  - 保留规则升级：**非按轮截断**——`_group_rounds` 后逐轮打标签（round_id/role/是否含决策关键字/是否工具对），预算分配器先满足高价值轮（含 `决策/待办/偏好/目标` 关键词、用户问题、未完成工具决策），再按预算填历史片段。
- 新增 `llm_select_fragments(messages, budget_alloc)`：**LLM 动态选片段**（fast 模型，输出 `{"keep_round_ids":[...]}`）；失败/窗口外回退 `_default_structured_summary`（规则确定性，现路径不变）；A/B 对比旧 4 键 JSON：保留轮内结构 + 摘要键，输出仍兼容 `{summary_json, kept_messages}` 契约（graph.py `compact_node` 零改动消费）。
- `compact_messages()` 内部：先 `context_edit`（轻量，保留）→ 仍超 → `budget_alloc` 计算 → LLM 选片段（或规则回退）→ 组装 summary + 选中轮原文。

### 3.2 锚定闸门（保护前缀缓存）

- 新增 `anchor_gate(messages, anchor_round)`：在对话第 `ANCHOR_ROUND=3` 轮焊死闸门（配置）；闸门前（System + 核心决策轮 + 工具前缀）**永不修改**，闸门后工具日志可压缩/可清；
- 与 task-C2 联动：闸门前内容即"可缓存前缀"，任何压缩操作不得改动闸门前字节（对齐 Claude 锚定策略 + Glean "静态优先动态最后"）。
- 新增 `tool_result_clearing` 增强：已实现 N 轮后一行结论（task96），补"闸门前工具结果永不精简"边界（保前缀稳定）。

### 3.3 配置项

```python
COMPACTION_BUDGET_RATIOS = {"system": 0.10, "user_query": 0.20, "tool_result": 0.30, "history": 0.40}
ANCHOR_ROUND = 3                       # 锚定闸门轮数
COMPACTION_LLM_SELECT = True           # LLM 动态选片段开关；False=规则回退
```

### 3.4 测试

- `tests/test_contract_task_c1.py`：预算分配器比例守恒（Σ=1.0）、LLM 选片段 mock 注入、锚定闸门前字节不变、A/B 对比报告（固定 6 轮 vs 动态选片段的"第 3 轮数据可召回率"）。

## 4. 验收标准（Given/When/Then）

- **AC1（预算守恒）**：Given 任意消息流，When 运行 `BudgetAllocator.allocate()`，Then 各类型预算占比之和=100%，且每类型分配 token ≤ 其比例 × 总阈值。
- **AC2（动态选片段召回）**：Given 对话 10 轮（第 3 轮含关键数据、其余为冗余工具结果），When 压缩（LLM 选片段路径，窗口内），Then 压缩后 kept_messages 包含第 3 轮原文，用户后续问"第 3 轮数据"可完整作答；与固定 6 轮基线对比报告显示召回率提升。
- **AC3（规则回退等价）**：Given LLM 选片段不可用（窗口外/mock 失败），When 压缩，Then 回退规则 `_default_structured_summary`，输出 4 键 JSON 与旧版逐键兼容，压缩后 ≤ threshold。
- **AC4（锚定保护）**：Given 对话第 1~3 轮为 System+核心决策+工具前缀，When 执行任意压缩策略（context_edit/clearing/compaction），Then 闸门前消息字节零改动，缓存前缀不变。
- **AC5（回归）**：Given task26/task96 既有契约测试，When 改造后运行，Then 全部 PASS（`compaction_policy`/`needs_recompaction` 行为不变）。

## 5. 交接与记忆

- **完工报告**：`test-reports/task-C1-completion-report.md`（A/B 对比数据、锚定闸门字节校验、规则回退实测）。
- **记忆写入**：AI-Hub `trae-projects/EduAgent/project_memory.md` 追加"压缩非按轮截断：预算分配器 + 锚定闸门"决策。
- **完成动作**：git commit → sync.ps1。

## 6. 批判承接

- **production-upgrade-plan.md P4**（上下文压缩固定丢轮）：用户第 7 轮问第 3 轮数据被压掉 → AC2 落实。
- **critique-backlog-tracker.md**：task29 批判③关联「缓存命中实际落地」——本任务锚定闸门保证压缩不破坏前缀，配合 task-C2 的缓存命中监控形成闭环。

## 7. 与其他 task 关联

- **联动**：task-C2（锚定闸门共享前缀稳定语义，prompt_cache 的 conversation 层失效原因需含"压缩跨闸门"检测）；task-O1（压缩效率指标：压缩前后 token、丢轮数、锚定命中数）。
- **执行顺序**：W2 第二批；task96 已提供 context_edit 基础，本任务在其上叠加预算分配器与闸门。