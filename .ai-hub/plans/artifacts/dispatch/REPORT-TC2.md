# REPORT-TC2 — 盲测 B10/B11/B12 执行报告（owner 口径 3×3）

- **派发单**：`.ai-hub/plans/artifacts/dispatch/TO-EXEC-TC2.md`
- **分支**：`feature/opt-waves`
- **执行日期**：2026-09-24
- **执行者**：本会话（遵守铁律：零代码改动、DB 只读、token 运行时注入禁落盘、禁 Playwright、UI 层用 CDP）
- **服务**：仓库根 `start-eduagent.cmd` 启动；后端 9988 / 前端 3322 在线（实测 `http=200`）
- **判定汇总**：B10 **6/6 PASS** · B11 **0/3 FAIL** · B12 **3/3 PASS**

---

## 1. 九轮判定表

| # | 场景 | 轮 | 端 / 角色 | owner 判据 | 实测关键值 | 判定 |
|---|---|---|---|---|---|---|
| 1 | B10 流式 | r1 | 静态 `chat.html` / student | 逐字渐进（distinctTextLens 多值） | distinctTextLens=61, finalTextLen=171 | ✅ PASS |
| 2 | B10 流式 | r2 | 静态 `chat.html` / student | 同上 | distinctTextLens=109, finalTextLen=353 | ✅ PASS |
| 3 | B10 流式 | r3 | 静态 `chat.html` / student | 同上 | distinctTextLens=100, finalTextLen=290 | ✅ PASS |
| 4 | B10 流式 | r1 | React `/chat` / student | 同上 | distinctTextLens=95, finalTextLen=4001 | ✅ PASS |
| 5 | B10 流式 | r2 | React `/chat` / student | 同上 | distinctTextLens=48, finalTextLen=2634 | ✅ PASS |
| 6 | B10 流式 | r3 | React `/chat` / student | 同上 | distinctTextLens=73, finalTextLen=2742 | ✅ PASS |
| 7 | B11 黄条 | r1 | 静态 `chat.html` / student | 黄条可见（role=alert 黄底） | receipt:null, found:false（无黄条） | ❌ FAIL |
| 8 | B11 黄条 | r2 | 静态 `chat.html` / student | 同上 | receipt:null, found:false（无黄条） | ❌ FAIL |
| 9 | B11 黄条 | r3 | 静态 `chat.html` / student | 同上 | receipt:null, found:false（无黄条） | ❌ FAIL |
| 10 | B12 HITL | r1 | 静态 `chat.html` / admin | 卡弹出→approve 落库 | 卡 `course_create/高风险/atMs≈5.0s`；approve 后 series 2979→2980 | ✅ PASS |
| 11 | B12 HITL | r2 | 静态 `chat.html` / admin | 卡弹出→reject 零落库 | 卡弹出；reject 后 series 保持 2980 | ✅ PASS |
| 12 | B12 HITL | r3 | 静态 `chat.html` / admin | 卡弹出→reject 零落库 | 卡弹出；reject 后 series 保持 2980 | ✅ PASS |

> 说明：B10 判据为「逐字渐进」，CDP 时间线 `distinctTextLens`（答案区出现过的不重复文本长度档位数）全部 ≫1，证明非「转圈后整段弹出」。B11 黄条只在 `chat.html` 有渲染逻辑（React `/chat` 经只读分析确认无 `.receipt-warn`/`#hitlCard`），故 B11/B12 均在 `chat.html` 验收。

---

## 2. 场景细节与证据

### B10 流式 UI 双端（PASS）
- 探针：`test-reports/ta1-3/cdp_stream_probe.mjs`（CDP 零侵入，复用未改），输出见 `test-reports/blind-b10-12/b10-*.json`。
- 静态端三轮 `distinctTextLens` 61/109/100、`finalTextLen` 171/353/290、`netChunks` 96/246/208、`domMutations` 131/231/209。
- React 端三轮 `distinctTextLens` 95/48/73、`finalTextLen` 4001/2634/2742、`netChunks` 48/18/38、`domMutations` 96/50/74。
- 结论：双端均肉眼可见逐字渐进，且 CDP 时间线 `distinctTextLens` 多值佐证，**PASS 3×3（6 轮全过）**。

### B11 黄条视觉（FAIL，3/3 无黄条）
- 探针：`test-reports/blind-b10-12/blind_probe.mjs`（`--mode b11`，轮询 `.receipt-warn[role="alert"]` 90s）。
- 三轮 json：`b11-r1.json` / `b11-r2.json` / `b11-r3.json`，均 `receipt:null, found:false`。
- 三张截图哈希互异（满足"截图 3 张哈希互异"的形式要求，但**内容均无黄条**）：
  - `b11-r1.png` → `81da40ff…bbb00`
  - `b11-r2.png` → `ed94191d…16cf55`
  - `b11-r3.png` → `2b00c760…d8cca`
- **最小差证（同 query、两种传输路径的不一致）**：
  - 非流式 `POST /api/chat`（同话术、student token）：响应含 `tool_receipt_unverified=True` 且答案含诚实修正句「⚠️ 上述工具操作未实际执行…」→ 证据 `b11-evidence-nonstream.json`。
  - 流式 `POST /api/chat/stream`（同话术、同 token）：`event: done` 帧 `data.tool_receipt_unverified = false`（done 帧见 `b11-evidence-stream.txt`）→ `chat.html` 的渲染条件 `done.data.tool_receipt_unverified===true` 永不满足 → 黄条不渲染。
- **根因**：流式 SSE 路径下 `receipt_guard` 未对该写类语义打标（done 帧为 `false`），而同一对话在非流式路径下判定 `True`。属护栏在流式/非流式两条链路上的行为不一致缺陷，**归返工单**（非执行者权限内，已按铁律停手、零代码改动）。

### B12 HITL 卡（PASS）
- 探针：`blind_probe.mjs`（`--mode b12`，轮询 `#hitlCard` 120s，按 `--action approve|reject` 点击 `.hitl-confirm`/`.hitl-reject`）。
- DB 只读断言（`SELECT COUNT(*) FROM series`，MySQL CLI）：
  - before = `2979`（`b12-db-before.txt`）
  - r1 approve → `2980`，新增 `series_code=b12course1` / `series_name=盲测B12验证课1` / `created_by=100003` / `created_at=2026-09-24 16:42:09`（见 `b12-db-after-approve.txt`）
  - r2 reject → 保持 `2980`（`b12-db-after-reject2.txt`）
  - r3 reject → 保持 `2980`（`b12-db-after-reject3.txt`）
- 三轮卡均 `cardShown:true`，`tool:course_create` / `risk:高风险` / `atMs≈4–5s`，按钮点击成功（`actionClicked: CLICKED_approve|CLICKED_reject`）；approve 落库、两次 reject 零落库。
- 证据：`b12-r1-approve.json`+`.png`、`b12-r2-reject.json`+`.png`、`b12-r3-reject.json`+`.png`。
- 结论：**PASS 3/3**。

---

## 3. 铁律触发与处置

- 执行单铁律：**任一场景 3 轮未全过 → 停手上报（附复现脚本与最小差证），禁自行改代码（归返工单）**。
- B11 三轮均 FAIL → **已停手**，未对任何源码/配置/页面做改动；未 push。
- 复现脚本：`test-reports/blind-b10-12/run_tc2.sh`（全量 9 轮，含登录/端点/DB 只读断言，依仓库根 `start-eduagent.cmd` 起服务）。
- 返工单建议（待编排者建单）：统一 `receipt_guard` 在流式与非流式两条链路上的 `tool_receipt_unverified` 判定与下发，使 `chat.html` 在流式黄条场景按 owner 口径可见 `role="alert"` 黄条。

---

## 4. 证据清单（全部位于 `test-reports/blind-b10-12/`）

| 文件 | 说明 |
|---|---|
| `b10-chat.html-r1.json` `b10-chat.html-r2.json` `b10-chat.html-r3.json` | B10 静态端三轮 CDP 流式探针 |
| `b10-react-r1.json` `b10-react-r2.json` `b10-react-r3.json` | B10 React 端三轮 CDP 流式探针 |
| `b11-r1.json` `b11-r2.json` `b11-r3.json` | B11 三轮黄条探测（found:false） |
| `b11-r1.png` `b11-r2.png` `b11-r3.png` | B11 三轮截图（哈希互异，无黄条） |
| `b11-evidence-nonstream.json` | 最小差证：非流式 `tool_receipt_unverified=True` + 诚实句 |
| `b11-evidence-stream.txt` | 最小差证：流式 done 帧 `tool_receipt_unverified:false` |
| `b12-r1-approve.json` `b12-r1-approve.png` | B12 r1 approve：卡弹出+落库 |
| `b12-r2-reject.json` `b12-r2-reject.png` | B12 r2 reject：卡弹出+零落库 |
| `b12-r3-reject.json` `b12-r3-reject.png` | B12 r3 reject：卡弹出+零落库 |
| `b12-db-before.txt` `b12-db-after-approve.txt` `b12-db-after-reject2.txt` `b12-db-after-reject3.txt` | B12 DB 只读断言（2979→2980→2980→2980） |
| `blind_probe.mjs` `run_tc2.sh` | 探针与全量 runner（零代码改动前提下新增的测试产物） |

---

## 5. owner 验收口径对照

> Given owner 亲手操作三场景各一次，Then 现象与盲测判定一致。

- B10：owner 亲测应看到双端逐字渐进 → 与盲测一致（PASS）。
- B11：owner 亲测**看不到黄条**（与非流式不一致）→ 与盲测一致（FAIL，需先修护栏）。
- B12：owner 亲测应看到卡后「同意出课 / 拒绝不出课」→ 与盲测一致（PASS）。

---

## 6. 提交

- 单 commit（不 push）：`test(blind)/tc2: 盲测 B10 流式/B11 黄条/B12 HITL 卡(owner 口径 3×3)`
- 仅纳入 `test-reports/blind-b10-12/` 与 `AUTO20/blind-test-queue.md`、`REPORT-TC2.md`，路径限定 `git commit -- <paths>`（禁用 `scripts/p1_commit.py`）。
