# task06: full 档生成脚本适配（layers 1..7、断点续跑）

> **类型**：ops ｜**执行工具**：Trae ｜**阶段**：P2 ｜**并行组**：W1 ｜**工作量**：L
> **前置**：task01~04 ｜**后置（联调节点）**：task07

## 1. 选型依据
- tech-source-audit.md §七（full 档 + 分夜跑批 + 断点续跑；edu-data generate 脚本 progress.py 已有 checkpoint）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | generate/main.py 适配 |
| 验证 | sd-tester + RunCommand+mysql CLI | 中断续跑演练 + 幂等验证 |
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
- `uv run -m generate.main --profile full --layers 1..7`：分层参数 + 每层 checkpoint 记录（重入跳过已完成层）
- checkpoint 粒度到 layer 内批次；batch_size=5000 批量插入
- 分夜跑批操作手册：每晚 layer 分配/预计耗时/失败续跑命令

## 5. 验收标准（Given/When/Then 全文）
- Given 生成执行到 layer 4 被中断，When 次日重跑 `--layers 1..7`，Then 自动跳过已完成层、仅续跑 layer 5~7，总时长与手动续跑一致
- Given 生成脚本执行两次，When 对比两次结果，Then 幂等（唯一键不冲突，计数一致）；batch_size=5000 下单批插入耗时记录在报告
- Given layers 1..7 全部完成，When 运行分层计数校验，Then 每层计数符合预期（系列 base 219、模块 657、题库 73、题目 1752、用户 ≈10 万、订单 ≈8 万、曝光日志 ≈8 万）
- Given 生成过程中 Redis/MySQL 连接抖动，When 恢复后重跑，Then checkpoint 保证不重复不丢失

## 6. 交接与记忆
- 完成 → 看板 task06=DONE → sync.ps1
- 交付物：适配后的 generate/main.py + 分夜跑批手册 + 幂等验证报告
