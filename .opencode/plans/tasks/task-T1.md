# task-T1 — 工具调用闭环（换参→换工具→熔断→人工指南）

> 执行工具：**Trae** ｜ 依赖：task33, task92, task96（现状）+ task-O1 ｜ 状态：TODO
> 修订来源：`.opencode/plans/production-upgrade-plan.md` P6（工具闭环仅重试 1 次）
> 核心定位：把"重试 1 次就回退"升级为**闭环状态机**：第 1 次正常 → 第 2 次换参数 → 第 3 次换备用工具 → 第 4 次生成"人工操作指南"给用户并停止；叠加"拒绝计数熔断"（对齐 Codex auto-review 3 连续拒绝中断）。

## 1. 任务卡片

- **类型/工具**：backend（MCP 执行域） / Trae
- **依赖**：task33（`executor.py` 现状：per-server 熔断 + 只读缓存 + 审计日志）、task92（子代理 runner 的 tool 子代理调用链）、task96（tool result clearing）、task-O1（重试/熔断事件埋点基座）
- **并行组**：W3（第三批 P2，与 task-S1/R1 并行）
- **工作量**：**L**
- **测试窗口纪律**：闭环状态机纯逻辑随时可测；含 LLM 决策（是否换参/换工具）的集成仅窗口内

## 2. 选型依据（竞品实证，引用 production-upgrade-plan.md）

| 竞品 | 做法 | 参考 URL |
|---|---|---|
| **Codex orchestrator.rs** | approval → 选沙箱 → attempt → 沙箱升级重试（denied→无沙箱重试需新审批）→ sandbox_outcome telemetry | https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/orchestrator.rs |
| **Codex auto-review** | **3 连续拒绝/10 拒绝/50 轮 内熔断中断回合**；reviewer 代理决策；显式 override 路径 | https://developers.openai.com/codex/concepts/sandboxing/auto-review |
| **Codex retry telemetry** | `codex.retry` 事件带 attempt/delay/retry layer | https://github.com/openai/codex/pull/38452 |

## 3. 实现规划要点

### 3.1 闭环状态机（改造 `app/mcp/executor.py` + `app/ai/flows/agent.py`）

- 新增 `app/mcp/retry_loop.py`（或并入 executor）`ToolRetryStateMachine`：
  - 状态：`attempt=1 正常执行 → attempt=2 换参数（LLM 重写 args，fast 模型）→ attempt=3 换备用工具（`TOOL_FALLBACK_MAP`：如 web_search → calculator/内置检索；计算 → code_runner 兜底）→ attempt=4 生成人工操作指南并停止`;
  - 每步产出 `{attempt, action, tool_name, args, outcome, latency_ms}` 事件（供 task-O1 的 tool_result/retry 事件）；
  - 换参/换工具决策需 LLM（窗口内）；窗口外/LLM 失败直接跳级到 attempt=3（规则兜底）；
  - **人工操作指南 fallback**：工具全挂时输出结构化人工步骤（`MANUAL_GUIDE_TEMPLATE`：问题描述/尝试过的工具/建议用户手动操作步骤/联系管理员），不再仅 `need_search=True`。
- 备用工具映射配置：

```python
TOOL_FALLBACK_MAP = {
  "web_search": ["calculator", "search_knowledge"],
  "code_runner": ["search_knowledge"],
  "calculator": ["search_knowledge"],
}
MAX_TOOL_ATTEMPTS = 4
```

### 3.2 拒绝计数熔断（对齐 Codex auto-review）

- `executor.py` `_server_breaker` 增强：per-server 熔断保持（连续 5 失败 30s），新增**拒绝计数熔断**：
  - `TOOL_CONSECUTIVE_REJECTIONS=3`：同一会话内连续 3 次被工具拒绝（isError/权限拒绝）→ 中断该回合工具循环，转人工指南（对齐 Codex "3 连续拒绝熔断中断回合"）；
  - 计数存 Redis `mcp:reject:{session_id}`（TTL `TOOL_REJECT_TTL_S=300`），跨请求持久，防多轮反复打同一失败工具。
- 熔断事件写 `mcp_tool_call_log`（status 增加 `REJECTION_LIMIT`），供审计。

### 3.3 与子代理 runner 联动（task92）

- `app/ai/subagents/runner.py` 的 tool 子代理：`call_tool` 服务包装为闭环状态机调用（`app/ai/graph.py` `_build_tool_services` 的 `call_tool` 函数替换为 `executor.call_tool_with_retry`）；
- 子代理 maxTurns 与闭环 attempt 联动：attempt≥3 时子代理直接返回"工具不可用，建议人工操作"摘要，不再空转。

### 3.4 测试

- `tests/test_contract_task_t1.py`：状态机全路径（1→2→3→4 各动作断言）、换参 LLM mock 注入、拒绝计数熔断（3 次触发中断）、人工指南模板渲染、事件 payload 结构。

## 4. 验收标准（Given/When/Then）

- **AC1（闭环升级）**：Given 工具 X 首次调用失败，When 进入重试闭环，Then 第 2 次为换参数调用（args 被 LLM 改写或规则跳级）、第 3 次为备用工具调用、第 4 次输出结构化人工操作指南，全过程不再"重试 1 次就回退"。
- **AC2（人工指南）**：Given 所有可用工具均失败/熔断，When 状态机达到 attempt=4，Then 返回含「问题描述/已尝试工具/用户手动操作步骤/联系管理员」的结构化指南（非仅 need_search=True）。
- **AC3（拒绝计数熔断）**：Given 同一会话内工具被拒绝 3 次（isError/权限拒绝），When 第 4 次尝试，Then 该回合工具循环直接中断，计数存 Redis 且 TTL 生效，不反复打同一失败工具。
- **AC4（事件埋点）**：Given 闭环任意一步，When 执行，Then 产出 `{attempt, action, tool_name, args, outcome, latency_ms}` 事件且携带 trace_id（task-O1 消费），`mcp_tool_call_log` 落库含最终状态。
- **AC5（回归）**：Given task33 既有契约（per-server 熔断/只读缓存/审计日志），When 改造后运行，Then 全 PASS（原 5 次连续失败熔断行为保留）。

## 5. 交接与记忆

- **完工报告**：`test-reports/task-T1-completion-report.md`（闭环状态机路径实测、拒绝计数熔断验证、人工指南输出样例）。
- **记忆写入**：AI-Hub `trae-projects/EduAgent/project_memory.md` 追加"工具调用四步闭环 + 3 连续拒绝熔断"决策。
- **完成动作**：git commit → sync.ps1。

## 6. 批判承接

- **production-upgrade-plan.md P6**（工具闭环仅重试 1 次，工具全挂无 fallback）→ AC1/AC2/AC3 落实。
- **critique-backlog-tracker.md**：task31 批判①「AutoModel 重写打分 vs FlagReranker 语义等价性」间接相关（工具链路质量评估需闭环事件数据）；本任务事件埋点为 task32/39 提供工具成功率基线。

## 7. 与其他 task 关联

- **联动**：task-O1（tool_result/retry/sandbox_outcome 事件消费，5 维指标中的"工具调用成功率"）；task-G1（智能重试退避共用 `app/core/retry.py`，429/超时/模型错分流）；task-S1（写风险工具的人工指南若涉及敏感操作需过 HITL-Gate）；task-A1（harness 抽象的工具节点包装本状态机）。
- **执行顺序**：W3 第三批；依赖 task-O1 的事件基座，建议 O1 完成后实施。