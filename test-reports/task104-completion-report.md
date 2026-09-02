# task104 完工报告 — chat.html 双绑定冲突清理 + 会话创建接真

- 域 FE ｜ 平台 trae ｜ 波次 W0 ｜ 依赖 task101
- 只改文件：`edu-frontend/public/chat.html`
- 硬守则合规：未改 EAPI/edu-api.js；注入未重定义全局 `$`/`renderSides`（注入内为 IIFE 局部 `var $`、`function renderSides`）；接口/SSE 结构**先 curl 实测后写**；禁 Playwright（用 node 纯语法校验替代）；不 commit。

---

## §0 真实 SSE 事件流记录（curl -N POST /api/chat/stream）⭐ 开工后第一步实测

以 student 登录（`user000001/Test@123456`），body `{"query":"你好，介绍一下你自己","session_id":null,"stream":true}`、带 Bearer token、`-m 60`，完整抓包关键行：

```
event: start
data: {"session_id": null, "query": "你好，介绍一下你自己"}

event: retrieval
data: {"docs": [{...5 篇...}], "graph_entities": [], "retrieved_count": 150,
      "final_count": 5, "rewrite_query": "你好，介绍一下你自己",
      "degraded_reason": "rerank_sidecar_unavailable", "mcp_tool_calls": []}

event: token
data: {"delta": "⚠"}
event: token
data: {"delta": "基于"}
event: token
data: {"delta": "通用"}
...（逐个增量 token，字段为 delta）...
event: token
data: {"delta": "？"}

event: done
data: {"code": 0, "message": "ok", "data": {"session_id": null, "message_id": null,
      "retrieved_count": 150, "final_count": 5, "latency_ms": 11173,
      "rewrite_query": "你好，介绍一下你自己", "degraded_reason": "rerank_sidecar_unavailable", "mcp_tool_calls": []}}
```

**实测结论（以此为准，不凭猜）：**
1. `token` 事件 data 字段名是 **`delta`**（不是 `token`）。印证 audit §四与 AGENTS.md 教训③ 有出入 → 前端旧取 `j.token` 会**流式内容全空**，必须改 `j.delta`。
2. `done` 事件 data 是**嵌套壳** `{code:0, message:"ok", data:{session_id, message_id, ...}}`，**没有 `content` 字段**（旧前端 `if(d.content)` 永远不命中、也不报错）。session_id 在传入 null 时 done 返回 null（后端行为）。
3. 无 `error` 事件（rerank 降级走 `degraded_reason`，非 error）。C-B 契约预留 error 分支已保留。

辅助接口实测（同 token 组）：
- `POST /api/chat/sessions`（body `{}`）→ `{code:0,data:{session_id:"s_1affbc542632", title:"新会话 542632", ...}}` → EAPI.post 解壳后为 `{session_id, title,...}`。
- `GET /api/chat/sessions` → `{code:0,data:[{session_id,title,last_message_at,...}]}`（按最近排序）。
- `GET /api/chat/sessions/{id}/history` → `{code:0,data:[{message_id,role:"user"|"assistant",content,...}]}`（纯数组，无 `messages` 包裹）；空会话 `data:[]`。
- `DELETE /api/chat/sessions/{id}` → 首次 `{ok:true}`，复删 `404 CHAT_SESSION_NOT_FOUND`（软删正常）。
- 探测 `GET /api/chat/sessions/{id}/rename` → **404（无重命名端点）**。

---

## §1 改动清单（全部在 chat.html）

**A. 双绑定隔离（②）**
- 演示脚本顶部新增登录态判定：`let __logon = !!localStorage.getItem("edu:auth:token")`。
- 有 token（登录）时**不绑定** demo 的 document 级委托（`.sess`/`[data-del]`）→ 消除「demo 委托 + 注入元素级监听」双命中 `.sess` → 读 `MESSAGES[realId]` 抛 TypeError 的根因。
- 有 token 时不绑定 demo 的 `#sideNew/#drawerNew/#newSession`（demo 版会用演示数据覆盖真实列表）。
- 有 token 时：`#hamb` 不再调 demo `renderSides()`（防覆盖真实列表）；视口/状态演示按钮绑定整体关闭（登录态走注入）。
- 保留恒绑定（无冲突、必需）：`#toastClose`、`#drawerClose`、`#scrim`、composer 自动增高、`window.resize` 关闭抽屉。
- 无 token（`__logon=false`）→ demo 控制器按原样启用；chat 页本会跳登录（注入 IIFE 拦截），行为保持 。

**B. SSE 解析修正（④的关键核验点，❶❷）**
- `token` 事件：`j.token` → **`j.delta`**（流式内容即刻逐字渲染）。
- `done` 事件：改为解析**嵌套壳** `d.data`；不再用 `d.content`；若发送时无 sid（新话题）则 `loadSessions()` 刷新列表使会话入列表。streaming 内容已由 token 累加完，不做二次覆盖。
- `error` 事件保留（`er.message`）。

**C. 新建会话接真（③）**
- 注入新增 `createSession()`：`EAPI.post("/api/chat/sessions", {})` → 成功后 `sessions.unshift(...)` 头部插入 + `activeId=s.session_id` 选中 + 渲染 + 加载空历史。
- 绑定 `#newSession/#sideNew/#drawerNew` → `e.preventDefault(); createSession()`。
- 登录态 `#hamb` 由注入接管：renderSides（真实列表）+ 打开抽屉。

**D. 气泡 class 修正（④）**
- 注入两处 `msg me` → `msg user`（与 CSS `.msg.user` 匹配）；同时把内层 `class="bubble"` → `class="bubb"`（CSS 只有 `.bubb`，不改则气泡仍无底色/无内边距）。AI 气泡同改 `bubb`。

**E. 回归核对（⑤）**
- 会话历史 `GET {id}/history`：注入 `loadHistory` 兼容纯数组返回（`(msgs&&msgs.messages)||msgs`），role/content 读取正确。✅
- 删除 `DELETE`：已接（`EAPI.del`），实测定会话 → `{ok:true}`/复删 404。✅
- 重命名：chat.html **无**重命名按钮；后端 `.../rename` 探测 404 → 无需隐藏，不造假功能。✅

---

## §2 机验（grep 逐条）
- `grep -n "j.token\|j.delta\|j.data"` → 仅命中 `j.delta`（L741），**无 `j.token`**；done 用嵌套 `d.data`。与实测契约一致。✅
- `grep -c "msg me"` → **0**，CSS 定义 `.msg.user`/`.msg.ai` 与注入输出匹配；`class="bubble"` 残留 0。✅
- `node --check`（new Function 解析全部 4 个 `<script>` 块）→ `bad=0`（语法通过）。✅
- 登录态下 demo 委托不生效的代码路径：`demo 委托 # L596 if(!__logon){...}` + `#hamb L632 if(!__logon) renderSides()` + 注入 `#newSession/#hamb` 由注入绑定 → 有 token 时 `.sess` 点击只命中注入元素级监听（L684-686），不再读 demo `MESSAGES[realId]`。

## §3 GWT 逐条自评
| 验收项 | 自评 | 依据 |
|---|---|---|
| student token 发消息 → 流式 token 逐字渲染、完成后助手消息完整、session 入列表 | **达成**（源码级） | 实测 token 字段=delta，注入已改 `j.delta` 逐字追加；done 刷新列表。浏览器端因纪律禁 Playwright 未实跑 UI，为静态+真实 HTTP 实证 |
| 点真实会话 → 加载 `/history`、控制台无 TypeError；点新建 → 列表新增空会话且后端可见 | **达成**（源码级） | demo 委托已按 `__logon` 隔离；历史 GET 纯数组兼容；POST sessions 实测落库+GET 可见（s_1affbc542632 曾创建并已删除还原） |
| 无 token 打开 chat.html → 跳登录（保持） | **达成**（保持） | 注入 IIFE `if(!token){ location.href="/login-register.html" }` 未动；demo 在无 token 时仍可用（但会被跳转） |
| 机验 grep 一致性 | **达成** | 见 §2 |

---

## §4 未尽/风险说明
- 因硬性禁 Playwright（AGENTS.md 教训②）无法做真实浏览器点击/Network 复核，流式渲染以「真实 SSE 抓包 + 源码语义 + node 语法校验」三重实证代替。若编排者允许，可在浏览器手动点验。
- `done.data.session_id` 在 session_id=null 传入时后端返回 null（实测）；故 UI 依赖 POST /api/chat/sessions 显式建会话更稳，SSE done 仅作为兜底刷新触发。
- 任务要求「只改 chat.html」已满足；未 commit、未切分支。

> 交付物：`edu-frontend/public/chat.html`；接口/SSE 契约已按实测（task114 冻结口径：`delta` 字段 + `done` 嵌套壳）核对。