# task27: AI 助手：tool_specs 规范 + CoT/token 优化（prompt caching + 双模型）

> **类型**：agent ｜**执行工具**：Trae ｜**阶段**：P4.5 ｜**并行组**：W3 ｜**工作量**：M
> **前置**：task24 ｜**后置（联调节点）**：task29（评估）、task33（MCP 描述联动）

## 1. 选型依据
- tech-source-audit.md §二（Anthropic 差描述浪费 40% 时间→五要素规范；prompt caching 静态前缀；模型分级）
- tech-source-audit.md §五（双模型：fast 决策/子代理、strong 生成）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | tool_specs.py + prompt 精简 + 校验 |
| 测试 | sd-tester + summarize skill | 前缀 token 测量 + 非法 JSON 攻防 |
| 审查 | review-screener-1 | — |
| 工具 | context7 MCP | DeepSeek prompt caching 语义（provider 文档） |
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
- tool_specs.py：ToolSpec（name/description/input_schema/risk(read|write)/parallel_safe/timeout_s/admin_only）；五要素描述规范（做什么+何时用/何时不用/参数域/返回结构/示例/副作用幂等）
- 并行规则：parallel_safe 且无参数依赖 gather；每任务重试 1 + 总工具调用 ≤4
- CoT/token：system ≤300 token（决策规则表化）、few-shot 压缩、prompt caching（system+工具清单按 name 排序固定前缀）、Pydantic 校验（非法重试 1 → 保守回退）、answer 升级 strong

## 5. 验收标准（Given/When/Then 全文）
- Given 工具清单加载，When 测量前缀 token，Then system+工具清单 ≤300 token 且排序确定（同输入前缀逐字节一致，缓存命中）
- Given 决策 LLM 输出非法 JSON，When Pydantic 校验失败，Then 重试 1 次后保守回退（现状 _safe_json_extract 语义），不抛 500
- Given 两个 parallel_safe 且无依赖的工具任务，When 执行，Then 并发调用；admin_only 工具不进入普通用户决策 prompt（task33 联动验证）

## 6. 交接与记忆
- 完成 → 看板 task27=DONE → sync.ps1
- 交付物：tool_specs.py + 精简 prompt + 前缀测量报告 + 单测
