# task08 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」（task-review-critique-rule.md）
> 对象：task08 admin 账号恢复 + 全链路冒烟（Trae 报告 DONE，commit 7c91401）
> 结论：**验收通过**（3 项 GWT 实证全绿），2 条批判建议（P1/P2 级，不阻塞验收，转后续任务）

---

## 批判 1（P1）：RBAC 是"角色字符串 + 硬编码"，无权限模型扩展点

**问题描述**：实测 manager 访问 `/api/admin/users` 返回 403（admin 200 / student 403 均符合 GWT）。核查 `edu-agent/app/auth/dependencies.py`：RBAC 为 `require_role([ADMIN])` 参数化角色白名单，角色仅是 JWT 里的字符串（`UserRole` 枚举），无独立 permission 表/角色-权限映射表（数据库实测：仅 `org_staff_role`，无 `permission`/`rbac` 表）。这意味着：新增细粒度权限（如 manager 可管订单但不可管用户）需改代码硬编码白名单，无法配置化。

**证据来源**：
- 实跑：admin 200 / student 403 / manager 403（2026-08-18 实证）
- `edu-agent/app/auth/dependencies.py` require_role 源码（白名单集合判断）
- 数据库 `SHOW TABLES LIKE '%permission%'` = 空；`%rbac%` = 空
- task08 报告 §3 角色分布（admin 5/manager 3/teacher 3/student 189）

**与前沿差距**：主流方案（RBAC 表模型：role/permission/role_permission 三表 + 中间件加载）支持配置化授权与审计；当前方案在 66 表重构中 `org_staff_role` 存在但未启用细粒度权限，管理端补全（task70~91）涉及多角色多模块时会暴露扩展性短板。

**优化方案**：task70~91（管理端补全）实现时评估——若需要 manager/teacher 可操作管理端部分模块，则补 `role_permission` 映射（数据表）+ require_role 改为查映射；若管理端仅 ADMIN 使用，则保持现状并在 doc-architect 注明"单一管理员模型"决策。

**最小验证方法**：task08 报告 §3 中 manager 403 的预期判定——若设计意图是"manager 也有管理端权限"，则此为缺陷需修；若"仅 ADMIN"，则现状正确。

**预期收益与成本**：收益=避免管理端补全阶段返工；成本=0（仅决策记录，需在 task70 前确认）。

---

## 批判 2（P2）：100K 生成用户无 auth 记录，"全链路"冒烟未覆盖真实用户登录场景

**问题描述**：报告 §5 声明"100K 生成用户无 auth 记录（生成脚本不写 sys_user_auth），仅 188 个注册用户有 auth"。实测确认：登录验证只能用 adm02test/mgr01test/stu01test 三个手工账号。这意味着：①full 档 10 万用户无法登录系统（若生产意图是用户可登录，需批量生成 auth）；②冒烟链路步骤 1-2 实际只验证 3 个账号，未验证"100K 用户中的任一登录"。

**证据来源**：
- task08 报告 §5 偏差声明（100K 无 auth）
- 实测 `sys_user`=100000 vs `sys_user_auth` 仅 188+（需 task09 后登录改造时处理）
- 生成脚本 layer1 只写 sys_user 不写 sys_user_auth（报告 §5 + edu-data 源码）

**与正确做法差距**：数据基线"10 万用户"若用于演示/压测，登录是核心路径；无 auth 的用户在管理端用户列表可见、但无法参与登录态功能。

**优化方案**：①明确意图——若 full 档目标是"业务数据丰富度"，则 10 万用户无 auth 可接受（注册用户走真实注册）；②若需要可登录批量用户，在 task09~14（认证改造）或数据重灌脚本中补 `sys_user_auth` 批量生成（bcrypt 预哈希，复用 restore_admin.py 的哈希逻辑）。**需编排者与用户确认**。

**最小验证方法**：用户确认后决定；若选②，验证 = 随机抽 10 个生成用户可登录。

**预期收益与成本**：收益=登录态 E2E/压测可用全量用户；成本=视选择 0 或 1~2h（批量 auth 生成）。

---

## 总评

| GWT | 结果 | 证据 |
|-----|------|------|
| ① admin/manager 登录 + RBAC（admin 可进/student 不可） | ✅ | admin 200 / student 403 / manager 403(预期) |
| ② 全链路冒烟 | ✅ | 35/35 PASS（实跑 smoke_test.py，exit 0） |
| ③ CP2 检查点 | ✅ | 报告 + 实证 |

**批判 1/2 不阻塞本次验收**（均属后续任务决策点）；验收通过。
