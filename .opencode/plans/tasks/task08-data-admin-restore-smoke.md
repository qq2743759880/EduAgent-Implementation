# task08: admin 账号恢复 + 全链路冒烟

> **类型**：ops ｜**执行工具**：Trae ｜**阶段**：P2 ｜**并行组**：W1 ｜**工作量**：M
> **前置**：task07 ｜**后置（联调节点）**：CP2 检查点（数据层冒烟通过后后端域开工）

## 1. 选型依据
- tech-source-audit.md §一（RBAC 沿用，认证 JWT 体系不动）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 执行 | sd-dev + RunCommand+mysql CLI | admin 恢复脚本 + 冒烟执行 |
| 验证 | sd-tester | 冒烟报告 |
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
- 恢复 admin/manager 账号（task00 行级备份）与角色关联
- 冒烟链路：登录→课程浏览→班次→领券→下单→支付 mock→报名→学习→作业/考试→工单（此阶段交易域未建，用 SQL 直插验证数据层）

## 5. 验收标准（Given/When/Then 全文）
- Given full 档数据就绪，When 执行 admin 恢复 + 登录，Then admin/manager 登录成功且 RBAC 角色正确（admin 可进管理端、student 不可）
- Given admin 可用，When 走冒烟链路（登录→课程浏览→班次→领券→下单→支付 mock→报名→学习→作业/考试→工单），Then 每步成功（交易域未建前用 SQL 直插验证数据层）
- Given 冒烟通过，When 提交报告，Then CP2 检查点达成（编排者确认后可进入 P3）

## 6. 交接与记忆
- 完成 → 看板 task08=DONE + CP2 达成 → sync.ps1
- 交付物：admin 恢复脚本 + 冒烟报告
