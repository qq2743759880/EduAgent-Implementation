# W-NEXT-FEBE-SCAN-002 完成报告

- 任务：尾巴③ plan-broken 校验 + 尾巴④ 5 条真断点修复 → 扩 Next.js scanner（合并单，同文件域）
- 派单：orchestrator（C-01 规范）；执行：W-NEXT-FEBE-SCAN-002 子 agent；日期：2026-09-18
- 分支：feature/opt-waves；**本任务 commit：`aa856af7bb41191bdc36aada452d33636f89e276`**（parent `feba06d1`，纯前向；任务起点 tip 为编排者登记的 `896030f`，提交前 tip 已被并行 agent 前移至 `feba06d1`，已按纪律以提交时刻 tip 为 parent）
- 文件清单（全部为本任务文件域，**未触碰** check-demo.mjs / ci.yml / deploy_env_gate.mjs）：
  - `edu-agent/scripts/eval/febe_contract_check.py`（扩扫 + query-suffix 归一 + plan_broken 校验）
  - `edu-agent/tests/test_febe_contract_check.py`（18 → 26 用例）
  - `edu-frontend/src/lib/api/admin/questions.ts` / `questions.test.ts`
  - `edu-frontend/src/lib/api/admin/users.ts`
  - `edu-frontend/src/components/admin/UserLearningDialog.tsx` / `UserTable.test.tsx`
  - `edu-frontend/src/components/profile/BasicProfileForm.tsx` / `PreferencesForm.tsx`
  - `test-reports/_frontend_migration_status.json`（重新生成）
- lock：`edu-agent/scripts/eval/wnextfebescan2.lock` **未创建/不存在（清空态）**，提交前后均确认 absent。

---

## 1. 断点逐条处置表（真实路由证据 + 修法）

父任务按「路径归并」报 5 条；按 (method, path) 实测为 **9 对**（`GET/PATCH/DELETE /api/admin/questions/{x}` 共用同一字面量模板），9 对全部处置。处置后扩扫 `breakpoints=0`。

| # | 断点 (method path) | 调用现场 | 后端真实契约（openapi.json + router.py 权威） | 修法 | 真 token 实证 |
|---|---|---|---|---|---|
| 1 | GET /api/admin/questions | `questions.ts listQuestions`（死：全仓库 grep 零引用） | 后端**无跨题库题目总列表**；等价能力 = `GET /api/admin/questions/banks/{bank_id}/questions`（router.py:117），live 封装 `question-bank.listBankQuestions`（/admin/questions 页在用） | **删死封装**（避免与 question-bank 双轨发散）；列表唯一入口保留 question-bank | `GET /api/admin/questions/banks/449/questions` → **200** |
| 2 | POST /api/admin/questions | `questions.ts createQuestion`（下游 QuestionForm，legacy 未挂载） | `POST /api/admin/questions/questions`（router.py:141，QuestionAdminCreate） | **修路径** | `POST /api/admin/questions/questions` → **201**（id=10557，验证后 DELETE 清理） |
| 3 | GET /api/admin/questions/{x} | `questions.ts getQuestion`（死：[id] 页实际 import question-bank.getQuestion，路径本就正确） | `GET /api/admin/questions/questions/{question_id}` | **删死封装**（活引用全在 question-bank） | `GET /api/admin/questions/questions/10557` → **200** |
| 4 | PATCH /api/admin/questions/{x} | `questions.ts updateQuestion`（QuestionForm legacy） | `PATCH /api/admin/questions/questions/{question_id}` | **修路径** | `PATCH …/questions/10557` → **200** {updated:true} |
| 5 | DELETE /api/admin/questions/{x} | `questions.ts deleteQuestion`（死：page.tsx 用 question-bank.deleteQuestion） | `DELETE /api/admin/questions/questions/{question_id}` | **删死封装** | `DELETE …/questions/10557` → **200** {deleted:true,id:10557}（清理临时数据） |
| 6 | GET /api/admin/users/{x}/learning | `users.ts getAdminUserLearning` → UserLearningDialog（每次打开必 404） | **后端确无等价路由**（user_admin/router.py 仅 list/role/status/dashboard-metrics；实测 `GET /api/admin/users/100001/learning` → **404 code 40400**） | **删死调用**（users.ts 封装+类型全删）；UserLearningDialog 改为直接渲染缺口占位（字段结构预览，不发死请求、不写 MOCK）；UserTable.test 断言同步为「不发死请求 + 缺口披露」 | 404 证据 + 组件降级由 UserTable.test 5/5 锁定 |
| 7 | PATCH /api/users/me（BasicProfileForm:63） | 基本资料表单保存 | `PUT /api/users/me/profile`（users/router.py:31，UserProfileUpdate 全 Optional，None=不改） | **修方法+路径+字段映射**：`{nickname, avatar_url}`（avatar→avatar_url） | `PUT /api/users/me/profile`（表单形状，现值写回）→ **200** |
| 8 | PATCH /api/users/me（PreferencesForm:88） | 偏好设置表单保存 | 同上 | **修方法+路径+字段映射**：`learningGoal(单串)→learning_goals[1 项]`；`subjectPreferences(SubjectKey[])→subject_preferences[{subject_code, preference_score:5}]`（1-5 分制表单无分值概念，5=特别喜欢） | `PUT /api/users/me/profile`（该形状，现值写回）→ **200** |
| 9 | 对照组 | — | 旧 `PATCH /api/users/me` 实测 → **405**（Method Not Allowed，证明旧路由从未存在）；`GET /api/enrollments/me/cohorts`、`GET /api/progress/courses`（扫描器 query-suffix 归一后的真实路由）→ **200** | — | 16/16 PASS |

curl 实证共 **16/16 PASS**（见 §4；无 DB 直写，POST/PATCH 均以「创建后即删」「现值写回」零语义变更方式执行）。

## 2. 扩扫实现与 SUMMARY 对照

扩扫内容（`febe_contract_check.py`）：
- `scan_frontend()` = 原_public 扫描（public/*.html + edu-api.js，口径不变）∪ **`scan_frontend_src()`**：递归扫 `edu-frontend/src`，识别 `http.get/post/put/patch/delete`（api-client 封装）与 `adminGet/adminPost/adminPatch/adminDelete`（一层嵌套泛型 `<AdminPage<X>>` 可解析），复用既有 EAPI/fetch/xhr 正则；
- 排除 mock 域：`*.test.*` / `*.spec.*` / `*.stories.*` / `*.d.ts` / `node_modules` / `.next` / `__tests__`（测试 fixture 的假路径如 `/api/auth/anything` 不是对 8000 的真实调用，排除理由已写入代码注释）；
- **query-suffix 模板尾巴归一**（历史坑防御）：`` `.../cohorts${qs}` ``、`` `.../series/${id}${q}` `` 这类「非 `/` 分隔的 {x} 尾巴」剥除（合法 URL 路径参数必以 `/` 分隔）；归一前形态逐条打进 `[QUERY-SUFFIX]` 反遮蔽明细行（本次 33 处，全部为 query 尾巴/相邻拼接，无真实路径参数被误伤——单测锁定 4 归一 case + 3 不误伤 case）；
- to_connect **口径未动**（仍 = 后端路由 − 前端调用，纯集合差，无白名单遮蔽）。

SUMMARY 对照（`--quiet`）：

| 指标 | 扩扫前（parent） | 扩扫后（本任务） | 变化来源 |
|---|---|---|---|
| breakpoints | 0（但 src 未纳入扫描，漏检 9 对） | **0**（9 对已修） | 断点根因修复 |
| in_use_unfrozen | 0 | **0** | 后端 210 ⊆ 契约 236，新增在用全有契约 |
| unfrozen_only | 0 | **0** | 不变（⑪ 门判据不变） |
| to_connect | 109 | **66** | frontend 101→144：43 条 src-only 调用真实转入在用（口径未动，数字如实登记；单测常量 66 附变更单注释 W-NEXT-FEBE-SCAN-002） |
| frontend | 101 | **144** | public 101（不变）+ src 130（其中 43 条为新 uniq） |
| backend / contracts / malformed | 210 / 236 / 0 | 210 / 236 / 0 | 不变 |

治理分桶（emit_migration_status，`total=66`）：plan **6**（原 10，4 条因 src 已在用而转出：banks GET、banks/{x}/questions GET、rag rebuild POST、student-profile GET）/ deferred **28** / ops **6** / unassigned **26** / **plan_broken 0** / uncategorized 0（6+28+6+26=66 全覆盖）。

## 3. 尾巴③：plan 桶后端合法性校验

- 新增 `plan_bucket_broken(be_routes)`：`NEXTJS_PLANNED_ENDPOINTS − be_routes`，plan 桶每条必须真实存在于后端 OpenAPI；不合法项此前会被 `plan ∩ to_connect` **静默吞掉**，现在显式进入 **plan_broken 桶**；
- 输出：非 quiet 在 `[PLANNED-BREAKDOWN]` 段打印 `plan_broken N 条` + 每条 `⚠️ METHOD PATH 不在后端 OpenAPI` 警告行；**quiet 模式也输出 `[PLAN-BROKEN]` 警告行**（⑩/⑱ 只解析 [SUMMARY] 行，不受影响）；`--emit-migration-status` 新增 `plan_broken` 桶段 + `summary.plan_broken` 计数；
- 语义为 **WARN 不阻断**（不改 ⑩ 红判据，单测锁定注入场景 rc==0）；
- 真实后端：**plan_broken=0**（10 条 plan 全部是后端合法路由，逐条 openapi 对账 YES）；
- 单测锁定：「plan 桶 ∩ 后端路由 = plan 桶」（`test_plan_bucket_all_routes_exist_on_real_backend`）+ 注入缺路由后端必报警（`test_plan_broken_flagged_when_backend_lacks_route`、`test_plan_broken_explicit_bucket_in_nonquiet_output`）。

## 4. 真 token 实证（16/16 PASS，curl/urllib 真实 HTTP）

```
PASS POST /api/auth/login (admin adm02test)                        -> 200
PASS GET  /api/admin/questions/banks                               -> 200
PASS GET  /api/admin/questions/banks/449/questions                 -> 200   (#1 等价列表路由)
PASS GET  /api/admin/questions/types                               -> 200
PASS POST /api/admin/questions/questions                           -> 201   (#2 修路径；BPSCAN2-* 临时题)
PASS GET  /api/admin/questions/questions/10557                     -> 200   (#3)
PASS PATCH /api/admin/questions/questions/10557                    -> 200   (#4)
PASS DELETE /api/admin/questions/questions/10557                   -> 200   (#5，数据已清理)
PASS GET  /api/admin/users/100001/learning                         -> 404 (code 40400)  (#6 缺口证据)
PASS POST /api/auth/login (student user000001)                     -> 200
PASS GET  /api/users/me/profile                                    -> 200
PASS PUT  /api/users/me/profile {nickname, avatar_url}（现值写回）   -> 200   (#7 表单形状)
PASS PUT  /api/users/me/profile {learning_goals, subject_preferences}（现值写回）-> 200 (#8 表单形状)
PASS PATCH /api/users/me                                            -> 405  (旧断点路由对照：不存在)
PASS GET  /api/enrollments/me/cohorts                               -> 200  (query-suffix 归一真实性)
PASS GET  /api/progress/courses                                     -> 200  (同上)
```

无 mock、无 DB 直写；POST→DELETE 自清理，PUT 均为现值写回零语义变更。

## 5. 盲测三态

| 态 | 注入 | 结果 |
|---|---|---|
| ① 修复完成态 | —（扩扫 src） | `breakpoints=0 … to_connect=66 frontend=144`，exit **0** |
| ② 假断点注入 | `edu-frontend/src/__bp_blind_probe__.ts` 调 `GET /api/__blind__/no-such-route`（临时文件，验后即删） | `breakpoints=1 frontend=145`，exit **1**（红档生效，扫描器未失明） |
| ③ plan_broken 报警 | 受控后端缺全部 plan 路由（pytest monkeypatch） | `[PLAN-BROKEN]` 警告行列出全部断条（逐条 METHOD+PATH，不只报数字），rc=**0**（WARN 不变红）；非 quiet 模式 plan_broken 行显式可见 |

## 6. 测试与门禁回归

- `pytest tests/test_febe_contract_check.py`：**26 passed**（原 18 + 新 8：query-suffix 归一×2、src 扫描范围/泛型/排除×2、plan_broken×3、扩扫真实 bp=0×1；tc 锁定用例更新 109→66 并附变更单注释）；
- vitest：`questions.test.ts` 断言 URL 同步真实路由（31 passed：admin/question-bank/questions 三件套）；`UserTable.test.tsx` 5/5（断言改「不发死请求 + 缺口披露 + 字段结构可见」）；`tsc --noEmit` exit 0；
- **check-demo 终态：绿 21/21 + WARN ⑧⑩㉒（与基线完全一致）**，`⑩ 契约对账门` 保持 WARN（734ms），`⑱ febe root path 闭环` PASS（unfrozen_only=0 断点=0 在用未冻结=0）。
  - 过程披露：首次全量跑出现 ⑭（内部可见性：login 失败"后端不可达"）⑯（lifecycle start+stop×5）瞬态红 —— 两门与本项目文件域零交集（探针分别为 `wnextint1a_visibility_probe.py` / `_lifecycle_real_verify.py`）；单跑复验均 PASS（⑭ student 0 / admin 25；⑯ 5 轮 0 traceback PASS），系后端重启竞态；复跑全量即恢复 21/21。判定：非本任务引入。

## 7. P0 自批判（≥3）

1. **「删死调用是否真死」**：4 个删除封装（listQuestions/getQuestion/deleteQuestion/getAdminUserLearning）均经全仓库 grep（含 *.test.*）确认零活引用后才删；UserTable.test 原先**断言死调用必须被发起**——只删实现不改断言会造出假红/假绿，已同步改写并由 vitest 锁定。反向风险：questions.ts 的 createQuestion/updateQuestion **未删**（legacy QuestionForm 仍 import），**发现其 body 契约与后端不匹配**（QuestionAdminCreate 真实必填 bank_id/question_type_id/stem/answer_text，而 QuestionCreateInput 是 task03 草稿形状 tag_ids/stem_html/...，即便路径对也会 422）——该组件未挂载无运行时影响，已在 questions.ts 代码注释 + 此处**如实登记 follow-up**（整体删除 legacy cluster 或重写 payload，需任务单裁决），未以「路径修好」掩盖 body 缺口。
2. **「修路径是否对齐真实契约而非猜测」**：全部以 `/openapi.json` + `app/domains/question_admin/router.py` + `app/users/router.py`/`schemas.py` 代码为权威，逐条带真 token 实测（16/16）；并用 `PATCH /api/users/me → 405`、`GET /api/admin/users/{id}/learning → 404 code 40400` 做反向对照，证明旧路由确实不存在，而非"新路径碰巧也能用"。
3. **「扩扫正则路径拼接误截（历史坑）」**：新增 query-suffix 归一规则存在「把 `/api/foo${a}/bar${b}` 之类真实尾段参数误剥」的理论风险。处置：规则限定为**结尾处非 `/` 分隔的 {x} 游程**（路径参数必 `/` 分隔）；33 处命中逐一人工核验全部为 `?query` 模板尾巴/相邻拼接；单测锁 3 个不误伤 case（`/ 分隔参数保留`、`纯拼接 base+"/api/users/"+id`、`?bank_id=${id}` 字面 query）；归一前形态全量打印 `[QUERY-SUFFIX]` 明细（反遮蔽，无静默吞路径）。
4. **「plan 桶处置是否绕过 to_connect 口径」**：plan_broken 是**校验桶**不入 to_connect（其条目本就不在 be_routes，数学上不可能进 tc，故 `classified==total` 断言与 ⑩ 计数口径零影响）；plan_broken=0 与非 0 均显式输出；WARN 语义由单测锁定 rc==0，未私改 ⑩ 红判据。
5. **「tc 109→66 的数字遮蔽风险」**：数字变化完全来自 frontend 101→144（43 条 src-only 调用清单已在验证中逐一列出，全部命中后端真实路由且 ⊆ 冻结契约），to_connect 定义未动；新锁值 66 在两处单测附变更单号（W-NEXT-FEBE-SCAN-002），再漂移必须重新登记——继承原「109 不增不减」的防漂移语义而非放松它。
6. **「前端组件删调用后空态处理」**：UserLearningDialog 删死请求后并非裸空态——保留账号摘要 + 6 指标字段结构预览（label + snake_case 字段名 + '—'）+ 缺口披露条幅（不写 MOCK），UserTable.test 断言空态可见性；PreferencesForm 既有「读回缺口」（auth/me 合并视图 learning_goal 为 list 而 UserInfo 未承载，表单回显恒空）为**先前已存在**且写入 me.ts handoff，本次仅修写入侧并在代码注释标注，未扩大处理面。

## 8. 遗留 / follow-up 登记

- ~~legacy 题库簇（`QuestionForm.tsx` + `questions.test.ts` 的 body 契约差距，见 P0-1）：建议后续任务整体删除或按 QuestionAdminCreate 重写~~；✅ **已销（W-NEXT-QUESTIONFORM-FIX-001，2026-09-18，删除路线）**：全仓 git grep 确证 QuestionForm 零挂载零活 import（唯一 import 为组件自身测试 QuestionForm.test.tsx；questions.ts 模块唯二 importer = QuestionForm.tsx + 其自身测试）→ 整删 `QuestionForm.tsx` + `QuestionForm.test.tsx`，并同步删除 questions.ts 死封装 `createQuestion`/`updateQuestion`/`QuestionCreateInput` 及仅其消费的 `listQuestionTags`/`QuestionTag`/`QuestionAdminDetail`/`QuestionOption`（与后端 QuestionAdminCreate 真实必填 bank_id/question_type_id/stem/answer_text 的 body 契约差距随之消灭，不再存在 422 风险面）；controls.tsx 的 TagChip/NO_TAG_HINT（唯一消费者 QuestionForm）一并删除。验证：`tsc --noEmit` exit 0 + vitest 全量 79 文件/538 用例全绿 + 全仓 grep 死符号零代码残留。证据与自批判见 `test-reports/WNEXTQFORM1-completion-report.md`；
- `test-reports/_frontend_real_api.txt`（旧 public-only 口径 93 条）与 144 的新口径存在代差——不在本任务文件域（派单仅列 `_frontend_migration_status.json` 重生成），建议下次 `--emit-frontend-list` 时一并刷新；
- `GET /api/admin/users/{id}/learning` 后端开放后：按 users.ts 注释恢复封装与 UserLearningDialog 真实渲染（变更单驱动）。
