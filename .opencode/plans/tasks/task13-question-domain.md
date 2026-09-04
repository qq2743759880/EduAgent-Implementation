# task13: question 域：question_admin 重写 + quiz 出题源改造 + 批量导入

> **类型**：backend ｜**执行工具**：Trae ｜**阶段**：P3 ｜**并行组**：W2 ｜**工作量**：L
> **前置**：task10, task07 ｜**后置（联调节点）**：**契约冻结④ → 前端 task58（题库）、task59（题目编辑）、task49（复习中心出题源）**；task14 依赖

## 1. 选型依据
- tech-source-audit.md §一（edu.sql question 表权威：options_json/answer_text/analysis_text）
- edu-data-refactor-plan.md FR-API-03（1752 题批量导入、组卷快照、标签废除改全文检索）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev + be-validator | question_bank/question CRUD + 导入端点 + 组卷 |
| 测试 | sd-tester + RunCommand+mysql CLI | 1752 题导入演练 + 幂等 |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
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
- question_bank CRUD（bank_code 唯一）；question CRUD（options_json/answer_text/analysis_text/objective_flag）
- 批量导入：.xlsx/.csv → 校验 → 预览 → 分批导入 → 结果报告（失败行定位）
- 组卷改 session_exam + session_exam_question_rel（发布时题目快照）
- quiz 出题源 admin_question→`question`；标签逻辑删除（stem+analysis_text LIKE 检索）

## 5. 验收标准（Given/When/Then 全文）
- Given 批量导入 1752 题文件，When 执行导入，Then 全部入库且失败行（题干/答案缺失、题型非法）逐行报告；重复执行幂等（question_no 唯一键冲突回查返回原记录）
- Given quiz 出题，When 请求出题，Then 题目来源为 `question` 表且返回含 analysis_text 解析字段，错误码/响应壳统一
- Given 考试发布，When 考试期间修改原题，Then 考试作答仍按快照判分（组卷快照机制生效）

## 6. 交接与记忆（契约冻结④）
- 完成 → 写 `handoffs/task13-contract.md`：banks/questions/import 端点 + 导入结果结构 + 出题接口
- 看板 task13=READY_FOR_FRONTEND（解锁 TraeWork task58/59/49）→ sync.ps1
- 交付物：question_admin 重写 + quiz 改造 + pytest + 交接单
