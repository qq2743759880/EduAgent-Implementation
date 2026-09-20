# 变更单：写类工具首批落地（favorite_add=user_write + course_create 矩阵预登记）

- **编号**：CR-WRITETOOLS-001
- **状态**：已批准（用户 2026-09-20 逐项批复 P1-P6，见 `docs/时光.md` §九批复记录；kickoff：`.ai-hub/plans/artifacts/kickoff-WRITE1-FAV.md`）
- **执行**：W-NEXT-WRITE1（第一批=favorite_add 打样；course_create=planned/batch-2）
- **触及冻结契约**：`contracts/reshape-r-aci.json`（矩阵语义）、`contracts/reshape-r-hitl.json`（风险分级事实源）——**冻结文件本体不改**，本单为其语义修订的登记载体（后续契约文件版本化时并入）。

---

## 1. 变更内容

### 1a. favorite_add（applied，第一批）

| 项 | 原语义（reshape-r-aci.json） | 新语义（P1 裁定） |
|---|---|---|
| 类别 | admin_write（契约 write_class_tools「收藏写」=仅 admin） | **user_write（新类别首例）** |
| 矩阵 | 仅 admin | **student=allow / teacher=allow / manager=deny / admin=allow / guest(未知角色)=deny** |
| HITL | high（挂起期按 admin_write 别名） | **None（免弹卡）**——本人低危写，`_hitl_risk_level` 按 user_write 类别返回 None |
| executor 收口 | — | **write_class=True 注册期强属性**（`_BUILTIN_WRITE_CLASS_NAMES`）→ executor 收口仍做角色校验（manager 在此被拒，双保险） |

落地位置：
- `app/mcp/executor.py`：`_favorite_add_handler` + `register_builtin_tool("favorite_add", ..., write_class=True)`
- `app/ai/permission_gate.py`：`ToolClass` 增 `user_write`；`TOOL_CLASS_MAP["favorite_add"]="user_write"`；`_CLASS_ALLOWED_ROLES["user_write"]={student,teacher,admin}`；迁出 `CONTRACT_PENDING_TOOLS`（挂起区 9→8）；真实注册面 8→9
- `app/chat/flows/langgraph_agent.py`：`_hitl_risk_level` 改读 `classify_tool_intent`（P3 单一事实源；admin_write=high / course_write=medium 语义保持，user_write=None）
- `app/chat/tool_calling.py`：`_BUILTIN_TOOL_DESCRIPTIONS` 补 favorite_add 描述（工具发现面）
- `tests/test_tool_favorite_add.py`（新增）+ `tests/test_permission_gate.py`（teacher×favorite_add 反转 allow、挂起数 9→8、注册面 8→9）

安全不变量：
- user_id 服务端注入（`_EXEC_CONTEXT.operator_user_id`），args 伪造身份结构性不可达
- 参数 exact-pin：仅 `series_id`(int)，多余键拒（别名字段注入防线）
- 业务错结构化回传（ok=False + 后端错误码原文），严禁伪装成功

### 1b. course_create（planned，batch-2 未实施）

- 类别：**admin_write**（P2：仅 admin；manager=deny——如需放行另走变更单）
- HITL：required(high)；executor 双保险：handler 首行校验 `ctx["hitl_confirmed"]`，未确认 → 42201 拒（P4 语义，batch-2 落地时实施）
- 实施底稿：`docs/时光.md` §四

## 2. 不变量（验收断言）

1. 既有挂起工具语义零变化：`_hitl_risk_level` 对 points_change/order_create=high、course_*=medium（tests/test_r11_hitl.py test_g1_risk_level_classification 全绿即证）
2. knowledge_import（admin_write 实物）行为零变化
3. `reshape-r-hitl.json` 五字段帧（thread_id/tool_name/args/risk_level/timeout_s）零回归
4. fail-closed 不变：未登记/未知角色仍一律 deny
