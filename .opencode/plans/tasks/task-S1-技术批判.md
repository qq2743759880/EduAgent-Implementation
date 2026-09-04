# task-S1 验收批判（强制技术批判）

> 对象：task-S1 全流程 HITL 护栏 + AI 审查 AI（Trae，commit 4f0ef6b）
> 结论：**验收通过**（AC1~AC5 全绿、修复 2 个真 bug、竞品对标到位）。

## 实证结果
- commit `4f0ef6b`（6 文件 +1318）；hitl_gate.py（656 行纯逻辑零 IO）+ executor seam 交付。
- 契测 **39 passed**（S1 16 + task28/T1 回归 14 + task33 9）实跑确认。
- AC1 四步状态机未批准零执行（executor seam SKIPPED）；AC2 四审计字段+manual_guide 透出；AC3 超时双路径（sweep+resume 按原始 created_at）；AC4 AI 审查+3 连拒熔断；AC5 task28 退款 HITL 兼容（正交）。
- **修复 2 个真 bug**：async reviewer 未 await（inspect.isawaitable）；resume 重复建单（复用 action_id 按原始 created_at 超时）。
- 修正：web_search 只读不误判 network_access。

## 批判 1（P2）：HITL_ENABLED 默认 False，护栏未实际启用
- **问题**：默认关闭（为保零回归），exec_command/refund 写工具未在真实链路拦截（报告披露运维待办）。
- **方案**：运维 .env 设 HITL_ENABLED=True 灰度（先 exec_command/refund）后补真实拦截实测。

## 批判 2（P2）：hitl_approval 表未建（SQL 待发布执行）
- **问题**：refactor_sql/task-S1-create-hitl-approval.sql 需目标库执行（报告披露）。
- **方案**：数据库验收/发布流程纳入建表。

## 批判 3（P2）：sweep_expired_pending 无后台定时任务挂接
- **问题**：超时扫描函数就绪，但无定时调度（报告披露"后台定时任务调用"为待办）。
- **方案**：接入后台调度（对齐 task-M1 memory_worker 模式）。

**结论**：三条为运维启用项，不阻塞 task-S1。