# 性能审查报告 fe-task06

> G5 用户端仪表盘真实数据接入（fe-task06）· 性能审查
> 审查方式：静态代码审查（dashboard.ts / page.tsx / 7 组件 / community.ts 复用源）+ 真实构建（`npm run build`，Next 16.3 Turbopack）+ 浏览器实测（Playwright MCP 对 dev server `http://localhost:3000`，admin/Admin@12345 真实登录，复用 fe-task06-server-info 记录的 PID 1908 dev server，未 kill / 未重启）
> 审查范围：仅 fe-task06 改动（dashboard.ts 聚合 / page.tsx 6 query / 组件 empty/error props / MOCK 去除）

## 判定

verdict: **PASS**

- P0：0（无阻断性能目标的问题）
- P1：3（雷达重复请求、CLS 布局跳动、徽章墙 loading 空态）
- P2：5（echarts 首屏体积、RankList 三 tab 同渲染、UniversalTransition、containLabel 警告、打卡卡骨架高度）

---

## 发现表

| # | 位置 | 严重度 | 问题 | 建议 |
|---|------|--------|------|------|
| 1 | `page.tsx:129`（radar queryFn `Promise.all([getProgressDashboard(14), getMySubjectPreferences()])`）与 `page.tsx:112-116`（trend query 同端点） | P1 | 首屏 `/api/progress/dashboard?days=14` 被请求 **2 次**（trend + radar 各 1），浏览器实测确认（66ms / 104ms 两个请求）。架构文档薄弱点 10 已承认，60s staleTime 内不重复，但首屏必然多发 1 次 | radar queryFn 先读 `queryClient.getQueryData(["dashboard","trend"])` 命中则不再请求（仅缺失时兜底请求），或保持现状（影响 ~100ms 后端负载/首屏，本地实测无感知）。预期节省：首屏 −1 次请求 / −60~100ms 等待 |
| 2 | `page.tsx:341`（打卡骨架 `h-48`）、`page.tsx:410-417`（RankList）、`BadgeWallGrid.tsx:119-126` | P1 | **CLS 实测 0.289**（超 0.1 Good 阈值，接近 0.25 Poor）：骨架→数据替换未预留数据态高度——RankList 骨架 5×h-11（~220px）→ 10 行列表（~500px）、徽章墙 loading 空态 → 网格、打卡卡 h-48 → StreakBadge 均造成下方内容位移 | 加载态容器预留数据态 min-height：RankList 骨架按 `topN` 行数渲染等量行；BadgeWallGrid loading 渲染等量徽章卡骨架；打卡卡骨架高度对齐 StreakBadge 实测高度。预期：CLS 0.289 → ≤0.05 |
| 3 | `page.tsx:396-401`（`badges={badgesQuery.data ?? []}` + `description="加载中…"`） | P1 | **徽章墙 loading 态显示空态文案**「解锁第一枚徽章」（badges=[] → BadgeWallGrid 内部空态分支），数据到达后跳变为网格。状态机未区分 loading/empty（组件无 loading prop，只有 description 提示）。本地后端响应快未触发，慢网络下会闪「未解锁」误导文案 | BadgeWallGrid 增加 `loading?: boolean`，loading 时渲染等量网格骨架而非空态；或页面 loading 时暂不渲染该卡片（占位块）。预期影响：消除误导空态闪现（感知性能） |
| 4 | `ProgressTrendChart.tsx:3-19,25-33` / `AbilityRadarChart.tsx:3-18,29-36`（echarts 静态 import） | P2 | echarts/zrender 生产 chunk `27_834jfk717-.js` ≈ **493KB minified**（gzip 估 ~130-150KB）随 dashboard 首屏加载。已按需注册（core/components/charts/renderer），且被 learning/curriculum 页面共享（非本 task 新增），属 echarts 下限体积 | 趋势图是首屏 LCP 元素不建议整图懒加载；如未来接受折线图简化，可评估替换轻量图表库（超出本 task 范围）。预期影响：待测量（当前为共享依赖，本页无法单独减负） |
| 5 | `RankList.tsx:103-115`（`ranges.map` 三组 TabsContent 全部渲染） | P2 | 3 个 TabsContent 同时渲染 RankListBody：loading 时 3×5=15 个骨架块（2 组 display:none 隐藏仍渲染）；每次数据变更 3 组 list 计算/slice | TabsContent 惰性渲染（仅 active tab 渲染）或 loading 用单一占位。预期影响：骨架渲染数 15→5（−67%），隐藏 DOM −66% |
| 6 | `ProgressTrendChart.tsx:18,32`（`UniversalTransition`） | P2 | echarts features 模块仅用于系列动画过渡，单线图（hasPractice=false 无多系列切换）用途有限 | 移除 UniversalTransition 注册。预期影响：chunk −几 KB（待测量） |
| 7 | `ProgressTrendChart.tsx:103`（`grid.containLabel: true`） | P2 | echarts 6 console 实测警告：`Specified grid.containLabel but no use(LegacyGridContainLabel); use grid.outerBounds instead`（非性能，兼容提示） | 改用 `grid.outerBounds` 或注册 LegacyGridContainLabel 消除警告。预期影响：0（仅消警告） |
| 8 | `page.tsx:341`（打卡骨架 `h-48`） | P2 | StreakBadge 实测高度与骨架 192px 存在差异，贡献部分 CLS | 骨架高度对齐 StreakBadge（含 header+pill+7 格）实测高度。预期影响：CLS 贡献 −0.02~0.05（并入 #2） |

---

## 查询设计审计

**6 个 query 全量核实**（page.tsx）：

| queryKey | queryFn 返回 | staleTime | 实测 |
|----------|--------------|-----------|------|
| `["dashboard","trend"]` | `getProgressDashboard(14)` → 原始 DashboardOut | 60s | ✓ 浏览器实测 1 次请求 |
| `["dashboard","courses"]` | `getProgressCourses()` → ProgressCourseItem[] | 60s | ✓ 1 次 |
| `["dashboard","ability-radar"]` | `Promise.all([getProgressDashboard(14), getMySubjectPreferences()])` → deriveAbilityRadar | 60s | ⚠️ 内部再发 1 次 progress/dashboard（见发现 #1）；prefs 仅 `/api/users/me/profile` |
| `["dashboard","badges"]` | `getMyBadges()` → mapBadgesToWall | 60s | ✓ 1 次 |
| `["dashboard","points"]` | `getMyPoints(1,20)` → mapPointsToCard | 60s | ✓ 1 次 |
| `["dashboard","rank",range]` | `getRankings(RANGE_SCOPE[range],"POINTS",10)` → buildRankSlice | 60s | ✓ 见下 |

- **并发加载策略**：浏览器实测首屏 8 个 API **并行发出**（chat/sessions 为全局组件 + 7 个 dashboard 数据请求），时长互相重叠（66-130ms），无串行阻塞。5 数据区独立 query 互不影响 ✓
- **rank range 维度补全**：实测切「本周」→ 新增 `?scope=WEEKLY` 请求；切「本月」→ 新增 `?scope=MONTHLY`；切回「今日」→ **无新请求（命中 60s 缓存）**。queryKey 含 range 维度修复生效（架构薄弱点 5 已闭合），每次切 tab 仅 1 个新请求 ✓
- **courses 与 trend 依赖**：KPI 派生 `useMemo`（page.tsx:179-183）正确依赖 `[trendQuery.data, coursesQuery.data]`，两源并行获取，慢的一方拖住 4 卡 loading（设计决策，非缺陷）✓
- **雷达重复请求**：见发现 #1（P1，架构已承认的可接受项）

---

## 派生 / 渲染审计

**7 个派生函数位置与依赖**：

| 派生函数 | 位置 | 时机 | 依赖 | 评估 |
|----------|------|------|------|------|
| `toProgressTrend` | `page.tsx:173-176` useMemo | 渲染时 | `[trendQuery.data]` | ✓ 正确 |
| `deriveDashboardKpis` | `page.tsx:179-183` useMemo | 渲染时 | `[trendQuery.data, coursesQuery.data]` | ✓ 正确 |
| `deriveStreakLast7` | `page.tsx:186-189` useMemo | 渲染时 | `[trendQuery.data]` | ✓ 正确 |
| `deriveAbilityRadar` | `page.tsx:131` queryFn 内 | fetch 时 1 次 | — | ✓ 单一消费方，避免渲染重复计算 |
| `mapBadgesToWall` | `page.tsx:141` queryFn 内 | fetch 时 1 次 | — | ✓ |
| `mapPointsToCard` | `page.tsx:153` queryFn 内 | fetch 时 1 次 | — | ✓ |
| `buildRankSlice` | `page.tsx:164` queryFn 内 | fetch 时 1 次 | range | ✓ |

- **KPI 派生复杂度**：`deriveDashboardKpis` O(n)（courses.filter 单遍 + slice(0,7) 常量级），无性能风险 ✓
- **雷达 clamp**：`clamp(Math.round(base + (s-3)*5), 0, 100)` 偏移 ±10、0-100 边界正确；`overallRate==null → []` 空态（禁止全 0 雷达）✓
- **骨架屏→数据替换跳变**：❌ CLS 实测 0.289（发现 #2/#8），加载态高度未预留
- **组件 empty/error 覆盖层**：趋势/雷达 error 覆盖层 absolute inset-0 优先级高于 empty、高于图表（图表容器固定 320/340px 无布局跳动）✓；KPI 整区错误卡 / 打卡同源错误卡 / 徽章/积分/排行整卡错误替换均正确（error → 早退不显示 0）✓
- **echarts 使用**：两图表按需注册（core + 特定 component/chart/renderer），非整库 import ✓；`echarts.init` 单例挂 ref + resize/dispose 清理正确 ✓；首屏静态引入使 echarts chunk 进 dashboard 首屏（发现 #4）
- **`'use client'` 边界**：dashboard 全页 client（token 在 localStorage，SSR 必 401），无服务端 prefetch，符合画像约束 ✓

---

## 数据冗余审计

- **getMySubjectPreferences 主源/降级**（dashboard.ts:107-113）：主源 `/api/users/me/profile` → `readSubjectPreferences(profile)` 返回**非 null 即短路**（空数组 `[]` 为 truthy 同样短路，不触发降级）→ 仅字段缺失（null）才发 `/api/users/me`。**浏览器实测仅 1 次 `/api/users/me/profile`，无降级请求** ✓（主源存在时不发降级，符合审查维度 4）
- **gamification 复用**：`getMyBadges`/`getMyPoints`/`getRankings` 直接 `import from "@/lib/api/community"`（community.ts:286/291/298），零重复实现 ✓；类型（BadgeListResponse/PointsResponse/RankingResponse…）复用 ✓；queryKey 前缀 `["dashboard",...]` 与成就页 `["gamification",...]` 独立缓存，跨页不重复拉取 ✓
- **不复用 learning.ts getMyCourses()**（其 `[]` 兜底吞错）：`getProgressCourses` 严格抛错 ✓ 符合 R-7

---

## 包体审计

- **dashboard.ts 新增引入**：仅 `api-client` + 组件类型 + community 类型 + `SUBJECT_OPTIONS`，**无新增大库** ✓（审查维度 5 通过）
- **echarts**：生产构建 `.next/static/chunks/27_834jfk717-.js` ≈ 493KB minified（内容特征 `createSymbol`/`enterEmphasis`/`retrieveRawValue` = echarts core + zrender + 注册模块）。非仅本页：`SessionSidebar.tsx`（learning）、`CourseMindmapView.tsx`（curriculum）同样使用，属**共享依赖**，非本 task 新增。dashboard 首屏静态引入（发现 #4）
- **其他大 chunk 归属**：902KB（`2oyngvygvc--s.js`，Prism/markdown 高亮 = @uiw/react-md-editor，chat/community 使用）与 277KB（`3szwarg70504l.js`）均与 dashboard 无关 ✓
- **dev 运行时实测**：37 个 JS chunk、transfer 合计 ~11KB（dev 缓存命中 304/内存缓存），TTFB 95ms / DCL 126ms / load 484ms，DOM 1328 节点
- **工具说明**：Next 16 Turbopack build 输出无 First Load JS / Size 列；`npx @next/bundle-analyzer` 未安装配置（permission 亦受限）。包体数据为 `.next/static/chunks` 产物实测（file:size），非编造

---

## 静态校验

| 校验项 | 命令 | 结果 |
|--------|------|------|
| TypeScript | `npx tsc --noEmit`（等价：`npm run build` 内建 TypeScript 检查，tsconfig strict + noEmit） | **0 error**（next build「Finished TypeScript in 5.5s」通过，页面 18/18 静态生成成功） |
| ESLint | `npm run lint` | **未运行**——工具权限白名单不含该命令；降级为静态审查：`eslint.config.mjs` 使用 `eslint-config-next/core-web-vitals + typescript` 预设；dashboard 范围（page.tsx / dashboard.ts / 7 组件）人工核查：无未使用导入、无 react-hooks 依赖缺失（三处 useMemo deps 完整）、无 any 泄漏（dashboard.ts 仅 `Record<string, unknown>` 防御性读取 subject_preferences，带守卫）、MOCK_ 0 命中（server-info 已 grep 核实）。dashboard 范围静态审查 **0 明显 error** |
| 单测 | `npx vitest run src/lib/api/dashboard.test.ts`（server-info 记录） | 37/37 passed（派生纯函数 + 双命名兜底全覆盖） |

> 结论：静态校验通过（tsc 0 error）；lint 因工具权限未执行，已按静态审查降级并在上文如实说明，不编造「lint 通过」。

---

## 可测指标（浏览器实测，dev server + 本地后端）

- 首屏 API 请求数：**8 个**（7 个 dashboard 数据 + 1 个全局 chat/sessions）；其中 `/api/progress/dashboard?days=14` **重复 1 次**（radar 内）→ 实际端点 6 个 / 请求 7 次
- 路由懒加载数量：**0**（dashboard 图表静态引入；本页无 next/dynamic 懒加载——趋势图为首屏 LCP 元素，属合理）
- 重渲染风险组件：**3**（RankList 3 组 TabsContent 同渲染 + 每卡内联 icon JSX；KPI 4 卡共用 loading 源；BadgeWallGrid loading 空态）
- LCP：~1.17s（dev 本地，生产未测）；TTFB 95ms；DCL 126ms；load 484ms
- CLS：**0.289**（超 0.1 Good 阈值，来源：骨架→数据高度未预留）
- rank tab 切换：每次 +1 请求（WEEKLY/MONTHLY），回今日命中缓存 0 请求
- 生产 chunk：echarts/zrender ≈493KB minified（跨页共享）；dashboard 首屏 JS 37 chunk（dev 模式，生产结构以 build 产物为准）

---

## 结论

fe-task06（G5 仪表盘真实数据接入）性能整体**合格（PASS）**：

- **查询设计**：6 query staleTime 60s 统一、5 数据区并发、rank range 维度补全经浏览器实测验证正确（切 tab 精准 refetch + 缓存命中）、courses/trend 依赖正确——除雷达首屏重复 1 次 progress 请求（P1，架构已登记的可接受项）外全部达标
- **派生/渲染**：7 派生函数位置与依赖正确（queryFn 内派生 4 个 + useMemo 派生 3 个），KPI O(n)、雷达 clamp 正确；主要短板是骨架→数据 CLS 0.289（P1）与徽章墙 loading 空态（P1），均为可修复的加载态呈现问题
- **数据冗余**：subject_preferences 主源优先实测确认不发降级请求；gamification 完全复用 community.ts 无重复实现
- **包体**：dashboard.ts 零新增大库；echarts 按需注册且为跨页共享依赖（非本 task 引入），无回归
- **静态校验**：tsc 0 error；lint 因工具权限未运行（已如实降级说明）

**修正建议优先级**（供 fe-implementer 修正循环）：先修 CLS（RankList/徽章墙骨架高度预留，收益最大）、再消除雷达重复请求、最后补 BadgeWallGrid loading 态。
