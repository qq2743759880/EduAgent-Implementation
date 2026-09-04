# task24: AI 助手：LangGraph 图重构（route→plan→fan-out→merge→reflect→answer）+ Redis checkpointer + effort scaling

> **类型**：agent ｜**执行工具**：Trae ｜**阶段**：P4.5 ｜**并行组**：W3 ｜**工作量**：XL
> **前置**：task09, task10, task23 ｜**后置（联调节点）**：task25~28；前端 task50（chat 页不依赖新契约，仅接口对齐）

## 1. 选型依据
- tech-source-audit.md §二（LangGraph 1.2 保留升级 + AsyncRedisSaver durable execution；orchestrator-worker 对齐 Anthropic Building Effective Agents/Multi-agent Research System；effort scaling 四档对齐官方数字；artifact 轻引用）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | graph.py + 子代理 |
| 建模 | mermaid skill | 图拓扑（route/plan/fan-out/merge/reflect/answer） |
| 测试 | sd-tester + sd-challenger | kill 恢复攻防 + 并行性验证 |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
| 工具 | context7 MCP | LangGraph checkpointer/Store API 查询 |
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
- graph.py：route_node（fast 四类意图）→ 条件边（chitchat 直连 answer / knowledge-tool-learning 进 plan）→ plan_node（tasks[{agent,goal}]）→ fan-out（Send/gather 并行子代理）→ merge_node（汇总/去重/冲突标注）→ reflect_node（LLM-as-judge sufficient?）→ answer_node（strong 流式）
- AsyncRedisSaver checkpointer + RedisStore；MAX_REFLECT_ITERATIONS=2；超限 answer 标 degraded_reason="reflect_max_iter"
- effort scaling：L0 1 调用/L1 2-4/L2 5-8/L3 10+（保守判定）
- 子代理：search/tool/learning/memory（fast 模型，1000-2000 token 蒸馏摘要 + artifact 轻引用）
- user_id 真实注入（删除 2 处硬编码 TODO）

## 5. 验收标准（Given/When/Then 全文）
- Given 四类意图样本（知识检索/工具/学习建议/闲聊），When 逐一请求，Then 路由正确分发；chitchat 直连 answer_node（1 次 fast 调用）；knowledge 走 plan→fan-out→merge→reflect→answer
- Given 图中途进程崩溃（注入 kill），When 同 thread_id 重新 ainvoke，Then 从最近 Redis checkpoint 恢复继续执行（durable execution），不重复已完成节点
- Given 多任务 plan（2 个独立子代理任务），When 执行，Then 并行完成（asyncio.gather，总耗时 ≈ max 而非 sum）；state 中 user_id 为真实用户（grep 无 user_id=1）

## 6. 交接与记忆
- 完成 → 看板 task24=DONE → sync.ps1
- 交付物：app/ai/（graph.py + agents/）+ 图拓扑图 + pytest
- 风险（薄弱点 W1）：多子代理 LLM 成本/延迟放大。缓解：保守 effort scaling + task29 评估攻防 + 并发闸 8（task26）
