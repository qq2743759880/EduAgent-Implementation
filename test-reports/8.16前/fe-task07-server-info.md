# fe-task07 dev server 信息

- framework: Next.js 16.3
- profileId: nextjs-16-app-router
- 判定来源: profile:nextjs-16-app-router
- confirmLine: Next.js 16 + React 19 + Tailwind v4 + Zustand + TanStack Query + App Router
- port: 3000
- baseUrl: http://localhost:3000
- startedByInfra: false
- pid: 16676
- 工程目录: edu-frontend
- 启动命令: npm run dev
- 探测响应码: 200

## dev 健康

- `GET http://localhost:3000/` → 200，响应体为 HTML（Next.js 页面 title「EduAgent · 智能学习助手」，含 `<html lang="zh-CN">` 与 `/_next/static/` chunks）——确认是 dev server 响应，非端口误占。
- 5 个目标页面 HTTP 复测全 200：`/dashboard`、`/community`、`/achievements`、`/courses`、`/chat`。
- dev server 复用既有进程（`netstat -ano` 确认 0.0.0.0:3000 LISTENING，PID 16676）；`startedByInfra=false`，本 task 未启动、未重启、未 kill。
- 后端 `http://127.0.0.1:8000` 运行中（事实基线，本验证依赖其提供登录态与页面数据）。
- 地址约定：验证全程使用 `http://localhost:3000`（按要求不用 127.0.0.1）。

## 5 页渲染验证（Playwright 实际渲染，关键文本命中）

以既有登录态（fe-task06 遗留 JWT，task01test 账号，积分 31 / 排行第 2）逐页渲染，5 页均正常渲染、无任一「加载失败」/空态错误，**0 条 console error**：

| 页面 | HTTP | 关键文本命中 |
|---|---|---|
| /dashboard | 200 | heading「你好，同学」+ 副标题「这里是你的学习仪表盘…」；KPI 4 卡（今日学习时长 0 分钟 / 今日练习题 0 道 / 进行中课程 0 门 / 连续打卡 0 天）；近 14 天趋势图（echarts img alt 含 14 日 0 分钟）；学科能力雷达空态「学习后即可生成学科能力评估」；徽章墙 0/8 + 8 个解锁条件；学习排行榜今日 TOP10（我的排名 2 / 我的积分 17） |
| /community | 200 | heading「学习社区」+「学员社区 · 发帖 +5 分 · 回帖 +2 分」+ 发布帖子按钮 + 帖子列表（置顶欢迎帖 multiple 分页条目） |
| /achievements | 200 | heading「成就与成长」+「成就中心 · 让努力被看见」；徽章区（已解锁 0/8，下一目标「初出茅庐」进度 0/60）；积分区（Lv.1 · 萌新，当前积分 31，流水「余额 7」）；排行榜（日/周/月/总榜 tab + 积分/学习时长/徽章数维度 tab） |
| /courses | 200 | heading「共找到 12 门课程」+ 筛选条件「全部课程」+ 第 1/1 页；课程卡片（「英语 L1 面向零基础：国际音标…」¥279 ¥363 查看详情） |
| /chat | 200 | title「AI 学习助手 · EduAgent」+ 面板「你好，我是 EduAgent AI 学习助手」+ 快捷提问列表 +「打开独立聊天页」 |

结论：fe-task07 风格收敛后**无布局回归**——5 页路由可达（HTTP 200）、首屏关键内容全部渲染命中、无 JS console error、主导航 7 项（学习仪表盘/课程中心/我的课程/错题/单词本/AI 问答/社区/成就中心）在 5 页间一致（AppShell 统一布局收敛生效）。

## vitest 抽查

- 命令：`npx vitest run src/lib/api/dashboard.test.ts src/lib/api/community.test.ts`（edu-frontend 目录，vitest v4.1.10，`--reporter=verbose`）
- 结果：**2 个测试文件通过，52/52 tests passed**（3.03s）
  - `src/lib/api/dashboard.test.ts`：派生纯函数（KPI 除零保护 / 雷达 clamp 与空态 / 打卡顺序 / 趋势反转 / 徽章映射 / 积分白名单 / 排行映射）+ 数据获取（query 拼装、严格抛错、subject_preferences 双命名兜底）
  - `src/lib/api/community.test.ts`：社区 API 相关用例
- `src/lib/chart-palette.test.ts` 不存在（chart-palette.ts 存在但无对应测试文件），故按任务指示抽查 dashboard/community 相关。
- 日志留档：`test-reports/fe-task07-vitest.log`（stderr：`test-reports/fe-task07-vitest-err.log`）。

## Playwright 可用性

- 确认可用：MCP Playwright（playwright ^1.62.1 devDependency）已驱动 Chromium 完成上述 5 页真实渲染 + snapshot 关键文本检索。
- 项目内无 `playwright.config.*`（e2e 通过 MCP playwright 直连 dev server，不依赖项目级 config）。
- 建议 fe-visual-auditor / fe-tester 直接读取本文件连接 `http://localhost:3000`，勿再启动 dev server。

## 注意事项

1. **dev server 归属**：监听 PID 16676 非本 task 启动（startedByInfra=false），清理阶段勿 kill；由流水线最后一个前端 task 依据 server-info 的 startedByInfra 决定是否清理。
2. **登录态**：验证沿用浏览器既有 localStorage `edu:auth:token`（task01test，user_id 846）。如需 fe_task07_test（user_id 960）或 admin 账号复核，可 `POST /api/auth/login` 获取 JWT 注入 `localStorage["edu:auth:token"]` 后刷新页面（详见 fe-task06-server-info 注意事项 3）。
3. **学习数据为 0 是账号真实状态**：task01test 有社区积分（31 分）/排行数据，但 progress 学习统计为空（今日 0 分钟/0 道/进行中 0 门）。如需非零学习数据视觉确认，需换有学习记录的账号。
4. **本 task 零改动**：仅探测 + 渲染验证 + 产物写入，未修改任何业务源码；额外产物 `fe-task07-vitest.log` / `fe-task07-vitest-err.log` 位于 test-reports/。
