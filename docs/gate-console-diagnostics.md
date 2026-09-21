# G8 console 诊断分类与豁免清单（GATE-V2 工作项6）

> 建立日期：2026-09-21（feature/opt-waves）。口径来源：`TO-EXEC-GATE-V2` 工作项 6。
> 复跑命令（dev 态 3322 + 后端 9988 存活窗口）：
> `EDU_GATE_TOKEN=<token> node scripts/gates/asset-cache-gate.mjs --all`

## 一、分类规则（今后每轮 G8 诊断按此归类）

| 类别 | 判定特征 | 处置 |
| --- | --- | --- |
| A 静态资源 404 | `LOG: Failed to load resource` 且 URL 指向本地静态资产（`/assets/**`、`/*.css`、`/*.js`、`/*.svg`） | **修**：页面引用了不存在的资产 → 属页面真 bug，按铁律停手上报编排者裁定，不代改 |
| B JS 异常 | `EXC:` 或 `CONSOLE:` 指向页面脚本堆栈 | **修**：同上，停手上报 |
| C 预存 API 行为噪声 | `CONSOLE: [EAPI] ...` 与/或 `LOG: Failed to load resource: net::ERR_...` 且 URL 指向 `:9988/api/**` | **豁免登记**（本清单 §三），不阻断、不代改 |

## 二、当前全站实测（2026-09-21，dev 3322 + 9988 健康 + 有效 token）

- `node scripts/gates/asset-cache-gate.mjs --all`：**25 页 200 检查，failed=0，warnings=0，诊断合计 0**。
- **归因更正（2026-09-21，GATE-V2 执行者复核）**：编排者验收窗口的「18 条诊断」**不是环境瞬态，而是门禁自身插桩伪影**——G8 旧实现用 `Fetch.enable`（pattern `*.woff2*`）拦字体，CDP Fetch 域激活后页内 fetch 整批失败（pattern 不匹配也失效），每页 7~14 条 `[EAPI] Failed to fetch` + `LOG: ERR_FAILED`，与验收窗口 14/12/12/8/8 量级吻合（复核实测 106 条/18 页，me=14 完全复现）。已改为 `Network.setBlockedURLs`（commit `1fe9623`）后健康窗口实测 0 条、稳定可复跑。隔离证据：仅开 `Fetch.enable` → 14 诊断；仅 `setCacheDisabled` → 0；二者全关 → 0。
- 以下 §三 C-1 豁免**降级为条件性安全网**（后端真不可用窗口），健康窗口不参与归因。

## 三、豁免清单

### C-1 `[EAPI]` API 失败日志（机制性噪声，by design）

- **来源**：`edu-frontend/public/edu-api.js:116` —— 所有 API 错误统一 `console.error("[EAPI]", err, ...)` 后 rethrow（task122「不再静默吞错」改造的有意行为）；浏览器网络层对每个失败请求另发一条 `LOG: Failed to load resource`。
- **触发条件**：门禁运行窗口内后端 9988 不可达 / 返回 401 / 500 / 熔断，每失败一次 API 调用产生 1~2 条诊断。
- **量级佐证**：诊断头部页恰为 API 调用最重的页（静态调用点 me=8、dashboard=6、practice=10、coupons=9、courses=6，叠加运行时循环与 `auth/me`、网络层 LOG 后与验收窗口观察的 14/12/12/8/8 量级吻合）。
- **处置**：记 SKIP/非阻断（G8 console-errors 本就 warning 级）。**豁免有效前提**：仅当诊断文本指向 `:9988/api/**` 或 `[EAPI]`；出现指向静态资产或页面脚本堆栈的条目时本豁免不适用，按 A/B 类处置。

## 四、维持 0 诊断的运行前提

1. 3322 处于 **dev 态**（G6/G7/G8/G9 已接线 `assertDevBase` fail-fast，prod 态直接拒绝启动）。
2. 后端 9988 存活且未熔断（`/api/health` 类探测通过）。
3. `EDU_GATE_TOKEN` 注入**未过期** admin token（`assertFreshGateToken` 已对可解码 JWT 做 exp 预检，过期直接拒绝启动；实证：token 过期会使 auth 守卫页静默降级，coupons.html 曾假红 tab-reachable 14/68，新 token 复跑即 68/68 全绿）。另注意 `--all` 长跑（约 6 分钟）起跑前必须用新 token，避免中途过期。
