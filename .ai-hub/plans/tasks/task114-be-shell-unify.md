# task114 — 后端契约统一①：响应壳全站统一（冻结 C-A）

- 域：BE+契约 ｜ 平台：claude（be-architect 先行）｜ 波次：W2 ｜ 依赖：用户确认 D1/D4 默认方案
- 类型：**契约变更**（冻结单 handoffs/task114-contract.md，测试 agent 核验后解锁下游）

## 目标
全站单一响应壳 `{code:0,message:"ok",data}`，终结"前端每页双解析"。

## 证据
- audit §B4：recommender（router.py:16-35）、mindmap（router.py:14-36）、interactive 全系（quiz/vocab/coding/math）、`GET /api/users/me`（users/router.py:39-57 裸 dict + camelCase 混合 `tenantId/learningGoal/subjectPreferences/roles`）不走 ok() 壳。
- audit §X7：12 个学生页 adminEntry 依赖 users/me 的 `u.role`，是壳统一的高危消费面。
- RespWrap 中间件已存在（main.py:205-257）——优先评估"中间件统一包裹"而非逐端点改写。

## 改动点
1. 技术路线二选一并写入选型审计：① RespWrap 中间件对裸 response_model 路由统一包壳（改动小、全局生效）；② 逐端点改 ok()（显式但散）。**默认①**，users/me 单独重写为规范 snake_case UserInfo 合并视图。
2. `GET /api/users/me` 新契约冻结：`data: {user_id, account, nickname, role, learning_goal[], subject_preferences[], ...}`（snake_case，role 为字符串枚举）——12 页 adminEntry 与 me.html 消费点回归。
3. DashboardOut 扩展（D4）：增 `total_questions_attempted, active_courses_count`（来源 DB 实证有数据）。
4. 契约单写真实 curl 示例（至少 users/me、quiz/next、series 列表、progress/dashboard 四条），交 codex L1/CDC 核验。

## GWT 验收
- `curl -s http://127.0.0.1:8000/api/recommend/next -H "Authorization: Bearer <student>"` → `{code:0,message:"ok",data:{...}}`（jq 断言 .code==0）；mindmap/interactive 同断言。
- users/me 返回 snake_case 且含 `role`；12 个学生页 adminEntry 逻辑回归通过（结构断言 role 判定）。
- 前端 edu-api.js 的"裸 JSON 原样返回"兼容分支可保留（壳化后全部走解包），回归 community/dashboard 页。
- 回归：interface_acceptance_final.py + 前端 vitest 全绿；openapi 文档（/docs）response_model 全部可推导。

## 风险
- 中间件包壳可能双重包裹已手工 ok() 的端点 → 方案①实现须按"响应已是壳则跳过"幂等；该边界写入契约单。
- confidence 0.75（规划自审 Eng 条目）：缓解 = 冻结前 grep 前端全部取值点 + 分域灰度合入。
