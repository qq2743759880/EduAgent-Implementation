# task02: 13 张平行旧表删除 + 代码引用清理（动作 C）

> **类型**：database ｜**执行工具**：Trae ｜**阶段**：P1 ｜**并行组**：W1 ｜**工作量**：M
> **前置**：task01 ｜**后置（联调节点）**：task05、task11~13（替代表接管）

## 1. 选型依据
- tech-source-audit.md §一（edu.sql 唯一权威，三套模型归一）
- 依据 self-built-tables-audit.md：13 表删除清单与替代表映射

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | DROP 脚本 + 引用 grep 清单 |
| 验证 | sd-tester + RunCommand+mysql CLI | 外键巡检（information_schema） |
| 审查 | review-screener-1 | grep 覆盖 f-string 表名拼接 |
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
- 13 表：curriculum_*(4)、admin_question_bank、admin_question、admin_exam_paper、admin_exam_paper_item、admin_question_tag、admin_question_to_tag、admin_course_video_asset
- 替代表映射：curriculum_*→series 系；admin_question_bank/admin_question→question_bank/question；admin_exam_paper×2→session_exam 系；admin_question_tag×2→全文检索（删除后重构）；admin_course_video_asset→session_asset/video/chapter
- grep 覆盖：旧表名、旧路由、f-string/动态 SQL 拼接模式
- 仅注释/文档豁免需列清单

## 5. 验收标准（Given/When/Then 全文）
- Given 13 旧表已 DROP，When 对 edu-agent/edu-frontend 全量代码 grep 旧表名与旧路由，Then 零引用（仅注释/文档可豁免，需列清单）
- Given 删除后遗留外键依赖检查，When 执行 information_schema 外键巡检，Then 无孤儿外键、无悬空视图
- Given 遗漏隐藏引用（动态 SQL 拼接），When 运行任务列表查询，Then 不抛错（grep 已覆盖字符串拼接模式）
- Given task05 diff 校验运行，When 对比 edu.sql，Then 已删表不在保留清单亦不在 66 表清单中（无游离表）

## 6. 交接与记忆
- 完成 → 看板 task02=DONE → sync.ps1
- 交付物：DROP 脚本 + 映射清单 + grep 零引用报告
