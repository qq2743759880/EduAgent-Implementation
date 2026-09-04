# 无障碍审查报告 fx-task03

> 审查人：fe-a11y-auditor ｜ 基准：WCAG 2.2 AA
> 任务范围：G3 管理端课程/题库/用户页面（fx-task03 补课波，只审查+出报告，未改业务代码）

## 审查范围

- 页面（6）：`/admin/courses`、`/admin/questions`、`/admin/users`、`/admin/dashboard`、`/admin/courses/[seriesId]`（ModuleTree）、`/admin/questions/[id]`（QuestionForm embedded）
- 组件（10+）：`SeriesForm`、`QuestionForm`、`UserDetailDialog`、`UserTable`、`VideoUploadFlow`、`BatchImportDialog`、`ComposePaperDialog`、`ModuleTree`、`MetricCards`、`controls.tsx`（FieldRow/NativeSelect/TagChip/三态）、`PaginationBar`
- 共享依赖：`src/components/ui/dialog.tsx`（@base-ui/react/dialog）、`button/input/textarea/badge/progress/toast`

- 审查时间: 2026-08-13 09:40–09:55（UTC+8）
- 被审文件:
  - `edu-frontend/src/components/admin/controls.tsx`（FieldRow:43-72、NativeSelect:21-40、TagChip:75-99、ErrorState:111-124）
  - `edu-frontend/src/components/admin/SeriesForm.tsx`（108-217）
  - `edu-frontend/src/components/admin/QuestionForm.tsx`（169-338、ChoiceEditor:356-436）
  - `edu-frontend/src/components/admin/UserTable.tsx`（54-149）
  - `edu-frontend/src/components/admin/UserDetailDialog.tsx`（28-72、StatusPill:74-86）
  - `edu-frontend/src/components/admin/MetricCards.tsx`（42-139）
  - `edu-frontend/src/components/admin/ModuleTree.tsx`（131-273、ModuleCard:295-394）
  - `edu-frontend/src/components/admin/VideoUploadFlow.tsx`（206-320、Stepper:327-353）
  - `edu-frontend/src/components/admin/BatchImportDialog.tsx`（115-179）
  - `edu-frontend/src/components/admin/ComposePaperDialog.tsx`（99-224）
  - `edu-frontend/src/app/(admin)/admin/courses/page.tsx`、`questions/page.tsx`、`users/page.tsx`、`dashboard/page.tsx`
  - `edu-frontend/src/components/ui/dialog.tsx`、`button.tsx`、`input.tsx`、`toast.tsx`
  - `edu-frontend/src/components/curriculum/PaginationBar.tsx`
  - `edu-frontend/src/app/(admin)/layout.tsx`、`edu-frontend/src/app/layout.tsx`、`globals.css`

## 验证方式

**实机（Playwright @ http://localhost:3000，复用 fe-server-infra 启动的 dev server，未重复启动）**
- 注入本地登录态（`edu:auth:token` + `edu:auth:me` roles:['admin']）后访问 `/admin/*`，后端 127.0.0.1:8000 不可达，页面以骨架/错误态/空态渲染，操作按钮与弹窗均可实测
- 实测项：表单 Tab 顺序、Modal 打开焦点移入 / Tab 循环 / Escape 关闭 / 焦点归还、原生 select 键盘（Tab/ArrowDown/End/Home）、filter 控件可访问名称、QuestionForm 空表单错误提示关联、键盘 focus 的 `:focus-visible` 计算样式
- 对比度按 Tailwind v4 默认色板（slate/indigo/emerald/rose/amber）做 WCAG 相对亮度计算
- 环境噪声：Next.js 16 dev overlay（nextjs-portal）在部分焦点测试中触发自动路由跳转，测试中已 display:none 隐藏并多次复现关键结论；列表数据（UserTable/ModuleTree/VideoUploadFlow 步骤）因后端不可达未带数据实测，相关条目为**静态审查**并已标注

## 发现表

| # | 位置 file:line | 严重度 | 原则 | 问题 | 修复建议 |
|---|---------------|--------|------|------|---------|
| 1 | `controls.tsx:60-63`（FieldRow）＋ 三页筛选栏 `courses/page.tsx:80,89,98` / `questions/page.tsx:120,129,138,147,156` / `users/page.tsx:60,69,78` | HIGH | 1.3.1 / 4.1.2 | `<label>` 无 `for`、控件无 `id`/`aria-label`/`aria-labelledby`，表单控件**无可访问名称**。实机确认 5 个 filter label 的 htmlFor=null、select/input ariaLabel=null | FieldRow 内部为控件生成唯一 id 并 `htmlFor` 关联（或 `aria-labelledby`）；页面筛选 label 同样处理 |
| 2 | `controls.tsx:65-66`（FieldRow error）→ SeriesForm/QuestionForm/BatchImport/ComposePaper 全部表单 | HIGH | 3.3.1 / 3.3.3 / 4.1.3 | 错误提示仅渲染 `<p>`，**无 `aria-invalid`、无 `aria-describedby` 关联**。实机：QuestionForm 空表单提交后错误文本出现，但全部控件 aria-invalid=null、aria-describedby=null；错误后焦点也不定位到错误字段 | 错误 `<p id={errId}>` + 控件 `aria-describedby={errId}` `aria-invalid="true"`；提交失败后将焦点移到第一个错误字段（提供到达错误位置的路径） |
| 3 | `src/components/ui/dialog.tsx:42-80` + 各弹窗（SeriesForm/QuestionForm/BatchImport 等） | HIGH | 2.4.3 / APG dialog 模式 | 模态弹窗**焦点可逃逸 + 关闭后不归还**。实机：打开 SeriesForm 后初始焦点移入 ✓；但从 Close(X) 按钮 Tab 焦点逃出 dialog 到 BODY（Base UI trap 未生效，多次复现）；Escape 关闭 ✓ 但焦点落在 BODY，未回到触发按钮「创建系列」 | 显式传 Base UI `modal`（默认 true 未生效需排查版本行为）与 `finalFocus`；或业务侧在关闭时手动归还焦点到触发按钮；校验嵌套/受控 open 场景 |
| 4 | `QuestionForm.tsx:397-409`（ChoiceEditor 正确项标记按钮）、`QuestionForm.tsx:248-262`（true_false 对/错按钮） | HIGH | 1.4.1 / 4.1.2 | 选中态**仅靠颜色**（indigo 背景）传达，按钮无 `aria-pressed`，读屏器无法感知已选状态（aria-label 只描述动作） | 两个按钮组补 `aria-pressed={checked}`（TagChip 已正确使用 aria-pressed，可对齐） |
| 5a | `MetricCards.tsx:129`（角色名 text-[11px] slate-400）、`courses/page.tsx:184-190`（SeriesRow meta）、`UserTable.tsx:76,80`、`users/page.tsx:109`、`questions/page.tsx:199`、`UserDetailDialog.tsx:47` | HIGH | 1.4.3 | `text-slate-400`（#94a3b8）on white = **2.56:1**，远低于 4.5:1，用于 11-12px 信息文本（角色名/编码/日期/ID） | 提升至 slate-600/700（≥4.5:1）或加粗加大 |
| 5b | `ModuleTree.tsx:283`（completed 徽章 emerald-600 on emerald-50）、`ModuleTree.tsx:288`（cancelled 徽章 rose-600 on rose-50） | HIGH | 1.4.3 | 11px 徽章文本对比度：emerald-600 = **3.58:1**、rose-600 = **4.28:1**，均 < 4.5:1 | 改用 emerald-700 / rose-700（5.2:1 / 5.7:1） |
| 5c | `controls.tsx:116`（ErrorState message `text-rose-600/90` on `rose-50/50`） | HIGH | 1.4.3 | 半透明混合后 ≈ **4.14:1**（13px 正文 < 4.5:1） | 去掉透明度，用 rose-700 纯色 |
| 6 | `courses/page.tsx:130-136`、`ModuleTree.tsx:96-115`、`questions/page.tsx:215-219`（window.confirm 二次确认） | LOW | 2.4.3 / 无（记录） | 原生 `window.confirm` 无障碍受限（读屏器可读但无 ARIA 状态、无焦点管理）——按任务指示**记录但不阻塞** | 后续可替换为自定义 AlertDialog（Base UI）并归还焦点 |
| 7 | `VideoUploadFlow.tsx:327-353`（Stepper） | LOW | 1.4.1 / 4.1.2 | 步骤条 ol/li 语义正确，但**当前步骤无 `aria-current` 标记**，完成/当前/未到仅靠颜色+check 图标区分 | 当前步 li 加 `aria-current="step"` |
| 8 | `controls.tsx:67-68`（FieldRow hint `text-slate-400` 12px） | LOW | 1.4.3 | 辅助提示文本 2.56:1 偏低（非关键信息，建议优化） | 提升至 slate-500/600 |
| 9 | `src/app/layout.tsx:16-19` | LOW | 2.4.2 | 全站共用 title「EduAgent · 智能学习助手」，管理端各页 title 不随路由变化，读屏器切页无法从标题辨识 | 各 admin 页 export `metadata.title`（如「课程管理 - EduAgent」） |
| 10 | `controls.tsx:84-98`（TagChip） | LOW | 2.4.7 | 无自定义 `focus-visible` 样式，依赖浏览器默认 outline（其余控件均有 ring，风格不一致） | 补 `focus-visible:ring-2 focus-visible:ring-ring` |

## 实测记录

| 场景 | 结果 |
|------|------|
| Modal 打开焦点移入（SeriesForm / QuestionForm） | PASS — Base UI `role="dialog"` 渲染，初始焦点自动进入弹窗内首个输入 |
| Modal 内 Tab 顺序（SeriesForm：编码→名称→学科→分级→…→简介→取消→创建→Close） | PASS（DOM 顺序正确，全字段可达） |
| Modal Tab 焦点围困（Close 按钮后 Tab） | **FAIL** — 焦点逃逸到 BODY，再经浏览器自然循环回弹窗；非严格 trap |
| Escape 关闭 Modal | PASS — 弹窗正常关闭 |
| 关闭后焦点归还触发按钮 | **FAIL** — 焦点落在 BODY，未回到「创建系列」 |
| 原生 select 键盘（学科筛选：Tab 聚焦 → End=化学 → Home=全部学科） | PASS — NativeSelect 为原生 select，键盘操作完整 |
| 筛选/表单单控件可访问名称 | **FAIL** — label 无 for、控件无名称（见 #1） |
| 表单错误提示关联（QuestionForm 空提交） | **FAIL** — 错误文本渲染但无 aria-invalid/aria-describedby（见 #2） |
| focus-visible 计算样式（Button/Input/NativeSelect/Link） | PASS — 键盘聚焦 `:focus-visible` 命中，组件 class 含 `focus-visible:ring-3`（近黑 ring on 白底，对比充足） |
| PaginationBar（aria-label + aria-current + 双向箭头 aria-label） | PASS（静态） |
| 表格语义（UserTable 真 `<table>/<thead>/<th>`，7 列） | PASS（静态；后端不可达未带数据实测） |
| icon-only 按钮 aria-label（删除题目/删除模块/删除课次/删除班次） | PASS |
| TagChip `aria-pressed` | PASS |
| ModuleCard 折叠 `aria-expanded` | PASS |
| `prefers-reduced-motion`（globals.css:133-141） | PASS — 全局动画/过渡归零 |
| `<html lang="zh-CN">` | PASS |
| VideoUploadFlow Progress `aria-label="上传进度"` | PASS（静态） |
| 暗色模式（darkVariant 存在） | 说明：admin 组件大量硬编码浅色类（bg-white/text-slate-*），暗色下保持浅色，无翻转对比度问题；本次对比度均按浅色主题计算 |

## 严重问题（BLOCKER）

无。

（键盘可达性经实测全覆盖：所有交互元素为原生 button/link/input/select/textarea，无键盘死区；焦点环在主要控件可见；无关键功能缺失替代文本。）

## 需要修复（HIGH）

见发现表 #1–#5（共 5 类 9 处）：
1. 表单控件无可访问名称（FieldRow + 3 页筛选 + UserTable 行内角色 select）— 1.3.1/4.1.2
2. 错误提示未关联控件（无 aria-invalid/aria-describedby，错误后无焦点路径）— 3.3.1/3.3.3/4.1.3
3. 模态弹窗焦点逃逸 + 关闭后焦点不归还 — 2.4.3/APG
4. 选择态仅颜色传达（正确项/对错按钮无 aria-pressed）— 1.4.1/4.1.2
5. 对比度不足（slate-400 2.56:1、emerald-600 徽章 3.58:1、rose-600 徽章 4.28:1、ErrorState 4.14:1）— 1.4.3

## 建议（LOW）

见发现表 #6–#10（window.confirm 替换、Stepper aria-current、hint 对比度、页面 title、TagChip focus 样式）。

## 判定

- 结论: **FAIL**（存在 WCAG 2.2 AA 违规：1.3.1/4.1.2 名称与结构、3.3.1/3.3.3/4.1.3 错误提示、1.4.3 对比度、2.4.3 模态焦点、1.4.1 状态语义）
- 阻塞项: 无 BLOCKER；下列 HIGH 为必须修正项（修正后应复测）：
  1. 表单控件可访问名称缺失（FieldRow/筛选栏/角色 select）
  2. 表单错误提示未关联控件（aria-invalid/aria-describedby + 焦点路径）
  3. 模态弹窗焦点逃逸与关闭后焦点不归还
  4. 选择态仅颜色传达（缺 aria-pressed）
  5. 文本对比度不达标（slate-400 系 / emerald-600 / rose-600 徽章 / ErrorState message）
- 备注：UserTable/ModuleTree/VideoUploadFlow 因后端不可达为静态审查，相关 PASS 为「静态通过，待实机复验」；未实机复验部分不得作为实机通过被消费。
