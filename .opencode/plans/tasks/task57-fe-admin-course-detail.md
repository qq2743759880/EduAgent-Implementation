# task57: /admin/courses/[seriesId] 管理端系列详情（四级 CRUD）

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：XL
> **前置**：task56, task12 ｜**后置（联调节点）**：消费契约③（四级 CRUD + 视频三表）
> **规范状态**：doc-frontend §二 P14（已有规范）

## 1. 选型依据
- tech-source-audit.md §六；doc-frontend P14（Stepper 分片上传/转码轮询/章节管理）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 引用 P14 |
| 原型 | fe-implementer + prototype skill | admin-course-detail.html（视频上传/转码多态） |
| 审核 | 【用户 gate】 | 循环至 APPROVED |
| 实现 | fe-architect → fe-implementer + fe-styler | 复杂页架构 |
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
- 系列信息卡（可编辑）+「新增班次」；班次 DataTable（价格/容量 18/60/起止/状态）
- 选中班次 → Accordion 模块管理（stage_no 排序、模块 CRUD）→ 课次列表 → 资源 4 入口 Dialog（课件/视频/作业/考试）
- 视频上传 Stepper（分片 init→finalize→bind）+ 转码轮询（3s refetchInterval 终态停）+ 审核徽章 + 章节管理（start/end_second 拖拽预览）
- 全部软删

## 5. 验收标准（Given/When/Then 全文）
- Given HTML APPROVED，When 四级 CRUD 操作，Then 系列→班次→模块→课次逐级管理全通；唯一约束冲突（同 cohort stage_no）前端提示后端业务码
- Given 视频上传，When 分片上传完成 bind 到课次，Then transcode_status 轮询徽章正确（pending→warning/in_progress→primary/completed→success/failed→destructive）+ Timeline 转码轨迹
- Given 章节管理，When 保存起止秒，Then 与 session_video_chapter 对应；删除全部软删

## 6. 交接与记忆
- 完成 → 看板 task57=DONE → sync.ps1
- 交付物：admin-course-detail.html + React + 测试
