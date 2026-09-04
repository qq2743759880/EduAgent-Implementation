# 无障碍审查报告 fe-task06

> 审查者：fe-a11y-auditor｜日期：2026-08-13｜范围：G5 用户端仪表盘真实数据接入（三态：骨架/错误/空态）
> 标准：WCAG 2.2 AA｜方法：静态代码审查 + Playwright 实机验证（dev server http://localhost:3000，复用 fe-task06-server-info.md 进程；后端 127.0.0.1:8000；task01test 真实登录注入 localStorage `edu:auth:token`/`edu:auth:me`）

## 审查范围

| 页面/组件 | 实现文件 |
|---|---|
| /dashboard 页面（三态注入/错误卡/KPI 整区错误） | `src/app/(user)/dashboard/page.tsx` |
| KPI 4 卡（sr-only loading） | `src/components/dashboard/KpiCard.tsx` |
| 趋势图（loading/empty/error 覆盖层） | `src/components/dashboard/ProgressTrendChart.tsx` |
| 雷达图（空态/错误覆盖层） | `src/components/dashboard/AbilityRadarChart.tsx` |
| 徽章墙（空态引导 + 未解锁文本） | `src/components/dashboard/BadgeWallGrid.tsx` |
| 打卡（骨架占位 + 日标签） | `src/components/dashboard/StreakBadge.tsx`（页面级骨架） |
| 积分/排行（loading 骨架 + 空态） | `src/components/dashboard/{PointCard,RankList}.tsx` |
| 基础设施（lang/title/焦点/动效） | `src/app/layout.tsx`、`src/app/globals.css`、`src/components/ui/tabs.tsx` |

## 验证方式

**实机（Playwright，http://localhost:3000）**：
- 真实数据态：task01test（user_id=846）注入 JWT 后访问 /dashboard，6 个 query 全部真实渲染（KPI 0 分钟/0 道/0 门/0 天、积分 31、排行第 2、雷达空态、徽章 0/8）。
- 错误态：`page.route` 拦截 `/api/progress/**`、`/api/users/me/profile`、`/api/gamification/me/{badges,points,rankings}` → 500，实测 6 张错误卡 + 重试按钮（名称「重试」、68×32px、可聚焦）。
- 骨架屏时序：页面 reload 首帧（domcontentloaded + 数据未达）实测 KPI sr-only loading、PointCard「—」+ 3 行 pulse、RankList 5 行 pulse、StreakBadge 骨架 aria-hidden、徽章墙 description「加载中…」。
- 对比度：浏览器 canvas fillStyle 颜色转换（支持 lab()/oklch()）取实际渲染 RGB 计算 WCAG 比值，比手算 oklch 更准；焦点环取 computed outline/box-shadow。
- 键盘：Tab 遍历至重试按钮（BUTTON[重试]，tabindex 0）；Tab 组件为 Base UI（roving tabindex，今日 tabindex=0 / 本周·本月 tabindex=-1，aria-selected ✓）。
- 限制：MCP 浏览器会话存在标签页漂移（与 fe-task01 相同环境问题），徽章墙 items=[] 空态与趋势 data=[] 空态为**静态验证**（真实数据下 task01test 徽章 0/8 有 8 个锁定徽章、趋势有 14 个 0 点，不触发空态分支）；空态文案已确认在代码路径且非 aria-hidden。

## 三态实测

### 骨架屏（loading）
- ✅ KPI：`KpiCard.tsx:117-119` 值位渲染 `sr-only`「loading」，a11y 树实测出现 4 个 loading 节点（读屏器可感知）；骨架块 `animate-pulse bg-slate-100`。
- ⚠️ PointCard：`PointCard.tsx:85` loading 时大数字显示「—」（em dash），读屏器读「dash/em dash」，无语义；3 行 pulse 无文字（可接受）。
- ✅ RankList：5 行 `animate-pulse` 骨架，无文字（空 div 不朗读，可接受）。
- ✅ StreakBadge：页面级骨架 `page.tsx:341` `<div class="animate-pulse bg-muted rounded-xl h-48" aria-hidden="true">` — aria-hidden ✓。
- ✅ 徽章墙：loading 用 `description="加载中…"`（页面注入）✓。

### 错误态（route 拦截 500 实测）
- ✅ 6 张错误卡全部渲染：学习数据加载失败（KPI 整区 + 打卡位 + 趋势）、能力评估加载失败（雷达）、积分数据加载失败、徽章数据加载失败、排行榜加载失败；**无 0 值兜底**（符合「后端错误绝不显示 0」）。
- ✅ 重试按钮：native `<button type="button">`，可访问名称「重试」，Tab 可聚焦，68×32px（≥24×24 ✓ 2.5.8），白字 on primary = **6.19:1** ✓。
- ✅ 焦点环：聚焦重试按钮 computed outline = `auto 0.667px lab(7.78…)`（slate-900 深色，对比 17.78:1）— 可见 ✓（globals.css:125 `outline-foreground`，较 fe-task01 的 `outline-ring/50` 已修复）。
- ❌ **错误卡无 aria-live / role=alert**：实测 `roleAlerts=[]`、errorCards `ariaLive=null` → 错误文案本身不会被自动播报；仅 sonner toast（`aria-live=polite`）兜底，但 toast 内容是原始 error message（实测为「boom」），且 6 个 query 同时失败弹 6 个 toast 重复轰炸。

### 空态
- ✅ 雷达空态（真实数据触发）：覆盖层文案「学习后即可生成学科能力评估」实测可读、**非 aria-hidden**，对比度 **4.73:1** ✓；全 0 雷达未渲染（符合规范）。
- ✅ 徽章墙空态（items=[]，静态验证）：`BadgeWallGrid.tsx:119-126` 虚线框 + 引导文案 + 原生 `<Link href="/courses">去课程中心看看</Link>`（可聚焦、可访问名称 ✓）。
- ✅ 趋势空态（data=[]，静态验证）：`ProgressTrendChart.tsx:208-213` 覆盖层文案「开始学习后，这里会记录你每天的学习时长」，text-muted-foreground on 白底（≈4.73:1），非 aria-hidden ✓。
- ⚠️ 排行空态：`RankList.tsx:141` `text-slate-400` 文案对比 2.62:1 < 4.5:1（见发现 #4）。

## 发现表

| # | 位置 | 严重度 | 原则 | 问题 | 修复建议 |
|---|------|--------|------|------|----------|
| 1 | `page.tsx:82-100`（DataErrorCard）；`ProgressTrendChart.tsx:193-207`、`AbilityRadarChart.tsx:198-212`（图表错误覆盖层） | HIGH | 4.1.3 / 1.3.1 | 错误态容器无 `role="alert"`/`aria-live`（实测 ariaLive=null、roleAlerts=[]），错误文案不会自动播报；sonner toast 兜底但内容为原始 error message 且 6 个失败弹 6 个 toast | DataErrorCard 与两个图表错误覆盖层加 `role="alert"`（或 aria-live="polite"）；toast 去重（失败聚合为一条） |
| 2 | `page.tsx:86`、`ProgressTrendChart.tsx:196`、`AbilityRadarChart.tsx:201`（text-destructive on bg-destructive/10） | HIGH | 1.4.3 | 错误卡文案（text-sm font-medium）实测 **4.45:1** < 4.5:1（canvas 实测，fg≈#EC003F on 白） | 错误文案改用更深红（如 destructive 加深一档 / `text-red-700` 等效）或加深 `bg-destructive/10` 底色，确保 ≥4.5:1 |
| 3 | `BadgeWallGrid.tsx:181-183`（「未获得」）、`:186-190`（「解锁：STUDY_MIN_TOTAL …」） | HIGH | 1.4.3 | 10px 辅助文案 `text-slate-400` 实测 **2.62:1**（canvas）< 4.5:1；本 task 引入真实数据后全部 8 徽章均显示解锁条件，问题暴露面扩大 | 改 `text-slate-600`（≈5.2:1）或加深一档 |
| 4 | `StreakBadge.tsx:55`（星期标签 `text-[10px] text-slate-400`）、`RankList.tsx:141`（空态文案 `text-slate-400`）、`PointCard.tsx:120`（空态 `text-slate-400`） | HIGH | 1.4.3 | 10-14px `text-slate-400` 实测 2.58–2.62:1 < 4.5:1（存量组件，fe-task06 未改样式但属页面审查面） | 统一改 `text-slate-600`；登记 fe-task07 收敛清单 |
| 5 | `ProgressTrendChart.tsx:192`、`AbilityRadarChart.tsx:197`（echarts canvas） | HIGH | 1.1.1 | 图表 canvas 无 `role="img"`/`aria-label`，趋势 14 天数据读屏器完全不可获取（雷达有数据时数值同样不可读；仅空态文本可读） | 为 canvas 容器加 `role="img"` + `aria-label`，并提供 `sr-only` 数据摘要（如「近 14 天每日学习时长 0 分钟」）或隐藏表格 |
| 6 | `PointCard.tsx:79-86`（大数字 `bg-gradient-to-br from-amber-500 to-fuchsia-600 bg-clip-text text-transparent`） | HIGH | 1.4.3 | 积分数字为渐变透明文字：amber-500 #f59e0b on 白 = **1.94:1**（<3:1 大文本线），数字左半不可读（存量 ad-hoc，fe-task07 收敛清单登记） | 改纯 `text-amber-700` 或加深渐变（两端 ≥3:1 大文本 / ≥4.5:1 常规） |
| 7 | `KpiCard.tsx:118`（`<span className="sr-only">loading</span>`） | LOW | 3.1.1 | sr-only loading 为英文，zh-CN 页面读屏器读「loading」 | 改「加载中」 |
| 8 | `PointCard.tsx:85`（loading 显示「—」） | LOW | 1.1.1 | 加载态大数字为 em dash，读屏器无语义 | 与 KpiCard 一致用 sr-only「加载中」+ 保留数字占位 |
| 9 | `layout.tsx:16-19`（root metadata title） | LOW | 2.4.2 | 全站共用「EduAgent · 智能学习助手」，/dashboard 无独立 page title 描述页面内容 | dashboard 页 `export const metadata` 或客户端 `document.title` 设「学习仪表盘 · EduAgent」 |
| 10 | `page.tsx:204` + 各 CardTitle（`ui/card.tsx:36` 渲染 div） | LOW | 1.3.1 | 整页仅 1 个 h1，无 h2/h3；KPI/趋势/雷达/徽章/排行各区块标题无 heading 语义（实测 h1=1, h2=0, h3=0） | 各数据区块标题升为 `<h2>`（CardTitle asChild 或页面包一层） |
| 11 | `StreakBadge.tsx:57`（`aria-label={"day-"+(i+1)+"-"+st}` on div） | LOW | 1.1.1 | 打卡单元格在无 role 的 div 上用英文编码 aria-label，读屏器读「day-1-rest」而非中文状态（存量） | 改中文可读标签（如「周一 未打卡」）或改 sr-only 文本 |
| 12 | `page.tsx:91-98` 及图表重试按钮（自定义 button） | LOW | 2.4.7 | 聚焦环为浏览器默认 `outline auto 0.667px`（slate-900，对比 17.78:1 ✓ 但 0.667px 偏细） | 补 `focus-visible:ring-2 ring-foreground` 显式焦点环 |
| 13 | `KpiCard.tsx:117`、`PointCard.tsx:110-118`、`RankList.tsx:131-137` | LOW | 1.3.1 | 骨架块为无文字 pulse div（除 KpiCard sr-only 外），读屏器静默无「加载中」提示（视觉可接受） | 可选：骨架容器加 `aria-label="加载中"`（不阻塞） |
| 14 | 全部 6 个 query 同时失败 | LOW | 4.1.3 | 错误 toast 重复轰炸（实测 sonner 6 条） | toast 失败聚合并去重（与 #1 合并修复） |

## 判定

- **结论：FAIL**（存在多项 WCAG 2.2 AA 违规；无 BLOCKER，但 6 项 HIGH 未达 AA）
- 违规统计：BLOCKER 0 项、HIGH 6 项、LOW 8 项（涉及 1.4.3 / 1.1.1 / 4.1.3 / 1.3.1 / 2.4.2 / 3.1.1 / 2.4.7）
- **阻塞项（必须修正后才能判 PASS）**：
  1. `DataErrorCard` 与图表错误覆盖层无 `role="alert"`/`aria-live`，错误不自动播报（#1，4.1.3）
  2. 错误卡文案对比度 4.45:1 < 4.5:1（#2，1.4.3）
  3. 徽章解锁条件/「未获得」10px 文案 2.62:1 < 4.5:1（#3，1.4.3）
  4. 打卡星期标签/排行空态/积分空态 `text-slate-400` 2.58–2.62:1 < 4.5:1（#4，1.4.3）
  5. 趋势/雷达 canvas 无替代文本（#5，1.1.1）
  6. 积分大数字渐变底最低 1.94:1（#6，1.4.3，存量登记 fe-task07）
- 实机验证覆盖率：真实数据态 / 错误态 / 骨架时序 / 对比度 / 键盘完整实测；徽章墙空态、趋势空态为静态代码路径验证（task01test 真实数据不触发该分支）。
- 通过项摘要：重试按钮名称/尺寸/对比度 ✓、焦点环可见 ✓、雷达空态文案可读且对比达标 ✓、骨架 aria-hidden/sr-only ✓、`<html lang="zh-CN">` ✓、`prefers-reduced-motion` 全局规则 ✓（globals.css:136-144）、Base UI Tab roving tabindex ✓。
