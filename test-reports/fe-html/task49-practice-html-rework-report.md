# task49 复习中心 · practice.html — SOP 完整返工完成报告（fe-* 子代理）

> 日期：2026-08-21 ｜ HTML：`test-reports/fe-html/practice.html` ｜ 冻结点：R4 FINAL ｜ 调用链：风格定调 → frontend-design → prototype → colorize → polish → visual-validation → audit/critique
> 状态：**APPROVED**（独立 fe-auditor 从 REJECT 修复后复审通过）→ 可移交 fe-implementer 写 React

---

## 一、本次返工范围（R3 → R4）

按 `html-rework-sop.md` 完整走通，在既有已冻结的 candy-playful 风格内改进，未换风格（换风格=风格大改需重新走 §〇 gate）。

### Step 1–4 已落地（R3 阶段）
- **齐四态演示器**：success / loading / empty / error 四种状态面板 + loader 骨架屏 + shimmer 动画 + 空态/错误态重试。
- **多题型会话切换**：单选 / 多选 / 填空 / 判断 4 题，可真实切换并作答判分。
- **答题交互**：点选项 → 即时判分 → 解析区展开；填空输入提交判分；判断题对错二选一判分。
- **a11y 补强**：全局 `:focus-visible` 焦点环、`.visually-hidden`、进度条 `role=progressbar`+`aria-valuetext`、判分结果 `role=status+aria-live`、错误态 `role=alert`、入口有效 button+`aria-describedby`、题型条 `role=tablist/tab/aria-selected`。
- **token 化**：`#fff2f2→--error-bg`、`#e6e6e6→--code-text`、`#8ad4ff→--code-acc`。

### Step 5–6 本轮（R4）落地与修复
- **Step 5 visual-validation**：新建 `shoot-practice.js` 截图矩阵（375/768/1024/1280/1440 × success + loading/error/empty + 四题型 + 交互 probe），**真跑 13 张截图全绿、无 console/page 错误**。
- **Step 5b 交互 probe（Playwright）**：填空提交 404 → 判分+解析弹出；判断点选 → 判分+解析弹出；均验证可见。
- **Step 4 补审（grep 硬编码色）**：
  - 新增 token：`--shadow-red`、`--shadow-green`、`--error-border`，回收零散红/绿品牌 rgba（按钮阴影、错误边框），**硬编码业务色归零**。
- **Step 6 audit/critique（独立 fe-auditor 子代理，REJECT 一次）**：
  - **P1 【必须修复】判断题判分逻辑反转**——题干为假命题（tuple 不可变，ground truth=「错误」），原逻辑把点「正确」判为对、点「错误」判为错，与原方案点名验证场景相反。
  - **修复**：判分改为比较 ground truth（`correct = 用户所点 === 「错误」`）。实测：点「错误」→「回答正确！+1 金豆」；点「正确」→「回答错误 · tuple 不可变，此题选「错误」」。✅
  - P3 项（填空判分条件 `404。` 重复）— 一并去重。
- **响应式加固**：`DataTable` 375 下曾溢出 → 加 `.tlist-scroll`（`overflow-x:auto`）+ 小屏 `min-width:560px`，实测 **375/768/1280 页面零水平溢出**（`scrollWidth` 探针确认）。

---

## 二、验证结果（fe-auditor + 自测，独立子代理 APPROVED）

| 项 | 结果 |
|---|---|
| 截图矩阵 | 13 张全绿（375~1440 × 全态 + 四题型） |
| 交互 probe | 填空/判断判分+解析均可用、逻辑正确 |
| 横向溢出 | 375/768/1280 均 0 |
| P1 判断题判分 | 已修复验证（点错误→对 / 点正确→错） |
| 硬编码业务色 | :root 之外 0（红/绿/蓝/紫/橙/粉全 token） |
| hijack console/page 错误 | none |
| a11y | 主体通过（焦点环/aria-live/aria-describedby/tablist） |

遗留 P3 建议（不阻塞，移交 React 时处理）：题型切换条补 `aria-controls`/`tabpanel`/方向键；`h2(16px)<h3(18px)` heading 层级倒置；入口 CTA 混用 `<a role=button>`/`<button>`；emoji→SVG/sprite。

---

## 三、软肋与说明
- 数据契约（`GET /api/interactive/quiz/wrong-book`、`GET /api/vocab/daily`、`GET /api/questions`）为 interactive 待联调接口，页面按「写真实接口 + 待联调」标注，**未造假**。
- 效果图为静态+局部交互示意，非真实接口数据；单选题/多题为「已判分」静态演示，填空/判断可真实作答判分。

## 四、交付物
- `test-reports/fe-html/practice.html`（R4 FINAL，AUDIT LOG 已至 R4）
- `test-reports/fe-html/shoot-practice.js`（截图矩阵脚本）
- `test-reports/fe-html/audit-*.png`（auditor 验证截图）、`shot-p-*.png`（13 张矩阵截图）
- 独立审查报告由 fe-auditor 子代理产出（见 Step 6 结论）

**结论：HTML 效果图已 APPROVED，可移交互 fe-implementer 按此写 React 页面（/practice/[mode]）。**