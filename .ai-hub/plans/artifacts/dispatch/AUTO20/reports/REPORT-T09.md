# REPORT-T09 — GATE-V3 门禁数据就绪稳定窗机制化（AUTO20 T9）

- 分支：`feature/opt-waves`（开工前 `git branch --show-current` 核验通过）
- 日期：2026-09-22
- 域：`scripts/gates/**`（独占）+ `docs/gate-v3-notes.md`；`public/*.html`、`edu-agent/`、其他 docs 零触碰
- 状态：✅ 闭环（机制 + 四页 12 跑全绿 + 8 组负控/对照实验）

---

## 一、问题（GATE-V2 §7.3/§8 遗留移交项②）

三门禁采样时序 = navigate → 固定 settle（900ms）→ 采样，对「页面数据慢于 settle」无稳定态探测，
三类已实证假红：① courses 动画数据未就绪（running animations=25）② my-cohorts 卡片未就绪
（tab-reachable 14/31）③ me 页 /api/trade/orders 2.1s vs settle 900ms → 8 unreachable 假红
（当时手工调 EDU_GATE_SETTLE_MS=3500 才绿）。属机制缺口，调参不解决。

## 二、修法（机制化，非调参）

### 2.1 `_shared.mjs` 新增（GATE-V3 核心）

1. **网络空闲追踪**：`Network.requestWillBeSent/loadingFinished/loadingFailed` 三事件维护在途请求集
   （排除 ws:/devtools:/data:），`browser.pendingRequests()` 取数。CDP 真实事件驱动，不猜 URL。
2. **`waitForReady(snapshotFn)` 数据就绪稳定窗**：采样前轮询至
   - Phase 1 网络空闲（=0 **持续 250ms** 才算——CDP 事件异步到达，防单点观测竞态）；
   - Phase 2 **连续两次 DOM 快照一致**（双一致先例 = GATE-V2 W2 `settledAttrs`，推广到三门禁各自的
     完整采样表达式 A11Y/INSPECT/LAYOUT/ATTRS——每门禁采样点复用同一 helper，且轮询比对用的就是
     门禁自己的采样表达式，无第二套判定逻辑）；
   - 上限 `EDU_GATE_READY_TIMEOUT_MS`（默认 5000，0=禁用=旧路径）；超时返回 `settled:false +
     reason("network-busy"|"dom-unstable")` 并**按现状采样**——超时只落报告 JSON 的
     `readyWindow(s)` 留痕字段，不新增检查项、不改任何 check 判定（防窗口超时自己造红）。
3. **负控钩子 `setApiDelay(EDU_GATE_DELAY_API_MS)`**：CDP Fetch 拦截 127.0.0.1/localhost `/api/*`
   延迟 `continueRequest`，把快本地后端变成慢生产后端复现竞态；幂等；G9 不接线（Fetch 所有权归其
   状态 mock）。

### 2.2 三门禁接入点

| 门禁 | 接入点 | 语义保持 |
| --- | --- | --- |
| G6 | navigate 后、INSPECT 采样前 | 检查 6 条未动 |
| G7 | ① 5 viewport 各采样前（readyWindows 留痕）② **Tab walk 前**（walk 是独立 navigate，settle 仅 min(settleMs,500)——负控 C 实证缺此窗口则晚渲染卡片缺席→29/38 假红，当场补齐） | 11 条检查未动；聚合判定/N/A/基线合并全保留 |
| G9 | 仅 mock 三态（empty/disabled/long-text）；**hold/fail 五态按语义豁免**（loading 设计上挂起全部 /api/，等空闲与测试项矛盾；既有 transitional 轮询兜底） | 56 检查/页未动；N/A 白名单保留 |

铁律 3 自检：已有检查一条未删；稳定窗只改采样时机不改判据；`READY_TIMEOUT_MS=0` 完整还原旧路径；
community-post `?post_id=96` 已知坑全程保持（ROUTE_QUERY 既有）。

## 三、四页门禁验证（机制开启，默认 cap 5s；真 token 只存 shell 内存/临时文件，未入库）

| 页面 | G6 | G7 | G9 |
| --- | --- | --- | --- |
| me.html | PASS 6/6 | PASS 11/11 | PASS（0 error，5 WARN=hold/fail 态预期噪声） |
| my-cohorts.html | PASS 6/6 | PASS 11/11 | PASS（0 error） |
| courses.html | PASS 6/6 | PASS 11/11 | PASS（0 error） |
| community-post.html?post_id=96 | PASS 6/6 | PASS 11/11 | PASS（0 error） |

12 跑全部 `readyWindow(s).settled=true`（≈0.26~0.33s，健康后端开销≈一次轮询对）。

## 四、负控实验记录（真实 CDP 注入，全部留痕 .tmp-t09/out-*，运行产物不入库）

| # | 注入 | 配置 | 门禁/页 | 结果 | 结论 |
| --- | --- | --- | --- | --- | --- |
| A | delay 3s | READY=0 旧路径 | G7 me | 焦点元素 38→29（晚渲染缺席：订单卡+学习目标按钮等 9 个）；可及元素全 Tab 可达→PASS，`readyWindows:[]` | 注入生效；该页无假红暴露面 |
| B | delay 3s | READY=0 | G6 courses | PASS，`readyWindow:null` | 同上（courses 冻结基线无骨架条目） |
| C | delay 3s | READY=5000 | G7 me | 360px 态超时 `settled:false/network-busy/waitedMs:5019`（不阻塞）；其余 4 viewport `settled:true ≈2.9s`（等过 3s 慢响应）；**但 tab walk 假红 29/38 FAIL**——walk 前（旧版 500ms settle）晚渲染卡片缺席 | 暴露 walk 前缺口→当场补稳定窗（T9 修正），**这正是编排者实测 me 页假红的同型机制、首例注入稳定复现** |
| D | delay 3s | READY=8000 | G7 me | **38/38 全绿 PASS**（等待后采样）；`settled:true ≈2.9s`×5 | 负控闭环：注入→等待→绿 |
| E | delay 3s | READY=8000 | G6 courses | PASS，`waitedMs:5963` | G6 同闭环 |
| F | delay 6s | READY=5000 | G7 me | 5 viewport 全 `settled:false/network-busy ≈5.03s`，门禁正常跑完 PASS（按现状采样 29/29 全可达） | 超时=旧行为，留痕不造红不阻塞 |
| G | delay 3s | READY=8000 | G9 me | PASS 0 error；mock 三态窗口 `settled:true ≈0.59s`；hold/fail 态豁免 | G9 与延迟钩子隔离正常 |
| H | 无注入 | 默认 | G7/G9 login-register | 双 PASS；窗口 `settled:true ≈0.59s`（一次双一致轮询即过）；G9 0 warnings | 无网络页行为不变（仅 +~600ms 确认开销） |

## 五、批判自检

1. **双一致≠内容正确**：页面渲染死循环卡错误态也会双一致——state-visible/route-stable 等内容判据
   照常拦截，机制不掩盖页面真 bug。
2. **--all 开销**：健康页 +≈1.5s/页（G7），25 页 +≈40s；换 --all 长跑稳定绿，值。
3. **超时不阻塞是新的假绿通道吗**：最坏退化=回到 GATE-V2 现状（判据未动），且 `settled:false`
   留痕可归因，不比修复前差。
4. **G9 豁免是弱化吗**：hold/fail 态设计语义即网络不可用，等空闲与 state-intercepted 测试项矛盾；
   该五态判据全部保留。
5. **walk 前稳定窗是补丁吗**：是首版接入遗漏，负控 C 精确暴露（29/38 FAIL）后当场并入机制统一实现，
   有负控双向证据（C 缺窗口=FAIL，D 有窗口=PASS）。

## 六、改动清单

- `scripts/gates/_shared.mjs`：pendingRequests 追踪 + waitForReady + setApiDelay + parseCli 两个
  环境变量（READY_TIMEOUT_MS/DELAY_API_MS，均带非法值 fail-fast）+ usage 更新
- `scripts/gates/style-dep-gate.mjs`：采样前 waitForReady + readyWindow 留痕 + 负控钩子接线
- `scripts/gates/viewport-a11y-gate.mjs`：5 viewport 采样前 + tab walk 前 waitForReady +
  readyWindows 留痕 + 负控钩子接线
- `scripts/gates/state-matrix-gate.mjs`：mock 三态 waitForReady + readyWindow 留痕（hold/fail 豁免，
  Fetch 所有权不动）
- `docs/gate-v3-notes.md`：新增（机制说明 + 8 组实验记录 + 使用方式 + 批判自检）
