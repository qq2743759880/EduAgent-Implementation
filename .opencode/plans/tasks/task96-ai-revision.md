# task96 — AI 8 项修订任务（self-critique 落地）

> 执行工具：**Trae** ｜ 依赖：— ｜ 状态：TODO
> 修订来源：`.opencode/plans/self-critique-ai-agent-vs-competitors.md` + `ai-agent-revision-plan.md`
> 核心定位：R4 context editing——token 优化关键差距

## 1. 验收标准（Given/When/Then）

- **类型/工具**：agent / Trae ｜**依赖**：task26 改造 ｜**并行组**：W3 ｜**工作量**：L ｜**选型依据**：self-critique §三 R4 + Claude Code（context editing 最轻量手段）
- **交付物**：`context_edit.py`（精确删除历史消息保留前缀缓存：删工具调用+结果/冗余中间消息，保留用户意图/未完成决策）+ `tool_result_clearing`（工具结果 N 轮后精简为一行结论，原文进 artifact）+ 上下文使用率监控 + 阈值策略配置（context_edit 优先，compaction 兜底）
- **验收**：① Given 历史 3 条工具调用各 1500 token，When context_edit，Then 减 ~4.5k token 且前缀不变 ② Given 工具结果超 N 轮，Then 精简为一行 ③ Given 超阈值，Then 先 context_edit 后 compaction

## 2. agent / mcp / tool / skill 调度链

- agent 链：sd-dev → sd-tester → review-*
- 竞品参考：参考 Claude Code context-window.md（context editing 最轻量）
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
- 完成动作：写完工报告 test-reports/task96-completion-report.md → git commit → sync.ps1
