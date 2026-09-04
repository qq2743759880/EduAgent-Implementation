# task16: market 域新建（coupons 3 端点 + favorites 3 端点）

> **类型**：backend ｜**执行工具**：Trae ｜**阶段**：P4 ｜**并行组**：W2 ｜**工作量**：L
> **前置**：task10 ｜**后置（联调节点）**：**契约冻结⑦ → 前端 task63（/coupons）、task67（/favorites）**；task17 依赖

## 1. 选型依据
- tech-source-audit.md §一（edu.sql coupon 系 4 表/系列收藏表映射）
- tech-source-audit.md §四（幂等三层纵深：receive_no 唯一键 + 条件更新）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev + be-security | coupon/favorite 两子模块 |
| 测试 | sd-tester + sd-challenger | 500 并发领券攻防 |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
| 加固 | harden skill | 防超发审查 |
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
- GET /api/coupons（可领列表）、GET /api/coupons/me、POST /api/coupons/{id}/receive
- 领券防超发：`UPDATE coupon SET receive_count=receive_count+1 WHERE id=? AND receive_count<total_count`（受影响行数=0 即失败）
- favorites：GET/POST/DELETE /api/favorites（favorite_source 落库：series_detail/search_result/recommendation/activity_page）

## 5. 验收标准（Given/When/Then 全文）
- Given 券 total_count=500，When 500 个并发领取请求（receive_no 唯一键 + 条件更新），Then 恰 500 成功，第 501 起返回 40920"已领完"，无超发
- Given 已领券用户请求 /api/coupons/me，Then 按 receive_status ∈ {unused,used,expired} 返回并含过期时间；服务端收藏 POST/DELETE 幂等（重复收藏返回原记录）

## 6. 交接与记忆（契约冻结⑦）
- 完成 → 写 `handoffs/task16-contract.md`：6 端点 + 券枚举（cash/discount/trial/gift）+ receive_status
- 看板 task16=READY_FOR_FRONTEND（解锁 TraeWork task63/67）→ sync.ps1
- 交付物：domains/trade/coupon + favorite + pytest + 交接单
