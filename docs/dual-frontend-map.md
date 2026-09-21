# 双前端对账表：React 壳 vs 26 页黏土静态页（AUTO20 T11）

> 生成：2026-09-22 ｜ 分支 feature/opt-waves ｜ 证据基线：本仓 HEAD 工作区实测 + `test-reports/feat-wire-v2/matrix/wiring-matrix.json` + `http://127.0.0.1:9988/openapi.json`（2026-09-22 实时抓取）
> 结论一句话：**两套前端同住在 3322 一个 Next 服务器上——`/xxx` 是 React 路由，`/xxx.html` 是黏土静态页；日常演示与全功能走静态页，React 用户端/管理端已大部分真实接线但缺 3 个页面且有 3 条死链。**

---

## 1. 入口说明（哪个 URL 是谁）

| URL 形态 | 归属 | 事实依据 |
|---|---|---|
| `http://127.0.0.1:3322/` | **React 根路由**，`useEffect` 里 `router.replace("/login-register.html")` 直接踢去静态登录页 | `edu-frontend/src/app/page.tsx:15` |
| `http://127.0.0.1:3322/<name>`（无 .html） | **React 路由**（`src/app/(user)/`、`(admin)/`、`admin/users-refine`，共 28 个 page.tsx） | `find src/app -name page.tsx` 实测 28 个 |
| `http://127.0.0.1:3322/<name>.html` | **黏土静态页**（`public/*.html` 26 个文件 + `edu-api.js` 共享客户端） | `ls public/*.html` 实测 26 个 |
| 后端 | `http://127.0.0.1:9988`（uvicorn，`edu-agent/.venv`）；openapi 实测 177 paths / 210 个 HTTP 操作 | 2026-09-22 curl 实测 |
| React→后端 | axios 封装 `src/lib/api-client.ts`（响应壳 `{code:0,data}` 解包 + 401/403 全局回调） | `api-client.ts:1-233` |
| 静态页→后端 | `public/edu-api.js`：JWT + 壳解包 + 401 跳 `.html` 登录页；BASE 级联（默认 `http://127.0.0.1:9988`，同源 3322→9988） | `edu-api.js:1-38` |
| `/media/*` | Next rewrite 反代到后端 9988（视频同源） | `next.config.ts:33-41` |
| 登录后分流 | 静态页按角色：admin/manager→`admin-dashboard.html`，student→`dashboard.html`（`login-register.html:3018`）；**React 登录不分流**，一律 `?redirect` 或 `/dashboard`（`LoginForm.tsx:29-31`，admin 登录 React 会落到用户端仪表盘） | 两处文件行号 |
| 管理端守卫 | React `(admin)/layout.tsx` 统一 `AdminGuard`（仅 admin 放行）；`/admin/users-refine` 在路由组**外**，页面内自带三段守卫 `useRefineGate` | `(admin)/layout.tsx:30-36`、`users-refine/page.tsx:38` |

> 注意：两代前端**共用同一端口同一域名**，差异只在 `.html` 后缀——这就是"点开的前端也许是新风格但 React 没实现"困惑的根源：静态页和 React 页视觉同源（candy 糖果色），用户无法从外观分辨自己身在哪家。

---

## 2. 主对账表（功能域 × React × 静态页 × 后端）

图例：✅=完整实现（真实 API 接线）｜🔶=部分（页内个别板块占位）｜🚧=壳/跳板｜❌=不存在｜🔗=死链

| 功能域 | React 路由（态） | 静态页（wiring 实测） | 后端端点（openapi 实测） | 对账结论 |
|---|---|---|---|---|
| 登录/注册 | `/login` ✅ `/register` ✅（auth-client `POST /api/auth/login`:215、`register`:245；GuestOnlyRoute） | `login-register.html` ✅（matrix 5 wired/0 dead；角色分流 ：3018） | `/api/auth/*` 4 ops（login/register/me/refresh） | **双端都在用，静态页是实际主入口**（`/` 根路由跳它） |
| 学习仪表盘 | `/dashboard` ✅（16 处 API 引用：progress/gamification/community，`page.tsx:115-171`） | `dashboard.html` ✅（12 wired/0 dead） | `/api/progress` 5 + `/api/gamification` 5 | 双端完整 |
| 课程中心 | `/courses` ✅、`/courses/search` ✅（listSeries，`courses/page.tsx:30-34`） | `courses.html` ✅（35 wired；搜索内嵌） | `/api/series` 3 + `/api/courses` 2 | 双端完整；React 多独立搜索页 |
| 课程详情 | `/courses/[seriesId]` ✅（CourseDetailClient：curriculum+coupons+favorites+orders 四 API 模块，`:44-45`） | `course-detail.html` ✅（23 wired） | `/api/series`、`/api/coupons` 2、`/api/favorites` 3 | 双端完整 |
| 我的班次 | `/my-courses` ✅（`GET /api/enrollments/me/cohorts`，MyCoursesClient） | `my-cohorts.html` ✅（16 wired） | `/api/enrollments` 4 | 双端完整 |
| 学习播放 | `/learning/[seriesId]/[sessionId]` ✅（learning.ts + study.ts，LearningPlayClient 6 引用） | `learning.html` ✅（23 wired） | `/api/study` 4 + `/api/progress` | 双端完整 |
| AI 对话 | `/chat` ✅（ChatCandyClient→chat.ts：sessions/history/SSE `POST /api/chat/stream`，`chat.ts:4-10`） | `chat.html` ✅（31 wired） | `/api/chat` 8 ops（含 stream SSE） | 双端完整（SSE 契约=task104 实测口径） |
| 社区 | `/community` ✅ `/community/[postId]` ✅（listPosts/comments/like/favorite，task51/52） | `community.html` ✅（27 wired）+ `community-post.html` ✅（15 wired） | `/api/community` 9 | 双端完整 |
| 复习中心 | `/practice/[mode]` ✅（wrong-book/topic/vocab 三模式，task49） | `practice.html` ✅（36 wired） | `/api/interactive` 6 + 错题/单词 | 双端完整 |
| 成就中心 | `/achievements` ✅（rankings/points/badges，页头注明"全部真实 API 无 MOCK"） | `achievements.html` ✅（23 wired） | `/api/gamification` 5 | 双端完整 |
| 个人中心 | `/me` ✅（MeHeader/StatCards/StudentProfileForm 均 useQuery；**但功能入口 3 条死链** 🔗） | `me.html` ✅（41 wired，全站最多 API 引用 35） | `/api/users` 5 | React 页本体完整但导航 3 死链（见 §4） |
| 我的订单 | `/orders` ✅（trade/orders + createRefund，task100） | （并入 `me.html` 订单区 + `refund.html`） | `/api/trade` 17 | 双端覆盖（形态不同） |
| **我的优惠券** | ❌ 无路由（API 层 `lib/api/coupons.ts` 已备好但无人消费）🔗 `MeNavList.tsx:30` 死链 | `coupons.html` ✅（18 wired，26 处 API 引用） | `GET /api/coupons/templates`、`GET /api/coupons` ✅ | **静态独占；React 死链** |
| **我的收藏** | ❌ 无独立路由（收藏能力内嵌在 CourseDetailClient）🔗 `MeNavList.tsx:31` 死链 | `favorites.html` ✅（16 wired） | `GET/POST /api/favorites`、`DELETE /{series_id}` ✅ | **静态独占；React 死链** |
| **退款中心** | ❌ 无路由（createRefund 只作为 Orders 弹窗）🔗 `MeNavList.tsx:33` 死链 | `refund.html` ✅（13 wired） | `POST/GET /api/refunds`、`POST /{id}/cancel` ✅ | **静态独占；React 死链** |
| 售后工单 | `/tickets` ✅ `/tickets/[ticketId]` ✅（task100，含满意度评价） | ❌ 无独立页（`me.html:4277` "工单页暂未上线"诚实占位） | `/api/trade/after_sales/tickets` ✅ | **React 领先静态页**（唯一反超项之一） |
| 管理端·仪表盘 | `/admin/dashboard` 🔶（KPI/趋势/角色饼图真实；**热门课程榜=契约缺口占位卡 RankFallback**，`page.tsx:6`） | `admin-dashboard.html` ✅（9 wired，同样无热门榜数据） | `GET /api/admin/users/dashboard/metrics` ✅；admin 全局交易聚合端点**不存在** | 双端同等（后端缺口，双端都诚实占位） |
| 管理端·课程 | `/admin/courses` ✅ `/admin/courses/[seriesId]` ✅（383 行 CRUD+回收站 `?include_deleted=true`；ModuleTree 四级管理） | `admin-courses.html` ✅（120 wired）+ `admin-course-detail.html` ✅（19 wired）+ `admin-courses-recycle-proto.html`（原型） | `/api/admin` 67 ops | 双端完整 |
| 管理端·题库 | `/admin/questions` ✅ `/admin/questions/[id]` ✅（两级题库+批量导入四步） | `admin-questions.html` ✅（15 wired）+ `admin-question-detail.html` ✅（21 wired） | contract④ 端点组 | 双端完整 |
| 管理端·用户 | `/admin/users` ✅（task60：搜索防抖+筛选+分页）；另有实验件 `/admin/users-refine` ✅（refine-layer headless，C15 选型证伪件） | `admin-users.html` ✅（11 wired）+ `admin-users-refine-proto.html`（原型，0 API 引用=纯视觉稿） | `/api/admin/users/*` | 双端完整（React 多一个实验实现） |
| RAG 控制台 | `/admin/rag` ✅（集合/预设/审计/检索测试/**UploadPanel**，task04） | `admin-rag-upload.html` ✅（15 wired，37 处 API 引用） | `/api/admin/rag/*`（67 admin ops 内） | 双端完整 |
| MCP 控制台 | `/admin/mcp` ✅（Server 列表/健康扫描/工具测试/调用日志） | `admin-mcp.html` ✅（18 wired） | `/api/mcp` 25 ops | 双端完整 |
| 会话审计 | ❌ 无 React 路由 | `admin-chat-audit.html` ✅（`EAPI.get /api/admin/chat-audit/sessions`，commit 4aa7bff p05） | `/api/admin/chat-audit/*` ✅ | **静态独占**（matrix 25 页未含它——matrix 摄于该页诞生前） |
| 记忆/个性化 | （chat 内 memobar 组件，无独立路由） | （chat.html 内） | `/api/memory` 3 | 无独立页面，双端一致 |

---

## 3. React 28 路由实现态统计

| 态 | 数量 | 明细 |
|---|---|---|
| **完整实现（真实 API）** | **26** | 用户端 17（login/register/dashboard/courses/search/detail/my-courses/learning/chat/community×2/achievements/me/orders/tickets×2/practice）+ 管理端 9（dashboard/courses×2/questions×2/users/rag/mcp/users-refine） |
| **部分** | **0 个整页**（1 个页内板块：`/admin/dashboard` 热门课程榜=RankFallback 契约缺口占位，禁 MOCK 有据） | `RankFallback.tsx:1-12` |
| **壳/跳板** | **2** | `/`（→静态登录页，`page.tsx:15`）、`/admin`（→`/admin/dashboard`，`admin/page.tsx:14`） |
| **死链（链到不存在的路由）** | **3 条** | `MeNavList.tsx:30,31,33` → `/coupons` `/favorites` `/refunds`（`find src/app -type d` 实证三目录均不存在） |

判定方法：逐 page.tsx grep `useQuery|queryFn|from "@/lib/api|http.post`（28/28 全量过），并追进 `_components` 客户端组件确认真实接线；无 MOCK 数据残留（全仓 grep 佐证：唯一 MOCK 字样均为"无 MOCK"声明）。

## 4. 静态页 26 文件实测（任务书说 25 页的出处）

`wiring-matrix.json`（feat-wire-v2 验收基线）收录 **25 页，601 wired / 0 dead**。实际 `public/*.html` 现有 **26 个**：`admin-chat-audit.html`（commit 4aa7bff，feat-wire-rwk/p05）晚于 matrix 摄制入库，故未在 601 全景内——该页已独立双角色验收（admin 316 会话/student 403），同为真实接线。两个 `-proto` 页（`admin-courses-recycle-proto` 7 other、`admin-users-refine-proto` 17 other+0 API 引用）是**设计原型稿**，非功能面。

## 5. 「用户该用哪个入口」速查（当前答案）

- **日常演示 / 全功能**：静态页。从 `3322/login-register.html` 进（或直接访问 `3322/` 根路由自动跳入）。26 页覆盖含优惠券、收藏、退款、我的班次、会话审计等 React 缺失项；登录后按角色自动分流 admin/manager→admin-dashboard.html、student→dashboard.html。
- **React 壳现状**：路由存在且**绝大多数已真实接线**（26/28），用户端 `/dashboard /courses /learning /chat /community /achievements /me /orders /tickets /practice` 与管理端 `/admin/*` 都可用；但①`/me` 功能入口的优惠券/收藏/退款是**死链**；②React 登录不按角色分流（admin 会被送到用户端 dashboard）；③无会话审计页。
- **两代视觉同源**：React candy 玩法对齐静态页 approved 稿（task46-60 注释逐页声明"对齐 xxx.html"），所以**无法靠长相区分**——看地址栏有无 `.html` 即可分辨。
- **哪个更"新"**：React 侧是 Style3/质变方向（M1 质量门、refine 实验件、Next 16 惯例），但功能完备度暂低于静态页；静态页是已验收的 601-wired 全景演示面。

## 6. 演进建议（React 侧补齐优先级，供未来立项）

| 优先级 | 事项 | 依据（成本/收益） |
|---|---|---|
| **P0** | 补 `/coupons` `/favorites` `/refunds` 三条路由，消灭 `MeNavList` 3 死链 | API 层 `lib/api/coupons.ts / favorites.ts / refunds.ts` 全部现成、后端 7 个端点全就绪、静态页 `coupons/favorites/refund.html` 可作交互蓝本——纯页面工作，零后端改动 |
| **P1** | React 登录按角色分流：admin/manager → `/admin/dashboard` | `LoginForm.tsx:29-31` 现在一律 `/dashboard`；静态页 `login-register.html:3018` 已有正确口径可照抄 |
| **P1** | `/admin/chat-audit` React 化 | 端点已在（p05），静态页已验收；React 管理端壳（AdminGuard+侧边栏）现成，只差一个页面 |
| **P2** | `/me` 功能入口补齐校验测试（死链类回归进 frontend-quality-gate） | 本次 3 死链可被"路由存在性静态检查"机验拦截 |
| **P2** | admin 全局交易聚合端点（`GET /api/admin/trade/overview`）立项后，双端同步摘除 RankFallback 占位 | `RankFallback.tsx:5-7` 已登记"待 task70~91" |
| **P3** | `/admin/users`（task60 版）与 `/admin/users-refine`（B3 实验件）二选一收编 | 两实现并存是有意的 C15 选型证伪设计，但长期应收敛一个 |
| **P3** | 静态页 `me.html` 工单占位摘除（React `/tickets` 已领先） | `me.html:4277` 自述"页面待接"；可在 me.html 挂 `.html` 工单页或直接标注"请用 React 版" |

---

## 7. 证据附录

- React 路由盘点：`find edu-frontend/src/app -name page.tsx` → 28 个；逐文件接线判定见 §3 方法。
- 静态页接线：`test-reports/feat-wire-v2/matrix/wiring-matrix.json`（25 页 601 wired/0 dead）+ `dead-elements.json`（空数组）。
- 后端路由：`curl 127.0.0.1:9988/openapi.json` → 177 paths / 210 ops（按域：admin 67、mcp 25、trade 17、community 9、chat 8、gamification 5、favorites 3、refunds 3、enrollments 4、study 4…）。
- 静态页真实调用清单：`test-reports/_frontend_real_api.txt`（101 条，"每条均在后端 OpenAPI 路由内，零断点"）。
- 关键文件：`edu-frontend/src/app/page.tsx`（根路由跳转）、`edu-frontend/src/components/me/MeNavList.tsx`（死链）、`edu-frontend/public/edu-api.js`（静态客户端）、`edu-frontend/next.config.ts`（media 反代）、`edu-frontend/src/app/(admin)/layout.tsx`（AdminGuard）。
