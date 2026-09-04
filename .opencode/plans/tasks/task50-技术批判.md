# task50 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task50 /chat AI 问答页（TraeWork，commit b8fe273 + 993f6cb）
> 结论：**⛔ 验收不通过（P1）**——缺「会话列表/切换窗口」UI（规范明确要求 + chat.ts 已封装接口但未使用）

---

## 实证结果

| 项 | 实测 |
|----|------|
| commit | ✅ `b8fe273` + `993f6cb`（P1 幽灵消息修复 + 字号 token 化）|
| 组件交付 | ✅ C22 ChatBubble + C23 MessageComposer + ChatCandyClient + chat.ts + useChatStream |
| tsc / eslint | ✅ 0 错误 |
| vitest | ✅ 全量 403（chat 专项 15 项）|
| **会话列表窗口** | ❌ **缺失**——ChatCandyClient 只有当前会话历史加载，**无会话列表/切换 UI** |
| SSE done 壳解析 | ✅ degraded_reason/retrieved_count/latency_ms 透出 |

## 批判 1（P1 阻塞）：缺少会话列表窗口（doc-frontend 规范明确要求）

**问题描述**：doc-frontend-design-spec.md 对 /chat 页的「历史消息」明确要求：
> **GET /api/chat/sessions 会话列表；GET /api/chat/sessions/{id}/history 取消息**

但 ChatCandyClient **未实现会话列表**（仅用 getChatHistory 加载当前/深链会话）。chat.ts 已封装 `listChatSessions`/`createChatSession`/`deleteChatSession`（源码确认），却**未使用** → 用户无法切换历史会话，只能看当前会话。

**证据来源**：
- ChatCandyClient 源码：list=0、sidebar=0、无会话列表渲染
- chat.ts 导出 7 函数含 listChatSessions（未消费）
- doc-frontend P2 规范（会话列表明确要求）

**与正确做法差距**：规范定义 + 接口已封装，但 UI 未做。用户无法在会话间切换（编辑/查看历史会话），是聊天页核心交互缺失。

**优化方案**（返工）：
- ChatCandyClient 增加会话列表窗口（糖果色侧栏）：
  - `listChatSessions()` 拉取会话列表 → 显示会话标题/时间，当前会话高亮
  - 点会话 → `getChatHistory(sessionId)` 加载 + 切换（已具备切换逻辑）
  - 「新建会话」按钮 → createChatSession
  - 删除会话 → deleteChatSession
  - 响应壳统一后正常解包（契约⑬）

**最小验证方法**：打开 /chat → 显示会话列表 → 点击不同会话切换 → 新建/删除会话；grep 确认消费 listChatSessions。

**预期收益与成本**：收益=聊天页核心交互完整；成本=1~2h（会话列表 UI + 状态联动）。

## 批判 2（P2）：chat.html 效果图缺会话列表（HTML 审核时未暴露）

**问题描述**：chat.html 效果图无会话列表窗口（"会话/历史"字样仅提及，无列表 UI），HTML 审核 APPROVED 时未发现——设计稿本身缺会话列表，导致 React 阶段也未做。

**证据来源**：chat.html grep：sidebar=0、会话列表未实现。

**优化方案**：返工时先补 chat.html 效果图会话列表 → 用户 APPROVED → React 实现；后续 chat 类页面 HTML 审核须含全部核心交互。

## 汇总

| GWT | 结果 |
|-----|------|
| ① fe-spec-writer 补规范 | ✅ 规范含会话列表 |
| ② 流式渲染 + done 壳 | ✅ 实现 |
| ③ 排队超时提示 | ✅ 降级 banner |
| ④ 历史会话加载 | ⚠️ 有当前/深链会话加载，**缺会话列表切换** |

**结论：task50 验收不通过（P1 会话列表缺失）**。返工：ChatCandyClient 加会话列表窗口（消费 listChatSessions/create/deleteChatSession）→ HTML 效果图补会话列表 → 用户 APPROVED → 复验。
