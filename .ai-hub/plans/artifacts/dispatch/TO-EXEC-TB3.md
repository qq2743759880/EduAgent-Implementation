# TO-EXEC-TB3 — 基础设施页 admin-infra（yy 十点修复 · P1）

> 分支 `feature/opt-waves`；后端 9988 / 前端 3322。owner 批评 6："LLM 队列削峰、分布式锁、SETNX 缓存我根本没使用过，也没演示方案"。本单把它们变成**可点的实时面板**。开工令自包含。

## 背景

这些机制全部真实存在且有实证报告（task39：限流 429 次/缓存 322.6ms→5.3ms/锁最大同时持有=1；R1-③：Redis 队列 12 任务/4 worker 零丢失），但 owner 看不见。目标：admin-only 一页看到 Redis 四件套 + Mongo + learning_event 实时数据。

## 工作项

1. **schema 先冻**：新只读 API `GET /api/admin/infra/snapshot` 响应结构先在本报告「契约冻结」小节定稿再实现（admin/manager role 守卫，student 403）。
2. **后端**（只读，零写操作）：
   - Redis 四件套：限流计数（当前窗口命中/拒绝数）、缓存演示（挑一个真实缓存 key 的命中耗时对比——现场 `GET` 两次返回热/冷耗时或最近命中率统计）、锁状态（现有锁 key 列表+TTL）、队列深度（chat/任务队列 llen）。
   - Mongo 三集合统计（artifacts.files/chunks/learning_event 计数+最新一条时间）。
   - `learning_event` 样例（最近 5 条，脱敏 uid）。
   - 所有 Redis 访问走应用连接层；**全程只读，禁任何写命令**。
3. **前端**：新建 `edu-frontend/public/admin-infra.html`——黏土主题（引 `theme.css?v=<同站现行版本>` + `clay-*` 组件类，禁 emoji 图标用 Phosphor sprite `/assets/icons/icons.svg`）、admin 角色守卫三段不可少（无 token 跳登录→`/api/auth/me` role 校验→失败仍跳登录，参照 admin-dashboard.html 现行实现）、「运行演示」按钮实时拉 snapshot 刷新面板。
4. **门禁自验**：新页纳入扫描后跑 G3 `--page` 确认钩子登记；G6/G7/G9 单页跑绿（对齐全站现行基线口径，G9 的 N/A 项按白名单机制处理）；入口链：admin-dashboard.html 侧边栏加一链接（改这一处）。
5. 负向：student token 直打 `/api/admin/infra/snapshot` 断言 403。

## 铁律

- 域：新后端 router 文件+注册行（`app/main.py` 或现行 router 注册点**只加一行**——TB1 也在后端，禁大改公共文件）、`edu-frontend/public/admin-infra.html`（新文件）、`admin-dashboard.html` 侧边栏一行、G3 基线登记。
- 禁碰 chat.html/React（已收口）、`.env`、recommender。
- admin 页基线验收需运行时 `EDU_GATE_TOKEN`（禁落盘）。
- 不 push；单 commit：`feat(infra)/tb3: admin-infra 基础设施实时页(Redis四件套+Mongo+learning_event,只读)+admin入口`。
- 报告 `.ai-hub/plans/artifacts/dispatch/REPORT-TB3.md`：契约冻结小节、四件套/Mongo 每项真实数据截图、403 证据、门禁输出。

## owner 验收口径

Given owner 用 admin 打开基础设施页点「运行演示」，Then 四件套+Mongo 实时数据全部可见且数字随操作变化；用 student 打开被拒。
