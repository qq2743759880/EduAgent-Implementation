# task-C2 完工报告 — 缓存前缀达标（1024 门槛 + defer_loading + 填充注释 + 命中率 SEV）

> 执行者：后端+数据库开发者 ｜ 批次：W1 第一批 P0（与 task-M1 并行）｜ 关联：P7（production-upgrade-plan.md）
> 验收标准：AC1~AC5 ｜ 测试窗口纪律：真实 LLM 命中率实测仅窗口内（12:00-14:00/18:00-9:00），计量/SEV 逻辑用 mock 验证
> 提交：`（见文末 commit 指纹）` ｜ 基于最新 HEAD，单 commit，未用 `read-tree --empty`

---

## 0. 目标与竞品对标

原 `prompt_cache.py`（`build_decision_prefix`）把 system+工具清单压在 **300 token** 预算内 —— 远低于
DeepSeek/Claude **最小可缓存前缀 1024 token**（DEV 实证：低于门槛静默不缓存，两计数器恒为 0）。
同时工具 `input_schema` 直接进前缀 → 任一工具增删/描述重写即整层缓存失效。

本任务落地四点（对齐竞品实证）：

| 维度 | 竞品实证 | 本任务落地 |
|---|---|---|
| ① 填充达标 | Claude caching 1024 门槛；DEV 填充注释白嫖缓存 | `ensure_min_prefix` 静态注释撑到 ≥1024，逐字节稳定 |
| ② defer_loading | Claude Code defer_loading 工具存根保桩序稳定 | `to_prompt_entry(deferred=)` 只放 name+summary；`schema_registry` 按需展开 |
| ③ 锚定策略 | Glean 静态优先/不改 system/compaction 复用父前缀 | `anchor_guard` 闸门前缀永改 + 动态注入；`set_stubs` 按工具粒度失效 |
| ④ 命中率 SEV | Claude 把命中率当 uptime，低即 SEV | `evaluate_cache_sev` + `cache_meter` 按 {model,layer} 计量，<0.5 记 SEV |

---

## 1. 改动文件清单（12 文件）

| 文件 | 改动类型 | 内容 |
|---|---|---|
| `app/config.py` | 修改 | 新增 task-C2 配置段：`PROMPT_CACHE_MIN_TOKENS=1024` / `CACHE_FILLER_VERSION="v3"` / `TOOL_DEFERRED_MODE=True` / `CACHE_HIT_RATE_SEV=0.5` |
| `app/ai/tool_specs.py` | 修改 | `ToolSpec` 增 `summary` 字段 + `__post_init__` 派生稳定摘要；`to_prompt_entry(deferred=)`；`SCHEMA_REGISTRY`/`register_spec`/`expand_schema`/`build_tool_expansion_message`；`build_decision_prefix` 增 `deferred` 形参 |
| `app/ai/prompt_cache.py` | 修改 | 新增 `ensure_min_prefix` / `anchor_guard` / `set_stubs` / `evaluate_cache_sev` / `evaluate_hit_rate`；`set`/`invalidate` 失效事件加 `whole_layer` 标记 |
| `app/chat/flows/agent.py` | 修改 | `decide_agent_plan` 用 `build_decision_prefix(deferred=...)` + `ensure_min_prefix` 包裹决策 system 前缀（跨 1024 门槛，不改契约结构） |
| `scripts/eval/cache_meter.py` | 修改 | `build_big_prefix` 经 `ensure_min_prefix` 保证 ≥1024；新增 `evaluate_hit_rate`（委托 prompt_cache 单一真源）；`__main__` 窗口外走 mock 计量 |
| `tests/test_contract_task_c2.py` | 新增 | AC1~AC5 + 锚定闸门，共 19 用例 |
| `test-reports/task-C2-completion-report.md` | 新增 | 本报告 |

> 未触碰：`/me`、`/learning` 等既有契约结构；task27/95/97 源码（仅 `cache_meter.py` 扩展，向后兼容）。

---

## 2. AC1 填充达标（实测）

`build_decision_prefix` 仍保持 **≤300 token** 的精简决策前缀（GWT① 不回归）；`ensure_min_prefix` 在其上
**追加静态填充注释块**（system 层末尾、工具清单后，逐字节稳定）撑过 1024 门槛。

| 场景 | 原始前缀 (estimate_tokens) | 填充后 (estimate_tokens) | ≥1024 | 两次构建字节一致 |
|---|---|---|---|---|
| is_admin=False | 209 | **1042** | ✅ | ✅ |
| is_admin=True | 277 | **1110** | ✅ | ✅ |

- 填充块为固定文本 + 版本号 `v3`，**无时间/环境变量** → 同输入两次构建完全一致（实测 `byte_stable=True`）。
- 仅当 `estimate_tokens(prefix) < 1024` 时追加；已达标原样返回（`test_noop_when_already_above` ✅）。

---

## 3. AC2 defer 前缀稳定（实测）

- 决策前缀默认 `deferred=True`：工具桩只含 `{tool_name, description=summary}`，**不含 `input_schema`**。
- 场景：3 工具 → 重写 t2 完整 description（summary 不变）+ 新增 t4：
  - 既有 t1/t3 桩字节**零变化**（子串精确相等）✅
  - 仅新增 1 条存根，桩序按 name 升序稳定 ✅
- `PromptCache.set_stubs("project", ...)` 按工具粒度：
  - summary 不变的 description 重写 → `changed_tools=[]`、无失效事件；
  - 新增工具 → 记 `added`、**不记整层失效**；
  - 仅 `invalidate()` 显式清空才产生 `whole_layer=True` 整层失效事件（与"工具增删/重写不整层失效"对齐）。

> 关键：工具 schema 变更只影响 `schema_registry`（执行期展开），**永不进入前缀** → 前缀字节不变 → 缓存不失效。

---

## 4. AC3 schema 按需展开（实测）

- `build_decision_prefix(deferred=True)` 前缀中 **不含 `"input_schema"`** ✅。
- `build_decision_prefix(deferred=False, budget=10_000_000)`（full 模式 A/B）**含 `"input_schema"`** ✅。
- `expand_schema("calculator")` 从 `schema_registry` 返回完整 `ToolSpec`（含 `input_schema`）✅。
- `build_tool_expansion_message("calculator")` 生成 role=system 的"完整 schema 展开"消息，**进后续请求、不进前缀** ✅。
- 未知工具 `expand_schema`/`build_tool_expansion_message` 返回 `None`（退化到真实 MCP 兜底）✅。

---

## 5. AC4 命中率监控 + SEV（实测，mock 计量）

`evaluate_hit_rate(usage_list)` 从一组 `{prompt_cache_hit_tokens, prompt_cache_miss_tokens}` 计算：

| 用例 | 命中率 | SEV(<0.5) | level |
|---|---|---|---|
| 创建轮(miss) + 5 轮高命中 | **0.7778** | 否 | OK |
| 6 轮全未命中 | **0.0** | **是** | SEV |

- `cache_meter.py` 真实 LLM 路径（`meter()`）仅在测试窗口内执行；`__main__` 窗口外自动走 mock 计量示例（实测输出 `hit_rate=0.7844, level=OK`）。
- `CACHE_HIT_RATE_SEV=0.5` 可配：阈值调至 0.3 时 0.4 命中率不触发 SEV（验证阈值可配）。
- 指标按 `{model, layer}` 维度上报，供 task-O1 五维指标汇出（task-O1 未启动时本任务自包含）。

---

## 6. AC5 回归（实测）

| 测试集 | 结果 |
|---|---|
| `test_contract_task27.py`（tool_specs 规范 + 三层缓存） | **35 passed**（含 task95 合并跑） |
| `test_contract_task_c2.py` | **19 passed** |
| `test_contract_task97.py`（缓存监控） | **19 passed**（cache_meter 改动向后兼容） |

不回归项确认：决策前缀仍 ≤300 token、同输入逐字节一致、admin_only 隔离、`PromptCache` 三层组织 + 失效原因记录均保持。

---

## 7. 纪律遵守

- ✅ **纯增量 / 契约红线**：`build_decision_prefix` 签名向后兼容（新增 `deferred`/`budget`/`system_prompt` 可选形参），`/me`、`/learning` 响应结构未改动；`ensure_min_prefix` 为新增独立函数。
- ✅ **测试窗口**：真实 LLM 命中率实测（cache_creation/read 计数）需窗口内执行；本任务计量/SEV 逻辑已全部用 mock 验证，窗口内仅需跑一次 `python scripts/eval/cache_meter.py` 补真实 provider 计数。
- ✅ **git 基于最新 HEAD，禁 `read-tree --empty`**：单 commit，仅提交 task-C2 文件；prior-task 已 staged 文件未触碰。
- ✅ **一次一个 commit** → 运行 `sync.ps1` → 停下等验收。

---

## 8. 风险与下一步

1. **真实 LLM 命中率实测**：当前 17:xx 在窗口外，AC4 的真实 provider `cache_creation/cache_read` 计数需在 18:00-9:00 或 12:00-14:00 跑一次 `python scripts/eval/cache_meter.py`（rounds≥6）补证。
2. **`TOOL_DEFERRED_MODE=True` 生产影响**：决策 LLM 现仅见 name+summary（无 schema）。Claude Code 同此设计，但建议灰度观察决策准确率；如需回退设 `TOOL_DEFERRED_MODE=False`（full 模式，仍受 300 预算裁剪）。
3. **`schema_registry` 跨进程**：当前为进程内 dict，多实例各自注册。MCP 工具由 `specs_from_metas` 注册，进程重启后随首次会话重建；与 task-M2（Redis 共享）协同后可进一步跨实例一致。
4. **`CACHE_FILLER_VERSION` 升级**：变更填充文本会改前缀字节 → 触发一次整层缓存重建（预期内，仅版本升级时发生）。

---

## 9. Commit 指纹

- 分支：`feature/task44-courses`
- commit：`dcce826`（task-C2 单 commit；上一 HEAD `1f4e44b` = task-M1）
- 文件：见 §1（7 文件，1472  insertions）
- 本次提交仅含 task-C2 文件；prior-task 21 个已 staged 文件未触碰。
