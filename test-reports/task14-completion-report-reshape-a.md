# task14 完工报告（reshape-a 批次）：admin-users.html 用户管理全量真实接线

日期：2026-09-12 ｜ 执行：fe-html 接线 agent（独立） ｜ 计划：`.ai-hub/plans/dev-plan-reshape-a.md` A 批次 task14
GWT：搜索/分页/详情/启停全量接 user_admin 域（原仅 1 处 EAPI≈纯原型），守卫三段完整；启停测试后必须复原。
Commit：`93d0fed`（fix(reshape)/task14）

## ① 改动文件 + 行数

- `edu-frontend/public/admin-users.html`：+233 / −176（git 93d0fed）
  1. **删除全部演示态**：演示控制器（列表态/红线/学习详情三组假按钮）、演示 `USERS` 12 行假用户、假学习 6 指标 `LEARN_PREVIEW`、假动态时间线 `RECENT_ACT`（禁 MOCK）；`alert()` 操作接线按钮删除（禁 alert）；
  2. **列表全量接真实**：`GET /api/admin/users?keyword&role_code&status&page&page_size`，keyword 400ms 防抖（沿用原型节奏）、role_code/status 组合查询、`{total,page,page_size,items}` 分页壳渲染；**窗口化分页**（当前±2+首末页+省略号——实测 total=100,033，原型逐页按钮方案会渲染 1 万个按钮）；
  3. **详情（查看）**：弹窗渲染列表项 `AdminUserItem` 全部 11 字段（真实数据）；`GET /api/admin/users/{id}/learning` 契约缺口保留**诚实披露**（缺口声明 + 已实测不存在），删除假指标假动态；
  4. **启停（带二次确认）**：行内「禁用/启用」按钮 → 新增确认弹窗（说明将提交 `POST /api/admin/users/{id}/status` + reason 选填）→ 真实提交 → toast + 刷新列表；
  5. **编辑弹窗接真实**：role/status diff 检测，变更项分别 `POST /{id}/role`、`POST /{id}/status`，`Promise.all` 收敛；40303 红线=**后端权威**（服务端 active_admins(不含本人)<1 才拒绝，已读 service.py 源码坐实），前端用 `metrics.role_breakdown.admin` 做尽力提示（不据此放行），40303/其他错误码诚实 toast；
  6. **守卫三段完整**（纪律 lesson10）：`eduGuard.requireAdmin()`——①无 token 跳 login-register?redirect=（不依赖后端）；②`GET /api/auth/me` 校验 role∈{admin,manager} 否则跳 dashboard+横幅；③auth/me 失败按未授权跳登录。守卫通过后才调 `window.bootAdmin()`（列表请求只在守卫后发生）；
  7. 初始态=骨架屏行（原 `renderList()` 直绘演示数据已删）；错误态展示后端 message（含 manager 403 场景）。

## ② 资产消费证据

- **AGENTS.md**：教训 2（curl 独立实证）、教训 8（实测契约优先——页头注释即契约初稿，POST status/role 均实测确认而非照抄）、教训 9（禁 match 取参——本页无 URL 取参需求）、教训 10（守卫三段）。
- **dev-plan task14 GWT**：搜索/分页/详情/启停四件套全接；"现仅 1 处 EAPI"与实况一致（bootAdmin 一处且字段渲染残缺+alert 占位）。
- **contracts/reshape-a.json**（hash 30aeddbe）：`GET /api/admin/users` 在 verified_read_21；启停/角色为 POST 写端点，实测核对 `PATCH /api/admin/users/...` **不存在**（路由源码+404 实测），任务书允许的"PATCH 端点自己实测确认，若不存在→缺口上报"结论：**启停真实端点是 `POST /{user_id}/status`（非 PATCH），已按实测接线**。
- **edu-guard.js / edu-api.js 头部注释**：三段守卫、EAPI.post/壳解包/err.status。
- **后端源码（只读核实，禁改）**：`edu-agent/app/admin/user_admin/router.py`（require_role([ADMIN])，GET/POST 路由全清单）+ `schemas.py`（AdminUserItem 11 字段、UserStatusRequest{status,yn?,reason?}、RoleChangeRequest{target_role∈4 枚举,reason?}）+ `service.py`（40303 判定逻辑、40401）。

## ③ curl 实测证据（2026-09-12，本机 8000；带 CJK 的 body 经 --data-binary @file 提交）

| # | 请求 | 结果 |
|---|---|---|
| 1 | `GET /api/admin/users?page=1&page_size=10` | 200 2.25s `{total:100033,page:1,page_size:10,items:[{user_id:100038,username:"123456",real_name:null,phone:null,email:…,role_code:"student",status:1,yn:1,created_at:"2026-09-05T10:14:07",updated_at:…,last_login_at:null},…10 条]}` |
| 2 | `GET …&role_code=student&status=1` | 200 total=100021（角色+状态组合过滤生效） |
| 3 | `GET …&keyword=adm02test` | 200 total=1 → user_id=100003 role=admin（关键词检索生效） |
| 4 | `POST /api/admin/users/1/status {"status":0,"reason":"task14 toggle test, will restore"}` | 200 `{updated:true,user_id:1,status:0,yn:null}` |
| 5 | 复查 keyword=user000001 | status=1→**0** 确认落库 |
| 6 | **复原** `POST …/1/status {"status":1,"reason":"task14 restore"}` | 200；复查 status=**1**（已复原） |
| 7 | `POST /api/admin/users/1/role {"target_role":"teacher",…}` → 复查 role=teacher → **复原** `{"target_role":"student"}` → 复查 role=student | 200×2（角色变更回路+复原实证） |
| 8 | `POST /1/role {"target_role":"superadmin"}` | 422 `42200` pattern 校验失败（前端下拉仅 4 枚举，不会发出该请求） |
| 9 | `POST /999999/status` | 404 `40401 用户不存在 id=999999` |
| 10 | manager 登录后 `GET /api/admin/users` | **403 `{code:"40300",message:"角色无权限。当前角色=manager，允许角色=['admin']"}`** |

- **40303 红线实测说明**：库内 admin=5（metrics role_breakdown），对 adm02test(status=1) 提交 status=0 **成功**（不符合"最后一名"前提），**当即复原 status=1 并复查+复核登录 200**。红线拒绝分支与 service.py 源码一致：仅当「目标为 admin 且排除本人后可用 admin<1」才拒绝——前端因此不做假拦截，只做提示，后端权威。
- **DOM 桩自检**：`GET /api/auth/me → GET /metrics → GET /api/admin/users?page=1&page_size=10；ERRORS: none`（空页回退分支用 items=[] fixture 复测亦 none）。
- 静态检查：无 `alert(`、无演示数据残留（USERS/LEARN_PREVIEW/RECENT_ACT grep 清零）、无 match 取参；`http://127.0.0.1:3000/admin-users.html → 200`。

## ④ 批判承接核对

- 计划书登记的 task103/104 降级项不含本页；tech-critique 未对 task14 登记承接条目。
- 承接页面自身 AUDIT LOG 遗留：task109 守卫条目保留；task60 原型条目标注「2026-09-12 起为真实接线页」；原型"学习详情 6 指标字段预览"按其自declared「值为字段预览，非真实聚合」原则在端点仍未注册的今天**整体删除**（比保留更诚实）。

## ⑤ 自检三视角

- **交互态**：搜索 400ms 防抖（deb-pulse 脉冲）+ Enter 立查；筛选变更即查；启停/编辑均为「弹窗确认 → 真实提交 → toast → 列表刷新」闭环；无任何 onclick=alert 残留。
- **边界**：翻页越界（筛选后末页删行）自动回退 `Math.ceil(total/page_size)` 重查；空结果诚实空态文案「未匹配到用户」；错误态区分后端 message（manager 403 可读）+HTTP status；手机号/姓名/邮箱 null → "—"。
- **错误反馈**：写操作失败 toast 带后端 message，40303 追加「红线：至少保留 1 名可用管理员」人工可读说明；编辑弹窗失败后按钮恢复可点（不死锁）。

## ⑥ 缺口上报（诚实降级，不臆造）

| 缺口 | 实测依据 | 页面处置 |
|---|---|---|
| `GET /api/admin/users/{id}/learning` 未注册 | 任务书预登记 + 本次 404 印证 | 详情弹窗缺口声明卡，无学习指标假数据 |
| 启停端点为 POST 而非任务书猜测的 PATCH | router.py + curl | 按实测 POST 接线，报告留痕 |
| user_admin 全域仅 ADMIN；manager 过守卫必 403 | router.py + curl 实测 40300 | 守卫三段按纪律保持 {admin,manager}；403 在错误态诚实展示 |
| 红线「唯一 admin」无法在分页列表可靠判定（后端按全库判定） | service.py 源码 + 5-admin 场景实测 | 前端仅 metrics 尽力提示，后端 40303 权威兜底 |

## ⑦ 环境留痕

同 task12 报告⑦：开工时 8000/3000 未监听，按 AGENTS.md 命令拉起（next 用 node_modules 实际路径）；全程未重启。

## ⑧ 测试数据留痕（写操作全复原）

| 对象 | 操作 | 复原 | 终态核验 |
|---|---|---|---|
| user_id=1（user000001，学生测试账号） | status 1→0（实测#4#5） | status→1（实测#6） | keyword 复查 status=1 ✓ |
| user_id=1 | role student→teacher（实测#7） | role→student（实测#7） | 复查 role_code=student ✓ |
| user_id=100003（adm02test） | status 1→0（红线探测） | **当即** status→1 | 复查 status=1+登录 200 ✓ |
| user_id=999999 / superadmin 角色 | 404/422 拒绝性探测 | 无需（被后端拒绝，零变更） | — |

数据终态与开工时一致：user000001=student/status1、adm02test=admin/status1/yn1。
