# task41 完成报告 — UI 组件基础（C1~C14 + 全局枚举映射 StatusBadge）

> 执行者：前端开发者（TRAE SOLO CN）
> 状态：**待编排者验收**（未经验收不得开始 task42）
> 日期：2026-08-19
> 技术栈：Next.js 16.3 + React 19 + Tailwind v4 + shadcn（Borderless Style Base UI 范式）

---

## 一、交付清单（C1~C14 + lib/status 枚举映射）

### 组件源码（`src/components/ui/`）
| 编号 | 组件文件 | 说明 |
|---|---|---|
| C1 | `data-table.tsx` | 通用表：排序表头 / 加载骨架 / 空态内建；`aria-sort` + 可聚焦排序列 |
| C2 | `pagination.tsx` | 分页：page_meta 驱动，上一页/下一页/页码，`role="status"` 汇报 |
| C3 | `status-badge.tsx` + `src/lib/status.ts` | 徽章 **颜色+文字双通道**；13 组枚举映射（见下） |
| C4 | `stepper.tsx` | 步骤条：`aria-current="step"` 标记当前步 |
| C5 | `uploader.tsx` | 上传：明细项 + 进度/错误/移除，`role="button"` + aria-label |
| C6 | `timeline.tsx` | 时间线：语义 ol/li，时间/内容 |
| C7 | `empty-state.tsx` | 空态：居中图标+文案+CTA，`role="status"` |
| C8 | `error-state.tsx` | 错误态：**不吞错**原样展示 message + 重试入口，`role="alert"` |
| C9 | `filter-bar.tsx` | 筛选操作条：分组（控件群） |
| C10 | `confirm-dialog.tsx` | 确认对话框：destructive 变体，打开/取消/确认 |
| C11 | `dropdown-menu.tsx` | 下拉菜单：trigger + 菜单项 + destructive 变体；`aria-haspopup` |
| C12 | `select.tsx` | 下拉选择：label/必填*/错误/disabled；trigger 语义 `combobox` |
| C13 | `accordion.tsx` | 手风琴：trigger 展开/折叠，受控/非受控 |
| C14 | `price-text.tsx` | 价格渲染：空价格「-」、¥ 符号 |

### 全局枚举映射（`src/lib/status.ts`，13 组，覆盖要求的 11 组/12 项全覆盖）
`order_status` / `order_item_status` / `payment_status` / `refund_status` / `receive_status`(券) / `enroll_status`(报名) / `teaching_status`(课次) / `transcode_status`(转码) / `review_status`(审核) / `ticket_status`(工单) / `priority_level`(优先级) / `series_sale_status`(系列) / `delivery_mode`(交付)

> 「订单/支付/退款/券/报名/课次/转码/审核/工单/优先级/系列/交付」全部有映射；`order_item_status` 为额外补充。每组提供 `label`（文字通道）+ `tone`（success/warning/danger/neutral/primary 颜色通道），统一经 `statusTone()` / `statusText()` 解析，未知值回退 `neutral`/原值。

### 测试文件（`src/components/ui/__tests__/`）
`status-badge` / `data-table` / `pagination` / `states`(C7/C8/C9) / `stepper-timeline`(C4/C6) / `price-text` / `uploader` / `confirm-dialog` / `dropdown-menu-select`(C11/C12) / `accordion` —— **C1~C14 全覆盖，每组件含 render + 交互 + a11y 快照断言**。

---

## 二、验收标准 GWT 逐条对照

### Given① 全组件实现 → When 运行 vitest → Then 全绿 + a11y 断言 + StatusBadge 双通道
- **vitest 全量结果：42 个测试文件 / 323 个测试全绿（PASS）**
  ```
  Test Files  42 passed (42)
       Tests  323 passed (323)
  ```
- **a11y 断言逐项落实**（每组件均含 role / aria 断言）：
  - `status-badge`：`role="status"` + tone 颜色通道 + label 文字通道（双通道验证：纯色块被禁，断言同时校验文本与色调类）
  - `data-table`：原生 `<table>` + th `aria-sort`（asc/desc/none）；可排序列为可聚焦 `<button>`；骨架行 `aria-hidden` 屏蔽读屏 + 容器 `aria-busy`；空数据内建空态 `role="status"`
  - `pagination`：导航 + 当前页状态（aria-current 页）
  - `stepper`：当前步 `aria-current="step"`
  - `uploader`：上传区 `role="button"` + aria-label；明细项含进度/错误 a11y 播报
  - `empty-state`：`role="status"`；`error-state`：`role="alert"`（不吞错）
  - `confirm-dialog`：对话框打开/关闭焦点语义 + 确认/取消按钮 role
  - `dropdown-menu`：trigger `role="button"` + `aria-haspopup="menu"`；`select`：trigger 语义 `combobox` + `aria-expanded` + 错误 `role="alert"` + `aria-invalid`
  - `accordion`：trigger `role="button"` + `aria-expanded` 切换
- **StatusBadge 双通道达标**：徽章 = 语义色 bg/text token（`bg-success/10 text-success` 等）+ 可读中文 label 文字；无纯色块无文字的情况。

### Given② 组件使用 tokens → When grep 全站 → Then 无违规
grep 审计（全站 `src/components/ui/`）：
| 规则 | 命令 | 结果 |
|---|---|---|
| 无 `bg-[#...]` / `text-[#...]` / `border-[#...]` | `Select-String 'bg-\[#|text-\[#|border-\[#'` | **通过（0 命中）** |
| 无 `text-[Npx]` | `Select-String 'text-\[[0-9]+px\]'` | **通过（0 命中）** —— 清理了 form.tsx 2 处 `text-[13px]` → token `text-sm-table` |
| 无 sky/violet/cyan/teal/fuchsia 业务组件色 | grep 5 禁用色 | **通过（0 命中）**（图表色板白名单不变） |
| 无内联 `style` 色值 | `Select-String 'style=\{\{[^}]*#|rgb'` | **通过（0 命中）** |
- 自定义 token 全部在 `globals.css` `@theme` 注册：`--text-sm-table` / `--success` / `--warning` / `--destructive` / `--primary-soft`(+foreground) / `--muted` / `--primary` / `--radius-4xl` 等。
- **附注（非禁用范围）**：脚手架遗留的 `bg-slate-100/200`（progress/slider）、`bg-red-600/green-600`（offline-indicator）、form.tsx 遗留 slate/rose 已一并 token 化处理（slate/rose 本不在 5 禁用色清单，属顺手治理）；`text-center/left/right`、`text-sm/xs/xl` 为标准 Tailwind 工具类非自定义色。

### 补充质量门禁
- `npx tsc --noEmit`：**0 错误**，TSC_EXIT=0
- 修复并最终验证的问题（本次提交内）：
  - Base UI Select trigger 实际语义角色为 `combobox`（非 `button`）→ 测试改用 `getByRole("combobox")` + `within(trigger)` 定位选中值
  - Base UI Accordion 受控 `value` 需为数组 → 测试由 `value={null}` 改 `value={[]}`；`onValueChange` 签名 `(value, eventDetails)` → 断言补第二参 `expect.anything()`
  - data-table aria-sort 在 th 自身非后代 → 断言改用 `toHaveAttribute`

---

## 三、对抗性回归记录（本 task 修过的缺陷与根因）
1. **Select trigger 角色误判**（dropdown-menu-select 3 例失败）：base-ui 1.7 Select 将 trigger 渲染为 `combobox` 角色 + 隐藏原生 input，查询 `role="button"` 落空。改用 `getByRole("combobox", { name })` 精确命中。
2. **受控 Select value 与选项列表文本重复**：选中 label 同时存在于 trigger 与隐藏 popup 的 option，`getByText` 报 multiple。用 `within(trigger)` 限定作用域。
3. **Accordion 受控 `value={null}` 崩溃**：`AccordionItem.mjs:45` `openValues.indexOf(value)` 中 `openValues` 为 null。签名要求 `AccordionValue = Value[]`，初始化必须传 `[]`。
4. **Accordion onValueChange 断言失配**：回调签名 `(value, eventDetails)` 双参，单 matcher 断言首参即失败。补 `expect.anything()` 匹配第二参。
5. **data-table aria-sort 查询落空**：排序属性挂在 th 元素自身，`th.querySelector('[aria-sort]')` 找后代返回 null。改为直接对 th 断言。
6. **form.tsx 硬编码字号**：`text-[13px]` + 遗留 `text-slate-500`/`text-rose-600` → 替换为 `text-sm-table` + `text-muted-foreground` / `text-destructive`。

---

## 四、对下游（task44 /courses）的影响
本任务产出的 **C2 Pagination / C9 FilterBar / C14 PriceText / C7 EmptyState / C8 ErrorState** 即 task44「课程中心」HTML 原型（`test-reports/fe-html/courses.html`）审核签收后 React 化的直接依赖——届时以这些 token 化、含 a11y 的组件落地，避免二次硬编码。

---

## 五、验收状态
- [x] C1~C14 组件全部实现
- [x] lib/status 13 组枚举映射
- [x] vitest 全绿（323/323）
- [x] grep 审计 4 项全通过（含 form.tsx 治理）
- [x] tsc 0 错误
- [x] StatusBadge 颜色+文字双通道
- [x] sync.ps1 已运行（见下）

> **下一步**：等待编排者验收指令，验收通过后复工 task44（courses.html 签收后以 C 组件写 React）。