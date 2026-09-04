# task33: MCP 增强：工具描述评分/重写 + per-server 熔断 + 权限过滤

> **类型**：mcp ｜**执行工具**：Trae ｜**阶段**：P4.5 ｜**并行组**：W5 ｜**工作量**：M
> **前置**：task09 ｜**后置（联调节点）**：前端 task62（/admin/mcp 消费"描述体检"按钮与工具列表）

## 1. 选型依据
- tech-source-audit.md §三（MCP 描述自动审查重写：Anthropic"工具测试代理减少 40% 完成时间"；per-server 熔断对齐 Polaris 模型）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | description_reviewer.py + 熔断接入 + 权限过滤 |
| 测试 | sd-tester | 评分规则/重写/熔断攻防 |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
| 工具 | context7 MCP | MCP 官方规范（modelcontextprotocol.io） |
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
- description_reviewer：规则打分 0-100（动词开头+20/何时不该用+15/参数说明+20/返回结构+15/示例+10/无歧义+20）；<70 分 fast 模型按五要素重写 → mcp_tool.description_rewritten 新列（原描述仅展示）
- discover 后自动跑 + 管理端"描述体检"按钮；审计日志
- per-server 熔断：连续 5 次失败 → 30s 快速失败（替代等满 call_timeout）
- 只读工具同参缓存 60s；admin_only 权限过滤（list_enabled_tool_metas）；input_schema 版本化告警；结果截断 300-500 字

## 5. 验收标准（Given/When/Then 全文）
- Given 一个描述质量差（评分 <70）的工具经 discover 入库，When 审查自动执行，Then description_rewritten 符合五要素规范（≤120 字），审计日志记录 score/rewritten
- Given 某 MCP server 连续 5 次超时，When 第 6 次调用，Then 熔断快速失败（毫秒级返回 CircuitOpenError），30s 后半开放行探针
- Given 普通用户 chat，When 决策 prompt 组装工具清单，Then 不含 admin_only 工具（越权隐患关闭）；同参只读工具 60s 内命中缓存

## 6. 交接与记忆
- 完成 → 看板 task33=DONE → sync.ps1
- 交付物：description_reviewer.py + 熔断接入 + 权限过滤 + 审计日志 + 单测
- 联调：写 `handoffs/task33-contract.md`（体检按钮端点 + 工具列表结构，供 task62）
