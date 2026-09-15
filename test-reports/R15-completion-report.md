# R15 完成报告：权限门 + ACI 错误信封

> 契约：`contracts/reshape-r-aci.json`（已冻结，frozen_hash 前缀 `cad95c5f`，2026-09-15 用户签字）
> 工作区：`E:\stu\project\stu\EduAgent实施手册`｜单写者锁：`edu-agent/scripts/eval/r15.lock`（完工已删）
> 验证：真实 DB + pytest 独立实证；8010 临时实例冒烟后用毕关闭（8000 运行中未重启）

## 一、交付物

| 文件 | 类型 | 说明 |
|---|---|---|
| `edu-agent/app/ai/permission_gate.py` | 新建 | R15-① 权限门（CanUseToolFn，默认 deny fail-closed）+ 工具名→分类映射表 + ACI message 生成 |
| `edu-agent/app/chat/flows/langgraph_agent.py` | 修改 | R15-②③ 角色注入 `AgentState.user_role` + `tool_node` deny 路径 ACI 信封 |
| `edu-agent/tests/test_permission_gate.py` | 新建 | G1/G2/G3/G6 测试（36 用例，asyncio_mode=auto） |

未触碰（禁改清单）：`app/chat/router.py`、`app/chat/sse.py`、`app/chat/flows/graph_stream.py`、`app/ai/hitl_gate.py`（只读参考）、`app/mcp/executor.py`（**零改动**，设计目标达成）、前端 `public/**`、`contracts/**`。

---

## 二、R15-①② 实现要点

### 权限门 `can_use_tool(role, tool_name) -> GateDecision`
- `GateDecision(allowed: bool, action_hint: str|None)`；deny 时 `action_hint` 必非空可执行建议。
- **默认 deny**：未登记工具名 / 未知角色（含空白、缺省）一律拒绝，fail-closed。
- 矩阵：`admin=全量已登记`；`manager=只读 + 课程/题库写类`；`student=仅公开只读`。
- 纯逻辑模块，**无 DB / 无 LLM / 无 Redis 依赖**。

### 工具名→分类 映射表（全量清单，编排者验收重点）
集中定义于 `permission_gate.py`（唯一事实源，共 17 个工具）：

| 分类 | 工具名 | 允许角色 | 备注 |
|---|---|---|---|
| `public_read` 公开只读 | `add` `echo` `list_alphabet` `ping` `sse_health` `calculator` `search_knowledge` | student/manager/admin | 前五个为 DB `mcp_tool` 实际注册；后两个为 executor 内置工具（`_BUILTIN_TOOL_HANDLERS`） |
| `course_write` 课程/题库写类 | `course_create` `course_update` `course_delete` `question_create` `question_update` `question_delete` | manager/admin | 契约矩阵：manager 放行 |
| `admin_write` 契约 write_class_tools | `favorite_add`（收藏写）`points_change`（积分变更）`knowledge_import`（知识库导入）`order_create`（订单创建） | 仅 admin | 即"admin 专属工具"；manager/student 一律 deny |

> 依据：以 `executor.py` 实际注册清单（`mcp_tool` 表 5 个 + 内置 2 个）为准逐个标注类别；契约 write_class_tools 四类 + 课程/题库写类补齐全量显式工具名。未在映射表的任何工具名（`nonexistent_tool` 等）→ 任意角色 deny。

### deny 路径 ACI 信封（`tool_node`）
- `mcp_executor.call_tool(...)` **之前**过门；deny 时 **不抛异常、不进现有 except 分支、不调用 executor**，直接返回：
  ```python
  {"tool_results": [{"tool_name", "status":"denied", "code":"permission_denied",
                     "message":"<面向用户中文>", "action_hint":"<可行动建议>"}]}
  ```
- `message`（`permission_denied_message`）全中文、无 traceback、无错误码堆砌/堆栈泄出；`action_hint` 为可执行动作（"请先登录后再试。" / "该工具未登记或不在权限范围内，请联系管理员开通后重试。" / "此操作需更高权限，请联系管理员（admin）开通后重试。"）。
- 保留原 try/except 正常路径零改动；`tool_name` 为空的原分支（`status:"error"`）保持不变。

---

## 三、GWT 逐条实证

### R15-G1 矩阵：student×写类=denied+action_hint；manager×课程/题库写类=allowed；manager×admin专属=denied；admin×任意已登记=allowed；student×公开只读=allowed
- 实证：`tests/test_permission_gate.py::test_matrix_full`（22 组参数化）+ 相关用例，pytest 全绿。

```
@pytest.mark.parametrize 关键组合断言示例：
  student × search_knowledge(public_read)     -> allowed=True
  student × course_create(course_write)       -> allowed=False + action_hint 非空
  student × order_create(admin_write)         -> allowed=False + action_hint 非空
  manager × course_create(course_write)       -> allowed=True
  manager × question_update(course_write)     -> allowed=True
  manager × order_create(admin_write)         -> allowed=False（admin 专属拒）
  admin   × echo / course_delete / order_create -> allowed=True（全量）
  admin   × points_change(favorite/积分/导入/订单) -> allowed=True
```

### R15-G2 fail-closed：未登记工具 × 任意角色 = denied
- 实证：`test_fail_closed_unregistered_tool`（`nonexistent_tool` × admin/manager/student 均 deny + action_hint）+ `test_fail_closed_unknown_role`（空白 / teacher 等未知角色对公开只读也 deny）。

### R15-G3 图级（不经 LLM）：`AgentState{tool_name:写类, tool_args, user_role:"student", user_id:1}` 直调 tool_node → `status="denied"` 含 code/message/action_hint；executor.call_tool 零调用
- 实证：`test_tool_node_denied_student_write`（mock `app.mcp.executor.call_tool`，断言 `called["n"]==0`）、`test_tool_node_denied_manager_admin_write`、`test_tool_node_denied_unregistered`、阳性对照 `test_tool_node_allowed_admin_public_read_passes_to_executor`（admin×只读→正常路径成功调用 executor，证明正常路径未破坏）。

### R15-G4 角色注入真实 DB：run_agent(user_id=1) → state.user_role="student"（user000001）
- 实证（真实 DB）：`get_user_info_by_id(1).role.value == "student"`（即 run_agent 注入逻辑同源）；端到端 `run_agent(user_id=1)` 完整跑通返回 `{answer, docs, graph_entities, tool_results, loop_count, latency_ms}`，未抛错。`sys_user_auth.role_code` 确认 user_id=1 → student。

### R15-G5 回归
- **新增 R15 测试**：`tests/test_permission_gate.py` → **36 passed**。
- **既有套件回归**：运行命令 `cd edu-agent && .venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider`。
  - 带 R15 改动：`975 passed / 74 failed / 39 skipped`（首轮）→ `967 passed / 82 failed`（二轮），**R15 文件 0 失败**；
  - 基线（`git stash` 掉 R15 对 langgraph_agent 的改动后）对比：同一套既有失败，**仅多出 4 个 test_permission_gate 失败**（因 tool_node 无门，恰为 R15 自身用例）；
  - 结论：**R15 未引入任何既有测试回归**（净新增回归 = 0）。
- ⚠️ **如实说明（非本任务引入）**：仓库既有套件存在**运行间抖动的环境数据失败**（两轮 full-run 74↔82 波动），全部位于 `task15/16/18/19/20/21/22/23/midleware/mcp_health_async/review/r01/m2/94/be_task01` 等文件，与 R15 无 imports 关联，属测试数据/运行实例/Milvus 召回/MySQL 池初始化等既有环境依赖。故"既有测试全绿"在基线即不成立；R15 不放大该状态。

### R15-G6 信封质量抽查
- 实证：`test_envelope_quality_chinese_no_traceback` + `test_denied_action_hint_actionable`（message 全中文、无 traceback/`0x`/`File ` 堆栈痕迹、无错误码堆砌；action_hint 均含 `登录/联系/开通` 可执行动词）。

---

## 四、8010 临时实例冒烟（用毕关闭）
- `uvicorn app.main:app --port 8010` 启动成功：存储初始化 `{mysql, mysql_ro, milvus, mongodb, minio, neo4j, redis} = 全 ok`；`GET /docs → 200`、`/openapi.json` 正常加载。证明修改后的 `langgraph_agent.py` + 新增 `permission_gate.py` 不影响应用启动。验证后已 `Stop-Process` 关闭 8010 监听。

---

## 五、工具分类映射表复述（交付回执重点）
```
public_read（7）:  add, echo, list_alphabet, ping, sse_health, calculator, search_knowledge
course_write（6）: course_create, course_update, course_delete, question_create, question_update, question_delete
admin_write（4）:  favorite_add(收藏写), points_change(积分变更), knowledge_import(知识库导入), order_create(订单创建)
```

## 六、设计备注
- 契约矩阵仅列 admin/manager/student；`teacher` 及任意未知角色按 fail-closed 默认 deny（含公开只读）。如需 teacher 放行只读，属契约变更，须走变更单上浮，未自行改契约。
- `executor.py` 保持零改动（目标达成）；`hitl_gate.py` 仅作 RiskLevel/纯逻辑-IO 分离风格参考。

## 七、运行命令速查
- 新增测试：`cd edu-agent && .venv\Scripts\python.exe -m pytest tests/test_permission_gate.py -q -p no:cacheprovider`
- 全量回归：`cd edu-agent && .venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider`