# task109 — 管理端角色守卫

- 域：FE ｜ 平台：trae ｜ 波次：W1 ｜ 依赖：task101（EAPI 方法）
- 文件：6 个 admin-*.html + 2 个 admin 详情页（共 8 页）

## 目标
管理端页面具备真实路由守卫：无 token 跳登录、非 admin/manager 角色拒绝并回学习端，杜绝"学生 token 静默打 admin API 被吞错"。

## 证据
- audit §1.2-5：admin-*.html 仅把 `.page-head .sub` 文案改成登录提示，不校验 role、不重定向；admin-questions.html 连提示都没有。
- 后端中间件对 `/api/admin/*` fail-closed 强制 Bearer + 角色校验（auth_middleware.py:135-140），前端 401/403 会被 catch 吞掉，页面呈现"空白演示态"而非明确拒绝。
- 角色来源：登录响应 `data.user.role`（admin/manager/student/teacher）；页内可调 `GET /api/auth/me` 复核。

## 改动点
1. 统一守卫片段（入 8 页或抽 `edu-guard.js`）：无 token → `location.replace("login-register.html?redirect=<当前页>")`；有 token → `GET /api/auth/me` 校验 role ∈ {admin, manager}，否则 `location.replace("dashboard.html")` 并提示。
2. 守卫先行（阻塞渲染数据请求）：守卫未通过前不发 admin API 请求。
3. `GET /api/auth/me` 失败（网络/服务停机）按"无权限"处理跳登录，不静默。
4. 守卫逻辑全站一致：与学生端 adminEntry 显隐逻辑（按 /api/users/me role）并存，避免两套 role 判定打架——统一以 auth/me 为准，users/me 仅作展示。

## GWT 验收
- Given 无 token，When 直接打开任一 admin-*.html，Then 立即跳登录页且带 redirect 参数，**不发任何 admin API 请求**（Network 面板实证）。
- Given student token，When 打开 admin-dashboard.html，Then 跳回 dashboard.html 并见"无管理权限"提示。
- Given manager token，When 打开 8 个 admin 页，Then 全部正常进入（manager 权限按后端 ADMIN/MGR 口径放行）。
- 机验：8 页均含守卫调用（grep 脚本断言）；守卫脚本在数据注入 IIFE 之前执行（DOM 顺序断言）。

## 风险
- 每页多一次 /api/auth/me 请求，8 页管理端可接受；若后续嫌多，可与 task114 冻结的 users/me 合并复核（不在本期）。
