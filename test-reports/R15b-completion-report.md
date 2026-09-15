# R15b 完成报告：工具映射表对账实物（消灭虚构工具名）

> 契约：`contracts/reshape-r-aci.json`（已冻结，**本任务零改动**）｜工作区：`E:\stu\project\stu\EduAgent实施手册`
> 单写者锁：`edu-agent/scripts/eval/r15b.lock`（开工建、完工删）｜基线：R15 `920599a`
> 验证方式：pytest 独立实证（81 用例）+ 只读 grep/SQL 对账 + 真实 DB 冒烟；**8000 未重启**，未起 8010（本次为纯数据/逻辑改动 + 只读探针，无启动面变更）

---

## 一、批判承接核对（编排者实锤 → 逐条落地）

| 批判项 | 核查动作 | 结论 |
|---|---|---|
| R15 映射表 17 项里 **10 个写类工具名全代码零命中** | 逐名 grep `executor.py`（10×0 命中）+ 只读 SQL 反查 `mcp_tool WHERE tool_name IN (10 名)` → **空集** | ✅ 批判成立，10 名确为臆译虚构名 |
| 真实注册面 = 内置 2 + MCP 5 | `register_builtin_tool("calculator"/"search_knowledge")` 实采；`SELECT tool_name FROM mcp_tool WHERE yn=1` → 5 行 | ✅ 与批判一致（共 7 个实物） |
| fail-closed 对真实工具面是空防、矩阵与实物脱节 | TOOL_CLASS_MAP 重建为**只含 7 个实物**；新增 `audit_registry()` 自动化对账 + 3 个对账测试（源码实采 / DB 实采 / 挂起反向核验） | ✅ 已闭环：映射表 100% 可逐名对账 |

**复核提示（诚实标注）**：`knowledge_import` 作为**工具名**零命中，但仓库里存在 `knowledge_import_task` **数据表名**（`app/knowledge/task_store.py:55`、`routers/upload.py:13`）——是导入任务表，不是 MCP 工具，故仍归入挂起。

---

## 二、交付物

| 文件 | 类型 | 说明 |
|---|---|---|
| `edu-agent/app/ai/permission_gate.py` | 修改 | TOOL_CLASS_MAP 对账实物（7 个）；新增 `REGISTERED_*` / `REGISTRY_EVIDENCE` / `CONTRACT_PENDING_TOOLS` / `audit_registry()` / `class_allowed_roles()`；头部注释写明对账口径与补登记流程 |
| `edu-agent/tests/test_permission_gate.py` | 修改 | 重写为 81 用例：G1 对账+矩阵、G2 fail-closed（挂起 10 名 × 3 角色全 deny）、G3 图级、**G4 角色注入（新增）**、G6 信封 |
| `edu-agent/scripts/eval/_r15b_probe_mcp_tool.py` | 新建 | 只读对账探针（report 证据可复跑；全程 SELECT） |
| `test-reports/R15b-completion-report.md` | 新建 | 本报告 |

**禁改清单执行情况**：`app/mcp/executor.py` **零改动**（G5，见 §6）、`contracts/**` 零改动、`app/chat/flows/langgraph_agent.py` 未触碰（并行任务正持有该文件 WIP）、`app/chat/router.py`、`sse.py`、`graph_stream.py`、前端 `public/**` 均未触碰。

---

## 三、R15b-G1：逐名对账表（工具名 → 注册出处）

对账日期 **2026-09-15**｜证据脚本：`edu-agent/scripts/eval/_r15b_probe_mcp_tool.py`

### 3.1 映射表全量（TOOL_CLASS_MAP = 7 个，全部有实物）

| # | 工具名 | 类别 | 注册出处（file:line / SQL） | 实物核验 |
|---|---|---|---|---|
| 1 | `calculator` | public_read | `app/mcp/executor.py:676` `register_builtin_tool("calculator", _calculator_handler)` | ✅ 源码实采 |
| 2 | `search_knowledge` | public_read | `app/mcp/executor.py:677` `register_builtin_tool("search_knowledge", _search_knowledge_handler)` | ✅ 源码实采 |
| 3 | `add` | public_read | `SQL mcp_tool: id=2 tool_name=add server_id=1(stdio-echodemo) yn=1` | ✅ DB 实采 |
| 4 | `echo` | public_read | `SQL mcp_tool: id=3 tool_name=echo server_id=1(stdio-echodemo) yn=1` | ✅ DB 实采 |
| 5 | `list_alphabet` | public_read | `SQL mcp_tool: id=4 tool_name=list_alphabet server_id=1(stdio-echodemo) yn=1` | ✅ DB 实采 |
| 6 | `ping` | public_read | `SQL mcp_tool: id=1 tool_name=ping server_id=1(stdio-echodemo) yn=1` | ✅ DB 实采 |
| 7 | `sse_health` | public_read | `SQL mcp_tool: id=5 tool_name=sse_health server_id=2(sse-demo-localhost) yn=1` | ✅ DB 实采（**server enabled=0**，见 §8 观察项②） |

注册表本体锚点：`executor.py:624` `_BUILTIN_TOOL_HANDLERS: dict = {}`｜注册函数：`executor.py:627 def register_builtin_tool(...)`｜解析点：`executor.py:690 _BUILTIN_TOOL_HANDLERS.get(tool_name)`

**对账后真实工具全量清单（7 个）**：
```
add, calculator, echo, list_alphabet, ping, search_knowledge, sse_health
```
（`audit_registry()` 输出：`mapped_but_unregistered=[] / registered_but_unmapped=[] / pending_now_registered=[]`）

### 3.2 探针原始输出（可复跑）

```
[builtin] register_builtin_tool 实采 2 个: ['calculator', 'search_knowledge']
  executor.py:676: register_builtin_tool("calculator", _calculator_handler)
  executor.py:677: register_builtin_tool("search_knowledge", _search_knowledge_handler)
[builtin] 候选名在 executor.py 命中: 全部 0 命中 ✔
[mcp_tool] yn=1 共 5 行
  id=2 tool='add'          server_id=1 server_code='stdio-echodemo'   enabled=1
  id=3 tool='echo'         server_id=1 server_code='stdio-echodemo'   enabled=1
  id=4 tool='list_alphabet' server_id=1 server_code='stdio-echodemo'  enabled=1
  id=1 tool='ping'         server_id=1 server_code='stdio-echodemo'   enabled=1
  id=5 tool='sse_health'   server_id=2 server_code='sse-demo-localhost' enabled=0
[mcp_tool] 候选名反向核验命中: 空集 ✔（10 名全部未注册）
[summary] 真实注册面 = 2 内置 + 5 MCP = 7 个
```

### 3.3 自动化对账（不是人工声明）

| 用例 | 断言 |
|---|---|
| `test_registry_reconciliation_executor_source` | 源码正则实采 `register_builtin_tool("X", ...)` **双向等于** `REGISTERED_BUILTIN_TOOLS`，且每个都在 TOOL_CLASS_MAP |
| `test_registry_reconciliation_mcp_db` | 直连 `asyncmy`（不碰 app 连接池）实采 `mcp_tool(yn=1)`：映射表声明的 MCP 工具**无缺失**；挂起名单**不得已在库** |
| `test_registry_reconciliation_pending_absent_from_executor` | 10 个挂起名不得出现在 executor 源码（防再次臆译补名） |
| `test_registry_reconciliation_audit_clean` | `audit_registry()` 三类差异全空 |
| `test_registry_evidence_covers_every_mapped_tool` | `REGISTRY_EVIDENCE` 键集 == TOOL_CLASS_MAP 键集，逐名有出处 |

---

## 四、R15b-G2：10 个虚构名移出映射表 → CONTRACT_PENDING_TOOLS（挂起）

```python
CONTRACT_PENDING_TOOLS: dict[str, ToolClass] = {
    # 课程/题库写类（契约矩阵：manager 放行）—— 实物未注册
    "course_create": "course_write", "course_update": "course_write", "course_delete": "course_write",
    "question_create": "course_write", "question_update": "course_write", "question_delete": "course_write",
    # 契约 write_class_tools（仅 admin）—— 实物未注册
    "favorite_add": "admin_write", "points_change": "admin_write",
    "knowledge_import": "admin_write", "order_create": "admin_write",
}
```

- **语义保留**：类别归属（course_write / admin_write）写进挂起清单，契约意图不丢；上线即按类归位。
- **映射挂起**：不在 `TOOL_CLASS_MAP` → `classify_tool()` 返回 `None` → `can_use_tool()` **一律 deny**（fail-closed 自然拦截，**无需特判**，也就不会出现「挂起工具被误放行」的新面）。
- **实证**：`can_use_tool("admin", "course_create")` → `allowed=False`；`("student"/"manager"/"admin") × 10 名 = 30 组全 deny`（`test_pending_tools_denied_for_all_roles`，30 passed）。
- **兼容别名**：`COURSE_WRITE_TOOLS` / `ADMIN_WRITE_TOOLS` 保留为**挂起集合的别名**（消费方：`langgraph_agent.py:272 _hitl_risk_level` 的 HITL 风险分级、`tests/test_r11_hitl.py:69`）。选择保留而非删除的理由：① 不触碰并行任务正持有的 `langgraph_agent.py`（单写者纪律）；② HITL 分级按**契约意图**保留，工具上线后开箱即生效，与权限门 deny 不冲突（deny 在前，HITL 在后，纵深防御）。别名语义已在注释里写明「**不是**已注册工具面」。

**逐名对账（虚构名反向核验，10/10 零命中）**：

| 工具名 | executor.py 命中 | 其它源码引用 | mcp_tool 命中 |
|---|---|---|---|
| course_create / course_update / course_delete | 0 / 0 / 0 | 无 | 0 |
| question_create / question_update / question_delete | 0 / 0 / 0 | 无 | 0 |
| favorite_add / points_change | 0 / 0 | 无 | 0 |
| knowledge_import / order_create | 0 / 0 | 无（仅存在 `knowledge_import_task` 数据表名，非工具） | 0 |

---

## 五、R15b-G3：矩阵语义不变 + 测试全绿

### 5.1 契约矩阵**未改**（只让映射表对账实物）

| 类别 | 允许角色 | 实物工具数 | 说明 |
|---|---|---|---|
| `public_read` | student / manager / admin | **7** | 现有全部实物工具（均无写语义） |
| `course_write` | manager / admin | **0（挂起 6 名）** | 契约语义保留在 `_CLASS_ALLOWED_ROLES`，无实物可归类 |
| `admin_write` | admin | **0（挂起 4 名）** | 同上 |
| 未登记 / 未知角色 | — | — | default deny |

`test_contract_matrix_class_semantics_unchanged` 直接断言类→角色矩阵与契约一致（含 `len(TOOL_CLASS_MAP)==7`），确保 R15b 只动映射表、不动矩阵。

### 5.2 测试数字

| 范围 | 命令 | 结果 |
|---|---|---|
| R15b 权限门全套 | `pytest tests/test_permission_gate.py -q` | **81 passed**（0 failed / 0 skipped，DB 实采用例真跑未跳过） |
| 关联回归（R15b + R11 HITL + task93） | `pytest tests/test_permission_gate.py tests/test_r11_hitl.py tests/test_contract_task93.py -q` | **106 passed**（R11 HITL 10/10 绿，别名方案未破坏既有消费方） |

81 用例构成：G1 对账 5 + 真实工具矩阵 21（7×3）+ 类矩阵语义 1 + fail-closed 未登记 3 + 未知角色 4 + 挂起工具 30（10×3）+ 挂起清单校验 1 + 映射表分类 1 + G3 图级 6 + **G4 角色注入 7** + G6 信封 2。

---

## 六、R15b-G4：角色注入自动化测试（R15 P0-3 反哺）

**新增 7 用例**（`tests/test_permission_gate.py`：`test_run_agent_*` / `test_injected_role_*` / `test_get_user_info_by_id_symbol_is_real_db_lookup`）：

| 用例 | 机制 | 断言 |
|---|---|---|
| `test_run_agent_injects_role_from_get_user_info_by_id[manager/admin/student]` | mock `app.auth.service.get_user_info_by_id` 返回**真实 `UserInfo` 模型**（`role=UserRole.X`）；用 `_FakeGraph` 替身替换 `agent_graph`（零 LLM / 零 DB） | 捕获 `AgentState`：`user_role == info.role.value`、`user_id` 透传、`config.thread_id==session_id` |
| `test_run_agent_role_missing_falls_back_to_student` | 查询返回 `None` | 兜底 `student` |
| `test_run_agent_role_lookup_error_falls_back_to_student` | 查询抛 `RuntimeError` | 不冒泡、兜底 `student`（服务不因角色查询失败而挂） |
| `test_injected_role_actually_drives_gate` | 注入 `manager` 后取 `state["user_role"]` 直接过权限门 | 真实工具 `echo` → allow；挂起写类 `order_create` → deny（**注入→判定闭环**） |
| `test_get_user_info_by_id_symbol_is_real_db_lookup` | `asyncio.iscoroutinefunction` | 防注入点被改名/移除后测试空转 |

**真实 DB 冒烟（报告留痕，非单测依赖）**：`get_user_info_by_id(1)` → `user_id=1, role='student'`（与 R15 报告一致，源查询见 `app/auth/service.py:474-510`，SQL 取自 `sys_user_auth.role_code`）。

---

## 七、R15b-G5：零改动证明

```
$ git diff --stat HEAD -- edu-agent/app/mcp/executor.py     → （空）
$ git diff --stat HEAD -- contracts/                        → （空）
$ python -c "import app.main"                               → IMPORT_OK tools=7 pending=10
```
导入冒烟附加：`_hitl_risk_level("echo") → None`（真实只读工具免中断）、`_hitl_risk_level("order_create") → "high"`（挂起写类按契约意图仍 high）。

---

## 八、补登记流程（工具真实上线时怎么补）

1. **先上实物**：在 executor / MCP server 侧真实注册工具名，取到出处（`file:line` 或 `mcp_tool` 行）。
2. **再迁映射**：把名字从 `CONTRACT_PENDING_TOOLS` 移入 `TOOL_CLASS_MAP`（类别用挂起清单里已声明的那个），同步加进 `REGISTERED_BUILTIN_TOOLS` / `REGISTERED_MCP_TOOLS`，并在 `REGISTRY_EVIDENCE` 补一行出处。
3. **跑门**：`pytest tests/test_permission_gate.py` —— 若忘记迁移，`test_registry_reconciliation_audit_clean` / `..._mcp_db` 会以 `pending_now_registered` 非空 **FAIL**，把「映射表与实物再次脱节」挡在提交前。
   > 注：`manager=只读+课程/题库写类` 的放行语义已预置在 `_CLASS_ALLOWED_ROLES`，课程/题库写类工具一旦落实物，manager 立即按契约放行，**无需再改矩阵**。

---

## 九、观察项 / 遗留风险（如实登记，不阻断本次验收）

1. **`teacher` 角色在权限门外**：真实 DB 角色分布 `admin 5 / manager 3 / student 100047 / teacher 3`——**3 个 teacher 用户**被 `run_agent` 注入 `user_role="teacher"`，而 `KNOWN_ROLES` 只含 admin/manager/student → 连公开只读工具也 deny。这与 R15 契约决策一致（契约矩阵只列三角色，teacher 属未知角色 fail-closed），但**业务上 teacher 现在完全用不了 AI 工具**。是否放行需走契约变更单（本任务未自行改契约，未自行扩角色）。
2. **`sse_health` 的 server 已禁用**：`mcp_tool id=5 → server_id=2(sse-demo-localhost) enabled=0`。权限门放行（工具行在册）但运行时 `_default_attempt_executor` 会以「server 已禁用」失败——**权限判定与运行可用性是两个层面**，本任务只对账「注册面」，不代偿 server 健康。
3. **`add` 的语义**：echodemo 演示工具，当前归 public_read（无写语义）；若后续被赋予写语义，需按补登记流程重新归类。
4. **挂起工具仍出现在 HITL 分级集合中**：`_hitl_risk_level` 对挂起写类返回 high/medium（契约意图）。因权限门 deny 在前，该路径当前不可达；属纵深防御保留，非缺陷。

---

## 十、运行命令速查

```bash
# R15b 权限门全套（81）
cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_permission_gate.py -q -p no:cacheprovider

# 关联回归（106）
cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_permission_gate.py tests/test_r11_hitl.py tests/test_contract_task93.py -q -p no:cacheprovider

# 只读对账探针（grep + SQL 证据可复跑）
cd edu-agent && .venv/Scripts/python.exe scripts/eval/_r15b_probe_mcp_tool.py
```

---

## 十一、完工回执

- **commit**：见本报告同批提交 `fix(r)/R15b-tool-registry-truth`（路径限定：`edu-agent/app/ai/permission_gate.py`、`edu-agent/tests/test_permission_gate.py`、`edu-agent/scripts/eval/_r15b_probe_mcp_tool.py`、`test-reports/R15b-completion-report.md`、`.ai-hub/plans/artifacts/kickoff-R15b-tool-registry-truth.md`）
- **报告路径**：`test-reports/R15b-completion-report.md`
- **各 GWT 数字**：
  - R15b-G1 ✅ 逐名对账表 7/7 有实物出处；`audit_registry()` 三类差异全空；对账 5 用例绿
  - R15b-G2 ✅ 10 名移出 TOOL_CLASS_MAP 进 CONTRACT_PENDING_TOOLS（30 组全 deny，`admin × course_create` 仍 deny）
  - R15b-G3 ✅ 权限门 81 passed；关联回归 106 passed；类→角色矩阵断言未变
  - R15b-G4 ✅ 角色注入新增 7 用例绿（含 run_agent 捕获断言 + 注入→门判定闭环）
  - R15b-G5 ✅ `executor.py` / `contracts/` 零改动（`git diff` 空）；导入冒烟 OK
- **对账后真实工具全量清单（7）**：`add, calculator, echo, list_alphabet, ping, search_knowledge, sse_health`
- **挂起清单（10，无实物）**：`course_create, course_update, course_delete, question_create, question_update, question_delete, favorite_add, points_change, knowledge_import, order_create`
