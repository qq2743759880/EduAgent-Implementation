# 任务调度矩阵（59 任务 × agent/skill/workflow/MCP）

> 定位：每个 task 用哪些 agent、skill、workflow、MCP 的具体调度流程。
> 工作流基准：`D:\.ai-hub\workflows\dev-standard.mjs`（8 阶段闭环），本项目适配：后端技术栈 Python/FastAPI（非 PromptForge 桌面版）、前端技术栈 **Next.js 16.3 + React 19 + Tailwind v4 + shadcn**（非 Vite/HashRouter，调用时必须在 agent 指令中显式覆盖）。

## 一、任务类型 → 标准调度链模板

### T1 数据库/数据任务（Trae）
```
开发:  sd-dev（读 edu.sql + dev-plan 验收标准，产出 DDL/脚本）
      + RunCommand+mysql CLI（验证表结构）
      + mermaid skill（产出表关系图，必要时）
测试:  sd-tester（校验脚本/EXPLAIN/计数验证）
审查:  review-screener-1（正确性）→ review-moderator → review-judge
提交:  commit skill（每 task 一个 commit）
```

### T2 后端业务任务（Trae）
```
开发:  sd-dev 主开发（读 dev-plan + design-guide 契约）
      + be-architect（域模块设计，复杂任务如 task11/12/17/18 时调用）
      + be-validator（Zod/pydantic 契约校验，task10/16~22）
      + be-security（task17/18 资金安全红线审查）
      + context7 MCP（查 FastAPI/LangGraph/pydantic 最新文档）
测试:  sd-tester + sd-challenger 并行（PASS/FAIL/BLOCKED JSON verdict）
修正:  sd-dev 修正模式（读测试报告→修复→更新 lessons-learned）
审查:  review-screener-1/2/3 并行 → review-moderator → review-judge（SARIF）
提交:  commit skill
```

### T3 AI/RAG/MCP 任务（Trae）
```
开发:  sd-dev（agent 代码）
      + context7 MCP（LangGraph checkpointer/HITL 文档查询，task24/28）
      + mermaid skill（画 graph 拓扑图）
      + knowledge-trace skill（复杂知识点溯源时）
测试:  sd-tester（评估集/延迟/命中率）+ sd-challenger（攻防：L1误升L3、重复入账）
审查:  review-screener-1/2/3 → review-moderator → review-judge
验证:  task29/32 用 LLM-as-judge 评估脚本（非 agent，是代码产物）
提交:  commit skill
```

### T4 前端任务（TraeWork，含 HTML 原型审核 gate）
```
1 规格:  fe-spec-writer（读 doc-frontend-design-spec + 该页规范，产出 spec 到 .claude/specs/frontend/{taskId}/）
2 原型:  fe-implementer 产出 HTML 参考文件 test-reports/fe-html/{page}.html（全交互态+内联CSS）
3 审核:  【用户 gate】展示给用户 → 用户给设计图 → fe-implementer 按图改 → 循环至用户签收
4 实现:  fe-architect（组件架构，若页面复杂）→ fe-implementer（React 实现）
        + fe-styler（tokens 应用）
        + frontend-design skill / pick-ui-library skill（组件选型时）
        + context7 MCP（Next.js 16 文档——AGENTS.md 要求先读 node_modules/next/dist/docs）
5 审查:  fe-server-infra（dev server 复用）→ fe-perf / fe-a11y-auditor / fe-visual-auditor 并行
        + frontend-visual-validation skill + frontend-browser-testing skill
6 修正:  fe-implementer 修正循环（max 3 轮）
7 测试:  fe-tester（Vitest + Testing Library + Playwright）
8 提交:  commit skill
```

### T5 运维/收尾任务（Trae 或 opencode）
```
开发:  sd-dev / general
测试:  执行即验证（备份恢复演练、压测报告、故障注入）
审查:  review-screener-1/3
提交:  commit skill
```

## 二、59 任务调度矩阵

| task | 执行工具 | agent 链 | 关键 skill | workflow/MCP | 联调节点 |
|------|---------|---------|-----------|--------------|---------|
| 00 备份 | Trae | sd-dev→sd-tester | audit | RunCommand+mysql CLI | — |
| 01 66表DDL | Trae | sd-dev→sd-tester→review-* | mermaid | RunCommand+mysql CLI | — |
| 02 删13表 | Trae | sd-dev→sd-tester | audit | RunCommand+mysql CLI | — |
| 03 sys_user+索引 | Trae | sd-dev→sd-tester | — | RunCommand+mysql CLI | — |
| 04 任务表 | Trae | sd-dev→sd-tester | — | RunCommand+mysql CLI | — |
| 05 diff校验 | Trae | sd-dev→sd-tester | — | RunCommand+mysql CLI | — |
| 06 full档适配 | Trae | sd-dev→sd-tester | — | RunCommand+mysql CLI | — |
| 07 full档重灌 | Trae | sd-dev→sd-tester | summarize | RunCommand+mysql CLI | 「数据基线冻结」 |
| 08 admin恢复 | Trae | sd-dev→sd-tester | — | RunCommand+mysql CLI | — |
| 09 core框架 | Trae | sd-dev(+be-architect)→sd-tester→sd-challenger→review-* | harden | context7 | — |
| 10 响应壳统一 | Trae | sd-dev→sd-tester→review-* | audit | context7 | **契约冻结①→TraeWork task36** |
| 11 课程域 | Trae | sd-dev(+be-architect+be-validator)→sd-tester→review-* | — | RunCommand+mysql CLI | **契约冻结②→TraeWork task38/39** |
| 12 course_admin | Trae | sd-dev(+be-validator)→sd-tester→review-* | — | RunCommand+mysql CLI | **契约冻结③→TraeWork task47/48** |
| 13 题库域 | Trae | sd-dev(+be-validator)→sd-tester→review-* | — | RunCommand+mysql CLI | **契约冻结④→TraeWork task49/50** |
| 14 progress改造 | Trae | sd-dev→sd-tester→review-* | — | RunCommand+mysql CLI | **契约冻结⑤→TraeWork task53** |
| 15 存量壳适配 | Trae | sd-dev→sd-tester | audit | — | 复核契约① |
| 16 market域 | Trae | sd-dev(+be-security)→sd-tester→sd-challenger→review-* | harden | RunCommand+mysql CLI | **→TraeWork task41/45** |
| 17 order域 | Trae | sd-dev(+be-security+be-architect)→sd-tester→sd-challenger→review-* | harden | RunCommand+mysql CLI | **→TraeWork task42** |
| 18 payment域 | Trae | sd-dev(+be-security)→sd-tester→sd-challenger→review-* | harden | RunCommand+mysql CLI | **→TraeWork task43** |
| 19 refund域 | Trae | sd-dev→sd-tester→review-* | — | RunCommand+mysql CLI | **→TraeWork task44** |
| 20 enrollment域 | Trae | sd-dev→sd-tester→sd-challenger | — | RunCommand+mysql CLI | **→TraeWork task40** |
| 21 study域 | Trae | sd-dev→sd-tester→review-* | — | RunCommand+mysql CLI | **→TraeWork task52** |
| 22 tickets域 | Trae | sd-dev→sd-tester→review-* | — | RunCommand+mysql CLI | **→TraeWork task46** |
| 23 Redis缓存 | Trae | sd-dev→sd-tester→sd-challenger→review-* | harden | — | 前端 task52 依赖 |
| 24 LangGraph图 | Trae | sd-dev→sd-tester→sd-challenger→review-* | mermaid | context7(LangGraph) | — |
| 25 三层记忆 | Trae | sd-dev→sd-tester→review-* | — | context7+RunCommand+mysql CLI | — |
| 26 compaction | Trae | sd-dev→sd-tester→sd-challenger | — | context7 | — |
| 27 tool_specs | Trae | sd-dev→sd-tester | summarize | context7 | — |
| 28 HITL退款 | Trae | sd-dev(+be-architect)→sd-tester→review-* | — | context7(LangGraph HITL) | 依赖 task19+24 |
| 29 AI评估 | Trae | sd-dev→sd-tester | — | — | — |
| 30 contextualize | Trae | sd-dev→sd-tester | — | context7 | — |
| 31 reranker接入 | Trae | sd-dev→sd-tester→review-* | — | — | — |
| 32 rag评估 | Trae | sd-dev→sd-tester | — | — | — |
| 33 MCP增强 | Trae | sd-dev→sd-tester→review-* | — | context7(MCP) | — |
| 34 知识库重建 | Trae | sd-dev→sd-tester | summarize | mysql+milvus | — |
| 35 图谱重建 | Trae | sd-dev→sd-tester | mermaid | — | — |
| 36 api-client解包 | TraeWork | fe-spec-writer→fe-implementer→fe-tester | — | context7(Next16) | 消费契约① |
| 37 UI组件基础 | TraeWork | fe-spec-writer→fe-implementer→fe-styler→fe-tester | pick-ui-library,frontend-design | context7(Next16) | — |
| 38 课程中心 | TraeWork | 完整流水线+HTML审核gate | frontend-design,prototype | context7,playwright | 消费契约② |
| 39 课程详情 | TraeWork | 完整流水线+HTML审核gate | frontend-design,prototype | context7,playwright | 消费契约②+task38 |
| 40 我的班次 | TraeWork | 完整流水线+HTML审核gate | frontend-design | context7,playwright | 消费 task20/21 |
| 41 优惠券 | TraeWork | 完整流水线+HTML审核gate | frontend-design | context7,playwright | 消费 task16 |
| 42 订单 | TraeWork | 完整流水线+HTML审核gate | frontend-design | context7,playwright | 消费 task17 |
| 43 支付页 | TraeWork | 完整流水线+HTML审核gate | frontend-design | context7,playwright | 消费 task17+18 |
| 44 退款 | TraeWork | 完整流水线+HTML审核gate | frontend-design | context7,playwright | 消费 task19 |
| 45 收藏 | TraeWork | 轻量流水线+HTML审核gate | frontend-design | context7,playwright | 消费 task16 |
| 46 售后工单 | TraeWork | 完整流水线+HTML审核gate | frontend-design | context7,playwright | 消费 task22 |
| 47 管理端课程 | TraeWork | 完整流水线+HTML审核gate | frontend-design | context7,playwright | 消费契约③ |
| 48 管理端详情 | TraeWork | 完整流水线+HTML审核gate | frontend-design,prototype | context7,playwright | 消费契约③+task47 |
| 49 管理端题库 | TraeWork | 完整流水线+HTML审核gate | frontend-design | context7,playwright | 消费契约④ |
| 50 题目编辑 | TraeWork | 完整流水线+HTML审核gate | frontend-design | context7,playwright | 消费契约④+task49 |
| 51 RAG上传 | TraeWork | 完整流水线+HTML审核gate | frontend-design | context7,playwright | 消费 task54 |
| 52 学习页 | TraeWork | 完整流水线+HTML审核gate | frontend-design,prototype | context7,playwright | 消费 task21+23 |
| 53 适配页组 | TraeWork | 轻量流水线（4页） | — | context7,playwright | 消费契约⑤ |
| 54 RAG上传后端 | Trae | sd-dev→sd-tester→review-* | — | RunCommand+mysql CLI | **契约冻结⑥→TraeWork task51** |
| 55 旧代码清理 | Trae | sd-dev→review-screener-1 | audit | — | 全部完成后 |
| 56 文档交付 | Trae | sd-dev | mermaid,summarize | — | 全部完成后 |
| 57 E2E回归 | TraeWork | fe-tester+sd-tester | frontend-browser-testing,frontend-visual-validation | playwright | 全部完成后 |
| 58 压测容灾 | Trae | sd-dev→sd-tester | harden | — | 全部完成后 |

## 三、workflow 调用方式（dev-standard.mjs 适配本项目）

```js
// 后端任务（Trae 内调用）
手动调度（Trae 无 Workflow API）：按 dev-standard.mjs 8 阶段手动调 sd-*/review-*；数据库校验用 RunCommand+mysql CLI / Python 脚本

// 前端任务（TraeWork 内调用）
手动调度（Trae 无 Workflow API）：按 dev-standard.mjs 8 阶段手动调 sd-*/review-*；数据库校验用 RunCommand+mysql CLI / Python 脚本
```

**注意事项**：dev-standard.mjs 内嵌技术栈为 React 18+Vite+HashRouter，本项目为 Next.js 16.3——手动调度时在 prompt/需求中显式声明技术栈（Next.js 16.3，非 Vite），且 fe-architect 的"技术栈确认行"改为 `Next.js 16.3 + React 19 + Tailwind v4 + shadcn`（Q14 校验逻辑同步改）。

## 四、MCP 使用清单

| MCP | 用途 | 使用方 |
|-----|------|--------|
| context7 | 查 Next.js 16 / LangGraph / FastAPI / pydantic 最新文档 | 双方 |
| mysql（未注册）| 数据库表结构验证/DDL 检查 → **RunCommand+mysql CLI / Python 脚本替代**（verify_schema.py 先例）| Trae |
| playwright | 前端视觉审查/E2E/HTML 原型截图 | TraeWork |
| serena | 代码符号导航/引用查找 | 双方（可选） |
| mem0 | 长期记忆（Ollama 启动后可用） | 双方 |
