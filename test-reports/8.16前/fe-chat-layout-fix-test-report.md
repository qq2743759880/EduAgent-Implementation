# AI 学习问答页布局修复复测报告（h-screen）

- 任务：复测「AI 学习问答」聊天页布局修复（`min-h-screen` → `h-screen`）
- 测试类型：Playwright 真实浏览器回归（只测试，未改代码）
- 日期：2026-08-14
- 环境：Next.js 16 dev（http://localhost:3000）· 后端（http://127.0.0.1:8000，/health OK）
- 登录：admin/Admin@12345 真实登录换取 token，注入 `localStorage["edu:auth:token"]`（auth-client.ts K_TOKEN）+ `edu:auth:me`，全页重载生效
- 断言方式：DOM 几何测量（getBoundingClientRect / scrollHeight / overflow），模型不支持读图，数值为准

## 修复代码核实（只读）

`edu-frontend/src/app/(user)/chat/_components/ChatFullScreenClient.tsx:303-305`

```tsx
{/* 固定视口高度：消息区内部滚动，输入框始终可见（min-h-screen 会被内容撑高导致输入框滑出视口） */}
<div className="h-screen w-full bg-background">
  <div className="mx-auto flex h-screen w-full max-w-[1440px] gap-0 lg:gap-4 px-0 lg:px-4 py-0 lg:py-4">
```

修复已落地。消息区 `ChatPanel.tsx:312` 为 `min-h-0 flex-1 overflow-y-auto`，布局链：`h-screen` → `flex` → `main overflow-hidden` → `min-h-0 flex-1` → ChatPanel `h-full` → 消息区内部滚动 + 底部 Composer。

## 执行步骤

1. 打开 http://localhost:3000/chat（注入登录态）→ 登录态生效（`?sid=` 恢复历史会话）
2. 新建会话，发送「用一句话介绍你自己」→ SSE 流式回答完成（含「引用来源（1 条）」引用卡片，相关度 37%；回答为长段落 + 建议 + 引用）
3. 1280x800 下测量：文档高 / 输入框 / 发送按钮 / 消息滚动区 / 滚动固定性
4. 850x790 下重载同一会话，再发「你擅长哪些学科？」→ 同上测量
5. 收集 console 错误与 API 网络请求

## 验证结果（双 viewport）

### a. 文档总高度 vs 视口

| Viewport | 修复前 | 修复后实测 | 结论 |
|----------|--------|------------|------|
| 1280x800 | 3360px | **856px** | 大幅收敛（-75%）；仍超视口 56px |
| 850x790  | —      | **846px** | 同上（+56px） |

- 内容无关性：空会话 / 2 条消息 / 10 条长历史会话 → doc 恒为 856（1280）；2→3 条消息 doc 恒为 846（850）。**内容不再撑开页面（主 Bug 根除）**。
- 残余溢出 56px 来源（已定位）：AppShell（`components/layout/AppShell.tsx:127,222`）根 `min-h-screen flex` + 主区 `flex-1 flex-col`，sticky 顶栏 `h-14`（56px）在流内占位；聊天根 `h-screen`=100vh(800px) 位于顶栏之下 → 文档 = 800+56=856。`h-screen` 未扣除顶栏高度。

### b. 发送后输入框可见性 / 发送按钮可点击

| 项 | 1280x800 | 850x790 |
|----|----------|---------|
| 输入框 textarea | top=663, bottom=807（底部 7px padding 在折叠线下；打字行完全可见） | top=733, bottom=829（底部 39px 在折叠线下） |
| 发送按钮 | **top=772, bottom=800 完全可见**，可点击（实际点击成功发消息） | **top=795, bottom=823 整体在折叠线(790)下方**，需滚动 ~5px 才可见/可点 |
| 无需滚动使用 | ✅ 可打字可发送 | ⚠️ 可打字，但发送按钮被顶栏+移动端 header 挤出视口 |

- 850 更差的原因：<lg 断点下面板内出现移动端 header（`lg:hidden` ~55px），把 Composer 进一步下压。
- 说明：850 下 Playwright 点击发送按钮时，页面被自动滚动约 33px，且被 TanStack DevTools 悬浮球（dev 环境产物，生产不存在）拦截；改用程序化 `.click()` 成功触发发送（按钮 onClick 逻辑正常，未 disabled）。

### c. 消息区内部滚动 + 输入框固定（✅ 双 viewport 通过）

| 项 | 1280x800 | 850x790 |
|----|----------|---------|
| 消息区 overflow-y-auto | ✅（scrollH 1093 > clientH 536） | ✅（scrollH 1402 > clientH 552） |
| 滚动消息区到顶部后输入框位置 | top 663 不变（fixed=true） | top 733 不变（fixed=true） |
| 滚动后输入框仍在视口 | ✅（且 window.scrollY=0，页面未滚动） | ✅ |
| 自动滚底 | ✅（scrollTop=556/scrollHeight=1093） | ✅ |

### d. Console / 网络

- console：**0 error，0 warning**（仅 React DevTools 提示 + HMR/Fast Refresh 噪音）
- API：sessions / history / stream 全部 200 OK，无失败请求

## 截图

- `test-reports/screenshots/chat-fixed-1280.png`（1280x800 消息后最终态）
- `test-reports/screenshots/chat-fixed-850.png`（850x790 消息后最终态）
- `test-reports/screenshots/chat-fixed-1280-initial.png`（1280x800 空会话初始态）

## 判定

**VERDICT: FAIL（主 Bug 已修复，但严格验收未完全达成，存在系统性残余缺陷）**

通过项：
- ✅ 内容不再撑开页面：3360px → 856/846px，且与消息量无关（主 Bug 根除）
- ✅ 消息区内部滚动（overflow-y-auto）生效，滚动消息时输入框 + 发送按钮位置固定不动
- ✅ 1280x800 下输入框可用、发送按钮完全可见可点击（原始 Bug 视口下的核心场景达标）
- ✅ 0 console 错误，API 全 200

未达标项（需补充修复）：
1. **文档高度 = 视口 + 56px（两视口均如此）**：`h-screen`(100vh) 未扣除 AppShell sticky 顶栏（56px），严格不满足「文档总高度 ≈ 视口高度」。建议改为 `h-[calc(100dvh-56px)]` 或让 AppShell 主区对聊天页固定高度。
2. **850x790（<lg）发送按钮整体在折叠线下方**：移动端 header（`lg:hidden` ~55px）出现在 h-screen 容器内部，把 Composer 挤出视口 33-56px，需滚动页面才能点发送，严格不满足「输入框始终可见（无需滚动）+ 发送按钮可点击」。

修复建议（非本次执行范围）：聊天根改用 `h-[calc(100dvh-56px)]` 并在 <lg 时将移动端 header 移出 h-screen 流（或同减法计入），即可让文档 = 视口、输入区全可见。

## 复现信息

- 视口 850x790：http://localhost:3000/chat → 新建会话 → 发送任意消息 → 页面顶部（scrollY=0）时发送按钮位于 (795..823)，视口高 790，按钮不可见；需纵向滚动页面 ~33px 后可见。
- 视口 1280x800：同操作，发送按钮 (772..800) 可见可点，textarea 底部 7px（仅 padding）在折叠线下，不影响使用。
