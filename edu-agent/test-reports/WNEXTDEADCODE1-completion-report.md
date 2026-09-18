# W-NEXT-DEADCODE-001 完成报告：chat 域死代码删除（审计 P1-6 / P1-3）

- 执行日期：2026-09-19；分支 `feature/opt-waves`
- **代码 commit：`fbd4d64`**（5 files changed, **+55 / -1139**，净 -1084 行）
- 上游任务登记：`.ai-hub/plans/audit-edu-chat-langgraph.md` §六 P1-3、P1-6（死代码登记节）
- 验收方式：编排者 C-01 逐断言独立实证（全仓 grep 调用链溯源 + pytest 双侧对比 + 真实 HTTP）

---

## 一、资产消费证据

| 资产 | 消费方式 |
|---|---|
| `.ai-hub/plans/audit-edu-chat-langgraph.md` | 全文读取；消费 §六 P1-3（execute_tool_plan 死代码）、P1-6（flows/langgraph_agent.py 500 行死代码 + user_id=1 越权面）登记；§1.1 架构图用于旁路链保护判定 |
| AGENTS.md | 遵守教训 2（禁 Playwright，接口验收走真实 HTTP）、教训 3（SSE 帧序与 `j.delta` 口径）、教训 8（真实契约优先）；启动命令采用其登记口径 |
| `contracts/reshape-a.json`（间接） | 经 `router.py:296-299` 与 `graph_stream.py` 模块注释确认 STREAM_VIA_GRAPH 旁路与 SSE 契约冻结面，全程未触碰 |

## 二、三分类清单（取证先行：全仓 grep 调用方 + 调用链溯源）

### 2.1 `app/chat/flows/langgraph_agent.py`（审计称整文件死代码 → **实测符号级分类，审计结论需修正**）

关键取证：审计（2026-09-13）称「无任何模块 import 它」已过时——R11/R15/W-NEXT-2 演进后 `graph_stream.py:223` 生产导入 `_hitl_risk_level`。因此**禁止整文件删除**，按符号切分：

| 符号 | 分类 | 证据 |
|---|---|---|
| `_hitl_risk_level` | **活（生产调用方）** | `graph_stream.py:223` `from app.chat.flows.langgraph_agent import _hitl_risk_level`（`_enrich_hitl_pending_payload` L227 消费）→ `run_chat_tool_calls(on_write_class_pending=...)`（graph_stream.py:368）→ `tool_calling.py:443-444`（六节点图无 interrupt 节点，写类挂起由流层承载）。测试引用：test_r11_hitl.py:70、test_permission_gate.py（归一双口径用例）、test_hitl_fix_integration.py HF-G2 |
| `agent_node / retrieve_node / tool_node / generate_node / router / build_agent_graph / agent_graph / run_agent` | 半死（测试+离线 eval 引用，生产零调用） | 全仓 grep：生产零调用（service.py:22 的 `run_langgraph_agent` 来自 `app.ai.graph`，非本文件）。引用仅：tests/test_wnext2_write_tools.py:32-33、tests/test_permission_gate.py:46-47、scripts/eval/harnesses.py:235（离线评测基线，见自批判 P0-1）。tool_calling.py:443 证明生产 interrupt 挂起不经过本文件 tool_node |
| `AgentState / _agent_tool_catalog / AGENT_SYSTEM_PROMPT / _parse_agent_output / _build_agent_messages / _tool_result_from_resp / _tool_result_text / after_action_router` | 半死 | 仅被上组死机器内部引用 + 测试引用（test_wnext2）。`after_action_router` 连文件内都零引用（build_agent_graph 用 add_edge 而非条件边） |
| **user_id=1 硬编码越权面（3 处）** | 随死机器删除 | 删除时实测行号：retrieve_node `int(state.get("user_id", 1) or 1)`（L274）、tool_node 同款（L451）、run_agent 默认参 `user_id: int = 1`（L626）。审计登记行号 239/283 为审计时点，文件其后被 R11/R15 演进过，以删除时实测为准 |

### 2.2 `app/chat/flows/agent.py :: execute_tool_plan`

| 项 | 结论 | 证据 |
|---|---|---|
| 生产调用方 | **零** | 全仓 grep `execute_tool_plan` 仅命中定义处（agent.py:151）+ tests/test_contract_task_o1_instrumentation.py:114,122。旁路链（service.chat_stream → run_agent_turn）工具执行走 `tool_calling.run_chat_tool_calls`，不经本函数；且 `RULE_ROUTING_ENABLED=True`（config.py 默认）时 decide_agent_plan 提前 return（agent.py:91-97），tool_plan 恒空 → 函数即使被调也是空转 |
| 分类 | **半死（仅测试引用）** | 同上 |
| 附属事实 | `record_tool_result` OTel 事件的全仓唯一生产者就在此函数内（agent.py:198,207）→ 该埋点契约点随主体退役（删除前它也只在死代码里触发，生产行为零变化），O1 测试同步退役，见 §四 |

### 2.3 保护对象核查（活代码零触碰）

- **STREAM_VIA_GRAPH 旁路（R05 冻结，禁删）**：`service.py:35 from app.chat.flows.agent import run_agent_turn`、`decide_agent_plan`、`generate_stream` 链全程未动（commit diff 仅 agent.py 的 execute_tool_plan 段 + docstring + import time）。
- **graph_stream.py（R02 主路径）**：零触碰（仅消费其 import 的 `_hitl_risk_level`，故保留）。
- **禁碰清单**：retriever.py / 子代理模块 / graph.py / app\core\*\* / config.py 开关 / breaker.py——commit 文件清单可证全部未沾。

## 三、删除清单（file:line 为删除前实测）

| 文件 | 删除内容 | 证据（生产零调用方） |
|---|---|---|
| `app/chat/flows/langgraph_agent.py` | L38-67 AgentState；L73-92 `_TOOL_CATALOG_CACHE`/`_agent_tool_catalog`；L95-131 AGENT_SYSTEM_PROMPT；L137-154 `_parse_agent_output`；L157-189 `_build_agent_messages`；L192-253 agent_node；L259-293 retrieve_node（**user_id=1 L274**）；L322-352 `_tool_result_from_resp`；L355-374 `_tool_result_text`；L377-461 tool_node（**user_id=1 L451**）；L467-545 generate_node；L551-560 router；L564-569 after_action_router；L575-617 build_agent_graph；L623 `agent_graph=…compile()`（导入即编译副作用一并消除）；L626-696 run_agent（**user_id=1 默认参 L626**）。**保留 L303-319 `_hitl_risk_level` + 新模块头说明** | §2.1 |
| `app/chat/flows/agent.py` | L147-211 execute_tool_plan（含段头注释）；L25 `import time`（仅其使用）；文档头 L10-12 补退役说明；段 3 改编号 2 | §2.2 |
| `tests/test_wnext2_write_tools.py` | 21 用例清理之一：W2-G4 三用例（死图 interrupt）+ `_compile_tool_graph`/`_state`/`_patch_executor_counter`；W2-G6 两用例（`_tool_result_text` KeyError 回归 + generate_node 诚实约束）+ `_FakeChatClient`；T4-C2 run_agent 兜底文案一用例；失效 imports（langchain/langgraph/lga）。保留 `_SettingsShim`（CR-1 活用例在用）与全部活路径用例 | 测试主体（tool_node/generate_node/run_agent/_tool_result_text）被删 |
| `tests/test_permission_gate.py` | G3 段六用例（tool_node deny/放行）+ `_build_state`/`_patch_executor`；G4 段四用例（run_agent 角色注入 + `_FakeGraph`/`_user_info`）。保留：`test_get_user_info_by_id_symbol_is_real_db_lookup`（活符号守护）、`test_norm_eliminates_case_whitespace_dual_criterion`（活符号 `_hitl_risk_level` 归一双口径） | 测试主体被删 |
| `tests/test_contract_task_o1_instrumentation.py` | `test_executor_emits_tool_result`（execute_tool_plan 埋点契约点，主体被删）；docstring 退役说明 | §2.2 附属事实 |

**统计（git numstat）**：agent.py +4/-70；langgraph_agent.py +17/-670；O1 测试 +9/-34；permission_gate 测试 +13/-190；wnext2 测试 +12/-175。**合计 +55 / -1139**。langgraph_agent.py 695 → 43 行。

## 四、回归证据（独立实证，非引用历史）

### 4.1 pytest（同口径双侧对比）

| 批次 | 基线（删除前） | 删除后 | 差异解释 |
|---|---|---|---|
| 受影响面 11 文件（O1/wnext2/permission_gate/r11_hitl/agent_loop/taskP1L/a1/e1/hitl_fix/chat_stream_error/chat_flow_args_fix） | **228 passed, 2 skipped** | **207 passed, 2 skipped** | -21 = 恰为本任务删除的用例数（W2-G4×3+W2-G6×4+T4-C2×1+G3×6+G4 角色注入×6+O1×1），**零意外失败、零意外 skip** |
| chat/HITL/R11/R02 宽面 15 文件（+chat_delete/chat_tool_calling/r12_tool_decision/task_r02/task_r02tail/tool_deferred_offline/llmswitch） | — | **236 passed, 3 skipped** | 3 skip 均基线遗留：R12_LIVE_LLM 环境门控×1、T8-C2 skip 标记×2（`-rs` 输出可复核） |
| 守卫/探针（wnextcheckdemohard2_guards/wnextint1a/wnextprobe1） | — | **59 passed** | — |

### 4.2 真实 HTTP（重启 8000 加载删除后工作区；脚本 `test-reports/_wnextdeadcode1_http_check.py` 可复跑）

```
[login] ok account=user000001
[non-stream] http=200 latency_ms=2120 → code=0 answer[52chars]='现在完成时表示过去发生的动作…have/has + 过去分词。' docs=5
[stream] http=200 text/event-stream → 帧序 start→retrieval→token×89→done
[stream] delta 累加 162 字符完整答案；done.data {code:0,message:"ok",latency_ms:3135,degraded_reason=None}；无 error 帧
ALL HTTP CHECKS PASSED
```

服务端日志交叉证据（logs/app.log）：`00:18:19 [graph_stream] 完成 thread_id=anon-2037… tokens=89 docs=5 node_arrivals_ms={route:24, skill:25, compact, context_edit, plan, fan_out:1091, merge, reflect, answer}` ——SSE 轮经 R02 graph_stream 主路径跑满九节点链；`app.chat.flows.agent:decide_agent_plan` 规则决策命中日志证明旁路活链同场可用。

## 五、P0 自批判（4 条）

1. **scripts/eval/harnesses.py `run_baseline` 遗留潜伏断点（未修——文件归属受限）**：`run_agent` 删除后 `base.run_agent(...)`（harnesses.py:235）将 AttributeError；被 run_baseline 的 `try/except Exception` 捕获记为 `res.error`，replay.py:167 的 baseline 模式不崩但产出全 error 结果。harnesses.py/replay.py 不在本任务文件归属白名单（langgraph_agent.py/确证死的兄弟文件/tests 对应用例/报告），未越权改动。pytest 不受影响（A1 AC5 仅测 sixnode；E1 仅断言 importable+run_sixnode）。**移交建议**：eval 资产属主任务退役 baseline harness 或重指基线（task29 对比已收口，baseline 的历史使命已终结）。
2. **O1 埋点契约点 2 是「随主体退役」而非「迁移」**：`tool_result` OTel 事件全仓唯一生产者就在被删的 execute_tool_plan 内；删除后生产代码不再产生该事件类型（与删除前生产行为一致——它本来就只在死代码里触发）。若存在预期该事件的下游报表/告警，需知悉。未给活路径（tool_calling/executor）补埋点：改 mcp/executor 越归属且改变生产行为，应属独立任务决策。
3. **测试清理 -21 用例中，「图内 interrupt()→Command(resume)→hitl_decision=True 传递」的 R11 原始机制测试模板随之消失**：活路径等价覆盖存在（HF-G2 五字段 via graph_stream._enrich；CR-1 流层挂起/放行），且该机制在活代码中已不可达（tool_calling.py:443 六节点图无 interrupt 节点），删除正确；但若未来六节点图恢复 interrupt 节点，无现成测试模板（需 git 考古 fbd4d64^）。
4. **回归环境含并行 agent 未提交 WIP**（memory/queue+service、subagents、retriever、chat/service.py、config.py、edu-frontend 为其他在跑任务的修改）：pytest 与 HTTP 实证均在含 WIP 工作区执行，基线/删除后为同一工作区故对比口径一致；本 commit 仅含本任务 5 文件，未沾他人 WIP（`git status` 中其余 M 文件保持未提交，归属各自任务）。

## 六、批判承接核对

**无承接项**。核对方式：`grep -n "DEADCODE" .ai-hub/plans/critique-tracker-v1.md` 零命中——上游对本任务无待承接批判；本任务上浮的 4 条自批判见 §五（第 1 条为移交建议，非本任务可闭合项）。

## 七、红线合规

- 文件归属：仅动 `app/chat/flows/langgraph_agent.py`、`app/chat/flows/agent.py`（execute_tool_plan 死路径，随本任务报备）、tests 三文件、本报告；lock `scripts/eval/wnextdeadcode1.lock` 已按规约 commit 前删除。
- 禁碰清单零触碰：retriever.py（R-N2 在跑）、子代理模块（R12 在跑）、graph.py、app/core/**（含 R-M1 breaker.py）、config.py 开关、graph_stream.py、service.py。
- user_id=1 越权面（审计 P1-6 后半）随死机器 3 处全数消除；`app/ai/permission_gate.py` 中提及本文件的注释（:180/:297/:326）所指符号 `_hitl_risk_level` 保留，注释仍然成立。
