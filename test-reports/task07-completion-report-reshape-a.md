# task07 完成报告 —— chat.html 智能问答补全（reshape-a）

- 执行 agent：fe-html 接线工程师（独立开发）
- 日期：2026-09-06
- 改动文件：`edu-frontend/public/chat.html`（仅此一个；后端/contracts/edu-api.js 零改动）
- GWT 来源：`.ai-hub/plans/dev-plan-reshape-a.md` task07「When POST /api/chat/stream `{query,session_id,stream:true}`；Then j.delta 流式渲染/retrieval 引用/历史分页/error 诚实」；契约权威 `contracts/reshape-a.json`（hash 30aeddbe）

---

## 1. curl 实测证据（2026-09-06，学生 user000001 真实 token）

### 1.1 会话列表 GET /api/chat/sessions?limit=5
```
code:0  data type: list len:5
first item keys: [created_at,last_message_at,message_count,session_id,title,updated_at,user_id,visibility,yn]
{"session_id":"s_277ef21c6990","title":"你是谁","message_count":4,"last_message_at":"2026-09-06T17:13:21.193000",...}
```
→ 扁平数组（非分页壳）；字段 session_id/title/message_count/last_message_at。

### 1.2 新建 POST /api/chat/sessions（body {}）
```
code:0  data:{"session_id":"s_86c88d25b60a","title":"新会话 25b60a","message_count":0,"last_message_at":null,...}
```
→ title 后端默认生成「新会话 xxxxxx」。

### 1.3 历史 GET /api/chat/sessions/{sid}/history?limit=2
```
code:0  type:list len:2
msg keys: [content,created_at,latency_ms,mcp_called_count,mcp_tool_calls_json,message_id,rag_docs_json,
           rag_error,rag_final_count,rag_query_rewrite,rag_retrieved_count,rag_retrieved_count,role,session_id,user_id]
role=user content='你是谁' created_at=2026-06T17:12:37 (ASC 正序)
```

### 1.4 分页参数实测（漂移①②依据）
| 探测 | 结果 |
|---|---|
| `GET /api/chat/sessions/{sid}`（会话详情端点） | **405**（端点不存在） |
| `history?limit=501` | **422**（limit 上限 500） |
| `history?limit=2` | 返回最早 2 条（ASC + LIMIT，**无 page/offset**） |
| `DELETE /{sid}` | `{"code":0,"data":{"ok":true}}`（软删） |
| `history`（不存在会话） | 404 `{"code":"CHAT_SESSION_NOT_FOUND","message":"会话不存在：s_nonexist"}`（**code 为字符串**） |

### 1.5 SSE 事件形状（承接 task104 实证 `_task104_sse_capture.txt`，未重跑不改主链路）
```
event: start|retrieval|token(×201)|done
done data: {"code":0,"data":{"session_id":null,"retrieved_count":150,"final_count":5,"latency_ms":18121,"degraded_reason":"rerank_sidecar_unavailable",...}}
```
→ token 字段=`delta`（教训 3）、done 嵌套壳无 content —— 与页面现有解析一致，**未发现真 bug，主解析逻辑零改动**（守则⑤）。

## 2. 漂移登记（实测 vs contracts/reshape-a.json / 页面注释）

| # | 漂移 | 实测证据 | 前端处置 |
|---|---|---|---|
| D1 | **契约 `GET /api/chat/sessions/` 被理解为"会话详情端点"，实际不存在（405）**；历史"分页"仅 `limit`（1..500，超限 422），无 page/page_size/offset | §1.4 | 历史 `?limit=500` + 按 `message_count` 渲染诚实截断横幅（"已加载最早 N 条 / 共 M 条"） |
| D2 | 错误码 `code` 为字符串（`"CHAT_SESSION_NOT_FOUND"`），非数字壳 | §1.4 | 展示 `message` 原文，不解析 code 类型 |
| D3 | 契约未列 `limit` 参数（sessions list / history 均有，ge=1 le=200/500） | §1.1/§1.4 | 按实测传 `?limit=50` / `?limit=500` |
| D4 | done.data.degraded_reason 存在（rerank_sidecar_unavailable），页面降级 banner 逻辑依赖 done.data 但契约未标注该字段 | task104 capture | 保留现状（SSE 主链路未动，降级 banner 属后端字段待变更单） |

## 3. 补全内容（对照派单 5 项）

1. **会话管理真实化**：新建（POST，按钮防重复创建 disabled）、切换（点选→loadHistory，含快速切换竞态防护 `activeId!==sid` 丢弃过期渲染）、删除（DELETE 软删→本地过滤，active 会话被删自动落到列表首个）。
2. **历史消息分页（实测口径）**：`GET /history?limit=500`；`message_count > 返回条数` 时渲染截断横幅（漂移 D1 的诚实降级）；历史渲染补 meta 时间 + `rag_final_count` 引用数（🔎 N 篇引用）。
3. **error 事件诚实展示**：沿用 failStream（保留已生成内容 + 行内 `.md-err` 中断提示 + toast），**不打断已有渲染**；已由 CDP 实证。
4. **网络断开/SSE 中断降级**：①发送前 `navigator.onLine===false` → toast「当前设备已断网」且不清输入；②流式中 `window offline` 事件 → failStream「网络连接已断开（offline）」，保留部分渲染（CDP 实证 toast 文案与 partial 保留）。
5. **SSE 主解析逻辑未动**：token.delta 累加 / start-retrieval 思考动效 / done 嵌套壳 / error 分支全部保持 task104 原状。

### 附带修复（会话管理范围内发现的真实缺陷，均在非 SSE 解析区）
| 缺陷 | 修复 |
|---|---|
| done→`loadSessions()` 整页刷新：会把 activeId 弹回列表头部并重载历史，流式完成的视图被弹走；且 done 与刷新间再次发送会因 activeId 仍为 null 再开新会话 | done 立即收编 `activeId=d.data.session_id` + `loadSessions({keepView:true})` 只刷侧栏 |
| 流式中可再次发送：并发流双写 `#aiResp`（同 id 元素互踩） | `setStreaming(true)`：禁用发送 + 队列动效 + stop 态；完成/失败复位 |
| 会话列表加载失败 `.catch` 静默吞 → 登录态残留静态 demo 假数据（假会话/假消息） | errState 诚实错误态 + 重试按钮（CDP 实证渲染 "Failed to fetch" 且重试恢复） |
| 会话标题 `s.title` 直接 innerHTML 注入（存储型 XSS 面） | `esc()` 转义 |
| 静态假上下文徽标「📎 来自·通用编程入门班 第3讲」登录态仍显示（假数据） | 隐藏（chat 契约无上下文字段） |
| 流式中可删除/切换当前会话 → 渲染目标 `#aiResp` 丢失 | streaming 时禁删当前会话/禁切换 |

## 4. 独立实证（CDP，非 Playwright；脚本 `test-reports/_task07_cdp_verify.mjs`，结果 `task07-cdp-result.json`）

headless Chrome（CDP 9228）+ 学生 token 真实加载 `:3000/chat.html`，**13/13 全绿（ALL PASS）**：

| 检查 | 证据 |
|---|---|
| real-sessions-rendered | count=15，id 形如 `s_*`（真实库数据） |
| demo-data-replaced / fake-ctx-hidden | stage 无演示假消息；假上下文徽标 display:none |
| session-switch-history | 点选切会话，active 高亮 + 历史渲染 msgs=2 |
| create-session | UI 点击 → POST 真实创建 `s_1527019598a6`，列表 15→16，空态诚实 |
| streaming-state-honest | 发送后 queueHint 可见 + sendBtn disabled=true |
| sse-stream-completed | 真实 LLM 流式完成，回答 "二"（1+1 等于几） |
| done-keepview | done 后列表数不变、active 保持、`#aiResp` 内容保留（无弹跳） |
| delete-session | UI 点 .del → DELETE 真实删除，列表 16→15 |
| offline-degrade | 流式中派发 offline → toast「AI 响应中断：网络连接已断开（offline）」+ 发送复位 + partialKept=23（已生成内容保留） |
| history-error-state | EAPI.BASE 指不可达端口 → 切会话 → `.error-st` 渲染 "Failed to fetch"（Chrome refused 重试退避，轮询捕获） |
| error-retry-recovers | 恢复 BASE 后点重试 → 错误态消除 |
| console-no-js-errors | 全程无真实 JS 异常（唯一 error 为预期的 EAPI 网络失败日志） |

语法门：5 个内联 script 全过 `node --check`。测试残留清理：验证用会话已 DELETE（404=已删确认），仅存真实库会话。

## 5. 资产消费证据

- `edu-api.js`（禁改未改）：EAPI.get/post/del、EAPI.store.getToken、EAPI.BASE、EAPI.buildLoginUrl 级 401 跳转、全局错误 toast 钩子（会话/历史失败提示零自绘）。
- `EduMD.toHtml`：历史 AI 消息 Markdown 渲染 + 未加载时 esc 降级（既有资产复用）。
- 糖果 tokens/CSS：`.error-st/.think/.degrade/.meta .refs` 全部复用页面既有样式，零新增 CSS 块（只修不增）。

## 6. 批判承接核对（dev-plan §批判承接核对表）

- C15/C16/C17/C18 均落点 B 批次任务，本任务不涉及生产代码改动——核对无遗漏。
- 本任务承接 P2「纯接线页 HTML gate 降级为增量 diff 审查」：改动全部位于真实 IIFE 块，demo 块（未登录态）与 CSS 零改动。
- 教训 3（SSE 契约）/教训 8（实测优先）/教训 9（禁 match——本页取参仅 post/路由 id 场景，未新增 match）/教训 10（守卫）逐条核对遵守。

## 7. 三视角自检

- **Eng**：改动收敛在单一 IIFE；异步竞态三处防护（切换 `activeId!==sid`、流式禁发/禁切/禁删、按钮 finally 复位）；无新增全局污染（未重定义 `$`/renderSides——教训 4）；`node --check` 5/5。
- **Data/契约**：只消费实测字段（session_id/title/message_count/last_message_at/message_id/role/content/created_at/rag_final_count）；不写任何 MOCK；分页按实测 limit 口径并登记漂移 D1-D4。
- **UX/演示**：三态齐（历史 loading 思考 pill / 失败 error-st+重试 / 空 emptyHtml）；断网与流中断均"诚实文案+保留内容"；演示故事线（学生提问→流式回答→切会话→删会话）CDP 全链实证可跑。

## 8. 遗留与建议

- D1 建议 B 批次变更单：`/history` 增加 page/offset 或改 DESC+before 游标，否则 >500 消息会话只能看到最早 500 条（当前前端已诚实标注）。
- `degraded_reason` 降级 banner（页面 CSS 已备）依赖 done.data 字段，实测确有该字段但本次流未触发降级路径展示，留待 R1-③ 同类真实窗口验证。
