# 对抗性测试报告 Task02

## 第 1 次测试

### 判定：FAIL

- 测试时间：2026-08-12
- 测试范围：`src/app/(admin)/layout.tsx`、`src/lib/admin-guard.tsx`、`src/lib/admin-nav.ts`、`src/lib/api/admin.ts`、`src/lib/api-client.ts`（联动）、`edu-agent/app/auth/dependencies.py`（后端实测）
- 实测环境：后端 8000 运行中（/health 200）、`edu-agent/.env:4 DEBUG=true`、前端 3000 dev 运行中

---

## 一、实测证据（非臆造）

| # | 攻击动作 | 实测结果 | 结论 |
|---|----------|----------|------|
| A1 | 无任何 Authorization/X-Force 头 `GET /api/admin/users` | **200**，返回 46 条用户（含 email/手机号字段） | DEBUG 绕过实锤（薄弱点 1） |
| A2 | 带 `X-Force-Role: student` 访问 `/api/admin/users` | 403 | force 伪造在 DEBUG 下生效 |
| A3 | 带 `X-Force-Role: manager` 访问 `/api/admin/users` | **403** | **manager 后端无任何管理端点权限** |
| A4 | 带 `X-Force-Role: admin` 访问 `/api/mcp/servers` | 200（3 个 MCP server 列表） | MCP 工具信息可无凭据拉取 |
| A5 | 无头 `GET /api/auth/me` | 200，`role:"admin"` 虚拟管理员 | DEBUG 下 me 接口返回伪 admin |
| A6 | 无 JS 直接 `GET http://127.0.0.1:3000/admin/dashboard` | **200**（55KB HTML，仅守卫占位符，无侧边栏/管理数据） | 无 middleware，SSR 无 302、无内容泄漏 |
| A7 | `GET /admin/courses`（task03 未建页面） | 404，无泄漏 | fallback 安全 |
| A8 | `GET /admin`（根路径） | 404，无泄漏 | 安全 |
| A9 | 前端单测（admin-nav/admin-guard/api-admin/admin-layout 4 文件） | 34/34 通过 | 既有测试全绿（但固化错误契约，见 #2） |

---

## 二、问题清单

| # | 维度 | 严重度 | 位置 | 质疑 | 可能后果 | 建议 |
|---|------|--------|------|------|---------|------|
| 1 | 架构级（DEBUG 鉴权绕过） | 严重 | `edu-agent/.env:4` DEBUG=true；`edu-agent/app/auth/dependencies.py:80-127`（无 token 即虚拟 admin）；`edu-agent/app/main.py:141` CORS `allow_origins=["*"]`；前端无对应缓解 | A1 实锤：**无凭据直接拉取 46 条用户数据**。DEBUG=true + CORS `*` + 无鉴权三件套组合后，**任意网页/脚本可直接跨域读取 127.0.0.1:8000 的 46 个管理端端点**（用户 PII、MCP 工具、RAG 全库）。task02 前端仅 token 守卫一条防线，无 middleware、无 me 角色一致性校验、无启动自检，对 DEBUG 绕过零缓解。A6 证明前端守卫是纯 CSR，拦不住直连 | 管理端全部数据 + 用户 PII 无凭据可读；恶意网页（CORS *）可静默窃取本地管理数据 | ① 生产部署必须 DEBUG=false（本轮红线 1 禁止改后端，但需作为上线门槛强制检查）；② 后端 CORS 至少收紧到 `http://localhost:3000`；③ 前端可加 middleware 服务端校验 + 管理端守卫校验后端 me 角色与 JWT 一致性（防 DEBUG 虚拟 admin 数据被 UI 渲染） |
| 2 | 架构级（RBAC 契约不一致） | 严重 | 前端 `admin-guard.tsx:77` `isAdminRole` 放行 admin+manager；`admin-nav.ts:23` `ADMIN_ALLOWED_ROLES=["admin","manager"]`；后端 `user_admin/router.py:23`、`course_admin/router.py:41`、`question_admin/router.py:30`、`rag_admin/router.py:44`、`mcp/router.py:36` **全部 `require_role([ADMIN])`** | 前后端契约不一致：前端放行 manager 并渲染 5 个菜单（仪表盘/课程/题库/用户/RAG），但 A3 实测 manager 访问任意一个管理端点即 403。**manager 登录后看到全部菜单、点击即错误壳**，与"Given admin/manager 登录 → 渲染 6 菜单"验收标准只验证渲染、未验证数据可用性（验收标准盲区）。单测 admin-guard.test.tsx:132 与 admin-nav.test.ts:19 已把错误契约固化 | manager 用户体验 = 全菜单 403 白忙；管理端对 manager 形同虚设；验收标准"manager 可访问管理端"隐含承诺无法兑现 | 统一契约二选一：① 后端 course/user/question/rag 放开 `require_role([ADMIN, MANAGER])`（与 design-guide §4.7 暗示"仅 MCP admin-only"对齐）；② 或前端守卫收紧为仅 admin + 菜单 6 项全 admin-only，并在 dev-plan 验收标准中删除 manager 访问管理端的措辞。二选一必须落到代码，不能停在文档 |
| 3 | 验收标准盲区（302 语义） | 一般 | `admin-guard.tsx:61-81`（CSR `router.replace`）；项目根无 `src/middleware.ts`；`next.config.ts` 无配置 | 验收标准"未登录访问 /(admin)/dashboard → **302** 跳转登录页"字面未满足：A6 实测无头请求返回 **200**（HTTP 语义无跳转），重定向纯客户端发生。当前 dashboard 为占位页无数据泄漏，但 task03/04 页面接入数据后，若未来任何页面在 SSR 侧执行数据获取（如 RSC/缓存策略变更），200 语义将成为数据泄漏通道 | 无头客户端/爬虫/搜索引擎永远拿到 200（占位或未来真实页面）；HTTP 语义与验收标准不符 | 在 middleware 层做服务端守卫（NEXT 16 若支持）或明确验收标准为 CSR 重定向（推荐后者，成本低）；task03/04 接入数据时强制用 `useQuery` 且守卫放行前禁止 SSR 数据请求 |
| 4 | 安全（open redirect） | 一般 | `LoginForm.tsx:30` 与 `protected-route.tsx:130` 同款正则 `^\/[A-Za-z0-9?=&/%\-_@+.~#]*$` | 该正则允许 `//evil.com`（`/`、`.` 均在字符集内且 `^\/` 后可直接再 `/`）。用户访问 `/login?redirect=//evil.com` 登录后 `router.replace("//evil.com")` 按协议相对 URL 解析 → **跳转外域**。虽为既有代码（task02 前的 login 页），但管理端未登录回跳链路（AdminGuard → `/login?redirect=...`）正消费同一参数，属本轮守卫链路的相邻攻击面 | 钓鱼：诱导 admin 登录后跳转仿冒站点回填凭据；redirect 参数成为外部跳转开关 | 校验拒绝以 `//` 开头（或协议相对）的值；建议改为白名单前缀 `^/(admin\|user\|dashboard\|login\|register)` 之类 |
| 5 | 错误壳（网络错误伪装） | 轻微 | `api-client.ts:129` `new ApiError(status \|\| 500, ...)`；`admin.ts:52` `toAdminErrorBody` 原样透出 | 断网/连接拒绝时 `status=0` 被替换为 500，调用方（toast）显示"后端 500"而实际是网络断开，与后端真实 500 无法区分，误导排障 | 错误归因错误：运维按后端 500 排查实际是本地断网 | 网络错误保留 `status:0` 并在 message 注明"网络错误/连接失败"；或 toAdminErrorBody 对 status=0 输出专门文案 |
| 6 | 防御正确性（force 优先级） | 轻微 | `dependencies.py:80` force 校验位于 Authorization 校验**之前** | 携带合法 JWT + `X-Force-Role: admin` 时返回虚拟 admin 而非 JWT 真实用户（DEBUG-only）。前端已 grep 确认不发送该头，风险面仅限直连调用者 | 已登录用户被 X-Force-Role 顶替身份（DEBUG 环境）；与"规则 1：带 Authorization 强制真实校验"的注释意图相悖 | 建议 force 分支放在 Authorization 校验之后（仅在无 Authorization 时生效），与 dependencies.py:71 注释语义对齐 |

---

## 三、薄弱点核查清单（design-guide §7）

| design-guide 薄弱点 | 防御证据 file:line / 实测 | 结论 |
|---|---|---|
| 1 DEBUG 鉴权绕过 | 无有效防御。A1/A4/A5 实测无凭据直取管理数据；前端仅 CSR token 守卫，无 middleware/一致性校验 | **未防御（严重，问题 #1）** |
| 2 前端静默吞错（R-7） | `api/admin.ts:22-43` 四个封装全部无 catch、失败向上抛 ApiError；`admin.test.ts:56-109` 覆盖 403/500 透出；`api-client.ts:84-129` 对 HTML/纯文本/422 数组/标准壳四类错误体兜底归一 | 已防御（骨架层），task03/04 页面消费层待 task03/04 对抗验证 |
| 3 聊天路径不匹配（R-1） | 不在本轮范围（task05） | 不适用 |
| 4 DELETE 会话缺失（R-2） | 不在本轮范围（task05） | 不适用 |
| 5 文档口径漂移（R-9） | 本轮新发现**反向漂移**：design-guide §4.7/§2.3 与 dev-plan 验收标准暗示 manager 可访问管理端（仅 MCP admin-only），后端实测全部端点 ADMIN-only（问题 #2） | 漂移（严重，问题 #2） |

---

## 四、核查通过项（防御有效，供参考）

- student/teacher/未知角色/roles 缺失：守卫拦截 + toast + 重定向 `/dashboard`（单测 + 逻辑双重确认），无白屏（hydrate 占位）
- 未登录：`/login?redirect=%2Fadmin%2Fdashboard` 编码正确（单测断言 `admin-guard.test.tsx:94`），登录后 LoginForm 读取回跳
- 角色归一化多态：`auth-client.ts:66-116` `_normalizeUser` 兼容 `role` 字符串 / `{value}` / `role_code` / `roles[]`，大小写不敏感（`admin-nav.ts:51-53`）
- MCP 菜单 admin-only：`filterAdminNav` 正确（admin 6 项 / manager 5 项）
- SSR 无泄漏：A6 实测 SSR HTML 仅守卫占位，无侧边栏/管理数据
- 未匹配路由 fallback：/admin、/admin/courses 404 无泄漏（A7/A8）
- 路由冲突：/admin/* 与用户端 /dashboard /courses 无 URL 冲突（admin-nav.test.ts:82-86 契约 + 实测）
- 退出登录：logout 清 token 后守卫 useEffect 重跑拦截，与 handleLogout 双保险
- toast 可用：`providers.tsx:40` Toaster 已挂载

---

## 五、结论

FAIL：存在 2 个严重级问题（#1 DEBUG 鉴权绕过前端零缓解、#2 前后端 RBAC 契约不一致 manager 全菜单 403），1 个验收标准盲区（#3 302 语义），1 个安全弱点（#4 open redirect），2 个轻微项。其中 #2 属 task02 前端产物与后端的直接契约冲突，需在本轮修复；#1/#3 属既有后端/基线约束，建议上报主 Agent 作为上线门槛与后续迭代项。

---

## 六、修正处置结论（2026-08-12 修正轮，sd-dev）

| # | 处置结论 | 落地 |
|---|----------|------|
| 1 | **不修后端（红线 1）**。DEBUG 鉴权绕过为后端既有设计（dependencies.py 无 token 即虚拟 admin）+ CORS `*`（main.py:141），本轮禁止改动。上线硬门槛：`.env` DEBUG=false（explore R-3）；CORS 生产收紧待后端迭代。前端已加注释说明（admin-guard.tsx 头部），提示该风险存在 | 注释说明 |
| 2 | **后端 ADMIN-only 为权威契约，前端已对齐（必修）**。后端 user/course/question/rag/mcp 五个 router 全部 `require_role([ADMIN])`，manager 实测 403 → 前端收紧为仅 admin：`ADMIN_ALLOWED_ROLES=["admin"]`、`filterAdminNav` 非 admin 渲染 0 项、AdminGuard 仅 admin 放行（manager/teacher/student 一律拦截 + toast + 重定向 /dashboard）。同步更新 admin-nav.test.ts / admin-guard.test.tsx / admin-layout.test.tsx 断言。dev-plan 验收标准「manager 访问管理端」措辞已标注为不符合后端契约并收紧 | 代码 + 测试 + dev-plan 标注 |
| 3 | **不修（302 语义）**。验收标准明确为 CSR 重定向（AdminGuard `router.replace`），middleware 方案不采用（Next 16 该机制与现有 CSR 守卫体系不匹配，且 A6 实测无内容泄漏）；task03/04 页面接入数据时强制 `useQuery` 且守卫放行前禁止 SSR 数据请求 | 维持现状 |
| 4 | **已修（open redirect）**。新增 `lib/redirect.ts` `isSafeRedirect`：拒绝以 `//` 或 `/\` 开头的协议相对路径（`^\/(?![/\\])` 负向前瞻），LoginForm / protected-route（GuestOnlyRoute）/ 根路由 page.tsx 三处统一接入，消除复制正则漂移；单测覆盖 `//evil.com`、`/\evil.com`、`/admin/dashboard`、`/login` 四例 + 外域 URL/伪协议/空值边界 | 代码 + 单测 |
| 5 | **已修（网络错误伪装）**。api-client 响应拦截器对无响应体（status=0，断网/连接拒绝/超时）输出明确文案「网络错误，无法连接后端服务，请检查网络」/「请求超时…」，`new ApiError(status || 500)` 改为保留 status=0（不再伪装 500）；toAdminErrorBody 对 status=0 透出明确文案。新增 api-client.test.ts + admin.test.ts 用例 | 代码 + 单测 |
| 6 | **不修（force 优先级）**。dependencies.py force 校验先于 Authorization 为后端既有 DEBUG 行为，属红线 1 范围；前端已确认不发送 X-Force-Role 头，风险面仅限直连调用者（DEBUG 环境） | 维持现状 |
