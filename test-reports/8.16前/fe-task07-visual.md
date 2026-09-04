# 视觉审查报告 fe-task07（用户端 9 页风格统一收敛 → 管理端基准）

- 审查 Agent：fe-visual-auditor
- 审查日期：2026-08-13
- 审查范围：用户端 9 页收敛后视觉验收（visual-acceptance ①②③④⑤⑥ 中 fe-visual-auditor 职责：⑤ 双 viewport 截图 + ② 语义色表覆盖枚举 + ③ grep 审计）
- **禁止改动业务代码：本次仅审查 + 出报告，零源码改动**

## 环境

- 前端工程：`edu-frontend`（Next.js 16.3 / React 19 / Tailwind v4，画像 `nextjs-16-app-router`）
- dev server：**复用** `test-reports/fe-task07-server-info.md`（`http://localhost:3000`，PID 16676，`startedByInfra=false`，未重复启动）；后端 `http://127.0.0.1:8000` 运行中
- 登录态：`POST /api/auth/login`（admin/Admin@12345）获取 JWT → 注入 `localStorage["edu:auth:token"]` + `["edu:auth:me"]`（roles:["admin"]，管理端 AdminGuard 需要）→ 刷新页面
- 浏览器：Playwright MCP（Chromium）
- 截图目录：`test-reports/screenshots/fe-task07/`
- **审查方法（诚实声明）**：当前模型不支持图像输入，无法进行像素级 Read 读图。故视觉验证采用**真实浏览器渲染证据替代**——① DOM 几何水平溢出检测（5 页 × 1440/375/720 三视口）；② 关键元素 `getComputedStyle` 实际渲染样式提取（背景/渐变/圆角/边框/文字色，与 tokens 逐项对照）；③ visual-acceptance §②③④ 全量 grep 审计。全部基于真实渲染结果，**不伪造截图、不臆断**。截图基线仍完整落盘，可供具备图像能力的审查者复核。

## 截图清单（15 张）

| # | 文件 | 视口 | 页面 | 用途 |
|---|------|------|------|------|
| 1 | dashboard-1440.png | 1440×900 | /dashboard | 用户端核心页 |
| 2 | dashboard-375.png | 375×812 | /dashboard | 375 回归 |
| 3 | community-1440.png | 1440×900 | /community | 页头渐变/分版/置顶 |
| 4 | community-375.png | 375×812 | /community | 375 回归 |
| 5 | achievements-1440.png | 1440×900 | /achievements | 页头渐变/奖牌 |
| 6 | achievements-375.png | 375×812 | /achievements | 375 回归 |
| 7 | courses-1440.png | 1440×900 | /courses | 封面渐变/价格/CTA |
| 8 | courses-375.png | 375×812 | /courses | 375 回归 |
| 9 | chat-1440.png | 1440×900 | /chat | 会话面板/状态点 |
| 10 | chat-375.png | 375×812 | /chat | 375 回归 |
| 11 | community-post-1440.png | 1440×900 | /community/48 | 帖详情（置顶角标） |
| 12 | community-post-375.png | 375×812 | /community/48 | 375 回归 |
| 13 | me-1440.png | 1440×900 | /me | 表单与 admin 同源 |
| 14 | admin-dashboard-1440.png | 1440×900 | /admin/dashboard | **管理端对比基准** |
| 15 | admin-dashboard-375.png | 375×812 | /admin/dashboard | 管理端 375 对照 |

> 命名遵守 visual-acceptance ⑤ `{page}-{viewport}.png`；`-dark` 全部 N/A（design-options §1.6 light-only 裁决，无 dark 验收项）；`-hc` 以既有 tokens 复核（状态色对比度组合见下方 ⑥ 说明，未新增色值）；`-200pct` 以 720 视口等效检测（见发现-通过项 ⑤）。

## 收敛达成度核对（视觉验收 ①②③④⑤）

### ① 壳一致性 —— 达成
- `grep -rl "w-64"` 全仓命中仅 `components/layout/AppShell.tsx:135`，无第二套壳实现；
- 品牌区 `from-primary-deep to-primary-strong` 唯一实现在 AppShell（:145 品牌图标、:179 导航激活态）；`(user)/layout.tsx:250` 同款命中属 **isAuthGate 分支**（登录/注册页独立品牌条，①-3 特判保留，非壳重复）；页头 hero 3 处（community:54 / courses:146 / achievements:31）为本次收敛的目标合法位置；
- 内容底：AppShell 默认 `pageClassName="bg-slate-100/70"`（注释「管理端基准」），用户端 `(user)/layout.tsx:268` 显式传同值，`(admin)` 用默认值——**两壳内容底同源一致**；渲染验证：两壳根容器 computedStyle 均为 `bg-slate-100/70`（oklab 0.968/0.7）；
- 管理端 shell 结构（AdminGuard 仅拦截非 admin；品牌区/激活态/抽屉全下沉 AppShell）与用户端逐项 diff 一致。

### ② 语义色表全覆盖枚举 —— 达成（双向核对）
- ②-1 越界色相 `(sky|violet|cyan|teal|fuchsia|orange|purple|blue|red|green|yellow|pink)-[0-9]+`：`src/app/(user)` **0 命中**；`src/components/` 命中仅 `auth/`（LoginForm/AuthCard/RegisterForm，登录注册入口，非本 task 9 页写路径）与 `admin/`（只读基准）；
- ②-2 状态色档位 `(amber|rose|emerald)-(300|400|500|600|700|800)`：用户端写路径 **0 真命中**（`profile/ProfileLayout.tsx:62` 命中为 fe-task07 注释文字，非 class）；命中集中在 auth/admin/ui（只读/范围外）；
- ②-3 主色/中性 token 化：`(user)` 仅 `layout.tsx:268 bg-slate-100/70`（内容底，管理端同源基底，合法）；写路径 0 命中；
- ②-4 语义 token 覆盖：`text-success|bg-success|text-warning|bg-warning|text-destructive|bg-destructive|bg-primary-soft|border-warning/40|border-destructive/30` 在用户端业务组件 **100+ 处命中**，保留清单场景全覆盖——置顶（PostCard:28 `border-warning/40 bg-warning/10`）、未读（ChatFloatingButton:106 `bg-warning text-white`）、在线（ChatPanel:233 `bg-success`）、错误态（RankingTabs:170 `border-destructive/30 bg-destructive/10`）、正负增减（PointLogTable:134）、完成率、回帖奖励（CommentSection:127 `text-success`）、星级豁免（ReviewList fill-warning）、奖牌（RankingTabs:44 text-warning）、回帖奖励等；
- **分功能多色收敛实证**：KpiCard ACCENT_MAP 6 色 → 全 `bg-primary-soft text-primary` + ring 光环清空（KpiCard.tsx:29-60）；BadgeWallGrid CAT_COLORS → 全 `bg-primary-soft text-primary border-primary-border`；PointCard 4 快捷项全主色；StatStrip/来源类型/点赞收藏激活统一主色。

### ③ grep 审计 —— **1 项残留（规格违背）**
| 命令 | 结果 |
|------|------|
| ③-1 arbitrary 色值（含 Tailwind v4 变体全集） | **0 命中**（写路径；auth 范围外有存量） |
| ③-2 内联 `style={{color/background}}` | **0 命中** |
| ③-3 `text-[Npx]` arbitrary 字号 | **0 命中**（写路径；auth/admin 范围外有存量） |
| ③-4 `via-` / 越界 `to-*` 渐变 | **0 命中**（用户端 9 页 + 业务组件；命中仅 app/page.tsx、not-found.tsx、auth/——登录入口，范围外） |
| ③-5 卡片 hover 漂移 | **0 命中**（用户端；`(admin)` 2 处 `hover:border-indigo-200` 为只读基准自身存量，非本 task 责任） |
| ③-6 分功能多色图标底 | **0 命中**（用户端写路径） |
| ③-7 `fill="#"`/`stroke="#"`/hex 属性 | **0 命中** |
| ③-8 ECharts hex 集中化 | **残留 2 处**：`src/components/dashboard/AbilityRadarChart.tsx:157`（splitArea `#f8fafc/#ffffff` 网格底色）、`:176`（数据点描边 `#fff`）——见「发现-规格违背-1」 |

### ④ 卡片规范 —— 达成
- `rounded-2xl` 手写卡：用户端写路径 **0 命中**；
- `bg-white/[0-9]` 半透明卡底：命中 11 处全部为 **hero/封面 overlay**（community/courses 页头 hero 玻璃拟态 `bg-white/10 backdrop-blur`、课程封面 Badge `bg-white/20`），符合 ④-2「overlay/遮罩层 backdrop-blur 非卡片场景可保留」例外，逐条可解释，非卡片底；
- `ring-1 ring-black/5`：**0 命中**；
- 卡片三段式实证：KpiCard `bg-card border-border shadow-card`、PointCard/RankList/StreakBadge/BadgeWallGrid/AbilityRadarChart/ProgressTrendChart 全部 `bg-card + border-border + shadow-card`；渲染验证卡片 `radius=14px`（rounded-xl）、borderColor=slate-200（lab 91.7）、白底（lab 100）；hover 统一 `hover:border-primary-border hover:shadow-card`（PostCard:28 实证）。

### ⑤ 双 viewport 视觉对比（与管理端基准）
- **水平溢出检测**：5 页（dashboard/community/achievements/courses/chat）× 1440/375/720（=200% 等效）共 15 组合，`scrollWidth - clientWidth = 0` **全部无水平溢出**；
- **管理端对比（真实渲染 computed style 对照）**：

| 对比点 | 用户端（收敛后） | 管理端（基准） | 结论 |
|--------|-----------------|---------------|------|
| 内容底 | `bg-slate-100/70`（oklab 0.968/0.7） | `bg-slate-100/70`（同值） | **一致** |
| 卡片 | `bg-card`(白) + 14px 圆角 + slate-200 边框 + 轻阴影 | `bg-white` Card + 14px 圆角 + slate-200 边框 | **一致** |
| 指标卡图标底 | KpiCard 全 `bg-primary-soft text-primary`（indigo 浅底） | MetricCards indigo=`bg-indigo-50 text-indigo-600`（primary-soft 同源 indigo 浅底），emerald/rose 仅状态语义（注释 D-01/02/03 收敛） | **一致**（主色 + 状态语义双轨同构） |
| 主 CTA | `bg-primary`（indigo-600, lab 38.4 52.6 -92.4）+ 白字 | 同 shadcn default variant `bg-primary` | **一致** |
| 状态语义色 | 置顶 `border-warning/40 bg-warning/10`、在线 `bg-success`(emerald-600)、未读 `bg-warning text-white`、错误 `border-destructive/30 bg-destructive/10` | 同 token 语义（ModuleTree 告警 amber、ServerTable ok emerald-600/error rose-500） | **一致** |
| 品牌渐变 | 页头 hero `from-primary-deep to-primary-strong`、封面 `from-primary-deep to-primary` | AppShell 品牌区同款 | **一致** |

- **视觉回归**：5 页首屏渲染无「加载失败」空态错误（server-info 交叉验证 + 本次实测标题/关键文本命中）；`/community/48` 帖详情、`/me` 表单渲染正常；卡片间距/对齐/层级无破坏迹象（computed style 圆角/边框/内边距与 tokens 一致）。

### ⑥ a11y/对比度（复核，非新增色值）
- 主色按钮白字 / indigo-600：≥4.5:1（既有 token 基准，未变）；
- 状态色组合：置顶 `text-warning-foreground on bg-warning/10`、错误 `text-destructive on bg-destructive/10`、成功 `text-success on bg-success/10` 与 fe-task00 对比度复核一致；星级 fill-warning（amber-500 图标 ≥3:1 非文字）；未读 `bg-warning text-white` 实心徽章（4.5:1+）；
- `text-4xs`（10px）仅装饰性角标/计数（RankList:180、PointLogTable 等），关键信息均有文字/结构补偿。

## 发现分类

### [规格违背]（必须修正）
| # | 位置 | 问题 | 期望 | 实际 |
|---|------|------|------|------|
| 1 | edu-frontend/src/components/dashboard/AbilityRadarChart.tsx:157,176 | ECharts option 内 2 处 hex 未集中到 chart-palette.ts（`#f8fafc` splitArea 网格底色、`#fff` 数据点描边），违反 visual-acceptance ③-8「全仓 0 命中除 chart-palette.ts」 | hex 收敛至 `chart-palette.ts` 常量（如 border/grid 或新增 white 常量） | 2 处 inline hex 残留 |
| 2 | （记录项）auth/ 登录注册入口（LoginForm.tsx:156、RegisterForm.tsx:209、AuthCard.tsx:38,44、app/page.tsx、not-found.tsx） | 存量 sky/teal 渐变与 `via-` 渐变未收敛 | 非 fe-task07 写路径（9 页清单外），由编排器裁决后续 task | 保持现状 |

> #1 色相合法（纯白/slate-50 中性，非越界色），视觉无感知影响，但按验收标准 ③-8 字面不达标；#2 为范围外记录，不参与本 task 判定。

### [浏览器行为错误]（必须修正）
- 无。5 页 × 3 视口渲染正常、无 console 布局错误、无水平溢出、无遮挡（DOM 几何检测 15 组合 0 溢出）。审查过程中 admin 账号注入初期出现过用户端路由自动跳转现象（/courses→/my-courses→/dashboard），复测后确认为 me 信息未注入时 ProtectedRoute 时序行为/工具时序假象，注入 me 后全部路由稳定渲染，**未列为缺陷**。

### [内容/文案]（建议修正）
- 无新发现（页头副标题、卡片文案均正常渲染，无截断/乱码）。

### [主观建议]（不强制）
- ③-8 修复时可在 chart-palette.ts 增加 `splitAreaBg: "#f8fafc"` 与 `pointBorder: "#ffffff"` 常量，与既有 entries 风格一致；
- `(admin)/questions/page.tsx:193`、`(admin)/courses/page.tsx:174` 存在 `hover:border-indigo-200 hover:shadow-sm`（hover 变体漂移），虽为管理端只读基准、非本 task 范围，建议编排器安排管理端轨任务统一为 `hover:border-primary-border hover:shadow-card`，保证「全站唯一规范」彻底闭环。

## 判定

- 结论：**FAIL**
- 阻塞项：
  1. `AbilityRadarChart.tsx:157,176` — ECharts option 内 2 处中性 hex（#f8fafc / #fff）未集中至 `chart-palette.ts`，视觉验收 ③-8 grep 审计不达标（规格违背，低严重度：色相合法、视觉无感知）。
- 非阻塞说明：视觉验收 ⑤（双 viewport 无溢出/无回归 + 管理端观感一致）、② 语义色表双向核对、④ 卡片规范、① 壳一致性全部达成；唯一 FAIL 项为 ③-8 形式残留。

## 机器可读结论（供评测自动断言）

```json
{
  "taskId": "fe-task07",
  "result": "FAIL",
  "blockers": [
    "AbilityRadarChart.tsx:157,176 ECharts inline hex (#f8fafc/#fff) 未收敛至 chart-palette.ts，违反 visual-acceptance ③-8（grep 审计残留，中性色，视觉无影响）"
  ],
  "screenshots": 15,
  "convergence": {
    "shellConsistency": "PASS",
    "semanticColorTable": "PASS",
    "gradientConvergence": "PASS",
    "cardSpec": "PASS",
    "grepAudit": "FAIL (1 residual)",
    "dualViewportNoRegression": "PASS"
  },
  "adminComparison": "PASS (content bg / card spec / primary accent / status semantics identical)"
}
```

## 审查结论摘要

- **收敛达成结论**：用户端 9 页风格收敛总体达成——分功能多色源（KPI 6 色/徽章 5 色/来源类型 3 色/StatStrip 3 态/点赞收藏双色/稀有度 4 色/页头三色渐变/积分渐变/装饰渐变）全部归位主色 indigo/中性 slate；状态语义色（success/warning/destructive）token 化并按保留清单完整保留（置顶/未读/在线/对错/增减/完成率/星级/奖牌/回帖奖励）；渐变收敛为 §1.2 三位置（品牌/封面头像/纯色）；卡片统一 `bg-card rounded-xl border-border shadow-card`；内容底、壳、主色、状态语义与管理端基准**逐项一致**；双 viewport（1440/375）与 200% 等效（720）无任何水平溢出/布局回归。
- **唯一阻塞**：③-8 grep 审计残留 2 处中性 hex（非越界色、视觉无感），修 1 处文件 2 行即可复测转 PASS。
- **方法备注**：本报告视觉验证基于真实浏览器渲染证据（computed style + DOM 几何 + grep 审计），非像素级读图（模型不支持图像输入）；15 张截图基线已落盘 `test-reports/screenshots/fe-task07/`，供像素级复核。
