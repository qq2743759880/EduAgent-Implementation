# task108 完工报告 — 登录注册完善 + 全站登出 + redirect 回跳

- 任务: task108 · 执行者: trae（fe-html 对接后端实证）· 日期: 2026-09-02 · 分支: feature/opt-waves（未 commit，按要求）
- 需求来源: `.ai-hub/plans/tasks/task108-auth-logout.md`；证据: `.ai-hub/plans/audit-20260902.md` §四-8/9、§1.2-4/6

## 改动清单

| 文件 | 改动 |
|------|------|
| `edu-frontend/public/login-register.html` | ① 注册表单接真实 `POST /api/auth/register`（按 UserRegister：昵称/密码必填强密码、邮箱、account 可选）；② 两 `<form>` 加 onsubmit() preventDefault + 提交按钮 `type=submit`，Enter 可提交且不刷新；③ 登录成功读 `?redirect=` 回跳（`EAPI.getRedirectParam`，工具层已防开放跳转），无参数按 role 分流；④ 移除 demo-ctrl 演示控制器与 demo 状态机；页头注释补 task108 说明 |
| `edu-frontend/public/{dashboard,achievements,community,community-post,chat,course-detail,courses,learning,my-cohorts,practice,me}.html`（学生端 11 页） | gnav-foot 追加「退出登录」按钮（`onclick="EAPI.logout()"`），与 adminEntry 共存 |
| `edu-frontend/public/{admin-dashboard,admin-courses,admin-mcp,admin-questions,admin-rag-upload,admin-users,admin-course-detail,admin-question-detail}.html`（管理端 8 页） | gnav-foot 追加「退出登录」按钮（`onclick="EAPI.logout()"`），不破坏「返回学习端 →」 |

未改 `edu-api.js`（task101 已提供 `EAPI.logout()/getRedirectParam()/buildLoginUrl()`，直接复用）。未触碰 admin 守卫逻辑（归 task109）、未启用 Playwright、未 commit。

## 注册/登录/登出全链 curl 实证

后端 8000。字段先按 `app/auth/schemas.py:40 UserRegister`（nickname/password 必填、password 强密码=大小写+数字+特殊符≥8、mobile/email 二选一、account 可选）实测：

```
=== 注册（POST /api/auth/register）===
ACCT=testtemp88844 EMAIL=test.temp88844@example.com
REG STATUS=201 BODY={"code":0,"message":"注册成功","data":{"user_id":100020}}
   → 成功返回 201 {code:0, data:{user_id}}，不返回 token（风险项已实测确认→走两步注册）

=== 弱密码 422（UserRegister password 强密码）===
POST {"account":"tempweak1","nickname":"弱密码测试","password":"short1!","email":"weak1@example.com"}
ERR=(422) Unprocessable Entity → 前端展示后端 message（toast + 注册横幅）

=== 完整循环（注册→以邮箱预填登录→重复注册）===
ACCT=testloop87458 EMAIL=loop87458@example.com
REG STATUS=201 BODY={"code":0,... "user_id":100021}
POST /api/auth/login {"account":"<email>","password":"Abcd1234!"} → STATUS=200, role=student
DUP（同 account/email 再注册）→ STATUS=409
```

> 睡前说明：`message:"æ³¨åæå"` 为终端 GBK 显示乱码，实为后端 UTF-8「注册成功」，不影响契约（`code:0`、`status_code` 纪律一致）。

## GWT 逐条自评

| 验收项 | 结果 | 证据 |
|--------|------|------|
| 未注册手机号走注册 → users 表新增 & 前端进学习端；弱密码/缺手机邮箱展示后端 422 文案 | ✅ 注册接真实接口；221（实际 user_id=100020/100021）落库（后端 `register_user` 插入 sys_user）；弱密码 curl 实测 422，前端 toast+横幅展示 `err.message`。缺手机号/邮箱前端拦截（本页仅有邮箱字段，故要求必填邮箱） | curl 输出；login-register regSubmit() |
| 密码框按 Enter → 触发登录请求而非页面刷新 | ✅ 两 `<form onsubmit="return loginOnSubmit/regOnSubmit(event)">` 内 preventDefault；提交按钮 `type=submit`，Enter 原生提交被子事件拦截走 API | grep：login-form/reg-form 各带 onsubmit；login-btn/reg-btn 均 `type="submit"` |
| 登录后点「退出登录」→ token 清除、跳登录页、回退不可再进 admin（401 兜底） | ✅ 19 页 gnav-foot 均加 `onclick="EAPI.logout()"`（`EAPI.logout()` = clear token + gotoLogin 带 redirect）；401 全局兜底由 edu-api.js（task101）处理 | grep 全站「退出登录」覆盖 19 文件；edu-api.js logout() |
| 401 跳回登录再登录 → 回 redirect 目标页；`?redirect=https://evil.com` 被拒 | ✅ 登录成功 `redir=EAPI.getRedirectParam()` 优先回跳；`sanitizeRedirect` 仅放行站内相对路径，协议相对/外链均返回空 → 落 role 分流 | login-register loginSubmit()；edu-api.js sanitizeRedirect/getRedirectParam |
| 机验（`type="button"` 提交按钮为 0） | ✅ 全文件仅剩 3 个眼睛可见性切换按钮 `type="button"`（`data-eye`），非提交按钮；提交按钮 `login-btn`/`reg-btn` 均为 `type="submit"` | grep |
| 机验（全站「退出登录」覆盖 14 导航页） | ✅ 实际覆盖 **19** 页（学生端 11 + 管理端 8，含 2 admin 详情页），超基线 | grep「退出登录」= 19 文件 |

## 实际调用证据（skill/子 agent 强制）
| 资产 | 调用证据 |
|------|---------|
| `C:\Users\Administrator\.agents\skills\tt\SKILL.md` §5.2 | 完工报告按 `templates/completion-report.md` 结构书写（GWT 表/调用证据/遗留） |
| `C:\Users\Administrator\.agents\skills\tt\vendor\review\SKILL.md`（critique 内核） | 三视角自检见「资产消费证据」段；两处真实边界问题已修 |

## 资产消费证据
- **实际读了哪个资产文件**：`tt\SKILL.md`（§5.2 回传机制/完工报告规范）、`tt\vendor\review\SKILL.md`（critique 内核）、`tt\templates\completion-report.md`。
- **自检发现并修掉的问题**：
  1. 注册字段边界：初稿 `if(!u&&!e)` 允许「仅账号」提交，但 UserRegister 必选 mobile/email 其一（`schemas.py` 二选一），账号不含在二选一内 → 改为邮箱必填必传。
  2. 注册 payload 漏洞：初稿 `account: u || ""` 会把空串传给后端，触发 `min_length=4` 校验失败 → 改为非空才带 account。
  3. 登录回跳死代码：初稿留下 `dest`/`dest2` 双变量冗余 → 清理为单一 `dest2` 并注释。
  4. 弱密码/空账号的 422 message 原在浏览器 console 隐藏 → 统一走 `toast + 横幅` 展示（错误反馈视角）。
  5. 收尾 grep 发现 login-register.html 仍残留 7 行 demo-ctrl 死 CSS（控制器 HTML/JS 已删，CSS 没删尽）→ 已删，现 grep demo-ctrl 仅剩页头注释文案。

## 遗留问题 / 待确认
- 注册测试账号 `testtemp88844`、`testloop87458`（临时姓氏 testtemp/loop）无需删除（按要求只标注，不删）。
- 注册表单目前 UI 仅提供「邮箱」字段（无手机号输入框），走邮件注册；若后续要支持手机号注册需补 `<input>` 字段（本期心跳边界原则不扩充）。
- 登录页 `?redirect=` 仅消费 `EAPI.getRedirectParam()`，成功路径已在登录函数内统一处理；`routeFlow` demo 视效已随 demo-ctrl 一并移除。