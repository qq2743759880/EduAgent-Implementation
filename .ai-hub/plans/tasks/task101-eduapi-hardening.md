# task101 — edu-api.js 壳客户端加固

- 域：FE ｜ 平台：trae（备援 openclaw）｜ 波次：W0 ｜ 依赖：无（S1 先行）｜ 契约：不改动后端
- 文件：`edu-frontend/public/edu-api.js`（58 行）+ 各消费页最小适配

## 目标
把全站唯一共享客户端修成可靠的鉴权/错误底座，是后续所有 FE 任务的基建。

## 证据
- audit §1.3：L33-43 401 分支要求 `code` 为字符串才清 token（数字码 40101、FastAPI `{detail}`、非 JSON 网关错误全部漏接）；非 JSON 错误 `return null` 被当成功。
- L7 BASE 硬编码 `http://127.0.0.1:8000`；无超时；401 跳转不带 `?redirect=`；无 logout 方法；错误统一 `catch(function(){})` 静默吞。

## 改动点
1. 401 判定改为：`resp.status === 401` 即清 token + 跳 `login-register.html?redirect=<当前路径+query>`。
2. 非 2xx 且非 JSON / 壳外错误：抛带 status 的 Error，**禁止 return null**。
3. `EAPI.BASE` 支持覆盖：`window.EDU_API_BASE || location.origin.replace(:3000,:8000)` 级联 + 默认 127.0.0.1:8000。
4. fetch 加 AbortController 超时（默认 15s，SSE 除外——chat 页用原生 fetch 不经此通道）。
5. 新增 `EAPI.logout()`（clear + 跳登录）与 `EAPI.onError(fn)` 全局错误钩子（task122 接 toast）。
6. 登录页解析 `?redirect=` 并在登录成功后回跳（与 task108 分工：本任务只提供参数读取工具，登录页改动归 task108）。

## GWT 验收
- Given 无 token，When `curl -s http://127.0.0.1:8000/api/users/me`（DEBUG=False），Then 401 且壳 code="40101"；浏览器端过期 token 访问任一接入页自动跳登录页且地址带 redirect。
- Given 后端 8000 停机，When 页面发起请求，Then 控制台可见 Error 且 onError 钩子触发，**不再出现静默 null**。
- Given token 正常，When 正常请求，Then 行为与现状一致（回归：community/dashboard 页数据照常）。
- 机验：`grep -c "catch(function(){})" edu-frontend/public/*.html` 只减不增（本任务先改 edu-api.js 自身，页面级静默吞归 task122）。

## 风险
- 401 行为变严可能暴露原先被吞的隐性失败 → 验收含 12 个学生页冒烟走查；独立 commit 便于一键回滚。
