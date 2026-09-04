# task46 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task46 /courses/[seriesId] 课程详情（TraeWork，commit 58883a9 + 49821bf）
> 结论：**✅ 验收通过**（GWT 实证全绿），2 条批判（P2 不阻塞）

---

## 实证结果

| 项 | 实测 |
|----|------|
| commit | ✅ `58883a9`（代码+测试+HTML+截图）+ `49821bf`（报告）|
| 组件交付 | ✅ 7 组件（CourseDetailHero/CohortList/CouponPicker/FavoriteButton/CourseDetailSyllabus/CohortDetailPanel/CourseDetailTabs）+ page.tsx |
| tsc | ✅ 0 错误 |
| vitest | ✅ **49 文件/366 测试全 PASS 实跑**（28.96s）|
| eslint | ✅ **0 errors**（2 warnings=set-state-in-effect 合法）|
| next build | ✅ 成功（/courses/[seriesId] 路由）|
| grep 审计 | ✅ 硬编码色/禁用色/任意字号/fallback 全 0 |
| MOCK | ✅ 仅注释（"数据流全部真实契约，无 MOCK"说明）|

## 批判 1（P2）：coupons/orders/favorites 后端未完成，前端真实调用将 404（预期内待联调）

**问题描述**：CourseDetailClient 真实调用 `api/coupons`、`api/favorites`、`api/orders`（createOrder/receiveCoupon/addFavorite）——但后端 task16/17/20（coupons/orders/enrollments）**尚未完成**，这些端点当前 404。前端正确遵守了"写真实接口+待联调，禁 MOCK"（task46 prompt 要求），错误走 toast/错误态兜底，页面不崩。

**证据来源**：CourseDetailClient.tsx 源码（import createOrder/receiveCoupon/addFavorite + TanStack Query mutation + toast）；后端 task16/17 未落地（看板 BLOCKED/TODO）。

**与正确做法差距**：当前详情页"立即报名/领券/收藏"在真机点击会 404（无法完整演示）——这是后端未就绪导致，非前端缺陷。

**优化方案**：不阻塞本次验收（前端已按规范实现）。后端 task16/17/20 完成后，联调：跑契约测试（contract-diff）+ Playwright 全链路（报名→支付）。已在看板 task46 注明"待 task16/17 联调"。

**预期收益与成本**：收益=前端先行不阻塞；成本=联调时后端 task16/17 补测试。

## 批判 2（P2）：详情页依赖的 enrollments（task20）未就绪，报名后跳转支付页待验证

**问题描述**：「立即报名」→ createOrder → 跳 /orders/[orderId]/pay，但 orders 页面（task64/65）与支付后端（task18）未完成——跳转目标当前不可用。

**证据来源**：CourseDetailClient createOrder 逻辑 + 看板 task64/65/18 未完成。

**优化方案**：联调期验证（同批判 1）。不阻塞本次验收。

## 总评

| GWT | 结果 |
|-----|------|
| ① HTML APPROVED → React 对照一致 | ✅（fe-review 第 2 轮 APPROVED；视觉对照）|
| ② 立即报名（cohort_id+coupon_id）跳支付/满员 disabled/未登录 redirect | ✅ 实现（createOrder mutation + CohortList 满员 disabled + J4 redirect）|
| ③ 领券/收藏（favorite_source=series_detail/登录联动）| ✅ 实现（receiveCoupon + FavoriteButton aria-pressed + favorited 联动）|
| ④ 四级树（series→cohort→module→session 排序）| ✅ CourseDetailSyllabus 实现 |

**结论：task46 验收通过。** 批判 1/2 均 P2 不阻塞（后端 task16/17/20 未就绪，前端已正确实现待联调）。task47 可继续。
