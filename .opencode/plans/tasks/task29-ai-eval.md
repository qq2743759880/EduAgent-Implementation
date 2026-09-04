# task29: AI 助手评估：评估集 + LLM-as-judge + 延迟/成本验证

> **类型**：test ｜**执行工具**：Trae ｜**阶段**：P4.5 ｜**并行组**：W3 ｜**工作量**：M
> **前置**：task24~27 ｜**后置（联调节点）**：CP4.5 检查点

## 1. 选型依据
- tech-source-audit.md §二（LLM-as-judge：官方结论"单一 LLM 单 prompt 评分一致性最高"，0-1 评分 + pass/fail）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | 评估集 + judge 脚本 |
| 验证 | sd-tester + sd-challenger | 回放评分 + 攻防（L1 误升 L3） |
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
- 评估集：四类意图各 N 条 + L1~L3 分级样本
- LLM-as-judge 评分脚本（单一 judge prompt 0-1 评分）；延迟分位监控（P95/首包）
- 成本测算表：L0~L3 每档 token 与调用次数、prompt caching 命中率（provider 计量）

## 5. 验收标准（Given/When/Then 全文）
- Given 评估集回放，When LLM-as-judge 评分，Then 意图路由准确率 ≥ 重构前基线；L0 误判为 L3 的比率 <5%（攻防 W1）
- Given 压测 L1~L3 各等级，Then P95 ≤8s、流式首包 ≤3s；L3 成本在预算内（月账单测算报告）
- Given prompt caching 开启，When 连续请求同前缀，Then 缓存命中率 ≥80%（provider 侧计量）

## 6. 交接与记忆
- 完成 → 看板 task29=DONE → sync.ps1
- 交付物：评估集 + judge 脚本 + 评估报告（CP4.5 依据）
