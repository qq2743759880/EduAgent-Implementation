# task92 — AI 8 项修订任务（self-critique 落地）

> 执行工具：**Trae** ｜ 依赖：— ｜ 状态：TODO
> 修订来源：`.opencode/plans/self-critique-ai-agent-vs-competitors.md` + `ai-agent-revision-plan.md`
> 核心定位：R1 子代理独立上下文——修复共享 state 结构性缺陷

## 1. 验收标准（Given/When/Then）

- **类型/工具**：agent / Trae ｜**依赖**：task09, task10 ｜**并行组**：W3 ｜**工作量**：XL ｜**选型依据**：self-critique §三 R1 + tech-source-audit §二
- **交付物**：`app/ai/subagents/runner.py`（独立 LLM 会话循环：独立 messages/system prompt/工具集/maxTurns）+ `definitions.yaml`（子代理 frontmatter：name/description/tools/model/maxTurns/memory_scope，对齐 Claude Code）+ 4 内置子代理（search/tool/learning/memory）+ artifact 写入
- **验收**：① Given 2 个并行子代理，When 执行，Then 各自独立上下文（非共享 state），主 state 仅收 ≤2000 token 蒸馏摘要 ② Given 子代理检索 100 文档，When 完成，Then 原文在 artifact、主上下文只含摘要 ③ Given 子代理崩溃，When 重试，Then 不污染主上下文
- **关键**：修复 self-critique 维度3 结构性缺陷（原计划子代理共享 state，丢失上下文隔离）

## 2. agent / mcp / tool / skill 调度链

- agent 链：sd-dev(+be-architect) → sd-tester → review-*
- 竞品参考：context7(LangGraph Send/独立会话)；参考 Claude Code sub-agents.md（独立 context window）
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
- 完成动作：写完工报告 test-reports/task92-completion-report.md → git commit → sync.ps1
