# task12 完工报告（reshape-a 批次）：admin-dashboard.html 管理仪表盘真实接线

日期：2026-09-12 ｜ 执行：fe-html 接线 agent（独立） ｜ 计划：`.ai-hub/plans/dev-plan-reshape-a.md` A 批次 task12
GWT：接 `/api/admin/users/dashboard/metrics`（慢查询：加 loading 态，优化排 B/C，决策点②）；无数据诚实空态；不留假图形。
Commit：`74dcb67`（fix(reshape)/task12）

## ① 改动文件 + 行数

- `edu-frontend/public/admin-dashboard.html`：+121 / −40（git 74dcb67）
  1. **默认态翻转**：原审核脚本强制 `view-success.hidden=false`（假成功态+硬编码假 KPI），改为默认渲染 `view-loading` 骨架屏——metrics 为慢查询（本次实测 2.1~2.7s），骨架屏为任务硬性要求；
  2. **KPI 6 卡真实接线**：新加 id 挂点（kpi-total/kpi-active7d/kpi-newreg7d/kpi-disabled/rb-admin·manager·teacher·student/kpi-avglogin），删除原硬编码 128,450/23,912/1,028/37/角色假分布/4.6 天；
  3. **注册趋势柱状图真实渲染**：由 `register_trend_7d` 重建 7 柱（date 切 MM-DD、count 为高度基准、maxC 归一），**全 0 时诚实渲染 0 值矮柱（height:2% + "0" 标签）**，不伪造形状；aria-label 同步真实数值；
  4. **角色饼图真实计算**：conic-gradient 由 `role_breakdown` 逐段累加计算（色序 admin indigo/student purple/teacher blue/manager rose 保持 §1.7），中心总数 + 学员占比按真实比例；删除原 v2 手写假分段与 "128K" 假中心值；
  5. **bootAdmin 重写**：原 3 处 EAPI 消费的字段名是错的（`total_users/active_users/new_users_today`，与 schemas.py 不符且选择器 `[data-metric=…]` 在 DOM 中不存在，等于从未生效）——改为真实字段名直连；新增 `loadDashboardMetrics()` 供空态/错误态重试按钮复用（不再 `location.reload()` 整页刷新）；
  6. 空态文案改为准确语义（total_user_count=0）；错误态展示 `err.message + HTTP status`（不吞错）；保留「热门课程榜」契约缺口占位卡（trade 域无 admin 全局聚合端点，诚实降级不动）。

## ② 资产消费证据

- **AGENTS.md**：教训 2（禁 Playwright，验收用 curl 独立实证）、教训 8（真实契约优先于页面注释——原页头注释虽写对字段名但 JS 用错）、教训 10（管理端守卫三段不可少）均读完并遵守；启动命令条目用于拉起服务（见⑦环境留痕）。
- **dev-plan task12 GWT**：慢查询加 loading 态 = 骨架屏已落地；决策点②（优化排 B/C）未做任何后端优化，仅前端诚实 loading。
- **contracts/reshape-a.json**（hash 30aeddbe，冻结未改）：`GET /api/admin/users/dashboard/metrics` 在 `verified_read_21` 清单内；`PATCH /api/admin/questions/questions/` 等本任务未涉及。
- **edu-guard.js 头部注释 + edu-api.js 头部注释**：守卫三段复用 `eduGuard.requireAdmin()`（无 token 跳登录 → auth/me 校验 role∈{admin,manager} → 失败跳登录），数据注入收敛 `window.bootAdmin()`；EAPI 壳解包 `{code:0,data}`、非 2xx 抛 `err.status/err.body`。
- **后端契约权威**：`edu-agent/app/admin/user_admin/schemas.py` `DashboardMetrics`（total_user_count/active_user_count_7d/role_breakdown/disabled_user_count/new_register_count_7d/avg_login_days_per_user_30d/register_trend_7d）+ `router.py`（require_role([ADMIN])）。

## ③ curl 实测证据（2026-09-12，本机 8000）

```text
POST /api/auth/login {"account":"adm02test","password":"Test@123456"} → 200（token 175 chars）
GET  /api/admin/users/dashboard/metrics（Authorization: Bearer …）
  → 200  2.726s   {code:0,message:"ok",data:{
       total_user_count:100033, active_user_count_7d:0,
       role_breakdown:{admin:5,manager:3,teacher:3,student:100022},
       disabled_user_count:1, new_register_count_7d:3,
       avg_login_days_per_user_30d:0.01,
       register_trend_7d:[{date:"2026-09-06",count:0}…{date:"2026-09-12",count:0}]  // 7 天全 0
     }}
```
- **慢查询坐实**：2.1~2.7s（远超任务书所述 715ms），骨架屏必要性成立。
- **全 0 趋势是真实数据**：柱图如实渲染 0 值柱与 "0" 标签，与 GWT「不留假图形」一致（真实全 0 ≠ 假图形）。
- **DOM 桩自检**（node vm 共享上下文 + fetch 拦截注入上述真实 JSON + auth/me 真实 JSON，页面脚本 edu-api.js/edu-guard.js 真实加载）：
  `BOOT_CALLS: GET /api/auth/me → GET /api/admin/users/dashboard/metrics；ERRORS: none；loading hidden=true → success hidden=false；bars-real 渲染 7 柱真实值。`
- 页内静态检查：无 `alert(`、无旧假数值（128,450/08-17/128K 等已 grep 清零）、无 match 取参；`http://127.0.0.1:3000/admin-dashboard.html → 200`。

## ④ 批判承接核对

- reshape-a 技术批判/契约审查（`.ai-hub/plans/reshape-a-技术批判.md`、`contract-review-reshape-a-v2.md`）未对 task12 登记单独承接条目；本任务承接的是**页面历史 v2 返工遗留**（v2 已修饼图分段，但 KPI/趋势仍是假数）——本次清零。
- 决策点②（metrics 慢查询优化）按计划排 B/C 批次，本任务不加缓存不加索引，仅诚实 loading——**未越权**。

## ⑤ 自检三视角

- **交互态**：进入页面 → 骨架屏（慢查询 2s+ 期间有反馈）→ 成功态全真实；空态/错误态按钮走 `loadDashboardMetrics()` 真实重查，无假重试（原 setTimeout 假成功已删）。
- **边界**：register_trend_7d 缺失/非数组 → 图表保持空骨架柱不抛错；role_breakdown 缺键 → `||0` 兜底渲染 0；rbSum=0 → 灰色 donut +「暂无用户」；`d.total_user_count==null` → 空态。
- **错误反馈**：失败态展示具体 `err.message（HTTP xxx）`；401 由 edu-api 单飞 refresh 收敛，refresh 失败统一跳登录（edu-guard 第三段兜底）。

## ⑥ 缺口上报（诚实降级，不臆造）

| 缺口 | 实测依据 | 页面处置 |
|---|---|---|
| 管理端无订单数/营收/热门课程榜全局聚合端点 | trade 域均用户本人视角（页头注释+计划书登记 task70~91） | 保留缺口占位卡，不伪造榜单 |
| metrics 无缓存端点、~2.7s 慢查询 | 本次 curl 2.7s | 仅骨架屏，优化待 B/C 决策点② |
| user_admin 路由 `require_role([ADMIN])` 仅 admin 可读，manager 过守卫后本端点将 403 | router.py + task14 实测（manager→403 40300） | 守卫三段保持 {admin,manager} 口径（纪律级），403 时错误态诚实展示 message |

## ⑦ 环境留痕（重要）

- 开工时 **8000/3000 均未监听**（netstat/PowerShell Test-NetConnection 双证实；任务书「服务已运行」为过期信息）。按 AGENTS.md 记载命令**拉起**（非重启——无进程在听，零干扰）：uvicorn 8000（含 Milvus/Mongo/MinIO/Neo4j 192.168.85.101 连接失败告警，dev 模式可忽略，MySQL 本机 3306 正常）、next dev 3000（AGENTS.md 命令中 `next\dist\bin\next` 路径不存在，实际用 `node node_modules/next/dist/bin/next dev -p 3000` 拉起成功）。两服务运行至收尾未中断。

## ⑧ 测试数据留痕

- 本次为只读任务：**零数据变更**。验证账号 adm02test 登录 token 未落库任何页面文件。
