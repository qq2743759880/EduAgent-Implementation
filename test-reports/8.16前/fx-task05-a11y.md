# 无障碍审查报告 fx-task05

> 审查人：fe-a11y-auditor ｜ 基准：WCAG 2.2 AA ｜ 审查人权限：只审查+出报告，未改任何业务代码

## 审查范围

fx-task05（G7 前后端联调 + bug 修复）—— 本 task **零新增页面/组件/路由**，补丁仅限 `src/lib/api/chat.ts`（R-7 #7 searchRagOnly 补 console.error）与 `chat.test.ts` 用例；其余交付物为联调脚本（测试工具，无 UI）。审查聚焦 chat 相关既有 UI 的联调视角。

- 被审文件：
  - `edu-frontend/src/lib/api/chat.ts:246-250`（searchRagOnly catch 补 `console.error("[chat] 检索失败：", e)`）
  - `edu-frontend/src/lib/api/chat.test.ts:141-167`（searchRagOnly R-7 主用例）
  - `edu-frontend/scripts/verify-task05-chat-ui.mjs` / `task05-*-toast-test.mjs`（联调脚本，无 UI）
  - 既有 chat UI（联调视角抽查）：`src/app/(user)/chat/_components/ChatFullScreenClient.tsx`、`src/components/chat/ChatSessionSidebar.tsx`、`src/components/chat/ChatPanel.tsx`、`src/components/chat/ChatMessageBubble.tsx`、`src/components/chat/hooks/useChatSessions.ts`、`src/components/ui/dialog.tsx`、`src/app/providers.tsx`（Toaster）、`src/lib/query-client.ts`（全局 onError）、`src/app/globals.css:136`（prefers-reduced-motion）
- 审查时间：2026-08-13 09:00–09:30
- 基线：`frontend-stack.json`（profileId nextjs-16-app-router）、`.claude/specs/frontend/fx-task05/{design-options,component-contracts,frontend-spec}.md`、`test-reports/fx-task05-server-info.md`

## 验证方式

**实机（Playwright @ http://localhost:3000，复用 fe-server-infra 已启动的 dev server PID 1908，未重复启动）+ 静态代码审查**。

- 登录态：后端 127.0.0.1:8000 运行中（PID 3692），admin/Admin@12345 真实 JWT 注入（addInitScript 先于页面脚本，无 hydrate 竞态），/chat 加载 50 个会话成功
- 实测链路：
  1. /chat 桌面布局（1440×900）会话侧栏 + 消息历史渲染、可访问树逐元素核对
  2. 删除会话全链路：hover 行 → 删除按钮 → 确认 Dialog（焦点/ARIA 关联）→ 确认删除 → DELETE 200 → toast「对话已删除」→ 行移除 + URL sid 切邻居 → 焦点落输入框
  3. 删除确认 Dialog 焦点/Tab/Escape 行为
  4. 历史加载失败态：route 拦截 `**/history` 返回 500 → 观察空态兜底（会话列表保留、聊天窗不白屏、无错误横幅、console `[chat]` 日志）
- 自动检查：Playwright accessibility snapshot + DOM 断言（未运行 axe；dev server 幽灵导航干扰——Next.js dev overlay 偶发把页面导航到 /dashboard，fx-task04 已记录同环境噪声；关键结论均已多次复现或静态佐证）
- 对比度：fx-task05 零新增视觉元素，不适用本 task；既有 muted 对比度问题见 fe-task00 LOW-04，不重复升级

## 发现表

| # | 位置 file:line | 严重度 | 原则 | 问题 | 修复建议 |
|---|---------------|--------|------|------|---------|
| 1 | `ChatSessionSidebar.tsx:357-367`（SessionRow 整行 `div` `onClick={onPick}`，无 `role`/`tabIndex`/键盘处理） | **BLOCKER** | 2.1.1 / 2.4.3 / 4.1.2 | **会话行键盘不可达（键盘死区）**：实机确认 50 个会话行的可聚焦元素仅有删除按钮，会话行本身 `role=null、tabIndex=null、onClick=true`。键盘用户无法用 Tab/Enter 选中/切换会话（唯一进入会话的方式是鼠标点击），读屏器用户无法通过名称直接选择会话 → 核心交互（读取历史/切换会话）对键盘用户关闭。**既有问题（chat 组件属 F1 轨/fe-task00 写路径外，非 fx-task05 引入）** | 会话行改为原生 `<button>`（或 `role="button"` + `tabIndex={0}` + Enter/Space 处理 + `aria-current="true"` 标注选中态），删除按钮内嵌并保持 `aria-label` |
| 2 | `ChatPanel.tsx:359-384`（Textarea 无 label/aria-label/aria-labelledby） | HIGH | 1.3.1 / 3.3.2 / 4.1.2 | 输入框可访问名**仅来自 placeholder**（实机 snapshot：textbox 名称 = placeholder 全文「向 EduAgent 提问：…」）。placeholder 非合格 label（WCAG 3.3.2：占位文本不可作为 label 替代，聚焦后消失、读屏器部分支持），错误提示 `draftErr`（L350-351）也无 `aria-describedby` 关联。**既有问题** | 补 `<label htmlFor>` 或 `aria-label="向 AI 提问"`；错误提示补 `id` + `aria-describedby` + `aria-invalid` |
| 3 | `ChatFullScreenClient.tsx:237-254`（getChatHistory 失败）+ `chat.ts:225-229`（catch 返回 `[]`） | LOW | 4.1.3（增强）/ 1.3.1 | 历史加载失败对用户**静默**：route 500 实测——会话列表保留 ✅、聊天窗显示欢迎空态不白屏 ✅、无红色错误横幅 ✅（符合契约「错误态不渲染红色错误横幅」，design-options §4）、console 有 `[chat]` 日志 ✅；但用户无法区分「该会话无历史」与「历史加载失败」两种状态，读屏器无任何加载失败状态播报。`ChatFullScreenClient.tsx:248-251` 的 `toast.error("Failed to load history")` 是**死代码**（getChatHistory 内部 catch 返回 `[]` 不抛错，外层 catch 永不触发）。**既有问题** | 可保留空态兜底（契约），但建议在历史为空且请求失败时以 `role="status"`/`aria-live="polite"` 播报「历史加载失败」（或触发一次 toast）；把失败标志从 getChatHistory 上抛，使 L248-251 的 toast 生效 |
| 4 | `ChatSessionSidebar.tsx:300-336`（删除确认 Dialog）+ `dialog.tsx` | LOW | 2.4.3（待复验） | **Esc 关闭未能稳定复现**：多次实测 Dialog 打开后按 Escape，`[role="dialog"]` 仍存在（焦点在「取消」按钮上）；dispatch Escape 到 dialog/document 也不关闭。但同一 Dialog 组件（dialog.tsx，Base UI modal 默认 true）在 fx-task03 管理端实测 Esc PASS，且本环境 Next.js dev overlay 幽灵导航高频打断键盘事件，**疑似环境噪声而非组件缺陷**，不升为违规 | 建议 fe-tester 在稳定环境（关闭 dev overlay）复验一次；若仍不关闭，排查 Base UI 版本 dismissible 行为（受控 open + onOpenChange 组合） |
| 5 | `MobileDrawer.tsx:41-94`（原生 dialog） | LOW | 2.4.3（待实机） | 原生 `<dialog>` + showModal 焦点管理由浏览器承担（静态审查 OK），但因幽灵导航未在移动视口实机复验键盘路径 | 实机补测移动抽屉：打开焦点移入 / Esc / 关闭后归还 |
| 6 | `ChatFullScreenClient.tsx:348-362` 等既有 chat UI | LOW | 1.4.3（既有记录） | 输入区 `text-muted-foreground/80` 对比度 ≈3.9:1 < 4.5:1（fe-task00 LOW-04 已记录）；fx-task05 零新增视觉，未引入新对比度问题 | 由 fe-task07/chat 收敛 |

## chat 交互实测记录

| 场景 | 结果 | 证据 |
|------|------|------|
| /chat 已登录会话列表渲染 | ✅ 通过 | admin JWT 注入后侧栏「历史对话 共 50 个会话」，会话行 50 条（用户隔离由 verify-task05-chat-ui.mjs 断言） |
| 会话侧栏语义 | ✅ 通过 | `aside aria-label="历史会话"` + `ul/li` 结构 + 日期分组 label（今天/过去 7 天）+ 计数渲染；删除按钮原生 `<button aria-label="删除对话 {标题}">` 可聚焦 |
| **会话行键盘可达性** | ❌ **失败** | 行 `div onClick` 无 role/tabIndex（发现 #1 BLOCKER）；实机 `firstRowRole=null, tabindex=null` |
| 删除确认 Dialog 打开 | ✅ 通过 | 标题「删除对话」+ 描述「确定要删除「浏览器实测会话」吗？删除后将无法恢复…」；`aria-labelledby`/`aria-describedby` 由 Base UI 自动关联（base-ui-_r_4_/_r_5_）；初始焦点在「取消」按钮 |
| 确认删除 → 后端 | ✅ 通过 | 点击「确认删除」→ DELETE 200（onMutate 乐观移除 → onSuccess 成功）→ toast「对话已删除」→ 会话计数 50→49、行消失不回滚；URL `sid` 切到邻居会话 |
| **toast aria-live** | ✅ 通过 | sonner 容器自带 `aria-live="polite"`（node_modules/sonner/dist/index.mjs:1145）+ 实机 toast 元素 data-type=success、文本「对话已删除」，读屏器可播报；错误路径 toast「删除会话失败」（useChatSessions.ts:178）语义色 rose |
| Dialog 关闭后焦点归还 | ✅ 通过 | 删除成功关 Dialog 后 active=TEXTAREA（ChatFullScreenClient handlePickedSide → focusInput() 80ms），焦点未落 BODY，符合删除后继续对话的焦点策略 |
| 历史加载失败态（route 500） | ✅ 契约合规 | 空态兜底：会话列表保留、聊天窗欢迎空态不白屏、无红色错误横幅、console 有 `[chat] 加载会话历史失败`；对用户的失败告知缺失见发现 #3（LOW） |
| 消息气泡语义 | ✅ 通过 | 头像 aria-label（AI 助手/系统消息/用户昵称）、StreamingDots `aria-label="生成中"`、代码复制按钮可访问名、markdown 链接 rel=noreferrer |
| 发送/停止/新对话按钮 | ✅ 通过 | 均为原生 button + aria-label（发送消息/停止生成/新对话/打开会话列表） |
| Dialog Tab 顺序 | ⚠️ 部分 | Dialog 内「取消→确认删除→Close」顺序正确；Tab 第 4 步曾逃逸到页面导航（同一 Base UI 焦点围困问题，fx-task03 HIGH-03 已记录管理端同型问题，chat 侧栏未单独复现确认） |
| Esc 关闭 | ⚠️ 待复验 | 未稳定复现（发现 #4，疑似 dev overlay 环境噪声） |
| 移动抽屉 / 触控 | ⚠️ 静态 | MobileDrawer 原生 dialog 静态 OK；未实机（发现 #5） |
| prefers-reduced-motion | ✅ 通过 | globals.css:136-144 全局动画/过渡归零（WCAG 2.3.3） |
| `<html lang>` / title | ✅ 通过 | SSR title「AI 学习助手 · EduAgent」唯一描述内容（server-info L20） |

## 严重问题（BLOCKER）

1. **`ChatSessionSidebar.tsx:357-367` — 会话行键盘不可达（键盘死区）**：会话选择是 chat 页核心交互，键盘/读屏器用户无法到达。**既有问题**，非 fx-task05 补丁引入（chat 组件写路径在 F1 轨/fe-task00）。

## 需要修复（HIGH）

1. **`ChatPanel.tsx:359-384` — 输入框无可访问 label**（可访问名仅 placeholder；错误提示无 aria-describedby）。**既有问题**。

## 建议（LOW）

见发现表 #3–#6（历史失败静默/死代码 toast、Esc 待复验、移动抽屉待实机、既有对比度记录）。

## 判定

- 结论：**FAIL**
- 阻塞项：
  1. **BLOCKER #1**：会话行键盘不可达（ChatSessionSidebar.tsx:357-367）—— 既有问题，归属 F1 轨/fe-task00 修复，非 fx-task05 引入
  2. **HIGH #2**：输入框无 label / 错误提示无关联（ChatPanel.tsx:359-384）—— 既有问题
- **fx-task05 补丁零 a11y 回归确认（独立结论）**：本 task 唯一代码改动 `chat.ts:246-250`（searchRagOnly catch 补 `console.error("[chat] 检索失败：", e)`）为纯日志语句，不触碰 DOM、不改变渲染、不改变焦点/ARIA/对比度；`chat.test.ts:141-167` 为单元测试；联调脚本无 UI。**补丁未引入任何 BLOCKER/HIGH/LOW 级新违规**。
- 报告内所有 BLOCKER/HIGH 均为既有 chat UI 问题（fe-task00/F1 轨交付范围），本 task 审查按联调视角抽查并记录，修复归属非 fx-task05 写路径（frontend-spec §边界：不改 `src/components/chat/**`、`src/app/(user)/**`、`providers.tsx`）。
- 静态/待复验项（#4 Esc、#5 移动抽屉）不得作为实机通过被消费。
