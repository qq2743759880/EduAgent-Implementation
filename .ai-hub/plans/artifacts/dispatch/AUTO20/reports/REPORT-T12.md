# REPORT-T12：course_create batch-2 高危工具 HITL 实弹（AUTO20）

- 执行者：T12 子 agent（chat 后端域独占）
- 日期：2026-09-22
- 分支核验：开工前/后 `git branch --show-current` = `feature/opt-waves` ✓
- commit：`e7d7176` `feat(be)/T12-course-create-hitl: ...`（8 文件，+630/-22，未 push）

---

## 一、底稿与资产消费（证据可复现）

| 资产 | 消费方式 |
|---|---|
| `docs/时光.md` §四（B1-B5） | 逐节实读；B1/B2/B4 全落，B3 单一事实源已由 WRITE1 落地（本轮只做语义迁移核验） |
| `contracts/cr-writetools-001.md` §1b | planned/batch-2 语义逐条兑现（admin_write 仅 admin、HITL required(high)、42201 双保险） |
| favorite_add 先例（commit `4a598b3`） | executor 注册区/permission_gate 迁移/启发式分支/子代理清单四处同构复用 |
| `app/domains/course_admin/service.py:123` | **实读核实 `create_series(data: SeriesCreateAdmin)` 真实存在**（铁律4解除）——草图中 `operator_id/modules` 直传签名与现实不符，按实读签名落 |
| `app/ai/permission_gate.py` / `app/chat/flows/langgraph_agent.py:27` / `app/chat/flows/graph_stream.py:212` | 类别/HITL 分级/五字段帧链路实读复用，零改动（闸3 纯核验） |

## 二、三处底稿差异的处置（WRITE1 批勘误承接 + 本轮新增 1 处）

1. executor 在 `app/mcp/executor.py`（非 app/ai/）——按现实落位，注册区紧跟 favorite_add。
2. course service = `app/domains/course_admin/service.py`，`create_series` 存在（service.py:123），
   签名 `(data: SeriesCreateAdmin)`：institution_id/delivery_mode/created_by 必填。**处置**：
   - institution_id：服务端取 `org_institution yn=1` 最小 id（args 传 institution_id 落入多余键拒，
     exact-pin 防线——防 LLM 臆造父引用）；
   - delivery_mode：缺省 `online_recorded`（schema 三态枚举之一）；
   - created_by：执行上下文 operator_user_id（服务端权威）。
3. modules 语义差异（**本轮新发现，如实登记**）：时光.md §B1 草图把 modules 当系列级可写字段，
   但现实 schema `ModuleCreateAdmin` 需 cohort_id/lesson_count/total_hours/stage_no/start_date/end_date
   （模块必须挂班次之下，service 无「系列级模块直挂」写入面）。**处置**：modules 作为可选参数
   精确校验（list[str]）后仅登记进回执 `modules_requested` + `modules_note` 如实标注
   「未创建班次/模块（需先建 cohort，走管理端）」，不谎报落库——与 W-NEXT-MCP-001
   「回执如实反映真实写」红线一致。

## 三、闸 1-3 落地

### 闸1 executor（`app/mcp/executor.py`）
- `_course_create_handler` + `register_builtin_tool("course_create", ..., write_class=True)`；
  `_BUILTIN_WRITE_CLASS_NAMES` = {course_create, favorite_add, knowledge_import}
- **双保险（P4）**：handler 首行校验 `_EXEC_CONTEXT["hitl_confirmed"]`，未确认 →
  `AppException(code=42201)`（新常量 `COURSE_CREATE_UNCONFIRMED_CODE`，422xx→HTTP 422 自动映射），
  service 零调用。注入面：`call_tool` / `call_tool_with_retry` 的 `_EXEC_CONTEXT.set(...)` 增加
  `"hitl_confirmed": bool(hitl_decision is True)`——仅 resume confirm 批准时为 True，
  LLM/args 伪造结构性不可达（与 favorite_add「user_id 服务端注入」同构）。
- arg_schema `COURSE_CREATE_ARG_SCHEMA`：title(str,minLength 1)/series_code(str,`^[a-z0-9_]+$`)/
  modules 可选，additionalProperties False；handler 内 exact-pin 手工校验同构 knowledge_import。
- 单一执行事实源：`course_admin.service.create_series`（唯一约束 40901 冲突结构化回传
  `{"ok":False,"code":"40901",...}`，严禁伪装成功）。

### 闸2 permission_gate（`app/ai/permission_gate.py`）
- `CONTRACT_PENDING_TOOLS` 删 course_create（8→**7**）；`TOOL_CLASS_MAP["course_create"]="admin_write"`
  （P2：仅 admin，manager=deny——原挂起 course_write「manager 放行」矩阵语义变更已批）；
  注册面 9→**10**（REGISTERED_BUILTIN_TOOLS 5 + MCP 5）；`REGISTRY_EVIDENCE` 补出处；
  `_PUBLIC_READ_EXCLUDE` 增 course_create；头部修订记录补 T12 段。
- P2 语义变更（medium→high）按批定执行：course_create 从 course_write 挂起类别迁入
  admin_write 实物类别，`_hitl_risk_level` 自动 medium→high，无需改判定函数。

### 闸3 HITL 链（零改动核验 + 接线补齐）
- `_hitl_risk_level("course_create")` = **high**（classify_tool_intent 单一事实源自动生效，
  实测打印确认；course_update 仍 medium、favorite_add 仍 None、knowledge_import 仍 high）。
- pending_confirm 五字段帧全链：tool_calling.on_write_class_pending → graph_stream
  `_enrich_hitl_pending_payload`（risk_level=high、timeout_s=300、thread_id）→
  `sse_line("pending_confirm", ...)`；E2E 实测帧见下文场景①。
- resume confirm→执行 / reject→零落库：E2E 场景②③实证（下方）。
- 接线补齐（对齐 favorite_add 先例三处）：
  - `tool_calling._BUILTIN_TOOL_DESCRIPTIONS` 补 course_create 描述（工具发现面）；
  - `_parse_heuristic` 新增建课分支：**标题+系列码同现才触发**；关键词兜底空参跳过
    （防闲聊「怎么创建课程？」误弹卡——T7 盲测防线）；
  - `rule_router._TOOL_PATTERNS` 补建课意图（intent=tool 路由）；
  - `subagents/definitions.yaml` tool 子代理清单补 course_create（含「需 HITL 确认、
    未确认 42201 拒」提示）。

## 四、测试数字

- 新增 `tests/test_tool_course_create.py`：**30 passed**（时光.md §B4 T1-T8 全落：
  T1-T3 schema 三态/exact-pin 13 例；T4 未确认 42201+service 零调用×2；
  T5 确认执行+40901 回传×2；T6 risk=high+五字段帧+SSE 字节级×3；
  T7 矩阵 deny+student 诱导零卡×2；T8 审计双路径×2；注册强属性/迁移/禁缓存/arg_schema 对账/
  启发式正反例×5）
- 同步：`test_permission_gate.py`（挂起 7/注册面 10/写类名 9/teacher deny 参数化改 question_*、
  新增 T12 迁移用例）；`test_tool_favorite_add.py`（course_create medium→high 语义锁定）
- 回归：`pytest tests/ -k "tool or permission or hitl or favorite or course" -q`
  → **280 passed, 53 skipped, 7 errors**。7 errors 全部为
  `test_course_admin_restore.py`(4) + `test_course_admin_json_columns.py`(3) 的
  **urllib URLError（本机 9988 未起时 fixture 依赖）**，stash 本轮改动后复跑仍复现 → 预存环境性，与本次无关。
- 专项邻域：`test_r11_hitl + test_hitl_fix_integration + test_wnext2_write_tools +
  test_chat_tool_calling + test_contract_taskP1L + test_receipt_guard` → **86 passed, 2 skipped**。

## 五、E2E 实弹（真实 HTTP + DB 复核）

**HITL_ENABLED 开关前后值（铁律3）**：
- 改前：`.env` 无生效 `HITL_ENABLED` 行（第 92 行注释尾含乱码 `HITL_ENABLED=True` 字样，
  pydantic 未读取）→ settings 实际 **False**
- 验收窗口：`.env` 尾追加 `HITL_ENABLED=true`（含 `AUTO20-T12-E2E-TEMP` 标记注释）→ **True**
- 改后：删除临时两行，diff 对账 `.env` 与原始状态仅差临时行（已删）→ settings **False**；
  重启后端 → `/health` **200** ✓

| # | 场景 | 实测结果 |
|---|---|---|
| ① | admin「帮我创建一门新课，标题'HITL实弹测试课'，系列码 hitl_test_001」流式 | `event: start → pending_confirm → done`；帧体五字段齐：thread_id=s_bbb5f351fff7 / tool_name=course_create / args={title,series_code} / **risk_level=high** / timeout_s=300 ✓ |
| ② | resume action=reject → 重开流 | resume 200 `{status:rejected}`；续流 done degraded_reason=`hitl_rejected_no_pending`，答案「已取消该高风险操作，工具未执行，也没有发生任何数据变更。」；DB `series WHERE series_code='hitl_test_001'` = **0 行** ✓ |
| ③ | 再触发 → resume action=confirm → 续流 | 答案含创建成功语义（工具输出 `{"ok":true,"created":true,...}`）；DB 出现 **id=3135 series_code=hitl_test_001 sale_status=draft**；审计 `mcp_tool_call_log` SUCCESS 行（user_id=100003, args 原文）；`hitl_approval` 行 status=executed（operator=100003, approver=100003）✓ |
| ③b | 数据侧复核（admin API） | `GET /api/admin/courses/series?keyword=hitl_test_001` → 1 item（id=3135）✓；幂等复验：admin API 同参再建 → **409 40901「系列编码已存在」**（时光.md 盲测#5 语义）✓ |
| ④ | 测试数据清理 | `DELETE /api/admin/courses/series/3135` → 200「系列已下架」；`include_deleted=true` 复核 → sale_status=**off_sale**（软删 receipt 留档）✓ |
| ⑤ | student（user000001）诱导「帮我创建课程」（带参数版触发计划） | 事件流**无 pending_confirm**；mcp_tool_calls 内 `course_create error {status:"denied", code:"permission_denied", ...}`；DB `student_induce_001` = **0 行**；未授权者连确认卡都看不到 ✓ |
| ⑥ | 恢复 HITL_ENABLED=false + 重启 | `/health` 200 ✓；运行中 settings.HITL_ENABLED=False ✓ |

（附注：场景③ 首次 confirm 出现 resume 40450 系脚本 bug——先流式探测消耗了待确认标记；
按正确顺序 resume→stream 复跑后全链成功。40450 本身是契约「确认已超时」防御分支的正确表现，
顺带实证。）

## 六、批判自检

1. **modules 不落库**：与草图 B1「modules 可写」不符，但现实 course_admin schema 无系列级模块
   直挂面（硬造=违反铁律4）。回执如实标注，未谎报。后续如需「建课即建模块」，应走变更单
   扩 contract（cohort 也要同批建），非本批范围。
2. **institution_id 服务端兜底取 MIN(id)**：最小化臆造面，但「AI 建课默认挂哪所院校」属产品语义，
   建议后续以 admin 配置或变更单固化（当前取 yn=1 最小 id 可复现、可审计）。
3. **双通道挂起重叠**：E2E 场景③ done 帧出现两条 mcp_tool_calls（success + SKIPPED→error），
   根因 = tool 子代理与流式预取双通道同轮各发一次 course_create（一条 confirm 批准执行成功，
   一条无 hitl_decision 走 HITL gate pending）。写类收口未被绕过（后者零落库、零越权），
   但答案侧「双凭据」观感冗余——**登记为 P1 观察项**：流式续跑时 pending_args 命中后
   可短路启发式重复计划（W-NEXT-CHATFLOW-001 Track A 已做一半，重复计划消除待下一批）。
4. **子代理 exact-pin 拒绝 dict 形 tool 名**（日志 EXACT_PIN_REJECTED invalid_tool_name）：
   LLM 曾把整个 dict 当 tool_name 传入被白名单拒——fail-closed 正确行为，未造成执行；不改。
5. **HITL gate 的 hitl_approval「pending」残留行**（场景③ 首次 40450 遗留 + 场景⑤ student
   被 executor 收口拦下的 gate 前零接触）：pending 行 TTL 由 hitl gate 自管，无越权风险；
   student 路径实证「未授权不进 HITL 审批队列」（executor._deny_if_write_class 在 gate 前）✓。
6. 铁律逐条：分支 ✓ / 只 add 精确路径 ✓（HEAD 对账 e7d7176 前为 793f24b，无并行域文件混入）/
   HITL 开关复原 ✓（前后值如上）/ 禁 DB 直写 ✓（清理走 admin API DELETE 软删）/ SQL 参数绑定 ✓
   （新增 SQL 仅 `MIN(id)` 常量查询）/ API key 未出 .env ✓ / create_series 实读存在 ✓。

## 七、验收断言清单（编排者可复现）

- [x] executor 真实注册：`python -c "import app.mcp.executor as ex; print('course_create' in ex._BUILTIN_TOOL_HANDLERS, ex._BUILTIN_WRITE_CLASS_NAMES)"`
- [x] 迁移：`CONTRACT_PENDING_TOOLS` 7 个不含 course_create；`TOOL_CLASS_MAP["course_create"]=="admin_write"`；`audit_registry()` 三差全空
- [x] `_hitl_risk_level("course_create")=="high"`
- [x] 30 例新测试全绿 + 目标面 280 passed（7 errors 预存环境性，已 stash 对照）
- [x] 五字段帧 risk=high（单测字节级 + E2E 场景① 双证）
- [x] reject 零落库 / confirm 真落库 + 审计行 / student deny 无卡（E2E ②⑤ + DB 断言）
- [x] 清理 receipt：DELETE 200「系列已下架」→ off_sale
- [x] HITL_ENABLED 复原 + health 200
