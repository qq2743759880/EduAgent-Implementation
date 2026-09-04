# task26: AI 助手：compaction + artifact 轻引用 + Redis 防过载（队列削峰/会话并发/大 key 治理）

> **类型**：agent+infra ｜**执行工具**：Trae ｜**阶段**：P4.5 ｜**并行组**：W3 ｜**工作量**：L
> **前置**：task24 ｜**后置（联调节点）**：task29（评估）

## 1. 选型依据
- tech-source-audit.md §二（compaction 对齐 Anthropic Context Engineering：6000 token 阈值/tool result clearing；artifact 对齐 Multi-agent Research System 附录"Subagent output to filesystem"）
- tech-source-audit.md §四（Redis 多角色：队列削峰/大 key 治理）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | compaction.py + artifact 分流 + 并发闸/队列 |
| 测试 | sd-tester + sd-challenger | 压缩 token 校验 + 排队超时攻防 |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
| 工具 | context7 MCP | LangGraph Redis 全家桶文档 |
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
- compaction：>6000 token 触发、新增 >3000 再触发、工具输出 >1500 立即蒸馏；summary 结构化 JSON（profile_updates/pending_tasks/decisions/facts）；新消息流 = summary + K=6 轮原文
- artifact：Redis TTL 1h + 本地 JSON 按大小分流；answer JIT 拉取
- 防过载：全局 LLM 并发闸 8（信号量）+ 会话并发 ≤2（chat:concurrent INCR/DECR）+ chat:queue BLPOP 排队 10s 超时提示 + ZSET 分片（单次 50 条）+ checkpoint TTL 7 天 + bigkey 扫描 >1MB 告警

## 5. 验收标准（Given/When/Then 全文）
- Given 消息流 >6000 token，When plan_node 前触发压缩，Then 压缩后上下文 ≤6000 token、summary 保留结构化决策语义、最近 6 轮原文保留
- Given 单条 MCP 工具输出 >1500 token，When 返回，Then 立即蒸馏：原始 JSON 进 artifact（TTL 1h），流内仅 1 行结论（tool result clearing）
- Given LLM 并发闸满（8 个进行中）+ 第 9 个请求，When 进入队列，Then BLPOP 排队；>10s 返回友好提示而非堆积；单用户并发第 3 个请求被拒（≤2）

## 6. 交接与记忆
- 完成 → 看板 task26=DONE → sync.ps1
- 交付物：compaction.py + artifact 服务 + 防过载组件 + 单测（含排队攻防）
