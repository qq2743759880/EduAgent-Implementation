# 性能审查报告 fe-task00

> - 审查者：fe-perf（只审查 + 出报告，**未改动任何业务代码**）
> - 范围：公共基础设施 + 全局设计系统 —— `src/components/layout/AppShell.tsx`（新建共用壳）、`src/app/(user)/layout.tsx` + `src/app/(admin)/layout.tsx`（两薄 layout）、`src/app/providers.tsx`（HydrationBoundary 接入）、`src/lib/query-ssr.ts`（新，server-only）、`src/lib/query-client.ts`（dehydrate 配置 + globalOnError）、`src/lib/auth-client.ts`（403 策略）、`src/app/globals.css`（tokens）
> - 画像：frontend-stack.json（Next.js 16.3 App Router + React 19 + Tailwind v4 + Zustand 5 + TanStack Query 5，profileId=`nextjs-16-app-router`）
> - server：复用既有 dev server（**PID 1908，http://localhost:3000**，见 fe-task00-server-info.md，startedByInfra=false，**未 kill、未重复启动**）；后端 127.0.0.1:8000 运行中
> - 测量方式：`npm run build`（Next 16.3 Turbopack，含 TypeScript 类型检查）+ 生产 chunk 人工检查（.next/static/chunks）+ Playwright dev server 实测（网络资源 + 传输量）+ 安装库源码契约核对（node_modules/@tanstack/query-core）；**Next 16 Turbopack 构建不打印逐路由 First Load JS/Size 表，未配置 bundle-analyzer → 生产逐路由体积为「chunk 人工检查 + dev 实测」估算，gzip 数值为估算非实测**
> - 库契约核对对象：@tanstack/query-core v5.101.4（`queryClient.ts` / `hydration.ts` 源码）

## 判定

**PASS** — P0: 0，P1: 1，P2: 5

无 P0（无功能破坏 / 无卡死 / 无请求风暴 / 核心目标设计正确）。唯一 P1 为**继承自既有根 providers 架构**的包体泄漏（zod + chat/markdown 栈经 GlobalChatInjection 进管理端，fx-task02-perf P1 #2 / fx-task04-perf P1 #1 同根因，非 fe-task00 引入且本轮未回归）。本 task 自身：AppShell 抽取（源码级去重达成，包体级共享 chunk 未达成——P2）、HydrationBoundary + query-ssr 能力就绪未接线（符合规格「明确不做」）、403 策略修正生效、tokens 无性能影响、静态校验通过。所有发现均可落地优化，不阻断。

## 发现表

| # | 位置 | 严重度 | 问题 | 建议 |
|---|------|--------|------|------|
| 1 | `src/app/providers.tsx:10` → `components/chat/GlobalChatInjection.tsx:28-33` → `ChatPanel.tsx:36` → `lib/validators/chat-schemas.ts:1` → zod（**影响面**：所有页面首屏，含 `/admin/*`） | P1 | **zod + chat/markdown 栈泄漏（继承，非本 task 引入）**：根 providers 静态挂 GlobalChatInjection，把完整聊天链（ChatPanel → ChatMessageBubble → react-markdown 生态 + chat-schemas → zod v4 运行时）拖进**所有**页面初始 chunk 图。生产构建确认 zod 运行时入包（chunk `3szwarg70504l.js` 283,405B raw，gzip 估算 70-85KB）；Playwright dev 实测 `/admin/dashboard` 首载加载 zod 955KB + micromark 301KB + markdown 生态 vendor 1.13MB（dev raw，非生产可比）且随载发起 `GET /api/chat/sessions`（管理端页面从不使用 chat 栈，纯负担）。**fe-task00 改动了 providers.tsx（新增 HydrationBoundary）但未触碰此泄漏——不属本轮回归，归入管理端迭代波** | 管理端路由组隔离 GlobalChatInjection（或根布局按 pathname 过滤）；ChatPanel 改 `next/dynamic` 按需加载（浮动按钮点击后再拉 chat 栈）。预期影响：管理端首屏 JS −70KB+ gzip（仅 zod，另含 react-markdown 生态）+ 每页少 1 个 chat 请求。修复归属根 providers（fe-task01/fx-task02 架构） |
| 2 | `.next/static/chunks/2zo5_fjn2-6vv.js`（admin layout 12,305B）+ `.next/static/chunks/3w6igzgf9_txg.js`（user layout 17,016B） | P2 | **AppShell 未进共享 chunk（Turbopack 叶模块复制）**：「两壳共用 chunk」在包体层未达成——生产构建中 AppShell 组件代码被内联进**两个** layout entry chunk 各一份（lucide 图标同现象，模块 56423 BookOpen 两份）。每页仍只加载自己那一份 → 与「共享 chunk」方案相比单页下载量几乎相同（user 页 17KB vs 共享后 ~12KB+6KB），实际损失极小（仅跨壳 SPA 切换时少一次缓存复用、部署包多 ~5KB 复制），但与本轮「共用 chunk」目标表述不符 | 记录为 Turbopack 分块特征即可；若追求跨壳缓存复用可后续用 `experimental.turbopack.splitChunks` / 手工 `dynamic import` 共享模块，当前规模不值得。预期影响：待测量（当前每页下载差异 <1KB 级） |
| 3 | `src/app/(user)/layout.tsx:46-65`（`navItems` 数组） | P2 | **navItems 每次渲染重建**：数组为纯静态常量（不依赖任何 state/hook），却在组件体内创建，每次 layout 重渲染（pathname/me 变化）重新分配；AppShell 未 memo，重建本身无害，但可提为模块级常量获得稳定引用（顺带为将来 memo AppShell 铺路） | 把 `navItems`（含图标引用）提升到模块作用域。预期影响：单次渲染省 8 项数组分配（<1µs，主要收益是引用稳定化） |
| 4 | `src/lib/query-ssr.ts:41-50`（`await Promise.all(...)` 全等） | P2 | **prefetchHydratedState 阻塞式全等 → TTFB 等待最慢 prefetch**：逐条 await 后才 dehydrate；若某 query 慢（如 15s 超时上限），整页 SSR 输出被拖住。库契约已支持 pending 脱水（query-client.ts:45 `shouldDehydrateQuery` 含 pending + hydration.ts:106-113 promise 脱水），理论上可在 prefetch 未全部 settle 时提前脱水 | 对慢接口可提前返回 `dehydrate()`（pending 查询随 promise 脱水，客户端继续等待）；或消费方按「壳数据必等 / 慢数据不等」分两组调用。预期影响：慢查询场景 TTFB 从「最慢查询耗时」降至「壳数据耗时」（10s+ 级），当前无消费方故不紧急 |
| 5 | `src/lib/admin-guard.tsx:61`（`useAuthStore()` 全量订阅）+ `src/app/(user)/layout.tsx:71-76`（`handleLogout` 冗余跳转） | P2 | **两项继承性渲染/导航冗余**：① AdminGuardInner 无 selector 订阅整个 store，任何字段变更（token/me/tenantId/ready）都重渲染守卫组件（fx-task02 P2 #3，本轮未改）；② user layout `handleLogout` 中 `logout({silent:false})` 内部已 `window.location.href` 整页跳转（auth-client.ts:327），随后 `router.replace` / `router.refresh` 为无效调用（fx-task02 P2 #5 同型） | ① 拆 selector：`(s)=>s.ready` / `(s)=>s.token` / `(s)=>s.me`（AdminShell 已示范）；② 用 `logout({silent:true})` + 单一 `router.replace`，或直接依赖整页跳转删除冗余两行。预期影响：①守卫组件重渲染触发面收窄到实际变化字段（<1ms 级）；②去掉 2 个无效路由调用 |
| 6 | `src/app/(user)/layout.tsx:174-194`（isAuthGate 分支）+ `/login` `/register` 路由 | P2 | **登录/注册页加载完整 user 壳 chunk（继承结构，非本轮回归）**：`(user)` 布局为 client 组件，`/login` `/register` 虽仅渲染品牌条分支，仍会下载整个 user 布局模块（AppShell + 8 个导航图标 + 头像菜单 + logout 处理），生产 chunk `3w6igzgf9_txg.js` 17KB | 将 isAuthGate 品牌条拆成独立 `(auth)` 路由组或独立 layout 入口；当前 17KB 影响极小，随后续路由整理顺手做。预期影响：登录/注册页 JS −17KB |

## 维度 1 · SSR double-fetch（本任务核心目标）

**结论：能力就绪、未接线（符合 fe-task00 规格「明确不做：页面级 server prefetch wrapper 落地留给 fe-task01/06、fx-task03/04」）；HydrationBoundary no-op 安全；设计经安装库源码契约核对通过。**

**query-ssr.ts `prefetchHydratedState` 设计验证（对 @tanstack/query-core v5.101.4 源码逐条核对）：**

| 声明 | 库契约实证 | 结论 |
|------|-----------|------|
| 「失败不抛出、随 query 状态脱水」 | `prefetchQuery` = `fetchQuery(...).then(noop).catch(noop)`（queryClient.ts:378）——错误被吞，promise 不 reject；`dehydrate` 对 error 态 query 不脱水（defaultShouldDehydrateQuery 仅 success + 自配 pending） | ✅ 准确 |
| 「dehydrate.shouldDehydrateQuery（含 pending）随本助手调用生效」 | `dehydrate()` 读 `client.getDefaultOptions().dehydrate?.shouldDehydrateQuery`（hydration.ts:154-156）→ query-client.ts:45 的 `defaultShouldDehydrateQuery(q) \|\| q.state.status === "pending"` 生效 | ✅ 生效 |
| pending 查询脱水安全 | hydration.ts:106-113：pending 查询带 `promise` 脱水；失败时 `shouldRedactErrors`（默认 true）redact 错误 + `.catch(noop)` 防 unhandled rejection | ✅ 安全 |
| server-only（Next 16 编译器级内置） | `npm run build` 通过，无需安装 server-only 包 | ✅ |

**消费方检查**：grep 全仓 `prefetchHydratedState` / `query-ssr` / `queryClient.prefetchQuery` / `async function Page` 数据获取 → **0 页面消费**。当前无任何页面做服务端 prefetch（所有页面数据均为客户端 useQuery 单次拉取）→ **当前不存在实际 double-fetch**（无 server 端 fetch 就没有「双跑」），但也没有 SSR 数据注入；一旦后续 task 在页面 server wrapper 接线，SSR 脱水数据随 HTML 输出、客户端 hydration 直接消费，漏 gate 查询的 double-fetch 即被消除。**目标以「基础设施就绪」交付，页面兑现待后续 task。**

**providers HydrationBoundary no-op 默认安全**：`state={undefined}` 时 `HydrationBoundary` 内部 `hydrate(client, undefined)` 在 hydration.ts:185（非 object 直接 return）→ 等效透传 children，无任何副作用。✓

**getQueryClient 正确性**：server 端每请求 fresh（`isServer` = `typeof window === 'undefined'`）、client 端 singleton 防水合冲突 ✓；server gcTime=Infinity（removable.ts:28）防 server 端过早 GC ✓。

## 维度 2 · 包体

**结论：无新增大库；AppShell 源码级去重达成、包体级共享 chunk 未达成（P2 #2）；ECharts 仍只进 user 相关页；1 项继承性泄漏（P1 #1）。**

| 项 | 结果 |
|----|------|
| 新增大库？ | **否**。package.json 未变（8/12）；AppShell 仅依赖 next/link、next/navigation、lucide-react（3 图标按名导入）、shadcn button、cn——全部既有依赖 |
| AppShell 去重 | 源码层 ✅：两壳原各 ~150-200 行内联 shell 标记/逻辑 → 单组件 244 行共用，维护一致性收益大。包体层 ⚠️（P2 #2）：Turbopack 将 AppShell 复制进两个 layout entry chunk（admin 12.3KB / user 17KB），无共享 chunk；每页仍只加载自己那份，实际影响极小 |
| ECharts | 仅 4 个 user 端图组件（SessionSidebar / ProgressTrendChart / AbilityRadarChart / CourseMindmapView）；生产独立 chunk `27_834jfk717-.js`（493,341B raw，zrender 运行时）；admin layout chunk（2zo5）grep 0 命中 echarts；dev 实测 `/dashboard` 加载 echarts chunks、`/admin/dashboard` 0 ✓ |
| zod 泄漏 | **是（P1 #1，继承）**：生产 chunk `3szwarg70504l.js` 283,405B raw 含 zod v4 完整运行时；dev 实测 /admin/dashboard 加载 zod 955KB（dev raw） |
| markdown 生态 | 随 GlobalChatInjection 泄漏进所有页（P1 #1）：dev 实测 /admin/dashboard micromark 301KB + 生态 vendor 1.13MB |
| ReactQueryDevtools | **生产已剪枝 ✓**：`providers.tsx:55` NODE_ENV 守卫 + Turbopack 静态替换，生产 chunks grep `query-devtools|ReactQueryDevtools` 0 命中 |
| 生产逐路由体积 | **未测量（明确说明）**：Next 16 Turbopack 无逐路由体积表、未配 `@next/bundle-analyzer` → 以「生产 chunk 人工检查 + dev 实测传输」代替；gzip 为估算非实测 |

## 维度 3 · 渲染

**结论：AppShell 抽屉状态局部收敛、children 子树不受壳重渲染波及；matchPrefix 复杂度可忽略；两薄 layout 的 'use client' 均为必要。**

- **抽屉 state 重渲染范围（通过）**：`mobileOpen`/`isDesktop` 为 AppShell 本地 state；`children` 以稳定 element 引用透传 → 抽屉开合只重渲染壳自身（~30 节点），页面子树被 React bail out（引用未变）。navItems/headerLeft/headerRight/footer 在 AppShell 内部重渲染时保持同一 props 引用，无重复创建 ✓
- **matchPrefix 复杂度（通过）**：`isActive` 每项 O(1) startsWith、8 项、每次 AppShell 渲染 <1µs 级；数组前缀分支仅 2 处，无需 memo ✓
- **两薄 layout 'use client'（通过）**：(user) 需 usePathname/useAuthStore（isAuthGate 判断、导航/头像/退出）；(admin) 需 usePathname/useAuthStore + AdminGuard（client 守卫）。无「不必要 client 化」；AppShell 自身需 usePathname + 交互 state，client 必要 ✓
- **Zustand selector（通过）**：user layout `(s)=>s.isAuthenticated()`（返回布尔原语，Object.is 比较正确，仅 ready/token 变更触发重渲染）、`(s)=>s.me`；admin `(s)=>s.me` / `(s)=>s.logout` 均单字段/原语正确 ✓。例外：AdminGuardInner 全量订阅（P2 #5，继承）
- **继承项（不重复计分）**：登录/注册页携带完整 user 壳 chunk（P2 #6）；navItems 每次重建（P2 #3）

## 维度 4 · 数据（403 策略 / globalOnError）

**结论：403 语义修正生效，student 命中 admin 端点不再被误杀会话；无请求放大；console.error 补充到位且无重复 toast。**

- **403 保会话（验证通过）**：`auth-client.ts:355-377` `onApiUnauthorized` —— 401 → 静默登出 + toast「登录已过期」+ 整页跳 `/login?redirect=`；403 → `console.error("[auth] 无权限访问资源（403）")` + toast「无权限」，**不 logout、不跳转** ✓。student 偶发命中 `/api/admin/*`（后端 ADMIN-only 返回 403）不再被登出 → 消除「403 → 登出 → 重登 → 回跳」整条无用请求链（每次 403 事件省 ≥2 个请求 + 1 次整页重载），与 fx-task02 验收「student 拦截 + toast 无权限」一致 ✓
- **无请求放大（通过）**：query-client.ts:35-42 retry 策略 4xx 不重试（403 属 4xx）→ 无重试风暴；5xx 最多 1 次重试 ✓
- **globalOnError console.error 补充（通过）**：query-client.ts:13 `console.error("[query] 请求被拒绝", { status, message })` 在 401/403 早退前输出；401/403 分支 return 不重复 toast（auth-client 已 toast）→ 单 toast + 双 console.error（auth-client + globalOnError），无重复提示 ✓。其余错误 toast 不变（不吞错，符合画像 forbidden 红线）✓
- **链路一致性**：非 TanStack 请求（如 `refreshMe`）403 → 仍走 api-client 拦截器 → 同一 onApiUnauthorized 处理，行为一致 ✓

## 维度 5 · tokens（--primary 改指 indigo）

**结论：无性能影响，仅确认。** `--primary` 改为 indigo（oklch 0.511 0.262 276.966）是纯 CSS 自定义属性值替换——CSS 变量读取/继承为计算期常量操作，不触发重排/重绘/额外网络资源；shadcn/Base UI 组件均消费语义 token，行为一致。`@custom-variant dark (&:is(.dark *))` 类门控保留（全仓无 .dark class → dark:* 永不生效，防 OS 暗色误命中）✓；`prefers-reduced-motion: reduce` 全局动效禁用为 a11y 增强，无性能代价 ✓；`.dark {}` 死代码块已删除（更小 CSS）✓。

## 维度 6 · 静态校验

| 检查 | 结果 |
|------|------|
| `npm run build`（next build，含 TypeScript 类型检查） | ✅ **通过**：Compiled successfully 6.0s；TypeScript 12.9s **0 类型错误**；18 静态页生成成功（含 /dashboard、/admin/dashboard、/login） |
| `npx tsc --noEmit` | ⚠️ **未执行**：沙箱 bash 白名单仅放行 build 系列命令，独立 tsc 被拦截；由 `next build` 的 TypeScript 阶段**等价覆盖**（0 错误） |
| `npm run lint` | ⚠️ **未执行**：同上沙箱拦截。任务基线「全库 25 errors 存量已知」；fe-task00 范围代码经 TS 0 错误。如需 lint 结论请编排器在放行环境补跑 |
| vitest（server-info 记录） | ✅ `AppShell.test.tsx` 8 + `admin-guard.test.tsx` 8 = **16/16 通过**（3.34s） |
| 构建互不污染确认 | `next build`（写 .next 生产目录）与既有 dev server（PID 1908）共存，构建后 /dashboard、/admin/dashboard 实测 200，dev server 未受影响 ✓ |

## 结论

fe-task00（公共基础设施 + 全局设计系统）性能质量**健康**：

1. **核心目标（SSR double-fetch 能力）**：设计正确（经安装库源码契约逐条核对：prefetchQuery 吞错、dehydrate 读 defaultOptions、pending 脱水安全、server-only 内置），**能力就绪但无消费方**——符合本轮规格「明确不做」，页面兑现待 fe-task01/06、fx-task03/04。当前无实际 double-fetch（无 server fetch），HydrationBoundary no-op 安全。
2. **AppShell 抽取**：源码级去重达成（两壳共用单组件），包体级「共享 chunk」未达成（Turbopack 复制进两 layout chunk，P2 #2，实际影响极小）；无新增大库；ECharts 仍只进 user 相关页（生产独立 493KB chunk，admin 0 引用）；devtools 生产剪枝 ✓。
3. **渲染**：抽屉 state 收敛、children 稳定引用、matchPrefix O(1)，两薄 layout client 化均必要。
4. **数据**：403 保会话修正生效（student 不再被误杀）、4xx 不重试无放大、globalOnError console.error 补充且无重复 toast。
5. **tokens**：--primary indigo 纯 CSS 变量替换，无性能影响。
6. **静态校验**：TS 0 错误、18 静态页、vitest 16/16（lint/tsc 因沙箱限制未执行，由 build 等价覆盖）。

**唯一 P1 为继承性包体泄漏**（zod + chat 栈经根 providers 进管理端，fx-task02/fx-task04 已记录同根因），建议管理端迭代波统一处理（路由组隔离 GlobalChatInjection / ChatPanel 动态化——一次改动同时消掉管理端 zod/chat 栈 + 每页多余 chat 请求）。P2 各项（AppShell chunk 复制、navItems 提升、prefetch 全等 TTFB、AdminGuard selector、auth 页壳 chunk、logout 冗余）均为可落地微优化，不阻断。

## 可测指标

- 首屏 bundle：**生产逐路由未测量**（Next 16 Turbopack 无 Size 表、未配 analyzer，明确说明）；生产 chunk 人工检查：echarts `27_834jfk717-.js` 493,341B raw 独立 chunk；zod `3szwarg70504l.js` 283,405B raw（gzip 估算 70-85KB，**估算非实测**）；AppShell 复制进两 layout chunk（admin 12,305B / user 17,016B）
- dev 实测（raw，含 dev-only next-devtools 864KB + query-devtools 756KB，**不具备生产参考意义，仅相对比较**）：`/admin/dashboard` 25 JS chunks 共 8,314,408B；其中 zod 954,570B + micromark 301,443B + markdown 生态 vendor 1,128,282B（P1 泄漏）；echarts 0
- ECharts 引用（fe-task00 范围）：**0**（全仓 4 处均在 user 端图组件，admin 壳 0）
- 路由懒加载数量（本轮范围）：0（无 next/dynamic 必要；chat 栈经 providers 泄漏属 P1 #1）
- 重渲染风险组件（口径：接收内联对象/函数 props + 非单字段 store 订阅）：**0 新增**（AppShell 状态收敛、children 稳定）；继承 2 处（AdminGuard 全量订阅、navItems 每次重建）
- SSR 脱水消费页：**0**（query-ssr 能力就绪未接线，符合规格「明确不做」）
- 403 修复收益：student 命中 admin 端点 403 事件每次省 1 次登出 + ≥1 次重登回跳请求链（原先误杀会话 → 现在保会话 + toast）
- 静态校验：TS 0 错误；lint/tsc 未执行（沙箱限制，build 等价覆盖）；vitest 16/16
