# task46 完成报告 — /courses/[seriesId] 课程详情（React「学中玩」版）

> 执行者：前端开发者（TRAE SOLO CN）
> 状态：**待编排者验收**（未经验收不得开始下一任务）
> 日期：2026-08-20
> 技术栈：Next.js 16.3 + React 19 + Tailwind v4 + shadcn（Borderless Style Base UI 范式）
> 前置：task44（/courses 课程中心）、task41（C1~C14 组件）、task11（契约② series/cohorts/modules）
> 参考：HTML 效果图 `test-reports/fe-html/course-detail.html`（已签收 APPROVED）

---

## 一、交付清单

### 新增/重写源码
| 文件 | 说明 |
|---|---|
| `src/app/(user)/courses/[seriesId]/page.tsx` | async server component：await params 解析 seriesId → 渲染 CourseDetailClient |
| `src/app/(user)/courses/[seriesId]/_components/CourseDetailClient.tsx` | 客户端主逻辑：四态（loading/error/empty/success）+ 班次联动 + 报名/领券/收藏 + 数据流编排 |
| `src/components/curriculum/CourseDetailHero.tsx` | Hero 2:3 分栏：糖果渐变封面（白字标题 + 吉祥物 + facts）+ 购买面板（班次选择/价格联动/收藏 aria-pressed/领券/立即报名/费用明细） |
| `src/components/curriculum/CohortList.tsx` | 班次 RadioGroup 卡：价格/剩余席位/容量进度条/满员 disabled |
| `src/components/curriculum/CouponPicker.tsx` | 领券弹窗（Dialog）：GET /api/coupons?series_id= 模板列表、领取、已领取可勾选抵扣（radio aria-label 含券名） |
| `src/components/curriculum/FavoriteButton.tsx` | 收藏按钮：aria-pressed + aria-label 双通道，未登录跳 /login?redirect= |
| `src/components/curriculum/CourseDetailSyllabus.tsx` | 课程大纲四级树：module（stage_no 升序）→ session（session_no 升序）+ teaching_status 徽章双通道 |
| `src/components/curriculum/CohortDetailPanel.tsx` | 班次详情面板：开班/结课/容量/班主任等 |
| `src/components/curriculum/CourseDetailTabs.tsx` | Tabs 四栏：课程大纲/班次详情/课程评价/思维导图（Base UI tablist 语义） |
| `src/lib/api/coupons.ts` | 新增 `listSeriesCoupons(seriesId)` → GET /api/coupons?series_id= |
| `src/test/setup.ts` | 补 ResizeObserver mock（Base UI TabsList 依赖构造函数形态） |

### 测试文件（新增 2 个，共 16 项）
`page.test.tsx`(9：四态 + 班次联动 + 满员默认回退 + 未登录/登录交互) / `course-detail-components.test.tsx`(7：CohortList/FavoriteButton/CouponPicker/Syllabus/Tabs/Hero)

---

## 二、验收标准 GWT 逐条对照

### Given① HTML APPROVED → When React 实现完成 → Then 与 HTML 对照一致（visual-acceptance）
- HTML 效果图 `course-detail.html` 经 SOP 返工后 **用户签收通过**（2026-08-20），STYLE FROZEN=candy-playful。
- React 版复用 task44/41 组件（CourseCard/C2 Pagination/C14 PriceText/C7 EmptyState/C8 ErrorState），新建 7 个课程详情专用组件，结构对齐效果图（Breadcrumb/Hero 2:3/购买面板/CohortList/Tabs 四栏）。
- fe-visual-auditor 对照效果图审查：tokens 合规（0 硬编码色值）、teaching_status 徽章文字+颜色双通道；P2 视觉细节偏差（购买面板顺序/封面三色渐变/选中态颜色等）记录为非阻断。

### Given② 选中班次 → When 点击立即报名（cohort_id + coupon_receive_record_id）→ Then 创建订单成功跳支付页；满员 disabled；未登录跳 /login?redirect=
- **下单**：`POST /api/trade/order`（series_id + cohort_id + coupon_id + Idempotency-Key=crypto.randomUUID()），成功 toast 订单号（支付页 task47 接入后跳转）。
- **满员 disabled**：`current_student_count >= max_student_count` 班次在 CohortList 中 disabled；默认选中「最低价在售且有席位」班次（P1 修复：排除满员，含回退 cohorts[0]）。
- **未登录**：报名/领券/收藏均 `router.push('/login?redirect=%2Fcourses%2F{id}')` 原路返回（测试断言 pushMock 收到编码 redirect）。

### Given③ 领券与收藏 → Then 领券弹窗刷新可用券列表；收藏写 favorite_source=series_detail 且心形与登录态联动
- **领券**：弹窗懒加载 `GET /api/coupons?series_id=`（couponOpen && authed 才 enabled）；领取 `POST /api/trade/coupon/receive` 幂等；已领取态交叉标记（listMyCoupons + 本会话新领）→ 可勾选抵扣（radio 选中 coupon_id 用于下单）。
- **收藏**：`GET/POST/DELETE /api/favorites`（target_type=series）；FavoriteButton aria-pressed 双通道；未登录跳登录页。

### Given④ 四级树渲染 → Then series→cohort→module（stage_no 升序）→session（session_no 升序）层级正确
- CourseDetailSyllabus 按 `stage_no` 升序渲染模块、`session_no` 升序渲染课次；teaching_status 徽章（scheduled/in_progress/completed/cancelled）文字+颜色双通道；随选中班次联动刷新（queryKey `["cohort_modules", cohortId]`）。

---

## 三、独立 fe-tester 复核结论

独立子代理（fe-tester）全量验证，**结论：APPROVED**（无 P0/P1）：
- **vitest 全量：49 文件 / 366 测试全绿**（task46 页面 9 + 组件 7 全绿）
- **tsc --noEmit**：0 错误
- **eslint**：task46 12 文件 0 错误 0 警告；项目 `npm run lint` 退出码 0
- **grep 硬编码色值审计**：0 违规（仅 2 处动态 width 进度条，非色值）
- **next build**：成功，`/courses/[seriesId]` 动态路由正常注册
- **Playwright**：后端不可用 → error 态（加载失败+重试）与无效 id → empty 态（课程不存在）均渲染正确；截图 `test-reports/screenshots/task46-{loading,error,empty}.png`

## 四、独立 fe 审查复核结论（≤3 轮）

独立子代理（fe-a11y/perf/visual-auditor）两轮审查：
- **第 1 轮 NEEDS_FIX**：P1（默认班次未排除满员）+ P2 若干。
- **修复**：P1 加 `.filter((c) => c.current_student_count < c.max_student_count)` + 补测试「最低价班次满员时默认选中下一个有席位班次」；P2 修 3 项（loading 骨架 role="status"+aria-live、抵扣 radio aria-label 含券名、payAmount Math.max(0,...) 负值边界）。
- **第 2 轮 APPROVED**：修复正确无副作用；empty 测试断言改为 `findByText + closest('[role="status"]')` 更严格（避免骨架 status 误命中）；未发现新增问题。
- P2 未修复记录项（购买面板顺序/封面三色渐变/选中态颜色/375px Tabs 溢出/hot 席位条颜色/对比度 3.3:1）为视觉细节偏差，非阻断。

---

## 五、交付物与交接

- 交付物：`course-detail.html`（已签收）+ React 实现（9 组件/页面）+ 测试（16 项）+ 测试/审查报告 + 截图 14 张
- 看板：task46=DONE（待编排者验收指令后进入下一任务）
- 已运行 `powershell -File D:\.ai-hub\sync.ps1` 同步 AI-Hub
