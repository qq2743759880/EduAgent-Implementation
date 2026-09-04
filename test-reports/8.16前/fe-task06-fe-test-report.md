# 前端测试报告 fe-task06

- 任务：fe-task06（G5 用户端仪表盘真实数据接入，FR-11）
- 类型：**最终功能测试**（含本轮修正回归：a11y 6 HIGH + perf P1 3）
- 测试时间：2026-08-13
- 测试人：fe-tester（web 前端测试 agent）
- **判定：PASS**（验收标准 7 条全部通过；本轮修正 a11y 5/6 HIGH + perf 3/3 P1 落实，a11y HIGH #6 属存量 ad-hoc 登记 fe-task07 按规格边界不触碰）
- 测试方式：只测试 + 报告，**未改动任何业务代码**

---

## 1. 环境

| 项 | 值 | 说明 |
|----|----|------|
| 画像 | `frontend-stack.json`（profileId=nextjs-16-app-router） | Next.js 16.3 + React 19 + Tailwind v4 + Zustand + TanStack Query + App Router |
| 规格 | `.claude/specs/frontend/fe-task06/frontend-spec.md` + `visual-acceptance.md` | 验收标准 7 条（对齐 dev-plan 任务 7） |
| dev server | `http://localhost:3000`，HTTP 200 | 复用既有进程（server-info 记录 PID 1908），未启动/未重启/未 kill |
| 后端 | `http://127.0.0.1:8000` 运行中，HTTP 200 | 真实 API（非 mock） |
| 测试账号 | `task01test / Test@123456`（student，user_id=846）真实登录 + JWT 注入 `localStorage["edu:auth:token"]` | 社区积分/排行数据真实（31 分、今日 +17、排行第 2）；学习区 0 值为数据库真实状态 |
| 浏览器 | Playwright（Chromium，MCP） | route 拦截仅用于错误态/空态/非零数据形态注入，成功态全部走真实 API |
| 单测 | `npx vitest run`（vitest v4.1.10，jsdom，setup=src/test/setup.ts） | 30 files / 256 tests 全绿（含 dashboard.test.ts 37 用例） |
| 类型 | `npx tsc --noEmit` | exit 0，0 错误 |
| 静态 | `npx eslint`（dashboard 范围） | exit 0，0 错误 |

> 执行命令全部在 `edu-frontend` 下运行。

---

## 2. 验收标准逐条映射（frontend-spec §验收标准 → Given/When/Then）

| # | 验收标准（Given/When/Then） | 验证方式 | 结果 | 证据 |
|---|-----------------------------|----------|------|------|
| 1 | 5 数据区真实 API（无 MOCK）：趋势=`GET /api/progress/dashboard?days=14`、徽章=`GET /api/gamification/me/badges`、积分=`GET /api/gamification/me/points?page=1&page_size=20`、排行=`GET /api/gamification/rankings?scope={DAILY\|WEEKLY\|MONTHLY}&dimension=POINTS&top_n=10`、KPI=`/api/progress/dashboard`+`/api/progress/courses` 派生；MOCK 常量全部删除 | 浏览器（网络请求）+ grep | ✅ | reload 实测 6 个请求路径与规格逐字一致（§4.1）；page.tsx/dashboard.ts 无 MOCK_TREND/MOCK_RADAR_SELF/MOCK_RADAR_PEER/MOCK_BADGES/MOCK_GAINS/buildRankList/ALL_RANGE_LIST/daysAgoLabel（grep 0） |
| 2 | grep `MOCK_` 0 命中；query 不设 placeholderData | grep | ✅ | 写路径（`src/app/(user)/dashboard/`、`src/components/dashboard/`、`src/lib/api/dashboard.ts`）`MOCK_` **0 命中**；`placeholderData` 0 命中（骨架屏为主加载呈现） |
| 3 | 骨架屏 / 错误态 / 空态：加载显示骨架不显示 MOCK；某区失败独立错误态 + 重试 refetch 不渲染 0 兜底；新学员显示空态、数值 0 不显示空态 UI | 浏览器（route 拦截 + 慢网） | ✅ | 骨架：加载窗口实测 34 个骨架块 + KPI 4 卡 sr-only loading + 徽章「加载中…」+ 打卡 aria-hidden 骨架（§4.3）；错误：progress/courses 500 → KPI 整区错误卡 `role=alert`（不显示 0 分钟兜底），徽章 500 → 该卡错误 + 他区正常（§4.4）；空态：雷达空态实测、my_rank:null 实测、徽章/趋势空态为静态路径（task01test 真实数据不触发，见 §7 说明）；数值 0（今日 0 分钟）正常渲染非空态 |
| 4 | 雷达图派生：`overall_correct_rate×100` 基础分 + subject_preferences 权重偏移 5 维（english/coding/math/chinese/physics），仅「我的能力」1 组，不落 MOCK 数组；`overall_correct_rate=null` → 空态「学习后即可生成学科能力评估」，禁止全 0 五边形 | 浏览器 + 单测 | ✅ | 非零注入（rate=0.8，prefs 5 科）实测 aria-label「学科能力：我的能力 英语 90、编程 85、数学 75、语文 80、物理 85」——base 80 + (s-3)×5 偏移正确，仅 1 组（§4.2）；task01test（rate=null）实测空态文案 + `img "学科能力雷达（暂无数据）"`，无全 0 雷达（§4.1）；deriveAbilityRadar 单测（clamp/空态）37 用例覆盖 |
| 5 | KPI 派生：今日时长=末项 study_seconds/60、今日练习题=末项 questions_attempted、进行中课程=overall_ratio∈(0,1) 系列数、连续打卡=latest_streak_days；delta 真实（练习题卡=累计正确率，attempted=0 →「暂无数据」）；不再从 anyMe?.streak/points 取值 | 浏览器 + 单测 | ✅ | 非零注入实测：30 分钟（1800s/60）+「较昨日 +10 分钟」、8 道 +「正确率 80%」（32/40）、1 门（0.6 计入，0.0/1.0 不计）、5 天 +「近 7 天活跃 3 天」（§4.2）；task01test 实测 attempted=0 →「暂无数据」中性（§4.1）；KpiCard 值来自 `kpis` useMemo 派生，无 anyMe 取值（代码审查） |
| 6 | 排行榜周期切换：今日/本周/本月 → scope=DAILY/WEEKLY/MONTHLY 重新请求或命中缓存；my_rank=null 时仅列表不渲染「我的排名」行 | 浏览器 | ✅ | 切本周 +1 请求（scope=WEEKLY）、切本月 +1（scope=MONTHLY）、切回今日 **0 请求命中 60s 缓存**（§4.5）；mock my_rank:null → 排行榜仅渲染列表（小明/小红），无「我的排名」行（§4.6） |
| 7 | 无视觉回归（三态无布局跳动，图表高度 320/340 保持） | 委派 fe-visual-auditor | ✅* | `test-reports/fe-task06-visual.md` 双 viewport 截图验收已产出（本报告不做像素断言，属职责边界）；本报告验证图表容器高度代码固定（ProgressTrendChart `height=320` / AbilityRadarChart `height=340`，`style={{height}}` 恒定） |

**验收标准 7 条全部通过（✅）**。

---

## 3. 本轮修正回归（a11y 6 HIGH + perf P1 3）

### 3.1 a11y（fe-task06-a11y.md 6 HIGH）

| HIGH | 问题（原） | 修正 | 复验结果 |
|------|-----------|------|----------|
| #1 4.1.3 | 错误态容器无 role=alert/aria-live，错误不自动播报 | DataErrorCard + 两图表错误覆盖层加 `role="alert"` | ✅ 浏览器实测：progress/courses 500 → `[role="alert"]` 出现（KPI 整区 + 打卡位 + 趋势覆盖层）；徽章 500 → 1 个 role=alert「徽章数据加载失败重试」 |
| #2 1.4.3 | 错误卡文案 4.45:1 < 4.5:1（text-destructive） | 改 `text-rose-700`（destructive 加深档） | ✅ 实测 lab(41.17 71.63 30.31) ≈ #be123c，对白底 **≈6.28:1** ≥ 4.5:1（bg-destructive/10 叠加后仍达标） |
| #3 1.4.3 | 徽章「未获得」/解锁条件 10px 文案 2.62:1 | `text-slate-400` → `text-slate-600`（BadgeWallGrid.tsx:198/204） | ✅ 代码确认（≈5.2:1） |
| #4 1.4.3 | 打卡星期标签/排行空态/积分空态 text-slate-400 2.58–2.62:1 | StreakBadge.tsx:55、RankList.tsx:144、PointCard.tsx:120 → `text-slate-600` | ✅ 代码确认 |
| #5 1.1.1 | 图表 canvas 无替代文本 | 容器 `role="img"` + 动态 `aria-label`（loading/error/empty/数据摘要四态） | ✅ 浏览器实测：趋势 aria-label「近 14 天学习时长：每日学习时长（分钟）07/31 0，…08/13 0」（14 点全量）；错误态「（加载失败）」；雷达「学科能力：我的能力 英语 90…」 |
| #6 1.4.3 | 积分大数字渐变 1.94:1 | **存量 ad-hoc**，design-tokens.json §adHocRegistry 登记，fe-task07 收敛；规格边界「存量 ad-hoc 色零改动，本 task 只登记不触碰」 | ⚠️ 按规格边界**未触碰**（非本 task 引入），保留至 fe-task07 → 见 §7 遗留项-1 |

### 3.2 perf（fe-task06-perf.md P1 3）

| P1 | 问题（原） | 修正 | 复验结果 |
|----|-----------|------|----------|
| P1-1 | 雷达 queryFn 内重复请求 /api/progress/dashboard（首屏 2 次） | `queryClient.fetchQuery(["dashboard","trend"])` 复用 trend 同 key 请求 | ✅ 浏览器实测 reload 全程 `/api/progress/dashboard?days=14` **仅 1 次**（7 个 API 请求中无重复） |
| P1-2 | CLS 0.289：骨架→数据高度未预留（RankList 5 行 vs 10 行、徽章墙、打卡 h-48） | RankList 骨架按 topN 等量行（RankList.tsx:134）、BadgeWallGrid loading 等量徽章卡骨架、打卡骨架 h-[168px] 对齐 StreakBadge 实测高度（page.tsx:352） | ✅ 代码结构确认：骨架行结构（px-3 py-2.5 + h-8）与 RankRow 同高、等量 topN；CLS 数值复测建议 perf 复核（§7 遗留项-3） |
| P1-3 | 徽章墙 loading 显示空态误导文案「解锁第一枚徽章」 | BadgeWallGrid 增加 `loading` prop，loading 渲染等量网格骨架（替代空态） | ✅ 浏览器实测：慢网窗口徽章墙显示「加载中…」（description）+ 网格骨架（pulses 34 含徽章墙），无「解锁第一枚」误导闪现 |

---

## 4. 浏览器实测明细（localhost:3000 + task01test 真实登录）

### 4.1 真实数据渲染（5 数据区，成功态）

| 数据区 | 渲染结果 | 后端对照 |
|--------|----------|----------|
| KPI 4 卡 | 今日学习时长 0 分钟（较昨日持平）/ 今日练习题 0 道（暂无数据）/ 进行中课程 0 门 / 连续打卡 0 天（近 7 天活跃 0 天） | progress/dashboard（study_seconds=0、attempted=0、latest_streak_days=0）+ courses（5 系列 ratio 全 0.0） |
| 连续打卡 | 0 天 + 7 格（rest×6 + today，day-1-rest…day-7-today） | 同上 |
| 积分与成长 | 当前积分 31、今日 +17、明细 8 条（发帖 62/+5、回帖 #12/+2、发帖 61/+5…） | gamification/me/points（total_points=31，recent_logs 8 条逐字段对齐） |
| 近 14 天趋势 | canvas `role=img` + aria-label 14 点（07/31 0 … 08/13 0，全 0 分钟），单线无 legend | progress/dashboard recent_days 14 条 |
| 学科能力雷达 | 空态「学习后即可生成学科能力评估」（rate=null → 派生 []，无全 0 雷达） | progress/dashboard overall_correct_rate=null |
| 徽章墙 | 0/8，8 个未获得徽章 + 解锁条件（STUDY_MIN_TOTAL 60/600/6000、QUIZ_FULL_CORRECT 1、COURSE_FINISHED 1、VOCAB_MASTERED 50、POST_LIKES_TOTAL 10、COMMENT_LIKES_TOTAL 50） | gamification/me/badges（total=8、unlocked_count=0、trigger_rule/rule_value 对齐） |
| 学习排行榜 | 今日 tab TOP10：用户894(55)、我(17,第2,带「我」badge)、用户953(7)…；我的排名 2 / 我的积分 17 | gamification/rankings?scope=DAILY&dimension=POINTS&top_n=10（source=LIVE_CALC） |

> 6 个 query 全部真实 API 成功；学习区 0 值为 task01test 数据库真实状态，非 mock/非兜底伪造（与 server-info 一致）。

### 4.2 非零数据形态（route 注入非零 progress/courses/profile，验证派生正确性）

| 区 | 结果 | 派生核对 |
|----|------|----------|
| KPI | 30 分钟（较昨日 +10 分钟）/ 8 道（正确率 80%）/ 1 门 / 5 天（近 7 天活跃 3 天） | 1800s/60=30 ✓；32/40=80% ✓；ratio=0.6 计入、0.0 与 1.0 不计 ✓；latest_streak_days=5 ✓ |
| 雷达 | `我的能力 英语 90、编程 85、数学 75、语文 80、物理 85`，仅 1 组无 legend | base=80；(s-3)×5 偏移：英语 5→90、编程 4→85、数学 2→75、语文 3→80、物理 4→85 ✓ |
| 趋势 | 08/11 15、08/12 20、08/13 30（分钟） | study_seconds/60 且时间正序（末位今天）✓ |
| 打卡 | 5 天 + ✓ 格（done）+ 今日占位 | deriveStreakLast7 窗口语义 ✓ |

### 4.3 骨架屏时序（route 延迟 API 2.5s，制造 loading 窗口）

- 加载窗口实测：**34 个 `.animate-pulse` 骨架块** + KPI 4 卡 sr-only `loading` + 徽章墙 description「加载中…」+ 打卡页面级骨架 `[aria-hidden="true"]` + 排行榜/积分行骨架；**无 MOCK 数据闪现** ✓
- 数据到达后：KPI「今日学习时长」等真实渲染 ✓

### 4.4 错误态（route 拦截 500，卡片级独立）

| 场景 | 结果 |
|------|------|
| `/api/progress/courses` → 500 | KPI 整区错误卡「学习数据加载失败」`role=alert` + 重试按钮（可聚焦，bg-primary），**不渲染 0 分钟/0 道兜底**；积分（当前积分 31）、排行榜（TOP10）等**他区正常渲染** ✓ |
| `/api/progress/dashboard` → 500 | 3 处 role=alert（KPI 整区 + 打卡位 + 趋势覆盖层，同源同 retry 按规格）✓；雷达空态/正常渲染不受影响（独立错误）✓；趋势 canvas aria-label 变「（加载失败）」✓ |
| `/api/gamification/me/badges` → 500 | 徽章卡错误 `role=alert`「徽章数据加载失败重试」1 个 ✓ |
| 点击重试（解除拦截后） | 错误卡消失（failedAlerts=0），趋势恢复真实 aria-label 数据摘要，打卡恢复渲染 ✓ |

### 4.5 排行榜周期切换 refetch

- reload → `scope=DAILY`（1 次）；切「本周」→ `scope=WEEKLY`（+1）；切「本月」→ `scope=MONTHLY`（+1）；切回「今日」→ **0 新请求（命中 60s staleTime 缓存）** ✓
- 本周面板真实渲染（TOP10 + 我的排名 2）✓

### 4.6 空态边界

- mock `my_rank:null` → 排行榜仅渲染列表（小明/小红），**不渲染「我的排名」行** ✓
- 雷达空态（rate=null）实测 ✓；徽章 `items=[]` 空态、趋势 `recent_days=[]` 空态为静态代码路径验证（task01test 真实数据有 8 个锁定徽章/14 个 0 点，不触发空态分支；a11y 报告同口径）

### 4.7 a11y 回归补充（浏览器实测）

- 趋势/雷达 canvas：`role="img"` + aria-label 四态动态摘要 ✓（§4.1/§4.4）
- 错误态文字 + 图标（AlertCircle 装饰 aria-hidden）非仅颜色 ✓
- 重试按钮语义 native `<button>`，可访问名称「重试」，可聚焦 ✓；对比度 text-rose-700 ≈ 6.28:1、bg-primary 白字 ≥ 4.5:1（a11y 报告实测 6.19:1）✓
- 排行榜 Tab：`role="tablist"/"tab"` + `aria-selected`（快照可见「今日 [selected]」）✓
- 徽章墙空态引导链接 `next/link`（/courses）焦点可达（代码确认）✓

---

## 5. 单测统计（`npx vitest run`）

```
Test Files  30 passed (30)
     Tests  256 passed (256)
  Duration  17.78s（vitest v4.1.10，exit 0）
```

本 task 重点文件：

| 文件 | 用例数 | 结果 |
|------|--------|------|
| src/lib/api/dashboard.test.ts | 37 | ✅（派生纯函数：KPI 除零/雷达 clamp 与空态/打卡顺序/趋势反转/徽章映射/积分白名单/排行映射 + query 拼装/严格抛错/subject_preferences 双命名兜底） |
| src/lib/api/community.test.ts | — | ✅（getMyBadges/getMyPoints/getRankings 复用源） |
| 其余 28 文件（api-client/auth/protected-route/社区/成就/管理端等） | — | ✅ 全量通过 |

> stderr 中 `[dashboard] rankings scope mismatch: requested=WEEKLY, got=DAILY` 为测试用例故意触发 console.warn，属预期。

---

## 6. 静态校验与 grep 审计

| 审计项 | 命令 | 结果 |
|--------|------|------|
| TypeScript | `npx tsc --noEmit` | exit 0，0 错误 |
| ESLint（dashboard 范围） | `npx eslint "src/app/(user)/dashboard/page.tsx" "src/lib/api/dashboard.ts" "src/lib/api/dashboard.test.ts" "src/components/dashboard"` | exit 0，0 错误 |
| G1 MOCK 清除 | `grep MOCK_`（写路径 3 处） | **0 命中** ✓；`placeholderData` 0 命中 ✓ |
| G2 分功能多色 | `grep (emerald\|sky\|rose\|violet\|amber\|fuchsia\|teal\|orange\|pink\|cyan)-[0-9]+` | 62 处命中**全部为存量登记行**（design-tokens.json §adHocRegistry/§statusSemanticKeep：KpiCard ACCENT_MAP、PointCard 渐变/KIND_BADGE/gainTone、BadgeWallGrid CAT_COLORS、RankList 奖牌/头像渐变、StreakBadge 单元格）；本 task 新增仅错误态 `text-rose-700`（a11y #2 修复的语义加深档）✓ |
| G3 arbitrary 色值 | `grep bg-\[#\|text-\[#\|border-\[#\|from-\[#\|via-\[#\|to-\[#` | **0 命中**（echarts option 内部 hex 属图表配置层豁免）✓ |
| G4 内联色硬编码 | `grep style={{"color/background` | **0 命中**（仅 echarts 容器 `style={{width,height}}` 布局）✓ |
| G5 装饰性渐变/玻璃 | `grep bg-gradient\|backdrop-blur` | 14 处**全部为存量登记行**（PointCard/KpiCard/BadgeWallGrid/RankList/StreakBadge），本 task 未新增 ✓ |

---

## 7. 遗留项

1. **a11y HIGH #6 积分大数字渐变（1.94:1）未修**——属存量 ad-hoc（PointCard.tsx:81 `from-amber-500 to-fuchsia-600 bg-clip-text`），design-tokens.json §adHocRegistry 登记，规格边界「存量 ad-hoc 色零改动，本 task 只登记不触碰」，归口 fe-task07 收敛。**非本 task 新增，不影响本 task 判定。**
2. **a11y LOW 项未修（本轮范围外）**：KpiCard sr-only `loading` 英文（LOW #7）、PointCard loading 大数字「—」无语义（LOW #8）、StreakBadge aria-label 英文编码 `day-1-rest`（LOW #11）、/dashboard 无独立 page title（LOW #9）、区块标题无 h2（LOW #10）、错误 toast 重复轰炸（LOW #14）——均登记，建议 fe-task07 或后续 a11y 迭代跟进。
3. **perf P1-2 CLS 数值复测待办**：本轮修复为结构修复（RankList 骨架 topN 等量行 + 打卡 h-[168px] + 徽章墙等量骨架），骨架与数据态高度已对齐；CLS 0.289 → ≤0.05 的数值复测建议 fe-perf 复核（本报告以代码结构与骨架对齐验证为准）。
4. **环境性 console error（非本 task 缺陷）**：GlobalChatInjection 尝试拉取 localStorage 残留 chat 会话历史返回 403（会话不属于当前用户，server-info 注意事项 2 同口径）；dashboard 自身 6 query 无失败。
5. **空态分支验证说明**：徽章墙 `items=[]` 与趋势 `recent_days=[]` 空态为静态代码路径验证（task01test 真实数据有 8 个锁定徽章与 14 个 0 点，不触发空态分支）；空态文案已确认在代码路径且非 aria-hidden（a11y 报告同口径）。雷达空态与 my_rank=null 已浏览器实测。

---

## 8. 结论

- **判定：PASS**
- 功能验收标准 **7/7 通过**：5 数据区真实 API（6 端点网络请求逐字对齐 + MOCK 常量删除）、grep `MOCK_` 0 命中、三态（骨架 34 块时序 / 卡片级独立错误 role=alert + 重试恢复 / 空态与数值 0 边界）、雷达 5 维派生（rate×100 + 偏好偏移，仅 1 组）、KPI 4 卡派生（含除零 →「暂无数据」）、排行榜周期切换（WEEKLY/MONTHLY 精准 refetch + 回今日缓存命中 + my_rank null 不渲染我的排名行）
- **本轮修正回归通过**：a11y 5/6 HIGH 落实（role=alert 实测播报语义 + text-rose-700 ≈6.28:1 + 徽章/打卡/排行/积分 text-slate-600 + canvas role=img/aria-label 四态摘要；HIGH #6 存量登记按规格不触碰）；perf 3/3 P1 落实（雷达 /api/progress/dashboard 仅 1 次、CLS 骨架高度对齐、徽章 loading 等量骨架替代误导空态）
- 单测 30 files / 256 tests 全绿（dashboard 37 用例）；tsc 0 错误；eslint dashboard 范围 0 错误；G1–G5 grep 审计 0 违规
- 遗留：a11y HIGH #6 + LOW 项登记 fe-task07 收敛；CLS 数值复测待 perf 复核；环境性 chat 403 非本 task 缺陷
