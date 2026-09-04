# task36: RAG 上传后端增强（tasks 接口 + Redis/表双写 + MinIO edu-upload 留存）

> **类型**：backend+rag ｜**执行工具**：Trae ｜**阶段**：P7 ｜**并行组**：W2 ｜**工作量**：M
> **前置**：task04, task10 ｜**后置（联调节点）**：**契约冻结⑥ → 前端 task61（/admin/rag 上传入口）**

## 1. 选型依据
- tech-source-audit.md §四（Redis 多角色：task_store 持久化 `edu:knowledge:task:{id}` TTL 24h + knowledge_import_task 表双写）
- edu-data-refactor-plan.md FR-RAG-03（MinIO edu-upload 留存 30 天 + tasks 列表接口）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | tasks 接口 + 双写 + MinIO 留存 |
| 测试 | sd-tester + RunCommand+mysql CLI | 重启恢复 + 留存验证 |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
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
- GET /api/knowledge/tasks（admin，分页倒序：状态/进度/文件数/错误）
- task_store 内存 → Redis（key edu:knowledge:task:{id} TTL 24h）+ knowledge_import_task 表双写（重启不丢 + 对账）
- 上传原文件留存 MinIO edu-upload（object_key 记入任务表，30 天过期策略）；导入完成后不删源文件
- 响应壳统一 + RBAC admin/manager

## 5. 验收标准（Given/When/Then 全文）
- Given 上传任务运行中，When 服务重启，Then 任务状态从 Redis/MySQL 恢复（pending/running 不丢、done/failed 可查），前端 TaskTable 轮询正常
- Given 导入完成，When 检查 MinIO edu-upload，Then 源文件留存且 object_key 与任务表关联；30 天过期策略生效（生命周期规则验证）
- Given 管理端查询，When GET /api/knowledge/tasks，Then 分页倒序返回任务列表且 RBAC 仅 admin/manager

## 6. 交接与记忆（契约冻结⑥）
- 完成 → 写 `handoffs/task36-contract.md`：upload/tasks/status/partitions 端点 + FormData 规格（.md/.txt/.markdown/.pdf/.docx，单文件 ≤200MB，≤50 文件）
- 看板 task36=READY_FOR_FRONTEND（解锁 TraeWork task61）→ sync.ps1
- 交付物：tasks 接口 + 双写 + MinIO 留存 + 交接单
