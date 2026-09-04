# task37: 旧代码清理（别名兜底/三套题库残留/未引用 schema）

> **类型**：ops ｜**执行工具**：Trae ｜**阶段**：P9 ｜**并行组**：W8 ｜**工作量**：M
> **前置**：全部前置任务 ｜**后置（联调节点）**：task38 并行、task39/69 依赖

## 1. 选型依据
- edu-data-refactor-plan.md §6（三套模型归一后的残留清理）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 执行 | sd-dev | 全量 grep + 清理 |
| 审查 | review-screener-1 + audit skill | 清理清单复核 |
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
- 后端：curriculum 旧模块残余、admin_question_bank/admin_question 相关 schema/路由、未引用 schema 文件、废弃接口代码（/api/curriculum 除重定向外全清）
- 前端别名兜底：curriculum.ts:184、fallbackPrice/fallbackRating/getSeriesTreeFlat（注意：edu-frontend 归 TraeWork 管，Trae 只清 edu-agent；前端残留写 discrepancy 单上浮）
- README/注释同步

## 5. 验收标准（Given/When/Then 全文）
- Given 全量 grep（curriculum_module|admin_question_bank|旧响应格式 {"ok"}|detail 字段业务代码），When 执行，Then edu-agent 业务代码零命中（仅历史文档豁免，列清单）
- Given 清理完成，When 跑全量回归（task69 冒烟子集），Then 无回归
- Given 前端侧发现残留，When 确认，Then 写 `handoffs/task37-discrepancy.md` 交编排者派单 TraeWork（不越界修改）

## 6. 交接与记忆
- 完成 → 看板 task37=DONE → sync.ps1
- 交付物：清理报告 + discrepancy 单（如有）
