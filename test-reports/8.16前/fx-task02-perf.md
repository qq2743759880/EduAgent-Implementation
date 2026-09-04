# 性能审查报告 fx-task02

> - 审查者：fe-perf（补课波，只审查+出报告，未改动任何业务代码）
> - 范围：`src/app/(admin)/layout.tsx`、`src/lib/admin-guard.tsx`、`src/lib/admin-nav.ts`、`src/lib/api/admin.ts` + `admin-api-types.ts`、`src/app/(admin)/admin/dashboard/page.tsx`
> - 画像：frontend-stack.json（Next.js 16.3 App Router + Tailwind v4 + Zustand + TanStack Query）
> - server：复用 fe-task01 dev server（PID 3780，http://localhost:3000，见 fx-task02-server-info.md，未重复启动）
> - 测量方式：curl（SSR 输出）+ Playwright（真实传输体积）+ `tsc --noEmit` + `eslint`；**未跑 `next build`**（dev server 占用 `.next`，避免产物互相污染，生产体积为估算/未测量，已在文中标注）

## 判定

**FAIL** — P0: 0，P1: 2，P2: 4

无 P0（无功能破坏/无卡死），但存在 2 个 P1 级性能问题：① 管理端 SSR 零内容（全量客户端渲染，LCP 后移）；② 根 providers 把 chat/markdown 大栈拖进所有管理端页面（包体泄漏）。均为可落地优化项，非功能缺陷。

## 发现表

| # | 位置 | 严重度 | 问题 | 建议 |
|---|------|--------|------|------|
| 1 | `src/lib/admin-guard.tsx:88-95`（配合 `(admin)/layout.tsx:1`） | P1 | SSR 零内容：`ready` 在服务端为 false，AdminGuardInner 直接返回「正在校验登录状态…」占位。curl 实测 `/admin/dashboard` SSR HTML 46,949B，正文仅有占位符 div——侧边栏/顶栏/页面内容全部不进 SSR，admin 用户的 LCP ≈ 客户端 JS 加载 + hydrate + 重渲染，首屏闪烁「校验中」 | 静态壳拆服务端组件：品牌区、页脚、菜单结构（`ADMIN_NAV_ITEMS` 本身是纯常量）放服务端布局直接输出 SSR，仅 `children` 内容区挂在客户端守卫后（守卫仍为客户端强制，无安全降级）；架构级可选：token 迁 httpOnly cookie 后用 middleware 做服务端 RBAC，实现完整 SSR。需产品/架构确认 |
| 2 | `src/app/providers.tsx:39` + `src/components/chat/GlobalChatInjection.tsx:28-33`（既有根 providers，直接影响管理端） | P1 | 管理端误引入大库：GlobalChatInjection 挂在根 providers，所有 `/admin/*` 页面都静态加载完整 chat 栈（ChatPanel → ChatMessageBubble → react-markdown/remark/micromark/unified/mdast/hast）。Playwright 实测管理端首载含 1,123,251B（dev raw）markdown 生态 chunk；且 admin 登录后 `useChatSessions({enabled: authed})` 会在管理端页面发起 chat sessions API 请求（额外数据开销） | 管理端路由组（或根布局按 pathname）不挂 GlobalChatInjection；或 ChatPanel 改 `next/dynamic` 按需加载（浮动按钮点击后再拉 chat 栈） |
| 3 | `src/lib/admin-guard.tsx:63` | P2 | `useAuthStore()` 无 selector 全量订阅整个 store，任何 store 字段变更（token/me/tenantId/ready）都重渲染守卫组件 | 拆三条 selector：`useAuthStore((s) => s.ready)` / `(s) => s.token` / `(s) => s.me`（AdminShell 已示范正确写法，layout.tsx:45-46） |
| 4 | `src/lib/admin-guard.tsx:37-48` | P2 | Suspense 边界过宽：包裹整个 AdminShell + children，任何子页面 suspense（如未来使用 useSearchParams 的页面）都会让整壳回退到「正在校验登录状态…」占位（文案误导 + 整树卸载视觉） | 收窄边界：仅包 `AdminGuardInner`（它才是 useSearchParams 的使用者），children 留在边界外 |
| 5 | `src/app/(admin)/layout.tsx:63-68` | P2 | handleLogout 冗余跳转：`logout({silent:false})` 内部已 `window.location.href` 整页跳转（auth-client.ts:328），后续 `router.replace` / `router.refresh` 为无效调用（整页导航已发生） | 保留单一跳转路径：用 `logout({silent:true})` + `router.replace`，或直接依赖 logout 的整页跳转并删掉多余两行 |
| 6 | `src/app/(admin)/layout.tsx:1` | P2 | 整布局 `"use client"`：品牌区、版权页脚等纯静态内容也被客户端化，无法静态化/服务端缓存 | 与 #1 合并：静态部分下沉服务端组件，客户端仅保留需要 pathname/state 的导航区与守卫 |

## 守卫与布局审计

**AdminGuard 整树包裹 → 全量客户端渲染（确认，P1 #1）**
- SSR 链路：layout → AdminGuard → AdminGuardInner，`ready=false`（zustand 初始态）→ 直接返回占位符。实测 `/admin/dashboard` SSR 输出仅含占位 div + scripts，壳与内容均不在 HTML 内。
- 服务端响应本身快：TTFB 78ms、200，无构建级拖累；瓶颈在「首屏内容要等 hydrate 后才有」。
- 安全模型不受影响：守卫仍是客户端强制（后端 `/api/admin/*` ADMIN-only 为权威契约），推荐改造（SSR 静态壳）不暴露任何数据，可安全落地。

**Suspense 边界（P2 #4）**：位置正确（useSearchParams 必须挂 Suspense，代码有注释说明），但半径过大，fallback 语义错位。

**admin-nav 菜单计算（通过）**
- `filterAdminNav(me?.roles)` 已包 `useMemo`（layout.tsx:49），`ADMIN_NAV_ITEMS` 为模块级常量、admin 角色时返回同一引用；无每次渲染重复计算问题。
- 面包屑 `useMemo` 依赖 `[pathname]` 正确；`CRUMB_LABELS` 模块级常量。
- AdminShell 的 zustand selector（`s.me` / `s.logout`）写法正确（对比 #3 中守卫组件未用 selector）。

**重渲染**：壳组件的重渲染来源 = pathname 变化（必须，激活态/面包屑）+ me 变化（selector 已隔离）；6 个菜单项为轻量 Link，无 memo 必要也无 props 稳定性问题。顶栏/侧边栏无明显重复渲染风险。

## 包体审计

| 项 | 结果 |
|----|------|
| ECharts 进管理端？ | **否**。`echarts` 仅在 user 端 learning/dashboard/curriculum 图组件（SessionSidebar/ProgressTrendChart/AbilityRadarChart/CourseMindmapView），`(admin)` 路由组与 `components/admin/*` 零引用；dashboard 壳（MetricCards）用 lucide + Card，无图表库 |
| 管理端大库泄漏 | **是（P1 #2）**：根 providers 的 GlobalChatInjection 把 react-markdown/remark/micromark 生态（实测 1,123KB dev raw chunk）+ chat 全套 hooks 拖入所有 `/admin/*` |
| 管理端自身依赖 | 轻量：next/link、next/navigation、lucide-react 图标（按名导入可 tree-shake）、sonner、shadcn Button（base-ui）、zustand、axios（254KB dev raw）——无问题 |
| dashboard 数据链 | `page.tsx → MetricCards → lib/api/admin/users.getDashboardMetrics → adminGet`（task02 骨架），纯 axios，无重依赖，链路健康 |
| 生产体积 | **未测量**（dev server 占用 `.next`，未跑 `next build`）。dev 模式首载 JS ≈ 8.7MB raw（未压缩 + 含 next-devtools 864KB / ReactQueryDevtools 756KB，两者仅 dev 存在），不具备生产参考意义，仅用于相对比较（markdown 栈占比 ≈ 13%） |

## 数据获取与 Query 配置审计

- `api/admin.ts` 骨架：**不吞错**。GET/POST/PATCH/DELETE 一律向上抛 `ApiError`，`toAdminErrorBody` 归一化错误壳；无 catch 空态冒充成功，符合画像 forbidden 红线「不得新增 catch 返回空态吞错」。admin/users.ts（task03 复用）同样走骨架。✅
- 骨架为纯函数层（无 useQuery），staleTime 由调用方配置；全局默认合理：`staleTime 30s / gcTime 5min / refetchOnWindowFocus:false / 4xx 不重试、5xx 重试 1 次`（query-client.ts:29-41）；MetricCards 用 60s。✅
- 管理端登录态下会随页面加载触发 chat sessions 请求（来自 #2 的 GlobalChatInjection），属额外数据开销，归入 P1 #2。

## 静态校验结果

| 检查 | 结果 |
|------|------|
| `npx tsc --noEmit`（edu-frontend） | ✅ **通过**，0 错误 |
| `npm run lint`（task02 范围 6 文件，eslint 定向） | ✅ **0 error / 0 warning**（exit 0） |
| `npm run lint`（全仓库） | ⚠️ 26 errors + 26 warnings，**全部位于 task02 范围外**（`(user)/courses/search`、`(user)/me`、`components/learning/*`、`components/chat/*`、`lib/api/curriculum.ts`、`components/ui/radio-group.tsx` 等既有/后续 task 代码，非本次回归）。其中 `react-hooks/set-state-in-effect`、`no-explicit-any`、`rules-of-hooks` 与性能相关，建议后续 task 波处理 |
| vitest（admin-guard.test.tsx，server-info 记录） | ✅ 8/8 passed（55ms） |

## 结论

fx-task02 管理端骨架（守卫/布局/导航/API 层）代码质量健康：菜单计算已 memo、错误不吞、类型与 lint 在范围内零问题、ECharts 未泄漏。两个 P1 均非 task02 引入的缺陷，而是**既有架构（根 providers 挂 chat）与守卫设计（全客户端渲染）对管理端的性能代价**，建议在管理端迭代波内处理：

1. **优先（P1 #2，改动小收益大）**：管理端路由组隔离 GlobalChatInjection / ChatPanel 动态化 —— 一次改动同时消掉包体泄漏 + 管理端多余 chat 请求。
2. **计划内（P1 #1）**：静态壳下沉服务端组件，管理端 SSR 至少输出品牌+菜单结构，LCP 从「hydrate 后」提前到「HTML 解析即见」。
3. P2 四项（selector 拆分、Suspense 收窄、logout 冗余、布局 client 化）随下一次管理端改动顺手清理。

## 可测指标

- 首屏 bundle（dev 实测，生产未测量）：`/admin/dashboard` 首次导航 JS 传输 ≈ **8,746 KB raw**（31 chunks）；其中 markdown 生态 chunk ≈ 1,123 KB（≈13%），next-devtools + ReactQueryDevtools ≈ 1,621 KB（仅 dev）
- ECharts 管理端引用数：**0**（全部在 user 端）
- 路由懒加载数量（`(admin)` 内 `dynamic()`）：0（管理端目前无大组件需懒加载；chat 栈经 providers 泄漏属 #2）
- 重渲染风险组件：AdminGuardInner（#3 全量 store 订阅）→ 修复后 0
- SSR 内容覆盖：管理端页面 SSR 正文内容 ≈ 0%（仅占位符，P1 #1）；TTFB 78ms
- 静态校验：tsc 0 错误；task02 范围 eslint 0/0；全仓库 26 errors（范围外）
