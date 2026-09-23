# TO-EXEC-TA1-3 — 流式双端定因修复 → 黄条视觉实证（yy 十点修复 · P0 · chat.html 同文件串行链）

> 分支 `feature/opt-waves`；后端 9988 / 前端 3322（Next16 Turbopack dev 态）在岗。本开工令自包含。**TA1 与 TA3 必须同一执行者串行做**（同改 chat.html，禁止并行双写）。

## 背景

owner 多次实测「流式输出从未生效」，且「AI 谎报自动黄条警示」从未见过。既有事实（编排者已核）：
- 后端 SSE 契约：`POST /api/chat/stream`，body `{query, session_id, stream:true}`（字段是 `query` 不是 `message`）；事件 `start|retrieval|token|done|error`，token 事件增量在 `j.delta`（`app/chat/router.py:9,281`、`app/chat/sse.py`）。
- 静态页 `edu-frontend/public/chat.html` 有 `.receipt-warn` CSS/JS（约 :174-178），但从未视觉验证过。
- React 侧 `/chat` 路由在 `edu-frontend/src`（chat 相关页面+api-client）。
- 前提挑战 P1/P3 裁定：**双端 CDP 抓帧定因先行，定界前不动手修**；黄条同样先 CDP 构造触发实证断点。

## 工作项 · TA1（流式）

1. **定因（先测后修，结论落报告）**：
   - 后端层：`curl -N` 直打 `POST /api/chat/stream`（登录 student `user000001 / Test@123456`，字段 `account`），断言 token 事件逐帧到达且 `j.delta` 增量非空。若后端在此层就断（一次性吐全量/无 token 帧），修复面升级后端——如实上报，勿静默改前端掩饰。
   - 前端层（CDP，禁 Playwright）：分别打开 `http://127.0.0.1:3322/chat.html` 与 React `http://127.0.0.1:3322/chat`，发起真实提问，抓 SSE 帧→DOM 渲染时序（fetch/XHR 事件 + MutationObserver 时间线），定位断点（如：读了 `data.token` 弃用字段、未按 `data:` 行解析、一次性 innerHTML 覆盖、缓冲未 flush）。
2. **修复**：断点在哪修哪。React 侧改动最小化；静态页改动不得破坏 `docs/dom-hooks-frozen.md` 冻结钩子（若修复必须增删 hook，同步跑 `node scripts/gates/dom-hook-inventory.mjs --page <url> --check --out test-reports/gate-single` 并把新基线写入报告）。
3. **自验**：双端各 3 次真实提问，CDP 时间线证据显示逐字渐进渲染（多次 token→DOM 增量），非一次性出全文。

## 工作项 · TA3（黄条，TA1 完成后）

4. **构造触发**：用能让完成语义与凭据缺失的问法触发 `receipt_guard`（`app/chat/receipt_guard.py`：写类完成语义∧无 success 凭据→`tool_receipt_unverified`）——先读该文件词表选稳定话术；后端响应字段先 curl 断言真含警示字段。
5. **视觉实证+修复**：CDP 截图黄条在 chat.html 真实可见；若渲染路径断（CSS 类名不匹配/时机在 innerHTML 覆盖后被冲掉），修 chat.html 渲染时序。产出**稳定触发话术**（连续 3 次触发成功）。
6. **话术进手册**：`docs/面试演示-逐步点击手册.md` 增补「黄条演示站」（话术原句+预期现象+截图路径）；`docs/用户使用手册.md` 同步一节。

## 契约冻结

若修复需改 SSE 帧消费结构，**先在本报告冻结「SSE 前端消费契约」小节（事件名/字段/解析顺序）再动 React chat 代码**；禁止顺手改后端 SSE 输出结构（下游有 blind-test 依赖）。

## 铁律

- 只许改：`edu-frontend/public/chat.html`、`edu-frontend/src` 内 chat 相关文件、两本手册、（必要时）`docs/dom-hooks-frozen.*` 与 g3 基线。禁碰 `.env`（TA2 在改）、permission_gate/receipt_guard 后端代码（除非定因证明后端断，且须先停手上报裁定）。
- 3322 是 Turbopack dev：改 React 后直接热更，禁判形 webpack-hmr 404。
- 禁 DB 直写；SQL 参数绑定；不 push。两段各一 commit：
  - `fix(fe)/ta1: chat 流式双端定因修复(逐字渐进渲染)+SSE 消费契约冻结`
  - `fix(fe)/ta3: 黄条视觉实证修复+稳定触发话术进手册`
- 与 TA2/TA4 并行无文件交集；若 TA2 重启后端撞你的 curl/CDP 窗口，等探活恢复后重跑，报告记时间戳。

## 报告

`.ai-hub/plans/artifacts/dispatch/REPORT-TA1-3.md`：定因结论（双端时间线证据，先测后修顺序可追溯）、SSE 消费契约小节、修复 diff 摘要、双端 3/3 渐进渲染证据、黄条 3 次触发截图路径、话术原文。编排者将亲跑 curl+CDP 复现。

## owner 验收口径（GWT）

Given 服务在岗，When owner 在两个聊天界面（React /chat 与静态 chat.html）各提问一次，Then 看到逐字打字机效果而非转圈后整段弹出；When owner 照手册话术提问，Then 界面上看到黄色警示条。各亲测 3 次。
