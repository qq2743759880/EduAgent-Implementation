# task48: /learning/[seriesId]/[sessionId] 学习播放页

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：L
> **前置**：task41, task21, task23 ｜**后置（联调节点）**：消费契约⑪（study 10 端点）+⑭（缓存性能验收）
> **规范状态**：doc-frontend §二 P9（已有规范）

## 1. 选型依据
- tech-source-audit.md §六；doc-frontend P9（VideoPlayer/Accordion/QuizPanel/enrolled 守卫）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 引用 P9 |
| 原型 | fe-implementer + prototype skill | learning.html（视频/作业/考试三态） |
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
- 视频区 16:9（VideoPlayer 接 session_video + 章节跳转 session_video_chapter + 15s 打点 tick-batch）
- 右侧大纲 Accordion（✓ 已完成/▶ 当前/○ 未开始）；Tabs（视频/作业/考试：作业提交判分、考试计时器/交卷）
- 底部工具栏：AI 提问 → /chat?context=session:{id}（J17）、错题本 → /practice（J18）
- enrolled 守卫：student_cohort_rel.active 才可看 enrolled_only（403 ErrorState）；transcode 未完成占位

## 5. 验收标准（Given/When/Then 全文）
- Given HTML APPROVED，When 未报名访问 enrolled_only 课次，Then 403 拦截 + ErrorState（不吞错）；已报名正常播放
- Given 观看中，When 15s 打点提交，Then tick-batch 写 edu-data 提交表（外键语义）；课次完成判定 = 观看 ≥90% 或作业提交
- Given 作业/考试提交，Then session_homework_submission / session_exam_submission 落库、判分结果展示、analysis_text 解析可见
- Given transcode_status 未 completed，When 渲染，Then 「转码中/不可播」占位（不白屏）

## 6. 交接与记忆
- 完成 → 看板 task48=DONE → sync.ps1
- 交付物：learning.html + React + 测试
