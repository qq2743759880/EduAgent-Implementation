# task-T1 完工报告 — 工具调用闭环（换参→换工具→熔断→人工指南）

> 执行工具：WorkBuddy（后端+数据库开发者）｜ 依赖：task33 / task92 / task96 / task-O1
> 修订来源：`.opencode/plans/production-upgrade-plan.md` P6（工具闭环仅重试 1 次）
> 状态：**完成，待验收**

## 一、验收标准达成（AC1~AC5）

| AC | 要求 | 落地 | 验证 |
|---|---|---|---|
| **AC1** 闭环升级 | 第1次正常→第2次换参→第3次换工具→第4次人工指南，不再"重试1次就回退" | `ToolRetryStateMachine` 四步决策 + `call_tool_with_retry` 编排 | 单测 `test_ac1_*`：第3步 switch_tool 成功返回，actions 顺序 `[execute_normal, rewrite_args, switch_tool]` |
| **AC2** 人工指南 | 全失败→结构化指南（问题描述/已尝试工具/手动步骤/联系管理员），非仅 need_search | `build_manual_guide()`，落 `MANUAL_GUIDE` 状态 | 单测 `test_ac2_*`：返回 dict 含 4 个必需字段 |
| **AC3** 拒绝计数熔断 | 同会话连续被拒 3 次→第4次中断回合，计数 Redis `mcp:reject:{session_id}` TTL=300 | `_RedisRejectCounter`（Redis 不可用时降级内存） | 单测 `test_ac3_*`：第2次同会话请求直接 `REJECTION_LIMIT` 且执行器 0 调用；成功则重置计数 |
| **AC4** 事件埋点 | 每步产出 `{attempt,action,tool_name,args,outcome,latency_ms}` + trace_id，落 `mcp_tool_call_log` | `_emit_retry_event`（task-O1 `retry` 事件）+ `_write_call_log` 终态落库 | 单测 `test_ac4_*`：3 条事件均含 6 字段 + trace_id |
| **AC5** 回归 | task33 既有契约全绿（per-server 熔断/只读缓存/审计） | `call_tool` 单步路径不动；新路径复用 `_execute_single_attempt` | `tests/test_task33_mcp_desc_review.py` **9 passed** |

## 二、改动文件清单

| 文件 | 改动 |
|---|---|
| `app/mcp/retry_loop.py` | **新增**。纯逻辑状态机 `ToolRetryStateMachine`、单步 `RetryStep` / `AttemptOutcome`、`RejectStore` 协议 + `MemRejectStore`、`build_manual_guide()` 模板。零 IO 依赖，可纯测。 |
| `app/mcp/executor.py` | 抽取 `_execute_single_attempt`（task33 行为不变）；新增 `call_tool_with_retry`（编排）、`_default_attempt_executor`、`_RedisRejectCounter` + `_make_reject_store`、`_emit_retry_event`、`_final_manual_guide` / `_final_rejection_limit`。`call_tool` 原样保留（AC5）。 |
| `app/mcp/schemas.py` | `ToolCallStatusEnum` 加 `REJECTION_LIMIT` / `MANUAL_GUIDE`；`MCPToolTestResp` 加可选字段 `attempt / actions / manual_guide / rejection_limited`（默认值，向后兼容）。 |
| `app/config.py` | task-T1 专属配置段：`TOOL_FALLBACK_MAP` / `MAX_TOOL_ATTEMPTS=4` / `TOOL_CONSECUTIVE_REJECTIONS=3` / `TOOL_REJECT_TTL_S=300` / `TOOL_RETRY_LLM_REWRITE=True`。 |
| `app/ai/graph.py` | `_build_tool_services.call_tool` 服务改调 `call_tool_with_retry`（注入 `session_id=thread_id, trace_id=thread_id`）。 |
| `tests/test_contract_task_t1.py` | **新增**。11 条契约测试（AC1~AC4 全覆盖，纯注入式无 DB/LLM/Redis）。 |
| `refactor_sql/task-T1-add-status-enum.sql` | **新增**。ALTER 扩展 `mcp_tool_call_log.status` 枚举（发布前于目标库执行一次）。 |

## 三、闭环路径实测（单测输出，11 passed）

状态机决策路径（original=`web_search`，fallback=`calculator`）：

```
attempt 1 → execute_normal   web_search
attempt 2 → rewrite_args    web_search   (LLM 改写 args，或规则跳级兜底)
attempt 3 → switch_tool    calculator   (TOOL_FALLBACK_MAP 第一个备用工具)
attempt 4 → 人工操作指南（GUIDE，停止）
```

- 第 3 步成功 → 返回 `SUCCESS`，`resp.attempt=3`，`actions` 含 3 条事件，`manual_guide=None`。
- 全部失败 → 返回 `MANUAL_GUIDE`，`actions` 含 3 步，`manual_guide` 结构化。
- 无 `session_id` → 仍受 `MAX_TOOL_ATTEMPTS` 约束，仅执行 3 步不无限重试。

## 四、拒绝计数熔断实测（AC3）

- 同会话第 1 次请求：3 步全拒 → `MANUAL_GUIDE`，计数累加到 3（Redis `mcp:reject:{sid}` 存 3，TTL 300s）。
- 同会话第 2 次请求：进入前检测到计数 ≥3 → **立即**返回 `REJECTION_LIMIT`，工具执行器 **0 次调用**，附带人工指南。
- 任一步成功 → 计数重置为 0（连续语义，对齐 Codex auto-review）。
- Redis 不可用时自动降级内存计数，闭环逻辑不崩（仅失去跨请求持久）。

## 五、人工操作指南输出样例（AC2，`build_manual_guide` 真实输出）

```json
{
  "problem_description": "工具「web_search」在闭环（最多 3 步：正常 → 换参数 → 换备用工具）尝试后仍不可用：tool not registered",
  "attempted_tools": [
    {"attempt": 1, "action": "execute_normal", "tool_name": "web_search", "outcome": "ERROR", "error_message": "isError: upstream 503"},
    {"attempt": 2, "action": "rewrite_args", "tool_name": "web_search", "outcome": "ERROR", "error_message": "isError: upstream 503"},
    {"attempt": 3, "action": "switch_tool", "tool_name": "calculator", "outcome": "ERROR", "error_message": "tool not registered"}
  ],
  "user_manual_steps": [
    "确认网络连通性，以及对应 MCP Server 是否在线（管理端 → MCP 服务 → 健康检查）。",
    "核对工具「web_search」的输入参数是否符合其 schema（参考上方『已尝试工具』中的参数）。",
    "若因权限/鉴权被拒，请确认当前账号是否具备该工具的调用权限。",
    "以上均无异常仍失败，请稍后重试，或改用人工方式完成该操作。"
  ],
  "contact_admin": "如为生产故障，请联系管理员排查 MCP Server 状态，或查看调用日志表 mcp_tool_call_log 获取完整错误。",
  "original_args": {"q": "北京天气"}
}
```

## 六、事件埋点样例（AC4）

每步经 `_emit_retry_event` 写入 task-O1 `retry` 事件（payload 含 `trace_id`）：

```json
{"attempt": 2, "action": "rewrite_args", "tool_name": "web_search",
 "args": {"q": "北京天气", "retry": 2}, "outcome": "ERROR",
 "latency_ms": 98, "error_message": "isError: upstream 503", "trace_id": "trace-xyz"}
```

最终态（指南/拒绝熔断）额外经 `_write_call_log` 落 `mcp_tool_call_log`（status=`MANUAL_GUIDE` / `REJECTION_LIMIT`）。

## 七、运维待办（非代码阻塞）

1. **DB 枚举 ALTER**：目标库执行 `refactor_sql/task-T1-add-status-enum.sql` 后，`MANUAL_GUIDE` / `REJECTION_LIMIT` 才能真正落库（本地单测用 mock 已验证写入调用；生产需先 ALTER，否则该行 INSERT 被 try/except 吞掉仅告警）。
2. **备用工具落地**：`TOOL_FALLBACK_MAP` 当前指向 `calculator` / `search_knowledge` 等名称；若对应 MCP 工具未在 `mcp_tool` 注册，第 3 步会判为失败并自然走向指南（安全降级）。后续可接子代理 `search_knowledge` 服务做真正的降级检索。
3. **LLM 改写**：仅"窗口内"生效；关闭 `TOOL_RETRY_LLM_REWRITE` 或 LLM 失败时自动回退规则跳级（原参透传，动作语义仍记 `rewrite_args`）。

## 八、测试汇总

```
tests/test_contract_task_t1.py         11 passed
tests/test_task33_mcp_desc_review.py    9 passed   (AC5 回归)
```

## 九、下一步

- 本任务已完成，等待验收。
- 验收通过后建议接 **task-S1（全流程 HITL 护栏 + AI 审查 AI）**——其高风险动作人工指南若涉及敏感操作可复用本任务的 `MANUAL_GUIDE` 结构过 HITL-Gate。
