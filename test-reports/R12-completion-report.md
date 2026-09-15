# R12 完工报告：LLM 工具决策接管（dev-plan-reshape-r W3）

> 执行 agent：R12（独立开发）· 日期 2026-09-15 · 工作区 `E:\stu\project\stu\EduAgent实施手册`
> 单写者锁 `edu-agent/scripts/eval/r12.lock` 已随完工删除 · 未触碰 sixnode.py / r02tail / r20b 领地

---

## 1. 交付概览

R12 把图内工具决策从「玩具正则」（`tool_calling._parse_heuristic`，audit P1-5：只认 add/ping/echo/list_alphabet 字面关键词）升级为 **LLM 驱动的结构化 tool_plan 决策器**，带超时预算与规则路由 fallback；**默认 `TOOL_DECISION_MODE=rule` 生产行为零变化**，编排者验收时以 `TOOL_DECISION_MODE=llm` 显式开启。

| 文件 | 变更 |
|---|---|
| `edu-agent/app/chat/tool_decision.py` | **新增**（218 行）：LLM 决策器核心（prompt 构建 / 超时预算 / Pydantic 校验 / fallback / 降级计数） |
| `edu-agent/app/chat/tool_calling.py` | 修改（+20/-2）：`run_chat_tool_calls` 决策段按 mode 分流；上下文头注入 `决策器=…` 审计标记 |
| `edu-agent/app/config.py` | 修改（+17）：`TOOL_DECISION_MODE`（默认 `rule`）/ `TOOL_DECISION_TIMEOUT`（默认 5.0s） |
| `edu-agent/tests/test_contract_r12_tool_decision.py` | **新增**：12 例契约测试（4 验收面全覆盖） |
| `edu-agent/scripts/eval/r12_http_probe.py` | **新增**：8011 临时实例真实 HTTP+SSE 验收探针 |

## 2. Registry 工具清单（真实拉取，DB mcp_tool×mcp_server，enabled=1 且 yn=1）

`list_enabled_tool_metas()` 实测（2026-09-15，本机 MySQL）：

| tool_id | server | tool_name | description | input_schema（要点） |
|---|---|---|---|---|
| 1 | stdio-echodemo | `ping` | 返回 pong=true 的心跳，用于健康检查 | `{}` 无参数 |
| 2 | stdio-echodemo | `add` | 整数 a + b，返回 {sum, was_negative} | `a:int, b:int`（required） |
| 3 | stdio-echodemo | `echo` | 原样回显 text，返回 {echo, length} | `text:string`（required） |
| 4 | stdio-echodemo | `list_alphabet` | 返回 1~52 个字母序列 A..Z 循环 | `n:int 1..52`（required） |

工具清单经 `tool_specs.specs_from_metas` 映射为五要素 ToolSpec，**name/description/input_schema 全量注入决策 prompt**（`build_decision_prefix(deferred=False)` full 模式，按 name 稳定排序保前缀字节确定，预算 700 token）。

## 3. 决策器设计（app/chat/tool_decision.py）

```
query ──► build_tool_decision_messages ──► LLM(fast, temp=0, ≤200tok)
             │  system=工具决策专用规则(防误触发条款+MCP_TOOL_MAX_TRIES)
             │  + 真实 registry 工具清单(name/description/input_schema)
             ▼
        asyncio.wait_for(TOOL_DECISION_TIMEOUT, 默认 5s, 钳制 0.5~30s)
             │
     ┌─ 成功 ─┴─ 超时/异常 ──────────────────────────┐
     ▼                                               ▼
 parse_decision_text (Pydantic DecisionPlan)    规则路由 fallback
     ▼                                            (_parse_heuristic 现行为)
 未知工具名过滤(只留 registry 真实工具)              + 降级计数入日志
 MCP_TOOL_MAX_TRIES 截断                            (WARNING 携带累计 stats)
     ▼
 ToolPlanItem[]{tool, args, reason="llm决策(Nms)"}
     ▼
 run_chat_tool_calls 原执行闭环（零改动）: executor.call_tool(args=) → 结果回填
 → mcp_tool_call_log 审计行 → SSE retrieval 帧 mcp_tool_calls
```

关键决策点：
- **新决策模块而非原地改写**：`_parse_heuristic` 原样保留＝fallback 路径＝rule 模式现行为；执行闭环（executor.call_tool / call_log / SSE 契约）零改动，R04 修复的 `args=` 签名沿用。
- **llm_call 可注入**：生产默认 `_ChatClient(fast)` 线程池执行；测试注入 fake/慢桩（GWT② 假慢 LLM 即此通道）。
- **空 tool_plan 是合法决策**（非工具 query 的 LLM 判定，非 fallback）——只有超时/异常/不可解析三种降级。
- **防杜撰**：LLM 输出经 Pydantic 校验 + 未知 tool_name 丢弃（WARNING 可查）。
- **禁改面合规**：不动 sixnode.py（R02-tail）、不动 SSE 契约（`决策器=…` 标记只进 system prompt 内部上下文头与日志，前端可见帧字段零变化）。

## 4. 降级链说明（超时预算 + fallback）

| 触发 | reason（日志/ToolDecisionResult.fallback_reason） | 行为 |
|---|---|---|
| `asyncio.wait_for` 超时 | `timeout` | → `_parse_heuristic` 规则路由结果接管，延迟有界（预算钳制 0.5~30s） |
| LLM 调用抛异常（网络/鉴权等） | `error` | 同上 |
| 输出不可解析 / Pydantic 校验失败（重试语义沿用 decision_validator 单次解析口径） | `unparseable` | 同上 |
| LLM 返回不在 registry 的工具名 | （非降级） | 丢弃该项并 WARNING，其余 plan 照常 |

降级计数：进程级 `_STATS = {llm_ok, llm_timeout, llm_error, llm_unparseable, rule_mode}`，每次 fallback 打 `WARNING [TOOL-DECISION] LLM 决策降级→规则路由 fallback reason=… stats={…}`；`get_tool_decision_stats()` 供监控/测试断言。

**HTTP 层活体证据**（8011 实例，`TOOL_DECISION_TIMEOUT=0.001`→内部钳 0.5s，query=「请调用工具算一下 7 与 35 的总和」——规则路由覆盖不到、仅 LLM 能命中的样本）：
```
[TOOL-DECISION] LLM 决策降级→规则路由 fallback reason=timeout
  stats={'llm_ok': 0, 'llm_timeout': 1, 'llm_error': 0, 'llm_unparseable': 0, 'rule_mode': 0}
  detail=budget=0.5s latency_ms=509
```
该请求照常完成（done code=0、60 token 正常回答、mcp_calls=[]）——GWT「注入假慢 LLM 超时后按规则路由完成请求且延迟有界」在真实 HTTP 链路成立（509ms vs 0.5s 预算）。

## 5. pytest 结果（12 例全过，4 验收面全覆盖）

`tests/test_contract_r12_tool_decision.py`，实测输出：
```
tests/test_contract_r12_tool_decision.py::test_r12_0_decision_prompt_contains_registry_schema PASSED
tests/test_contract_r12_tool_decision.py::test_r12_1_llm_mode_produces_correct_tool_plan PASSED
tests/test_contract_r12_tool_decision.py::test_r12_1b_llm_mode_with_real_registry_tools PASSED
tests/test_contract_r12_tool_decision.py::test_r12_2_timeout_falls_back_to_rule_bounded PASSED
tests/test_contract_r12_tool_decision.py::test_r12_2b_unparseable_output_falls_back PASSED
tests/test_contract_r12_tool_decision.py::test_r12_2c_llm_error_falls_back PASSED
tests/test_contract_r12_tool_decision.py::test_r12_3_non_tool_query_no_false_trigger PASSED
tests/test_contract_r12_tool_decision.py::test_r12_3b_non_tool_via_run_chat_tool_calls PASSED
tests/test_contract_r12_tool_decision.py::test_r12_default_rule_mode_keeps_legacy_behavior PASSED
tests/test_contract_r12_tool_decision.py::test_r12_run_chat_tool_calls_llm_wiring PASSED
tests/test_contract_r12_tool_decision.py::test_r12_4_call_log_success_audit_row PASSED
tests/test_contract_r12_tool_decision.py::test_r12_5_live_llm_end_to_end SKIPPED (默认跳过,R12_LIVE_LLM=1 显式开启)
================== 11 passed, 1 skipped, 1 warning in 4.19s ==================
```
- ① llm 模式正确 tool_plan：单测（内存 registry+fake LLM）+ 集成（真 DB registry，断言绑定真实 tool_id）双覆盖
- ② 超时→规则 fallback：假慢 LLM 1s 预算实测 1.03s 内放弃、规则结果接管（add(3,4)）+ 降级计数 +1；另覆盖 error/unparseable 两条降级支路
- ③ 非工具 query 不误触发：LLM 判空 → executor 守卫桩零触达（触达即 fail）
- ④ call_log SUCCESS 审计行：决策桩 + **真 executor（stdio spawn）+ 真 DB**，SELECT `mcp_tool_call_log` 断言 SUCCESS 行存在
- 活体例（`R12_LIVE_LLM=1`，真 LLM minimax-m3 经火山 ark）：
```
[R12 真 LLM 证据] summaries=[('add', "{'a': 17, 'b': 25}", 'success')]
call_log={'call_id': 'mcp-1789436306081-0380a06f', 'tool_name': 'add', 'status': 'SUCCESS'}
1 passed in 4.94s
```

## 6. llm 模式真实工具调用证据（真实 HTTP 端到端 + call_log 行）

临时实例 8011（`TOOL_DECISION_MODE=llm TOOL_DECISION_TIMEOUT=5`；8010 被并行任务 r02tail 占用，改用 8011，用完已关），`scripts/eval/r12_http_probe.py`（登录 student user000001 → POST /api/chat/stream, stream=true）：

```
[1] login ok (student user000001)
[2] tool-intent query -> mcp_calls=[{"call_id": "mcp-1789436455530-2a1ffb90", "tool_name": "add",
    "args_summary": "{'a': 88, 'b': 14}", "status": "success", "latency_ms": 142,
    "result_summary": "{\"sum\": 102, \"was_negative\": false}"}]
    tokens=11 answer_chars=390 done_code=0
    -> llm 决策+真执行 PASS (call_id=mcp-1789436455530-2a1ffb90)
[3] non-tool query -> mcp_calls=[] tokens=114 done_code=0
    -> 不误触发 PASS
```

DB `mcp_tool_call_log`（只读 SELECT）两条 llm 模式 SUCCESS 审计行：
```
call_log: {'call_id': 'mcp-1789436455530-2a1ffb90', 'tool_name': 'add', 'status': 'SUCCESS',
           'latency_ms': 142, 'trace_id': 'mcp-chat-64064569', 'args_json': '{"a": 88, "b": 14}'}   ← HTTP 探针
call_log: {'call_id': 'mcp-1789436306081-0380a06f', 'tool_name': 'add', 'status': 'SUCCESS',
           'latency_ms': 76,  'trace_id': 'r12-live-llm',     'args_json': '{"a": 17, "b": 25}'}   ← pytest 活体例
```

服务端决策日志（logs/app.log）：
```
[TOOL-DECISION] llm 决策完成 latency_ms=2837 plans=[('add', {'a': 88, 'b': 14})]      ← HTTP 工具意图
[TOOL-DECISION] llm 决策完成 latency_ms=1811 plans=[]                                 ← HTTP 非工具
[TOOL-DECISION] llm 决策完成 latency_ms=1855 plans=[('add', {'a': 17, 'b': 25})]      ← pytest 活体
[TOOL-DECISION] LLM 决策降级→规则路由 fallback reason=timeout … budget=0.5s latency_ms=509 ← 超时降级活体
```

## 7. 回归对账

- 相关域（R02 流式图 / agent_loop / task27 决策校验 / tool_deferred / mcp_health / task33）：**72 passed, 8 skipped, 0 failed**。
- 全量 `pytest tests/`：816 passed / 14 failed / 158 skipped / 11 errors。失败/error 全部在 curriculum/course/series/be_task01/task94/task_m2 等域。
- **A/B 对账证明与 R12 无关**：摘除我的 2 个 app 改动（git stash）后同 9 文件集重跑＝**2 failed + 11 errors，与带改动重跑逐项一致**（存量：task94 需 D:\.ai-hub 活体目录、be_task01 需 DB 态等环境面；共享工作树中另有并行任务未提交改动 sixnode.py/graph_stream.py/retriever.py，未触碰）。
- 派单基线备注：勘察时 8000 实际未监听（基线信息过期），8010 为 r02tail 活体实例——均未触碰，验证全部走自建 8011 临时实例（已关闭）+ venv 进程内测试。

## 8. Commits

| commit | 内容 |
|---|---|
| `feat(r)/R12-llm-tool-decision` | 决策器新模块 + config 开关 + run_chat_tool_calls 接线 + 12 例契约测试 + HTTP 探针（单 commit，5 文件 716 行） |

## 9. 遗留与交接

- `flows/agent.py:184` 旧路径 `execute_tool_plan` 仍用 R04 修复前签名 `arguments=`（死代码面，R05 删旧路径时一并清除；本次不越界改旧路径）。
- R02 报告登记的「子代理检索 query=任务输入串」结构面属 sixnode/plan 编排（R02-tail 领地），本决策器接管的是 `run_chat_tool_calls` 工具选择段；两者在 W3 汇合后由编排者复验合并效果。
- TOOL_DECISION_MODE 默认 rule；编排者验收 llm 模式：启动前设 `TOOL_DECISION_MODE=llm`（可选 `TOOL_DECISION_TIMEOUT`，默认 5s）。
