# task27 完工报告：AI 助手 tool_specs 规范 + CoT/token 优化（prompt caching + 双模型）

> 后端｜阶段 P4.5｜类型 agent｜执行 Trae 手动调度（dev-standard.mjs 8 阶段）
> 前置：task24（LangGraph）、task25（三层记忆）、task26（compaction/guard）已验收｜后置：task29（联调评估）、task33（MCP 描述联动）
> 交付物：`app/ai/tool_specs.py` + `app/ai/decision_validator.py` + `app/ai/prompt_cache.py` + `agent.py` 决策层接线 + 契约测试（见 §6）

---

## 1. 背景与核心决策

task26 已验收 → 本任务按 tech-source-audit §二（R5 缓存三层组织；MCP 差描述浪费 40% → 五要素规范）落地 **tool_specs 规范 + CoT/token 优化 + prompt caching**：

- **ToolSpec 五要素**：`name / description / input_schema / risk(read|write) / parallel_safe / timeout_s / admin_only`，description 遵循「做什么 + 何时用/何时不用 + 参数域 + 返回结构 + 示例 + 副作用幂等」规范；进入 prompt 前按预算裁剪。
- **前缀稳定**：工具清单按 `name` 稳定排序 → 同输入前缀**逐字节一致**，命中前缀缓存。
- **精简 prompt**：原 `agent.py` 决策 prompt 约 800 token → 规则表化 `DECISION_SYSTEM_PROMPT`，system+工具清单 ≤300 token。
- **Pydantic 校验**：决策输出经 `DecisionPlan`/`AgentToolCall` 强类型校验，非法 → **重试 1 次** → 仍失败**保守回退**（`need_search=true` 检索兜底），不抛 500（GWT②）。
- **访问控制**：`admin_only` 工具不进入普通用户决策 prompt，仅 `is_admin=True` 注入（GWT③）。
- **并行执行**：`parallel_safe` 且无参数依赖的工具 `asyncio.gather` 并发（GWT③）。
- **缓存三层组织**：`system`（模型/静态规则）/`project`（MCP 工具清单）/`conversation`（摘要/上下文），内容变更记录失效原因（GWT④）。

**关键设计（本轮修正，独立审查子代理 R3）**：
`_compact_tools_in_budget` 初版只压缩 description 而**保留每条 input_schema**（大 body），前缀实测 410 token 无法达标；改为**三级确定性收敛**：① description ≤40 字 → ② 仍超则逐条移除 `input_schema`（决策前缀仅为意图/选工具，schema 校验由执行期 MCP 兜底）→ ③ 兜底压描述。压后 4 个普通工具前缀 286 ≤ 300，且逐字节稳定。

**环境说明**：本模块为**纯内存/纯函数**，无 external LLM / Redis 依赖，可直接单测，不受 Redis 可达性影响。

---

## 2. 验收标准逐条核验（GWT 精简版，全文见任务文档）

### ① ToolSpec 五要素齐全；system+工具前缀 ≤300 token、按 name 稳定排序、同输入前缀逐字节一致
**判定：✅ PASS**

- `ToolSpec` 七字段齐备且校验枚举（`risk ∈ {read,write}`）。
- `specs_from_metas` 把任意 tool meta（MCPToolItem 等）映射为 ToolSpec，内置同名工具优先用内置规范（含 admin_only/parallel_safe），未知工具默认 read/非并行。
- `build_decision_prefix`：先 `stable_sorted_specs` + `specs_for_access` 过滤 → 拼 header + 工具 JSON；超预算三级收敛到 ≤300。
- `measure_prefix_tokens` 复用 compaction 估计（保守偏大）。
- 契约测试：`test_prefix_token_budget_under_300`（实测 286）、`test_prefix_stable_sorted_and_byte_identical`（打乱输入两次构建 `==` 且 name 升序）。

### ② 非法 JSON 经 Pydantic 校验失败后只重试 1 次，仍失败则保守回退（现状 _safe_json_extract 语义），不抛 500
**判定：✅ PASS**

- `parse_decision_text`：`_extract_json_obj` 稳健提取（容忍 ```json 包裹/首尾噪音）→ `DecisionPlan`/`AgentToolCall` Pydantic 强类型校验，tool_plan 结构非法（缺 tool_name、非 list）→ `None`。
- `decide_plan_with_retry(query, llm_call, max_attempts=2)`：首次解析失败 → 重试 1 次 → 仍失败返回 `conservative_fallback(query)`（`need_search=true, query_rewrite=query`），meta 暴露 `retried/fell_back` 供监控断言。
- 契约测试：`test_invalid_json_retried_once_then_conservative`（非法×2 → calls==2、retried、fell_back、need_search=true）、`test_valid_after_one_retry_recovers`（第 2 次合法 → 不回退）、`test_pydantic_typed_tool_plan`、`test_malformed_tool_plan_returns_none`。

### ③ 两个 parallel_safe 且无依赖工具并发执行；admin_only 工具不进入普通用户决策 prompt（task33 联动验证）
**判定：✅ PASS**

- `run_parallel_tools(tool_plan, spec_of, call_tool)`：分并行组（`parallel_safe=True` 无依赖 → `asyncio.gather`）/ 串行组（非 safe/缺规范逐个执行），按输入序号回填结果。
- `specs_for_access(is_admin)`：普通用户前缀剔除 `admin_user_impersonate`/`admin_broadcast_message`，admin 视角注入。
- 契约测试：`test_two_parallel_safe_tools_run_concurrently`（0.3s×2 并发，实测 <0.5s，串行会 0.6s+；`parallel=True`）、`test_serial_for_non_parallel_safe`、`test_admin_only_excluded_for_regular_user`（普通不含 admin 工具、admin 含）。

### ④ 缓存按 system/project/对话三层组织，失效原因可记录
**判定：✅ PASS**

- 常量 `CACHE_LAYERS = ("system", "project", "conversation")`；key=sha256(content)。
- `PromptCache.set(layer, content, reason)`：同 key 命中态不失效；内容变化记录 `{ts,layer,reason,prev_key,new_key}`。
- `get` 计 hit/miss（供命中率监控）；`invalidate(layer, reason)` 显式失效（模型切换/effort/MCP 变更/compaction/升级场景）。
- `stats()` 输出逐层 hits/misses/hit_rate + 失效条数。
- 契约测试：`test_three_layers_and_hit`、`test_invalidation_reason_recorded_on_change`（mcp_tool_change ×2）、`test_explicit_invalidate_records_reason`（compaction）、`test_unknown_layer_raises`。

---

## 3. 独立子代理红线审查（R1-R5）

独立子代理（general_purpose_task）实跑 `pytest tests/test_contract_task27.py tests/test_agent_loop.py -q`（**25 passed, 0 failed**）并逐一读取 4 模块 + test，判定：

| 维度 | 判定 | 说明 |
|------|------|------|
| R1 数据一致 | ✅ PASS | `build_decision_prefix`/`specs_from_metas` 契约一致；`decide_plan_with_retry` 的 `DecisionPlan`/`AgentToolCall` 与 agent.py 消费字段（`.tool_name/.args/.need_search/.query_rewrite/.answer_direct`）对齐 |
| R2 安全 | ✅ PASS | admin_only 过滤使普通用户前缀不含管理工具；前缀仅暴露 name/描述/schema，不泄露 risk/admin 元数据或越权补漏 |
| R3 正确性 | ✅ PASS | GWT①②③④ 真实行为断言（`_SeqLLM` 注入真实字符串非 mock 假测）；初审发现唯一缺陷「scheme 未随预算裁剪致 410 token」已修复 |
| R4 健壮性 | ✅ PASS | 空工具/空 tool_plan/缺 tool_name/schema 为字符串均不崩不抛 500；未知缓存层抛受控 ValueError；LLM 异常优雅降级 need_search=true |
| R5 契约冻结 | ✅ PASS | 实现/配置（`TOOL_PREFIX_BUDGET=300`、`CACHE_LAYERS`、`max_attempts=2`）与 GWT 一致 |

**子代理修复**：仅 `app/ai/tool_specs.py` 的 `_compact_tools_in_budget`（预算收敛加 schema 裁剪 + 三级确定性顺序），其余模块无需改动。

---

## 4. 接线与变更文件

- 新增：`app/ai/tool_specs.py`（ToolSpec + 前缀 + 并行）、`app/ai/decision_validator.py`（Pydantic 校验 + 重试 + 回退）、`app/ai/prompt_cache.py`（三层缓存）、`tests/test_contract_task27.py`（15 契约测试）。
- 改写：`app/chat/flows/agent.py` `decide_agent_plan` — 改用精简前缀（`build_decision_prefix`）+ `specs_from_metas` + `decide_plan_with_retry`，新增 `is_admin=False` 参数（向后兼容）；移除 800 token 旧 `AGENT_DECISION_PROMPT` 与 `_format_tools_for_prompt`；`_safe_json_extract` 保留为导入兼容（委托 `_extract_json_obj`）。
- 既有 `tests/test_agent_loop.py` 10 测试无回归（决策层行为语义不变）。

## 5. 环境承载说明

本任务模块纯内存/纯函数，无 external LLM / Redis / Milvus 依赖，全部契约测试本地直接通过，无降级项。

## 6. 测试命令

```bash
cd edu-agent
& ".\.venv\Scripts\python.exe" -m pytest tests\test_contract_task27.py tests\test_agent_loop.py -q   # 25 passed
```

## 7. 交接与记忆

- 看板 task27 → DONE → `sync.ps1`。
- 后置：task29（评估）可复用 `measure_prefix_tokens` + `PromptCache.stats` 做缓存命中率监控；task33（MCP 描述联动）复用 `ToolSpec`/`specs_from_metas` 与 `admin_only` 注入。
- 已提交 git（message 含 task27），等待编排者验收（未验收不开始下一任务）。