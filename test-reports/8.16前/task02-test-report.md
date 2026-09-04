# 功能测试报告 Task02

## 第 1 次测试

### 判定：PASS

验收标准（dev-plan.md task02）逐条核对通过，详见下方运行记录。薄弱点命中仅记录，不构成 FAIL。

---

### 测试环境

| 项 | 值 |
|---|---|
| 前端 | edu-frontend（Next.js 16 dev server http://localhost:3000，测试时启动） |
| 后端 | edu-agent（http://localhost:8000 运行中，`/health` 200，`.env DEBUG=true`） |
| 测试框架 | Vitest 4.1.10 + @testing-library/react；Playwright 1.62.1（chromium） |
| 测试账号 | stu02test/Test@123456(student,user_id=847)、adm02test/Test@123456(admin,848)、mgr02test/Test@123456(manager,849)（注册后用 X-Force-Role 改角色，见薄弱点 #1） |

### 1. 单元测试（`npx vitest run`）

结果：**9 个测试文件 65 例全部通过**（5.91s）。task02 新增 4 个测试文件全绿：

| 测试文件 | 用例数 | 覆盖验收 |
|---|---|---|
| src/lib/admin-nav.test.ts | 12 | RBAC 菜单过滤：admin 6 项、manager/student 5 项、MCP 仅 admin、大小写不敏感 |
| src/lib/api/admin.test.ts | 10 | 403/500 → `{code,message,detail}` 壳透出不吞错；写操作失败必抛 |
| src/lib/admin-guard.test.tsx | 8 | student/teacher 拦截 + toast + 重定向；未登录跳登录页带 redirect；hydrate 占位 |
| src/lib/admin-layout.test.tsx | 4 | 真实 AdminLayout：admin 6 菜单/manager 5 菜单/student 拦截/未登录跳转 |

（既有 task01 测试 31 例同样全过，无回归。）

### 2. 浏览器验证（Playwright，真实登录）

| # | 场景 | 结果 | 说明 |
|---|------|------|------|
| 1 | 未登录访问 /admin/dashboard | ✅ PASS | 跳 `http://localhost:3000/login?redirect=%2Fadmin%2Fdashboard`，登录页可见。HTTP 层为 200 + 客户端守卫跳转（layout 为 "use client"），非服务端 302，URL 与回跳行为等价满足验收 |
| 1b | 登录后回跳原 URL | ✅ PASS | 未登录 → /admin/dashboard → 登录 adm02test → 回跳 /admin/dashboard 且管理端正常渲染 |
| 2 | student 访问 /admin/dashboard | ✅ PASS | toast「无权限访问管理端」出现 → 重定向 /dashboard → 页面完整渲染（bodyLen=1496）无白屏、无校验占位残留 |
| 3 | admin 访问 /admin/dashboard | ✅ PASS | 侧边栏 6 菜单全部渲染（仪表盘/课程/题库/用户/RAG/MCP），MCP 可见 |
| 4 | manager 访问 /admin/dashboard | ✅ PASS | 侧边栏 5 菜单，无 MCP |
| 5 | student 访问 /admin/courses（页面未建） | ✅ PASS | 页面未建（task03 才建），Next.js 404 兜底，**不渲染管理端壳**，无信息泄露；守卫拦截行为由场景 2 实测 + admin-guard/layout 单测覆盖 |

### 3. admin API 403/500 错误壳

- **后端实际触发**：student token（stu02test）调 `GET /api/admin/users` → **403**，响应体 `{"code":40300,"message":"角色无权限。当前角色=student，允许角色=['admin']","detail":"角色无权限…"}` —— `{code,message,detail}` 壳成立。
- **前端透出**（单测）：admin.test.ts 验证 403（40300/FORBIDDEN/detail）与 500（50000/INTERNAL_SERVER_ERROR）均以 ApiError 四字段 `{status,code,message,detail}` 抛给调用方，不静默吞错；`src/lib/api/admin.ts` 骨架无 `catch 返回空态` 路径，写操作（POST/PATCH/DELETE）失败一律抛。

### 4. 代码审查要点

- **接口契约**：`admin-guard.tsx` 使用 `useAuthStore` 的 `{ready, token, me}`，与 `auth-client.ts` 实际暴露一致；`me.roles` 经 `_normalizeUser` 归一为 `role_code` 字符串数组，`admin-nav.ts` 的 `normalizeRole`（trim+lowercase）兼容大小写。
- **错误处理**：`useSearchParams` 包在 Suspense 边界内（Next.js 16 约束），hydrate 完成前显示「正在校验登录状态…」占位，无白屏。
- **路由隔离**：6 个菜单 href 均为 `/admin/*` 前缀，与用户端 `/courses`、`/dashboard` 隔离。
- **dashboard 占位壳**：`page.tsx` 为 task03 预留 6 指标卡占位（标注 task03 填充），无 API 调用，符合 dev-plan 文件范围对照。

### 架构薄弱点验证结果

| # | 薄弱点 | 是否命中 | 说明 |
|---|--------|---------|------|
| 1 | DEBUG 鉴权绕过（dependencies.py:80-127） | ⚠️ 部分命中 | 后端既有特性（task02 无后端改动）：本次测试借用 `X-Force-Role: admin` 准备 admin/manager 账号，证实其可伪冒角色。**前端守卫不受影响**：实测场景 1 未登录用户被重定向登录页，守卫基于真实 JWT 登录态（token + me.roles），X-Force-Role 仅作用于后端 API 不进入前端 auth store。深层威胁面（无 Token 直调管理端端点）属后端既有问题，交 sd-challenger 深挖 |
| 2 | 前端静默吞错（R-7） | ✅ 未命中 | task02 范围内 api/admin.ts 骨架显式不吞错（单测覆盖 403/500 抛错）；dashboard 占位壳无查询无吞错路径 |
| 3 | 聊天路径不匹配（R-1） | 不适用 | task05 范围，task02 代码未涉及 `/messages`/`/history` |
| 4 | DELETE 会话缺失（R-2） | 不适用 | task05 范围，task02 无会话删除代码 |
| 5 | 文档口径漂移（R-9） | ✅ 未命中 | task02 的 admin.ts 为通用骨架（adminGet/adminPost/adminPatch/adminDelete 传 path），未写死任何具体端点路径，无漂移点 |

### 观察项（非阻断）

- 验收标准字面「302 跳转登录页」在实现中为 **200 + 客户端守卫跳转**（layout 为 "use client"，`router.replace`）。用户可见行为（跳转 + redirect 回跳）与验收意图一致，记录不判 FAIL；如后续要求 HTTP 层真 302 需改服务端 middleware，属可选优化。
- student 访问 `/admin/courses` 当前为 404 兜底而非守卫拦截（页面未建）；task03 建页后守卫将自动生效（单测已覆盖该路径）。

### 结论

4 条验收标准全部满足，无阻断性缺陷。薄弱点 #1 命中（后端既有 DEBUG 特性）已记录，交 sd-challenger 对抗验证。

---

## 第 2 次测试（复测：对抗 #2/#4/#5 修正回归）

### 判定：PASS

| # | 上次问题（挑战报告） | 当前状态 | 证据 |
|---|----------------------|---------|------|
| 1 | #2 RBAC 契约不一致（前端放行 manager、后端 403） | ✅ 已修复 | `admin-nav.ts:26` `ADMIN_ALLOWED_ROLES=["admin"]`；`filterAdminNav` 非 admin 渲染 0 项；`admin-guard.tsx:81` 仅 admin 放行（manager/teacher/student 一律拦截）。单测全绿：admin-nav.test.ts（manager→0 菜单、`Manager` 大小写不放行）、admin-guard.test.tsx:116（manager 拦截+toast+重定向 /dashboard）、admin-layout.test.tsx:91（真实 AdminLayout manager 拦截） |
| 2 | #4 open redirect（redirect 正则允许 `//evil.com`） | ✅ 已修复 | 新增 `lib/redirect.ts` `isSafeRedirect`（正则 `^\/(?![/\\])...` 拒绝 `//`/`/\` 协议相对路径），LoginForm / protected-route（GuestOnlyRoute）/ 根路由统一接入。redirect.test.ts 8 例全绿：`//evil.com`、`/\evil.com`、外域 URL、`javascript:` 伪协议、空值全部拒绝；`/admin/dashboard`、`/login`、带 query/hash 站内路径放行 |
| 3 | #5 网络错误 status=0 伪装成 500 | ✅ 已修复 | `api-client.ts:86-93` 无响应体 → status 保留 0 + 明确文案「网络错误，无法连接后端服务，请检查网络」/「请求超时…」（不再 `status \|\| 500`）；`admin.ts:50-54` `toAdminErrorBody` 对 status=0 透出专门文案。api-client.test.ts 3 例（ERR_NETWORK→status=0+文案、ECONNABORTED→超时文案、非 500 断言）+ admin.test.ts:123 用例全绿 |

### 测试环境

| 项 | 值 |
|---|---|
| 前端 | edu-frontend（Next.js 16.3.0 dev server http://localhost:3000，测试期间为清理 `.next` 后重启的干净实例） |
| 后端 | edu-agent（http://127.0.0.1:8000 运行中，`/health` 200，账号 adm02test/mgr02test 登录均正常） |
| 测试框架 | Vitest 4.1.10 + @testing-library/react；Playwright-core 1.62.1（chromium headless shell，浏览器抽查用 `http://localhost:3000`） |

### 1. 单元测试（`cd edu-frontend && npx vitest run`）

结果：**11 个测试文件 77 例全部通过**（5.95s）。较第 1 轮（65 例）新增：redirect.test.ts 8 例 + api-client.test.ts 3 例 + admin.test.ts 1 例（status=0 用例），全部全绿；task01 既有用例无回归。

| 测试文件 | 用例数 | 覆盖修复项 |
|---|---|---|
| src/lib/admin-nav.test.ts | 12 | #2 manager 0 菜单 / 大小写 / 混合角色 |
| src/lib/admin-guard.test.tsx | 8 | #2 manager/teacher/student 拦截、admin 放行 |
| src/lib/admin-layout.test.tsx | 4 | #2 真实 AdminLayout manager 拦截重定向 |
| src/lib/redirect.test.ts | 8 | #4 `//evil.com` 拒绝、`/admin/dashboard` 放行等 |
| src/lib/api-client.test.ts | 3 | #5 status=0 网络文案、超时文案、非 500 |
| src/lib/api/admin.test.ts | 11 | #5 toAdminErrorBody status=0 透出 |

### 2. 浏览器抽查（Playwright 真实登录，`http://localhost:3000`）

| # | 场景 | 结果 | 说明 |
|---|------|------|------|
| 1 | admin（adm02test）访问 /admin/dashboard | ✅ PASS | 停留 /admin/dashboard，侧边栏 6 菜单（仪表盘/课程/题库/用户/RAG/MCP）全部渲染，MCP 可见 |
| 2 | manager（mgr02test）访问 /admin/dashboard | ✅ PASS | 被守卫拦截：toast「无权限访问管理端」出现，重定向 /dashboard，管理端侧边栏不渲染（与后端 ADMIN-only 契约一致） |

### 3. 代码审查要点（修复落地核对）

- **RBAC 收紧**：admin-nav.ts 放行集合与后端 `require_role([ADMIN])` 完全一致，消除了"manager 见菜单即 403"的契约冲突。
- **redirect 统一**：三处使用方（LoginForm.tsx:23,31 / protected-route.tsx:7,131 / 根路由）统一接入 `isSafeRedirect`，不再复制正则；`^\/(?![/\\])` 负向前瞻阻断协议相对路径。
- **网络错误归因**：status=0 全链路保留（拦截器→ApiError→toAdminErrorBody），toast 可显示"网络错误/超时"而非误导性"后端 500"。

### 架构薄弱点验证结果（本次复测范围）

| # | 薄弱点 | 是否命中 | 说明 |
|---|--------|---------|------|
| 1 | DEBUG 鉴权绕过（后端既有） | ⚠️ 已记录（挑战 #1 处置：不修后端，前端注释说明） | 本轮未涉及后端改动，维持第 1 轮结论 |
| 2 | 前端静默吞错（R-7） | ✅ 未命中 | admin 骨架与 api-client 不吞错，本轮单测强化覆盖 |
| 3 | 聊天路径不匹配（R-1） | 不适用 | task05 范围 |
| 4 | DELETE 会话缺失（R-2） | 不适用 | task05 范围 |
| 5 | 文档口径漂移（R-9） | ✅ 已对齐 | 挑战 #2 处置后前端 RBAC 与后端 ADMIN-only 契约一致，dev-plan 验收措辞已标注收紧 |

### 环境备注（非代码缺陷）

浏览器抽查初期页面卡「跳转中…」、按需 chunk 403，排查后确认为测试脚本自身使用 `http://127.0.0.1:3000` 访问所致：Next dev server 的 DNS rebinding 防护（allowedDevOrigins）对带 `Origin: http://127.0.0.1:3000` 的请求返回 403（`Origin: http://localhost:3000` 则 200，已用 HTTP 复现对照）。改用 `http://localhost:3000`（与第 1 轮测试一致）后浏览器抽查全部通过。**不属于被测代码缺陷**，未记 FAIL。

### 结论

对抗 #2/#4/#5 三项修复全部落地并通过单测（77/77）+ 浏览器抽查（2/2）；dev-plan task02 4 条验收标准继续满足，无阻断性缺陷。薄弱点 #1（后端 DEBUG 特性）维持第 1 轮记录，交 sd-challenger 上线门槛跟踪。
