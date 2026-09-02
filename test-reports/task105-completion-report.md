# task105 — 学生端字段对齐（no-op 修复）完工报告

- 分支：feature/opt-waves（本任务**未 commit**，不改分支）
- 域：FE ｜ 波次：W1 ｜ 平台：trae
- 只改 4 个文件：`edu-frontend/public/achievements.html`、`dashboard.html`、`my-cohorts.html`、`me.html`（edu-api.js 未改）

## 一、改动清单

### 1. achievements.html（徽章墙 / 积分流水 / 排行榜）
- 删除原 no-op 注入（选择器 `.badge-wall/.badges` 与实际 `.badge-grid` 不匹配）。
- 选择器对齐真实 DOM：`.badge-grid/.badge-card`、`.badge-count/.badge-next`、`.total-pts/.lv-pill/.lv-range/.lv-prog`、`.log-list/.log-head`、`.rank-body/.mr-val`。
- 接三端点（并发）：徽章墙按 `items` 重建 `.badge-card`（已解锁/未解锁+进度），`badge-count` = `unlocked_count`/`total`，`badge-next` = `next_milestone`；积分用 `level_no/level_title/total_points/level_progress_pct/recent_logs` 渲染总览+等级条+流水；排行 `WEEKLY/POINTS/top_n=10` 渲染 `.rank-body` + `my_rank`。Tabs（时间/维度）绑定重新查询。

### 2. dashboard.html（KPI + 趋势图）
- KPI 对齐 DashboardOut 真实字段：`kpi-time` = `total_study_seconds`→分钟；`kpi-streak` = `latest_streak_days`。
- 答题数(`kpi-q`) 与在学课程(`kpi-course`) 两卡：后端无对应字段（契约 C-A 后才有），按 spec 显示 `—`（**不访问缺失字段，杜绝 undefined/NaN**；同时满足 grep=0）。
- 新增 `drawTrend()`：消费 `recent_days[]`（`stat_date` 标签 + `study_seconds`→分钟），重绘 `#trend-line/#trend-area/#trend-dots/#trend-labels/#trend-y-axis`（原前端未消费 recent_days，此为其修复点）。

### 3. my-cohorts.html（班次 Tab + 空/错态真实化）
- 选择器 `.cohort-list/.cohort` → 对齐实际 `.cohort-card`，改在真实三 Tab 面板（`tab-active/completed/refunded`）内重建卡片。
- 接 `GET /api/enrollments/me/cohorts?page=1&page_size=10`（注意：该端点返回**裸数组** `data:[]`，修正原注入误读 `d.items`）。
- 按 `enroll_status` 过滤三 Tab（active→学习中/completed→已完成/其余→已退款），更新 `.cnt` 计数徽章。
- 空态「去选课」→ `courses.html`；错误态「重试」→ `location.reload()`；新增 `showPanel()` 做 success/loading/error/empty 面板切换。
- 说明：spec 写"在学/已结课/全部"，但页面既有真实三 Tab 是 active/completed/**refunded**（硬守则不动 DOM 结构/不重名），故按其实际 Tab 过滤，已在 §四 如实标注。

### 4. me.html（Stat 卡字段对齐）
- `st-sessions` 由后端不存在的 `completed_sessions_count` 改为 learning-summary 真实字段 `active_cohorts_count`；对应卡片标签/单位由「完成课次/课次」改为「在学班次/班次」。
- `st-time` = `total_watched_seconds`（字符串，`Number()` 转换）→ 小时；`st-points/st-level` 走 gamification `/me/points`。
- 资料编辑归 task121（未动）。

## 二、四页涉及端点 curl 真实字段（后端 8000，student user000001 / Test@123456）

### achievements
```
GET /api/gamification/me/badges
{"code":0,"data":{"total":8,"unlocked_count":2,"next_milestone":"下一目标：📚 勤学苦练（进度 150/600，25%）",
 "items":[{"badge_code":"BDG-STUDY-1H","badge_name":"初出茅庐","badge_desc":"累计学习时长 ≥ 1 小时","category":"LEARNING","icon_emoji":"🌱","rarity":"COMMON","trigger_rule":"STUDY_MIN_TOTAL","rule_value":60,"reward_points":50,"unlocked":true,"progress_current":150,"progress_required":60,"progress_pct":100.0}, ...8 条...]}}

GET /api/gamification/me/points
{"code":0,"data":{"user_id":1,"total_points":163,"level_no":1,"level_title":"萌新","level_min":0,"next_level_min":500,"level_progress_pct":32.6,"logs_total":7,
 "recent_logs":[{"log_id":113,"point_type":"LIKE_GAIN","delta":2,"balance_after":163,"note":"社区 POST #48 获赞 uid=100003","created_at":"2026-08-21T08:38:35"}, ...7 条...]}}

GET /api/gamification/rankings?scope=WEEKLY&dimension=POINTS&top_n=10
{"code":0,"data":{"scope":"WEEKLY","dimension":"POINTS","snapshot_date":"2026-09-02","top":[],
 "my_rank":{"rank_no":1,"user_id":1,"user_name":"用户1","metric_value":0,"level_no":1,"is_myself":true,"badge_count":2},"source":"LIVE_CALC"}}
```
（scope 枚举实测可用：`DAILY|WEEKLY|MONTHLY|ALL_TIME`，见 gamification/router.py:45；本账户为周榜榜首所以 `top=[]`、`my_rank` 出现。）

### dashboard
```
GET /api/progress/dashboard?days=14
{"code":0,"data":{"total_days":0,"total_study_seconds":0,"total_questions_attempted":0,"total_questions_correct":0,"overall_correct_rate":null,"latest_streak_days":0,
 "recent_days":[{"stat_date":"2026-09-02","study_seconds":0,"video_ticks":0,"homework_submitted":0,"homework_correct_rate":null,"exam_submitted":0,"exam_avg_score":null,"questions_attempted":0,"questions_correct":0}, ...共14天...]}}

### my-cohorts
GET /api/enrollments/me/cohorts?page=1&page_size=10
{"code":0,"message":"ok","data":[]}   ← 裸数组；本学生无报名
（EnrolledCohort 字段：enrollment_id/cohort_id/cohort_name/series_id/series_name/series_code/subject_code/level_code/cover_url/delivery_mode/enroll_status/overall_ratio/module_done/module_total/session_done/session_total/next_session/finished_at/refund；enroll_status ∈ active/completed/cancelled/refunded，见 enrollment/schemas.py:16,37-59）

### me
GET /api/users/me/learning-summary
{"code":0,"data":{"total_watched_seconds":"0","active_cohorts_count":0,"homework_submitted":0,"exam_submitted":0,"exam_avg_score":0.0}}
GET /api/gamification/me/points   → 同上（total_points=163, level_no=1）
```

## 三、GWT 逐条自评

| GWT | 判定 | 说明 |
|---|---|---|
| 打开 achievements → 徽章墙/积分/排行榜渲染真实数值且与 curl 三端点一致（抽查 2 项） | **达成** | 抽查：徽章墙解锁数 = `unlocked_count=2`/`total=8`（`.badge-count` 写入）；积分 = `total_points=163`（`.total-pts` 写入）；排行 `my_rank.rank_no=1`（`.mr-val` 写入"第 1 名"）。均与 curl 一致。_注：浏览器端渲染未跑（禁 Playwright），以代码+curl 实证。_ |
| 打开 dashboard → 4 张 KPI 卡无 undefined/NaN，趋势图来自 recent_days | **达成** | `kpi-time=0 分钟`、`kpi-streak=0 天` 为真实值；`kpi-q/kpi-course` 显示 `—`（不读缺失字段）；趋势图由 `recent_days` 重绘。无 undefined/NaN 文案。 |
| 打开 my-cohorts → 卡片渲染真实班次且 Tab 过滤正确 | **部分** | 注入已按真实 `.cohort-card` + 三 Tab（active/completed/refunded）实现过滤与计数；但本学生 DB 无报名（curl `data:[]`），真实现落到空态 `panel-empty`（去选课→courses.html），**卡片渲染与多 Tab 分发无种子数据无法浏览器实证**，如实标注"部分"。另：页面既有第三 Tab 为"已退款"，非 spec 所写"全部"，按实际 DOM 对齐。 |
| 机验：`grep completed_sessions_count\|total_questions_attempted` = 0 | **达成** | 四页均 0 命中（见下）。 |
| 机验：每页 Network 无 4xx/5xx | **部分** | 无法在本环境浏览器抓包（禁 Playwright）；后端四端点在 curl 均 200 `code:0`，注入用 `.catch` 兜底不抛未捕获错误。 |

## 四、最低机验输出
```
grep "completed_sessions_count|total_questions_attempted" {4 页} → 0 / 0 / 0 / 0
选择器↔DOM 一致性（注入选择器在该文件至少 CSS/DOM+注入各命中≥1）：
  achievements: .badge-grid(6) .badge-card(28) .total-pts(5) .log-list(4) .rank-body(5)
  dashboard:    #kpi-time #kpi-q #kpi-course #kpi-streak #trend-line #trend-dots #trend-labels（均命中）
  my-cohorts:   .cohort-card(11) #tab-active/completed/refunded #panel-empty/error/success
  me:           #st-time #st-sessions #st-points #st-level
JS 语法编译检查（node new Function 全 script）：achievements=4 / dashboard=3 / my-cohorts=4 / me=4，errors=0
```

## 五、边界与说明
- 所有注入保持"无 token 保留演示数据"模式（`if(!EAPI||!EAPI.store.getToken()) return`），未重定义全局 `$`/`renderSides`。
- me.html`total_watched_seconds` 为字符串 `"0"`，用 `Number()` 转换避免 `"0"` 拼接问题；其余字段均带 `|| 0`/`!= null ? : fallback` 兜底，杜绝 undefined/NaN。
- dashboard 答题数/在学课程两卡按 C-A 冻结决策显示 `—`；待契约 C-A 扩 `DashboardOut` 后召回真实值。
- my-cohorts 端点返回裸数组（非分页壳），前端 `Array.isArray(d)` 优先兼容。