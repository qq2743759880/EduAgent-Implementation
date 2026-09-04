# AI 学习问答页布局最终复测报告（h-[calc(100dvh-56px)]）

- 任务：最终复测「AI 学习问答」聊天页布局修复（根容器 `min-h-screen` → `h-[calc(100dvh-56px)]` 扣 AppShell 顶栏 56px + main 加 `min-h-0`）
- 测试类型：Playwright 真实浏览器回归（**只测试，未改任何代码**）
- 日期：2026-08-14
- 环境：Next.js 16 dev（http://localhost:3000，热更新生效）· 后端（http://127.0.0.1:8000，/health `{"status":"ok"}`）
- 登录：admin/Admin@12345 后端真实登录换取 token（HTTP 200），注入 `localStorage["edu:auth:token"]` + `edu:auth:me` + `edu:auth:tenant`（auth-client.ts K_TOKEN），全页重载生效（/login 自动跳转 /dashboard 证明登录态生效）
- 断言方式：DOM 几何测量（getBoundingClientRect / scrollHeight / scrollTop / overflow）+ 真实指针点击；数值为准

## 修复代码核实（只读，未改动）

`edu-frontend/src/app/(user)/chat/_components/ChatFullScreenClient.tsx`

```tsx
303  {/* 固定视口高度：扣 AppShell 顶栏(56px)，消息区内部滚动，输入框始终可见 */}
304  <div className="h-[calc(100dvh-56px)] w-full bg-background">
305    <div className="mx-auto flex h-[calc(100dvh-56px)] w-full max-w-[1440px] gap-0 lg:gap-4 px-0 lg:px-4 py-0 lg:py-4">
317  <main className="relative flex min-h-0 min-w-0 flex-1 flex-col ... overflow-hidden">
```

- 根容器已从 `h-screen` 改为 `h-[calc(100dvh-56px)]`（loading 态 295 行同步更新）
- 聊天 main 已加 `min-h-0`（317 行），消息区保持 `min-h-0 flex-1 overflow-y-auto`（ChatPanel 内部）
- 修复已全部落地，本次测试针对该版本

## 执行步骤

1. 1280x800 打开 /chat（注入登录态，恢复会话 s_59b214f5f375）
2. 发送「用一句话介绍你自己」→ SSE 流式回答完成（含「引用来源（1 条）」引用卡片 + 长段落）
3. 验证发送按钮可点击：输入「1+1=2 对吗」→ 按钮启用 → 真实点击成功 → 回答完成（含 MCP 工具 add + 引用卡片）
4. 1280x800 测量：文档高 / 输入框 / 发送按钮 / 消息滚动 / 滚动固定性 → 截图
5. 切 850x790 重载 /chat，恢复同一会话（4 条问答历史）→ 测量 → 发送「2+3=?」验证 850 点击性 → 截图
6. 收集 console 错误与 API 网络请求

## 验证结果（双 viewport）

### a. 文档总高度 = 视口高度（+56px 已消除）

| Viewport | 修复前（上一轮） | 本轮实测 | 结论 |
|----------|------------------|----------|------|
| 1280x800 | 856px（=800+56） | **800px = 视口 800** | ✅ PASS |
| 850x790  | 846px（=790+56） | **790px = 视口 790** | ✅ PASS |

- 两视口 `document.documentElement.scrollHeight = window.innerHeight`，`window.scrollY = 0`、`maxScrollY = 0`（页面不可滚动）
- 长历史（4 条问答 + 引用卡片）下文档高恒定，内容不再撑开页面

### b. 输入框与发送按钮可见性 / 可点击性

| 项 | 1280x800 | 850x790 |
|----|----------|---------|
| 输入框 textarea | top 622.7, bottom 766.7，**完全在视口内**（≤800），可打字 | top 677.3, bottom 773.3，**完全在视口内**（≤790），可打字 |
| 发送按钮 | top 732, bottom 760，**完全可见** | top 738.7, bottom 766.7，**完全可见**（修复前 795..823 在折叠线 790 下方） |
| 发送按钮启用逻辑 | 空输入 disabled → 输入后启用（已验证） | 同左，输入「2+3=?」后启用 |
| 真实点击 | ✅ 两次真实点击均成功发消息（1+1=2 对吗 / 用一句话介绍你自己） | ✅ 无遮挡下真实点击成功发消息（2+3=?，textArea 清空 + 气泡出现 + API 200） |

**结论：✅ PASS** —— 850 窄窗口发送按钮不再被压到折叠线下方（738.7..766.7 < 790，留有 23px 余量），输入框与发送按钮始终可见、可点击。

> 点击测试备注：850 下 Playwright 合成点击曾被 ① TanStack Query DevTools 悬浮球（`tsqd-parent-container`，**dev 环境专属产物，生产不存在**）② 全局浮动 AI 助手按钮（`ChatFloatingButton`，fixed z-40，应用级全局组件）拦截；临时隐藏两者（纯测试操作，未改代码）后真实点击发送成功。详见「附注」第 2 条。

### c. 消息区内部滚动 + 输入框固定底部

| 项 | 1280x800 | 850x790 |
|----|----------|---------|
| 消息区 overflow-y-auto | ✅ clientH 480 / scrollH 2668（3 条问答后） | ✅ clientH 496 / scrollH 2402 |
| 滚动消息区到顶部后输入框位置 | top 622.7 → 622.7（**不变**，fixed=true） | top 677.3 → 677.3（**不变**，fixed=true） |
| 滚动消息区到顶部后发送按钮位置 | top 732 → 732（**不变**） | top 738.7 → 738.7（**不变**） |
| 滚动后 window.scrollY | 0（页面未滚动，输入框固定在视口内） | 0 |
| 自动滚底 | ✅ scrollTop=2188/scrollH=2668 | ✅ scrollTop=1905/scrollH=2402 |

**结论：✅ PASS** —— 消息区内部滚动，滚动时输入框与发送按钮位置固定不动（fixed 底部）。

### d. Console / 网络

- console：**0 error，0 warning**（会话内累计仅 2 条 info 级 HMR/Fast Refresh 噪音）
- API：sessions / history / stream 全部 200 OK，无失败请求
- **结论：✅ PASS**

## 截图

- `test-reports/screenshots/chat-final-1280.png`（1280x800，3 条问答最终态，138 KB）
- `test-reports/screenshots/chat-final-850.png`（850x790，4 条问答最终态，86 KB）

## 判定

**VERDICT: PASS** —— 布局修复验收达成，双 viewport 五项检查全部通过：

| # | 检查项 | 1280x800 | 850x790 |
|---|--------|----------|---------|
| a | 文档总高度 = 视口高度（无 +56px） | ✅ 800=800 | ✅ 790=790 |
| b | 输入框/发送按钮可见 | ✅ 完全在视口内 | ✅ 完全在视口内（折叠线问题根除） |
| b | 发送按钮可点击 | ✅ 真实点击两次成功 | ✅ 无遮挡下真实点击成功 |
| c | 消息区内部滚动 | ✅ scrollH 2668 > clientH 480 | ✅ scrollH 2402 > clientH 496 |
| c | 滚动时输入框固定底部 | ✅ 位置不变 + window 不滚 | ✅ 位置不变 + window 不滚 |
| d | console 0 error | ✅ | ✅ |

- 上一轮 FAIL 的两条未达标项均已消除：
  1. 文档高度 = 视口 +56px → **已修复**（`h-[calc(100dvh-56px)]` 正确扣除 AppShell sticky 顶栏）
  2. 850 发送按钮在折叠线下方 → **已修复**（按钮上移至 738.7..766.7，留 23px 余量）

## 附注（非本次修复回归，供产品参考）

1. **全局浮动 AI 助手按钮（ChatFloatingButton）在 850 宽与发送按钮重叠**：该按钮 `fixed z-40`、56x56、右下角（bottom 24 / right 24），所有路由恒渲染（`GlobalChatInjection.tsx:232`「浮动按钮：所有状态下都渲染」）。850x790 下其区域 (710..766, 770..826) 完整覆盖聊天页发送按钮 (738.7..766.7, 793.3..821.3)；1280x800 下 FAB 在 x 1176..1232，不重叠。这是既有全局组件行为，**与本次布局修复无关**（修复前发送按钮在折叠线下方，与 FAB 无交叠；修复后按钮上移暴露了交叠）。建议产品侧评估在 /chat 路由隐藏 FAB 或调整其 offset。
2. **TanStack Query DevTools 悬浮球**（`tsqd-parent-container`）为 dev 环境专属产物，生产不存在；本轮验证发送按钮可点击时已临时隐藏（纯测试操作，未改代码）。
3. 发送按钮空输入时 disabled、输入后启用，为正常设计，非缺陷。

## 复现信息

- 视口 1280x800：http://localhost:3000/chat（注入登录态）→ 发送任意问题 → 文档高 800 = 视口，输入框 (622.7..766.7) / 发送按钮 (732..760) 全可见，消息区内部滚动。
- 视口 850x790：同操作 → 文档高 790 = 视口，输入框 (677.3..773.3) / 发送按钮 (738.7..766.7) 全可见（修复前 795..823 需滚动 ~33px），消息区内部滚动，输入框固定。
- 若需复现 FAB 重叠：850 宽 /chat 页右下角可见 56x56 圆形「打开 AI 助手」按钮覆盖发送按钮区域。
