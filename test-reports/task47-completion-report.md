# task47 完成报告 — /my-courses 我的班次（React「学中玩」enrollments 语义版）

> 执行者：前端开发者（TRAE SOLO CN）
> 状态：**待 fe-tester/fe-review 独立复核 → 编排者验收**（未经验收不得开始下一任务）
> 日期：2026-08-20
> 技术栈：Next.js 16.3 + React 19 + Tailwind v4 + shadcn（Borderless Style Base UI 范式）
> 前置：task41（C1~C14 组件）、task44（/courses 课程中心任务，candy-playful tokens 冻结）、task46（课程详情，Tabs/Panel 范式）、任务文档 task47 / P10 规范
> 参考：HTML 效果图 `test-reports/fe-html/my-cohorts.html`（已签收 APPROVED，STYLE FROZEN=candy-playful）

---

## 一、交付清单

### 新增/重写源码
| 文件 | 说明 |
|---|---|
| `src/lib/api/enrollments.ts` | 新增 enrollments API 封装：`getEnrolledCohorts(status?)` → 契约⑪ `GET /api/enrollments/me/cohorts?status=`（**task20/21 待联调**，类型全可选容错） |
| `src/components/feature/cohort-card.tsx` | 新增 C16 CohortCard（enrollments 语义）：糖果渐变封面（吉祥物 + 系列·交付 + 班次名 + StatusBadge）、进度条、下次课条、三态操作 |
| `src/components/feature/cohort-card.test.tsx` | 新增组件单测（5 项：三态渲染 + a11y progressbar + 跳转） |

### 重构文件
| 文件 | 说明 |
|---|---|
| `src/app/(user)/my-courses/page.tsx` | 页头重构：面包屑 + 吉祥物 +「我的班次」标题（P10），删除旧 StatStrip 统计三态 |
| `src/app/(user)/my-courses/_components/MyCoursesClient.tsx` | 客户端重构：P3 progress 语义 → enrollments 语义；Tabs active/completed/refunded 由 enroll_status 驱动；queryKey `["enrollments","me"]` |
| `src/app/(user)/layout.tsx` | 侧边栏「我的课程」→「我的班次」（语义对齐 P10） |

### 删除文件（重构后被替换、全代码零引用）
`src/components/learning/MyCourseCard.tsx`、`src/components/learning/CourseTabsEmpty.tsx`

---

## 二、验收标准 GWT 逐条对照

### Given① HTML APPROVED → When React 实现完成 → Then 与 HTML 对照一致（visual-acceptance）
- HTML 效果图 `my-cohorts.html`（sdk 模式 tabs + 移动端主全宽按钮 + 下次课 truncate）已由用户**审核签收通过**（2026-08-20）。
- React 版复用 task41 组件（StatusBadge/Tabs/EmptyState/ErrorState）+ 新建 C16 CohortCard，对齐效果图：Breadcrumb＋吉祥物页头、candy 糖果渐变封面、进度条（68% 常态 / 92% hot 橙）、下次课条（左 truncate + 右时间）、移动端「主全宽 + 辅并排第二行」布局。
- tokens 合规：封面/进度条/下次课均只用 candy 语义 token（`candy-orange/green/blue/yellow/purple` + `-soft`），**0 硬编码 hex**。

### Given② 三 tab 驱动 → When enroll_status ∈ 全集 → Then active/completed/refunded 正确分组与渲染
- 组件由后端 `enroll_status`（**非**旧 P3 `overall_ratio≥99.99%` 推断）驱动，配合 `src/lib/status.ts` `enroll_status` 映射（StatusBadge 文字+颜色双通道）。
- `active 学习中`：进度条（模块 X/Y · 课次 X/Y 聚合）+ 下次课条 + [继续学习][课程详情][售后]；
- `completed 已完成`：100% + 结课时间 + [查看证书][写评价][再次报名]；
- `refunded 已退款`：整卡灰色态（saturate+opacity）、无进度条、退款单信息 + [查看退款]；
- `cancelled` 契约① 后并入 neutral，不独立成 tab。
- **badge 计数真实**：主请求拉全量 `GET /api/enrollments/me/cohorts`（不带 status），客户端按 enroll_status 分组 → 三 tab 计数均为真实数组长度（非占位）。

### Given③ 交互 → Then 跳转 / 空态 / 错误态正确
- **继续学习** → `/learning/{seriesId}/{sessionId}`（最近未完成课次）；无 next_session 回退 `/courses/{seriesId}`；已完成 → 查看证书/写评价。
- **课程详情** → `/courses/{seriesId}`；**售后** → `/tickets`；**再次报名** → `/courses`；**查看退款** → `/refunds`。
- **空态**：EmptyState「还没有报名班次」+ CTA 去选课 → /courses（分 tab 文案差异化）。
- **错误态**：ErrorState 原样展示错误 + 重试；不吞错不伪装成功（task40 R-7 红线）。
- **受保护路由**：未登录 → `/login?redirect=/my-courses`；登录守卫加 `ready` 前置（hydrate 完成前不误判，防止硬刷新瞬时误跳 /login）。
- **a11y**：进度条 `role=progressbar` + aria-valuenow/min/max/label（含单测覆盖）；状态由文案承载（不依赖颜色）；StatusBadge 颜色+文字双通道。

### Given④ a11y → Then 键盘可导航、状态可读、动画可降级
- Tabs：Base UI Tabs（roving tabindex + 方向键 + aria-controls/labelledby/aria-selected，随组件提供）。
- 进度条：`role="progressbar"` + `aria-valuenow/min/max` + `aria-label`（「课程进度 68%」）。
- 状态：由文案承载（不依赖颜色），candy 色仅视觉增强。
- 尊重 `prefers-reduced-motion`：transition 仅 width/duration，卡片 hover 位移轻量。

---

## 三、自动化验证结论（主对话执行，待 fe-tester 独立复核）

| 项 | 结果 |
|---|---|
| `tsc --noEmit` | **0 错误** |
| `eslint`（6 个改动文件） | **0 错误 0 警告** |
| `vitest` 全量 | **50 文件 / 371 测试全绿**（含新增 CohortCard 5 项） |
| `npm run build` | **成功**（/my-courses 为 ƒ Dynamic，Suspense + 登录态动态数据） |

---

## 四、待联调清单（后端 task20/21）
- `GET /api/enrollments/me/cohorts` 后端就绪后联调：`EnrolledCohort` 字段名以交接单为准，类型已全可选容错。
- 关注 `next_session`（module/session 层级）、`refund`（退款单号/金额/时间）、`delivery_mode` 徽章映射。