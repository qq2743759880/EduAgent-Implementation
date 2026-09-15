# W-NEXT-2 完成报告（写类工具上线 + 四道防线修复，P0）

> 执行者：W-NEXT-2 单写者（锁 `edu-agent/scripts/eval/wnext2.lock`，完工已删）
> 分支：`feature/opt-waves`；日期 2026-09-16；批判源：`test-reports/critique-blind-t4-t9.md`（T4-C1 / T4-C2 / T4-C3 / T4-C4 + T8-C1 / T8-C2）
> 交付 commit：`00bb384`（首版）+ **第二轮复验加固**（见 §0.1，commit hash 见文末回执）
> 环境：后端 8000 运行中（**未重启**，遵守红线）；验证用 **8010 临时实例**；契约 `contracts/reshape-r-aci.json` / `contracts/reshape-r-hitl.json` 未改（禁碰）；`app/chat/router.py`、`app/chat/sse.py`、`app/ai/hitl_gate.py`、`public/**`、`contracts/**` 未改。
> 本报告为**第二轮修订版**：首版有 2 处夸大表述、3 处限定缺失（独立复验指出），已逐条纠正并标注（见 §10 修订记录）。

## 0. 改动清单（文件归属内）

| 文件 | 改动 | 对应批判 / 步骤 |
|---|---|---|
| `edu-agent/app/ai/permission_gate.py` | `knowledge_import` 从 `CONTRACT_PENDING_TOOLS` 迁入 `TOOL_CLASS_MAP`=`admin_write`；补 `REGISTERED_BUILTIN_TOOLS`；新增 `WRITE_CLASSES`/`is_write_class`/`classify_tool_intent`/`resolve_role`/`gate_tool_call`/`build_denied_envelope`；docstring 注册面证据改 8 实物 / 9 挂起；**加固：新增 `_norm`（`strip().lower()`）并让 `classify_tool`/`classify_tool_intent` 归一** | 步骤1 + 步骤3 / T4-C3 |
| `edu-agent/app/mcp/executor.py` | ① `_classify_hitl_action`/`_is_cached_call` 分类改走 permission_gate 单一事实源；② 新增 `_resolve_builtin_name`/`_execute_builtin_attempt`/`_make_builtin_hitl_exec`/`_knowledge_import_handler` 并注册 `knowledge_import`（**933/934/935 行**，见 §9）；③ `call_tool`/`call_tool_with_retry` 写类纵深防御门 + `_permission_denied_resp`；**加固 a：抽出 `_deny_if_write_class` 并在 `call_tool` 两处（调用方名 ① + registry 解析名 ②）与 `call_tool_with_retry`（解析后）调用，堵 `tool_id`-only 绕过**；**加固 b：重试闭环第 3 步 `switch_tool` 换备用工具前对**目标名**再过同一道门（堵 `TOOL_FALLBACK_MAP` 被 env 覆盖后「读工具→写工具」的配置诱导越权）** | 步骤1/2/3 / T4-C1、T4-C3、T8-C1 |
| `edu-agent/app/chat/tool_calling.py` | 流式预取路径接权限门：写类工具 `gate_tool_call` deny → 零 executor 调用、零落审计，ACI 三字段入 summary；只读路径不解析角色（零额外 IO）；**加固：两处用户可见 `degraded_extra` 文案去 `type(exc).__name__`** | 步骤2 / T4-C1、T4-C2 |
| `edu-agent/app/chat/flows/langgraph_agent.py` | `AgentState` 补 `tool_name/tool_args/query_rewrite/user_id/user_role` 等键（LangGraph 只为声明键建 channel，缺失即断链）；`_agent_tool_catalog()` 从注册面动态生成 prompt 工具清单；`_tool_result_text()` 修 denied/rejected 断链；`generate_node` 注入「无一次成功 → 禁完成态描述」诚实约束；兜底文案不泄异常类名 | 步骤2b / T4-C2、T4-C3、T8-C2 |
| `edu-agent/app/chat/flows/graph_stream.py` | 续流静默吞修复：Redis 有决策但图无挂起 → 显式收束（`hitl_rejected_no_pending` / `hitl_confirm_expired_no_pending`），绝不假装续跑；**加固：用户可见 `message`/`degraded_reason` 去掉 `type(exc).__name__`（含 MCP 阶段降级两处文案；保留 `落库失败` 子串以兼容既有断言）** | 步骤4 / T8-C2 |
| `edu-agent/tests/test_permission_gate.py` | 按 8 实物 / 9 挂起重写矩阵与计数断言；新增 10 写类名分类 + 不缓存断言、knowledge_import 注册断言；**加固补测：`test_norm_eliminates_case_whitespace_dual_criterion`（大小写/空格变体双口径）** | 步骤1/3 + 复验加固 |
| `edu-agent/tests/test_wnext2_write_tools.py`（新增，**19 用例**） | W2-G2 / G3 / G4 / G6 集成测试（13）+ **加固补测 6**：T8-C2 无挂起收束（confirm/reject 参数化）、executor 收口二次校验（tool_id-only 越权 + admin 阳性对照）、**P1 备用工具越权（student deny + admin 阳性对照）** | 步骤2/3/4 + 复验加固 |

### 0.1 第二轮复验加固（独立复验发现问题 → 已修 → 已补测试）

| # | 复验发现 | 修复 | 回归防护测试 |
|---|---|---|---|
| P1-a | **executor 收口可绕过**：`call_tool(operator_user_id=<非admin>, tool_id=N)` 不传 `tool_name` → 调用方名为空 → 写类校验整体跳过 → 真实执行 | 新增 `_deny_if_write_class`；`call_tool` 在 ① 调用方名 + ② registry 解析出的真实名两处校验；`call_tool_with_retry` 解析后追加一次 | `test_executor_second_gate_blocks_tool_id_only_write_call`（deny + 零执行）/ `..._admin_tool_id_only_still_passes`（admin 不误伤）；**回退验证**：把 `_deny_if_write_class` 置为恒 `None` 复跑 → `knowledge_import` 真实进入执行器（证明该测试是真回归保护） |
| P1-b | **配置诱导越权（复验新发现）**：重试闭环第 3 步 `switch_tool` 直接用 `settings.TOOL_FALLBACK_MAP` 目标名调执行器，**无门无 HITL**；该 map 可被 env JSON 覆盖 → 注入 `{"calculator": ["knowledge_import"]}` 即把「读工具 → 写工具」接成链路（复验实测：student → 写类 handler 真实执行并返回 SUCCESS） | `call_tool_with_retry` 在 `step.tool_name != original_tool_name` 时对**目标名**跑同一道 `_deny_if_write_class`（`executor.py:1436-1446`） | `test_p1_fallback_write_tool_blocked_for_student`（deny + 备用写类工具**零执行**，仅前两步为原工具）/ `..._allowed_for_admin`（阳性对照，第 3 步放行）；**回退验证**：门置为恒 `None` 复跑 → `CALLED: ['calculator','calculator','knowledge_import']`、`STATUS: MANUAL_GUIDE`（证明修复前确可越权） |
| P2-a | T8-C2 无挂起收束分支（`graph_stream.py:305-329`）**全仓库零测试** | 无需改代码（修复已在首版） | `test_t8c2_resume_without_pending_never_silently_runs[confirm/reject]`：断言图 `astream` **零调用** + 显式收束文案 + `degraded_reason` |
| P2-b | 流式路径仍泄异常类名（`graph_stream` 用户可见 message / degraded_reason，两处 MCP 阶段降级文案） | 两处文案去 `type(exc).__name__`（类名只进 logger） | 既有 `test_chat_stream_error.py`（含 `落库失败` 子串断言）全绿 |
| P2-c | `Create_Course` 双口径（HITL 判写类 / 权限门判非写类） | `permission_gate._norm` 归一 | `test_norm_eliminates_case_whitespace_dual_criterion`（见 §1-④）：**已登记名** 4 变体双口径消除；**未登记/挂起名的分类不对称属有意设计**（门 fail-closed + 有实物才放行），已在该用例 docstring 与 §7.5-CR1 残留风险中登记 |
| P2-d | **同类泄漏同路径未收口**：`tool_calling` 两处 `degraded_extra` 也带 `type(exc).__name__`，同样经 `merged_deg` 进用户可见 done 帧 | **已修**（归属文件）：`tool_calling.py:249/385` 改稳定文案 | 14 文件回归全绿（无既有断言依赖类名串） |
| P2-e | **其余同类泄漏（非归属，未改，登记）**：`service.py:402/682`（W-NEXT-9）、`router.py:351/366`（禁碰）、`sse.py:51-74`（禁碰）、`generator.py:541/609` | 未改 | 见 §7.5 CR-WNEXT2-exc-classname-leak-remaining |

未改（属其它工作流）：`app/chat/router.py`、`app/knowledge/importer/loader.py`（WNEXT10 F5-a）、`app/chat/service.py`（W-NEXT-9）、`app/domains/question_admin/router.py`（W-NEXT-5）。
> ⚠️ 工作区存在**并行写者**的未提交改动（`app/chat/router.py`、`app/knowledge/importer/loader.py`、`app/ai/skills/registry.py`、`app/ai/graph.py`、`app/ai/platform_capability.py` 等）→ 本任务 commit **只含归属文件**，不夹带（见 §10）。

---

## 1. W2-G1 统一工具分类单一事实源（T4-C3）

`executor._classify_hitl_action` 与 `_is_cached_call` 不再各写一份前缀判定，统一走 `permission_gate.classify_tool_intent` / `is_write_class`（`TOOL_CLASS_MAP ∪ CONTRACT_PENDING_TOOLS`），前缀判定仅作未登记名兜底。

| # | GWT | 实测 | 结论 |
|---|---|---|---|
| ① | 10 个写类工具名分类命中 `write_file` | `test_write_class_names_classified_and_not_cached[course_create/course_update/course_delete/question_create/question_update/question_delete/favorite_add/points_change/knowledge_import/order_create]` **10/10 PASSED**；`test_write_class_names_cover_10` PASSED | ✅ |
| ② | 写类工具 `_is_cached_call(...)==False`（禁缓存非幂等副作用） | 同上 10 用例内置断言 `_is_cached_call(...) is False` 全通过 | ✅ |
| ③ | 未登记名不误伤（保持既有 retry 语义） | `test_contract_task_t1*.py` / `test_contract_r12_tool_decision.py` 全绿（见 §6） | ✅ |
| ④ | **已登记名的大小写/空格变体无双口径**（复验加固） | `test_norm_eliminates_case_whitespace_dual_criterion`：`Knowledge_Import` / ` knowledge_import ` / `KNOWLEDGE_IMPORT` / 混合大小写 4 变体均 `classify_tool=="admin_write"`、`is_write_class=True`、`_hitl_risk_level=="high"`、`can_use_tool(student).allowed=False` 且 `can_use_tool(admin).allowed=True`（修复前 admin 会被误拒）；未登记名对 admin 仍 deny（归一不放宽 fail-closed） | ✅ |

## 2. W2-G2 流式路径接权限门 + deny 断链修复（T4-C1 / T4-C2）

| # | GWT | 实测 | 结论 |
|---|---|---|---|
| ① | 写类 deny → **零 executor 调用**（不执行、不落审计） | `test_w2g2_stream_write_deny_zero_call_and_aci_envelope` PASSED（断言 `executor.call_tool` 调用次数=0） | ✅ |
| ② | deny 结果含 **ACI 三字段** | 同用例断言 `{code,message,action_hint} ⊆ envelope.keys()`；实测 `build_denied_envelope` 返回 `code="permission_denied"` + 面向用户 message + 可执行 `action_hint` | ✅（见 §7.1 信封超集观察项） |
| ③ | admin 写类放行 → 真实进 executor | `test_w2g2_stream_write_admin_allowed_calls_executor` PASSED | ✅ |
| ④ | 只读路径**不解析角色**（零额外 DB IO，不退化 T1 性能） | `test_w2g2_read_tool_path_does_not_resolve_role` PASSED | ✅ |
| ⑤ | executor 公共收口纵深防御（**限定说明见下**） | `_permission_denied_resp`（`executor.py:123-146`）在 executor 内对写类工具做角色校验，返回 ACI 信封内嵌 `content_text`，**不落审计、不进 HITL 队列**；`call_tool` 的 ① 调用方名 + ② registry 解析名两道校验（见 §0.1-P1-a） | ✅（**不是**「三条执行路径统一拦写类」，见下） |
| ⑥ | 重试闭环第 3 步换备用工具前对**目标名**再过同一道门（配置诱导越权收口） | `call_tool_with_retry` 在 `step.tool_name != original_tool_name` 时跑 `_deny_if_write_class`（`executor.py:1436-1446`）；`test_p1_fallback_write_tool_blocked_for_student`（deny + 备用工具零执行）/ `..._allowed_for_admin`（放行）PASSED | ✅ |

**⑤ 的限定（首版夸大，已纠正）**：三条路径中**只有 executor 收口（`call_tool`/`call_tool_with_retry`）是生产可达的拦截面**：
- 路径①流式 `tool_calling.run_chat_tool_calls` 的写类门**已接线且单测通过**，但其工具清单来自 `list_enabled_tool_metas()`（只查 DB `mcp_tool` 的 5 个只读工具）→ **内置写类工具 `knowledge_import` 在生产流式路径无触发面**（详见 §7.3 CR）。
- 路径③旧 R11 图 `langgraph_agent.tool_node`（有门 + interrupt）经 HTTP **不可达**（§7.2 CR）。
- 故生产语义是：**「executor 收口」+「生产图无工具节点」共同构成实际防线**；不能说成三路径均已生效。
- 另：本表 ①②③④ 均为**函数级**进程内实证（真实权限门 + 真实 `run_chat_tool_calls`，executor 侧为计数替身），生产触达面受限见上；`/api/mcp/tools/test` 端点对非 admin 亦不可达（§4.1 诚实边界）。

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

> **限定（首版未标注，已补）**：本节用的是**合成最小图**（`StateGraph(AgentState)` + 真实 `langgraph_agent.tool_node` + `InMemorySaver`，入口直连 tool 节点），用于实证 **interrupt 三件套语义与 `tool_node` 自身正确性**；它**不等于**生产 `/api/chat/stream` 主路径——生产六节点图**无 tool/interrupt 节点**（§7.2 CR），故 G4 的「端到端」仅到「图级」为止，HTTP 级端到端**结构不可达**（见 §4.1 诚实边界）。

| # | GWT | 实测 | 结论 |
|---|---|---|---|
| ① | 挂起态零执行 + interrupt payload **五字段** | `test_w2g4_real_graph_interrupt_confirm_executes`：真实 `StateGraph(AgentState)` + 真实 `tool_node` + `InMemorySaver`；`set(v.keys()) == {"thread_id","tool_name","args","risk_level","timeout_s"}`、`tool_name="knowledge_import"`、`risk_level="high"`（admin_write→L3）、`timeout_s=300`、挂起阶段执行次数 **0** | ✅ |
| ② | confirm → 真实执行一次 | `Command(resume={"action":"confirm"})` → 执行次数 **1**、`args_kw is True`（`call_tool(args=…)` 关键字传参）、`hitl_decision is True`（不二次挂起） | ✅ |
| ③ | reject → 零执行 | `test_w2g4_real_graph_interrupt_reject_zero_exec` PASSED | ✅ |
| ④ | student → deny 且无 interrupt | `test_w2g4_real_graph_student_denied_no_interrupt` PASSED | ✅ |

### 4.3 续流静默吞修复（T8-C2）

`graph_stream` 续流前先探明图挂起态；无挂起 → 按 reject/confirm 分别显式告知「工具未执行、无任何数据变更」/「确认已失效」，并落 `degraded_reason=hitl_rejected_no_pending|hitl_confirm_expired_no_pending`。**不再把 `Command(resume=…)` 丢进无挂起图静默跑完**（用户以为「确认执行了」而实际零执行）。

| # | GWT | 实测 | 结论 |
|---|---|---|---|
| ① | 有决策 + 图**无挂起** → 不静默续跑 | `test_t8c2_resume_without_pending_never_silently_runs[confirm]` / `[reject]`：monkeypatch `_pop_hitl_decision` 有决策、`_ensure_agent_graph` 返回 `aget_state().next==()` 的替身图；断言替身图 **`astream` 调用次数=0**、SSE 体含 `hitl_confirm_expired_no_pending`（或 `hitl_rejected_no_pending`）+ 用户可见文案、`finalize` 收到的答案文案即收束文案 | ✅（首版零测试，本轮补齐） |
| ② | 续流文案不含异常类名 | 同上用例断言文案为固定中文，无 `type(exc).__name__` 泄漏 | ✅ |

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
| 核心（3 文件） | `pytest tests/test_permission_gate.py tests/test_wnext2_write_tools.py tests/test_r11_hitl.py -q` | **119 passed**（首版）→ 加固后 **126 passed**（4.42s） |
| 扩展（7 文件） | `pytest tests/test_permission_gate.py tests/test_wnext2_write_tools.py tests/test_contract_task_t1.py tests/test_contract_task_t1_fallback.py tests/test_contract_r12_tool_decision.py tests/test_chat_stream_error.py tests/test_r11_hitl.py -q` | **144 passed, 1 skipped**（首版）→ 加固后 **156 passed, 1 skipped**（12.88s） |
| **加固后影响面（14 文件）** | `pytest tests/test_permission_gate.py tests/test_wnext2_write_tools.py tests/test_r11_hitl.py tests/test_sse_envelope_contract.py tests/test_contract_r12_tool_decision.py tests/test_contract_task_r02.py tests/test_contract_mcp_health_async.py tests/test_task33_mcp_desc_review.py tests/test_contract_task_t1.py tests/test_contract_task_t1_fallback.py tests/test_contract_task_s1.py tests/test_contract_task_o1_instrumentation.py tests/test_contract_task93.py tests/test_chat_stream_error.py -q` | **234 passed, 1 skipped**（46.17s） |
| 全仓扫描（`pytest tests -q`） | — | **1090 passed / 78 failed / 39 skipped**；78 项**逐项归类后与本次改动无关**，见下 |

**78 failed 归类（避免误读为回归）**：

| 类别 | 数量级 | 证据 | 是否本次引入 |
|---|---|---|---|
| 需真实 MySQL/Redis/Milvus 的 Live 契约套件（`test_contract_task15/16/18/19/20/21/22/113/23/…`） | 76 | 报错为 `RuntimeError: MySQL 连接池未初始化，请先调用 init_mysql()` / Milvus 召回为空 / AI-Hub 路径 `on_disk==0` → 全量单进程运行时的环境初始化缺失 | ❌ 非本次（环境） |
| **其它并行写者**的在途改动：`app/ai/platform_capability.py` + `app/ai/skills/registry.py`（未提交/未跟踪） | 2 | `test_wn_ext10_rag_internal_filter.py::test_inventory_matches_tool_class_map` 断言 `len==7`；`test_contract_task94.py::test_skill_node_no_match_yields_empty` 期望 `skill_context==""` — 两者均由该写者的「平台能力清单注入」引入 | ❌ 非本次（跨写者，见 §7.5-CR2） |
| 本任务影响面 | **0** | 14 文件集 **234 passed / 1 skipped**，含全部权限门 / HITL / chat 流错误 / MCP / 工具决策契约 | — |

`1 skipped` 为既有跳过项：`tests/test_contract_r12_tool_decision.py:365`「真 LLM 活体例：设 `R12_LIVE_LLM=1` 显式开启（默认跳过，保 CI 确定性）」，非本次改动引入（`-rs` 实测来源）。既有 `test_permission_gate.py` / `test_r11_hitl.py` / chat 契约测试**全绿，无回归**。

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

### 7.5 变更单草案（第二轮复验新发现）

#### CR-WNEXT2-executor-gate-bypass（P1，**已在本任务内修复**，仅登记）
- **事实（修复前）**：`call_tool(operator_user_id=<非admin>, tool_id=N)`（不传 `tool_name`）→ `_resolve_builtin_name` 返回空、`tool_name=None` → 调用方名校验整体跳过 → registry 解析出的写类工具**真实执行**（可绕过收口）。
- **修复**：`_deny_if_write_class` 抽出 + `call_tool` 在 ① 调用方名 / ② registry 解析名两处校验 + `call_tool_with_retry` 解析后追加校验；回归防护测试 2 条（见 §0.1）。
- **残留风险（登记）**：门是「**名单驱动**」——由 `TOOL_CLASS_MAP`（8 个实物工具）判定写类。**未来新上线的写类工具若忘登记映射表，收口不拦**。彻底解法是把「写类」变成注册时的强制属性（`register_builtin_tool(..., write_class=True)`），涉 `executor` 注册 API 与既有 3 个 handler，属范围外 → 上浮。

#### CR-WNEXT2-parallel-writer-regression（P2，跨写者，**非本任务**）
- **事实**：工作区存在并行写者在途改动（`app/ai/platform_capability.py`（未跟踪）+ `app/ai/skills/registry.py`），注入「平台能力清单（由 `TOOL_CLASS_MAP` 动态生成）」后：
  - `tests/test_wn_ext10_rag_internal_filter.py::test_inventory_matches_tool_class_map` 硬编码 `len(names)==7` → 本任务上线 `knowledge_import` 后为 **8** → 断言失败；
  - `tests/test_contract_task94.py::test_skill_node_no_match_yields_empty` 期望 `skill_context==""` → 现返回能力清单块 → 断言失败。
- **归属**：两份断言分别属 WNEXT10 写者与 task94 既有契约，**均不在本任务归属**（`test_wn_ext10_*` 且为未跟踪文件）→ 未改。
- **建议**：①`test_inventory_matches_tool_class_map` 改为 `len(names) == len(TOOL_CLASS_MAP)`（它已 `from app.ai.permission_gate import TOOL_CLASS_MAP`，硬编码 7 属自相矛盾）；②task94 用例按「无 skill 命中 → 仍注入平台能力清单」更新期望。

#### CR-WNEXT2-exc-classname-leak-remaining（P2，非归属文件，**未改**）
- **事实（本轮复验后实测行号）**：T4-C2「兜底文案不泄内部类名」在本任务归属文件内已收口（`langgraph_agent` 兜底、`graph_stream` 三处、`tool_calling` 两处），但**同一用户可见通路**上仍有非归属点位把 `type(exc).__name__` 写进面向用户的字段：
  | 点位 | 字段 | 可见性 |
  |---|---|---|
  | `app/chat/service.py:402` | `mcp_degraded` → `merged_deg` → done 帧 `data.degraded_reason` | 用户可见（`/api/chat/answer`） |
  | `app/chat/service.py:682` | 返回元组 degraded → 同上 | 用户可见（`/api/chat/stream` 非图路径） |
  | `app/chat/router.py:351/366` | 落库失败 `message` / `degraded_reason` | 用户可见（`STREAM_VIA_GRAPH=False` 旧路径） |
  | `app/chat/sse.py:51-74` | `map_stream_exception` 8 分支拼类名 → error 帧 `message` | 用户可见（全部 SSE 错误帧） |
  | `app/chat/generator.py:541/609` | `merged_deg` → `degraded_reason` | 用户可见 |
- **归属**：`service.py`（W-NEXT-9）、`router.py` + `sse.py`（本任务禁碰红线）、`generator.py`（未在归属清单）→ 均**未改**。
- **建议**：统一改为稳定中文文案，类名只进 logger（可复用本任务在 `graph_stream` / `tool_calling` 的写法：`logger.warning(f"… {type(exc).__name__}: {exc}")` + 用户侧固定串）。
- **备注**：`tool_calling.py:382` 的 `result_summary` 仍保留类名与末行 traceback —— 该字段是**工具错误记录**（供 LLM 重试决策/审计），非面向用户文案，本轮**有意保留**，不在本 CR 范围。

#### CR-WNEXT2-env-debug-redline（P0，环境红线，**未除**）
- **事实**：`edu-agent/.env` 为 `DEBUG=true`（非 git 跟踪）。项目记忆第 6 条：`settings.DEBUG=true` 时无 `Authorization` 头会返回虚拟管理员 `user_id=1` → 未登录可读用户数据。
- **本任务相关性**：本任务新增的写类门在 `DEBUG=true` 下**不构成额外风险**（门在 executor 内，与 DEBUG 降级无关），但 `DEBUG=true` 本身使「未登录 → 管理员身份」成立 → 需部署前改 `DEBUG=false`。**本任务未改 `.env`**（环境文件非代码归属），上浮为部署前检查项。

## 8. 边界与未做

- 未改：`chat/router.py`、`chat/sse.py`、`ai/hitl_gate.py`、`public/**`、`contracts/**`（红线）；`chat/service.py`（W-NEXT-9）、`question_admin/router.py`（W-NEXT-5）、并行写者文件（见 §0 末）。
- **异常类名泄漏的修法（首版表述已纠正）**：首版称「已规避」——准确表述为**归属文件内四处已修**：①`langgraph_agent` 兜底文案；②`graph_stream` 用户可见 `message`/`degraded_reason`（含 MCP 阶段两处，本轮复验加固）；③`tool_calling` 两处用户可见 `degraded_extra`（本轮复验加固）。`map_stream_exception`（`sse.py`，禁碰）、`service.py`、`router.py:351/366`、`generator.py` **未改**（用户可见通路仍有点位）→ 已登记为 §7.5 `CR-WNEXT2-exc-classname-leak-remaining`，不声称已全清。
- 8010 临时实例仅用于本次实证，未触碰 8000；实证后已关闭。
- 契约测试的 `1 skipped` 为既有跳过项（`R12_LIVE_LLM` 未开启）。
- 本任务 commit **只含归属文件**，不夹带并行写者的未提交改动（见 §10）。

## 9. 附：登记回主表

- `REGISTRY_EVIDENCE` 与 docstring 的内置工具出处已统一为 **`executor.py:933/934/935`**（`register_builtin_tool` 实际行；首版误记 925/926/927，已校订源码注释与本报告 §0/§3/§9），`test_registry_reconciliation_executor_source` 以源码正则实采复验通过。

## 10. 修订记录（第二轮：独立复验 → 批判加固）

| # | 首版问题 | 本轮处置 |
|---|---|---|
| 1 | 夸大：§2-⑤「三条执行路径统一拦写类」 | 改为限定表述（仅 executor 收口生产可达 + 两条路径结构受限，见 §2-⑤ 限定块） |
| 2 | 夸大：§8「已规避泄异常类名」 | 改为「两处已修 + `sse.py` 映射既有行为未清」，见 §8 |
| 3 | 缺失限定：G2/G4 在结构不可达前提下仍标 ✅ | §2 表注 + §4.2 合成图限定块补齐 |
| 4 | 缺失：T8-C2 修复零测试未标注 | §4.3 补 2 条用例 + 明确「首版零测试，本轮补齐」 |
| 5 | 缺失：只有断言无回归保护（P1 绕过可复用） | 新增 executor 二次校验 2 条用例（§0.1） |
| 6 | 未修：`graph_stream` 仍泄类名；`Create_Course` 双口径 | 代码修复 + §0.1 登记 |
| 7 | 混淆：全仓 78 failed 未归类 | §6 补归类表（环境 76 / 跨写者 2 / 本任务 0） |
| 8 | 未登记：并行写者文件、`.env DEBUG=true`、名单驱动局限 | §7.5 三条 CR |
| 9 | **复验新发现 P1-b**：`TOOL_FALLBACK_MAP` 配置诱导越权（第 3 步备用工具无门） | 代码修复（`executor.py:1436-1446`）+ 2 条回归防护用例 + 回退验证证据（§0.1 P1-b / §2-⑥） |
| 10 | 同路径仍泄类名（`tool_calling` 两处） | 代码修复（归属内）+ §0.1 P2-d；非归属点位转 CR（§7.5 CR-WNEXT2-exc-classname-leak-remaining） |
| 11 | §6 回归数字口径（19 用例后） | 核心 126 / 扩展 156+1skip / 影响面 **14 文件 234 passed, 1 skipped**（46.17s） |

## 11. 交付 commit

| # | commit | 内容 | 核验 |
|---|---|---|---|
| 1 | `00bb384` | 首版（步骤1~4 + 集成测试 + 报告初版） | `git symbolic-ref HEAD` = `refs/heads/feature/opt-waves` |
| 2 | `<第二轮 hash，见完工回执>` | 第二轮复验加固（`_norm` 归一 / executor 收口二次校验 / 备用工具门 / 类名收敛 / 19 用例 / 本报告修订版） | `git symbolic-ref HEAD` = `refs/heads/feature/opt-waves`；`git rev-parse HEAD` 记录 |

> 两个 commit 均**只含归属文件**：`app/ai/permission_gate.py`、`app/mcp/executor.py`、`app/chat/tool_calling.py`、`app/chat/flows/langgraph_agent.py`、`app/chat/flows/graph_stream.py`、`tests/test_permission_gate.py`、`tests/test_wnext2_write_tools.py`、`test-reports/WNEXT2-completion-report.md`；未夹带并行写者的在途改动（`app/chat/router.py`、`app/ai/graph.py`、`app/ai/skills/registry.py`、`app/knowledge/importer/loader.py`、未跟踪 `app/ai/platform_capability.py`、`tests/test_wn_ext10_rag_internal_filter.py`）。