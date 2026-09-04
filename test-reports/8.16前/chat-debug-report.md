# 前端「AI 学习问答」页面实测诊断报告

- 任务：实测前端 `/chat`（AI 学习问答）页面，定位用户无法使用该功能的原因
- 方式：只测试诊断，未修改任何代码
- 环境：Next.js dev `http://localhost:3000`（frontend-stack.json：Next.js 16 + App Router + Tailwind v4 + Zustand + TanStack Query）；后端 `http://127.0.0.1:8000`（v0.2.0，chat 接口已确认可用）
- 登录：admin / Admin@12345 → `POST http://127.0.0.1:8000/api/auth/login` 返回 `access_token`
- 注入方式：读 `edu-frontend/src/lib/auth-client.ts` 确认 localStorage key 为 `edu:auth:token` / `edu:auth:me` / `edu:auth:tenant`；注入后整页刷新触发 zustand `hydrate()`（ProtectedRoute 依赖 store 的 `ready && token`）
- 日期：2026-08-14

---

## 一、实测结论（发送后的具体表现）

| 验证项 | 结果 |
|--------|------|
| 输入「用一句话介绍你自己」+ **键盘 Enter 发送** | ✅ **成功**：用户消息入队 → `POST /api/chat/stream` → **200 OK** → assistant 气泡流式渲染（内容：「根据当前知识库，暂无匹配内容… 引用：未命中知识库」，含 1 条引用来源 37%） |
| 输入 + **鼠标点击发送按钮**（1280x800） | ✅ **成功**：请求 #36 `POST /api/chat/stream → 200 OK`，消息入队、回答渲染、输入框清空 |
| 鼠标点击发送按钮（850px 窄窗口） | ❌ **点击被第三方浮层拦截**（见根因 2） |
| console 报错 | ✅ 无（Errors 0 / Warnings 0，全会话） |
| 网络请求 | ✅ `POST http://127.0.0.1:8000/api/chat/stream` 两次均 **200**；`GET /api/chat/sessions`、`GET /api/chat/sessions/{sid}/history` 均 200 |
| 页面是否卡住/白屏 | ❌ 不卡、不白屏，流式渲染正常 |

**功能链路（后端 → 前端 → 渲染）本身完全正常**，用户「用不了」是 **UI 层问题**，见下方根因。

---

## 二、根因分析（按影响排序）

### 根因 1（最主要）：聊天页布局 bug —— 发送后输入框/发送按钮被顶出视口

- 页面外层容器使用 `min-h-screen`（`edu-frontend/src/app/(user)/chat/_components/ChatFullScreenClient.tsx` 第 303 行），而非固定视口高度（`h-screen`/`h-[100dvh]`）。
- `ChatPanel` 非浮动态为 `h-full`（`src/components/chat/ChatPanel.tsx` 第 211 行）、消息区 `min-h-0 flex-1 overflow-y-auto`——内部滚动**仅当容器高度被外部固定时才生效**；由于外层只保证最小高度，消息一多容器被内容自然撑高，内部滚动形同虚设。
- 实测（发送「用一句话介绍你自己」+ 后续两条消息后）：
  - 850x790 窗口：文档总高 **3701px**（视口 790），输入框需滚动 **2910px** 才可见；
  - 1280x800 窗口：文档总高 **3360px**，`main` 容器 3272px、面板 3271px（本应 ≈800px），输入框需滚动 **2560px**；
  - `main` 高度 = 文档流高度（2902/3272px），`overflow-y: hidden` 但容器自身已被撑高，消息区 `scrollH === clientH`（无内部滚动）。
- **用户视角**：打开页面时布局正常（消息少，面板 ≈ 视口高）；发送一条含引用卡片/MCP 工具输出的较长回复后，整个页面被撑高，**输入框与发送按钮滑出视口之外**，用户看不到输入框 → 无法继续提问 / 点击「没反应」→ 误以为功能坏了或页面卡住。

### 根因 2（窄窗口环境性）：第三方「腾讯兔小巢」浮层遮挡发送按钮

- 在 850px 宽窗口下，右下角 fixed 48x48 反馈浮层（`.tsqd-open-btn-container`，z-index 100000，位置 (774.7, 730)）与发送按钮 (778, 761.7, 28x28) **矩形重叠**（重叠区覆盖按钮上半部约 58%）。
- Playwright 鼠标点击发送按钮被拦截，报错原文：
  `<path ...> from <div dir="ltr" class="tsqd-parent-container">…</div> subtree intercepts pointer events`（重试至超时）。
- 1280x800 下浮层移至 (1204, 740)，与发送按钮 (835, 732) **不重叠**，鼠标点击正常。
- **来源判定**：前端源码零 tsqd 引用（grep 无结果）、network 无第三方 SDK 请求、`window.tsqd` 等全局变量不存在、DOM 中直接内联注入（class 前缀 `go24…`/`tsqd-…`）→ 判定为**测试浏览器环境注入**（Playwright/浏览器 profile 层面），非产品代码；真实用户浏览器一般不会出现。故列为环境性干扰，不作为产品缺陷根因。

### 非根因确认

- ❌ 后端接口问题：两次 stream 请求均 200，SSE 正常，回答渲染成功；
- ❌ 认证问题：token 注入 + hydrate 成功，受保护路由正常放行；
- ❌ console/JS 异常：0 报错；
- ❌ 流式渲染：assistant 气泡正常出现（含引用来源卡片）；
- ⚠️ 回答内容多为「知识库未命中/降级模式提示」（Milvus 跳过、Neo4j 未连接）——属后端业务/部署层面，非「功能不可用」原因。

---

## 三、关键证据

### 1. 网络请求状态（Playwright network capture）

```
31. [GET]  http://127.0.0.1:8000/api/chat/sessions                        => [200] OK
32. [GET]  http://127.0.0.1:8000/api/chat/sessions/s_8a7efb2de84e/history => [200] OK
33. [GET]  http://127.0.0.1:8000/api/chat/sessions/s_8a7efb2de84e/history => [200] OK
34. [POST] http://127.0.0.1:8000/api/chat/stream                          => [200] OK   ← 键盘 Enter 发送
35. [GET]  http://127.0.0.1:8000/api/chat/sessions                        => [200] OK
36. [POST] http://127.0.0.1:8000/api/chat/stream                          => [200] OK   ← 鼠标点击发送（1280 窗口）
37. [GET]  http://127.0.0.1:8000/api/chat/sessions                        => [200] OK
```

### 2. Console（全会话）

```
Errors: 0, Warnings: 0
```

### 3. 点击被拦截错误原文

```
TimeoutError: browserBackend.callTool: Timeout 5000ms exceeded.
  - <path clip-rule="evenodd" .../> from <div dir="ltr" class="tsqd-parent-container">…</div> subtree intercepts pointer events
  - <ellipse rx="266" cx="316.5" cy="715.5" .../> from <div dir="ltr" class="tsqd-parent-container">…</div> subtree intercepts pointer events
```

### 4. 布局测量（evaluate）

```
850x790:  docH=3701  scrollY(需滚动到输入区)=2911  tsqd(775,730,48x48) ∩ sendBtn(778,738,28x28) = overlap:true
1280x800: docH=3360  mainH=3272  panelH=3271  scrollY(需滚动到输入区)=2560  sendBtnInViewport=false(初始)
```

### 5. 请求链路代码佐证（只读源码，未修改）

- `edu-frontend/src/lib/api/chat.ts` L291 `chatStream()`：`fetch(`${API_BASE}/api/chat/stream`)`，body `{session_id, query, content, subject_code, level_code, stream}`；token 直接读 `localStorage["edu:auth:token"]`（L115 `readToken`）。
- `edu-frontend/src/lib/api-client.ts` L49-53：`API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000"` → 浏览器跨源直连后端，CORS 由后端放行（实测通过）。

---

## 四、截图（已存 `test-reports/screenshots/`）

| 文件 | 内容 |
|------|------|
| `test-reports/screenshots/chat-debug.png` | 850px 窄窗口，输入区可见 + 右下角兔小巢浮层与发送按钮重叠（点击被拦截现场） |
| `test-reports/screenshots/chat-debug-1280-input-area.png` | 1280x800 滚动到底部后的输入区（正常可用态，需滚动 2560px 才到达） |
| `test-reports/screenshots/chat-debug-1280-top-messages.png` | 1280x800 顶部消息区（用户消息 + assistant 回答 + 引用来源正常渲染） |

---

## 五、修复建议（供开发参考，本次未改动代码）

1. **主修（根因 1）**：将 `ChatFullScreenClient` 外层容器由 `min-h-screen` 改为固定视口高度（如 `h-screen` / `h-[100dvh]`），并确保 `main` 高度受约束（`flex-1` + `overflow-hidden` 已具备），使消息区内部滚动生效、输入框恒驻视口底部。
2. **次修（根因 2，若需防环境干扰）**：可对发送按钮/输入区提高 z-index 或为第三方浮层容器设置隔离；若 tsqd 仅在个别浏览器环境注入，产品侧可忽略，但建议在 UI 自动化/验收时留意该浮层对底部控件的遮挡。
3. 可选：发送后自动把输入区滚动进视口（`scrollIntoView`），缓解旧布局下「回复后找不到输入框」的体验。
