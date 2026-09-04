# task114 · W1-C4 批判项「注册两步式登录 UX」完工报告

- 执行 agent：W1-C4 批判执行 agent（随 task114）
- 优先级：P2
- 日期：2026-09-04
- 目标：注册成功后优化体验（自动登录 / 明确提示引导），消除「注册成功 → 再手动登录一次」的两步割裂。
- 改动面：仅 `edu-frontend/public/login-register.html`（内联 JS `regSubmit` 成功分支）。未改后端契约、未改 `edu-api.js`、未 commit。

---

## 1. 资产消费证据段

| 资产 | 路径 | 消费方式 | 自检产出 |
|------|------|----------|----------|
| ponytail | `C:\Users\Administrator\.agents\skills\ponytail\SKILL.md` | 全文读取，`full` 强度 | 采用「复用既有 loginSubmit 的 token 写入 + 角色跳转锚点」，最小 diff：仅改 `regSubmit` 的 `.then` 成功分支，未新增任何抽象/工具/全局变量 |
| tt | `C:\Users\Administrator\.agents\skills\tt\SKILL.md` §5.2 | 读取 §5.2「回传机制 / 独立实证 / 资产调用硬约束」 | 独立实证不采信注释契约：真实 HTTP 起新实例验证 register 尾部契约；报告含「资产消费证据」+ 矩阵 |
| ui-ux-pro-max | `C:\Users\Administrator\.agents\skills\ui-ux-pro-max\SKILL.md` | 读取（UX 判断） | 类别 2「Touch & Interaction」（Loading feedback、禁止 0ms 瞬变）→ 自动登录期间保留 `btn.busy`（loading）并在跳转前 `setTimeout 400ms` 给足反馈；类别 8「Forms & Feedback」（错误就地、渐进披露）→ 失败时 toast-error 就地提示并回落登录页 |
| review | `C:\Users\Administrator\.agents\skills\tt\vendor\review\SKILL.md` | 读取 + critique 三视角自检（交互态/边界/错误反馈） | 见 §5 逐批判记录 |

**agent×skill×workflow 矩阵**

| 环节 | agent | skill / 内核 | 产物 |
|------|-------|--------------|------|
| 契约实证 | W1-C4 执行 agent | （HTTP/DB 实测，非 skill） | register 尾部实测结论（§2） |
| UX 最小改动 | W1-C4 执行 agent | ponytail（full） | `regSubmit` 成功分支 auto-login |
| UX 判断 | W1-C4 执行 agent | ui-ux-pro-max 类别 2/8 | loading + 失败回落策略 |
| 完工自检 | W1-C4 执行 agent | review critique 三视角 | §5 |
| 纪律 | W1-C4 执行 agent | tt §5.2 独立实证 + §6 静态页纪律 | 不采信注释、不改后端契约、不 commit |

---

## 2. register 响应实测结论 —— **情况 B（无 token）**

- **后端真实契约（读取源码 + 真实 HTTP 双确认）**：
  - `app/auth/router.py`/`service.py`：`POST /api/auth/register` → `201 {code:0, message:"注册成功", data:{user_id}}`；默认角色 `student`；重复注册 → `409 {code:"40912", message:"该登录账号已被注册"}`。
  - `POST /api/auth/login` → `200 {data:{access_token,refresh_token,user:{role}}}`；注册后自动 login 可成功进入。
- **真实 HTTP 独立实证**（用项目自身 `.venv` 在 8002 起新实例，避免污染线上 8000）：
  - register：`201`，`data` **仅含 `user_id`，无 `access_token`** → 确认 **Situation B**，**不能靠 register 直接自动登录**。
  - register 后立即 login（account / email 均可）：`200 role=student`，返回 `access_token`+`refresh_token` → **自动 login 一次即可写 token 并进入**。
  - /me（Bearer）→ `200`：token 可访问受保护接口。
  - 重复注册（同 account）：`409 code=40912`「该登录账号已被注册」→ 冲突提示保留。
  - 非法 account（含 `@`）：`422 code=42200`「账号只能包含字母、数字、下划线和连字符」 → 前端肉测分支 422 亦不弱化。

> ⚠️ **线上 8000 部署差异（发现项）**：线上 8000 实际由 `Z:\anaconda3\envs\kb311\python.exe` 运行（非仓库 `.venv`），其对新注册账号走 **email 可登录、account 不可登录**（同一条记录、同一 hash，却 account 401/email 200，逻辑上不可能，判定为陈旧进程/数据）。而仓库当前源码（8002 实测）account/email 均正常。按「真实契约优先 + 当前源码为权威」，auto-login 取 `u || e` 兜底自动适配两种情形（账户或邮箱任一命中即进）。**建议部署后重启 8000 至当前源码并复验**。

---

## 3. 采用方案：**情况 B（自动 login + 明确提示 + 一步进入）**

由于 register 不返回 token，无法「注册即登录」，故采用：注册成功后 **立即自动调用一次 login**（用用户刚提交的登录账号 `u || e` + 密码 `p`）→ 写 token → 按角色跳转。体验从「两步」降为「一步」，消除了二次手动输入。

**改动说明**（仅 `login-register.html` 内联 JS `regSubmit` 成功分支）：
1. 注册成功 `then` 内：调用 `EAPI.post("/api/auth/login", {account: u||e, password: p})`（login 账号取与 register 推导 `account>email` 兜底一致的 `u||e`）。
2. login 成功：`EAPI.store.setToken` + `setRefreshToken(d2.refresh_token)`（对齐 W1-C1 持久化）；`data2.user.role` 角色分流复用 login 同款锚点 → admin/manager→`/admin-dashboard.html`，否则→`/dashboard.html`；优先 `?redirect=`（`EAPI.getRedirectParam` 已防开放跳转）。toast「注册成功，已自动登录，正在进入…」+ `setTimeout 400ms` 跳转。
3. 自动 login 失败：**静默降级** → 移除 `busy`、toast「账号已创建，自动登录失败，请手动登录」、`setPage("login")` + 预填 `li-id = u || e || n`（保留原「预填账号」兜底，不丢失登录凭据）。
4. 原 inner `catch` 注册失败分支（409 冲突/422/网络错误）不变，`toast-error` + `showRegBanner` 提示未弱化。

复用：`loginSubmit` 的 token 写入/角色跳转/`getRedirectParam` 逻辑、`toast`、`setPage`、`btn.classList.busy`。未新增全局。

---

## 4. 独立实证

- **register → 自动 login → token 写入 → 角色跳转**：真实 HTTP（8002 新实例）register `{user_id}` → login 200 返回 `access_token`+`user.role=student` → /me 200（token 有效）→ 按既有锚点跳转 target = **`/dashboard.html`**（student 默认；admin/manager 走 `/admin-dashboard.html`）。`dashboard.html`/`admin-dashboard.html` 均存在。
- **重复注册失败提示**：同 account 二次 register → `409 40912`「该登录账号已被注册」，前端走 `showRegBanner` 提示保留。
- **JS 语法**：全部内联 `<script>` 经 Node `new Function` 校验通过。
- 清理：测试临时账号已从 DB 删除（`account LIKE 'w1c4%'`），临时 8002 实例已停止，临时脚本已删。

---

## 5. 边界 / 逐批判记录（review critique 三视角）

| 视角 | 批判发现 | 处置 |
|------|----------|------|
| 交互态 | 自动登录期间若按钮脱离 busy 会显得「卡住」 | 保留 `btn.busy` 直到登录成功跳转或失败回落才移除；跳转前 toast + 400ms 延迟给足反馈（ui-ux-pro-max 类别 2：loading + 非 0ms 瞬变） |
| 边界 | register 只返回 user_id，不能盲目假设返回 token | 实测定为 Situation B，不写「注册即登录」死逻辑，改走自动 login 一次 |
| 边界 | 自动 login 失败时用户不能丢登录能力 | 静默降级回落登录页并预填 `u||e||n`，保留手动登录路径 |
| 错误反馈 | 重复账号/弱密码/非法输入的提示不能弱化 | 外层 `.catch` 未动，`409/422/400` message 仍经 `showRegBanner` 就地展示 |
| 契约 | 线上 8000 陈旧实例 account 登录异常 | 已定位为部署差异（§2）；auto-login 用 `u||e` 双标识兜底自动适配，不依赖单一标识；建议部署重启复验 |

**跨越/未做项**：不改后端 `/api/auth/register` 契约（超出范围）；未 commit（纪律要求）。

---

**结论**：采用情况 B（register 无 token → 自动 login 一次写 token → 按角色跳转），一步进入，消除两步割裂；失败静默降级保底。改动仅 `login-register.html`，diff 最小，后端契约零改动。