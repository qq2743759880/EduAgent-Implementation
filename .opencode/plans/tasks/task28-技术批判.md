# task28 验收批判（强制技术批判）

> 对象：task28 AI HITL 退款审批（Trae，commit 916519a）
> 结论：**验收通过**。

## 实证结果
- commit `916519a`（8 文件 +812）；hitl_graph.py/repository.py/router.py/main.py/config.py 交付。
- task28 契测 **3 passed（116s，种子+回滚）** 实跑确认，与报告一致。
- hitl_graph.py：interrupt(11)/resume(Command)/approve-apply-END 节点、PlainRedisSaver、FOR UPDATE(5 处，P2 并发防重复)、service_ticket/priority/escalat(72h 超时建工单, 4处/23处)。

## 批判 1（P2）：72h 超时升级工单依赖 LangGraph 调度，生产触发可靠性待压测
- **问题**：超时任务依赖 LangGraph checkpoint 与外部调度，生产长尾（72h）触发可靠性未实跑验证。
- **方案**：task39 压测/里程碑时用缩短 TTL 模拟超时，验证 escalation 幂等与告警。

## 批判 2（P2）：resume 原子三表退款依赖 task19 状态机一致性
- **问题**：approved resume 原子更新 refund/order/student_cohort_rel，但需与 task19 既有退款状态机严格对齐，边界（部分退款/已驳回）未全量覆盖。
- **方案**：task29 评估或后续补部分退款/驳回分支联调。

**结论**：两条为后续验证项，不阻塞 task28。
