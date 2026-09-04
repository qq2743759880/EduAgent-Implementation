# fe-task00 dev server 信息

> 生成时间：2026-08-13 13:50（GMT+8）
> 生成 agent：fe-server-infra（验证 + 产物模式，未启动/未重启 dev server）

- framework: Next.js 16.3
- profileId: nextjs-16-app-router
- 判定来源: profile:nextjs-16-app-router
- confirmLine: Next.js 16 + React 19 + Tailwind v4 + Zustand + TanStack Query + App Router
- port: 3000
- baseUrl: http://localhost:3000（**任务要求必须用 localhost 而非 127.0.0.1**，因应用存在 origin 校验；画像 baseUrl 为 http://127.0.0.1:3000，仅作参考，实际验证全部走 localhost）
- startedByInfra: false（dev server 由主编排器重启，fresh；本 agent 仅验证，未执行启动命令）
- pid: 1908（node，监听 `::`，启动时间 2026-08-13 13:46:09）
- 工程目录: edu-frontend
- 启动命令: npm run dev（画像 devServer.command；由主编排器在 edu-frontend 下执行）
- 日志文件: 主编排器管理（画像 logFile=/tmp/next-dev-{taskId}.log 为 Unix 路径；Windows 下 /tmp 不存在，本 agent 未启动故未产生本地 logFile）
- 探测响应码: 200（/）、200（/dashboard）、200（/login）、200（/admin/dashboard）

## 健康检查（HTTP 探测，curl.exe，localhost:3000）

| 端点 | 状态码 | 关键文本 |
|------|--------|----------|
| / | 200 | Next.js App Router 首页正常 |
| /dashboard | 200 | 用户壳 AppShell：`app-sidebar` 侧边栏 + 顶栏 + 守卫骨架 loading「正在校验登录状态…」+ EduAgent 品牌条（SSR HTML 已含）；未登录访问重定向 `/login?redirect=%2Fdashboard` |
| /login | 200 | isAuthGate 品牌条：「EduAgent」「欢迎回来」「登录后开始你的个性化学习旅程」+ 账号/邮箱 + 密码 + 记住我 + 登录 + 免费注册 |
| /admin/dashboard | 200 | 管理端壳：「EduAgent 管理端」+ 6 导航（仪表盘/课程/题库/用户/RAG/MCP）+ 面包屑（管理端 / 仪表盘）+ 顶栏退出；数据来自 `GET /api/admin/users/dashboard/metrics`（用户总数 920、角色分布 管理员 3/运营 2/学员 115、禁用 2、7d 新增注册 120） |

## AppShell 两壳 SSR 渲染验证（Playwright snapshot，登录态 admin/Admin@12345）

### 用户壳（/dashboard）
- 侧边栏 `complementary "主导航"`：**恰好 8 个导航项** —— 学习仪表盘(/dashboard)、课程中心(/courses)、我的课程(/my-courses)、错题/单词本(/practice/wrong-book)、AI 学习问答(/chat)、社区(/community)、成就中心(/achievements)、个人中心(/me)
- 侧边栏底部：品牌条「EduAgent」→ / + 退出登录 + 版权「© EduAgent · 让学习被量化，让努力被记住」
- 顶栏 `banner`：问 AI（/chat）+ 用户头像「超 超级管理员」+ 当前账号/已登录浮层
- 主区：你好，超级管理员 + 今日学习时长 62 分钟、今日练习题 28 道（正确率 82%）、进行中课程 4 门、活跃学科 5/5、连续打卡 13 天、积分 1,480、徽章墙 5/10、学习排行榜（本周 TOP10 + 我的排名 18）

### 登录壳（/login，isAuthGate）
- 品牌条：banner「返回 EduAgent 首页」→ EduAgent（/）
- 主区品牌条：「EduAgent」「欢迎回来」「登录后开始你的个性化学习旅程」+ 登录表单
- 守卫行为：未登录访问受保护页 → `/login?redirect=%2F<page>`；已登录访问 /login → 自动重定向回 /dashboard

### 管理端壳（/admin/dashboard，admin-guard）
- 侧边栏 `complementary "管理端导航"`：6 导航（仪表盘/课程/题库/用户/RAG/MCP）+「© EduAgent · 管理控制台」
- 顶栏：面包屑（管理端 / 仪表盘）+ 超级管理员 + 退出
- 守卫行为：未登录/非管理员访问 → `/login?redirect=%2Fadmin%2Fdashboard`；退出后实测重定向正确

## vitest 抽查

- 命令：`npx vitest run src/components/layout/AppShell.test.tsx src/lib/admin-guard.test.tsx`
- 结果：**2 文件通过，16 测试全部通过**（AppShell.test.tsx 8 个、admin-guard.test.tsx 8 个），Duration 3.34s
- 提示（非错误）：vitest.config.mts:16 使用 `__dirname`，`configLoader: 'native'` 计划未来默认化时需改用 `import.meta.dirname`（不影响当前通过）

## Playwright 可用性

- 浏览器：Playwright MCP 连接成功，1440x900 viewport
- 截图基线：`test-reports/screenshots/fe-task00/dashboard-1440.png`（登录态 /dashboard 全视口截图，作为两壳视觉一致性基线之一）
- 登录链路验证：/login → admin/Admin@12345 → 登录成功 → redirect /dashboard（后端 127.0.0.1:8000 运行中）

## 注意事项

1. **baseUrl 一律使用 http://localhost:3000**，勿用 127.0.0.1（应用 origin 校验；画像中 127.0.0.1 仅为模板值，已被本文件 localhost 覆盖）。
2. startedByInfra=false：dev server 由主编排器启动（PID 1908），**本 agent 及下游 agent 不得 kill / 重启**；清理职责归主编排器。
3. 下游审计/测试 agent（fe-visual-auditor / fe-a11y-auditor / fe-perf / fe-tester）**必须读取本文件连接 server，禁止自行再启动 dev server**（端口 3000 已占用，双启动会失败）。
4. 登录态：admin / Admin@12345 可成功登录；前端可能从 API 拉取 mock/真实数据（dashboard 指标来自后端 metrics 接口，显示正常）。
5. vitest.config.mts `__dirname` 警告可后续优化，不影响测试通过。
6. 本任务仅验证 + 产物，未修改任何业务源码。
