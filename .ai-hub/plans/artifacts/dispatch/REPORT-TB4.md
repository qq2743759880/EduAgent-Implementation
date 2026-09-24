# REPORT-TB4 — RAG/MCP 控制台 UX（yy 十点修复 · P1）

- **工作单**：`.ai-hub/plans/artifacts/dispatch/TO-EXEC-TB4.md`
- **分支**：`feature/opt-waves`
- **日期**：2026-09-24
- **域**：`edu-frontend/public/admin-rag-upload.html`、`edu-frontend/public/admin-mcp.html`（+ G3 基线登记）
- **后端契约改动**：**零**（未改任何后端文件、未改任何接口路径/字段；`.env` 未触碰）
- **未触碰**：`admin-infra.html`（TB3 新页）、chat 相关任何文件

---

## 0. 交付口径（对应工作单五条 + 业主验收）

| 工作单项 | 产物 | 状态 |
|---|---|---|
| 1. admin-rag* 五 tab：说明卡 + 空态引导 + loading/结果反馈 | 5/5 tab 说明卡；5 处空态引导；4 条 `.feed` 反馈通道 | ✅ |
| 2. admin-mcp：① 顶部说明卡 ② 新增 Server 分步引导（5 步）③ 工具健康徽标 | 3 张说明卡；5 步步骤条；健康徽标读 `last_health_ok` | ✅ |
| 3. 样式：clay 一致 + 三段 admin 守卫 | 复用 `theme.css` / `clay-*` / Phosphor sprite；无 emoji | ✅ |
| 4. 自验：G6/G7/G9 单页 + G3 `--page` 登记零漂移 + 无 token 跳登录 + student 被拒 | 四门全绿；G3 两页 PASS；守卫 4 项 PASS | ✅ |
| 5. 可用性自证：每页「5 秒能说清这页做什么」 | 见 §5（两页自检记录） | ✅ |

**业主验收**（不看文档，打开两页）：5 秒内能说出这页/每 tab 管什么；能无提示走完「新增 MCP Server」引导流程 —— 由 §4 探针 19 项 + §3 空态截图共同实证。

---

## 1. 逐页改动清单

### 1.1 `admin-mcp.html`（678 → 1015 行）

**新增样式**（TB4 块，紧跟 `.foot-note` 之后；另有 `.admin-html-page` clay 覆盖）：
`.tb4-what / .tb4-wcard / .wt / .wd / .we`（说明卡）、`.tb4-guide`、`.tb4-empty / .et / .ed`（空态）、
`.steps / .steps li.cur / .steps li.done`（步骤条）、`.step-pane / .on`、`.step-tip`、`.f-hint`、
`.hc-box / .hc-st / .hc-ok / .hc-bad`、`.tblok-fb / .show / .ok / .bad / .busy`、`.spin` + `@keyframes tb4spin`。

**① 顶部功能说明卡**（3 张 `.tb4-wcard`）：
- 「这个页面是什么」—— 把外部 MCP Server（工具提供方）注册进来，让 AI 在对话中调用它们的工具。
- 「三步上手」—— 注册 → 健康检查 → 发现工具。
- 「四块区域各管什么」—— Server 列表 / 工具清单 / 调用日志 / 新建向导。

**② 新增 Server 改 5 步分步引导**：
- 由原扁平弹窗改为 `<ol class="steps" id="srvSteps">`：`li[data-step=1..5][role=button][tabindex=0]`
  （1 填 code/名称 → 2 选 transport → 3 填连接参数 → 4 健康检查 → 5 保存）。
- 5 个 `.step-pane[data-pane=1..5]`，`srvSetStep(n)` 单点驱动 `cur`/`on` 高亮与面板显隐。
- 每步带 `.f-hint` 占位示例（如 `local-tools` / `python` / `["mcp_server.py"]` / `http://localhost:9001/sse`）。
- `srvValidate(n)` 逐步守卫：第 1 步 `server_code` 必填；第 3 步 stdio 必填 `run_command` 且参数须为 JSON 数组、SSE/HTTP 必填 `base_url`。校验不过 → `srvErr(m)` 就地红字，**不推进**。
- 「创建 Server」按钮仅在第 5 步显示（`srvMdlSave` 前 4 步 `display:none`）。
- 第 4 步 `srvProbe` 走「临时建 Server → `/health` → 失败即删」的真实连通性探测，结果落 `srvProbeOut`；第 5 步 `srvReview` 汇总待提交字段。

**③ 工具列表健康徽标**（读 `last_health_ok`）：
- 新增 `healthBadgeFrom(ok)` → 复用既有 `.badge` 变体：`true/1`→`b-done`「健康」、`false/0`→`b-failed`「异常」、其余→`b-pending`「未检测」。
- `loadTools()` 先拉 `/api/mcp/servers` 建 `SRV_HEALTH` 映射（按 `String(id)` 与 `String(server_code)` 双键），再拉 `/api/mcp/tools`，逐行渲染徽标。
- Server 列表新增 `<th>健康</th>` 列（表宽 5 → 6 列）。

**其余 UX 加固**：
- 三张表各加 `.step-tip` 现状说明（「每台 Server 一行。健康=最近一次检查结果…」）。
- 三个反馈通道 `#srvFeed` / `#scanFeed` / `#toolFeed`，由 `feed(id,kind,msg)` 统一输出 busy/ok/bad + 图标。
- 健康检查 / 发现工具 / 停启用 / 删除 / 扫描 / 工具测试 全部走 `feed()` 的 loading → 结果二态。
- 空态：`emptyHint(title, body)` 输出「用途 + 编号下一步」富文本，覆盖 Server / 工具 / 日志三表（+ 各自加载失败态）。
- 初始化改为串行 `loadServers() → loadTools() → loadLog()`，保证徽标映射先于工具表渲染。

### 1.2 `admin-rag-upload.html`（1066 → 1280 行）

**新增样式**：`.tab-what / .tw-card / .tw-t / .tw-d / .tw-e`、`.tb4-empty`、`.feed / .show / .ok / .bad / .busy`、`.spin` + `@keyframes tb4spin`（含 `.admin-html-page` clay 覆盖）。

**① 页面级定向卡**（`.tab-what`，置于 `gap-note` 后）：「这个页面是什么」+「五个 tab 各管什么」。

**② 五个 tab 各自说明卡**（每 tab 2 张 `.tw-card`，明确「这个 tab 做什么」+「调什么 / 调完看什么」+ 第三张「什么时候用 X」）：

| tab | 说明卡要点 |
|---|---|
| 上传 | 调什么：文件格式/大小限制；调完看什么：导入任务状态变绿「完成」 |
| 集合 | 调什么：分区 + 模式（incremental 补漏 / full 清空重建）；看什么：`status` 与「最近重建」 |
| 调参 | 调什么：top_k / cutoff_drop_ratio / rrf_k / use_hyde / enable_graph；看什么：保存后回「高级检索」验证 |
| 审计日志 | 调什么：无（只读）；看什么：`retrieved_count→final_count` 折损定位参数问题 |
| 高级检索 | 调什么：查询 + 参数；看什么：命中条数、最高分、score 降序列表 |

**③ 空态引导**（`emptyHint` 5 处）：已选文件区、导入任务、集合、调参预设、审计日志（+ 各自加载失败态、分区空/失败态）。此前是白板或单行 `muted`。

**④ 关键操作 loading + 结果反馈**（4 条 `.feed`）：
- `#upFeed` 上传：选文件即报「合法 N 个 / 已拦截 M 个（原因）」；上传循环统计 `failed`，收尾报「成功 N 个 / 失败 M 个」并指向导入任务。
- `#ragRbFeed` 索引重建：busy → ok/bad，期间禁用 `ragRbBtn`。
- `#ragPpFeed` 保存预设：校验名称（「名称必填（2-64 字符），例：备考-高召回」）→ busy → ok/bad。
- `#ragSFeed` 高级检索：按钮转圈 + 结果区占位；命中报「命中 N 条，按 score 降序；最高分 X」，零命中给出可执行建议（「回『调参』把 cutoff 调低，或到『上传』确认资料已导入」）。

---

## 2. G3 DOM Hook 基线登记（工作单第 4 项）

**动作**：`node scripts/gates/dom-hook-inventory.mjs --all`（27 页全量登记，工作单许可路径）。

**漂移对照**（`--page ... --check`）：

| 页面 | 改前 hooks | 改后 hooks | 漂移 |
|---|---|---|---|
| `admin-mcp.html` | 18 | **23** | +5：`query-selector` 4→5、`query-selector-all` 5→8、`class-list` 5→6 |
| `admin-rag-upload.html` | 37 | **37** | **0（零漂移，无需登记）** |

新登记的 4 条指纹（步骤条必需的结构遍历，无法避免）：
1. `query-selector｜querySelector("#srvTable tbody")`
2. `query-selector-all｜querySelectorAll("#srvSteps li")`（×2 行）
3. `query-selector-all｜querySelectorAll("#mdl-server .step-pane")`
4. `class-list｜classList.toggle("on",+panes[j].getAttribute("data-pane")`

> RAG 页零漂移是刻意设计的结果：全部新 UI 走**新增 class**（`.tab-what`/`.feed`/`.tb4-empty`）与**复用既有 id**，未引入新的 `querySelector` 字面量。

**复检**：登记后两页 `--page --check` 均 **PASS**（`frozen-hooks-present` + `new-hooks-reviewed` 各 2 项）。

**⚠️ 范围披露（caveat）**：`--all` 是全量重生成，会顺带把**当前磁盘上所有页面**（27 页）的 hook 集写入基线。本次登记时 `admin-infra.html`（**TB3 的页面，不在 TB4 域内**）已在基线内（`page_count` 改前改后均为 27，即由同期其他 agent 的 `--all` 先登记）。TB4 未修改 `admin-infra.html` 的任何内容，仅因共享基线文件被一并重写。

---

## 3. 四门自验（工作单第 4 项 · 现状基线口径）

单页运行，基线与改后**警告画像完全一致**。

### G6 `style-dep-gate.mjs`
```
admin-mcp.html        pages=1 checks=6  failed=0 warnings=0  → PASS
admin-rag-upload.html pages=1 checks=6  failed=0 warnings=0  → PASS
```
（注：G6 **无 `--check` 参数**，始终与冻结快照 `style-dep-snapshot.json` 比对；传 `--check` 会 `Unknown argument`。）

### G7 `viewport-a11y-gate.mjs`
```
admin-mcp.html        pages=1 checks=11 failed=0 warnings=0  → PASS   （视口 360/768/1280/1440/1920）
admin-rag-upload.html pages=1 checks=11 failed=0 warnings=0  → PASS
```

### G9 `state-matrix-gate.mjs`
```
admin-mcp.html        pages=1 checks=56 failed=0 warnings=5  → PASS
admin-rag-upload.html pages=1 checks=56 failed=0 warnings=5  → PASS
```
（5 条 WARN 与改前基线完全一致，为既有 console 诊断项，非本任务引入。）

### G3 `dom-hook-inventory.mjs --page`
```
admin-mcp.html        pages=1 checks=2 failed=0 → PASS
admin-rag-upload.html pages=1 checks=2 failed=0 → PASS
```

### 空态/引导截图（工作单第 4 项要求）
`test-reports/tb4/shots/`（用 CDP `Fetch.fulfillRequest` 把列表接口 mock 成空壳后实拍）：

| 文件 | 内容 |
|---|---|
| `admin-mcp-empty-servers.jpg` | Server 表空态：「还没有注册任何 MCP Server」+ 3 步编号引导（新增 Server → 健康 → 发现工具） |
| `admin-mcp-empty-tools.jpg` | 工具清单空态：「还没有发现任何工具」+ 指引先做健康检查 |
| `admin-mcp-empty-logs.jpg` | 调用日志空态：「还没有调用记录」+ 指引去上表测试 |
| `admin-rag-empty-upload.jpg` | 已选文件区空态 |
| `admin-rag-empty-collections.jpg` | 集合表空态：「还没有任何集合」+ 3 步引导 |
| `admin-rag-empty-presets.jpg` | 调参预设空态 |
| `admin-rag-empty-audit.jpg` | 审计日志空态 |

> 三张 MCP 空态图**文件哈希互不相同**（逐表 `scrollIntoView` 后取景），非同一张抄三遍。

---

## 4. 可用性探针（E4 证据）· `scripts/tb4-ux-probe.mjs`

真实浏览器（CDP，**Playwright 禁用**），复用 `scripts/gates/_shared.mjs::createBrowser`。
运行：`EDU_GATE_TOKEN=<jwt> EDU_GATE_STUDENT_TOKEN=<jwt> node scripts/tb4-ux-probe.mjs`

```
[PASS] admin-mcp.html · top-explanation-cards: 3 张功能说明卡
[PASS] admin-mcp.html · explains-what-and-how: 这个页面是什么 把外部 MCP Server（工具提供方）注册进来…
[PASS] admin-mcp.html · stepper-5-steps: 步骤条 5 步
[PASS] admin-mcp.html · stepper-opens-step1: 初始 step=1 pane=1
[PASS] admin-mcp.html · stepper-advances: 下一步 → step=2 pane=2
[PASS] admin-mcp.html · stepper-save-only-on-last: 第 2 步隐藏「创建 Server」=true
[PASS] admin-mcp.html · stepper-goes-back: 上一步 → step=1
[PASS] admin-mcp.html · stepper-closes: 取消后弹窗关闭=true
[PASS] admin-mcp.html · stepper-blocks-empty-code: 仍停在第 1 步，提示「✕ 第 1 步：server_code 必填…」
[PASS] admin-mcp.html · tool-health-badges: 4 个徽标，样例 ["健康","健康","健康","健康"]
[PASS] admin-mcp.html · empty-state-guidance: 3 处空态引导块（Server=1 工具=1 日志=1）
[PASS] admin-mcp.html · empty-state-has-next-step: 空态文案含下一步指引
[PASS] admin-rag-upload.html · five-tabs: tabs=collections,upload,presets,audit,search
[PASS] admin-rag-upload.html · every-tab-has-explanation: 5/5 个 tab 有说明卡
[PASS] admin-rag-upload.html · empty-state-provided: 5 处空态引导块
[PASS] admin-mcp.html · guard-no-token-redirects: 无 token（tokenLen=0）→ /login-register.html
[PASS] admin-rag-upload.html · guard-no-token-redirects: 无 token（tokenLen=0）→ /login-register.html
[PASS] admin-mcp.html · guard-student-rejected: student（tokenLen=171）→ /dashboard.html
[PASS] admin-rag-upload.html · guard-student-rejected: student（tokenLen=171）→ /dashboard.html

TB4 UX Probe: PASS  checks=19 failed=0
```
**稳定性**：连续 3 次运行均 `PASS 19 failed=0`（退出码 0）。证据 JSON：`test-reports/tb4/tb4-ux-probe.json`。

### 守卫口径说明（三段 admin 守卫，工作单第 4 项）
本页复用 `edu-guard.js::eduGuard.requireAdmin()`，其**既定行为**为：
1. 本地无 token → 跳 `/login-register.html?redirect=<本页>`（同步，第一道判定）；
2. 有 token → `GET /api/auth/me` 校验 `role ∈ {admin, manager}`；**非白名单 → id 跳 `/dashboard.html` 并显示「无管理权限」横幅**；
3. `auth/me` 失败 → 按未授权跳登录。

故实测口径为：**student 被拒 = 离开 admin 页（落 `/dashboard.html`）**，而非落登录页 —— 与 `edu-guard.js` 源码第 8 行注释一致。

### 探针实现中踩到并修正的两个坑（供后续复用）
1. **`createBrowser` 会注入身份**：`_shared.mjs` 在 `EDU_GATE_TOKEN` 存在时注册 `Page.addScriptToEvaluateOnNewDocument`，**每个新文档**都把 token 写回 `localStorage`。因此「页内 `removeItem` 后再导航」必被覆盖（实测 `tokenLen` 又回 175，守卫假通过）。→ 守卫用例改为**另开干净浏览器**（临时清空 `EDU_GATE_*` 环境变量）并自行控制注入脚本。
2. **同 URL 二次导航命中缓存/bfcache**，页面脚本（守卫）不重跑。→ 导航加 `?__tb4g=<ts>` cache-bust 参数。

---

## 5. 可用性自证：「5 秒能说清这页做什么」（工作单第 5 项）

**`admin-mcp.html` —— 5 秒自检**
> 打开先看到三张卡：**「这个页面是什么」把外部 MCP Server 注册进来让 AI 调用其工具**；「三步上手：注册 → 健康检查 → 发现工具」；「四块区域：Server 列表 / 工具清单 / 调用日志 / 新建向导」。
> 一眼能回答三个问题 —— 这页管什么（MCP 工具提供方）、先做什么（点「+ 新增 Server」）、做完看什么（Server 行变绿 OK → 「发现工具」→ 工具进下方清单）。
> 表格上方各有一行现状说明；工具表「健康」列直接给绿「健康」/红「异常」/灰「未检测」徽标。
> **结论：达标。** 说明卡 → 区块 tip → 空态编号引导构成三级递进，任一层都能独立支撑 5 秒理解。

**`admin-rag-upload.html` —— 5 秒自检**
> 打开先看到页面级卡：**「这个页面是什么」+「五个 tab 各管什么」**（集合 / 上传 / 调参 / 审计日志 / 高级检索，一行一 tab 说清职责）。
> 切到任一 tab，面板顶部固定一张说明卡，明确「这个 tab 做什么」「**调什么**」「**调完看什么**」；例如调参 tab：「调什么：top_k / cutoff_drop_ratio / rrf_k / use_hyde；调完看什么：保存后回高级检索验证命中」。
> 所以不必先读文档就能建立正确心智：**先上传 → 再看集合状态 → 不好用就去调参 → 用高级检索验证 → 审计日志查为什么**。
> **结论：达标。** 页面级卡解决"这页是什么"，tab 级卡解决"每个 tab 管什么、怎么调、看什么反馈"，两级合起来覆盖业主的 5 秒问题。

---

## 6. 铁律自查

| 铁律 | 自查 |
|---|---|
| 后端契约零改动 | ✅ 未改 `edu-agent/**` 任何文件；未改接口路径/字段；`.env` 未触碰 |
| 不动 `admin-infra.html`（TB3） | ✅ 文件内容零改动（仅因共享基线 `--all` 被一并重写，见 §2 caveat） |
| 不动 chat 相关 | ✅ 未触碰 |
| 不 push | ✅ 仅本地单次 commit |
| 单次提交信息 | `feat(fe)/tb4: RAG/MCP 控制台 UX(说明卡+分步引导+健康徽标)` |
| 无 emoji | ✅ 图标全部走 Phosphor sprite（`ic-info`/`ic-warning`/`ic-check-circle`/`ic-gear`/`ic-play`）+ 步骤条内联 SVG |
| Playwright 禁用 | ✅ 全链路 CDP（复用 `createBrowser`） |

---

## 7. 提交清单

```
edu-frontend/public/admin-mcp.html
edu-frontend/public/admin-rag-upload.html
docs/dom-hooks-frozen.json
docs/dom-hooks-frozen.md
scripts/tb4-ux-probe.mjs
test-reports/tb4/tb4-ux-probe.json
test-reports/tb4/shots/*.jpg            （7 张空态/引导截图）
test-reports/gate-baseline/g3-dom-hook-inventory.{json,txt}
test-reports/gate-baseline/g6-style-dep-gate.{json,txt}
test-reports/gate-baseline/g7-viewport-a11y-gate.{json,txt}
test-reports/gate-baseline/g9-state-matrix-gate.{json,txt}
.ai-hub/plans/artifacts/dispatch/REPORT-TB4.md
```

---

## 8. 遗留与提示

1. **共享基线并发写**：`docs/dom-hooks-frozen.json` 与 `test-reports/gate-baseline/*` 是**全仓共享**文件，同期并行 agent 的 `--all` / 单页运行会互相覆盖。本次已实测到一次覆盖（4 个 hook 登记被冲掉 → 复检 FAIL → 重新 `--all` 修复）。**后续在并行窗口提交前，请再复检一次 `--page --check`。**
2. **`admin-infra.html` 已进 G3 基线**（非本任务产物）。若 TB3 后续修改该页，需由其自行 `--all` 重登记；本报告 §2 已如实披露。
3. 本工作单未改动后端，故未重跑后端 pytest 基线。
