# task94 — AI 8 项修订任务（self-critique 落地）

> 执行工具：**Trae** ｜ 依赖：— ｜ 状态：TODO
> 修订来源：`.opencode/plans/self-critique-ai-agent-vs-competitors.md` + `ai-agent-revision-plan.md`
> 核心定位：R2 落地验证

## 1. 验收标准（Given/When/Then）

- **类型/工具**：agent / Trae ｜**依赖**：task93 ｜**并行组**：W3 ｜**工作量**：S
- **交付物**：56 个 skills 全量注册验证 + 抽 3 个代表性 skill（如 dev-standard/audit/knowledge-trace）跑通渐进式披露
- **验收**：Given 全部 skills 注册，When 请求触发代表性 skill，Then 正确加载执行；无 404/死链 skill

## 2. agent / mcp / tool / skill 调度链

- agent 链：sd-dev → sd-tester
- 竞品参考：AI-Hub skills 目录扫描验证
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
- 完成动作：写完工报告 test-reports/task94-completion-report.md → git commit → sync.ps1
