# task47 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task47 /my-courses 我的班次（TraeWork，commit 2ff44b1 + 03bffb4）
> 结论：**✅ 验收通过**（GWT 实证全绿），2 条批判（P2 不阻塞）

---

## 实证结果

| 项 | 实测 |
|----|------|
| commit | ✅ `2ff44b1`（功能）+ `03bffb4`（fe-tester 复核整改）|
| 交付物 | ✅ enrollments.ts + cohort-card.tsx + MyCoursesClient.tsx + page.tsx；删除旧 MyCourseCard/CourseTabsEmpty |
| tsc | ✅ 0 错误 |
| vitest | ✅ **50 文件/371 测试全 PASS 实跑**（21.44s，含 CohortCard 5 项）|
| eslint | ✅ **0 错误 0 警告**（改动文件）|
| next build | ✅ 成功（/my-courses 为 ƒ Dynamic）|
| grep 审计 | ✅ 硬编码色/禁用色/任意字号/fallback 全 0 |
| MOCK | ✅ 仅注释（"后台返回即渲染，无 MOCK"）|

## 批判 1（P2）：enrollments 后端（task20/21）未完成，前端类型全可选容错待联调

**问题描述**：enrollments.ts 的 `getEnrolledCohorts` 类型"全可选容错"——因后端 task20/21（契约⑪）未完成，前端以宽松类型 + 真实接口调用 + 空态兜底处理。当前真机点击会空态（后端 404/无数据），需 task20/21 落地后联调验证真实 enrollments 数据驱动三 tab。

**证据来源**：enrollments.ts（类型全可选）；后端 task20/21 未落地（看板）。

**优化方案**：不阻塞本次验收（前端已按规范实现，同 task46 处理）。task20/21 完成后：联调 GET /api/enrollments/me/cohorts?status= → 跑契约测试 + Playwright 全链路；收紧类型（去可选容错）。

## 批判 2（P2）：fe-tester 复核整改的登录守卫 hydrate 安全修复未在报告详述

**问题描述**：03bffb4（fe-tester 复核整改）含"登录守卫 hydrate 安全修复"——报告未详述该修复内容（hydration 不一致问题）。需确认修复是否彻底（SSR/CSR 登录态不一致导致的水合错误）。

**证据来源**：commit 03bffb4 message；报告提及但未详述。

**优化方案**：已由 fe-tester 复核 APPROVED（无 P0）。后续可补看护（登录守卫用 useEffect 水合后判断，避免 SSR 渲染登录态）。不阻塞。

## 总评

| GWT | 结果 |
|-----|------|
| ① HTML APPROVED + enrollments 数据驱动三 tab + 真实进度聚合 | ✅ 实现（Tabs 由 enroll_status 驱动 + 分组计数真实）|
| ② 继续学习跳最近未完成 + 空态去选课 CTA | ✅ 实现（J14 跳转 + 空态 CTA）|
| ③ enroll_status 徽章映射 | ✅ 实现（active→success/completed→muted/refunded→destructive）|

**结论：task47 验收通过。** 批判 1/2 均 P2 不阻塞（enrollments 后端待联调 / 登录守卫修复已复核）。task48 可继续。
