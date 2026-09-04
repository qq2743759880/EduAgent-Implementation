# task59 完工报告 — /admin/questions/[id] 管理端题目解析编辑

> 执行人：前端开发者（Trae）｜阶段：P6｜并行组：W7｜工作量：M
> 日期：2026-08-24｜类型：frontend

## 1. 一页摘要

管理端题目「编辑/解析」详情页已按 **HTML 原型 → APPROVED → React** 流程重写，落地 **contract④（task13）question 单题域**。核心达成：

- **编辑/预览双态**：Edit 态表单可编辑题干/答案/解析/选项；Preview 态用 `MarkdownView` 渲染题干 + 解析，与用户端 QuizPanel 一致的 Markdown/LaTeX 呈现。
- **题型联动**：按 `dim_question_type` 动态切换选项控件——单选→RadioGroup、多选→Checkbox、判断→固定「对/错」按钮、填空/简答→「不提供选项编辑器」提示；**已填选项数据在切换间不丢失**（options 独立 state，仅 UI 形态随 typeCode 变化）。
- **解析必修**：`analysis_text` 为空时前端 `validate()` 拦截（不调 PATCH）+ 行内提示；后端 `min_length` 仍兜底返回 422（契约④双保险）。
- **objective 徽章只读派生**：客观·自动判题 / 主观·人工批改 由 `dim_question_type.objective_flag` 派生展示，**不纳入 PATCH 提交体**（非 question 字段）。
- **保存持久化**：PATCH `/api/admin/questions/questions/{id}`，payload 含 `question_type_id / stem / answer_text / analysis_text / options_json`；成功 invalidate 相关 query 并返回题库列表。
- **旧契约清理**：重写文件头时移除 task03/v0.2.0 的 `text-slate-500` 灰系与旧 `QuestionForm / tag_ids` 引用，无残留。

## 2. GWT 验收逐条自查

| # | Given / When / Then | 结果 | 证据 |
|---|---------------------|------|------|
| G1 | Given 单选题目详情，When 渲染，Then 默认 RadioGroup 选项控件 + 客观徽章；切换判断→固定对/错；切填空→无选项提示 | **PASS** | `QuestionDetailEditor.tsx` `curMeta` 派生 `typeName`/`objective`/`isChoice`；`typeCode === "single_choice"`→RadioGroup、`"multi_choice"`→Checkbox、`"true_false"`→固定 √/× 按钮、`fill_blank|short_answer`→「该题型不提供选项编辑器」；首次选中符合题型的选项（`chosenLabels`），单选点选即写 answerText |
| G2 | Given 已填数据，When 单选填 A→切多选→切回单选，Then 选项内容与选中态完整保留不丢 | **PASS** | options 内控独立于 typeCode state；`addOption/removeOption/updateOptionContent` 操作 string[]，切换只改 `mode`，数据不重置；`[id]/page.test.tsx`「题型切换已填数据不丢」「Hello!」跨切换断言 |
| G3 | Given `analysis_text` 为空，When 点击保存，Then 前端拦截不调 PATCH + 提示解析必填；填空值时 PATCH `/questions/{id}` payload 含 analysis_text/options_json 全字段 | **PASS** | `validate()`：`!analysis.trim()` → `errs.analysis = "解析（analysis_text）为必填…"` 且 `save.mutate` 不被调用（测试断言 `updateMock` not toHaveBeenCalled）；`submitPayload()` 组装 5 字段 → `updateQuestion(id, payload)`；GWT② 两条测试全绿（拦截 + payload objectContaining 断言） |
| G4 | Given objective 能力，When 展示徽章，Then 由 objective_flag 派生（客观·自动判题/主观·人工批改），PATCH 不提交该字段 | **PASS** | `ObjBadge` 组件按 `objective` 渲染两态徽章（语义 token `bg-candy-green-soft/text-candy-green` 与 `bg-candy-purple/10/text-candy-purple`）；`submitPayload` 仅含 question_type_id/stem/answer_text/analysis_text/options_json，无 objective_flag |

## 3. 数据面盘点与契约对齐附注（contract④）

- 对齐源：`.opencode/handoffs/task13-contract.md`（契约冻结④，L1 权威）＋ task59-fe-admin-question-detail.md。
- **新增长点**（`lib/api/admin/question-bank.ts`，前缀 `/api/admin/questions`）：
  - `GET /questions/questions/{id}` → `QuestionDetail`（含 `analysis_text`，编辑页回填）；
  - `PATCH /questions/questions/{id}` → `{updated,id}`（body 五字段，analysis_text min_length 兜底 422）；
  - `GET /banks/{bank_id}` → `QuestionBank`（面包屑/头部题库名回填）。
- **字段 snake_case**：`stem/answer_text/analysis_text/options_json/objective_flag/question_type_id`；`QuestionUpdateInput` 严格对齐 PATCH 契约。
- **错误分支**：422（analysis_text 必填，前端已先拦）经 `messageOf` 归一为行内错误提示；`updateQuestion` 失败沿用 adminPatch 写操作必抛约定（R-7），交由 mutation `onError` 呈现——不做静默吞掉。
- **institution 归属**：复用 `dim_question_type` / `dim_question_bank` 只读引用，详情页不落任何 new write 表，无数据面副作用。

## 4. 交付物清单

| 类别 | 文件 | 说明 |
|------|------|------|
| 原型 | `test-reports/fe-html/admin-question-detail.html` | 已 APPROVED；题型切换联动、四选项示例、解析必修提示、客观/主观徽章、Markdown 预览演示 |
| API 层 | `edu-frontend/src/lib/api/admin/question-bank.ts` | 新增 `getQuestion/updateQuestion/getBank` + `QuestionDetail/QuestionUpdateInput` 类型 |
| 组件 | `edu-frontend/src/components/admin/QuestionDetailEditor.tsx` | 编辑/预览 Tabs、题型联动选项操控、解析必修校验、objective 派生徽章、MarkdownView 预览、保存 invalidate + 跳转 |
| 页面 | `edu-frontend/src/app/(admin)/admin/questions/[id]/page.tsx` | 并行 useQuery 拉题目详情/题型/题库，加载/错误态，渲染编辑器 |
| 测试 | `src/lib/api/admin/question-bank.test.ts`（+2 API 用例） | `getQuestion` 返回含 analysis_text 详情、`getBank` 题库详情；`updateQuestion` PATCH body 五字段断言 |
| 测试 | `src/app/(admin)/admin/questions/[id]/page.test.tsx`（5 页面用例） | GWT① 题型联动 + 已填数据不丢 + 客观/主观徽章；GWT② 解析必修前端拦截 + 保存 payload 持久化 |

## 5. 质量门禁

| 门禁 | 结果 |
|------|------|
| css 纪律审计 5 项（hex/内联色/禁闭色/任意字号/灰系） | task59 源文件真命中全 0（`gray` 仅 page.tsx 文件头注释描述"清理灰系"文字，非代码类名；语义 token 均见 globals.css：candy-green-soft/candy-purple/primary-soft） |
| Vitest 全量 | **69 文件 476 测试 PASS**（本任务新增 2 API + 5 页面 = 7；修复：objective 徽章双处渲染改 `getAllByText`、`adminGet` 单参恒拼 `{params:undefined}` 改断言） |
| TypeScript `tsc --noEmit` | 0 错误 |
| ESLint | task59 文件 0 error / 0 warning（清理 editor 的 onSuccess 冗余参数、测试未用 `stemInput`） |
| Next `next build` | 成功，`/admin/questions/[id]`（ƒ Dynamic）路由注册正常 |
| 独立测试子代理 | `[id]/page.test.tsx` 断言题型切换联动、解析必修拦截（不调 PATCH）、保存 payload、两类徽章派生 |

## 6. 已知边界 / 后续

- **objective 只读派生**：客观性徽章由 `dim_question_type.objective_flag` 派生展示，非 question 字段，编辑页不可改、PATCH 不提交——与 contract④ 设计一致（客观性由题型表冻结）。
- **多选题答案回填**：`chosenLabels` 仅对单选首次回填选中高亮；多选/判读的 answerText 以文本形式在答案框编辑，后续如需多选选项点击勾选可扩展（非本次契约范围）。
- **后端兜底隐藏**：前端已拦截空解析，后端 422 仅作为契约双保险；不会到达用户侧（前端永远先拦）。
- **菜单高亮/面包屑**：返回题库列表用 `router.push("/admin/questions")`，与 task58 两级 Tab 承接，无新端点。

---
> 运行 `D:\.ai-hub\sync.ps1` 分发后，等待编排者 task59=DONE 验收指令，再进入 task60。