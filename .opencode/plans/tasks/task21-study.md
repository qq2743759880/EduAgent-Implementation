# task21: study 域新建（10 端点 + progress 提交表改造）

> **类型**：backend ｜**执行工具**：Trae ｜**阶段**：P4 ｜**并行组**：W2 ｜**工作量**：L
> **前置**：task20 ｜**后置（联调节点）**：契约冻结⑪（与 task20 合并发布）→ 前端 task47/48；task23 性能合流

## 1. 选型依据
- tech-source-audit.md §一（edu.sql 提交表权威：session_video_play/play_event/submission）
- edu-data-refactor-plan.md FR-API-05（study 10 端点 + access_scope 鉴权）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | sessions/videos/chapters/history/homeworks/exams |
| 测试 | sd-tester + RunCommand+mysql CLI | 鉴权矩阵 + 外键语义 |
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
- 10 端点：sessions/videos/chapters/video-history（15s 打点写 session_video_play + play_event）/homeworks（列表/详情/提交→判分）/exams（详情/提交/结果）
- access_scope 鉴权：public/trial/enrolled_only/internal_only（enrolled_only 需 student_cohort_rel.active）
- progress 提交改 edu-data 表（与 task14 合流）

## 5. 验收标准（Given/When/Then 全文）
- Given 未报名用户请求 enrolled_only 资源，When GET 该课次视频，Then 403（前端 ErrorState 展示"需报名"）
- Given 学习 15s 打点提交（tick-batch），Then play_event 落库且外键 play_session_id 语义正确；作业/考试提交写 submission 表且恢复 edu.sql 外键
- Given 课次含 session_asset（video/handout/exercise/reference/image），When 请求课次详情，Then 按 material_category + access_scope 正确过滤返回
- Given 视频 transcode_status，When 查询，Then pending/in_progress/completed/failed 状态与 task12 转码管线一致

## 6. 交接与记忆（契约冻结⑪）
- 完成 → 与 task20 合并写 `handoffs/task20-21-contract.md`
- 看板 task21=READY_FOR_FRONTEND（解锁 TraeWork task47/48）→ sync.ps1
- 交付物：domains/learning + pytest + 交接单
