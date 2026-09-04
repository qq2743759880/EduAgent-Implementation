# 无障碍审查报告 fx-task04

## 审查范围

G4 管理端 RAG + MCP 控制台（fx-task04）——2 页面 + 10 组件：

- 页面：`src/app/(admin)/admin/rag/page.tsx`、`src/app/(admin)/admin/mcp/page.tsx`
- RAG 组件：`PresetForm.tsx`、`RebuildDialog.tsx`、`CollectionTable.tsx`（含 StatusBadge）、`SearchTester.tsx`、`AuditLogTable.tsx`
- MCP 组件：`ServerForm.tsx`、`ServerTable.tsx`（含 HealthDot）、`ToolTable.tsx`、`ToolTestDialog.tsx`、`CallLogTable.tsx`（含 CallStatusBadge）
- 共享控件：`src/components/admin/controls.tsx`（FieldRow / NativeSelect）、`src/components/ui/*`（dialog/input/textarea/checkbox/badge/button）
- 审查时间：2026-08-13
- 被审文件：见上（file:line 引用见发现表）

## 验证方式

实机（Playwright + dev server http://localhost:3000，route mock API 恢复数据渲染）+ 静态代码审查。

- dev server 存活（PID 17284，非本 infra 启动）；后端 127.0.0.1:8000 未运行 → 使用 route mock 恢复 MCP/RAG 页面数据渲染后实测
- **RAG 页实测受阻**：`/admin/rag` 首次可渲染骨架，但随后因 `presetsQuery.data?.find is not a function`（`page.tsx:43`，后端不可达时 data 非数组）页面崩溃进入 Next.js "This page couldn't load"；该 RAG 页属于**功能缺陷**（非纯 a11y 问题，见 LOW-08），阻塞了 PresetForm / RebuildDialog / CollectionTable / SearchTester 的实机弹窗与键盘验证（已做静态审查）
- 实测通过：MCP 页 ServerForm / ToolTable / ToolTestDialog 弹窗链（焦点移入 → Escape 关闭 → 焦点归还）、Tab 顺序、行操作按钮可访问名、HealthDot / 徽章文本语义、表单错误显示、JSON 解析错误显示
- 自动检查：Playwright accessibility snapshot 逐元素核对名称/角色；未运行 axe（dev server 幽灵导航 + 页面崩溃干扰，改用快照+DOM 断言方式，等效覆盖）

## 严重问题（BLOCKER）

| # | 位置 | 问题 | 修复建议 |
|---|------|------|---------|
| BLOCKER-01 | `controls.tsx:58-64`（FieldRow）+ `PresetForm.tsx:105-201` / `ServerForm.tsx:134-202` / `RebuildDialog.tsx:80-90` / `ToolTestDialog.tsx:134-147` / `SearchTester.tsx:47-90` / `AuditLogTable.tsx:71-97` / `CallLogTable.tsx:79-116` / `ServerForm.tsx:114-129`（import-url） | 表单控件**无程序化 label**：`FieldRow` 渲染的 `<label>` 无 `htmlFor`，控件无 `id`，也无 `aria-label`；过滤区/SearchTester 的 label 同样未关联。实机确认：ServerForm 弹窗内全部 `input/select/textarea` 的 `el.labels` 为空、`aria-label` 为空；`ServerForm` import-url input、`transport-select`、`run-command` 等名称仅依赖 placeholder 或完全无名称；快照中 `combobox`（NativeSelect）显示无名，`created_after` textbox 完全无名（无 label、无 placeholder）。读屏器用户无法识别任何表单字段含义 → WCAG 1.3.1 / 4.1.2 / 3.3.2 | FieldRow 内为控件生成唯一 `id` 并 `htmlFor` 指向；过滤区/SearchTester label 补 `htmlFor` + 控件 `id`；Select/Textarea 同样处理；import-url 用 `label htmlFor` 或 `aria-label` |

## 需要修复（HIGH）

| # | 位置 | 问题 | 修复建议 |
|---|------|------|---------|
| HIGH-01 | `controls.tsx:65-66`（FieldRow error）+ `PresetForm.tsx:105-112` / `ServerForm.tsx:147-162,167-192` / `ToolTestDialog.tsx:134-147` | 表单**错误提示无程序化关联**：错误 `<p>` 无 `id`，控件无 `aria-invalid`、无 `aria-describedby`。实机确认：ServerForm 空提交后错误文本正常显示（"请输入 Server 编码"等 3 条），但全部控件 `invalid=null db=none`；ToolTestDialog 输入非法 JSON 后 textarea 仅红色边框（`borderRose=true`）而无任何 ARIA 状态。读屏器读不到错误内容与所属字段 → WCAG 1.3.1 / 3.3.1 / 3.3.3 | 错误提示 `<p>` 加 `id`；控件 `aria-invalid` + `aria-describedby` 指向错误节点；错误出现时加 `role="alert"` 或 `aria-live` |
| HIGH-02 | `rag/page.tsx:33-35` + `CollectionTable.tsx:99-113`（rebuilding 轮询）/ `SearchTester.tsx:102-165`（结果区）/ `RebuildDialog.tsx:92-99` / `ToolTestDialog.tsx:149-182` | **动态状态区域无 aria-live**：rebuilding 集合轮询 10s 状态流转、检索结果、重建 job_id 结果、工具调用结果均非 live region，读屏器无法获知异步更新（尤其重建进度从"重建中"→"就绪"的轮询变化）→ WCAG 4.1.3 | 结果/状态容器加 `role="status"` 或 `aria-live="polite"`（rebuilding 状态列、search result、rebuild-result、tool-test-result） |
| HIGH-03 | `ServerTable.tsx:138-153`（HealthDot）+ 各表大量 `text-slate-400` 辅助文本（`CollectionTable.tsx:46-47,63` / `ServerTable.tsx:68,97` / `AuditLogTable.tsx:144,156` / `CallLogTable.tsx:163,170` / `SearchTester.tsx:116` 等） | **对比度不达标（实测计算）**：① 健康灯 OK 文本 `text-emerald-600`(12px) 对白底 ≈ **3.76:1** < 4.5（1.4.3）；② 未知态文本 `text-slate-400`(12px) 对白底 ≈ **2.60:1** < 4.5；③ 绿点 `bg-emerald-500` 对白底 ≈ **2.51:1** < 3（1.4.11 非文本）；④ 未知灰点 `bg-slate-300` 对白底 ≈ **1.47:1** < 3；⑤ 大量 11-12px `text-slate-400` 辅助信息系统性 2.6:1（1.4.3） | 健康灯 OK 改用 `text-emerald-700`+深色点（emerald-600/700）；未知态文本与点改用 `slate-600`/`slate-500`；全量辅助文本至少升级为 `text-slate-500`（≈4.78:1） |
| HIGH-04 | `CollectionTable.tsx:109`（rebuilding 圆点 `bg-amber-500` on `bg-amber-100`）≈ **1.94:1** < 3（1.4.11 非文本对比度，且为状态指示）；`CollectionTable.tsx:101` 与 `CallLogTable.tsx:194-198` TIMEOUT 徽章 `text-amber-700` on `bg-amber-100` ≈ **4.43:1** < 4.5（临界） | 状态徽章/状态点对比度不足 | rebuilding 点改深琥珀（amber-600）或加描边；TIMEOUT 徽章文字改 `amber-800` 或背景加深 |

## 建议（LOW）

| # | 位置 | 问题 | 修复建议 |
|---|------|------|---------|
| LOW-01 | `CollectionTable.tsx:27` / `AuditLogTable.tsx:122` / `ServerTable.tsx:42` / `ToolTable.tsx:154` / `CallLogTable.tsx:141` | 表格无 `<caption>`（或 aria-label）描述表格内容，复杂数据表可读性弱（1.3.1 增强） | 每张表加 `<caption className="sr-only">` 或 `aria-label` |
| LOW-02 | `CollectionTable.tsx:29-36` / 各表 `<th>` | `<th>` 未显式 `scope="col"`（简单表默认推断可工作，但增强明确性） | 表头加 `scope="col"` |
| LOW-03 | 各表行内 icon（`Database`/`Cable`/`FileText`/`TriangleAlert` 等）与纯装饰图标（`RefreshCw`/`Search`/`Trash2`） | lucide 图标默认无 `aria-hidden`，读屏器可能播报空图标节点；`SearchTester.tsx:127` 降级提示的 `TriangleAlert` 无 aria-hidden | 装饰性 svg 统一 `aria-hidden="true"`；语义性图标（如降级警告）保留可访问文本即可 |
| LOW-04 | `ServerTable.tsx:90` / `CollectionTable.tsx:63` | 行内错误/状态消息用 `title` 悬停补充，键盘/读屏器不可达（但主文本已渲染，影响有限） | 如需完整信息，直接用可见文本或 `aria-label` |
| LOW-05 | `ToolTestDialog.tsx:75`（`sr-only` "Close"） | 弹窗关闭按钮可访问名为英文 "Close"（UI 库默认），中文界面可读性稍差 | 改中文 `aria-label="关闭"` |
| LOW-06 | `SearchTester.tsx:74,86` | top_k / final_max_k 在选中预设时 `disabled`，无说明文案告知为何禁用 | 禁用时加 hint（FieldRow 已支持）说明"选择预设后由预设决定" |
| LOW-07 | `mcp/page.tsx:56-58`（scanSummary）/ `ServerForm.tsx:112` | 健康扫描摘要、import-url 区块文本为普通 div，无语义强调 | 摘要可用 `aria-live="polite"`（结合 HIGH-02 一并处理） |
| LOW-08 | `rag/page.tsx:43` | 功能缺陷（非纯 a11y）：后端不可达时 `presetsQuery.data?.find` 抛 TypeError 导致 RAG 页整页崩溃，阻塞 RAG 组件实机验证 | `Array.isArray(presetsQuery.data) ? … : null` 容错；建议 fe-tester 跟进 |

## 判定

- 结论：**FAIL**
- 阻塞项：
  1. BLOCKER-01 表单控件无程序化 label（4 个弹窗表单 + 3 个过滤区 + SearchTester + import-url，全部输入控件）
  2. HIGH-01 错误提示无 aria-invalid / aria-describedby（实机确认）
  3. HIGH-03/HIGH-04 对比度不达标（健康灯 OK/未知态、slate-400 辅助文本、状态圆点/徽章）
  4. HIGH-02 动态状态区域无 aria-live（重建进度轮询、检索/调用结果）

> 注：判定为 FAIL 依据判定规则——存在 BLOCKER（BLOCKER-01 属"无替代文本/语义缺失的关键表单功能"，读屏器用户无法完成任何表单任务）；HIGH 类为"必须修正项"一并列入阻塞项。

## 实测记录

| 项目 | 结果 | 证据 |
|------|------|------|
| ServerForm 打开焦点移入 | ✅ 通过 | 点击"新增 Server"后 `document.activeElement` = `INPUT[import-url]`（弹窗内首控件） |
| ServerForm Escape 关闭 + 焦点归还 | ✅ 通过 | Escape 后 dialog=0，activeElement=`BUTTON[server-open]`（触发按钮） |
| ServerForm Tab 顺序 | ✅ 通过 | `SELECT[transport-select] → INPUT[server-code] → INPUT[] → INPUT[run-command] → INPUT[] → TEXTAREA[]`，符合 DOM 顺序、无死区 |
| ServerForm 控件 label 关联 | ❌ 失败 | 全部 7 个控件 `el.labels` 为空、无 `aria-label`（BLOCKER-01） |
| ServerForm 空提交错误显示 | ⚠️ 部分 | 3 条错误文本正常出现；但 `aria-invalid=null`、`aria-describedby=none`、错误 `<p>` 无 id（HIGH-01） |
| ToolTable 打开焦点移入 | ✅ 通过 | activeElement=`BUTTON[tools-db-refresh]`（弹窗内首按钮） |
| ToolTestDialog 打开焦点移入 | ✅ 通过 | activeElement=`TEXTAREA[tool-args]` |
| ToolTestDialog 非法 JSON | ⚠️ 部分 | textarea 红边框触发（borderRose=true），但无 `aria-invalid`/`aria-describedby`（HIGH-01） |
| 两层弹窗 Escape 逐级关闭 + 焦点归还 | ✅ 通过 | 关闭 ToolTestDialog → 焦点回 `test-echo`；关闭 ToolTable → 焦点回 `tools-1` |
| ServerTable 行操作按钮可访问名 | ✅ 通过 | "发现工具"×2、"注销"×2 按钮均带文本（非 icon-only） |
| HealthDot / 徽章文本语义 | ✅ 通过 | 健康灯文本 OK/ERR/未知、徽章文本已启用/已停用/就绪等均在无障碍树 |
| 页面结构 | ✅ 通过 | `lang="zh-CN"`、`<title>` 唯一、h1→h2 层级正确、原生 `<table>/<th>` 语义 |
| 焦点可见性（静态） | ✅ 通过 | Input/Textarea/NativeSelect/Button/Checkbox 均含 `focus-visible:ring-3`；对话框 Popup 带 `outline-none` 但 Base UI 提供聚焦样式 |
| 触控目标（静态） | ✅ 通过 | 按钮 h-7/h-8（28/32px）≥24px；checkbox 经 `after:-inset-*` 扩展命中区 |
| RAG 页实测 | ⚠️ 受阻 | 页面崩溃（LOW-08），PresetForm/RebuildDialog/CollectionTable/SearchTester 弹窗与轮询未实机验证，静态审查结论见上 |
| console 错误 | ⚠️ 记录 | 后端未运行时 chat/API 报 `ERR_CONNECTION_REFUSED`（环境问题，非组件缺陷）；RAG 页 `presetsQuery.data?.find is not a function`（LOW-08） |

## 结论

核心弹窗焦点管理（Base UI Dialog 提供：打开移入、Escape 关闭、两级归还）与 Tab 顺序、触控目标、页面结构均通过；但**表单可访问性存在系统性缺陷**——所有表单控件无程序化 label、错误提示无 ARIA 关联（实机确认），对比度多处不达标，动态状态区域无 aria-live，RAG 页存在阻塞性功能崩溃。**结论 FAIL，需修复阻塞项后复验。**
