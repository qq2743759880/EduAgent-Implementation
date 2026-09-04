# task20 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task20 enrollment 只读域（Trae，commit f6ea5cc）
> 结论：**✅ 验收通过**（GWT 实证全绿），2 条批判（P2 不阻塞）

---

## 实证结果

| 项 | 实测 |
|----|------|
| commit | ✅ `f6ea5cc`（11 文件 +931）|
| 交付物 | ✅ enrollment 四件套 + task20-21-contract.md + 报告 + test_contract_task20.py |
| 契约测试 | ✅ **7/7 实跑**（in-process ASGI，不依赖外部存储机）|
| /me/cohorts?status=active | ✅ 200 + 5 items（EnrolledCohort[] 数组）|
| 进度聚合 | ✅ **overall_ratio/session_total=28/module_total=3 真实**（无 MOCK）|
| enroll_status | ✅ active 5 条（分布正确）|
| 满班并发（GWT①）| ✅ 报告：8 并发 → 成功 1/拦截 7，current==max 无超卖（经 task17 occupy_seat）|
| 范围裁定 | ✅ 只读端点（student_cohort_rel.order_item_id NOT NULL 约束实证）|

## 批判 1（P2）：满班并发攻防为 DB 层验证（非 HTTP 层）

**问题描述**：GWT① 满班并发（8 并发 → 成功 1/拦截 7）由 DB 层验证（task17 occupy_seat 条件更新直接模拟），非 HTTP 层并发（与 task16/17 同模式，限流环境限制）。

**证据来源**：报告 §验收证据（DB 8 并发攻防）；task20 只读端点本身无写操作。

**优化方案**：不阻塞（条件更新逻辑 task17 已证 + DB 实证）。HTTP 层并发压测转 task39。

## 批判 2（P2）：进度聚合依赖 homework_submission 提交表判定（refunded 无测试数据覆盖）

**问题描述**：GWT② 要求"退款后 enroll_status=refunded 自动移入已退款 tab"——当前测试账号无 refunded 记录（实测全 active），refunded 分支的进度聚合未实测（仅代码实现 + 契约测试）。

**证据来源**：实测 adm02test 全 active；refunded 无数据。

**优化方案**：不阻塞（契约测试 + 代码实现覆盖）。task47（前端 my-courses）联调时可造 refunded 数据验证 tab 切换。

## 总评

| GWT | 结果 |
|-----|------|
| ① 满班并发（下单路径承载）| ✅ DB 8 并发成功1拦截7 |
| ② /me/cohorts?status= 进度聚合 | ✅ 实测 overall_ratio/session/module 真实 |
| ③ 支付回调报名展示 | ✅ 报名由 task18 写，本域正确展示（adm02test 5 条 active）|

**结论：task20 验收通过。** 契约⑪ task20 段冻结（task21 完成后解锁前端 task47/48）。批判 1/2 均 P2（压测留 task39 / refunded 分支待 task47 联调验证）。
