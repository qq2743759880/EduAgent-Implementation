# W-NEXT-QUESTIONFORM-FIX-001 完成报告（legacy QuestionForm 死簇处置）

- 变更单：W-NEXT-QUESTIONFORM-FIX-001（FEBE-SCAN-002 报告 follow-up 第 1 条销项）
- 执行：ZCode 独立会话，分支 `feature/opt-waves`（起点 5059246）
- 日期：2026-09-18
- **代码提交：`fc6f856`**（feature/opt-waves；本报告随 chore 提交补登该 hash）
- lock：`edu-agent/scripts/eval/wnextqform1.lock` 已于 commit 前删除

---

## 1. 处置路线与理由

**路线：① 删除（任务二选一中的删除路线）。**

取证结论（详证见 §2）：QuestionForm 组件**零挂载、零活 import**——全仓唯一 import 语句是组件自身测试 `QuestionForm.test.tsx:16` 的 `from "./QuestionForm"`；其余全为注释/历史报告提及。选删除而非重写（路线②）的理由：

1. **活 UI 已有正确契约实现**：题目创建/编辑活入口 = `/admin/questions` 两级管理页 + `QuestionDetailEditor` + `BankImportDialog`，全部走 `question-bank.ts`（自包含，imports 仅 `@/lib/api/admin` 与 `@/lib/admin-api-types`，实测确认），其真实路由契约已在 FEBE-SCAN-002 以真 token curl 实证（POST→201 id=10557 / PATCH→200，处置表 rows 2/4）。
2. **重写无服务对象**：路线②（按 QuestionAdminCreate 重写 payload）= 给一个不存在的 UI 入口重写表单，且新旧契约字段逐字段不匹配（见 §3 表），重写成本全部花在无人使用的代码上。
3. **body 契约风险面清零**：删除后「即便路径正确也 422」的草稿 payload 彻底不存在，优于任何"注释披露"态。

## 2. 取证证据（grep 输出摘录）

**2.1 组件 import/挂载点（全仓，git grep，删除前采集）**

- `grep -rn "from .*QuestionForm" src/` → **唯一命中**：`src/components/admin/QuestionForm.test.tsx:16: } from "./QuestionForm";`（组件自身测试）
- `git grep -n "QuestionForm"`（全仓全部跟踪文件）：代码命中仅 `QuestionForm.tsx` / `QuestionForm.test.tsx` / `controls.tsx:6,17`（注释） / `questions.ts:128,131`（follow-up 披露注释） / `[id]/page.tsx:1`（task59 过去式历史注释）；其余 16 文件全部为历史报告/计划存档（`.ai-hub/plans/*`、`test-reports/8.16前/*`、task48/59/critique-task69 报告等）。
- **页面/路由零挂载**：`src/app/**` 下零 `QuestionForm` import（`[id]/page.tsx` 用 `QuestionDetailEditor`，`/admin/questions` 页走 `question-bank.ts`）。

**2.2 questions.ts 模块消费面（逐导出符号 grep，排除 QuestionForm 自身）**

| 导出 | 模块外消费者 | 判定 |
|---|---|---|
| `createQuestion` / `updateQuestion` / `QuestionCreateInput` | 仅 questions.test.ts（自身测试） | 死封装，删 |
| `listQuestionTags` / `QuestionTag` / `QuestionAdminDetail` / `QuestionOption` | 零（learning.ts 的 QuestionOption 是**独立同名定义**，非 import） | 死，删 |
| 题型/学科/难度枚举、`questionTypeLabel` 等、`TRUE_FALSE_ANSWERS`、`buildOptionLabels` | 仅自身测试 | 保留（见 §6 自批判 1） |

- `vi.mock`/动态 `import()`/barrel index.ts 三类隐蔽引用：**零命中**。
- `updateQuestion` 其余命中全部为 `question-bank.ts:194`（同名活实现）及其消费者（QuestionDetailEditor.tsx:18、page.test.tsx:11、question-bank.test.ts:24、quiz-preview-parity.test.tsx:22）——与被删封装同名不同模块，不受影响（tsc 绿即证）。

**2.3 controls.tsx 附随取证**

`TagChip` / `NO_TAG_HINT` 消费者 = **仅 QuestionForm.tsx**（`grep -rln "TagChip\|NO_TAG_HINT" src/` → controls.tsx 定义处 + QuestionForm.tsx）。历史注释 D-10 声称"QuestionForm / ComposePaperDialog 共用"——实测 ComposePaperDialog 从未引用（历史注释本已失真）。

## 3. 被销 body 契约差距（字段对照，证据：edu-agent/app/domains/question_admin/schemas.py:57）

| QuestionAdminCreate（后端真实必填） | 旧 QuestionCreateInput（task03 草稿，已删） |
|---|---|
| `bank_id: int`（必填） | **缺失** |
| `question_type_id: int`（维表主键） | `question_type: string`（枚举 code）——类型与语义双不匹配 |
| `stem: str`（必填） | `stem_html: string` |
| `answer_text: str`（必填） | `correct_answer: string` |
| `options_json: Optional[Any]` | `options_json: [{label,content}]`（形状未证伪但未证实） |
| `analysis_text: Optional[str]` | `analysis_html` / `correct_answer_detail` |
| — | 多余字段：`subject_code` / `difficulty_level` / `default_score` / `knowledge_point_codes` / `tag_ids`（后端 schema 无） |

## 4. 变更清单（仅本任务文件域）

| 文件 | 处置 | 行数变化 |
|---|---|---|
| `edu-frontend/src/components/admin/QuestionForm.tsx` | **整删**（git rm） | -595 |
| `edu-frontend/src/components/admin/QuestionForm.test.tsx` | **整删**（git rm，13 用例随组件消亡） | -196 |
| `edu-frontend/src/lib/api/admin/questions.ts` | 删死封装 `createQuestion`/`updateQuestion`/`QuestionCreateInput`/`listQuestionTags`/`QuestionTag`/`QuestionAdminDetail`/`QuestionOption` + `adminPost/adminPatch` import；文件头改写为收口记录 | 178→92 |
| `edu-frontend/src/lib/api/admin/questions.test.ts` | 删 3 个死 body 契约用例（createQuestion 透传/PATCH 路由/409 抛错）及 http mock 脚手架；保留题型枚举+label 用例 | 85→32 |
| `edu-frontend/src/components/admin/controls.tsx` | 删 `TagChip`/`NO_TAG_HINT`（唯一消费者 QuestionForm）+ 头注释收口；FieldRow/NativeSelect/focusFirstFieldError/三态有大量活消费者，保留 | 198→167 |
| `test-reports/WNEXTFEBESCAN2-completion-report.md` | §8 follow-up 第 1 条标记**已销**（划线保留原文 + 销项记录） | 1 行改写 |
| `test-reports/WNEXTQFORM1-completion-report.md` | 新增（本报告） | — |

红线遵守：未触碰 `edu-frontend/public/**`、`deploy.mjs`、`edu-agent/app/**`；工作区中 `deploy/README.md`、`edu-agent/app/**`、`check-demo.mjs`、`be-task01-hit-report.md` 等改动系**其他会话的既有未提交改动**，本任务未触碰、不入本任务提交（commit 仅 add 本任务 7 文件）。

## 5. 验证输出

1. **tsc**：`npx tsc --noEmit`（edu-frontend）→ **exit 0，零输出**（删后无任何悬空 import/类型）。
2. **vitest**：
   - 全量第 1 跑：`1 failed | 537 passed (538)`——失败例 `src/app/(user)/me/page.test.tsx:70` `findByText("慕剑知")` 超时。**与本任务文件域零交集**（该文件仅 import `@/lib/api/me`/`@/lib/api/community`，grep 证实）；
   - 该文件隔离复跑：**2/2 passed**（4.32s）；
   - 全量第 2 跑：**79 文件 / 538 用例全部通过**（63.75s）。判定：并行负载下瞬时竞态 flake，非本任务引入（见 §6 自批判 3）。
3. **残留 grep（删除后）**：
   - `git grep QuestionForm -- edu-frontend/src` → 仅 3 类：本次收口注释（questions.ts/questions.test.ts/controls.tsx 文件头，刻意留档）+ `[id]/page.tsx:1` 过去式历史注释（见 §6 自批判 2）；**零 import、零标识符引用**。
   - 死符号（`createQuestion`/`QuestionCreateInput`/`listQuestionTags`/`NO_TAG_HINT` 等）在 `*.mjs/*.js/*.json/*.py`：**零命中**；`src` 内命中均为收口注释或 question-bank 同名活封装。
4. **测试数对账**：删前 554（538+QuestionForm.test 13+questions 死用例 3）→ 删后 538，差值 16 与删除清单一致，无"顺带丢测试"。

## 6. P0 自批判（≥3）

1. **questions.ts 残留零消费 display utils 的裁量**：删组件后，保留的枚举/`questionTypeLabel`/`TRUE_FALSE_ANSWERS`/`buildOptionLabels` 同样零模块外消费者。保留理由：follow-up 原文口径是「整体删除 legacy QuestionForm + 本文件**死封装**」（封装=API wrapper，body 构造），枚举/label 是后端契约对照的展示层文档且有 2 个活测试锁定；若按最激进口径应整文件删除。风险：未来批判可能判"半死不活"；回退成本 = 删 92 行文件+对应用例，零 import 面，一次 Edit 的事。
2. **`[id]/page.tsx:1` 历史注释未清**：红线「禁碰 app/**」歧义（edu-frontend/src/app/** vs 后端 edu-agent/app/**）+ 该句是 task59 已发生事实的过去式记录（非活引用），按不越权+不篡改历史保留。若验收判"零残留"须含此行，一行 Edit 可补清——口径分歧已如实登记而非悄悄处理。
3. **flake 归因未采集 HEAD 基线**：全量首跑的 1 例失败未在改动前基线（HEAD 全量）复现对照，"非本任务引入"的判定依据是文件域零交集 + 隔离复跑绿 + 全量复跑绿，而非双基线 diff。残余风险：若为偶发翻牌型 flake 则与本改动无关但未根治（不在本任务文件域，不扩大处理面）。
4. **TagChip/NO_TAG_HINT 删除超出"组件专属文件"字面范围**：controls.tsx 是共享控件文件；删除依据是消费面实证（唯一消费者=QuestionForm）+ 留下即死代码且 D-10 注释永久失真。风险：并行分支若基于旧 controls.tsx 新增 TagChip 消费，合并时冲突——git 历史可恢复，且文件头收口注释已声明删除时点与理由。
5. **删除路线销掉"重写路线"参照物**：`QuestionCreateInput` 类型消失后，未来若需单题创建 UI 必须按 QuestionAdminCreate（`bank_id`/`question_type_id` 维表 int/`stem`/`answer_text`）从零构造——旧草稿的"题型=枚举 code"心智模型不再有代码载体。已在 questions.ts 文件头留 schema 指针（schemas.py:57）作为重写时的契约入口。

## 7. 批判承接核对

- **FEBE-SCAN-002 §7 P0-1 披露的 follow-up**（= 本任务来源）：**已销**（本报告 §1-§5；WNEXTFEBESCAN2 报告 §8 已同步标记）。
- **FEBE-SCAN-002 §8 其余两条**（`_frontend_real_api.txt` 93→144 代差刷新、`GET /api/admin/users/{id}/learning` 后端开放后恢复封装）：不在本任务文件域，**无承接**。
- **历史批判回溯**：task59 批判②（题型切换旧答案残留，61989bb）的修复对象即 QuestionForm——其修复成果（`applyTypeSwitch` 及 5 边界用例）随组件整体消亡。判定：**不构成回退**，被修复物本身已不存在；活编辑器 QuestionDetailEditor 的保存路径由 `[id]/page.test.tsx`（mock question-bank.updateQuestion 断言 payload）独立锁定，vitest 绿。critique-backlog-tracker 无指向本任务的其他未闭环项。**承接结论：无承接项。**

## 8. 资产消费证据

| 具名资产 | 消费方式 |
|---|---|
| `edu-frontend/src/lib/api/admin/questions.ts` | 全文读取（178 行，权威封装 + follow-up 披露）→ 定位死封装边界 → 修剪至 92 行 + 收口注释 |
| `test-reports/WNEXTFEBESCAN2-completion-report.md` | §1 处置表 rows 2/4（真实路由+201/200 curl 实证）、§7 P0-1（body 契约差距披露）、§8 follow-up 读取 → §8 第 1 条标记已销 |
| `AGENTS.md` | 关键教训 2（禁 Playwright，验收独立实证：tsc/vitest/git grep 真实执行）、教训 8（真实契约优先于页面注释，字段对照以后端 schemas.py 为准） |
| `edu-agent/app/domains/question_admin/schemas.py` | 读取 QuestionAdminCreate（:57）做逐字段对照（§3 表） |
| `edu-frontend/src/components/admin/QuestionForm.tsx` + `.test.tsx` | 删除前全文读取，确认无隐藏导出被外部消费 |
| `edu-frontend/src/components/admin/controls.tsx` | 全文读取 + 逐导出消费面取证 → 修剪 |
| `edu-frontend/src/lib/api/admin/question-bank.ts` | 头部 + `updateQuestion`(:194) 读取，确认活封装自包含、不受删除影响 |
