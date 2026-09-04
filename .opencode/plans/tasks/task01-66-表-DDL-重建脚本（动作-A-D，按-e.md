# task01 — 66 表 DDL 重建脚本（动作 A/D，按 edu.sql）

> 执行工具：**Trae** ｜ 类型：database ｜ 前置依赖：—（与 task00 并行） ｜ 并行组：W1 ｜ 工作量：XL ｜ 状态：TODO
> 联调节点：—

## 1. 验收标准（Given/When/Then）

- **类型**：database｜**依赖**：无（与 task00 并行）｜**并行组**：W1｜**工作量**：XL
- **交付物**：`refactor_sql/` 目录：DROP+CREATE 脚本（按 edu.sql 原样，66 表：dim_*(7)、org_*(10)、staff/student_profile、series 系 8 表、题库系 5 表、交易系 9 表、报名/学习/售后/结算/风控等）、27 保留表清单、`order`/`question` 保留字转义规范、回滚脚本
- **验收标准**：
  - Given edu.sql 已解析为重构 SQL，When 在测试库执行，Then 66 表列/类型/唯一键/外键/注释与 edu.sql 逐项 diff 为空（task05 脚本验证）
  - Given 27 张平台扩展表存在，When 执行重构，Then 27 表结构与数据零影响（alembic_version/sys_user_auth/chat_*/community_*/gamification_*/quiz_*/vocab_*/mcp_*/user_profile 等）
  - Given 重建失败，When 执行回滚脚本，Then 恢复至 task00 备份状态
- **风险**：`order`/`question` 为 MySQL 保留字，asyncmy 参数化 SQL 转义不一致易踩坑。缓解：全部引用处统一反引号 + 单测覆盖

## 2. agent / mcp / tool / skill 调度链

- agent 链：sd-dev → sd-tester → review-screener-1 → review-moderator → review-judge
- MCP 工具：context7（查库文档）、mysql（Trae 验证表结构）、playwright（TraeWork 视觉审查/E2E）
- skill：mermaid(表关系图，可选)
- 前置必读：`.opencode/plans/dev-plan.md` 本任务节 + 全局执行原则（§0 六条红线）

## 3. workflow 调用

```js
Workflow(dev-standard.mjs, args={ skipDocs:true, skipExplore:true, skipPlan:true, startFrom:1, rounds:1, testerTypes:["tester"] })
```

## 4. 与其他 task 关联

- 前置依赖：—（与 task00 并行）
- 联调节点：—
- 并行窗口：与本任务同组 W1 的其他任务可并行；前后端联调时序见 `.opencode/plans/orchestration-frontend-backend.md` §二

## 5. 实现规划要点

- 交付物/验收摘要（dev-plan 总览）：66 表结构 diff 为空、27 表保留不受影响
- 实现细节与 Given-When-Then 全文见上方 §1（源自 dev-plan 详述）
- 完成动作：写交接单 `.opencode/handoffs/task01-*.md`（若为契约冻结点）→ 更新 `D:\.ai-hub\memory\project-handoff.md` 看板 → 运行 `powershell -File D:\.ai-hub\sync.ps1`
- 对接守则：`.opencode/plans/collaboration-protocol.md`（越界上浮/契约纪律/记忆分区）
