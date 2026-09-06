# task02 完工报告（reshape-a 批次）：login-register.html 回归加固

日期：2026-09-06 ｜ 执行：fe-html 接线 agent ｜ 计划：`.ai-hub/plans/dev-plan-reshape-a.md` A 批次 task02
（注：`test-reports/task02-completion-report.md` 为历史批次同名报告，与本批无关，故本报告加 `-reshape-a` 后缀）

## ① 改动文件 + 行数

- `edu-frontend/public/login-register.html`：+67 / −11（git diff --stat）
  - 新增 `fmtApiErr(err)`：EAPI 错误 → 诚实提示映射（401→40111 账号或密码错误；422→解析 `err.body.data` 数组拼字段级消息；超时→EAPI 原生超时文案；其余→后端 message）
  - 新增 `markFieldErrs(err, map)` + `LOGIN_FIELD_MAP`/`REG_FIELD_MAP`：422 命中字段点亮既有 `.ferr` 行内错误 + `input.err`（纯复用页面现有样式/元素，零新 UI）
  - 新增 `setBtnBusy(btn,on)`：`busy` 类 + `disabled` 属性双保险防重复提交；`loginSubmit`/`regSubmit` 及注册自动登录降级路径全部改走该函数
  - `showLoginBanner`/`showRegBanner` 增加可选 `code` 参数：横幅 `<code>` 动态显示实测 `status · code`（默认值不变）

## ② 资产消费证据

- 读完 `AGENTS.md`（教训 2 禁 Playwright 用 curl、教训 8 真实契约优先于页面注释、教训 9 禁 match 取参——本页未取 URL 参数，无违反点）
- 读完 `.ai-hub/plans/dev-plan-reshape-a.md` task02 GWT（登录 account 字段 / 注册即登录 / 401 / role 跳转 / redirect 站内校验）
- 读完 `contracts/reshape-a.json`（POST /api/auth/login、POST /api/auth/register 在冻结端点清单，hash 30aeddbe，未改）
- 读完 `edu-frontend/public/edu-api.js` 头部注释 + 全文（EAPI.post、getRedirectParam、401 单飞 refresh 通道）
- **自检发现并修掉**：
  1. EAPI 对 HTTP 401 走 `handleUnauthorized`，**丢弃后端 body**（`edu-api.js:196-200`），页面原样展示会变成"登录凭证无效或已过期"——对输错密码的用户是误导。修复：页面按 curl 实测口径把登录接口的 401 映射回"账号或密码错误（40111）"（登录页上 401 只可能来自 login/register 调用本身，无歧义），并在"缺能力登记"记录该客户端限制。
  2. 提交按钮只有 `busy` 类**没有 disabled**，请求在途可重复点击 → 双重提交。修复：`setBtnBusy` 双保险。
  3. 422 时 EAPI 抛出的 message 是 pydantic 英文首条（如 "String should have at least 4 characters"），不字段化。修复：解析 `err.body.data` 数组拼"字段错误（42200）：account：…"并点亮对应行内 `.ferr`（横幅注释本来就写明"命中字段追加行内错误"，此前未实现）。

## ③ curl 实测证据（POST http://127.0.0.1:8000/api/auth/*）

| # | 请求 body | 实测响应 |
|---|---|---|
| A | login `user000001/Test@123456` | 200 `{"code":0,...,"data":{"access_token":"eyJ...","user":{"role":"student",...}}}` |
| G | login `adm02test/Test@123456` | 200 → `role= admin`（role 分流锚点 admin→admin-dashboard.html 实证） |
| B | login `user000001/Wrong@999` | **401** `{"code":"40111","message":"账号或密码错误"}` |
| B' | login `no_such_user_xx/...` | **401** 同上（不泄漏账号存在性） |
| C | login `{"account":"ab","password":"x"}` | **422** `{"code":"42200","message":"String should have at least 4 characters","data":[{"loc":["body","account"],"msg":"...","ctx":{"min_length":4}}]}` |
| H | login 缺 password | **422** `{"code":"42200","message":"Field required","data":[{"loc":["body","password"],...}]}` |
| D2 | register 重复邮箱 | **409** `{"code":"40914","message":"该邮箱已注册"}` |
| E2 | register `not-an-email` | **422** `{"code":"42200",...,"data":[{"loc":["body","email"],"msg":"value is not a valid email address..."}]}` |
| F | register 弱密码 `123` | **422** `{"code":"42200","message":"String should have at least 8 characters",...}` |

页内 JS 语法：抽取内联 script `node --check` 通过（SYNTAX_OK）。未重启 3000/8000 服务。

## ④ 批判承接核对

无承接项（tech-critique 未对 task02 登记承接条目）。

## ⑤ 自检三视角

- **交互态**：提交在途按钮转圈（busy 类既有动画）+ `disabled` 防重复，失败/降级路径按钮恢复可点，成功路径 400ms 后跳转无需恢复。
- **边界**：注册自动登录失败降级路径回归确认——仅复位按钮 + 回登录 Tab + 预填账号（`li-id = u||e||n`），不清已填内容、不阻断手动登录；`?redirect=` 仅接受站内相对路径（EAPI.getRedirectParam 防开放跳转，回归未动）。
- **错误反馈**：401/409/422/超时各有诚实文案（后端原文优先，401 按实测 40111 口径映射），422 附加字段级行内错误点亮，横幅 code 位显示真实 `status · code`。

## 缺能力登记（edu-api.js 只修不增，未自行扩展）

- `EAPI` 的 401 通道（`handleUnauthorized`）不携带后端 body/message，登录页无法直接读到"账号或密码错误"原文，只能在页面按实测口径映射。若后续允许客户端改动，建议 401 时 `apiError` 附上 `err.body` 再抛（登记，不动代码）。
- 页面 toast 与 EAPI 默认错误 toast（task122 注入）会同时出现且同为底部居中，存在视觉叠放；属全局既有行为，非本页引入，未处理。
