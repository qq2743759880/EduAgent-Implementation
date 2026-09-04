# fx-task03 dev server 信息

> 生成：fe-server-infra（补课波·只做环境验证与产物，未修改任何业务源码）
> 本文件是唯一事实来源：fe-visual-auditor / fe-a11y-auditor / fe-perf / fe-tester 必须读取它连接 server，**不要自行再启动一个 dev server**。

## 基本信息

- framework: Next.js 16.3.0（App Router + Client Components + Turbopack dev）
- profileId: nextjs-16-app-router
- 判定来源: profile:nextjs-16-app-router
- confirmLine: Next.js 16 + React 19 + Tailwind v4 + Zustand + TanStack Query + App Router
- port: 3000
- baseUrl（推荐）: **http://localhost:3000**
- baseUrl（仅无 Origin 场景可用）: http://127.0.0.1:3000（见注意事项 #1）
- startedByInfra: true（fx-task03 轮次启动：探测时原 fx-task02 记录的 PID 3780 已死、3000 无监听，故按任务指令后台重启）
- pid: 17284（node，`next dev` 实际监听 3000；父 cmd PID 17684 = `npm run dev`）
- 工程目录: edu-frontend
- 启动命令: `npm run dev`（实际 = `next dev`，日志显示 `Ready in 1387ms`，Next.js 16.3.0 Turbopack）
- 日志文件: `edu-frontend/next-dev-fx-task03.log`
- 探测响应码: /admin/* 各路由 200（SSR）、/login 200、后端 127.0.0.1:8000 000（未运行）

## 健康检查结果（2026-08-13，curl + Playwright 实测）

| 路由 | HTTP | 说明 |
|------|------|------|
| `/admin/courses` | 200（SSR） | 课程管理页骨架完整渲染：标题「课程管理」、创建系列按钮、学科/难度/关键词筛选器、加载态「加载系列…」 |
| `/admin/questions` | 200（SSR） | 题库管理页骨架完整渲染：标题「题库管理」、新建标签/批量导入/自动组卷/新建题目按钮、学科/题型/难度/标签/关键词筛选器、加载态「加载题目…」 |
| `/admin/users` | 200（SSR） | 用户管理页骨架完整渲染：标题「用户管理」、角色筛选器、搜索框、重置；数据区显示错误态「网络错误，无法连接后端服务」+ 重试按钮（后端不可达的预期 UI） |
| `/login` | 200 | 登录页完整渲染（含 redirect 参数回填） |
| `/` | 200 | 首页正常 |
| `/admin/*`（未登录浏览器） | 客户端重定向 | Playwright 实测：清除 localStorage 后访问 `/admin/courses` → 4s 内自动跳转 `http://localhost:3000/login?redirect=%2Fadmin%2Fcourses` —— AdminGuard 未登录分支守卫生效 ✓（SSR 仍返回 200，见注意事项 #2） |

**后端状态（数据获取不可达）**：`127.0.0.1:8000` 未运行——curl 全部 000、netstat 无 LISTENING；浏览器网络面板 `GET http://127.0.0.1:8000/api/admin/courses/series?page=1&page_size=10` → `net::ERR_CONNECTION_REFUSED`。管理端三页骨架（导航/筛选/操作区/加载态/错误态）均正常渲染，仅真实列表数据不可达。admin/Admin@12345 登录本次**未实测**（后端不在，登录接口不可达；浏览器侧保留的持久化登录态为超管会话，见注意事项 #4）。

## vitest 抽查结果（不跑全量）

命令（edu-frontend 下）：`npx vitest run src/components/admin/MetricCards.test.tsx src/components/admin/SeriesForm.test.tsx`

- Test Files: **2 passed (2)**
- Tests: **9 passed (9)**（MetricCards 3 + SeriesForm 6），耗时 4.71s
- 退出码 0；仅 Vite `configLoader: 'native'` 的 `__dirname` 弃用警告（见注意事项 #3），不影响结果
- 完整输出：`test-reports/fx-task03-vitest.log`

## Playwright 可用性

- 可用 ✓：MCP playwright 已连接，成功完成导航 / 快照 / 重定向观察 / console 捕获 / localStorage 操作（全部基于 **http://localhost:3000**）
- 已验证：登录态下管理端三页骨架渲染、未登录时 AdminGuard 重定向 `/login?redirect=...`

## 已知注意事项

1. **必须用 `http://localhost:3000` 访问，勿用 127.0.0.1**：Next.js 16 dev 的 origin 校验（DNS-rebinding 防护）只信任 localhost。带 `Origin: http://127.0.0.1:3000` 的浏览器请求，`/_next/static/chunks/*.js`、字体、HMR WebSocket 全部 403；`localhost` 来源全部 200。curl 无 Origin 头时两者皆 200，仅靠 curl 探测发现不了此差异。
2. **RBAC 守卫是客户端行为，验证须用真实浏览器**：SSR 阶段返回 200，重定向发生在 hydrate 后（useEffect + router.replace）。curl 只能验证 SSR 200；验证「未登录 → /login?redirect=」必须用 Playwright。
3. **`/api` 无 Next.js 代理**：前端 axios 直连 `127.0.0.1:8000` 后端。后端未运行时管理端/聊天页 console 会出现 `net::ERR_CONNECTION_REFUSED`（如 `/api/chat/sessions`、`/api/admin/courses/series`）——预期噪音，不是回归；管理端数据权限以后端 `require_role([ADMIN])` 为权威契约。
4. **浏览器会话状态**：本验证开始时浏览器保留了此前轮次的持久化登录态（超管），借此实测了管理端三页骨架；随后清除 localStorage 验证了未登录重定向。后续审查 agent 若需登录态，需自行走 `/login`（后端必须已启动）或注入 JWT。
5. **vitest 警告**：`vitest.config.mts:16` 用了 `__dirname`（Vite 提示未来默认 `configLoader: 'native'` 时不支持），仅警告不影响结果。
6. **管理端 URL 规范**：`/admin/*`（仪表盘/课程/题库/用户/RAG/MCP），无 `/admin` 根路由（404 属正常，勿报为缺陷）。

## 清理约定

- dev server 由本任务启动（startedByInfra=true，PID 17284/17684），**保持运行**供后续审查 agent 使用；**不 kill**——仅当流水线最后一个前端 task 由持有 startedByInfra=true 记录的轮次执行清理。
- 共享锁 `.dev-server.lock` 已删除；`edu-frontend/next-dev-fx-task03.log` 保留至清理轮次一并删除。
- 本文件由 fe-server-infra 写入，后续前端 task 完成后由编排器统一处理生命周期。
