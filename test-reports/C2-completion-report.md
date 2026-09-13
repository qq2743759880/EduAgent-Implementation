# taskC2 前端生产 build 尝试（P4）— 完成报告

- 日期：2026-09-12
- 执行：C 阶段前端构建工程师（独立实证：真实 next build + next start + curl 抽验）
- 结论：**构建成功，build+start 可用；不触发 P4 降级出口**

## 1. 现状自证

- `edu-frontend/package.json`：`next 16.3.0`（React 19.2.8），scripts：`dev: next dev` / `build: next build` / `start: next start`。
- `edu-frontend/next.config.ts`：`allowedDevOrigins: [127.0.0.1, localhost]` + `output: "standalone"`。
- 差异面：Next 16 dev（Turbopack）产物写入 `.next/dev`；`next build` 默认写 `.next` 根目录且会清理重建，与在跑的 dev server（3000 端口，PID 22844）同目录有互相覆盖风险。
- 规避措施（零行为变化的配置增强）：next.config.ts 增加 env 守卫 `NEXT_PROD_DIST_DIR`，设置时 `distDir` 隔离到 `.next-prod`，不设置时完全维持原行为。build 与 start 均带此变量，**未触碰在跑的 3000 dev 服务与 8000 后端**。

## 2. build 完整输出（`NEXT_PROD_DIST_DIR=.next-prod npx next build`，exit code 0）

```text
▲ Next.js 16.3.0 (Turbopack)
✓ Running next.config.ts took 70ms

  Creating an optimized production build ...
✓ Compiled successfully in 35.4s
  Running TypeScript ...
  （自动追加 tsconfig include：.next-prod/types/**、.next-prod/dev/types/**）
  Finished TypeScript in 43s ...
  Collecting page data using 15 workers ...
  Generating static pages using 15 workers (0/20) → (20/20) in 1536ms
✓ Generating static pages using 15 workers (20/20) in 1536ms
  Finalizing page optimization ...

Route (app)：29 条路由（○ Static 21 / ƒ Dynamic 8）
○ /  ○ /_not-found  ○ /achievements  ○ /admin  ○ /admin/courses  ƒ /admin/courses/[seriesId]
○ /admin/dashboard  ○ /admin/mcp  ○ /admin/questions  ƒ /admin/questions/[id]  ○ /admin/rag
○ /admin/users  ○ /admin/users-refine  ƒ /chat  ○ /community  ƒ /community/[postId]
○ /courses  ƒ /courses/[seriesId]  ○ /courses/search  ○ /dashboard  ƒ /learning/[seriesId]/[sessionId]
○ /login  ○ /me  ƒ /my-courses  ƒ /orders  ƒ /practice/[mode]  ○ /register  ƒ /tickets  ƒ /tickets/[ticketId]
```

- 无错误、无警告阻断；TypeScript 全量通过；无 Turbopack 专属行为阻塞 build（生产 build 在 Next 16 本身即 Turbopack）。
- 原始日志：`edu-frontend/_c2_build_output.log`（*.log 已 gitignore）。

## 3. next start 生产服务抽验（`NEXT_PROD_DIST_DIR=.next-prod npx next start -p 3001`，用完已关闭）

| 抽验项 | 结果 |
|---|---|
| `/login-register.html`（public 静态页） | HTTP 200，117,445 B |
| `/`（src/app 根路由 page.tsx） | HTTP 200，24,087 B |
| `/login`（src/app 路由） | HTTP 200，36,852 B，`<title>EduAgent · 智能学习助手</title>` |
| `/_next/static/chunks/*.js`（生产 chunk） | HTTP 200 |
| 抽验后 3000 dev 复核 | 仍 HTTP 200，全程未被干扰 |

- 临时 3001 进程（PID 29792）已 `taskkill` 关闭，3001 端口清零。

## 4. 判定与降级出口

- 判定：**build+start 可用**（错误分类不适用：0 配置类错误、0 代码类错误）。
- P4 降级出口：**不触发**。dev-plan-cmin-deploy.md 无需追加降级结论。

## 5. 部署结论（供 taskC1 一键脚本接入）

生产形态＝**build + start**（standalone 输出已配置，Docker 可直接复用 `.next-prod/standalone`）。精确命令（edu-frontend/ 目录下执行；`NEXT_PROD_DIST_DIR` 必须在 build 与 start 两侧一致）：

```bash
# 构建（一次性，或产物变更后）
NEXT_PROD_DIST_DIR=.next-prod npx next build
# 生产启动（Node 脚本内可用 spawn 的 env 传入 NEXT_PROD_DIST_DIR=.next-prod）
NEXT_PROD_DIST_DIR=.next-prod npx next start -p 3000
```

Windows cmd 等价：`set NEXT_PROD_DIST_DIR=.next-prod && npx next build` / `set NEXT_PROD_DIST_DIR=.next-prod && npx next start -p 3000`。

备选（C1 若用 standalone 形态）：`node .next-prod/standalone/edu-frontend/server.js`（需同步拷贝 `.next-prod/static` 与 `public`，本批未做端到端验证，C1 采用上方的 next start 形态为准）。

## 6. 变更清单（commit：feat(c)/C2-next-build）

- `edu-frontend/next.config.ts`：+env 守卫 distDir 覆盖（不设变量行为不变）。
- `edu-frontend/tsconfig.json`：next build 自动追加 `.next-prod/types` include（Next 自动维护）。
- `edu-frontend/.gitignore`：+`.next-prod/`（构建产物禁入库；`.next/` 原已在列）。
- `next-env.d.ts`：build 曾自动改写为 `.next-prod` 路径，已还原为 `.next/dev` 态（该文件为自动生成，不入库本次改写）。
- 未触碰：`public/*.html`、`edu-api.js`、在跑 3000/8000 服务。

## 7. 复跑指引

```bash
cd edu-frontend
NEXT_PROD_DIST_DIR=.next-prod npx next build
NEXT_PROD_DIST_DIR=.next-prod npx next start -p 3001   # 临时端口，验证后关闭
curl -s -o /dev/null -w "%{http_code}" http://localhost:3001/login-register.html   # 期望 200
```
