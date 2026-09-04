# task93 — AI 8 项修订任务（self-critique 落地）

> 执行工具：**Trae** ｜ 依赖：— ｜ 状态：TODO
> 修订来源：`.opencode/plans/self-critique-ai-agent-vs-competitors.md` + `ai-agent-revision-plan.md`
> 核心定位：R2 skill 运行时——补结构性缺失

## 1. 验收标准（Given/When/Then）

- **类型/工具**：agent / Trae ｜**依赖**：task92 ｜**并行组**：W3 ｜**工作量**：L ｜**选型依据**：self-critique §三 R2 + tech-source-audit 新增
- **交付物**：`app/ai/skills/runtime.py`（SKILL.md 解析：frontmatter description/name/paths/context/disable-model-invocation/allowed-tools）+ `registry.py`（扫描 AI-Hub skills + 项目 .claude/skills）+ `loader.py`（渐进式披露：description 列表常驻 ≤1536 字符/条，body 按需加载）+ `trigger.py`（description 匹配 + paths 条件触发）+ `fork_exec.py`（context:fork 走 task92 runner）
- **验收**：① Given AI-Hub 56 skills，When registry 启动，Then 全部索引 ② Given 触发匹配，When 决策，Then body 按需注入（不进前缀）③ Given allowed-tools，When 执行，Then 该轮工具免授权
- **关键**：补 self-critique 维度4 结构性缺失（skill 机制是三家通用标准 agentskills.io）

## 2. agent / mcp / tool / skill 调度链

- agent 链：sd-dev → sd-tester → review-*
- 竞品参考：参考 agentskills.io 标准 + Claude Code skills.md（渐进式披露）；消费 AI-Hub 56 skills
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
- 完成动作：写完工报告 test-reports/task93-completion-report.md → git commit → sync.ps1
