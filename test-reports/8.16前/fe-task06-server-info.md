# fe-task06 dev server 信息

- framework: Next.js 16.3
- profileId: nextjs-16-app-router
- 判定来源: profile:nextjs-16-app-router
- confirmLine: Next.js 16 + React 19 + Tailwind v4 + Zustand + TanStack Query + App Router
- port: 3000
- baseUrl: http://localhost:3000
- startedByInfra: false
- pid: 1908
- 工程目录: edu-frontend
- 启动命令: npm run dev
- 探测响应码: 200

## dev 健康

- `GET http://localhost:3000/` → 200，响应体为 HTML（Next.js 页面 title「EduAgent · 智能学习助手」）——确认是 dev server 响应，非端口误占。
- `GET http://localhost:3000/dashboard` → 200。
- dev server 复用既有进程（监听 PID 1908，netstat 确认 0.0.0.0:3000 LISTENING）；`startedByInfra=false`，本 task 未启动、未重启、未 kill。
- 后端 `http://127.0.0.1:8000` 运行中，登录与 5 个 dashboard 数据接口均可用。

## dashboard 真实数据渲染确认

以 student 账号 task01test（user_id=846，nickname=任务一测试）登录（`POST /api/auth/login` 获取 JWT → 注入 localStorage key `edu:auth:token` → 刷新 /dashboard），Playwright 实测渲染：

| 模块 | 渲染结果 | 后端对照接口（curl 带同 token 交叉验证，完全一致） |
|---|---|---|
| KPI 4 卡 | 今日学习时长 0 分钟（较昨日持平）/ 今日练习题 0 道（暂无数据）/ 进行中课程 0 门 / 连续打卡 0 天（近 7 天活跃 0 天） | GET /api/progress/dashboard?days=14（total_study_seconds=0、attempted=0、latest_streak_days=0）；GET /api/progress/courses（5 系列 overall_ratio 全 0.0，0 边界不计入进行中） |
| 连续打卡 | 0 天 + 7 格（rest×6 + today） | 同上 latest_streak_days=0 |
| 积分与成长 | 当前积分 31、今日 +17、明细 8 条（发帖 62/+5、回帖 #12/+2、发帖 61/+5、发帖 60/+5、发帖 53/+5、回帖 #10/+2、发帖 52/+5、回帖 #9/+2） | GET /api/gamification/me/points（total_points=31、recent_logs 8 条，数值/note/时间全对齐） |
| 学科能力雷达 | 空态「学习后即可生成学科能力评估」（overall_correct_rate=null → 派生 []，不渲染全 0 雷达，符合实现） | GET /api/progress/dashboard（overall_correct_rate=null） |
| 近 14 天趋势 | 折线图渲染 14 个点（全 0 分钟） | GET /api/progress/dashboard（recent_days 14 条 study_seconds 全 0） |
| 徽章墙 | 0/8，8 个未获得徽章 + 解锁条件（STUDY_MIN_TOTAL 60 / 600 / 6000、QUIZ_FULL_CORRECT 1、COURSE_FINISHED 1、VOCAB_MASTERED 50、POST_LIKES_TOTAL 10、COMMENT_LIKES_TOTAL 50） | GET /api/gamification/me/badges（total=8、unlocked_count=0、trigger_rule/rule_value 全对齐） |
| 学习排行榜 | 今日 tab TOP9：用户894(55)、我(17,第2)、用户953(7)、用户905(5)、用户907(5)、用户911(5)、用户890(5)、用户892(5)、用户1(4)；我的排名 2 / 我的积分 17 | GET /api/gamification/rankings?scope=DAILY&dimension=POINTS&limit=10（top+my_rank 全对齐，source=LIVE_CALC） |

结论：dashboard 为**真实数据渲染**——6 个 TanStack Query（trend/courses/radar/badges/points/rank）全部成功（无任一 DataErrorCard「加载失败」），渲染数值与后端 API 逐字段一致。学习区 0 值是 task01test 账号在数据库中的真实状态（该账号有社区发帖/积分数据、暂无学习记录），非 mock、非渲染失败、非前端兜底伪造。

## MOCK 去除确认

- `grep "MOCK_"` 于 `src/` 全范围（含 `src/app/(user)/dashboard/page.tsx`、`src/lib/api/dashboard.ts`、`src/components/dashboard/`、`src/lib/api/community.ts`）→ **0 命中**。
- dashboard 数据链路全部走 `src/lib/api/dashboard.ts` → axios → 后端 API；KPI/趋势/雷达/徽章/积分/排行均为后端数据派生纯函数，无 mock 兜底（`getProgressCourses` 明确不复用带 `[]` 兜底的 learning.ts，错误向上抛）。

## vitest 抽查

- 命令：`npx vitest run src/lib/api/dashboard.test.ts`（edu-frontend 目录，vitest v4.1.10）
- 结果：**1 个测试文件通过，37/37 tests passed**（2.51s）
- 覆盖：派生纯函数（KPI 含除零保护/雷达 clamp 与空态/打卡顺序/趋势反转/徽章映射/积分白名单/排行映射）+ 数据获取（query 拼装、严格抛错、subject_preferences 双命名兜底）
- stderr 中 `[dashboard] rankings scope mismatch: requested=WEEKLY, got=DAILY` 为测试用例故意触发 console.warn，属预期。
- 日志留档：`test-reports/fe-task06-vitest.log`

## 注意事项

1. **学习数据为 0 是账号真实状态**：task01test 有社区积分/排行数据（31 分、今日 +17、排行第 2），但 progress 学习统计为空（total_days=0、overall_correct_rate=null）。如需非零学习数据（KPI 非 0 / 雷达有值 / 徽章已解锁）的视觉确认，需用 admin/Admin@12345 或存在学习记录的账号，本验证未改动任何业务数据。
2. **console 403 与 dashboard 无关**：页面加载时 GlobalChatInjection（全局 AI 助手）尝试拉取 localStorage 残留的 chat 会话 `s_b1b1a58e6bf1` 历史，后端返回 403「无权限访问该会话」（会话不属于当前登录用户），产生 3 条 console error；dashboard 自身 6 个 query 无任何失败。
3. **登录态注入方式**：JWT 存 `localStorage["edu:auth:token"]`；ProtectedRoute 以 `ready && token` 放行；浏览器端 axios 拦截器从 Zustand store 注入 `Authorization: Bearer <token>`（SSR 进程读不到 token，禁止把鉴权数据传给 query-ssr）。
4. **dev server 归属**：监听 PID 1908 非本 task 启动（startedByInfra=false），清理阶段勿 kill；由流水线最后一个前端 task 依据 server-info 的 startedByInfra 决定是否清理。
5. **端口/地址约定**：dev server 统一用 `http://localhost:3000`（勿用 127.0.0.1）；后端地址为 `http://127.0.0.1:8000`（事实基线）。`/dashboard` 路由组为 `src/app/(user)/dashboard/page.tsx`（URL 无 (user) 前缀）。
