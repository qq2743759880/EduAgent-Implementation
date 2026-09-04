# task61: /admin/rag RAG 控制台（含新增上传入口）

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：L
> **前置**：task41, task36 ｜**后置（联调节点）**：消费契约⑥（task36 RAG 上传后端）
> **规范状态**：doc-frontend §二 P18（已有规范，上传 Tab 区块）

## 1. 选型依据
- tech-source-audit.md §六；doc-frontend P18（Uploader/TaskTable/PartitionPanel/_default 禁删）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 引用 P18 |
| 原型 | fe-implementer | admin-rag-upload.html（上传/任务/分区三区块） |
| 审核 | 【用户 gate】 | 循环至 APPROVED |
| 实现 | fe-implementer + fe-styler | React |
| 审查 | fe-server-infra → fe-perf/fe-a11y-auditor/fe-visual-auditor | ≤3 轮 |
| 测试 | fe-tester | Vitest + Playwright |
| 工具 | playwright MCP + context7 MCP | — |
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
- Tabs 新增「上传」Tab：UploadPanel（拖拽/多选、.md/.txt/.markdown/.pdf/.docx、单文件 ≤200MB、≤50 文件、前端校验拦截、onUploadProgress 进度条）
- TaskTable（5s refetchInterval 轮询 pending→running→done/failed、chunks 进度、错误明细+重试）
- PartitionPanel（列表/删除、_default「公共分区·不可删除」禁用）；CollectionHealthCard（上传完成 invalidate ["rag","collection"]）

## 5. 验收标准（Given/When/Then 全文）
- Given HTML APPROVED，When 上传多文件，Then 进度条实时、上传后进入任务列表、任务轮询全链路可见（chunks 进度展示）
- Given 分区管理，When 操作，Then _default 禁删提示；GET /api/knowledge/tasks 分页倒序驱动 TaskTable
- Given 上传完成，When 自动刷新，Then 集合行数更新（FR-RAG-02 全链路闭环）

## 6. 交接与记忆
- 完成 → 看板 task61=DONE → sync.ps1
- 交付物：admin-rag-upload.html + React + 测试
