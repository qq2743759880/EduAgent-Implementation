# fx-task05 dev server 信息

- framework: Next.js 16.3（next 16.3.0 / React 19.2.8）
- profileId: nextjs-16-app-router
- 判定来源: profile:nextjs-16-app-router
- confirmLine: Next.js 16 + React 19 + Tailwind v4 + Zustand + TanStack Query + App Router
- port: 3000
- baseUrl: http://localhost:3000（**必须用 localhost，勿用 127.0.0.1——前端 origin 校验**；画像默认 127.0.0.1 仅作备选探测地址，实际联调一律 localhost）
- startedByInfra: false
- pid: 1908（监听 0.0.0.0:3000 与 [::]:3000，node 进程；由主编排器管理，非本 infra 启动）
- 工程目录: edu-frontend
- 启动命令: npm run dev（未重启；本任务只复用，无新启动进程、无残留）
- 探测响应码: /chat=200、/community=200、/admin/dashboard=200（均为 text/html; charset=utf-8，Next.js dev 渲染）
- 后端: http://127.0.0.1:8000 运行中（PID 3692 python/uvicorn；/health=200、/ =200、/docs=200、/openapi.json=200；DEBUG=true，根返回 JSON 信封 `{"app":"EduAgent","version":"0.1.0","debug":true}`）

## 健康检查结果

| 检查项 | 结果 | 说明 |
|--------|------|------|
| GET /chat（用户端会话页） | 200 | text/html 62.9KB；SSR 含 `(user)/chat/page.tsx` + `ChatFullScreenClient.tsx`，title「AI 学习助手 · EduAgent」，客户端渲染占位「Loading AI assistant...」，hydrate 后由 TanStack Query 拉取会话列表 |
| GET /community | 200 | text/html；200 耗时 2.4s（首次编译），页面正常渲染 |
| GET /admin/dashboard | 200 | text/html；管理端布局骨架（AdminGuard 客户端守卫，未登录 hydrate 后跳 /login?redirect=） |
| 后端 /health | 200 | uvicorn 就绪 |
| admin 登录 + JWT 注入 | 200 | POST /api/auth/login（admin/Admin@12345）→ access_token（Bearer，expires_in 86400），user_id=894 role=admin |
| GET /api/chat/sessions（会话列表） | 200 | admin 全局可见 53 个会话；字段含 session_id/message_count/created_at 等（与 chat.ts 归一化契约一致） |
| GET /api/chat/sessions/{id}/history（**R-1 复证**） | 200 | s_993b641d6fcd → 2 条消息（user + assistant），assistant 为真实 RAG 回答（rag_docs_json 5 条引用、latency 68949ms）——会话历史加载链路端到端可用 |

## vitest 抽查

命令：`npx vitest run src/lib/api/chat.test.ts`（vitest 4.1.10，2.38s）

- `src/lib/api/chat.test.ts`：**13 tests 全部通过**（1 file passed / 13 tests passed，exit 0）
- 覆盖：R-1 路径修复（/history 非 /messages）、R-2 DELETE 契约、R-7 失败 console.error 不静默吞错、session_id/message_count 归一化、searchRagOnly
- 日志：`test-reports/fx-task05-vitest.log`

## 联调脚本清单（fx-task05 专用）

| 脚本 | 状态 | 说明 |
|------|------|------|
| `edu-frontend/scripts/verify-task05-user-chain.mjs` | 存在、可读 | 8 阶段用户端全链路（注册→登录→选课→学习→答题→问答→社区→成就），真实 JWT 贯穿；问答段复证 R-1 `/api/chat/sessions/{id}/history`；注册随机账号 + 409 幂等兜底；退出码 0/1/2/3。**实际运行由 fe-tester 执行**（本任务已确认后端健康 + 脚本存在 + 关键端点实测通过） |
| `edu-frontend/scripts/verify-task05-chat-ui.mjs` | 存在 | 会话 UI 链路（浏览器渲染断言，依赖 dev server :3000） |
| `edu-frontend/scripts/verify-task05-admin-chain.mjs` | 存在 | 管理端链路 |

> 说明：本任务未执行 user-chain 全量脚本（含一次真实 LLM 问答，单次 latency 实测约 69s，执行成本高）；已验证脚本依赖的每个后端端点就绪（login/sessions/history 均 200），脚本可直接运行。

## 注意事项

1. **dev server 非本 infra 启动（startedByInfra=false，PID 1908）**：清理阶段**绝不 kill 1908**（主编排器管理）。本任务未启动任何进程，无残留需清理；`test-reports/.dev-server.lock` 不存在（未加锁）。
2. **后端非本 infra 启动（PID 3692）**：绝不 kill；后端为 fx-task05 联调先决条件，脚本依赖其存活。
3. **origin 校验**：所有前端探测/连接必须用 `http://localhost:3000`；后端 API 用 `http://127.0.0.1:8000`（前端 axios API_BASE 亦如此）。勿反向使用。
4. **JWT 注入方式（给 fe-tester / 审计 agent 参考）**：admin/Admin@12345 可登录，access_token 注入 `Authorization: Bearer`；浏览器注入 `localStorage.setItem("edu:auth:token", token)`（见 verify-task05-user-chain.mjs browserAssert）。
5. **/chat 会话列表是客户端加载**：curl 只见 SSR 占位「Loading AI assistant...」，真实列表需 hydrate + JWT；HTTP 侧已实测 sessions/history 接口 200，UI 渲染断言交给 fe-tester 的 verify-task05-chat-ui.mjs。
6. **vitest 通过**：chat.ts 契约（R-1/R-2/R-7）无回归，联调 bug 修复点被单测覆盖。
7. **日志**：本任务探测产物在 `%TEMP%\fx05_*.html/json`（临时），vitest 日志 `test-reports/fx-task05-vitest.log` 保留供排查。
