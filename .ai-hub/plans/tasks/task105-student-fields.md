# task105 — 学生端字段对齐（no-op 修复 + schema 重对）

- 域：FE ｜ 平台：trae ｜ 波次：W1 ｜ 依赖：task101；C-A 冻结后复核 DashboardOut（D4）
- 文件：`achievements.html`、`dashboard.html`、`my-cohorts.html`、`me.html`（stat 卡部分）

## 目标
修复四个"注入 no-op/字段猜错"页，让学生端成就、看板、班次、个人统计显示真实数据。

## 证据
- achievements.html:754：注入选择器 `.badge-wall/.badges/.points-num` 与实际 DOM（`.badge-grid/.badge-card`）不匹配 → 全 no-op；头注释声明的 rankings/积分流水完全未接。
- dashboard.html:641 期望 `total_questions_attempted/active_courses_count`，后端 `DashboardOut` 无此二字段（X2）；`recent_days[]` 趋势数据前端未消费。
- my-cohorts.html:564：`.cohort-list/.cohort` vs 实际 `.cohort-card` → no-op；字段期望 `series_title|cohort_name, enroll_status` 需按 enrollment 实际 schema 核对。
- me.html:4371-4377：`completed_sessions_count` 后端不返回（X3），实际字段 `{total_watched_seconds, active_cohorts_count, homework_submitted, exam_submitted, exam_avg_score}`。

## 改动点
1. achievements：选择器对齐真实 DOM；接 `GET /api/gamification/me/badges`（BadgeListResp）渲染徽章墙与解锁数；接 `me/points`（PointsResp 含 recent_logs）渲染积分流水；接 `GET /api/gamification/rankings?scope=WEEKLY&dimension=POINTS&top_n=10` 渲染排行榜。
2. dashboard：KPI 卡改为 DashboardOut 真实字段（总学习时长/连续天数 + recent_days 渲染趋势图）；`total_questions_attempted/active_courses_count` 两卡按 D4 决策：默认方案=后端扩字段（C-A），冻结前先隐藏这两卡或显示"—"，**禁止显示 undefined**。
3. my-cohorts：选择器改 `.cohort-card`；三 Tab（在学/已结课/全部）按 `enroll_status` 过滤；空态"去选课"按钮接 courses.html。
4. me：stat 卡字段换 learning-summary 真实字段名；资料编辑归 task121。

## GWT 验收
- Given student token（DB 有徽章/积分/班次种子），When 打开 achievements.html，Then 徽章墙/积分/排行榜渲染真实数值且与 `curl` 三端点返回一致（抽查 2 项数值）。
- When 打开 dashboard.html，Then 4 张 KPI 卡无 undefined/NaN，趋势图来自 recent_days；When 打开 my-cohorts.html，Then 卡片渲染真实班次且 Tab 过滤正确。
- 机验：`grep -n "completed_sessions_count\|total_questions_attempted" *.html` 仅在 C-A 冻结后允许出现（冻结前 = 0）；每页 Network 面板无 4xx/5xx 未处理。

## 风险
- gamification 排行榜 scope 参数枚举需实测（DAILY/WEEKLY/MONTHLY/ALL_TIME），写死前 curl 验证。
