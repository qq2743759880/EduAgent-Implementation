# task19-completion-report · 后端 trade/refund 退款域（契约冻结⑩）

> 类型：backend + database ｜ 阶段：P4/W2 ｜ 执行：TraeCode 手动调度（dev-standard 8 阶段）
> 契约依据：`plans/tasks/task19-trade-refund.md`（api-request §7 为售后工单域/task22，非退款；退款以 task19 文档 `/api/refunds` 为准）
> 状态：**待编排者验收**（未经验收不开始 task20）

---

## 交付范围

- **3 用户端点**：POST `/api/refunds`（申请）、GET `/api/refunds`（倒序列表）、POST `/api/refunds/{id}/cancel`（撤销）
- **HITL 挂载点预留（审批 stub，task28 替换为 LangGraph interrupt）**：POST `/api/admin/refunds/{id}/approve`、`/reject`（require_role ADMIN/MANAGER）、GET `/api/admin/refunds` 过渡列表
- **refund_status 状态机**：`pending → approved/rejected（审批 stub）→ refunded（task28/task20 接续）`；撤销 = 软删 `yn=0`（枚举无 cancelled，保留 refund_status）
- **refund_type 四枚举**：`personal_reason/course_unsatisfied/schedule_conflict/duplicate_purchase`（edu.sql 权威）
- **金额服务端强制**：申请金额 ≤ 实付（订单 payable 或 实际 paid 支付总额），分位容忍
- **refund_no 唯一键幂等 `(institution_id, refund_no)` + 同订单 pending 幂等**；审批/撤销条件更新

## 新增/修改文件

| 文件 | 说明 |
|------|------|
| `edu-agent/app/domains/trade/refund/{schemas,repository,service,router,__init__}.py` | 退款域 |
| `edu-agent/app/main.py` | 注册 refund_router + refund_admin_router（并补回 task18 payment_router——工作树被回滚） |
| `edu-agent/app/middleware/rate_limit.py` | 恢复 task18 env 覆写 + 新增 `EDUAGENT_TRADE_ORDER_LIMIT`（/api/trade/order 测试宽松） |
| `edu-agent/tests/test_contract_task19.py` | task19 HTTP 契约测试（含 H1 并发防双 pending） |
| 恢复 `edu-agent/app/domains/trade/payment/`（HEAD） | task18 文件被工作树回滚丢失，已从 HEAD 恢复 |

> ⚠️ 排障说明：开工发现工作树 `app/domains/trade/payment/`、`main.py` 的 payment 注册、`rate_limit.py` 的 task18 env 改动全部被回滚（HEAD 060a20d 仍在）。已从 HEAD 恢复 payment/ + rate_limit.py，并在 main.py 同时补回 payment 与新增 refund 注册，保证 task18/task19 并存。

---

## 验收标准逐条对照（Given/When/Then）

### GWT① 退款金额 > 实付 → 业务错误码
> Given 用户申请退款金额 > 实付金额，When POST /api/refunds，Then 拒绝并返回业务错误码（金额校验服务端强制执行）。

**实现**：service.create_refund 取订单 `payable_amount` 与 `SUM(payment_record.amount) WHERE payment_status='paid'` 的 paid_total，`effective_paid` 为实付上限；`apply_amount > effective_paid + 1e-6` → `TRADE_REFUND_EXCEED("40230", 400)`。前端 `apply_amount` 仅作输入（无价格信任）。

**实测**：`test_overpay_rejected` PASS——`apply_amount=pay+1` → 400、code `40230`、data null；`test_valid_amount_accepted` PASS——`apply_amount=pay` → 200 pending。

### GWT② pending 撤销 + 不可再次撤销 + 审批驱动
> Given pending 退款单，When 撤销，Then 状态不再 pending 且不可再次撤销；approved/rejected 由管理端审批动作驱动。

**实现**：撤销 = 条件更新 `UPDATE refund_request SET yn=0 WHERE id AND user_id AND refund_status='pending' AND yn=1`；二次撤销（yn=0）幂等返回 `cancelled=True`；非 pending 撤销 → `TRADE_REFUND_STATUS_INVALID("40031")`。审批 stub：`pending→approved/rejected` 条件更新；approved 后不可撤销。

**实测**：
```
test_cancel_pending_and_not_again PASS  —— 撤销后 pending 列表不再出现；二次撤销幂等
test_approval_stub_drives_states PASS    —— reject→rejected；approve→approved；approved 单撤销 → 400/40031
```

### GWT③ 拒绝返回 approver remark
> Given 退款被拒绝，Then 返回 approver remark 供前端展示拒绝理由。

**实现**：reject 把 `remark` + `approver_user_id` 落库；`_refund_from_row` 透出。**实测**：`test_rejected_has_remark` PASS——`status=rejected` 列表能查到 remark。

### GWT④ refund_type 四枚举校验通过
> Given refund_type 枚举，When 提交，Then 四枚举校验通过。

**实测**：`test_refund_type_enum_all_valid` PASS（4 枚举全 200 pending）；`test_refund_type_invalid` PASS（`bogus_type` → 422/42200）。

### 附加 GWT⑤ 资金安全：同订单并发申请仅一条 pending（H1 修复）
**实测**：`test_concurrent_submit_single_pending` PASS——8 并发提交同订单退款 → 全部返回同一 refund_no（FOR UPDATE 串行化，仅一条 pending，无双退款风险）。

---

## 资金安全红线核对（独立子代理 review，经修复）

| 红线 | 结论 |
|------|------|
| R1 金额服务端强制校验（≤ 实付） | ✅ 通过（分位容忍 1e-6） |
| R2 refund_no 唯一键幂等 + 同订单 pending 幂等 | ✅ **修复 H1 后通过**（FOR UPDATE 串行化，防并发双 pending 双退款） |
| R3 状态机条件更新（仅 pending 可撤销/审批） | ✅ 通过 |
| R4 approver remark / approver_user_id 透出 | ✅ 通过 |
| R5 事务边界（raw cursor 无 fetchone-tuple 误用） | ✅ 通过（本域事务内只用 execute/rowcount/lastrowid，读取走 fetch 辅助） |

**修复项**：
- **H1（高，R2 资金安全）**：同订单并发申请无 DB 级防重，CHECK-THEN-INSERT 非原子 → 可能双 pending 双退款。修复：事务内 `SELECT id FROM order WHERE id=%s FOR UPDATE` 锁订单行串行化并发，锁内重查 pending 后再插入或复用。已加 8 并发测试实证。
- **分位容忍**（R1 边界）：金额比较加 `1e-6`，避免浮点等额误拒。

**评审判定为可接受/记录**：
- approve 的 `approved_amount` 未做 ≤实付上限校验（管理员为可信角色，且 R1 已约束申请金额；task28 LangGraph 替换时可加）
- `student_id`/查询依赖 `order` 表 NOT NULL 约束（DB 层保证非空）
- reject 复用 `approved_at` 落拒绝时间（枚举/表无独立字段）

---

## 契约测试结果

| 套件 | 结果 |
|------|------|
| `tests/test_contract_task19.py` | **9/9 通过** |
| `tests/test_contract_task17.py` + `tests/test_contract_task18.py`（回归） | **12/12 通过**（payment 恢复 + 中间件改动无破坏） |
| 语法诊断（GetDiagnostics） | refund 全域 + rate_limit + main + tests 均 0 错误 |

---

## 验证命令
```bash
# 起服（限流宽松）
$env:EDUAGENT_RATE_LIMIT_DEFAULT="1000000"; $env:EDUAGENT_TRADE_PAYMENT_LIMIT="1000000"; $env:EDUAGENT_TRADE_ORDER_LIMIT="1000000"
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8003
.venv\Scripts\python -m pytest tests/test_contract_task19.py -v
```

## 关键经验留痕（排查项）
- **工作树曾被回滚**：task18 的 `payment/`、`main.py`、`rate_limit.py` 改动在开工时丢失，但 HEAD(060a20d) 仍在 → 从 HEAD 恢复，并在 main.py 一并补回 payment + 新增 refund。
- **`refund_status` 枚举无 cancelled**：用户撤销退款以软删 `yn=0` 表达（保留 refund_status），前端已撤销单不再出现在 pending/有效列表。
- **资金安全 H1**：同订单退款幂等需 DB 级串行化（FOR UPDATE），仅靠唯一键/先查后插不够。