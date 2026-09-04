# task07: full 档执行 + 计数校验（219/657/73/1752/10万/8万）

> **类型**：ops ｜**执行工具**：Trae ｜**阶段**：P2 ｜**并行组**：W1 ｜**工作量**：XL
> **前置**：task06 ｜**后置（联调节点）**：「数据基线冻结」→ 通报 TraeWork（编排者动作）；task08/11/13/34 依赖
> **口径修订（v1.1，2026-08-17 用户授权）**：验收标准从「单机构基准 219/73/1752」改为「**6 机构多租户口径**」——实证：org_institution 6 家真实（星航/青藤/知行/启明/优学/进阶）、order 按机构独立（13312/13456/13390/13307/13353/13182）；课程/题库为统一模板（series_name distinct=438、bank distinct=73×6）

## 1. 选型依据
- tech-source-audit.md §七（分夜跑批 + 幂等 upsert 批处理标准做法）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 执行 | sd-dev（监督生成）+ RunCommand+mysql CLI | 分批执行 + 校验 SQL |
| 验证 | sd-tester + summarize skill | 计数校验报告 |
| 审查 | review-screener-1 | 校验报告复核 |
| 提交 | commit skill | 数据不提交，仅脚本/报告 |

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
- 按 task06 手册分夜执行 layers 1..7；每日进度报告
- 六项校验 SQL：series base=219、module_code 去重=657、question_bank=73、question=1752、sys_user≈10万、order≈8万
- 抽样 3 系列四级关联查询验证无孤儿记录
- 完成后向编排者报告 → 编排者写「数据基线冻结」通报（TraeWork 知悉 edu.sql 已落地）

## 5. 验收标准（Given/When/Then 全文）
- Given 生成完毕，When 执行校验 SQL（**6 机构口径**：series=2628=219模板×2变体×6机构、module_code 去重=657、question_bank=438=73×6、question=10512=1752×6、sys_user≈10万、order≈8万），Then 六项全部达标，偏差 >0.5% 需人工复核
- Given 校验通过，When 抽样 3 个系列（覆盖 ≥2 个机构）执行四级关联查询（系列→班次→模块→课次），Then 数据完整无孤儿记录（cohort 必有 series、course 必有 cohort、session 必有 course）
- Given 校验完成，When 提交校验报告，Then 报告含每层耗时/批量参数/失败重试记录

## 6. 交接与记忆
- 完成 → 看板 task07=DONE + 「数据基线冻结」标记 → sync.ps1
- 交付物：full 档数据 + 六项计数校验报告
