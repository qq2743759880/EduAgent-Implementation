# fx-task04 dev server 信息

- framework: Next.js 16.3（next 16.3.0 / React 19.2.8）
- profileId: nextjs-16-app-router
- 判定来源: profile:nextjs-16-app-router
- confirmLine: Next.js 16 + React 19 + Tailwind v4 + Zustand + TanStack Query + App Router
- port: 3000
- baseUrl: http://localhost:3000（**必须用 localhost，勿用 127.0.0.1——origin 校验**）
- startedByInfra: false
- pid: 17284（监听 0.0.0.0:3000 与 [::]:3000；由并发实例启动，非本 infra 启动）
- 工程目录: edu-frontend
- 启动命令: npm run dev（本任务启动的 launcher PID 25112 检测到既有 server 后自动退出，无残留；3001 无监听）
- 探测响应码: /login=200、/admin/rag=200、/admin/mcp=200

## 健康检查结果

| 检查项 | 结果 | 说明 |
|--------|------|------|
| GET /login | 200 | 登录页完整渲染（Playwright 快照确认：账号/密码/记住我/登录按钮，console 0 error） |
| GET /admin/rag | 200 | 未登录：AdminGuard 客户端守卫，SSR 返回管理端布局骨架「正在校验登录状态」，hydrate 后客户端跳转 /login?redirect=；not-found.tsx 卡片为 Next.js 预渲染 not-found boundary，非路由 404 |
| GET /admin/mcp | 200 | 同上（同一 (admin) 布局骨架） |
| 后端 127.0.0.1:8000 | **不可达** | curl 返回 000（连接拒绝 / 未运行）；登录 API 与 /api/admin/* 数据接口暂不可用 |

## vitest 抽查

命令：`npx vitest run src/lib/api/admin/rag.test.ts src/components/admin/mcp/ServerTable.test.tsx`

- `src/lib/api/admin/rag.test.ts`：14 tests ✓
- `src/components/admin/mcp/ServerTable.test.tsx`：4 tests ✓
- 合计：**2 files / 18 tests 全部通过**（vitest 4.1.10，3.86s，exit 0）

## Playwright 可用性

- 可用：navigate http://localhost:3000/login 成功（URL 与 Title 正常），快照完整（登录表单 + 通知区），console error=0。
- 因后端 127.0.0.1:8000 不可达，**未执行 admin JWT 注入验证**（任务步骤 2 依赖后端）；后端启动后即可验证 /admin/rag 集合表格与 /admin/mcp 服务列表骨架渲染。

## 注意事项

1. **dev server 非本 infra 启动（startedByInfra=false，PID 17284）**：清理阶段**绝不 kill 17284**（可能是用户/并发实例自行启动）。本任务启动的 launcher（25112）已自动退出、3001 无监听，无残留需清理。
2. **后端未运行**：若需端到端验证 RAG/MCP 管理页数据渲染，需先启动后端（127.0.0.1:8000）；当前页面仅能验证 SSR 骨架与登录守卫行为。
3. **RBAC 为客户端守卫**：未登录访问 /admin/* 返回 HTTP 200 + 管理端骨架（非 302），客户端跳 /login?redirect=；后端 /api/admin/* ADMIN-only 为权威契约（manager/student/teacher 无管理端点权限）。
4. **origin 校验**：所有探测/连接使用 `http://localhost:3000`，勿用 127.0.0.1。
5. **日志**：`edu-frontend/next-dev-fx-task04.log` 记录本次启动尝试（检测到既有 server 后自动退出），保留供排查。
