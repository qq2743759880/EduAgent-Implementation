# task25: AI 助手：三层记忆 + 遗忘机制（user_memory 表 + Milvus collection）

> **类型**：agent ｜**执行工具**：Trae ｜**阶段**：P4.5 ｜**并行组**：W3 ｜**工作量**：XL
> **前置**：task24 ｜**后置（联调节点）**：task29（评估）

## 1. 选型依据
- tech-source-audit.md §二（三层记忆对齐 Anthropic Effective Context Engineering；遗忘曲线 Ebbinghaus exp(-λ·Δt)；importance 规则+LLM 双轨）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | user_memory 表 + 记忆服务 + 遗忘任务 |
| 测试 | sd-tester | 遗忘衰减/淘汰单测 |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
| 工具 | context7 MCP + RunCommand+mysql CLI | LangGraph Store API + 表结构 |
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
- Working = LangGraph state；Short-term = Redis session:{sid}:history ZSET + chat_message；Long-term = MySQL user_memory（user_id/memory_type/content/importance/score/created_at/last_access_at）+ Milvus user_memory collection（用户分区）
- 遗忘：score = importance × exp(-0.01·Δt) + recency_bonus；<0.1 软删；>500 条淘汰最低分
- 会话结束异步写 Redis 队列；检索双路召回 top-3 拼入 plan prompt

## 5. 验收标准（Given/When/Then 全文）
- Given 用户多轮对话含明确偏好（"我想考雅思"），When 会话结束，Then user_memory 落库（importance≥4）且不阻塞应答（异步队列）
- Given 用户下次提问相关话题，When 检索记忆，Then 向量召回 top-3 进入 lead plan prompt，回答体现记忆（"该用户上次提到…"）
- Given 记忆超 500 条，When 遗忘任务运行，Then 综合分最低者被淘汰；重要性高但久未访问的记忆按时间衰减而非误删
- Given 记忆写入失败，When 队列重试，Then 不影响应答链路（异步隔离）

## 6. 交接与记忆
- 完成 → 看板 task25=DONE → sync.ps1
- 交付物：user_memory 表 DDL + 记忆服务 + 遗忘任务 + Milvus collection 定义 + 单测
