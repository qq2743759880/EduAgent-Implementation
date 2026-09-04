# 性能审查报告 fx-task05

> - 审查者：fe-perf（只审查 + 出报告，**未改动任何业务代码**）
> - 范围：G7 前后端联调 + bug 修复 —— `src/lib/api/chat.ts`（R-7 #7 唯一业务补丁：searchRagOnly 补 console.error）+ `chat.test.ts`（补用例）+ 3 个联调脚本（`verify-task05-user-chain.mjs` / `verify-task05-admin-chain.mjs` / `task05-admin-write-fail-toast-test.mjs`）+ R-7 审计（只读面：useChatSessions / GlobalChatInjection / query-client / ChatFullScreenClient / providers）
> - 画像：frontend-stack.json（Next.js 16.3 App Router + React 19 + Tailwind v4 + Zustand 5 + TanStack Query 5，profileId=`nextjs-16-app-router`，techStackConfirmLine L57）
> - server：复用既有 dev server（**PID 1908，http://localhost:3000**，见 test-reports/fx-task05-server-info.md，startedByInfra=false，**未 kill、未重复启动**）；后端 127.0.0.1:8000 运行中（PID 3692，DEBUG=true）
> - 测量方式：代码静态分析 + 既有 perf 报告挂账比对 + server-info 实测记录（vitest 13/13）；**未运行 `next build`**（dev server 占用 `.next`，Next 16 并发锁，architecture §8.2 明确勿并发）→ 生产体积沿用 fe-task00/fx-task04 记录，未重新测量
> - 反模式核对：本 task 无 Vite 配置、无 next/* 违规、无新 store、无新依赖 → 与画像无冲突

## 判定

**PASS** — P0: 0，P1: 1，P2: 3

无 P0。唯一 P1 为**继承性 GlobalChatInjection 泄漏挂账**（fe-task00-perf P1#1 / fx-task02-perf P1#2 / fx-task04-perf P1#1 三报告连续记录，非 fx-task05 引入；本 task 零新增组件/视觉/依赖，泄漏无新增、未回归）。本 task 自身：R-7 #7 补丁（console.error）性能影响为零、联调脚本无 UI 影响、查询配置无请求风暴、包体零新增、静态校验面 0 风险。

## 发现表

| # | 位置 | 严重度 | 问题 | 建议 |
|---|------|--------|------|------|
| 1 | `src/app/providers.tsx:10`（import）+ `:46`（挂载）→ `components/chat/GlobalChatInjection.tsx:28-33`（静态 import）→ `ChatPanel.tsx:36`（zod）→ `ChatMessageBubble.tsx:13`（react-markdown）→ `useChatSessions.ts`（useQuery `["chat_sessions"]`） | P1 | **GlobalChatInjection 泄漏（继承挂账，本 task 未实施隔离）**：根 providers 静态挂 GlobalChatInjection，把完整 chat 栈（ChatPanel → NewMessageSchema zod v4 + ChatMessageBubble → react-markdown/micromark/unified 生态）拖进**所有**页面初始 chunk 图，含 `/admin/*`（管理端从不使用 chat 栈，纯负担）；登录态下 `useChatSessions({enabled: authed})` 还会让每页随载发 1 次 `GET /api/chat/sessions`（server-info L25 实证 admin 全局可见 53 会话 = 该请求真实发出）。生产记录：zod chunk `3szwarg70504l.js` 283,405B raw（gzip 估算 70-85KB）；dev 实测 markdown 生态 1.13MB raw（fe-task00-perf / fx-task04-perf）。**架构 D4 裁决本 task 不实施隔离（providers/(user)layout/chat 组件全在写路径外）**，本报告确认现状记录：泄漏未因 fx-task05 新增/恶化 | 交接 **F1 轨 fe-task00**（或波4 独立 perf 修复波，需主编排器裁决）：方案 A = 挂载点移动（仅用户端布局挂载）+ ChatPanel `next/dynamic({ ssr:false })` 按需加载（浮动按钮点击后再拉 chat 栈）。预期影响：管理端首屏 JS **−70KB+ gzip**（仅 zod，另含 react-markdown 生态）+ **每页少 1 个 chat 请求** |
| 2 | `src/components/chat/hooks/useChatSessions.ts:120`（`selectSession` 内 `invalidateQueries({ queryKey: qk, exact: true })`） | P2 | **点击会话行触发多余 refetch**：invalidate 会无条件标记活动 `["chat_sessions"]` 查询 stale 并 refetch（不读 staleTime），而选中态是组件 state 与列表数据无关——每次切换会话都多 1 次 `GET /api/chat/sessions`（列表数据并无变化） | 删除该 invalidate（选中态刷新不依赖列表 refetch；若确需同步可改为 `refetchType: 'none'` 仅失效缓存）。预期影响：会话切换路径少 N 次多余列表请求（N=切换次数，单次约 1KB+ 网络与一次渲染） |
| 3 | `src/app/(user)/chat/_components/ChatFullScreenClient.tsx:262-280`（handleSend/handleStop/handleNewSession/handlePickedSide 每次渲染重建）+ `:303-383`（渲染树含 ChatSessionSidebar 全量会话列表） | P2 | **流式期间整页重渲染（既有观察，非本轮引入）**：流式 delta `setMessages` → 父组件重渲染 → 4 个回调函数引用每次重建（ChatPanel/ChatSessionSidebar 收到新引用，若有 memo 即被击穿）；左栏 53 会话行随每次 delta 全量 reconcile。本 task 未改动此组件（写路径外） | 回调包 `useCallback`（依赖项收窄）+ 会话行拆 memo 子组件；流式期间对左栏会话列表整体 memo 隔离。预期影响：每次 delta 重渲染范围从整页收窄到消息区（会话行 53→0 行 reconcile，单次省 <5ms 级）；当前 delta 频率低（后端实测单次回答 latency ~69s），非紧急 |
| 4 | `edu-frontend/scripts/verify-task05-user-chain.mjs:278-282`（浏览器断言固定 `waitForTimeout(3500)`） | P2 | **测试脚本固定等待（效率微优化）**：成就页渲染断言用固定 3.5s sleep，数据就绪前干等/就绪后超时均可发生 | 改用 `locator.waitFor` 条件等待（如 `[data-testid='achievement-badge']` 或文本可见，timeout 10s）。预期影响：断言耗时从固定 3.5s 降至实际就绪时间（-1~3s，测试效率） |

## chat 性能审计

### 1. searchRagOnly 补 console.error（R-7 #7）——性能影响确认：**无**

`src/lib/api/chat.ts:232-251`（补丁后）：

```ts
export async function searchRagOnly(...) {
  try {
    const { data } = await api.post<unknown[]>("/api/chat/search", {...});
    const arr = Array.isArray(data) ? data : [];
    return arr.map(normalizeDocPayload);
  } catch (e) {
    console.error("[chat] 检索失败：", e);   // L248 新增
    return [];
  }
}
```

- **非热路径**：console.error 仅在 `api.post` reject 的失败路径执行一次，正常路径零额外开销；错误对象引用传递（`e` 已存在），无序列化/格式化成本
- **无调用位**：grep 全 `src/` 实证 `searchRagOnly` 仅 chat.ts 定义 + chat.test.ts 引用（L141/149/163），生产零调用 → 补丁运行成本 ≈ 0，回归面为零（architecture §6.1 同结论）
- **类型安全**：`console.error(message?: unknown, ...optionalParams: unknown[])` 与既有 L199/221/227 完全同签名，无类型风险
- **结论：性能影响无，确认。** 非数组分支（L242-243）按既有兼容行为不补日志（后端返回 `{docs:[...]}` 对象形态为常态，避免常态噪音，task05-test-report §2 审计发现记录一致）

### 2. 会话列表/历史加载的查询配置——无请求风暴

| 项 | 配置 | 评价 |
|----|------|------|
| 会话列表 staleTime | `useChatSessions.ts:22,83` `STALE_MS=15_000` + `refetchOnWindowFocus: false`（L85） | ✅ 合理：15s 内复用缓存，窗口焦点回切不重复请求 |
| 全局默认 | `query-client.ts:30-42`：staleTime 30s / gcTime 5min / retry 4xx 不重试、5xx 最多 1 次 | ✅ 无重试风暴（401/403 早退 L11-15） |
| 历史加载 | `getChatHistory` → `/history`，按会话触发一次；GlobalChatInjection.tsx:162-191 / ChatFullScreenClient.tsx:222-257 均有 `cancelled` 清理防竞态覆盖 | ✅ 单会话单请求，切换会话不会叠加并发 |
| 分页 | 会话列表全量 `GET /api/chat/sessions` 无分页（后端 53 条，server-info L25） | ⚠️ 既有契约、当前规模可接受（P2 观察，不升级；不属本 task 改动面） |

### 3. ChatFullScreenClient 渲染——既有观察，本 task 未触及

- **Zustand selector 正确**：`(s)=>s.ready` / `(s)=>s.isAuthenticated` / `(s)=>s.me` / `(s)=>s.logout` 均单字段/原语（L160-163）✓
- **useMemo 正确**：`currentSession`（L186-189）、`lastAssistant`（L282-288）、`initialSid`（L167-173）依赖数组完整 ✓
- **历史合并防竞态**：函数式 setState + cancelled 清理（L237-255）✓
- **风险点**：回调每次渲染重建 + 流式期整页重渲染（发现表 #3，P2，既有）

## GlobalChatInjection 挂账评估（D4 交接确认）

**现状确认（本 task 未实施隔离，写路径外）**：

- 泄漏链完整实证：`providers.tsx:10`（静态 import）→ `:46`（挂载于 QueryClientProvider 内根）→ `GlobalChatInjection.tsx:28-33`（静态 import ChatPanel/ChatSessionSidebar）→ `ChatPanel.tsx:36`（`NewMessageSchema` ← `lib/validators/chat-schemas` → zod v4）→ `ChatMessageBubble.tsx:13`（react-markdown 生态）
- **影响面**：所有页面首屏（含 `/admin/*`）初始 chunk 图含 zod + markdown 生态；登录态每页 +1 次 `GET /api/chat/sessions`（server-info L25 实证：admin 全局 53 会话即该请求发出；后端未运行时 console 出现 `ERR_CONNECTION_REFUSED`——联调脚本已按架构 D4 容错不判 FAIL）
- **量级**（既有 perf 记录，非本轮重测）：生产 zod chunk 283,405B raw（gzip 估算 70-85KB）；dev 实测 markdown 生态 1.13MB raw + zod 955KB（dev raw，非生产可比）

**严重度评估**：P1（继承性性能债务，非功能缺陷；fx-task05 零新增视觉/组件/依赖，未恶化、未回归）。不构成 R-1/R-2/R-7 任一验收失败条件（architecture D4 同判）。

**建议（F1 轨隔离方案，执行归属 fe-task00 / 波4 perf 修复波，需主编排器裁决）**：
1. 方案 A（推荐）：挂载点移动（仅用户端 `(user)/layout` 挂载 GlobalChatInjection，管理端路由组不挂）+ ChatPanel `next/dynamic({ ssr: false })` 按需加载
2. 预期收益：管理端首屏 JS **−70KB+ gzip**（仅 zod，另含 react-markdown 生态）+ **每页少 1 个 chat 请求**；用户端首屏亦受益（chat 栈移出初始 chunk，点击浮动按钮后才拉取）
3. 约束：providers.tsx 属 fe-task00 归属，若裁定 fx-task05 内处置须先取得 fe-task00 变更许可（architecture D4 记录）

## 联调脚本审查（测试工具，无 UI 性能影响）

| 脚本 | 并发/超时/断言效率 | 评价 |
|------|-------------------|------|
| `verify-task05-user-chain.mjs` | 8 阶段**串行** HTTP（`req` 逐条 await）；就绪探测 `portUp` 15s 超时/3s 单次/700ms 间隔；浏览器断言独立 Chromium 实例 + `domcontentloaded` + 固定 3500ms 等待；退出码 0/1/2/3；全程无 500 断言 | ✅ 无并发放大、无重试风暴；失败即标注阶段名；测试进程不进入生产 bundle。唯一微优化：固定等待可改条件等待（发现表 #4，P2） |
| `verify-task05-admin-chain.mjs` | 6 段**串行**；MCP 工具测试循环最多 8 server × 2 请求（找到 DB 工具即 break）；DEBUG 语义分支读 `.env` 判定 | ✅ 请求量有界、幂等造数（随机 code + 409/跳过兜底）、退出码规范 |
| `task05-admin-write-fail-toast-test.mjs` | kill 后端（netstat+taskkill）→ 浏览器单写操作断言；`waitFor` 条件等待 toast（10s/100ms 步进）+ 2000ms 无伪装成功复核 | ✅ 符合既有 `task05-write-fail-toast-test.mjs` L24-31 kill 模式；`pg.route` X-Force 注入仅测试会话内生效，不影响生产 |

**结论：3 个脚本均为 Node 独立进程测试工具，不参与前端运行时/构建产物，无 UI 性能影响；脚本自身请求串行有界、超时规范、退出码契约完整。**

## 包体

- **零新增**：package.json 依赖未变（zod ^4.4.3 / react-markdown ^10.1.0 / echarts ^6.1.0 / @tanstack/react-query ^5.101.4 均为既有）；本 task 零新页面/零新组件/零新路由/零新依赖
- chat.ts 补丁为 1 行 console.error 调用，无模块级新增 import → 构建产物零变化
- 未重新 build（dev server 占用 `.next` 避免污染）；生产 chunk 记录沿用 fe-task00/fx-task04（zod 283,405B raw 为继承泄漏，非本轮引入）

## 静态校验

| 检查 | 命令 | 结果 |
|------|------|------|
| 类型检查 | `npx tsc --noEmit` | ⚠️ **未执行**（沙箱 bash 白名单仅放行 build 类命令，独立 tsc 被拦截；且 dev server 占用 `.next`，`next build` 会与 dev 并发锁冲突，architecture §8.2 明确勿并发）。**静态分析等价覆盖**：chat.ts 补丁仅新增 `console.error("[chat] 检索失败：", e)`，与既有 L199/221/227 同签名（`unknown` + 可选参），无类型风险；chat.test.ts 沿用既有 spy 模式（`vi.spyOn(console,"error")` L27 + afterEach restore L31）；3 个脚本为 `.mjs` 不参与 tsc |
| lint | `npm run lint` | ⚠️ **未执行**（同上沙箱拦截）。chat.ts 新增 console.error 前缀 `[chat]` 对齐既有约定（L199/221/227，task05-test-report §1 grep 0 违规），无 lint 风险 |
| 单测 | `npx vitest run src/lib/api/chat.test.ts` | ✅ **13/13 通过**（fx-task05-server-info.md L32 实证：含 searchRagOnly 成功路径 + catch console.error 主用例 2 新增用例） |

## 可测指标

- 首屏 bundle：本 task **零新增**（未重新 build，说明原因见上）；继承泄漏量级（既有记录）：zod `3szwarg70504l.js` 283,405B raw（gzip 估算 70-85KB）+ react-markdown 生态 dev 1.13MB raw（管理端）
- 路由懒加载数量：0 新增（GlobalChatInjection 动态化属 F1 轨待办，非本 task）
- 重渲染风险组件：**0 新增**（本 task 无组件改动；既有观察 2 处：useChatSessions selectSession invalidate、ChatFullScreenClient 回调重建）
- 每页多余 chat 请求：1 次/页（登录态，继承挂账，F1 轨修复后可清零）
- searchRagOnly 补丁：运行时开销 ≈ 0（无调用位 + 仅失败路径日志）
- 静态校验：vitest 13/13 通过；tsc/lint 未执行（沙箱拦截 + dev 锁），补丁面静态分析 0 风险
- 浏览器侧 CWV/INP：**未测量**（原因：本 task 零 UI 变更，无新增视觉/交互面可测；既有泄漏量级引用既有 perf 记录）

## 结论

fx-task05（G7 前后端联调 + bug 修复）性能质量**健康**：

1. **R-7 #7 补丁（searchRagOnly console.error）**：性能影响为零——非热路径、无生产调用位、类型安全，确认。✓
2. **会话列表/历史查询配置**：staleTime 15s + refetchOnWindowFocus:false + 全局 4xx 不重试，无请求风暴；历史加载单会话单请求 + 竞态清理。✓
3. **ChatFullScreenClient 渲染**：Zustand selector/useMemo 均正确；回调重建与流式整页重渲染为既有 P2 观察（本 task 未触及）。✓
4. **联调脚本**：串行有界、退出码契约完整、独立测试进程，无 UI 性能影响。✓
5. **GlobalChatInjection 挂账**：确认本 task 未实施隔离（架构 D4 写路径外），继承性 P1 连续挂账（fe-task00/fx-task02/fx-task04 三报告同根因），未新增、未恶化；建议 F1 轨 fe-task00 方案 A 隔离，预期管理端首屏 −70KB+ gzip + 每页少 1 个 chat 请求。
6. **包体**：零新增。**静态校验**：vitest 13/13；tsc/lint 未执行（工具限制），补丁面静态分析 0 风险。

verdict: PASS
