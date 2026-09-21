# GATE-V3 数据就绪稳定窗机制（T9）

> 2026-09-22 · AUTO20 T9 · 只涉 `scripts/gates/**`；生产页面 `public/*.html`、`theme.css`、后端契约零触碰。

## 1. 问题：门禁对「数据未就绪竞态」无稳定态探测

三只浏览器门禁（G6 style-dep / G7 viewport-a11y / G9 state-matrix）的采样时序是
「navigate → 固定 settle（`EDU_GATE_SETTLE_MS`，默认 900ms）→ 采样」。页面数据加载慢于 settle 时，
采样落在骨架屏 / 占位 / 半渲染态上，产生**假红**。已实证三类（GATE-V2 报告 §7.3/§7.1/§8 移交项②）：

| 类别 | 实测案例 | 症状 |
| --- | --- | --- |
| ① 动画/骨架数据未就绪 | courses `reduced-motion` running animations=25 | 复跑即绿 |
| ② 卡片未就绪 | my-cohorts `tab-reachable` 14/31（17 unreachable） | 复跑即绿 |
| ③ 慢 API 未返回 | me 页 `/api/trade/orders` 2.1s vs settle 900ms → tab-reachable 8 unreachable 假红 | 手工调 `EDU_GATE_SETTLE_MS=3500` 才绿 |

现状靠**手工调 settle 环境变量**，本质是猜一个更大的固定等待——机制问题没有解决。

## 2. 修法：数据就绪稳定窗（机制化，非调参）

`_shared.mjs` 新增（`createBrowser` 返回对象上）：

### 2.1 网络空闲追踪

`Network.enable` 之上挂三个事件计数器：`requestWillBeSent` 入集（排除 ws:/devtools:/data:），
`loadingFinished` / `loadingFailed` 出集。`browser.pendingRequests()` 返回在途请求数。
由 CDP 真实网络事件驱动，不猜、不轮询 URL。

### 2.2 `waitForReady(snapshotFn, readyTimeoutMs?, pollMs?)` 稳定窗

采样前轮询至「**网络空闲** + **连续两次 DOM 快照一致**」才放行采样：

- **Phase 1 网络空闲**：在途请求数=0 且**持续保持 pollMs（250ms）**才通过——CDP 事件经 socket
  异步到达，单次空闲观测可能撞上「requestWillBeSent 尚未处理」的窗口，故要求空闲**持续**而非瞬时。
- **Phase 2 DOM 双一致**：连续两次 `JSON.stringify(snapshot)` 相等才通过。先例 = GATE-V2 W2 的
  `settledAttrs`（aria 双一致采样）；本机制把它推广到三只门禁的完整采样表达式
  （A11Y_EXPRESSION / INSPECT_EXPRESSION / LAYOUT_EXPRESSION / ATTRS_EXPRESSION）。
- **上限不阻塞**：`EDU_GATE_READY_TIMEOUT_MS`（默认 5000，0=禁用走纯 settle 旧行为）。超时返回
  `{settled:false, reason:"network-busy"|"dom-unstable", waitedMs, polls}` 并**按现状采样**——
  超时是信息不是失败：`settled:false` 只落在报告 JSON 的 `readyWindow`/`readyWindows` 字段供排查，
  不新增检查项、不改变任何 check 的判定（防「窗口超时自己造红」）。
- 每次轮询都跑门禁**自己的采样表达式**做双一致比对，与实际采样同一代码路径（无第二套判定逻辑）。

### 2.3 三只门禁采样点接入

| 门禁 | 接入点 | 说明 |
| --- | --- | --- |
| G6 style-dep | `navigate` 后、`INSPECT_EXPRESSION` 采样前 | courses 动画/骨架类假红的直接解 |
| G7 viewport-a11y | ① 5 个 viewport 每次采样前（readyWindows 留痕）② **Tab walk 前** | ②是关键：tab walk 是**重新 navigate**（settle 只给 `min(settleMs,500)`），慢查询在 walk 里重新开始；不给 walk 前加稳定窗，晚渲染卡片（如 3s 后才落地的订单卡）会在 walk 中缺席 → 假 unreachable。负控 D 实证此缺口 |
| G9 state-matrix | 仅 mock 驱动三态（empty/disabled/long-text）采样前 | hold/fail 态（loading/error/forbidden/token-expired/server-500）**按语义豁免**：loading 态设计上就挂起全部 /api/ 请求，等网络空闲只会烧满超时；这些态已有既有 transitional 轮询兜底 DOM 形状。G9 的 Fetch.* 是其状态 mock 所有权，稳定窗只读网络空闲计数，不与 Fetch 拦截冲突 |

### 2.4 负控钩子（防假绿的双向验证工具）

`browser.setApiDelay(EDU_GATE_DELAY_API_MS)`：经 CDP `Fetch.enable`（仅 127.0.0.1/localhost 的
`/api/*`）+ `continueRequest` 延迟放行，把「快本地后端」变成「慢生产后端」复现竞态。幂等；
G9 **不接线**（其 Fetch 所有权归状态 mock）。

## 3. 语义不变性（铁律 3 自检）

- 三门禁全部既有检查**一条未删**；G7 tab-reachable 聚合（radio/roving groupKey）、G9 N/A 白名单
  （na-pages.json + SKIP）、G6/G7 冻结基线合并（--update-baseline）语义全保留。
- 稳定窗只**改变采样时机**（就绪后采样），不改变任何判据；超时回退行为=旧行为（按现状采样）。
- `EDU_GATE_READY_TIMEOUT_MS=0` 完整还原旧路径（负控即用此模式复现假红）。
- 社区已知坑不回退：community-post 带 `?post_id=96`（ROUTE_QUERY 既有）全程保持。

## 4. 负控实验记录（全部真实 CDP + 3322 dev 态 + 真 token 实测）

| # | 注入 | 配置 | 门禁/页 | 结果 | 结论 |
| --- | --- | --- | --- | --- | --- |
| A | 延迟 3s | READY_TIMEOUT=0（旧路径） | G7 me.html | 焦点可及元素 38→29（晚渲染的 9 个缺席：1 张延迟加载区块卡片 + 6 个学习目标按钮 + 2 个空态），但该页可及元素全 Tab 可达 → 11/11 PASS，窗口留痕 `readyWindows:[]` | 注入生效（数据确实晚到）；此页恰好无假红暴露面 |
| B | 延迟 3s | READY_TIMEOUT=0 | G6 courses | PASS，`readyWindow:null` | 同上，courses 冻结基线无骨架条目，无假红暴露面 |
| C | 延迟 3s | READY_TIMEOUT=5000 | G7 me.html | **窗口真实生效**：360px 态 `settled:false, reason:"network-busy", waitedMs:5019`（5s 超时不阻塞），其余 4 viewport `settled:true, waitedMs≈2.9s`（等过 3s 慢响应后双一致）；**tab walk 暴露真缺口**：walk 前（旧版只等 500ms settle）晚渲染的订单卡/学习目标按钮缺席 → tab-reachable 29/38 FAIL | 修后：**walk 前补稳定窗（T9 修正）** |
| D | 延迟 3s | READY_TIMEOUT=8000 | G7 me.html | **38/38 PASS 全绿**（等待后采样拿到完整 38 个焦点元素）；窗口 `settled:true, waitedMs≈2.9s`×5 | **负控闭环：注入→旧路径缺元素→窗口等待→全绿** |
| E | 延迟 3s | READY_TIMEOUT=8000 | G6 courses | PASS，`waitedMs:5963`（等待 3s×串行双请求+双一致） | G6 同闭环 |
| F | 延迟 6s | READY_TIMEOUT=5000 | G7 me.html | **超时不阻塞**：5 viewport 全 `settled:false, reason:"network-busy", waitedMs≈5.03s`，门禁正常跑完 PASS（按现状采样，tab-reachable 29/29=当时可见元素全可达） | 超时回退=旧行为，报告留痕不造红 |
| G | 延迟 3s | READY_TIMEOUT=8000 | G9 me.html | PASS 56 检查 0 失败；mock 三态窗口 `settled:true, ≈0.59s`（mock 即时 fulfill，不需等待）；hold/fail 态按语义豁免 | G9 与延迟注入隔离正常，语义豁免生效 |
| H | 无注入 | 默认 | G7 login-register | PASS；窗口每 viewport `settled:true, ≈0.59s`（一次双一致轮询即过）；G9 login PASS 0 warnings | 无网络页行为不变（仅 +~600ms 双一致确认） |

**假红直接复现（C 组）的机制说明**：me 页 38 个焦点元素中 9 个（订单卡 t10-card ×5、学习目标按钮
pf-goal ×6 中 6 个在表单区、1 个延迟区块）由 `/api/trade/orders`、`/api/users/me/profile` 响应后
JS 渲染。3s 延迟注入下，旧路径（settle 900ms）与 walk（settle 500ms）都在响应落地前采样 →
缺席元素被判 unreachable。这正是编排者实测「me 页 2.1s 慢响应 → 8 unreachable 假红」的同型机制，
且是**首例经注入稳定复现**的记录（此前只能靠跑运窗口碰运气复现）。

## 5. 四页门禁验证（GATE-V3 机制开启，默认 READY_TIMEOUT=5000）

| 页面 | G6 | G7 | G9 |
| --- | --- | --- | --- |
| me.html | PASS 6/6 | PASS 11/11 | PASS 0 失败（5 WARN=hold/fail 态预期噪声） |
| my-cohorts.html | PASS 6/6 | PASS 11/11 | PASS 0 失败 |
| courses.html | PASS 6/6 | PASS 11/11 | PASS 0 失败 |
| community-post.html?post_id=96 | PASS 6/6 | PASS 11/11 | PASS 0 失败 |

全部 12 跑的 `readyWindow(s)` 均 `settled:true`（≈0.26~0.33s，健康后端下开销≈一次轮询对），
留痕于 `.tmp-t09/out-v3/*.json`（运行产物，不入库）。

## 6. 使用

```bash
# 默认即开启（cap 5s）
node scripts/gates/viewport-a11y-gate.mjs --page http://127.0.0.1:3322/me.html

# 自定义上限
EDU_GATE_READY_TIMEOUT_MS=8000 node scripts/gates/style-dep-gate.mjs --page ...

# 关闭（还原旧 settle-only 行为）
EDU_GATE_READY_TIMEOUT_MS=0 node ...

# 负控：把 /api/ 全部延迟 3s 复现慢后端
EDU_GATE_DELAY_API_MS=3000 EDU_GATE_READY_TIMEOUT_MS=8000 node scripts/gates/viewport-a11y-gate.mjs --page ...
```

## 7. 批判自检

1. **「双一致会不会锁死假绿」**：双一致只保证「DOM 不再变化」，不保证「变化后的 DOM 正确」；
   页面真 bug（如渲染死循环卡在错误态）→ 两快照一致地错 → 门禁仍按判据判红（如 state-visible/
   route-stable 照常拦截），机制不掩盖内容错误。
2. **「`--all` 25 页会不会被窗口拖慢」**：健康页开销≈1 次轮询对（≈0.26s/采样点）；G7 每页 5
   viewport + 1 walk + 1 settledAttrs ≈ +1.5s/页，25 页 ≈ +40s，换 --all 长跑稳定绿，值。
3. **「超时不阻塞会不会变成新的假绿通道」**：超时后的采样=旧行为，判据未动——最坏退化为
   「回到 GATE-V2 现状」，不会比修复前更差；且 `settled:false` 留痕可归因。
4. **「G9 豁免 hold/fail 态是弱化吗」**：这些态的设计语义就是网络不可用，等网络空闲与门禁自己的
   mock 语义矛盾（loading 态把请求挂起就是测试项）；既有 state-intercepted/state-route 判据未动。
5. **「tab walk 前的稳定窗是补丁吗」**：是第一版接入的遗漏（walk 是独立 navigate），负控 C 以
   29/38 FAIL 精确暴露后当场修正为机制的一部分（walk 前同一 waitForReady），非事后打补丁绕过。
