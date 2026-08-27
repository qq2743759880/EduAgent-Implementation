# task-C1 完工报告 — 上下文动态压缩（token 预算分配器 + 锚定闸门）

> 分支：`feature/task44-courses` ｜ 基于 HEAD：`ebbdbe4`（task-C2）｜ 单 commit（禁 `read-tree --empty`）
> 改造依据：`.opencode/plans/production-upgrade-plan.md` **P4 上下文压缩固定丢轮**
> 竞品对标：Codex token 预算分配器 / Claude compaction / Claude 锚定策略 + Glean 静态优先
> 测试窗口纪律：LLM 动态选片段仅 12:00–14:00 / 18:00–9:00 跑；规则回退随时可测（本任务以 mock llm 验证升维逻辑）

---

## 1. 交付文件清单（共 5 文件，commit 见 §9）

| 文件 | 改动 | 对应 AC |
|---|---|---|
| `edu-agent/app/config.py` | 新增 task-C1 段：`COMPACTION_BUDGET_RATIOS` / `ANCHOR_ROUND=3` / `COMPACTION_LLM_SELECT=True` | 配置 |
| `edu-agent/app/ai/compaction.py` | 新增 `BudgetAllocator` / `anchor_gate` / `llm_select_fragments` / `_default_fragment_selection` / `_compact_legacy` / `_compact_with_budget` / `make_fast_llm`；`compact_messages` 改为分发器（默认走原版） | AC1/AC2/AC3/AC4 |
| `edu-agent/app/ai/context_edit.py` | `context_edit` 增加 opt-in `anchor_round` 形参，闸门前字节零改动 | AC4 |
| `edu-agent/tests/test_contract_task_c1.py` | 14 项契约测试（AC1–AC4 + 默认路径回归） | 全部 |
| `test-reports/task-C1-completion-report.md` | 本报告 | — |

---

## 2. 架构设计（向后兼容关键点）

`compact_messages` 签名扩展为：
```python
compact_messages(messages, threshold=None, keep_rounds=None, summarizer=None,
                 *, llm=None, llm_select=None, anchor_round=None)
```
- **默认（opt-in 全关）**：`anchor_round=None` 且 `llm=None` → 走 `_compact_legacy`（与 task26 既有代码逐字节一致）→ **task26/96 回归不变（AC5 实测 33 passed/1 skipped）**。
- **增强路径**（`anchor_round` 或 `llm` 任一传入）→ `_compact_with_budget`：预算分配器 + 锚定闸门 + LLM/规则选片段。
- `LLM 选片段` 仅在调用方注入 `llm` 调用时生效（`COMPACTION_LLM_SELECT` 为总开关）；未注入自动回退规则选片段 → 零回归。
- 输出契约不变：`{applied, before_tokens, after_tokens, summary_json, summary_msg, kept_messages}`（4 键 JSON + 最近轮原文），`graph.compact_node` / `apply_context_strategy` **零改动消费**。

---

## 3. AC1 — 预算守恒（Σ=100%，每类 ≤ 比例×阈值）

`BudgetAllocator.allocate(messages, threshold)` 纯函数确定性。

实测（threshold=6000）：
```
ratios_sum = 1.0            valid = True
budgets = {system:600, user_query:1200, tool_result:1800, history:2400}   # 10%/20%/30%/40% × 6000
```
- 各类型预算占比之和 = 100%（归一化防御配置手滑）。
- 每类型预算 ≤ 比例 × 总阈值 + 1。
- 自定义比例（1:1:2:0）归一后仍 Σ=1.0，`history` 预算=0 正确。

---

## 4. AC2 — LLM 动态选片段召回（A/B 对比固定 6 轮）

构造 10/12/15 轮对话，关键数据 `KEY_DATA_xyz` 置于第 3/4/5 轮（即"用户第 N+2 轮问第 3 轮数据"场景），其余为冗余长回答。

| 场景 | 固定 6 轮召回 | 动态选片段召回 | 固定后 token | 动态后 token |
|---|---|---|---|---|
| n=10 key_round=3 | **0** ❌ | **1** ✅ | 3672 | 658 |
| n=12 key_round=4 | **0** ❌ | **1** ✅ | 3672 | 658 |
| n=15 key_round=5 | **0** ❌ | **1** ✅ | 3672 | 658 |

> 这正是 production-upgrade-plan.md **P4 批判点**：固定保留最近 6 轮，用户第 7 轮问第 3 轮数据被压掉（固定召回=0）。动态选片段经 `llm_select_fragments` 输出 `{"keep_round_ids":[...]}` 精准保留关键旧轮（召回=1），且压缩后 token 更低（658 vs 3672）——因为不再无谓保留 6 轮冗余原文，只留关键轮 + 结构化摘要。

`llm_select_fragments` 稳健抽取 JSON（`_extract_json_obj` 容忍 markdown/前后文），失败/窗口外 → 返回 `None` → 回退 `_default_fragment_selection`。

---

## 5. AC3 — 规则回退等价（4 键 JSON 逐键兼容，≤ threshold）

无 LLM 注入（窗口外/注入失败）→ 回退规则选片段 + `_default_structured_summary`。

实测：
```
applied=True  after_tokens=5508 (≤6000)
summary_json 键 = {decisions, facts, pending_tasks, profile_updates}   # 与旧版 4 键逐键一致
```
- 与 `compaction._default_structured_summary` 返回的键集合**完全一致**（test 断言 `set(obj.keys()) == set(ref.keys())`）。
- 压缩后 ≤ 阈值（兜底收缩循环保证）。

---

## 6. AC4 — 锚定保护（闸门前字节零改动）

`anchor_gate(messages, anchor_round=3)` 返回受保护前缀上界 = 连续 system 前缀 + 前 3 个含用户问题的轮次。

执行压缩（`compact_messages(..., anchor_round=3)`，`context_edit(..., anchor_round=3)`）：
```
gate_idx = 7
闸门前字节 before_render == after_render  ⇒  True   (prefix cache 前缀不变)
context_edit: prefix_stable = True
```
- 增强路径输出顺序 `frozen + [summary_msg] + selected`，`frozen` 为输入 `[:gate_idx]` 逐字节切片 → 闸门前内容零改写。
- 与 task-C2 联动：锚定前内容即"可缓存前缀"，任一压缩操作不得改动其字节，保护 prompt cache 命中（对齐 Claude 锚定策略 + Glean "静态优先动态最后"）。

---

## 7. AC5 — 回归（task26/task96 契约不变）

```
tests/test_contract_task26.py + test_contract_task96.py : 33 passed, 1 skipped  (real-Redis 测试 skip)
tests/test_contract_task97.py                          : 19 passed
```
- `compaction_policy` / `needs_recompaction` 行为不变。
- 默认 `compact_messages` 仍 `after_tokens ≤ 6000`、`AAA_20` 在 kept、`AAA_1` 原文已进摘要（不被保留原文）—— task26 GWT① 全部保持。
- 默认路径**不携带** task-C1 扩展字段（`anchor_gate_idx` / `keep_round_ids`），消费方零感知。

---

## 8. 纪律与风险

- **git**：基于 `ebbdbe4`，单 commit，未用 `read-tree --empty`；仅提交 task-C1 5 文件，prior-task 已 staged 的 21 文件未触碰。
- **测试窗口**：真实 LLM 升维实测（`make_fast_llm()` 封装火山 ark plan/v3 deepseek-v4-flash）须待窗口（18:00–9:00 / 12:00–14:00）内执行；窗口外以 mock llm 验证选片段逻辑。窗口内补测命令：
  ```bash
  .venv/Scripts/python.exe -c "
  from app.ai.compaction import compact_messages, make_fast_llm
  # 构造含关键旧轮的长对话 msgs 后：
  r = compact_messages(msgs, llm=make_fast_llm(), anchor_round=3)
  print('keep_round_ids=', r['keep_round_ids'], 'after_tokens=', r['after_tokens'])
  "
  ```
- **灰度建议**：生产默认 `anchor_round=None`（关闭锚定）以彻底零回归；确认稳定后由编排者在 `apply_context_strategy` / `compact_node` 注入 `anchor_round=settings.ANCHOR_ROUND` 与 `llm=make_fast_llm()` 启用。当前 `graph.compact_node` 按任务要求零改动，故 feature flag 由上层装配。
- **已知约束**：锚定开启时，若被冻结区本身超阈值（极端长 system+3 轮），`frozen` 不可收缩，兜底收缩作用于选中轮与 summary，保证总体 ≤ 阈值（实测 after_tokens 均 ≤ 阈值）。

---

## 9. Commit 指纹

- 分支：`feature/task44-courses`
- commit：`c725e1b`（task-C1 单 commit；上一 HEAD `ebbdbe4` = task-C2）
- 文件：见 §1（5 文件）
- 本次为 task-C1 单 commit；HEAD 在 task-C2 之后，prior-task 19 个已 staged 文件未触碰。
