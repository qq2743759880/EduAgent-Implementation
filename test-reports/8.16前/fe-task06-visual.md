# 视觉审查报告 fe-task06

- 任务：fe-task06（G5 用户端仪表盘真实数据接入：状态视觉规范）
- 审查范围：`/dashboard`（KPI 4 卡 / 打卡 / 积分 / 趋势 / 雷达 / 徽章墙 / 排行榜）+ 三态视觉（骨架/错误/空态）
- 审查方式：**规格驱动 + 真实浏览器渲染验证**。当前模型不支持图像输入，无法逐像素查看 PNG，改用 Playwright DOM 快照 + 布局测量（getBoundingClientRect）+ 计算样式 + 对比度计算 + 网络请求断言 完成量化验证；截图全部留存供人工复核。**非像素级复刻**。
- 规格依据：`design-options.md` §2.2/§4/§5/§6、`visual-acceptance.md`、`design-tokens.json`（fe-task06 消费侧 + adHocRegistry 存量登记）、`screen-map.md`
- 画像：`frontend-stack.json`（nextjs-16-app-router）

## 环境

- 启动方式：复用 fe-server-infra dev server（server-info `test-reports/fe-task06-server-info.md`，PID 1908，`startedByInfra=false`，未重复启动）
- 端口/baseUrl：`http://localhost:3000`（Next.js 16.3 dev / Turbopack）；后端 `http://127.0.0.1:8000`（运行中）
- 登录账号：`task01test / Test@123456`（student，user_id=846，昵称「任务一测试」），JWT 注入 `localStorage["edu:auth:token"]` 后刷新
- 截图目录：`test-reports/screenshots/fe-task06/`

## 截图清单（12 张）

| # | 文件 | 视口 | 状态/场景 |
|---|------|------|-----------|
| 1 | `dashboard-1440.png` | 1440×900 | 成功态（真实数据：KPI 0 值 / 积分 31 / 排行第 2 / 徽章 0-8 / 雷达空态） |
| 2 | `dashboard-375.png` | 375×812 | 成功态（移动端单列） |
| 3 | `dashboard-loading-1440.png` | 1440×900 | 骨架屏（route 延迟 10s） |
| 4 | `dashboard-loading-375.png` | 375×812 | 骨架屏（route 延迟 10s） |
| 5 | `dashboard-error-1440.png` | 1440×900 | 错误态（progress+courses → 500：KPI 整区 / 打卡 / 趋势 / 雷达错误卡） |
| 6 | `dashboard-error-375.png` | 375×812 | 错误态（同上） |
| 7 | `dashboard-empty-1440.png` | 1440×900 | 空态（徽章 items=[] 虚线框空态 + 雷达覆盖层空态） |
| 8 | `dashboard-empty-375.png` | 375×812 | 空态（同上） |
| 9 | `dashboard-trend-empty-1440.png` | 1440×900 | 趋势空态（recent_days=[] 覆盖层） |
| 10 | `dashboard-rank-month-1440.png` | 1440×900 | 排行榜「本月」tab（数据切换真实） |
| 11 | `dashboard-200pct-1440.png` | 1440×900 | 200% 字体缩放 |
| 12 | `dashboard-hc-1440.png` | 1440×900 | 强制高对比（forced-colors） |

> dark 视图 N/A：全站 light-only（design-options §1 / visual-acceptance §1 裁决，本 task 未新增 `dark:` 依赖）。

## 三态视觉记录

### 成功态（真实数据，task01test）

| 数据区 | 渲染结果（DOM 断言 + 网络请求核对） | 判定 |
|--------|------------------------------------|------|
| KPI 4 卡 | 「今日学习时长 0 分钟（较昨日持平）/ 今日练习题 0 道（暂无数据）/ 进行中课程 0 门 / 连续打卡 0 天」；`attempted=0 → 暂无数据` 中性文案正确 | ✅ 0 值为合法业务数据，非空态 |
| 积分卡 | 当前积分 31、今日 +17、明细 8 条（发帖/回帖混合），与 server-info 逐字段一致 | ✅ |
| 排行榜 | 今日 tab：我 17 分（第 2）、TOP9 完整；切「本周」榜首 1161 分、切「本月」榜首 23150 分——scope 切换真实（网络请求 `rankings?scope=WEEKLY/MONTHLY`） | ✅ |
| 徽章墙 | 0/8、8 个未解锁徽章 + 解锁条件（STUDY_MIN_TOTAL 60 等） | ✅ 非空态（items 非空） |
| 雷达图 | `overall_correct_rate=null` → 空态「学习后即可生成学科能力评估」（非全 0 雷达） | ✅ 空态正确 |
| 趋势图 | 单线（hasPractice=false 无 legend），14 点全 0 | ✅ 单线为预期形态 |

### 骨架屏（限速模拟：route 拦截延迟 10s）

- **14 个 pulse 块**：KPI 4 卡各自 `animate-pulse bg-slate-100 rounded-md`（KpiCard 复用）、打卡卡页面级块 `animate-pulse bg-muted rounded-xl h-48`、积分/排行行骨架等
- 图表显示 `loading`（showLoading indigo 文案）；徽章 `description="加载中…"`
- 骨架全部中性灰（无渐变、无分功能多色）
- **375/1440 双视口均无溢出、无塌陷**

### 错误态（route 拦截 progress+courses → 500）

- **KPI 整区错误卡**：「学习数据加载失败」+ 重试按钮，**未渲染 0 分钟/0 道兜底**（断言 `kpiZeroDup=false`）✅
- **打卡卡同源错误**（随 trend 同源，独立错误卡）✅
- **趋势/雷达覆盖层错误态**：`absolute inset-0` 覆盖层（高度 320/340 保持不塌陷）+ 重试按钮 ✅
- **卡片级独立**：progress 500 时积分（31 分）、徽章、排行榜仍正常渲染——单区失败不影响他区 ✅
- 共 4 处「加载失败」+ 4 个「重试」按钮（KPI/打卡/趋势/雷达）
- 双视口无布局跳动、无溢出

### 空态

| 空态 | 注入方式 | 视觉 | 判定 |
|------|---------|------|------|
| 徽章墙 | route 返回 `items:[]` | 虚线框 `border-dashed border-border bg-muted/40` + Award 图标 + 「解锁第一枚徽章，从今天的学习开始」+ `text-primary` 引导链接「去课程中心看看」 | ✅ 符合 §4.3 |
| 雷达 | 真实数据（overall_correct_rate=null） | 覆盖层空态「学习后即可生成学科能力评估」（340px 保持） | ✅ 符合 §4.2 |
| 趋势 | route 返回 `recent_days:[]` | 覆盖层空态「开始学习后，这里会记录你每天的学习时长」（320px 保持） | ✅ 符合 §4.4 |
| 积分/排行 | 组件既有空态（保留） | — | ✅ |

> 注：空态拦截需返回「纯响应体」而非 envelope（axios 层 `getMyBadges` 直接返回 body；返回 envelope 会二次解包导致 crash）。此为测试注入注意事项，非实现缺陷（真实后端直接返回纯结构）。

## 布局检查（1440 / 375）

| 检查项 | 1440 | 375 |
|--------|------|-----|
| 水平溢出 | `scrollWidth=1425 ≤ clientWidth`，无越界元素 | 无溢出、无越界元素 |
| section 重叠 | 6 区无重叠 | 6 区无重叠 |
| KPI 网格 | 4 卡同一行（distinctRows=1） | 单列堆叠（sm:grid-cols-2 下 2 列，375 单列正常） |
| 图表高度 | 趋势 320 / 雷达 340 保持（错误/空态覆盖层不塌陷） | 同上 |
| 三态切换布局跳动 | 骨架→错误→空→成功各状态 section 边界稳定、卡片不塌陷 | 同上 |
| 200% 缩放 | 无水平滚动、无元素裁切 | — |
| 高对比（forced-colors） | 无溢出、文字可读 | — |

## grep 审计（G1–G5）

| 项 | 命令范围 `src/app/(user)/dashboard` `src/components/dashboard` `src/lib/api/dashboard.ts` | 结果 |
|----|-------------------------------------------------------------------------------------------|------|
| G1 MOCK 清除 | `grep "MOCK_"` | **0 命中** ✅ |
| G2 不新增分功能多色 | `(emerald\|sky\|...)-[0-9]+` | 60 命中**全部为存量 adHocRegistry 登记行**（KpiCard ACCENT_MAP / BadgeWallGrid CAT_COLORS / PointCard / RankList / StreakBadge / 快捷入口 5 色），`page.tsx` 新增三态代码（DataErrorCard/骨架/空态/覆盖层）**无多色** ✅ |
| G3 不新增 arbitrary 色值 | `bg-[#|text-[#|...` | **0 命中** ✅ |
| G4 不新增内联色硬编码 | `style={{color/background}}` | 仅 echarts 容器 `style={{width,height}}`（布局非色）✅ |
| G5 不新增装饰性渐变/玻璃拟态 | `bg-gradient|backdrop-blur` | 新增行 0；存量渐变（PointCard/RankList/StreakBadge 等）登记于 adHocRegistry **本 task 零改动** ✅ |
| G6 状态语义核对 | 人工 | 新增代码全部 tokens 语义 class（`bg-muted` / `border-destructive/30` / `bg-destructive/10` / `text-destructive` / `text-muted-foreground` / `bg-primary`）；错误仅 destructive、空态仅中性、骨架仅 muted ✅ |

## 一致性核对（与 fe-task01 / fx-task02 既有模式）

- 错误态：本 task `rounded-xl border border-destructive/30 bg-destructive/10 text-destructive` + `bg-primary text-primary-foreground` 重试按钮 —— tokens 化后与 fe-task01 community「失败错误态可重试」、PointLogTable「错误不显示 0」模式同构（design-options §2.2）✅
- 骨架屏：`animate-pulse bg-muted rounded-xl`（中性灰，禁止渐变）——与 fe-task01 PointCard/RankList 同款 ✅
- 空态：`rounded-xl border border-dashed border-border bg-muted/40 text-muted-foreground` + 图标 + 引导文案 —— 与 fe-task01 RankList/PointCard 虚线框空态同构 ✅
- 判定顺序：`isError && !data → 错误`；`isLoading → 骨架`；`空数组 → 空态`；`有值 → 渲染`（对齐 PointLogTable.tsx:49-51 实证模式）✅

## 发现分类

### [规格违背]（必须修正）

无。

### [浏览器行为错误]（必须修正）

无。

### [内容/文案]（建议修正）

无。

### [主观建议]（不强制）

1. **错误态文字对比度略低于 WCAG AA 4.5:1**：`text-destructive`(#e70044) 与 `bg-destructive/10`(≈#fde6ec) 实测对比度 **3.95:1**（普通文字 14px medium 需 ≥4.5）。根因是 tokens 层 destructive 色值（fe-task00 固化，本 task 按规格使用语义 class，未引入任何硬编码色）；建议 fe-task07 tokens 治理时评估加深 destructive 或错误态加大字号/字重（按钮 6.19:1、空态 4.59:1 均达标）。
2. **测试环境提示**：若浏览器 localStorage 残留非当前用户 token（如 admin），`/api/progress/dashboard` 带该 token 会 500（admin 用户学习链路无数据导致），前端正确显示错误卡——属数据账号差异，非前端缺陷；视觉验收使用 task01test 会话即可复现真实数据成功态。

## 判定

- 结论: **PASS**
- 阻塞项: 无（0 规格违背、0 浏览器行为错误）
- 附加确认：成功态 5 数据区 + KPI 全部来自真实 API（网络断言 `127.0.0.1:8000/api/*` 请求 + 响应字段与 server-info 对照一致）；三态在 1440/375 无布局跳动；图表高度恒定；`MOCK_` 0 命中；新增代码无 arbitrary/内联/分功能多色。

## 机器可读结论（供评测自动断言）

```json
{"taskId": "fe-task06", "result": "PASS", "blockers": []}
```

---

*产物：`test-reports/fe-task06-visual.md` · 执行方：fe-visual-auditor · 未改任何业务代码（只读审查 + Playwright 截图/拦截注入，注入均在浏览器层，源码零改动）*
