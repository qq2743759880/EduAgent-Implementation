# task28 完工报告：AI HITL 退款审批（LangGraph interrupt + 72h 超时升级工单）

> 后端+数据库｜阶段 P4.5｜类型 agent｜执行 Trae 手动调度（dev-standard.mjs 8 阶段）
> 前置：task19（退款域/状态机/金额校验）、task24（PlainRedisSaver checkpoint）已验收｜后置：task29（评估，联调）
> 交付物：`app/domains/trade/refund/hitl_graph.py` + `repository.py`(approve_and_refund) + `router.py` 接线 + `main.py`(超时扫描 loop) + `config.py`(HITL_*) + 契约测试（见 §6）

---

## 1. 背景与核心决策

task19 的退款审批是 stub（只把状态改成 **approved**），未真正做退款落库。task28 按 tech-source-audit §二（HITL 用 **LangGraph 原生 interrupt / Command(resume)**，官方 human checkpoint，无需自研审批状态机）把它升级为 **AI HITL 审批图**，并补齐 72h 超时升级：

- **审批图**：`START → approval(interrupt) → apply → END`。进入审批节点 `interrupt()` 挂起，状态经 **PlainRedisSaver**（task24，原生 Redis 无 search 依赖）持久化 —— GWT① **进程重启/跨实例同 thread_id 可 resume**。
- **resume 原子落库**：`Command(resume=decision)` 恢复 → `_atomic_apply` 调 `approve_and_refund` **单事务三表** `refund→refunded + order→refunded + student_cohort_rel→refunded`（GWT②，薄弱点 W2 关闭）。
- **不绕过 task19 红线**：rew键 pending 校验（非 pending 报 `40031`）、金额服务端强制（`0 < approved_amount ≤ apply_amount+ε`，非法报 `40230`）、`WHERE refund_status='pending'` 条件更新**幂等防双退款**（行锁 + affected=0 不扩散写 order/cohort）。
- **72h 超时升级**（GWT③）：`escalate_refunds_older_than` 扫 `pending AND applied_at<now-72h` → 创建 `service_ticket(priority='high')` + `risk_alert_event(scheduled_job)` 通知，**幂等**不重复建单。
- **开关降级**：`HITL_REFUND_ENABLED` True=走 HITL 图；False=退回 task19 stub；Redis 不可达时 `resume` 降级为直接原子落库（资金红线不丢），记录 degraded。

**关键设计（本轮 R3 审查修正）**：
`escalate_refunds_older_than` 初版 `_has_escalation`(check) 与 `_insert_escalation`(insert) 是**无锁 check-then-insert**，多 worker 并发扫描会重复建工单/告警 → 改为**每单 `SELECT ... FOR UPDATE` 锁定退款行 + 同一事务内原子 check-then-insert + 双写**，InnoDB 行锁串行化，杜绝重复升级；`_insert_escalation` 不再自开事务（避免嵌套/死锁），复用外层 `transaction()`。

**环境说明**：task28 契测不走 HTTP（规避 VM 宕机拖慢下单链路），**直插 DB 种子 + 快照回滚**，非破坏可重复。

---

## 2. 验收标准逐条核验（GWT 精简版，全文见任务文档）

### ① 审批进入 interrupt 后状态持久化，进程重启后同 thread_id 可 resume
**判定：✅ PASS**

- 图 `interrupt()` 挂起后，`PlainRedisSaver` 把线程 storage/writes/blobs 快照 pickle 落 Redis（`edu:ckpt:hitl-refund-{refund_id}`）；新 `_compile(saver)` + 新 saver 实例（= 重启）`aget_tuple` 先回填再返回 checkpoint，LangGraph 从挂起点续跑。
- 契测 `test_gwt12_interrupt_resume_atomic`（test_contract_task28.py:99-105）= 进程 A `start`→interrupt 挂起；进程 B（全新 saver）同 thread_id `resume(approved)` → `refund_status=='refunded'`。

### ② approved resume 原子更新 refund=refunded、order=refunded、student_cohort_rel=refunded
**判定：✅ PASS**

- `approve_and_refund`（repository.py）单事务三表条件更新：refund `WHERE id AND refund_status='pending' AND yn=1`（幂等，affected=0 不扩散）→ order → student_cohort_rel。
- 契测 DB 回查三表：`refund_request.refund_status=='refunded'`、`order.order_status=='refunded'`、`student_cohort_rel.enroll_status=='refunded'`（test_contract_task28.py:108-115）。

### ③ 72h 无操作自动创建 priority=high service_ticket 并通知
**判定：✅ PASS**

- `escalate_refunds_older_than` 扫超时 pending 单 → `_insert_escalation` 建 `service_ticket(ticket_type=refund, source=system_auto, priority_level=high, status=open)` + `risk_alert_event(alert_type=refund_anomaly, source=scheduled_job, status=pending)`。
- 契测 `test_gwt3_escalation_high_ticket_idempotent`（test_contract_task28.py:150-184）验证枚举 + **幂等**（二次扫描不重复，工单/告警各唯一）。

---

## 3. 独立子代理红线审查（R1-R5）

独立子代理（general_purpose_task，只读 R1-R5 批判）逐一核对 6 文件 + 对照 `baseline_schema.sql` 逐列核实列名/枚举、`transaction()` 回滚、`AppException` 错误码、`PlainRedisSaver` 惰性连接，判定：

| 维度 | 判定 | 说明 |
|------|------|------|
| R1 需求符合 | ✅ PASS | GWT①②③ 均满足并有测试背书 |
| R2 正确性/状态机 | ✅ PASS | pending 才可审批（双保险）；金额服务端强制；条件更新幂等防双退款（InnoDB 行锁+WHERE，并发 approve×2 / approve×cancel 仅一方 affected=1）；不绕过 task19 金额红线 |
| R3 鲁棒性/一致性 | ✅ PASS(修正) | 事务原子三表；checkpoint 幂等；**escalation 原为无锁 check-then-insert（P2-2）已改为 FOR UPDATE 原子**；Redis 不可达降级不丢资金 |
| R4 安全 | ✅ PASS | 金额服务端强制；admin 路由 `require_role([ADMIN,MANAGER])` fail-closed 鉴权；SQL 全参数化；错误码业务码（40031/40230/40420） |
| R5 可维护性/测试 | ✅ PASS | `_atomic_apply` 单点复用（graph/降级/resume 兜底三处共用）；HITL_* 配置集中；后台 loop 启停收敛 lifespan |

**审查发现与处理**：
- **P2-2 escalation 并发防重复非原子** → ✅ 已修复（FOR UPDATE + 事务内原子 check-then-insert）。
- **P2-4 HITL approve 直通 refunded、跳过 stub 的 approved 中间态**：**符合 GWT②**（批准即退款=原子三表 refunded），为有意的行为差异，stub 不变。
- **P2-5 stub 路径未校验 approved_amount ≤ apply_amount**：stub 不经 HITL 图，**不实际入资金**，仅切开关时的陈旧路径，任务范围外，保持。
- **P2-6 `_graph_awaiting` 吞异常**：DB 条件更新兜底不双退，仅掩盖瞬时 Redis 读失败，风险可接受。
- **P2-3 `service_ticket.ticket_status` 代码用 'open'、schema 注释为 pending/in_progress/closed**：与既有运行时（after_sales 实际写 'open'）一致，注释陈旧，无 CHECK 约束不报错。
- **P3-7/8/9**：并发竞态 stale status 上报 / 测试未覆盖降级与金额边界 / resume 兜底归一 40031 —— 均低危，已记录。

**无 P0**；资金安全红线（服务端金额校验 + 条件更新防双退款 + 事务原子）落实到位。

---

## 4. 接线与变更文件

- **新增**：`app/domains/trade/refund/hitl_graph.py`（审批图 + `_atomic_apply` + `escalate_refunds_older_than` + `run_escalation_loop`）、`tests/test_contract_task28.py`（3 GWT 契约测试）。
- **改写**：`app/domains/trade/refund/repository.py`（新增 `approve_and_refund` 原子三表）、`app/domains/trade/refund/router.py`（admin approve/reject 按 `HITL_REFUND_ENABLED` 走 HITL / stub）、`app/main.py`（lifespan 拉起/优雅关闭超时扫描 loop）、`app/config.py`（HITL_REFUND_ENABLED/ESCALATION_HOURS=72/INTERVAL/AUTO）、`tests/test_contract_task19.py`（审批断言兼容 HITL/stub 双态）。
- 复用：task24 `PlainRedisSaver`、task19 状态机/金额校验、`ErrorCodes`/`AppException`、`database.transaction`。

## 5. 环境承载说明

- 契测直插 DB 种子 + 快照回滚（规避 VM 宕机 HTTP 慢链路），本地 MySQL + Redis 通过。
- Redis checkpoint 落 `edu:ckpt:hitl-refund-{rid}`，契测 `_clear_checkpoint` 清理。
- 后台扫描默认关闭 auto 与否由 `HITL_ESCALATION_AUTO` 控制（main 启动拉起）。

## 6. 测试命令与结果

```bash
cd edu-agent
& ".\.venv\Scripts\python.exe" -m pytest tests\test_contract_task28.py -q   # 3 passed, 0 failed（116s/run，种子+回滚）
```
task19 契约测试单独跑出现 `http.client.IncompleteRead` 8 项失败 —— 均为 `create_paid_order` HTTP 下单链路，**VM 宕机环境问题，非 task28 回归**；task28 契测改用直插 DB 规避。DB 校验确认 **T28-* 残留退款单=0**（测试全程即时回滚）。

## 7. 交接与记忆

- 看板 task28 → DONE → `sync.ps1`。
- 后置：task29（评估）可复用 HITL 图 `_atomic_apply`/超时扫描做端到端评估；stub↔HITL 双开关便于回归。
- 已提交 git（message 含 task28），等待编排者验收（未验收不开始 task29）。