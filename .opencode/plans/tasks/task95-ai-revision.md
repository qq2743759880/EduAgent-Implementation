# task95 — AI 8 项修订任务（self-critique 落地）

> 执行工具：**Trae** ｜ 依赖：— ｜ 状态：TODO
> 修订来源：`.opencode/plans/self-critique-ai-agent-vs-competitors.md` + `ai-agent-revision-plan.md`
> 核心定位：R3 MCP 工具延迟加载/认证/重连——修复缓存失效根因

## 1. 验收标准（Given/When/Then）

- **类型/工具**：agent / Trae ｜**依赖**：task09, task33 ｜**并行组**：W3 ｜**工作量**：L ｜**选型依据**：self-critique §三 R3 + Claude Code prompt-caching（tool search 保护前缀）
- **交付物**：MCP 工具延迟加载（摘要列表常驻，完整描述按需拉取，变更不破坏缓存前缀）+ OAuth 认证（Authorization Code + API key）+ 自动重连（指数退避 ≤5）+ 动态工具更新监听 + 子代理级 mcpServers 隔离 + per-tool 结果大小限制
- **验收**：① Given MCP 工具列表变更，When 会话中，Then 缓存前缀不受影响（deferred 语义）② Given server 进程退出，When 检测，Then 自动重连 ③ Given 子代理配置 mcpServers 子集，Then 主上下文不含这些工具
- **关键**：修复 self-critique 维度2/9 结构性缺陷（MCP 描述进前缀导致缓存失效）

## 2. agent / mcp / tool / skill 调度链

- agent 链：sd-dev(+be-security) → sd-tester → review-*
- 竞品参考：参考 Claude Code prompt-caching.md（tool search deferred 保护前缀）+ mcp.md（OAuth/重连）
- 选型依据：tech-source-audit.md + self-critique 报告（每次修订须对照竞品文档逐项验收）

## 3. workflow 调用

```js
Workflow(dev-standard.mjs, args={ skipDocs:true, skipExplore:true, skipPlan:true, startFrom:NN, rounds:NN })
```

## 4. 与其他 task 关联

- 前置依赖：—
- 联动：task92（R1）是 task24 重构基础；task93/94（R2）依赖 task92 fork 能力；task95（R3）与 task33 改造并行；task96（R4）改造 task26；task97（R5）依赖 task95 + task27
- 执行顺序：见 dev-plan.md「执行顺序（v3.2 优化后）」章节 E 阶段

## 5. 实现规划要点

- 严格对照竞品文档（Claude Code memory/sub-agents/skills/prompt-caching 官方文档已抓取，见 self-critique 报告 §〇证据来源）
- 完成动作：写完工报告 test-reports/task95-completion-report.md → git commit → sync.ps1
