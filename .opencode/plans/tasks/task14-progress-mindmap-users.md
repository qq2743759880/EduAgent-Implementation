# task14: progress/mindmap/recommender 改造 + users bug 修复 + /me 新接口

> **类型**：backend ｜**执行工具**：Trae ｜**阶段**：P3 ｜**并行组**：W2 ｜**工作量**：L
> **前置**：task11, task13 ｜**后置（联调节点）**：**契约冻结⑤ → 前端 task54（/me）、task43（dashboard）、task60（admin/users）**；task21 合流

## 1. 选型依据
- tech-source-audit.md §一（edu.sql 提交表权威；R-7 写失败上抛）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | progress 提交表改造 + dashboard 聚合 + users 修复 |
| 测试 | sd-tester + RunCommand+mysql CLI | 聚合数校验（无 MOCK） |
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
- progress 提交写 edu-data 提交表（session_video_play_event/session_homework_submission/session_exam_submission，恢复外键）
- dashboard 聚合改 student_cohort_rel+series 四级；mindmap/recommender 数据源 curriculum_*→series+question
- users/router.py:83 修复（UPDATE users→UPDATE sys_user，异常上抛）
- 新增 GET /api/users/me/student-profile、GET /api/users/me/learning-summary

## 5. 验收标准（Given/When/Then 全文）
- Given 学习打点提交，When 写入 play_event，Then 落 session_video_play_event 且外键约束生效；dashboard 聚合数与学生实际报名/学习一致（无 MOCK）
- Given 用户请求 /me/learning-summary，Then 返回学习时长/完成课次/积分等真实聚合，与 task54 前端对接字段一致
- Given 用户资料更新失败场景，When UPDATE 执行失败，Then 异常上抛（R-7）返回 5xxxx 而非静默吞掉（P10 遗留 bug 关闭）
- Given mindmap/recommender 请求，When 执行，Then 数据源来自 series 体系 + question（grep 无 curriculum_* 引用）

## 6. 交接与记忆（契约冻结⑤）
- 完成 → 写 `handoffs/task14-contract.md`：/me 两端点 + dashboard 聚合结构 + 提交表字段
- 看板 task14=READY_FOR_FRONTEND（解锁 TraeWork task54/43/60）→ sync.ps1
- 交付物：progress/mindmap/recommender/users 改造 + pytest + 交接单
