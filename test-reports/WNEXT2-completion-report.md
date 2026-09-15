# W-NEXT-2 完成报告（写类工具上线 + 四道防线修复，P0）

> 执行者：W-NEXT-2 单写者（锁 `edu-agent/scripts/eval/wnext2.lock`，完工已删）
> 分支：`feature/opt-waves`；日期 2026-09-16；批判源：`test-reports/critique-blind-t4-t9.md`（T4-C1 / T4-C2 / T4-C3 / T4-C4 + T8-C1 / T8-C2）
> 环境：后端 8000 运行中（**未重启**，遵守红线）；验证用 **8010 临时实例**；契约 `contracts/reshape-r-aci.json` / `contracts/reshape-r-hitl.json` 未改（禁碰）；`app/chat/router.py`、`app/chat/sse.py`、`app/ai/hitl_gate.py`、`public/**`、`contracts/**` 未改。

## 0. 改动清单（文件归属内）

| 文件 | 改动 | 对应批判 / 步骤 |
|---|---|---|
| `edu-agent/app/ai/permission_gate.py` | `knowledge_import` 从 `CONTRACT_PENDING_TOOLS` 迁入 `TOOL_CLASS_MAP`=`admin_write`；补 `REGISTERED_BUILTIN_TOOLS`；新增 `WRITE_CLASSES`/`is_write_class`/`classify_tool_intent`/`resolve_role`/`gate_tool_call`/`build_denied_envelope`；docstring 注册面证据改 8 实物 / 9 挂起 | 步骤1 + 步骤3 / T4-C3 |
| `edu-agent/app/mcp/executor.py` | ① `_classify_hitl_action`/`_is_cached_call` 分类改走 permission_gate 单一事实源；② 新增 `_resolve_builtin_name`/`_execute_builtin_attempt`/`_make_builtin_hitl_exec`/`_knowledge_import_handler` 并注册 `knowledge_import`（925/926/927 行）；③ `call_tool`/`call_tool_with_retry` 写类纵深防御门 + `_permission_denied_resp` | 步骤1/2/3 / T4-C1、T4-C3、T8-C1 |
| `edu-agent/app/chat/tool_calling.py` | 流式预取路径接权限门：写类工具 `gate_tool_call` deny → 零 executor 调用、零落审计，ACI 三字段入 summary；只读路径不解析角色（零额外 IO） | 步骤2 / T4-C1 |
| `edu-agent/app/chat/flows/langgraph_agent.py` | `AgentState` 补 `tool_name/tool_args/query_rewrite/user_id/user_role` 等键（LangGraph 只为声明键建 channel，缺失即断链）；`_agent_tool_catalog()` 从注册面动态生成 prompt 工具清单；`_tool_result_text()` 修 denied/rejected 断链；`generate_node` 注入「无一次成功 → 禁完成态描述」诚实约束；兜底文案不泄异常类名 | 步骤2b / T4-C2、T4-C3、T8-C2 |
| `edu-agent/app/chat/flows/graph_stream.py` | 续流静默吞修复：Redis 有决策但图无挂起 → 显式收束（`hitl_rejected_no_pending` / `hitl_confirm_expired_no_pending`），绝不假装续跑 | 步骤4 / T8-C2 |
| `edu-agent/tests/test_permission_gate.py` | 按 8 实物 / 9 挂起重写矩阵与计数断言；新增 10 写类名分类 + 不缓存断言、knowledge_import 注册断言 | 步骤1/3 |
| `edu-agent/tests/test_wnext2_write_tools.py`（新增，13 用例） | W2-G2 / G3 / G4 / G6 集成测试 | 步骤2/3/4 |

未改（属其它工作流）：`app/chat/router.py`、`app/knowledge/importer/loader.py`（WNEXT10 F5-a）、`app/chat/service.py`（W-NEXT-9）、`app/domains/question_admin/router.py`（W-NEXT-5）。

---

## 1. W2-G1 统一工具分类单一事实源（T4-C3）

`executor._classify_hitl_action` 与 `_is_cached_call` 不再各写一份前缀判定，统一走 `permission_gate.classify_tool_intent` / `is_write_class`（`TOOL_CLASS_MAP ∪ CONTRACT_PENDING_TOOLS`），前缀判定仅作未登记名兜底。

| # | GWT | 实测 | 结论 |
|---|---|---|---|
| ① | 10 个写类工具名分类命中 `write_file` | `test_write_class_names_classified_and_not_cached[course_create/course_update/course_delete/question_create/question_update/question_delete/favorite_add/points_change/knowledge_import/order_create]` **10/10 PASSED**；`test_write_class_names_cover_10` PASSED | ✅ |
| ② | 写类工具 `_is_cached_call(...)==False`（禁缓存非幂等副作用） | 同上 10 用例内置断言 `_is_cached_call(...) is False` 全通过 | ✅ |
| ③ | 未登记名不误伤（保持既有 retry 语义） | `test_contract_task_t1*.py` / `test_contract_r12_tool_decision.py` 全绿（见 §6） | ✅ |

## 2. W2-G2 流式路径接权限门 + deny 断链修复（T4-C1 / T4-C2）

| # | GWT | 实测 | 结论 |
|---|---|---|---|
| ① | 写类 deny → **零 executor 调用**（不执行、不落审计） | `test_w2g2_stream_write_deny_zero_call_and_aci_envelope` PASSED（断言 `executor.call_tool` 调用次数=0） | ✅ |
| ② | deny 结果含 **ACI 三字段** | 同用例断言 `{code,message,action_hint} ⊆ envelope.keys()`；实测 `build_denied_envelope` 返回 `code="permission_denied"` + 面向用户 message + 可执行 `action_hint` | ✅（见 §7.1 信封超集观察项） |
| ③ | admin 写类放行 → 真实进 executor | `test_w2g2_stream_write_admin_allowed_calls_executor` PASSED | ✅ |
| ④ | 只读路径**不解析角色**（零额外 DB IO，不退化 T1 性能） | `test_w2g2_read_tool_path_does_not_resolve_role` PASSED | ✅ |
| ⑤ | executor 公共收口纵深防御 | `_permission_denied_resp`（`executor.py:123-146`）对 3 条执行路径（流式 / 六节点图 `call_tool_with_retry` / langgraph `tool_node`）统一拦写类，返回 ACI 信封内嵌 `content_text`，**不落审计、不进 HITL 队列** | ✅ |

## 3. W2-G3 knowledge_import 写类工具真实上线（T8-C1）

`knowledge_import` 在 `app/mcp/executor.py:935` 真实注册（`register_builtin_tool`，handler 包装既有 `knowledge.task_store.create_task`，task_type=`agent_import`，visibility∈{private,public}，tenant_id 以 `_EXEC_CONTEXT` 为权威），并按 §补登记流程迁入 `TOOL_CLASS_MAP="admin_write"` —— `admin_write` 类别**首次有实物**，`allowed ∧ risky` 不再是空集。

| # | GWT | 实测 | 结论 |
|---|---|---|---|
| ① | 注册面可命中（出处分明） | `test_registry_reconciliation_executor_source` / `_mcp_db` PASSED；注册面 = **8 实物**（内置 3：`calculator`/`search_knowledge`/`knowledge_import`；DB `mcp_tool` 5：`add`/`echo`/`list_alphabet`/`ping`/`sse_health`） | ✅ |
| ② | `audit_registry()` 三类差异**全空** | `test_registry_reconciliation_audit_clean` PASSED | ✅ |
| ③ | 挂起清单不含已注册名（防映射与实物脱节） | `test_registry_reconciliation_pending_absent_from_executor` PASSED（9 条挂起名在 executor 源码零命中） | ✅ |
| ④ | `TOOL_CLASS_MAP["knowledge_import"]=="admin_write"` + 仅 admin 放行 | `test_knowledge_import_is_registered_admin_write`、`test_matrix_real_write_tools_only_admin_allowed[knowledge_import]` PASSED | ✅ |
| ⑤ | 入参非法 → 零落库 | `test_w2g3_handler_argument_validation_no_write` PASSED | ✅ |

## 4. W2-G4 端到端实证

### 4.1 真实 HTTP（8010 临时实例）

命令（可复跑）：
```powershell
# 8010 临时实例（不动 8000）
Start-Process .\.venv\Scripts\python.exe -ArgumentList "-m","uvicorn","app.main:app","--port","8010"
.\.venv\Scripts\python.exe <探针脚本>   # 登录→ POST /api/mcp/tools/test
```

| # | GWT | 实测（原文摘录） | 结论 |
|---|---|---|---|
| ① | student 写类 → deny | `POST /api/mcp/tools/test` body `{server_id:23, tool_name:"knowledge_import", args:{title,visibility,url}}`，student(`user000001`) → **HTTP 403** `{"code":"40300","message":"角色无权限。当前角色=student，允许角色=['admin']","data":null}` | ✅ deny |
| ② | student 零落库 | `mcp_tool_call_log WHERE tool_name='knowledge_import'` = **0**；`knowledge_import_task`（近 10 分钟）= **0** | ✅ |
| ③ | admin → HITL pending（零执行） | 同 body，admin(`adm02test`) → **HTTP 200** `status="SKIPPED"`、`error_message="【HITL 待审批】高风险动作已挂起，等待人工/AI 审批。"`、`manual_guide={"hitl_action_id":"hitl-write_file-b28ee632ea9d","status":"pending","explain_text":…,"propose_text":…,"operator":"100003","trace_id":"p8-test-ee76ee9e7e17"}` | ✅ HITL 命中 |
| ④ | HITL 落库 | `hitl_approval` +1 行：`id=37, action_id=hitl-write_file-b28ee632ea9d, target=knowledge_import, action_type=write_file, risk_level=L2, status=pending, operator=100003`；**未执行任何导入**（`knowledge_import_task`=0） | ✅ |
| ⑤ | 测试数据自建自清 | `DELETE FROM hitl_approval WHERE target='knowledge_import'` → `deleted rows: 1`，复查 count=**0** | ✅ |

**诚实边界（必须记录）**：`/api/mcp` 整路由是 `require_role([ADMIN])`（`app/mcp/router.py:43`），故 student 的拒绝发生在**最外层路由 RBAC**，executor 写类门的 ACI 信封在该端点对非 admin **结构不可达**；ACI 信封的实证在 §2-②/⑤（工具结果通道）。另 `MCPToolTestReq` 契约只含 `tool_id/server_id/tool_name/args`，**不含 `hitl_decision`** → 经该端点无法做「确认」。

### 4.2 confirm → 执行（真实图，集成测试）

| # | GWT | 实测 | 结论 |
|---|---|---|---|
| ① | 挂起态零执行 + interrupt payload **五字段** | `test_w2g4_real_graph_interrupt_confirm_executes`：真实 `StateGraph(AgentState)` + 真实 `tool_node` + `InMemorySaver`；`set(v.keys()) == {"thread_id","tool_name","args","risk_level","timeout_s"}`、`tool_name="knowledge_import"`、`risk_level="high"`（admin_write→L3）、`timeout_s=300`、挂起阶段执行次数 **0** | ✅ |
| ② | confirm → 真实执行一次 | `Command(resume={"action":"confirm"})` → 执行次数 **1**、`args_kw is True`（`call_tool(args=…)` 关键字传参）、`hitl_decision is True`（不二次挂起） | ✅ |
| ③ | reject → 零执行 | `test_w2g4_real_graph_interrupt_reject_zero_exec` PASSED | ✅ |
| ④ | student → deny 且无 interrupt | `test_w2g4_real_graph_student_denied_no_interrupt` PASSED | ✅ |

### 4.3 续流静默吞修复（T8-C2）

`graph_stream` 续流前先探明图挂起态；无挂起 → 按 reject/confirm 分别显式告知「工具未执行、无任何数据变更」/「确认已失效」，并落 `degraded_reason=hitl_rejected_no_pending|hitl_confirm_expired_no_pending`。**不再把 `Command(resume=…)` 丢进无挂起图静默跑完**（用户以为「确认执行了」而实际零执行）。

## 5. W2-G6 幻觉式成功检测

| # | GWT | 实测 | 结论 |
|---|---|---|---|
| ① | 工具结果渲染不 `KeyError`（deny/rejected/无 result 三形态） | `test_w2g6_tool_result_text_never_keyerror[record0/1/2]` PASSED（deny → `[已拦截] …（action_hint）`） | ✅ |
| ② | generate prompt 注入诚实约束 | `test_w2g6_generate_node_injects_honesty_constraint`：无一次成功时 prompt 含「工具调用没有一次成功执行…严禁完成态描述」且含 `[已拦截] 权限不足，操作被拦截。` | ✅ |
| ③ | 图执行兜底不泄异常类名 | `test_t4c2_run_agent_fallback_no_exception_class_leak` PASSED（文案 `AI 服务异常，请稍后重试`） | ✅ |
| ④ | prompt 工具清单动态化（禁硬编码，防 LLM 宣称不存在的工具） | `_agent_tool_catalog()` 由 `REGISTERED_BUILTIN_TOOLS ∪ REGISTERED_MCP_TOOLS` 生成 | ✅ |

## 6. W2-G5 全量回归

| 套件 | 命令 | 结果 |
|---|---|---|
| 核心（3 文件） | `pytest tests/test_permission_gate.py tests/test_wnext2_write_tools.py tests/test_r11_hitl.py -q` | **119 passed** |
| 扩展（6 文件） | `pytest tests/test_contract_task_t1.py …_t1_fallback.py …_r12_tool_decision.py tests/test_wnext2_write_tools.py tests/test_permission_gate.py tests/test_r11_hitl.py -q` | **144 passed, 1 skipped** |
| 全量相关契约（14 文件） | `pytest tests/test_contract_task_s1.py tests/test_contract_task_s1_audit_fields.py tests/test_permission_gate.py tests/test_wnext2_write_tools.py tests/test_r11_hitl.py tests/test_chat_stream_error.py tests/test_sse_envelope_contract.py tests/test_contract_r12_tool_decision.py tests/test_contract_task_t1.py tests/test_contract_task_t1_fallback.py tests/test_agent_loop.py tests/test_contract_task24.py tests/test_contract_task_r02.py tests/test_contract_all_routers.py -q` | **215 passed, 1 skipped**（56.51s） |

`1 skipped` 为既有跳过项（非本次改动引入）。既有 `test_permission_gate.py` / `test_r11_hitl.py` / chat 契约测试**全绿，无回归**。

## 7. 观察项 / 变更单草案（涉非归属文件，**停手上浮**）

### 7.1 观察项①：deny 信封为契约必需字段**超集**
`build_denied_envelope` 实返 5 键（含 `tool_name`/`status`），`contracts/reshape-r-aci.json` 的 `error_envelope.shape` 为必需三字段 `{code,message,action_hint}`。**超集不违反契约**（必需字段齐全），测试按超集断言。若契约要求「恰好三字段」需另开变更单。

### 7.2 变更单草案 CR-WNEXT2-hitl-graph-unreachable（P0，涉 `app/ai/graph.py`）
- **事实**：生产流式主路径 `STREAM_VIA_GRAPH=True` → `flows/graph_stream.py` → `app/ai/graph.py::_ensure_agent_graph()` 的**六节点图**（`preprocess/route/skill/compact/context_edit/plan/fan_out/merge/reflect/answer`），`add_node` 列表中**无 tool/interrupt 节点**；`__interrupt__` 帧永不到达 → `pending_confirm` 事件与 `/api/chat/resume` 确认链路经 HTTP **结构不可达**（T8-C2 的另一半：确认无从发起）。
- **影响**：admin 经 `/api/chat/stream` 触发写类工具时只能得到「HITL 挂起」结果文本，**无法在会话内确认执行**。
- **归属**：`app/ai/graph.py` 不在本任务文件归属内 → **未改**，仅上浮。
- **建议**：①在六节点图 `skill` 节点后增加工具 interrupt 节点（复用 `langgraph_agent.tool_node` 的 interrupt 语义）；或②`graph_stream` 在写类挂起时直接发 `pending_confirm` 帧 + 写 Redis 挂起标记（不依赖图 interrupt）。

### 7.3 变更单草案 CR-WNEXT2-toolcatalog-source（P1，涉 `app/chat/tool_calling.py` 的 `list_enabled_tool_metas`）
- **事实**：LLM 工具规划的工具清单来自 `list_enabled_tool_metas()`，只查 DB `mcp_tool`（5 个只读工具）→ **内置工具（`calculator`/`search_knowledge`/`knowledge_import`）不进入 LLM 可选清单**，故 LLM 对话路径无法规划到 `knowledge_import`（写类门在流式路径已「接线」，但对内置写类工具无触发面）。
- **影响**：`knowledge_import` 目前**仅**经 `POST /api/mcp/tools/test`（admin）真实可达；对话式触达需先统一工具清单来源（同 §1「单一事实源」精神）。
- **归属**：`tool_calling.py` 在本任务归属内，但改清单来源会改变 LLM 可见工具集（行为面变更）→ 按纪律**不擅自扩大范围**，上浮待裁定。

### 7.4 观察项②：executor 只读缓存路径既有缺陷（**非本次引入**，`git diff` 可证）
`executor.py:646` `lambda: _run_once_cached().model_dump(mode="json")` 对**协程对象**调 `.model_dump` → 必抛 `AttributeError` 被 652 行 `except Exception` 吞掉 → 只读工具缓存**实际从未命中**，且 pytest 报 `RuntimeWarning: coroutine … was never awaited`。属 T1/task33 遗留，不在本任务 4 步骤内，未改。

## 8. 边界与未做

- 未改：`chat/router.py`、`chat/sse.py`、`ai/hitl_gate.py`、`public/**`、`contracts/**`（红线）；`chat/service.py`（W-NEXT-9）、`question_admin/router.py`（W-NEXT-5）。
- `map_stream_exception`（`sse.py`，禁碰）未改；已通过修根因（兜底文案不泄异常类名）规避 `type(exc).__name__` 泄出。
- 8010 临时实例仅用于本次实证，未触碰 8000。
- 契约测试的 `1 skipped` 为既有跳过项。

## 9. 附：登记回主表

- `REGISTRY_EVIDENCE` 与 docstring 的内置工具出处已统一为 **`executor.py:933/934/935`**（`register_builtin_tool` 实际行；此前误记 925/926/927，已校订），`test_registry_reconciliation_executor_source` 以源码正则实采复验通过。