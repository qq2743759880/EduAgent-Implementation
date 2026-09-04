# task86 — 管理端补全任务

> 执行工具：**TraeWork** ｜ 依赖：— ｜ 状态：TODO
> 联调节点：消费契约⑫
> 来源：dev-plan.md §2.9（P0+P1 范围确认，P2 二期）

## 1. 验收标准（Given/When/Then）

- **类型**：frontend｜**依赖**：task41, task77b｜**并行组**：W7｜**工作量**：L｜**执行工具**：TraeWork
- **交付物**：营收趋势（折线）+ 转化漏斗（漏斗图）+ 出勤/完课率（柱状/环形）+ echarts 图表色板
- **验收标准**：
  - Given 报表页，When 切换维度/周期，Then echarts 渲染真实聚合数据；空态处理；HTML 原型审核通过
- **选型依据**：见 tech-source-audit.md §一/§三（响应壳/Redis 等）
- **联调节点**：契约冻结（见 orchestration-frontend-backend.md）

| task70 | M5 公告+站内信后端 | backend | Trae | task03, task10 | W2 | L | 公告/站内信 2 新表+CRUD+C 端未读接口 |
| task71 | M1 订单管理后端 | backend | Trae | task17 | W2 | M | admin orders 4 接口+状态过滤 |
| task72 | M2 退款审批后端(HITL) | backend | Trae | task19, task28 | W2 | L | admin refunds 4 接口+HITL 挂载 |
| task73 | M3 报名/学员画像后端 | backend | Trae | task20, task21 | W2 | XL | cohort students+profile+answers 聚合 |
| task75 | M6 工单管理后端 | backend | Trae | task22 | W2 | M | admin tickets 6 接口+满意度统计 |
| task77b | M8 报表后端 | backend | Trae | task71, task73 | W2 | M | 营收/漏斗/出勤报表 |
| task88 | M10 营销管理后端(券) | backend | Trae | task16 | W2 | M | 券模板 CRUD+核销统计 |
| task89 | M11 CRM 线索后端 | backend | Trae | task10 | W2 | M | leads CRUD+follow+stats+transfer |
| task78 | /admin/orders 订单管理页 | frontend | TraeWork | task41, task71 | W7 | L | 订单列表+详情+代取消+备注 |
| task79 | /admin/refunds 退款审批页 | frontend | TraeWork | task41, task72 | W7 | L | 退款单+审批弹窗+拒绝理由 |
| task80 | /admin/cohorts/[id] 班级学员页 | frontend | TraeWork | task41, task73 | W7 | L | 学员列表+进度+移出 |
| task81 | /admin/students/[id] 学员详情+作答页 | frontend | TraeWork | task41, task73 | W7 | XL | 画像+作答明细(解析) |
| task83 | /admin/tickets 工单+申诉页 | frontend | TraeWork | task41, task75 | W7 | L | 工单时间线+回复+满意度 |
| task84 | /admin/announcements 公告发布页 | frontend | TraeWork | task41, task70 | W7 | M | 公告编辑器+范围发布 |
| task85 | /admin/messages 站内信台 | frontend | TraeWork | task41, task70 | W7 | M | 发送台+记录 |
| task86 | /admin/reports 报表页 | frontend | TraeWork | task41, task77b | W7 | L | echarts 营收/漏斗/出勤 |
| task90 | /admin/marketing 营销管理页 | frontend | TraeWork | task41, task88 | W7 | M | 券管理+核销统计 |
| task91 | /admin/crm CRM 线索页 | frontend | TraeWork | task41, task89 | W7 | M | 线索+跟进+漏斗 |
## 附录 A：交付物总清单

1. 数据库：重构 SQL（66 表重建 + 13 删除 + 改造 + 索引 + 任务表）+ diff 校验脚本
2. 数据：full 档全量数据 + 六项计数校验报告 + 分层生成手册
3. 后端：core/ + middleware/ + 7 新域（market/order/payment/refund/enrollment/study/tickets）+ 4 改造域 + Redis 缓存层 + 响应壳统一 + pytest
4. AI 助手：LangGraph 新图 + Redis checkpointer + 三层记忆 + compaction + tool_specs + HITL + 评估报告
5. RAG：contextualize + reranker + course_public 分区 + rag_evaluator 报告
6. MCP：描述审查器 + per-server 熔断 + 审计日志
7. 前端：api-client 改造 + 8 新/10 改造客户端 + 14 基础组件 + **27 页面**（每页：HTML 审核台账 + React + 测试）
8. RAG 上传：前端 UploadPanel/PartitionPanel/TaskTable + 后端 tasks 接口 + Redis/表双写 + MinIO edu-upload 留存
9. 知识库：Milvus/Neo4j 重建报告
10. 收尾：清理报告 + 四份文档 + E2E 套件 + Locust 压测报告 + 容灾演练报告

## 附录 B：task-agent-matrix.md 重排说明（v3.0）

> 旧矩阵（59 任务编号）已随本文件重排，映射关系：旧 task36→新 task40、旧 task37→新 task41、旧 task38~53（18 页+适配组）→新 task42~68（27 页，每页一任务）、旧 task54→新 task36、旧 task55→新 task37、旧 task56→新 task38、旧 task57→新 task69、旧 task58→新 task39；后端 task00~35 编号不变。新矩阵以本文件总览表 + `tasks/taskNN-*.md` 的「Agent 调度链」节为准；`task-agent-matrix.md` 本体由编排者在下次维护时同步（本文件为规划权威）。

## 2. agent / mcp / tool / skill 调度链

- agent 链：同上完整流水线(echarts 图表)
- MCP：echarts；chart-palette
- 前端任务必须先过 HTML 原型审核流（产出 test-reports/fe-html/task86-*.html → 用户审核给图 → 返工 → 签收 APPROVED → 写 React）
- 选型依据：tech-source-audit.md（响应壳 §一 / Redis §四 / 前端栈 §五 / 设计 §六）

## 3. workflow 调用

```js
Workflow(dev-standard.mjs, args={ skipDocs:true, skipExplore:true, skipPlan:true, startFrom:NN, rounds:NN })
```

## 4. 与其他 task 关联

- 前置依赖：—
- 联调：消费契约⑫（前后端交接单机制见 orchestration-frontend-backend.md / collaboration-protocol.md）
- C 端对应：见 admin-modules-completion.md §四 闭环对应表

## 5. 实现规划要点

- 模块定位与数据表：见 admin-modules-completion.md（M1~M11 对应模块详表）
- 完成动作：写完工报告 test-reports/task86-completion-report.md（按 task-report-template.md）→ git commit → sync.ps1
