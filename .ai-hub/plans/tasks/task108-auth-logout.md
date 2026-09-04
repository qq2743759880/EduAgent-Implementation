# task108 — 登录注册完善 + 全站登出 + redirect 回跳

- 域：FE ｜ 平台：trae ｜ 波次：W1 ｜ 依赖：task101（EAPI.logout、redirect 工具）
- 文件：`login-register.html` + 全站 gnav（登出入口）

## 目标
补齐鉴权动线最后三块：真注册、表单可用性（Enter）、登出与回跳。

## 证据
- audit §四-8/9：regSubmit L3016-3030 从不调 `/api/auth/register`，默认态点"创建账号"700ms 后无任何反馈；两个 form 无 onsubmit 且按钮 type=button → Enter 原生提交刷新丢状态。
- audit §1.2-4/6：全站无登出按钮、无 store.clear 调用；login-register 宣称 `/login?redirect=` 流程但未实现解析。
- 后端契约：`POST /api/auth/register`（UserRegister：nickname/password 必填强密码，mobile/email 二选一，account 可选）；`POST /api/auth/login {account,password}` → `data.user.role`；`POST /api/auth/refresh`。

## 改动点
1. 注册表单接 `POST /api/auth/register`：字段按 UserRegister（昵称/密码/确认密码/手机或邮箱二选一）；成功后自动登录（复用登录）或提示去登录——取改动小者并写进页头注释。
2. 两表单加 onsubmit preventDefault + 提交按钮 type=submit；Enter 即提交；重复提交防抖。
3. 登录/注册成功后读 `?redirect=` 回跳（仅允许站内相对路径，防 open redirect）。
4. 全站 gnav-foot 增"退出登录"：调 `EAPI.logout()` → 清 token 跳登录页（admin 端 6 页与学生端同步添加）。
5. 登录后按 role 跳转保持现状（admin/manager→admin-dashboard，student→dashboard，AGENTS.md 教训⑤）。

## GWT 验收
- When 用未注册手机号走注册流程，Then 后端 users 表新增记录（DB 实证）且前端进入学习端；弱密码/缺手机邮箱时展示后端 422 字段错误文案。
- When 在密码框按 Enter，Then 触发登录请求而非页面刷新。
- Given 已登录，When 点任意页"退出登录"，Then token 清除、跳登录页，回退浏览器不可再进 admin 页（401 兜底）。
- When 从 401 跳转回登录页再登录，Then 回到 redirect 目标页；`?redirect=https://evil.com` 被拒绝（只回站内）。
- 机验：`grep -c "type=\"button\"" login-register.html` 提交按钮为 0；全站 `grep -l "退出登录" *.html` 覆盖 14 个导航页。

## 风险
- 注册成功自动登录需后端 register 不返回 token（实测确认），若不返回则走"注册→预填账号→登录"两步。
