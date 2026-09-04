# fx-task02 dev server 信息

> 生成：fe-server-infra（补课波·只补产物，未改业务代码）
> 本文件是唯一事实来源：fe-visual-auditor / fe-a11y-auditor / fe-perf / fe-tester 必须读取它连接 server，**不要自行再启动一个 dev server**。

## 基本信息

- framework: Next.js 16.3.0（App Router + Client Components + Turbopack dev）
- 判定来源: profile:nextjs-16-app-router
- confirmLine: Next.js 16 + React 19 + Tailwind v4 + Zustand + TanStack Query + App Router
- port: 3000
- baseUrl（推荐）: **http://localhost:3000**
- baseUrl（仅无 Origin 场景可用）: http://127.0.0.1:3000（见注意事项 #1）
- startedByInfra: true（fe-task01 轮次启动；本任务复用未重启）
- pid: 3780（node，监听 3000，2026-08-13 验证存活）
- 工程目录: edu-frontend
- 启动命令: `npm run dev`（实际 = `next dev`，日志显示 `Ready in 2.4s`）
- 日志文件: `.claude/logs/dev-fe-task01.log`（启动轮次的日志，Next.js 16.3.0 Turbopack）

## 健康检查结果（2026-08-13，curl + Playwright 实测）

| 路由 | HTTP | 说明 |
|------|------|------|
| `/` | 200 | 首页正常 |
| `/admin/dashboard` | 200（SSR） | **RBAC 守卫为客户端行为**：SSR 返回 200 + 占位「正在校验登录状态…」，hydrate 后未登录 → 客户端重定向（curl 看不到 302，属设计内，见注意事项 #2） |
| `/admin` | 404 | 正常：路由组 `(admin)` 不产生 URL 段，管理端真实路径为 `/admin/*` |
| `/admin/dashboard`（浏览器） | 重定向 | Playwright 实测：http://localhost:3000/admin/dashboard → hydrate 后 4s 内自动跳转 `http://localhost:3000/login?redirect=%2Fadmin%2Fdashboard`，并触发 sonner toast「请先登录」——AdminGuard 未登录分支守卫生效 ✓ |
| `/login` | 200 | 登录页完整渲染（账号/邮箱、密码、记住我、登录按钮、免费注册链接、返回首页链接） |
| `/api/*` | 无前端代理 | axios baseURL 直连后端 `http://127.0.0.1:8000/api/...`；未登录请求返回 401「登录凭证无效」属预期（后端 `/api/admin/*` 为 ADMIN-only，见 admin-guard.tsx 注释） |

## vitest 抽查结果（不跑全量）

命令（edu-frontend 下）：`npx vitest run src/lib/admin-guard.test.tsx`

- Test Files: **1 passed (1)**
- Tests: **8 passed (8)**，55ms（总耗时 2.77s）
- 覆盖：AdminGuard 未登录重定向 / 非 admin 角色拦截 / admin 放行 / redirect 参数携带等分支

## Playwright 可用性

- 可用 ✓：MCP playwright 已连接，成功完成导航 / 快照 / 重定向观察 / console 捕获（全部基于 **http://localhost:3000**）
- 注意：首次导航可能超时（冷启动 30s 超时），重试一次即成功

## 已知注意事项

1. **必须用 `http://localhost:3000` 访问，勿用 127.0.0.1**：Next.js 16 dev 的 origin 校验（DNS-rebinding 防护）只信任 localhost。带 `Origin: http://127.0.0.1:3000` 的浏览器请求，`/_next/static/chunks/*.js`、字体、HMR WebSocket 全部 403（实测）；`localhost` 来源则全部 200、`[HMR] connected` 正常。curl 无 Origin 头时两者皆 200，故仅靠 curl 探测发现不了此差异。
2. **RBAC 守卫是客户端行为，验证须用真实浏览器**：SSR 阶段返回 200 + 占位，重定向发生在 hydrate 后（useEffect + `router.replace`）。用 curl 只能验证 SSR 200；要验证「未登录 → /login?redirect=」必须用 Playwright 等浏览器工具。
3. **`/api` 无 Next.js 代理**：前端 axios 直连 `127.0.0.1:8000` 后端。未登录访问管理端页面时控制台会出现 401「登录凭证无效」——预期噪音，不是回归。管理端数据接口权限以后端 `require_role([ADMIN])` 为权威契约。
4. **vitest 警告**：`vitest.config.mts:16` 用了 `__dirname`（Vite 提示未来默认 `configLoader: 'native'` 时不支持），仅警告不影响结果。
5. **测试残留**：登录页表单有此前轮次预填的测试凭据（`smoke_test@test.com` / 记住我勾选，localStorage persist 残留），审查时注意会话状态可能非干净起点；对 fx-task02 管理端流程无影响（未登录 → 守卫仍重定向）。
6. **管理端 URL 规范**：`/admin/*`（仪表盘/课程/题库/用户/RAG/MCP），与用户端 `/dashboard` `/courses` 隔离；无 `/admin` 根路由（404 属正常，勿报为缺陷）。

## 清理约定

- 本任务未启动 dev server（复用 fe-task01 启动的进程，PID 3780），**不 kill**；仅当流水线最后一个前端 task 由持有 startedByInfra=true 记录的轮次执行清理。
- 本文件由 fe-server-infra 写入，后续前端 task 完成后由编排器统一处理生命周期。
