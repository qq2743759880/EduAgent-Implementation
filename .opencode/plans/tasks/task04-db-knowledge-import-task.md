# task04: knowledge_import_task 新表 + 通用 task 任务表（动作 F）

> **类型**：database ｜**执行工具**：Trae ｜**阶段**：P1 ｜**并行组**：W1 ｜**工作量**：S
> **前置**：task01 ｜**后置（联调节点）**：task36（RAG 上传后端双写）、task34（通用任务框架复用）

## 1. 选型依据
- tech-source-audit.md §四（Redis 多角色 + durable execution 任务状态表）
- doc-architect-tech-arch.md §3.9（任务级 durable execution：MySQL task 状态表 + progress_json）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | 两表 DDL |
| 验证 | sd-tester + RunCommand+mysql CLI | 状态流转模拟 |
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
- knowledge_import_task：task_id PK、task_type、tenant_id、visibility、status、total_chunks、imported_chunks、source_files JSON、error、created_at、started_at、finished_at
- 通用 task 表：status ∈ {pending,running,succeeded,failed} + progress_json（供 §3.9 durable execution 与 §6.3 批量任务）
- 与 Redis key `edu:knowledge:task:{id}`（TTL 24h）双写对账

## 5. 验收标准（Given/When/Then 全文）
- Given 表已创建，When 模拟导入任务写入状态流转，Then pending→running→succeeded/failed 全流转可持久化且重启后可从表恢复状态
- Given 任务表就绪，When RAG 上传管道双写 Redis + MySQL，Then 两存储状态一致（对账脚本校验）
- Given source_files JSON 列，When 写入 50 个文件元数据，Then 可完整回读（含 object_key/大小/类型）

## 6. 交接与记忆
- 完成 → 看板 task04=DONE → sync.ps1
- 交付物：两表 DDL + 状态流转模拟报告
