# REPORT-TA1-3 — 流式双端定因修复 → 黄条视觉实证

> 送工单：`TO-EXEC-TA1-3`（yy 十点修复 · P0 · `chat.html` 同文件串行链）
> 分支：`feature/opt-waves`　｜　执行方式：**同一执行者串行**（TA1 完成后才做 TA3，禁并行双写）
> 铁律遵守：**未改后端 SSE 输出结构**；未碰 `.env`；未碰 `permission_gate.py` / `receipt_guard.py`；未直写 DB（仅只读 SQL）；未 push

---

## 0. 一页结论

| 项 | 结论 |
|---|---|
| TA1 后端是否断？ | **否**。`j.delta` 帧结构完好、逐帧到达，上游是真流式（~200 帧/秒）。**未改后端**。 |
| TA1 前端断在哪？ | **不在字段、不在解析**（双端都正确消费 `j.delta`、正确按 `data:` 行解析）；断点在**渲染节奏与网络到达解耦不足**——120ms/`FLUSH_MS` 节流 + 全量 `innerHTML` 覆盖，而真实到达速率 400~620 字/秒，可见窗口仅 1.07~1.25s，肉眼等同"转圈后整段弹出"。 |
| 修复 | 双端同构引入**打字机揭示队列**（到达=事实源 `acc`；可见=`acc.slice(0, shown)`，30ms 节拍、≥90 字/秒自适应、尾部至多 2.2s、20s 硬兜底；收尾=**揭示排空 ∧ 连接收束**）。 |
| TA1 自验 | 真实流 after：chat.html `distinctTextLens` 11→91、`domMutations` 24→193；React 20→93 / 20→96。帧重放（单次网络到达 → 多次 DOM 增量）：chat.html **3/3**、React **3/3**。G3 冻结钩子 **PASS**。 |
| TA3 黄条 | 后端 `curl -N` 3/3 命中 `tool_receipt_unverified`；前端**真实端到端完整完成 2/2 命中**（落库机验）；帧重放渲染路径 **3/3** 黄条可见（几何/样式量化）。 |
| 环境阻塞 | **LLM 上游双路配额/订阅同时失效**（DeepSeek 402 / Ark 400），发生在实证中途；已如实登记，未以任何方式掩饰。 |

---

## 1. 定因（先测后修，全程可追溯）

### 1.1 后端层 — 帧结构完好，问题不在后端

`curl -N POST /api/chat/stream`（student，body `{query, session_id, stream:true}`，事件 `start|retrieval|token|done|error`）：

- **token 帧数 96~234**，每帧 `data:{"delta":"…"}` 均**非空**，逐帧独立到达 → SSE 帧结构与流式语义**正确**。
- token 帧**集中在 0.24~1.07 秒窗口内**到达，其后约 12s 才收到 `done` 帧（检索 + 生成前置耗时 20~40s）。
- **上游隔离**（绕开本仓库，裸 socket 直读 `api.deepseek.com`）：788 次 `recv` / 598 个 content 帧 / 窗口 2.999s ≈ **200 帧/秒** → 上游是真流式。
- 本仓库 `app/ai/.../generator.py` 用 `requests.iter_lines()`（512 字节缓冲）中继，实测吞吐 **219 帧/秒** → **基本忠实中继，非本仓库缓冲缺陷**。

> **判定**：后端无缺陷，**不改**（且工单明令禁改后端 SSE 输出结构——下游 blind-test 依赖）。

### 1.2 前端层 — 字段与解析都对，断点在「渲染节奏 vs 到达节奏」

CDP 双端抓取真实流（`Network.dataReceived` 抓帧 + `MutationObserver` 抓 DOM 时序）：

| 端 | 页面 | netChunks | domMutations | distinctTextLens | finalTextLen |
|---|---|---|---|---|---|
| **修复前** | `chat.html` | 201 | 24 | 11 | 354 |
| **修复前** | React `/chat` | 186 | 20 | 20 | 636 |

- 两端均**正确消费 `j.delta`**（无"读弃用字段 `data.token`"缺陷）；
- 两端均**正确按 `data:` 行解析**（无"未按行解析"缺陷）；
- 不存在"一次性 innerHTML 覆盖"（DOM 有多次变更）——但变更次数远低于帧数。

> **真断点**：旧实现按 120ms（`chat.html`）/ `FLUSH_MS`（React）节流**整段重写**，而正文到达速率 400~620 字/秒 → 可见文本窗口仅 **1.07~1.25 秒**，260~640 字在一次刷新内弹出 → 肉眼即"转圈 → 整段出现"。**缓冲未按节拍释放**是根因表征。

### 1.3 修复 — 打字机揭示队列（双端同构，节奏与网络解耦）

核心不变量：
- `acc` = **已到达全量**（唯一事实源，只增不减）；可见内容 = `acc.slice(0, shown)`；
- `shown` 由 `setInterval(revealTick, 30ms)` 推进：`cps = max(90, 剩余缓冲 / 2.2s)`，`step = round(cps × 30 / 1000)`；
- 硬兜底 `REVEAL_FORCE_MS = 20000`（防定时器悬挂）；
- **收尾条件 = 揭示排空 ∧ 连接收束**（`shown >= acc.length` **且** 已收 `done` 帧且 reader 关闭）；
- `pending_confirm`（HITL 卡）出现时立即停揭示并直出（人机确认优先，不与打字机争屏）；
- `failStream` 立即全量揭示 + 报错，不留半截。

纯函数/回调拆分（便于定点测试与复用）：`stopPacer` / `revealTick` / `ensurePacer` / `tryFinalize`（静态页）与 `stopPacer` / `revealTick` / `ensurePacer` / `maybeFinalize`（React）。

---

## 2. SSE 前端消费契约（**冻结**）

> 依工单要求：改 React 消费结构**前先冻结本节**。以下为双端共同遵守的消费契约，**后端输出结构未变**。

| 事件 | 关键字段 | 消费要求 |
|---|---|---|
| `start` | `session_id`, `query` | 建会话/记录；不得据 `session_id=null` 中止 |
| `retrieval` | `docs[]`（`doc_id/score/content`） | 只更新来源区；**不得触发正文全量重写** |
| `token` | **`delta`**（增量字符串） | **追加**到事实源 `acc`；**禁止**读 `data.token`；**禁止**以帧为单位直接整段重写可见正文 |
| `pending_confirm` | 工具名/参数/风险级 | 立即停揭示队列 → 渲染确认卡（HITL 优先） |
| `done` | 统一壳 `{code,message,data}`；`data.mcp_tool_calls` / `data.memorized` / `data.tool_receipt_unverified` | 置"连接收束"标志；**不得**立即整段落地；等揭示排空后收尾并追加记忆条/黄条 |
| `error` | 错误码/信息 | 停队列 + 全量落地 + 报错提示 |

**解析顺序硬约束**：必须按 `data:` 行解析 `event:` 与 `data:` 配对（`\n\n` 为帧界）；必须容忍 `session_id: null`（流式首帧不建会话）。
**收尾硬约束**：收尾仅在「揭示排空 ∧ 连接收束」双条件成立时发生（避免"答案还没敲完就把记忆条/黄条插进去"）。
**字段级兼容**：`done.data` 为**增量加字段**（`tool_receipt_unverified` 等后落字段），前端须按"缺省=false / 缺省=[]"消费，不得因未知字段报错。

---

## 3. 修复 diff 摘要

| 文件 | 变化 | 要点 |
|---|---|---|
| `edu-frontend/public/chat.html` | **+98 / −41** | 删 `renderTimer`/`scheduleRender`（120ms 节流）；新增 `acc/shown/pacer/finished/streamClosed/gotDone` 与 `renderStream(final)`、`stopPacer/revealTick/ensurePacer/tryFinalize`；`token` 分支改 `acc += j.delta` + `ensurePacer()`；`done` 分支改"缓存 `doneMemo`/`doneReceiptWarn` → `tryFinalize()`"；`r.done` 置 `streamClosed` 后按双条件收尾；`failStream` 立即全量；`pending_confirm` 停队列 |
| `edu-frontend/src/components/chat/hooks/useChatStream.ts` | **+96 / −24** | 删 `FLUSH_MS`/`flushTimerRef`/`scheduleFlush`；`draftRef` 增 `shown`；新增 `pacerRef/streamDoneRef/revealStartRef/finishedRef` 与 `stopPacer/revealTick/ensurePacer/maybeFinalize`；`flush()` 写 `slice(0, shown)`；`finalizePending` 先停队列再全量；5 处 `scheduleFlush()` → `ensurePacer()`；`onDone` 改 `streamDoneRef=true → maybeFinalize()` |

**未改动**：后端任何文件、`docs/dom-hooks-frozen.md` 冻结钩子清单、`.env`。**还原**：`edu-frontend/next-env.d.ts`（dev server 自动改写 `.next-prod`→`.next/dev`，不属本任务，已 `git checkout` 还原）。

---

## 4. TA1 自验证据

### 4.1 真实流（修复后 1 次，`after1_*.json`）

| 端 | netChunks | domMutations | distinctTextLens | 对比修复前 |
|---|---|---|---|---|
| `chat.html` | 185 | 193 | **91** | 11 → **91**（≈8.3×） |
| React `/chat` | 87 | 96 | **93** | 20 → **93**（≈4.7×） |

### 4.2 帧重放（确定性实证：**单次网络到达 → 多次 DOM 增量**）

> 方法：CDP `Fetch.enable` + `Fetch.fulfillRequest` 重放真实后端响应体（取自探针落盘 `raw.responseBody`），仅替换 done 帧 flag。**netChunks=1** 即可判定"增量必来自前端揭示队列"。

| 端 | 轮次 | netChunks | domMutations | distinctTextLens | 证据文件 |
|---|---|---|---|---|---|
| `chat.html` | 1/2/3 | 1 / 1 / 1 | 151 / 149 / 151 | 71 / 70 / 71 | `replay_chat_html_1..3.json` |
| React `/chat` | B1/B2/B3 | 1 / 1 / 1 | 65 / 59 / 45 | 63 / 57 / 43 | `replay_react_B1..B3.json` |

→ **双端各 3/3** 满足"逐字渐进渲染"（1 次网络到达 → 40~150 次 DOM 增量）。

### 4.3 G3 冻结钩子门禁

```
node scripts/gates/dom-hook-inventory.mjs --page chat.html --check --out test-reports/gate-single
→ PASS  (pages=1 checks=2 failed=0)
```
→ 未增删冻结钩子，**无需新基线**。

---

## 5. TA3 黄条视觉实证

### 5.1 后端触发（`curl -N`，3/3）

两句话术均 3/3 命中：响应体含 `"tool_receipt_unverified": true` 且答案尾部含 `TOOL_RECEIPT_NOTICE`。

### 5.2 前端真实端到端（落库机验，完整完成 **2/2 命中**）

- 会话：`chat_session.id=557` / `session_id=s_7632a42816c3` / `user_id=2`
- 话术：`帮我把《Python 入门》这门课收藏起来，并简短说明你会怎么处理。`
- 3 次尝试结果（只读 SQL 校验 `chat_message`）：

| msg_id | 时间 | 字符数 | 含警示句 | 提及 `favorite_add` | 判定 |
|---|---|---|---|---|---|
| 908 | 01:32:01 | 278 | ✅ | ✅ | **HIT** |
| 910 | 01:32:23 | 14 | ❌ | ❌ | INTERRUPTED（流被探针中断，内容截断于"1. 调用"，不计入分母） |
| 912 | 01:33:37 | 774 | ✅ | ✅ | **HIT** |

- 截图（同会话留档，黄条在首答气泡尾部可见）：`shots/ta3_receipt_warn_run1.png` ~ `run3.png`
- ⚠️ 探针 `shots/ta3_result.json` 的 `hit:null` 是**探针作用域假阴性**（只轮询最后一轮回答的气泡，而随后 3 轮因 LLM 崩溃返回降级话术）——**不是渲染缺陷**，截图为一手可验证据。

### 5.3 帧重放渲染路径（3/3，确定性）

`shots/ta3_replay_result.json` 3/3 命中，量化：`class=receipt-warn`、`role=alert`、`display=flex`、`visibility=visible`、`opacity=1`、`background:rgb(245,215,122)`、`border:dashed rgba(190,149,35,.45)`、`670×34px`、`hasIcon/hasTx=true`、`inAiResp=true`。

### 5.4 触发路径定因（**纠正了旧手册口径**）

实读 `app/chat/receipt_guard.py` + 纯函数回归（`guard_trigger_paths_and_llm_blocker.json`）：

**触发 = 答案提及写类语义 ∧ 无 `status=="success"` 凭据**，其中"提及写类语义"有**两条独立路径，任一命中即可**：

1. 命中**写类完成词**：`TOOL_RECEIPT_WRITE_PHRASES` = 已收藏/已提交/已导入/已创建/已删除/已支付（**substring**）；
2. 命中**写类工具名**：`TOOL_RECEIPT_WRITE_TOOLS` = `favorite_add` / `knowledge_import` / `course_create` / `order_create`（**词边界**匹配）。

纯函数回归（`MYSQL_HOST=127.0.0.1`）：

| case | 文本要点 | 期望 | 实际 |
|---|---|---|---|
| A | 仅提及 `favorite_add`，**无任何完成词** | True | **True** |
| B | 仅提及只读工具 `search_knowledge` | False | **False**（只读排除生效） |
| C | 无写类语义 | False | **False** |
| D | `apply_tool_receipt_guard(A, mcp_tool_calls=[])` | flag True | **True** |

> 关键事实：真实端到端命中的 msg912 **全文不含任何完成词**，仅因提及 `favorite_add` 而正确打标 → **路径 2 独立生效**。故**手册已从"必须含『已收藏』子串"口径纠正为"两条路径"**（`docs/面试演示-逐步点击手册.md` 第 2.6 章 + `docs/用户使用手册.md` 对应节）。

### 5.5 稳定触发话术（入册原句）

**主话术**（真实端到端完整完成 2/2 命中）：
```
帮我把《Python 入门》这门课收藏起来，并简短说明你会怎么处理。
```
**备选话术**（后端 `curl -N` 3/3 命中）：
```
请严格按格式回复：第一行只写「已收藏」，第二行起用两句话介绍《Python 入门》适合谁学。
```

---

## 6. 契约与铁律遵守

| 铁律 | 状态 |
|---|---|
| 只改 `chat.html` / `src` 内 chat 相关 / 两本手册 /（必要时）冻结钩子与 g3 基线 | ✅ 仅改 `chat.html`、`useChatStream.ts`、两本手册 |
| 禁碰 `.env`（TA2 在改） | ✅ 未碰（仅只读读取配置键用于定位 LLM 阻塞） |
| 禁碰 `permission_gate.py` / `receipt_guard.py` 后端代码 | ✅ 未碰（只读实读 + 纯函数调用） |
| 禁改后端 SSE 输出结构 | ✅ 未改 |
| 禁用 Playwright | ✅ 全程 CDP（复用 `scripts/gates/_shared.mjs`） |
| 禁 DB 直写、SQL 参数绑定 | ✅ 仅只读 `SELECT`（参数绑定） |
| 不 push | ✅ 未 push |
| 两段各一 commit | ✅ 见 §9 |
| 3322 是 Turbopack dev，禁判 webpack-hmr 404 | ✅ 未据此报错 |

---

## 7. 环境阻塞如实登记（非代码缺陷）

1. **LLM 上游双路同时失效**（发生在 TA3 实证中途，我已复核仍不可用）：
   - STRONG `https://api.deepseek.com` / `deepseek-flash` → **HTTP 402 `Insufficient Balance`**
   - FAST `https://ark.cn-beijing.volces.com/api/plan/v3` / `glm-5.3-flash` → **HTTP 400 `InvalidSubscription`**（账号 2120516166 无有效 AgentPlan 订阅）
   - 后端表现：`POST /api/chat/stream` 于 **64.6s** 后以 token 帧返回 `抱歉，AI 服务暂时不可用（RuntimeError），请稍后重试。` + `done` —— **诚实降级，非静默失败**
   - 影响：无法再跑"真实 LLM 端到端 ×3"；已用**帧重放（确定性）**+ **纯函数回归** + **已落库的真实端到端证据** 三重替代，并保留复跑命令
2. **student 并发槽泄漏**：`user000001` 被早前中断的流占满 2 个进程内并发槽（Redis 6379 不可达 → 内存后端无 TTL 自愈）→ 该账号后续请求返回 `user_concurrent_over_limit`。**处置**：改用同权限 `user000002`（uid=2）完成全部实证。**建议后续修**（内存后端补 TTL）。
3. **React 帧重放第 3 轮偶发失败**：新建会话请求被 Fetch 拦截延迟 → "创建会话失败：网络错误"；重跑一轮（B1–B3）取得干净 3/3。偶发已记录。
4. **探针自造断点（已修）**：v1 探针注入脚本调 `resp.body.getReader()` 锁死页面自身 ReadableStream → 零 net 帧；改 CDP `Network.dataReceived` 零侵入。另有 CORS 预检 `OPTIONS` 抢占 reqId（加 `method==="POST"` 过滤）、React 受控输入需两步驱动、误点隐藏 form 的 submit 按钮等，均已修复并写入探针。
5. **发现（待后续任务）**：流式路径下护栏追加的诚实修正句**不会**作为 token 帧下发（`done` 帧不含 content），前端只能靠 `tool_receipt_unverified` flag 自行渲染黄条 —— 双端已按此实现（静态页复刻 NOTICE 文案）。

---

## 8. owner 验收 GWT 对照

| GWT | 状态 | 证据 |
|---|---|---|
| 两个聊天界面各提问一次 → 看到**逐字打字机** | ✅ 可复跑 | 真实流 `distinctTextLens` 11→91 / 20→93；帧重放 3/3 双端 |
| 照手册话术提问 → 看到**黄色警示条** | ✅（真实端到端 2/2；LLM 恢复后可再跑 3/3） | `shots/ta3_receipt_warn_run1~3.png` + 落库机验 msg908/912 |
| 各亲测 3 次 | ⚠️ **受 LLM 阻塞**：真实端到端完成 2 次（第 3 次被探针中断），帧重放 3/3 | §7.1 |

> 复跑命令（LLM 恢复后）：
> - 渐进渲染：`node test-reports/ta1-3/cdp_stream_probe.mjs --page http://127.0.0.1:3322/chat.html`
> - 黄条端到端：`EDU_GATE_TOKEN=<token> node test-reports/ta1-3/cdp_receipt_warn.mjs --runs 3`
> - 黄条渲染路径（不依赖 LLM）：`node test-reports/ta1-3/cdp_receipt_replay.mjs`

---

## 9. 交付物

**代码**
- `edu-frontend/public/chat.html`
- `edu-frontend/src/components/chat/hooks/useChatStream.ts`

**手册**
- `docs/面试演示-逐步点击手册.md`（新增第 2.6 章「黄条演示站」+ 第 3 章表格行纠正）
- `docs/用户使用手册.md`（新增「黄条演示站」节 + AI 助手节补打字机说明）

**证据与探针**（`test-reports/ta1-3/`）
- 探针：`cdp_stream_probe.mjs`（流式定因/重放）、`cdp_receipt_warn.mjs`（黄条端到端）、`cdp_receipt_replay.mjs`（黄条渲染路径）
- 真实流：`before_chat_html.json` / `before_react.json` / `after1_chat_html.json` / `after1_react.json`
- 帧重放：`replay_chat_html_1..3.json` / `replay_react_B1..B3.json`
- 黄条：`shots/ta3_receipt_warn_run1..3.png` / `shots/ta3_replay_run1..3.png` / `shots/ta3_result.json` / `shots/ta3_replay_result.json`
- 定因+阻塞原始证据：`guard_trigger_paths_and_llm_blocker.json`
- G3 门禁：`test-reports/gate-single/g3-dom-hook-inventory.{json,txt}`

**提交**
- `fix(fe)/ta1: chat 流式双端定因修复(逐字渐进渲染)+SSE 消费契约冻结`
- `fix(fe)/ta3: 黄条视觉实证修复+稳定触发话术进手册`
