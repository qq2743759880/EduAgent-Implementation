# task58 完工报告 — /admin/questions 管理端题库（两级 + 批量导入）

> 执行人：前端开发者（Trae）｜阶段：P6｜并行组：W7｜工作量：L
> 日期：2026-08-24｜类型：frontend

## 1. 一页摘要

管理端题库页已按 **HTML 原型 → 用户多次反馈返工 → APPROVED → React** 流程重写，落地 **contract④（task13）两级管理 + 四步批量导入**。核心达成：

- **两级 Tabs**：`题库`（question_bank 列表 CRUD）→ `题目`（选题库后 GET /banks/{bank_id}/questions）。选题库自动切「题目」Tab 并联动请求。
- **题库 CRUD**：新建/编辑（BankFormDialog，40921 bank_code 唯一冲突行内提示）、删除（ConfirmDialog，展示题量警示）、检索（bank_name/bank_code 关键词 + 分页）。
- **题目列表**：按题库展示，题型维表过滤 + 全站关键词（题干/解析/题目编码 LIKE 全文检索）、客观/主观标记、软删确认。「编辑/解析」跳 task59 详情路由 /admin/questions/{id}。
- **四步批量导入**（BankImportDialog）：上传/粘贴 JSON → import-preview 逐行校验 → 导入进度 → 结果报告（imported/skipped/failed + 失败行定位回翻）。幂等（重复 question_code 跳过）。
- **标签废除**：旧 admin_question_tag 标签筛选控件彻底移除，知识点检索统一走 keyword 全文检索。

## 2. GWT 验收逐条自查

| # | Given / When / Then | 结果 | 证据 |
|---|---------------------|------|------|
| G1 | Given HTML APPROVED，When 批量导入 1752 题，Then 预览→确认→进度→结果报告全链路可用，失败行可定位；删除题库二次确认 | **PASS** | `BankImportDialog.tsx` 四步 Stepper（上传/编辑 → 校验/预览 → 导入进度 → 结果报告）；`importPreview` 展示有效/无效计数 + 无效行行号明细；`importExecute` 幂等执行后 imported/skipped/failed 计数 + messages 逐条语义色 + 无效行定位回翻；`ConfirmDialog` 二次确认删除题库（含 `question_count` 题量警示） |
| G2 | Given 两级导航，When 选题库切题目 Tab，Then GET /api/admin/questions?bank_id= 联动；「编辑/解析」跳 task59（J24） | **PASS** | `selectBank` → `setSelected` + `setTab("questions")` → `listBankQuestions(selected.id,…)` 请求 `/banks/{id}/questions`；「编辑/解析」= `Link href=/admin/questions/{id}`（task59 详情路由，动态路由已注册 ƒ Dynamic）；`page.test.tsx` 断言联动调用与 href |
| G3 | Given 检索，When 输入知识点关键词，Then stem+analysis_text 全文检索（无标签筛选控件残留） | **PASS** | 题目 Tab 关键词 Input 占位"题干/解析/题目编码（LIKE 全文检索）"透传 `keyword` → 后端 LIKE stem+analysis_text；页面无任何 tag 筛选控件；grep 无 `admin_question_tag`/TagChip 残留 |

## 3. 数据面盘点与契约对齐附注（contract④）

- 对齐源：`.opencode/handoffs/task13-contract.md`（契约冻结④，L1 权威）＋ task58-fe-admin-questions.md。
- **端点全集**（`lib/api/admin/question-bank.ts`，前缀 `/api/admin/questions`）：
  - 题型 `GET /types`；题库 `GET /banks`(分页+keyword+category_id+yn) · POST · PATCH /banks/{id} · DELETE /banks/{id}；
  - 题目 `GET /banks/{bank_id}/questions`(分页+question_type_id+keyword LIKE stem/analysis_text+yn) · `DELETE /questions/questions/{id}`；
  - 导入 `POST /import-preview?bank_id=N` · `POST /import-execute?bank_id=N`（body `{items:[…]}`，query 内嵌 bank_id）。
- **错误码分支**：40921（题库编码重复，institution+bank_code 唯一）/ 40922（题目编码重复，bank_id+question_code 唯一）；`toAdminApiError` 归一 code → 行内错误。
- **字段 snake_case**：question_bank{bank_code/bank_name/question_count/category_name/yn}、question{question_code/question_type_id/question_type_name/stem/objective_flag/yn}，`ImportItemInput{question_code/question_type_id/stem/answer_text/analysis_text/options_json}`。
- **institution_id**：题库创建按同项目 SeriesForm 惯例手填「机构 ID」（多校区归属）。
- **契约顺延（非缺口）**：`POST/PATCH /questions` 单题创建/编辑留给 task59（编辑/解析详情页）；`GET /banks/{bank_id}` 详情由列表行对象 `selected` 复用，不在本页重复请求。

## 4. 交付物清单

| 类别 | 文件 | 说明 |
|------|------|------|
| 原型 | `test-reports/fe-html/admin-questions.html` | 已 APPROVED；历次返工收敛（题库 31 个按知识点分类、1752 题归属 Python 基础编程题库、题目按题库分类展示、分页），示例与审计注释隐于多态演示控制器 |
| API 层 | `edu-frontend/src/lib/api/admin/question-bank.ts` | 两级 CRUD + 批量导入 + 题型 + 40921/40922 错误映射 + resolveTypeId/toAdminApiError 纯函数 |
| 表单 | `edu-frontend/src/components/admin/BankFormDialog.tsx` | 新建/编辑题库（remount-key 复位，对齐 SeriesForm 技法） |
| 导入 | `edu-frontend/src/components/admin/BankImportDialog.tsx` | 四步批量导入（上传→预览→进度→结果，失败行定位 + 样例填充） |
| 页面 | `edu-frontend/src/app/(admin)/admin/questions/page.tsx` | 两级 Tabs + 题库/题目检索分页 + 删库/删题确认 + 编辑跳 task59 |
| 测试 | `src/lib/api/admin/question-bank.test.ts`（12 契约/错误映射用例） | 端点路径、过滤透传、preview/execute body+query、40921/40922、resolveTypeId |
| 测试 | `src/app/(admin)/admin/questions/page.test.tsx`（5 页面用例） | 两级联动、编辑 href、删除二次确认、批量导入可用性、未选题空态 |

## 5. 质量门禁

| 门禁 | 结果 |
|------|------|
| css 纪律审计 5 项（hex/内联色/禁闭色/任意字号/灰系） | task58 源文件真命中全 0（`slate-` 仅 `translate-y` 误报；语义 token：primary-soft/primary-border/success|warning|destructive-foreground 均见 globals.css） |
| Vitest 全量 | **68 文件 468 测试 PASS**（本任务新增 12 API + 5 页面 = 17；旧 questions.test.ts 不受影响） |
| TypeScript `tsc --noEmit` | 0 错误 |
| ESLint | 0 error / 0 warning |
| Next `next build` | 成功，`/admin/questions`（○ Static）与 `/admin/questions/[id]`（ƒ Dynamic）路由注册正常 |
| 独立审查/测试子代理 | 独立子代理完成 8 项硬性约束逐条核查（契约/禁 MOCK/标签废除/两级联动/删除确认/风格纪律/R-7/TS 风险）→ 发现 BUG-1（BankFormDialog 表单复位失效）并已按 SeriesForm remount-key 技法修复 | 
| 独立页面测试子代理 | page.test.tsx 断言两级联动请求 `/banks/{id}/questions`、编辑 href、删除 ConfirmDialog → deleteBank、批量导入启用/禁用、未选题空态 |

## 6. 已知边界 / 后续

- **单题创建/编辑**：本页聚焦两级管理与批量导入；单题创建/编辑/解析由 task59 `/admin/questions/[id]` 承接（本页「编辑/解析」已跳该路由）。
- **导入进度为前端过渡**：contract④ 的 import-execute 同步返回全量结果、无独立进度端点；`BankImportDialog` 进度为 0→100% 过渡动画 + 成功停留 600ms 再进结果报告。
- **40921 行内 + 全局 toast 双弹**：409xx 冲突在 BankFormDialog 做行内提示，全局 MutationCache.onError 对非 401/403 也会 toast，存在双反馈——与同代码库其他表单架构一致（非本任务回归），待全局 cache 层统一 409 分支时收敛。
- **institution_id 手填**：沿用 SeriesForm 惯例，多校区归属由管理员输入，后续可接入机构切换 token 后自动注入。

---
> 运行 `D:\.ai-hub\sync.ps1` 分发后，等待编排者 task58=DONE 验收指令，再进入 task59。