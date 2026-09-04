# task46: /courses/[seriesId] 课程详情（四级展示 + 报名/领券/收藏）

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W7 ｜**工作量**：XL
> **前置**：task44, task16, task17, task20 ｜**后置（联调节点）**：消费契约②（series/cohorts/modules）+⑦（coupons?series_id）+⑧（POST /api/orders）；task47 依赖
> **规范状态**：doc-frontend §二 P8（已有规范，重构核心页）

## 1. 选型依据
- tech-source-audit.md §六；doc-frontend P8（四级 TreeAccordion/CohortList/CouponPicker/FavoriteButton）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 规格 | fe-spec-writer | 引用 P8 |
| 原型 | fe-implementer + prototype skill | course-detail.html（多交互态：班次选择/领券弹窗/收藏） |
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
- Breadcrumb + CourseHero（封面 2/3 + 购买面板 1/3）+ CohortList（价格/剩余席位/满员 disabled）+ CouponPicker + FavoriteButton（aria-pressed）
- Tabs：课程大纲（TreeAccordion 四级）/班次详情/评价/思维导图（echarts 复用）
- 「立即报名」→ POST /api/orders（cohort_id + coupon_receive_record_id）→ 跳 /orders/[orderId]/pay（J3）；未登录跳 /login?redirect=（J4）
- teaching_status 徽章（scheduled/in_progress/completed/cancelled）

## 5. 验收标准（Given/When/Then 全文）
- Given HTML APPROVED，When React 实现完成，Then 与 HTML 对照一致（visual-acceptance）
- Given 选中班次，When 点击立即报名（携带 cohort_id + coupon_receive_record_id），Then 创建订单成功跳支付页；满员班次（current_student_count >= max_student_count）disabled；未登录跳 /login?redirect= 原路（J4）
- Given 领券与收藏，Then 领券弹窗刷新可用券列表（GET /api/coupons?series_id=）；收藏写 favorite_source=series_detail 且心形态与登录态联动（J2/J5）
- Given 四级树渲染，Then series→cohort→module（stage_no 升序）→session（session_no 升序）层级正确

## 6. 交接与记忆
- 完成 → 看板 task46=DONE → sync.ps1
- 交付物：course-detail.html + React + 测试
