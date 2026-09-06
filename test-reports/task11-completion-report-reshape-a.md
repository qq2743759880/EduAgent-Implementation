# task11 完工报告（reshape-a 批次）：dashboard.html 学生仪表盘·清零演示兜底全量真实接线

日期：2026-09-06 ｜ 执行：fe-html 接线 agent ｜ 计划：`.ai-hub/plans/dev-plan-reshape-a.md` A 批次 task11
GWT：Given 学生登录态；When 打开 /dashboard.html；Then 统计/最近学习/推荐真实，无数据区块诚实空态（不造 MOCK 假数据撑场面），保留现有视觉。
commit：见 git log `fix(reshape)/task11`（与 task09 同批独立提交）

## ① 改动清单（edu-frontend/public/dashboard.html）

**清零的 MOCK/演示痕迹（全量）**：
1. 整个"效果图演示数据兜底渲染"脚本（约 75 行）：RANK 三周期假排行（Sunny/Leo/Mia/Tom/Ada 1280/6800/15200 分）、假 7 日折线数据 `[15,38,25,46,30,52,42]`、假饼图 conic-gradient（58%/24%/11%/7%）→ 删除；
2. 静态假 KPI：42 分钟/15 道/3 门/6 天 + 假 delta（▲较昨日+8 分钟/正确率 82%/近 7 天活跃 6 天）+ 假比例条（68%/55%/40%/86%）→ 全部清空由真实数据驱动；
3. 9 行假学科掌握度条形（编程 82%…企业培训 38%）→ 契约缺口诚实空态；
4. 假学习结构饼图图例（视频学习 58% 等无字段来源占比）→ 改"学习构成（累计）"：learning-summary 真实字段列表，donut 元素隐藏（无占比字段不造假饼图）；
5. 6 枚假徽章（连续打卡/满分达人/作业达人/阅读之星/每周学霸/成长新秀 + 假"3 / 12"）→ 真实 badges 端点渲染；
6. 假我的排名（#12 · 超越 88% 学习者）+ 假积分卡（学习小达人 Lv.6/1280 分/距 Lv.7 还需 320 分）+ 3 条假流水（每日打卡+20 等）→ 真实 rankings/points 端点渲染；
7. 硬编码昵称"你好，小柚子 👋" → GET /api/users/me nickname 真实渲染；
8. 从未接线的 v-empty 三段死标记（演示态残留）→ 删除，空态下沉为面板级诚实空态（更细粒度）；v-loading（初始显示）/v-error（主数据双失败+重试）首次真正由脚本驱动。

**接线明细**：KPI1 累计学习时长（total_study_seconds，标签从"今日"改"累计"以诚实对齐字段口径）+ delta 近 7 天分钟 + 比例条=今日/近7天峰值；KPI2 累计练习题（total_questions_attempted）+ 正确率（overall_correct_rate）+ 条=正确率；KPI3 在学课程（**active_courses_count**——原 task105 注释称"后端暂无字段"已过时，实测存在，教训⑧）+ delta=learning-summary 在学班次；KPI4 连续打卡（latest_streak_days）+ delta=近 7 天活跃天数（recent_days 派生）+ 条=活跃占比；7 日折线（recent_days 真实日期标签，全 0 诚实空态）；徽章条（仅 unlocked 按 unlocked_at 最近取 6，pill=真实 X/Y）；周榜 Top5（奖牌/首字母头像/Lv/分值/is_myself 高亮）+ 我的排名（#N 或"未上榜"）；积分卡（等级/总分/进度条/距下一级还需分/近 3 条流水正负着色）。状态机：loading 骨架 → success；五源任一失败面板级诚实降级；主数据（progress+summary）双失败 → v-error+重试（location.reload）；未登录 → 登录引导（隐藏全部区块、零 API 调用）。所有后端文本 esc() 转义；无 alert(、无 .match(。

## ② curl 实测证据（2026-09-06，真实 HTTP）

| 端点 | 实测关键字段（user000001） | 结论 |
|---|---|---|
| GET /api/progress/dashboard?days=14 | `{total_days:1,total_study_seconds:6633,total_questions_attempted:14,total_questions_correct:6,overall_correct_rate:0.4286,active_courses_count:2,latest_streak_days:0,recent_days:[{stat_date:"2026-09-06",study_seconds:0,video_ticks,homework_submitted,exam_submitted,questions_attempted...}]×14(新→旧)}` | 4 张 KPI 卡+折线全部有真实字段 ✓；recent_days 新→旧已按序消费 ✓ |
| GET /api/users/me/learning-summary | `{total_watched_seconds:"6633"(字符串),active_cohorts_count:2,homework_submitted:0,exam_submitted:0,exam_avg_score:0.0}` | 学习构成面板+KPI3 delta 真实消费 ✓（注意字符串类型已 Number() 归一） |
| GET /api/users/me | `nickname:"小柚子同学",role:"student"` | 昵称真实渲染 ✓ |
| GET /api/gamification/me/badges · me/points · rankings | 同 task09 报告（3/8 徽章、Lv.1 萌新 321 分、周榜 my_rank#2） | 徽章/积分/排行面板真实 ✓ |
| GET /api/progress/courses | 200 但**不在 reshape-a.json 冻结清单** | 按契约纪律不消费 → 掌握度面板诚实空态 ✓ |

**独立实证（node DOM 桩 + 真实 3000 页面脚本 + 真实 8000 数据，无 Playwright）**：`verify_task11.mjs` **27 项断言全 PASS**（期望值全部动态取自 API：昵称/四卡数值/正确率 43%/在学班次 2/活跃 1 天/折线 d 属性非空且标签为真实日期/学习构成 111 分钟/假饼图隐藏/徽章条最近解锁"首次通关"/pill 3 / 8/排行 top1/我的排名#2/积分 321/loading 隐藏 success 显示/无 alert-match）；`verify_task11_notoken.mjs` 5 项全 PASS（loginGate 显示、v-loading/v-success 隐藏、redirect 站内、**零 API 调用**——防 DEBUG 虚拟管理员数据误读，教训⑥）。页内 2 个内联 script `node --check` 全部 SYNTAX_OK；3000/8000 未重启。

## ③ 资产消费证据

- AGENTS.md 教训逐条对账：②禁 Playwright ✓（node 桩+curl）；⑥DEBUG 虚拟管理员防线 ✓（未登录零请求+登录引导）；⑧真实契约优先于页面注释 ✓（两处过时注释已纠正：active_courses_count 已存在、"答题数无字段"注释删除）；⑨禁正则 match 取参 ✓；静态页注入模式保留 ✓。
- 读完 `.ai-hub/plans/dev-plan-reshape-a.md` task11 GWT；`contracts/reshape-a.json`（progress/dashboard、users/me/learning-summary 在 verified_read_21，hash 30aeddbe 未动）；`edu-frontend/public/edu-api.js` 头部注释（EAPI.get/store/buildLoginUrl 复用，未改）。
- 视觉冻结遵守：糖果/indigo tokens、KPI 卡布局、§1.7 图表色、面板结构全部保留；仅数据与诚实状态替换（task03 先例：冻结视觉、清假数据）。

## ④ 批判承接核对

- C4（respbar 演示工具条移除）残留的"演示兜底脚本"本次彻底清零；
- GWT"推荐位"：契约五源均无推荐端点（reshape-a.json 无 recommendations 域）→ 不造假推荐，登录引导/空态文案引导去课程中心（"去课程中心开启学习吧"），登记为契约缺口待 B 批次决策；
- "学科掌握度"页头原注"契约缺口（禁 MOCK）…React 消费真实端点"承接：本次以诚实空态落地，未用契约外 /api/progress/courses 撑场面。

## ⑤ 自检三视角

- **交互态**：首屏 loading 骨架 → 数据到达后整页切换 success；错误可一键重试；个人中心/调整偏好按钮保留原跳转。
- **边界**：新用户全 0（0 分钟/0 题/0 连打卡）→ 显示真实 0 而非"—"或假数；折线全 0 → 诚实空态；无徽章/无排行/无流水各有独立空态文案；learning-summary 字符串秒数已归一；my_rank=null → "未上榜"；未登录零请求零假数据。
- **错误反馈**：五源 allSettled 面板级降级（单源失败不拖垮整页）；主数据双失败才整页 v-error；EAPI 统一 `[EAPI]` console.error；所有插值 esc() 防注入；无 undefined/NaN 上屏（!= null 守卫）。

## 遗留登记（不改视觉，按守则只登记）

- 推荐位：无契约端点，诚实引导空态顶替；若产品要求真实推荐需先立契约（B 批次）。
- 学科掌握度/学习结构占比：契约缺口，React 批次接 C-A 后按真实端点回填；CSS（.mastery/.donut）保留供复用。
- myrank"超越 N% 学习者"无契约字段，已改为"我的积分 X 分 · 快照日期"诚实文案。
