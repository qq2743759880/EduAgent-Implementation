# 前端测试报告 fe-task07

- 测试角色：fe-tester（Web 前端测试工程师）
- 测试日期：2026-08-13
- 测试对象：fe-task07（用户端全页面风格统一收敛 → 管理端风格，已收敛 + 已修正）
- 判定：**PASS**
- 测试性质：只测试 + 报告，**零业务代码改动**

---

## 一、环境

| 项 | 值 |
|---|---|
| 工程 | `edu-frontend`（Next.js 16.3 / React 19 / Tailwind v4，画像 `nextjs-16-app-router`） |
| dev server | `http://localhost:3000`（复用 `test-reports/fe-task07-server-info.md`，PID 16676，`startedByInfra=false`，**未重复启动**） |
| 后端 | `http://127.0.0.1:8000` 运行中（PID 3692） |
| 登录态 | `fe_task07_test`（user_id 960，student）—— 浏览器 localStorage JWT 实测 |
| 测试工具 | Vitest v4.1.10（全量单测）+ `tsc --noEmit` + ESLint + Playwright MCP（Chromium 实测渲染/computed style/对比度） |
| 验证方法 | 单测全量 + 类型/静态检查 + grep 审计（visual-acceptance §②③④ 全集）+ 浏览器实测（5+ 页 × 1440/375 双 viewport + WCAG 对比度 canvas 精确计算） |

---

## 二、验收标准 ①-⑥ 逐条 Given/When/Then 映射

| 验收 | Given | When | Then | 结果 |
|---|---|---|---|---|
| ① 壳一致性 | `(user)/layout.tsx` 与 `(admin)/layout.tsx` 同引 AppShell（fe-task00）；两薄 layout 只注入配置 | grep 确认无第二套壳实现；逐项 diff 品牌区/激活态/抽屉 | ① `w-64` 侧边栏唯一实现 = AppShell.tsx（唯一非 AppShell 命中为 `admin-guard.tsx` AdminShellSkeleton，SSR 加载骨架占位，无菜单注入/交互，管理端基准合法）；② 品牌渐变 `from-primary-deep to-primary-strong` 唯一实现 = AppShell（:145 品牌图标、:179 激活态）；`(user)/layout.tsx:250` 同款为 isAuthGate 登录页独立品牌条（①-3 特判保留）；③ 写路径未触碰 AppShell.tsx 与两 layout | **PASS** |
| ② 语义色表全覆盖枚举 + 同类组件 diff | design-tokens `mappingTable` + `legalPalette` + `legalStatusColors`；design-options §2 保留清单 | 逐页核对颜色 class ⊆ 封闭色板；与 `(admin)` 同类 diff | ① 分功能多色全收敛（图标底/KPI/分版/稀有度/学科封面/StatStrip/来源类型/点赞收藏激活等全部单主色）；② 保留项（置顶/未读/在线/对错/增减/完成率/星级/奖牌/回帖奖励）未误删（双向核对，见 §五 grep 审计 ②-4：154 处语义 token 覆盖）；③ 与 admin 基准 diff 无偏离 | **PASS** |
| ③ 无 arbitrary 色值/硬编码（grep 0 违规） | visual-acceptance §3 命令全集（含 Tailwind v4 变体防御） | 执行全部 ③-1~③-8 | ③-1~③-7 用户端写路径 **0 命中**；③-8 ECharts hex **仅 chart-palette.ts**（本轮修正达成，见 §五）；`text-[Npx]` 仅例外清单（MarkdownView prose 15px，spec 豁免）；`src/lib/api/curriculum.ts` SUBJECT_OPTIONS 的 `bg-sky-500` 等为**数据层死字段**（用户端零渲染引用，封面已统一主色渐变，且在审计命令范围外） | **PASS** |
| ④ 卡片/边框/圆角/阴影符合设计系统 | 卡片规范 `bg-card rounded-xl border-border shadow-card`（hover `hover:border-primary-border hover:shadow-card`） | 逐卡片核对用户端手写卡 | ① `rounded-2xl` 手写卡 0（唯一用户端命中为 ChatPanel 浮动面板容器 `h-[560px] max-h-[80vh]`，非卡片容器，逐条可解释）；② `bg-white/[0-9]` 命中全为 hero/封面 overlay + backdrop-blur（④-2 例外，逐条可解释）；③ `ring-1 ring-black/5` → `ring-border`（ChatPanel.tsx:206，D5）；④ hover 变体统一（PostCard/SourceCardList/ChatPanel/CourseCard/MyCourseCard 均 `hover:border-primary-border hover:shadow-card`）；⑤ `ui/card.tsx` 未改（GAP-03 挂账，符合写路径边界） | **PASS** |
| ⑤ 1440/375 双 viewport 对比管理端无视觉回归 | fe-visual-auditor 截图基线；本 tester 以真实渲染证据复核 | 5+ 页（dashboard/community/achievements/courses/chat/my-courses/me）× 1440/375 实测 | ① 无水平溢出（全部页面 1440/375 `scrollWidth - clientWidth = 0`）；② 无残留 sky/violet/fuchsia/orange 色相（375 实测 0 残留）；③ 主色/卡片/状态语义与管理端一致（图标底 indigo 浅底、卡片白底 14px 圆角 slate-200 边框、CTA bg-primary）；④ 375 抽屉行为正常（sidebar 移出 -256px，移动抽屉关闭态） | **PASS** |
| ⑥ a11y 三路审查（本轮修复验证） | a11y 报告 5 BLOCKER + 7 HIGH；globals.css 已定义 `-foreground` 深档 token | 浏览器 canvas 精确计算 B1-B5 + H1-H7 实测对比度 | B1-B5 全部 ≥4.5:1（实测 5.03，原 2.13-2.15）；H1 5.36 / H2 5.09 / H3 6.03·5.49 / H4 6.03 / H5 5.03 / H6 4.58 / H7 13.31 全部达标（见 §四对比度表）；焦点/aria 零回归（收敛只改 className） | **PASS** |

---

## 三、单测统计

| 项 | 结果 |
|---|---|
| 命令 | `npx vitest run`（edu-frontend 目录，vitest v4.1.10） |
| Test Files | **30 passed (30)** |
| Tests | **256 passed (256)** ✅（任务要求 256+ 用例绿） |
| 时长 | 17.51s |
| 退出码 | 0 |
| 日志 | `test-reports/fe-task07-fe-test-vitest.log` |

---

## 四、静态校验

| 检查 | 命令 | 结果 |
|---|---|---|
| 类型检查 | `npx tsc --noEmit` | **0 errors**（TSC_EXIT=0） |
| 静态检查 | `npm run lint` | **25 errors / 29 warnings —— 全部存量，非收敛引入**（见下） |

**lint 存量判定依据**：
1. 错误类型全为 `react-hooks/*`（exhaustive-deps / rules-of-hooks / preserve-manual-memoization / setState-in-effect）、`@typescript-eslint/no-explicit-any`、React Compiler 优化提示——均与 className/颜色收敛无关；
2. 错误文件 `src/components/learning/hooks/useVideoTicks.ts`、`src/components/ui/radio-group.tsx`、`src/lib/api/learning.ts`、`src/lib/api/curriculum.ts` **git diff 未修改**（纯存量）；
3. 收敛文件（QuizPanel/VocabDailyPanel/ChatSessionSidebar/MyCoursesClient/SubjectLevelFilters）的 diff 经逐行核对**全部为 className/颜色 token 变化**，lint 错误行（如 QuizPanel:104 `useInitialAnswer` 在 callback 内、:230 impure function、ChatSessionSidebar:109 useState）位于收敛 diff 之外；
4. `scripts/*.mjs` 4 个 task05 验证脚本 lint 错误为历史遗留测试脚本，非本 task 写路径。

> 结论：fe-task07 收敛**未引入任何新 lint error**；25 errors 存量问题（React Compiler 严格规则下的既有 hooks 模式）建议编排器安排后续 task 统一治理，不阻塞本 task 判定。

---

## 五、grep 审计（visual-acceptance §②③④ 全集）

范围：用户端写路径 = `src/app/(user)` + `src/components/{dashboard,community,achievement,learning,chat,curriculum,profile}`（admin/auth/ui/AppShell/两 layout 只读范围外）。

| 命令 | 结果 | 判定 |
|---|---|---|
| ②-1 越界色相 `(sky\|violet\|cyan\|teal\|fuchsia\|orange\|purple\|blue\|red\|green\|yellow\|pink)-[0-9]+` | 用户端写路径 **0 命中**；命中仅 auth/not-found（范围外）+ `lib/api/curriculum.ts`（数据层死字段，无渲染引用） | ✅ |
| ②-2 状态色档位 `(amber\|rose\|emerald)-(300\|400\|500\|600\|700\|800)` | 用户端写路径 **0 真命中**（命中均为注释文字「amber-700 档」或 admin/auth 范围外） | ✅ |
| ②-3 主色/中性 token 化（indigo/slate 直接档位） | 用户端写路径仅 2 处中性骨架/角标可解释：RankList:134 `bg-slate-100/80`（loading 骨架动画）、BadgeWallGrid:175 `bg-slate-700/80`（徽章计数角标深底）——非分功能多色、非卡片 | ✅ |
| ②-4 语义 token 覆盖 `text-success\|bg-success\|text-warning\|bg-warning\|text-destructive\|bg-destructive\|bg-primary-soft\|border-warning/40\|border-destructive/30` | **154 处命中**（用户端 7 组件目录），保留清单场景全覆盖（置顶/未读/在线/对错/增减/完成率/星级/奖牌/回帖奖励/错误态） | ✅ |
| ③-1 arbitrary 色值（含 Tailwind v4 变体全集） | 用户端写路径 **0 命中** | ✅ |
| ③-2 内联 `style={{color/background}}` | **0 命中** | ✅ |
| ③-3 `text-[Npx]` arbitrary 字号 | 用户端写路径 **0 命中**；唯一用户端组件命中为 MarkdownView.tsx:27 `text-[15px]`（prose 语境，spec §1.4 明确「prose 语境不收编」豁免） | ✅ |
| ③-4 `via-` / 越界 `to-*` 渐变 | 用户端写路径 **0 命中**（命中仅 not-found/page.tsx/auth，范围外） | ✅ |
| ③-5 卡片 hover 漂移 `hover:border-(indigo\|primary/40\|violet)\|hover:shadow-sm` | 用户端写路径 **0 命中** | ✅ |
| ③-6 分功能多色图标底 | 用户端写路径 **0 命中**（命中仅 admin/auth，范围外） | ✅ |
| ③-7 `fill="#"` / `stroke="#"` / `backgroundColor: "#"` | **0 命中** | ✅ |
| ③-8 ECharts inline hex 全仓（除 chart-palette.ts） | **仅 `src/lib/chart-palette.ts` 命中**（19 处受控色板，含本轮新增 `splitAreaBg: "#f8fafc"` 与 `white: "#ffffff"`）；`AbilityRadarChart.tsx` 0 inline hex（157/176 行已改引 `CHART_COLORS.splitAreaBg` / `CHART_COLORS.white`） | ✅ **本轮修正达成** |
| ④-1 `rounded-2xl` | 用户端写路径 0 卡片命中（ChatPanel.tsx:206 为浮动面板容器非卡片，可解释） | ✅ |
| ④-2 `bg-white/[0-9]` | 命中全为 hero/封面 overlay + backdrop-blur（④-2 例外清单） | ✅ |
| ④-3 `ring-black` | **0 命中**（ChatPanel 已改 ring-border） | ✅ |
| ④-4 卡片规范三段式 | 代表性卡均含 `bg-card`/`rounded-xl`/`border-border`/`shadow-card`（PostCard.tsx:27、SourceCardList.tsx:122、ChatPanel.tsx:512 等，computed style 实测 radius=14px / border=slate-200 / bg=白） | ✅ |
| ①-1 壳唯一实现 | `w-64` 命中 = AppShell.tsx 唯一壳；admin-guard.tsx 为骨架占位 | ✅ |

---

## 六、浏览器实测（Playwright localhost:3000，fe_task07_test 登录）

### 6.1 收敛达成（真实渲染 computed style）

| 收敛点 | 实测结果 | 判定 |
|---|---|---|
| 快捷入口/KPI 图标底多色 → 单主色 | 6 处图标底全部 `bg-primary-soft`（lab 95.48≈indigo-50）+ `text-primary`（lab 38.40≈indigo-600） | ✅ |
| 卡片规范 | 白底（lab 100）+ 圆角 14px（rounded-xl）+ border slate-200（lab 91.74）+ shadow | ✅ |
| dashboard 页头/数据区 | 1440/375 均 0 溢出；RankList 骨架/我的排名正常 | ✅ |
| community 页头三色渐变 → 品牌渐变 | `bg-gradient-to-r from-primary-deep to-primary-strong`（lab 16.13 → 32.45）实测 | ✅ |
| community 分版四色 → 单主色 | 分版 badge 全部 `bg-primary-soft text-primary`（含文字 label「综合」等） | ✅ |
| community 置顶 amber → warning token | 置顶卡 `border-warning/40 bg-warning/10`（oklab 0.769/0.4 + 0.1）保留状态语义 | ✅ |
| achievements 页头琥珀渐变 → 品牌渐变 | `from-primary-deep to-primary-strong` 实测 | ✅ |
| achievements 稀有度四色 → 中性 + label | 稀有度 badge 全部 `border-border text-muted-foreground`（lab 48.09≈slate-500）+ 文字「普通/稀有/史诗/传说」 | ✅ |
| courses 学科封面五色 → 统一主色渐变 | 封面全部 `bg-gradient-to-br from-primary-deep to-primary`（lab 16.13 → 38.40） | ✅ |
| courses 价格 amber/rose → 中性字重 | 现价 `text-xl font-bold text-foreground`（lab 7.79≈slate-900）+ 原价 `text-muted-foreground line-through` 实测 | ✅ |
| courses CTA amber → bg-primary | 搜索/全部按钮 `bg-primary`（lab 38.40）+ 白字（lab 98.26） | ✅ |
| my-courses StatStrip 三态色 → 全主色 | 统计图标底 3 处全部 `bg-primary-soft text-primary`；卡片 bg-card rounded-xl border-border | ✅ |
| chat 头像/空态渐变 | 全部 `from-primary-deep to-primary`（lab 16.13 → 38.40） | ✅ |
| chat 未读 badge → warning-foreground | `bg-warning-foreground text-white`（lab 47.27≈amber-700）—— **B2 修复实测** | ✅ |
| me 编辑徽章 → warning-foreground | 源码 ProfileLayout.tsx:62 `bg-warning-foreground` 确认；页面 0 越界色/0 arbitrary 字号 | ✅ |
| 375 抽屉行为 | desktop sidebar 移出视口（left -256px），移动抽屉关闭态，`打开导航` 按钮在 banner | ✅ |

### 6.2 对比度修复验证（canvas oklch→sRGB 精确计算，WCAG 2.2 AA）

| # | 色对 | 修复前（a11y 报告） | 修复后实测 | 门槛 | 判定 |
|---|---|---|---|---|---|
| B1/B4 | white on `bg-warning-foreground`（打卡徽章/partial 格） | 2.13 ❌ | **5.03** | 4.5 | ✅ |
| B3 | `text-warning-foreground` on white（均分数字） | 2.15 ❌ | **5.03** | 4.5 | ✅ |
| B5 | `fill-warning-foreground` on white（星级，1.4.11） | 2.15 ❌ | **5.03** | 3.0 | ✅ |
| H1 | `text-success-foreground` on white（回帖奖励/增减小字） | 3.65 ❌ | **5.36** | 4.5 | ✅ |
| H2 | `text-success-foreground` on bg-success/10 | 3.28 ❌ | **5.09** | 4.5 | ✅ |
| H3 | `text-destructive-foreground` on bg-destructive/10（错误态） | 3.94 ❌ | **5.49** | 4.5 | ✅ |
| H4 | white on `bg-destructive-foreground`（实心危险按钮） | 4.32 ❌ | **6.03** | 4.5 | ✅ |
| H5 | `text-warning-foreground` on white（第一名奖牌图标） | 2.15 ❌ | **5.03** | 3.0 | ✅ |
| H6 | `bg-warning-foreground` vs `bg-muted`（评分统计条，1.4.11） | 1.96 ❌ | **4.58** | 3.0 | ✅ |
| H7 | `text-secondary-foreground` on bg-muted（系统消息正文） | 4.35 ❌ | **13.31** | 4.5 | ✅ |

**结论：5 BLOCKER + 7 HIGH 全部实测达标（B 系 5.03:1、H 系 4.58-13.31:1），无残留违规。**

### 6.3 布局回归 / console

| 检查 | 结果 |
|---|---|
| 水平溢出（dashboard/community/achievements/courses/chat/my-courses/me × 1440/375） | 全部 0 溢出（`scrollWidth - clientWidth = 0`） |
| 375 残留越界色相 | 0 残留 |
| console errors | 3-6 条/页，**全部为同一 403**（`GET /api/chat/sessions/s_95258dc7d820/history`）——token 属 fe_task07_test(960)，last_session_id 为 task01test 遗留，后端正确拒绝跨账号会话访问；**业务鉴权行为，非收敛引入、非布局错误**（server-info 亦确认既有登录态下 0 错误） |
| 键盘/aria | 收敛只改 className，aria-pressed / role=list / roving tabindex 等零改动（a11y 报告交叉确认） |

---

## 七、遗留项（不阻塞）

| # | 项 | 级别 | 说明 |
|---|---|---|---|
| 1 | lint 25 errors / 29 warnings 存量 | 建议治理 | React Compiler 严格规则下的既有 hooks 模式 + no-explicit-any + task05 测试脚本；非 fe-task07 引入（见 §四判定依据） |
| 2 | `src/lib/api/curriculum.ts` SUBJECT_OPTIONS `color` 字段含 `bg-sky-500` 等死数据 | 建议清理 | 用户端零渲染引用（封面已统一主色渐变），数据层残留，建议后续 task 清理或改注释 |
| 3 | `(admin)` 只读基准自身存在 `hover:border-indigo-200` 等（admin/courses、admin/questions） | 范围外 | 管理端轨 fx-task 审计范围，visual 报告亦已记录 |
| 4 | auth 登录注册页 sky/teal 渐变 | 范围外 | fe-task07 9 页清单外，由编排器裁决后续 task（a11y/visual 双报告一致记录） |
| 5 | `chart-palette.test.ts` 不存在 | 低 | spec 未要求，chart-palette 为纯常量文件；如需可后续补 |
| 6 | chat 页因浏览器会话残留旧会话 ID 触发 403 toast | 环境噪音 | 刷新/新会话即无；属账号切换遗留，非应用缺陷 |

---

## 八、结论

**判定：PASS**

- 单测 **30 文件 / 256 用例全绿**（含 dashboard/community 派生纯函数与四态用例），`tsc --noEmit` **0 errors**；lint 25 errors 全存量（收敛 diff 零重叠，未引入新问题）。
- 本轮两项修正均实测达成：**a11y 对比度（5 BLOCKER + 7 HIGH → 全部 ≥4.5:1 / ≥3:1）**、**visual ③-8 ECharts hex 集中（AbilityRadarChart 0 inline hex，全仓仅 chart-palette.ts）**。
- 验收 ①-⑥ 全部通过：壳一致性 / 语义色全覆盖枚举 / grep 0 违规 / 卡片规范 / 双 viewport 无回归 / a11y 达标。
- 收敛目标态实测确认：分功能多色消失（图标底/KPI/分版/稀有度/学科封面/StatStrip/来源类型/点赞收藏激活全部单主色 indigo）、状态色 token 化且仅状态场景（success emerald / warning amber / destructive rose，均用 -foreground 深档保证对比度）、卡片规范三段式、渐变仅品牌/封面/纯色 3 位置、arbitrary 色值与字号 0 命中。
- 无布局回归、无收敛相关 console 错误（403 为跨账号遗留会话的业务鉴权行为）。

**机器可读结论**

```json
{
  "taskId": "fe-task07",
  "result": "PASS",
  "blockers": [],
  "unitTests": { "files": 30, "tests": 256, "passed": 256 },
  "typecheck": "0 errors",
  "lint": { "errors": 25, "allPreExisting": true },
  "grepAudit": {
    "arbitraryColors": 0, "inlineColors": 0, "arbitraryFontSize": "0 (prose exception)",
    "gradientAbuse": 0, "hoverDrift": 0, "multiColorIcons": 0, "hexAttrs": 0,
    "echartsHex": "only chart-palette.ts"
  },
  "a11yFix": { "B1-B5": "5.03:1 (>=4.5)", "H1-H7": "4.58-13.31:1 (>=4.5/3.0)" },
  "viewport": { "1440": "0 overflow", "375": "0 overflow, 0 residual hue" },
  "consoleErrors": "403 cross-account stale session only (business auth, not regression)"
}
```

报告已写入 `test-reports/fe-task07-fe-test-report.md`；过程日志留档：`test-reports/fe-task07-fe-test-vitest.log`、`fe-task07-fe-test-tsc.log`、`fe-task07-fe-test-lint.log`。本轮测试零源码改动。
