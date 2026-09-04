# 任务 × Agent 矩阵（优化期 v1.3 —— 编排者出 Prompt + 人工粘贴多平台执行 + 资产调用分级硬约束）

> 2026-09-02 用户裁定（二次变更）：ZCode 只做编排（出开工 Prompt / 独立验收 / 出下一张 Prompt），**不直接派子 agent**；由用户把 Prompt 粘贴到各 agent 平台执行。
> 闭环：编排者出 Prompt（含必读/守则/完工报告要求）→ 用户粘贴到目标平台 → 平台完工（改文件 + 写完工报告，不 commit）→ 用户回传平台名 + 报告路径 → 编排者独立实证验收（curl/grep/node/pytest 复跑）→ 通过：编排者选择性 commit + 出下一张 Prompt；不通过：出返工 Prompt（换平台）。
> v1.3 增补（用户确认）：**资产调用分级**写入本矩阵并作为硬约束执行（见 §资产分级），依据 tt SKILL.md §4「开工 prompt 必须列具名 skill 路径 + 完工报告必须列实际调用证据」。

## 角色与建议分工（可覆写）

| 角色 | 承担 | 建议平台 |
|---|---|---|
| 编排者 | Prompt 生成、验收、commit、契约冻结核验、集成 gate | ZCode（本会话） |
| 前端执行者 | task101~110/117/61/118~122 | trae（备援：traework/openclaw/cursor） |
| 后端执行者 | task113/114/115/116 | claude（备援：cursor） |
| 调研/流程 | task123 | traework |
| 验收复核视角补充 | 技术批判（可选，编排者兜底） | codex |

## 执行约定

- 开工 Prompt 要素（每张必含）：必读文档具名路径、当前任务 GWT、硬性守则（不改 schemas.py（契约任务除外）、静态页注入不重定义全局 `$`/`renderSides`、只改任务详档列出文件、真实 curl 实证、禁 Playwright、**不 commit**、DEBUG=true 注意项）、完工报告路径与证据要求、**资产调用段（按 §资产分级具名到文件路径，模板见下）**。
- 并行批次（S3/S4/S8）内各任务文件集不相交，可同时粘贴给不同平台；同一平台串行做多个任务时按 Prompt 顺序。
- 契约任务（task114/115/116）：执行平台先写 handoffs/taskNN-contract.md（含真实 curl 示例），编排者核验后其前端消费方任务才放行。
- 验收纪律：不采信完工报告，编排者复跑 GWT 机验命令；通过后由编排者选择性 commit `feat(opt)/taskNN-*`（只加本任务文件）。

## 资产分级（硬约束，2026-09-02 用户确认写死）

> `$TT` = `C:\Users\Administrator\.agents\skills\tt`。分级依据 tt SKILL.md §1 竞品直用策略：**有差异化优势才具名，不为合规凑数**——前端静态页修 bug 的核心知识在项目内注入 SOP + curl 实证，强加设计类资产是噪音。

| 级别 | 任务 | 必调资产（具名路径写进开工单） | 完工报告要求 |
|---|---|---|---|
| **A 全量**（BE/契约/安全） | task113/114/115/116 | `$TT\SKILL.md` §5.2 纪律 + `$TT\vendor\sdlc\SKILL.md`（工程主干）+ `C:\Users\Administrator\.agents\skills\harden\SKILL.md`（独立技能，**vendor 中无 harden，勿引 vendor 路径**）；契约单须按 be-architect 结构产出（curl 示例/影响面/级联清单），验收由 be-validator 视角核验 | 「资产消费证据」段必填：读了哪个文件、用了什么方法论、落在哪里（对应改动点） |
| **B 自检**（FE 交互闭环） | task117/61/118/119/120/121 | `$TT\SKILL.md` §5.2 + `$TT\vendor\review\SKILL.md` critique 内核（完工前三视角自检：交互态/边界/错误反馈） | 「资产消费证据」段必填：自检发现并修掉什么；无发现也要写"自检无发现"，禁止略过 |
| **B 自检**（FE 交互/鉴权动线） | task108/109/110 | `$TT\SKILL.md` §5.2 + `$TT\vendor\review\SKILL.md` critique 内核（完工前三视角自检：交互态/边界/错误反馈） | 「资产消费证据」段必填：自检发现并修掉什么；无发现也要写"自检无发现"，禁止略过 |
| **B 自检**（卫生/流程） | task122/123 | `$TT\SKILL.md` §5.2 + `$TT\vendor\review\SKILL.md`（122 用 polish checklist；123 用 critique 视角核对 backlog） | 同上 |
| **C 仅纪律**（已完成的小修类） | task101~107（已完工，不追溯） | 只要求 tt 完工报告/独立实证纪律（开工单已内置），不强制读 vendor 资产 | 常规证据段即可 |
| **编排者侧义务** | 每波次里程碑 | `$TT\scripts\review-gate.mjs`（批判闸门）+ 技术批判落盘 `.ai-hub/plans/tasks/taskNN-技术批判.md` + 登记 critique-backlog-tracker | 批判 ≥3 条含竞品对标；缺失不设 DONE |

### 资产调用段模板（追加到 A/B 级开工单末尾）

```text
■ 资产调用要求（tt 工作流硬约束，缺「资产消费证据」段的完工报告验收不予通过）
- <按上表具名列出本任务的资产路径，逐个标注用途>
- 完工报告新增「资产消费证据」段：写明实际读取了哪个资产文件、消费了什么方法论内核、对应哪些改动点；未产生对应改动的项如实写"已读未适用+原因"
- 禁止冒充调用：报告写了资产名但无对应方法级行为 = 违规，验收抽查发现即返工
```

### 验收侧硬约束（编排者执行）

0. **引用探测纪律（tt §1 红线，2026-09-02 harden 路径事故后写入）**：编排者生成开工单前必须逐个探测资产路径存在（`ls`/`Test-Path`），不引用不存在的资产；执行者读到不存在的路径时应如实报"资产缺失"而非假装已读。
1. A/B 级任务完工报告无「资产消费证据」段 → **直接打回**，不进入技术验收。
2. 证据抽查：对照报告声称的方法论与 diff 实际行为（如 harden 声称加固边界 → diff 中应有对应参数校验/异常分支）；对不上 = 冒充调用，返工。
3. 偏差登记（诚实记录）：task101~107 在本约束生效前完成，无资产消费证据，**不追溯**；自 task108 起全部按本矩阵执行。

## 任务矩阵

| 任务 | 开发平台 | agent 链 | 使用的 skill/工具（具名） | MCP/脚本 | 产物 |
|---|---|---|---|---|---|
| task101 | trae | fe-implementer | —（项目内 SOP：静态页注入模式，AGENTS.md 教训④） | node 结构断言 | 代码+完工报告 |
| task102 | trae | fe-implementer | 同上 | 同上 | 同上 |
| task103 | trae | fe-implementer | 同上 | 同上 + 截图视觉验收 | 同上 |
| task104 | trae | fe-implementer | 同上（chat SSE 契约：AGENTS.md 教训③） | curl SSE 实测 | 同上 |
| task105~110 | trae | fe-implementer | 同上 | curl + 结构断言 + 截图 | 同上 |
| task113 | claude | be-implementer | sdlc/develop + harden（边界加固） | pytest 契约测试 + curl 越权实测 | 代码+契约测试 |
| task114 | claude | be-architect（契约）→ be-implementer | sdlc | be-validator 独立核验 → handoffs/task114-contract.md（C-A） | 契约单+代码 |
| task115 | claude | 同 task114 | sdlc | 同上 → handoffs/task115-contract.md（C-B） | 同上 |
| task116 | claude | be-architect → be-implementer | sdlc | 同上 → handoffs/task116-contract.md（C-C） | 同上 |
| task117 | trae | fe-implementer | 静态页注入 SOP | 消费 C-C 契约单 | 同上 |
| task61 | trae | fe-implementer | 静态页注入 SOP | 消费既有契约⑥（handoffs/task36-contract.md） | 同上 |
| task118~121 | trae | fe-implementer | 静态页注入 SOP | curl + 截图 | 同上 |
| task122 | trae | fe-implementer+polish | review 簇（polish 内核） | grep 机验=0 | 同上 |
| task123 | traework | —（调研） | review 簇（critique 视角） | git log 考古 + pytest | 核对报告 |

## 验收链（每任务固定）

1. 开发完工 → `test-reports/taskNN-completion-report.md`（含实际调用证据：commit hash、curl 输出、pytest 输出）。
2. codex 测试 agent **独立实证**：逐条复现 GWT（不采信报告）；接口类跑真实 HTTP；前端类跑结构断言 + 渲染截图交视觉验收。
3. 技术批判硬闸门：`taskNN-技术批判.md`（≥3 条含竞品对标 URL+日期）+ `taskNN-优化修改方案.md` + `plans/critique-backlog-tracker.md` 登记；`review-gate.mjs --dir --id` 机验 exit 0 才 DONE。
4. 不通过 → 跨平台切换返工（FE：trae→openclaw；BE：claude→cursor）。
