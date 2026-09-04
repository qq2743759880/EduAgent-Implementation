# task50: /chat AI 问答页（SSE 流式，多 agent 接口对齐）

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：M
> **前置**：task41, task15 ｜**后置（联调节点）**：消费契约⑬（task15 SSE 壳）；不依赖 AI 新契约（task24~29 与前端互不阻塞）
> **规范状态**：⚠️ doc-frontend-design-spec.md 未覆盖本页 → fe-spec-writer 先行补充该页规范再出 HTML

## 1. 选型依据
- tech-source-audit.md §五（Next.js SSE 消费）；§一（SSE done/error 事件内嵌壳）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | **先行补充本页规范**（流式渲染/历史消息/输入区） |
| 原型 | fe-implementer | chat.html（流式态/历史态/错误态） |
| 审核 | 【用户 gate】 | 循环至 APPROVED |
| 实现 | fe-implementer + fe-styler | React（SSE EventSource/fetch stream） |
| 审查 | fe-server-infra → fe-perf/fe-a11y-auditor/fe-visual-auditor | ≤3 轮 |
| 测试 | fe-tester | Vitest + Playwright |
| 工具 | playwright MCP + context7 MCP | — |
| 提交 | commit skill | — |

## 3. 执行方式（Trae 手动调度，无 Workflow API）

Trae Code 无 opencode 专属的 `Workflow()` API，按 `D:\.ai-hub\workflows\dev-standard.mjs` 的 8 阶段**手动调度**（效果等价）：
```
1. 开发阶段   -> 调 sd-dev + be-architect + be-validator（读任务文档 + tech-source-audit）
2. 测试阶段   -> 调 sd-tester（+ sd-challenger 对抗）；数据库校验用 RunCommand 跑 mysql CLI / Python 脚本（无 mysql MCP）
3. 修正阶段   -> 据测试报告回 sd-dev 修复
4. 审查阶段   -> 调 review-screener-1/2/3 -> review-moderator -> review-judge（SARIF）
5. 提交阶段   -> git commit（message 含 task 编号）
```

mysql MCP 未在 Trae 环境注册（当前 MCP 仅 integrated_code_mode / integrated_goal）：
- 数据库校验改用 **RunCommand + mysql CLI / Python 脚本**（先例：scripts/verify_schema.py、scripts/verify_task07_counts.py）
- 或手动在 设置->MCP 按 `D:\.ai-hub\mcp\index.json` 模板添加 mysql


## 4. 实现规划要点
- SSE 流式渲染（POST /api/chat/stream）：消息增量追加、done 事件解析 `{code,message,data}` 内嵌壳、error 事件 toast
- 历史消息加载（chat_message）；「AI 提问」入口 ?context=session:{id} 上下文携带
- 多 agent 改造后接口对齐：流格式不变，首包分级提示（10s 排队提示/60s 降级答案文案）

## 5. 验收标准（Given/When/Then 全文）
- Given fe-spec-writer 补充本页规范，When 产出 HTML，Then 规范含流式渲染态/历史消息/错误态设计
- Given HTML APPROVED，When 提问，Then 流式逐字渲染；done 事件解析内嵌壳数据；error 事件展示 message
- Given 后端排队超时（task26），When 返回"当前咨询人数较多"，Then 页面展示该提示而非报错
- Given 历史会话，When 打开，Then 从 chat_message 加载（响应壳统一后正常解包）

## 6. 交接与记忆
- 完成 → 看板 task50=DONE → sync.ps1
- 交付物：补写规范 + chat.html + React + 测试

## 7. 实现记录（React 版完成 · commit b8fe273）
- **规范**：doc-frontend-design-spec.md 新增 P20 `/chat`（布局/组件/交互/状态机，章节 7新+13重构=20），登记 C22 ChatBubble、C23 MessageComposer
- **HTML 审核**：test-reports/fe-html/chat.html 五态效果图，用户签收 APPROVED
- **chat.ts**：SSE 支持；done 事件解析契约⑬ 内嵌壳，透出 `degraded_reason / retrieved_count / latency_ms`
- **useChatStream**：新增 `onFinalMessage` 回调（降级提示透出点）
- **C22 ChatBubble**：三角色气泡（user 糖果紫右 / ai 卡片左 / system 居中条）+ Markdown 安全渲染 + 流式闪烁光标 + 引用计数 + 时间戳
- **C23 MessageComposer**：Textarea 自动增高 + 发送/停止切换 + Enter 发送/Shift+Enter 换行 + context 徽标 + 排队 pill + degraded banner + 错误态锁定
- **ChatCandyClient**：糖果单栏状态机（空态/历史加载/流式/降级/错误态）；`?context=session:{id}` 深链上下文携带；历史加载 + 会话切换
- **验证**：tsc 0 / eslint 0 / vitest 403 全绿（chat 专项 25 项）/ next build 成功
- **遗留**：多 agent（task92/93）排队分级计时器——后端首包延迟与降级语义对齐后按需做 10s/60s 前端计时分级（当前以「流中首包无 token」近似排队提示）
