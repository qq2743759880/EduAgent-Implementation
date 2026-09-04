# 存量未开工任务复核结论（backlog-reconciliation.md）

> 复核时间：2026-09-04 · 编排者独立实证（非采信报告），只读审计 + 真实 HTTP + pytest 定向。
> 结论：AGENTS.md「待办」里列的存量任务**全部已在历史迭代中被实现或以 MySQL 方案替代**，无一项需再派发新开工单。

## task35（Neo4j 图谱重建） → ✅ 已由 MySQL 图谱替代（裁剪）

- 证据：`edu-agent/app/mindmap/builder.py` 文档串明「基于 MySQL graph_node/graph_edge 替代 Neo4j」，`build_from_neo4j()` 实为 MySQL Cypher 等价实现；`/api/mindmap/course/{seriesId}` 真实 HTTP 200，返回 `英语音标入门` 完整图谱（CourseSeries/Module/KP/Tag + CONTAINS 边 + mastery 叠加）。
- 消费端：前端 `components/curriculum/CourseMindmapView.tsx` + `curriculum.ts` 已消费 `GET /api/mindmap/course/{seriesId}`。
- Neo4j 仅保留 `/health/detail` 健康探针（degraded 因 192.168.85.101 未起，不影响 MySQL 图谱主链路）。
- **处置**：图谱功能已交付于 task14/task24（MySQL 图实现），task35 Neo4j 独立重建**视为已由替代方案完成，裁剪**。

## task45（全局搜索） → ✅ 已被 courses/search 取代（裁剪）

- 证据：后端无独立 `/api/search`；搜索由 `GET /api/series` 携带 `keyword/delivery_mode/sale_status/price/sort/page` 参数承担（`edu-agent/app/domains/course/router.py:26` list_series）。
- 前端 U6 `/courses/search` 已真实消费该契约（react-batch1 提交 cd96a6d C-A/C-B 对齐）。
- **处置**：task45 独立全局搜索页**过时，裁剪**；语义已收敛进课程搜索。

## task66（退款状态机） → ✅ 已实现

- 证据：`edu-agent/app/domains/trade/refund/schemas.py:18-20` 定义 `RefundType` 四枚举（personal_reason/course_unsatisfied/schedule_conflict/duplicate_purchase）+ `RefundStatus = pending/approved/rejected/refunded`；`hitl_graph.py`（task28）实现 LangGraph interrupt + Command(resume) + 72h 超时升级。
- 用户侧 `GET /api/refunds` 真实 HTTP 200 `{code:0,data:{total:0,items:[]}}`；状态机由 task19 契约测试覆盖。
- **处置**：视为已完成。

## task98（DB 验收框架） → ✅ 已落地

- 证据：`test-reports/task98-verify-all.log` 结尾 `✓ all 校验通过 — 可发布/合并`；质量 5 维（referential/total_value/consistency/temporal/quality）全绿断言 + pytest 792 用例归一化（17 项 expected 已登记，0 未登记）。脚本 `scripts/verify_task07_quality.py` 等已入 git 历史。
- **处置**：已完成。

## task99（批量 auth 补生成） → ✅ 已受理并 commit

- 证据：git 历史 4 commit（1288b92/ffee90d/97b8ed0/80d62b5），`sys_user_auth 212→100015`，bcrypt rounds=12 幂等 `INSERT IGNORE`，verify_schema 0 需修复；完工报告 `test-reports/task99-completion-report.md`。
- **处置**：已受理。

## P1C（Neo4j/Redis 断连熔断） → ✅ 已受理并 commit

- 证据：git commit `f1c5d37`（CircuitBreaker 在 RAG 图谱扩展/缓存读取/记忆向量三路径，复用 task33 breaker + task39 降级埋点）；定向复跑 `tests/test_breaker_db_resilience.py` → **7 passed**。
- **处置**：已受理。

## 遗留说明

- AGENTS.md「待办」中 task35/45 条已过时（源码审计于重构前），本次复核确认其目标已被 MySQL 图 / courses-search 覆盖，故下结论"裁剪"，不是"漏做"。
- 本单仅产出审计结论，无代码改动、无需 commit。