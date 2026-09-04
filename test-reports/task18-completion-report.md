# task18-completion-report · 后端 trade/payment 支付域（契约冻结⑨）

> 类型：backend + database ｜ 阶段：P4/W2 ｜ 执行：TraeCode 手动调度（dev-standard 8 阶段）
> 契约依据：`.opencode/handoffs/api-request.md §6`（前端已封装 Payment/PaymentLaunchResult）+ `plans/tasks/task18-trade-payment.md`
> 状态：**待编排者验收**（未经验收不开始 task19）

---

## 交付范围

- **8 端点**（支付发起/详情轮询/回调/分页查询/取消/重试/对账）×2 路径前缀（权威 `/api/trade/payment` + 双路径别名 `/api/payments`）,另加独立回调 `/payment-notifications/mock`
- **渠道枚举**：`wechat_palipay/bank_card/offline_transfer/public_account/campus_cashier`（edu.sql 权威）+ `mock`（模拟渠道）；唯一键 `(institution_id, payment_no)`；状态机 `pending→paid/closed/failed→closed/paid…`（edu.sql 枚举）
- **回调成功单事务**：payment paid + order paid + student_cohort_rel active + 券 used（报名联动，薄弱点 W2 攻防）
- **支付回调幂等**：payment_no 唯一键 + `WHERE payment_status='pending'` 条件更新
- **对账**：只读报告校验重复入账 / 金额不一致

## 新增/修改文件

| 文件 | 说明 |
|------|------|
| `edu-agent/app/domains/trade/payment/{schemas,repository,service,router}.py` | 支付域四件套 |
| `edu-agent/app/main.py` | 注册 payment_router |
| `edu-agent/app/middleware/rate_limit.py` | `/api/trade/payment` 与 default 限流阈值改环境变量可覆写（测试/压测用，默认值不变） |
| `edu-agent/tests/test_contract_task18.py` | task18 HTTP 契约测试（并发攻防 + 原子一致 + 线下 + 对账 + 双路径） |
| `edu-agent/scripts/_verify_task18.py` | service 层资金安全 DB 校验（不含限流干扰） |

> 注：`app/common/rate_limit.py` 为未挂载的重复文件，未作改动（审查确认活跃中间件为 `app/middleware/rate_limit.py`）。

---

## 验收标准逐条对照（Given/When/Then）

### GWT① 100 并发回调仅一次生效
> Given 同一 payment_no 的 mock 回调 100 并发重试，When 全部到达，Then 仅一次生效（其余命中条件更新 0 行），order 只 paid 一次、报名只 active 一次、券只核销一次。

**实现**：`settle_payment`（repository.py）首步 `UPDATE payment_record SET payment_status='paid' WHERE payment_no=%s AND payment_status='pending'`；并发下 MySQL 行锁串行化，仅首个 pending 事务 `rowcount=1` 生效并进入联动，其余 `rowcount=0` 回滚返回 `applied=False`。报名与券均用唯一键/条件更新幂等。

**实测证据（HTTP 层 100 并发）**：`test_100_concurrent_mock_callback_once` PASS——应用次数=1；DB 复核 `payment_status='paid'` 1 笔、order `paid` 1 笔、`student_cohort_rel.enroll_status='active'` 1 行；再次回调 `applied=False`（幂等复核）。

**实测证据（service 层，绕过限流）**：`_verify_task18.py GWT①`
```
100 并发回调 → applied 次数 = 1（期望 1）
payment paid 次数=1, order paid 次数=1, 报名 active 次数=1（均期望 1）
幂等复核：再次回调 applied=False [OK]
student_cohort_rel(68805).order_item_id=80108 ← 指向本次支付 order_item（归属正确）
券核销：50 并发回调 → coupon_receive_record.receive_status='used'（仅一次）
```

### GWT② 支付成功三表原子一致
> Given 支付成功，When 查询订单与班次，Then order=paid、enroll_status=active、payment_status=paid 三者原子一致（单事务落库）。

**实现**：`settle_payment` 在同一 `transaction()` 内，同一 `conn/cur` 顺序执行 payment→paid、order→paid、enroll→active、券→used，任一异常 `transaction()` 统一回滚（database.py:482-484），无部分提交。

**实测证据**（service 层）：
```
[GWT②] payment=paid, order=paid, enroll=active（均期望 paid/paid/active）
```

### GWT③ 线下转账停留 pending + mock 仅限模拟渠道
> Given 线下转账渠道，When 用户选择，Then 状态停留 pending + 前端提示「到账审核中」，无即时回调；mock 回调仅限模拟渠道。

**实现**：`offline_transfer` 发起即回 `PaymentLaunchResult.audit_pending=True`、`status=pending`，不做即时状态变更；`mock_notify` 强制校验 `payment_channel in {'mock'}`，否则 `40021`。

**实测证据**：
```
[GWT③] offline 支付状态 = pending（期望 pending，无即时回调）
[GWT③] offline 渠道 mock 回调 → 40021（期望 40021 拒绝）
```

### GWT④ 对账任务无重复入账
> Given 对账任务运行，When 比对 payment_record 与订单，Then 无重复入账记录（对账报告）。

**实现**：`run_reconcile`（repository.py）纯只读 SELECT + 内存统计，不产生任何入账写操作；同订单 >1 笔 paid → `DUPLICATE_PAYMENT` 异常标记，金额不一致 → `AMOUNT_MISMATCH`；`anomalies==[]` 时 `ok=True`。

**实测证据**：`test_reconcile_no_duplicate` PASS（`ok=True`、含 `report_no`/`total_paid_payments`）。

### GWT⑤ 双路径别名等价
> Given 前端可能走旧称 `/api/payments` 或权威 `/api/trade/payment`，回调用 `/payment-notifications/mock`，When 调用，Then 两套路径等价可通。

**实测证据**：`test_alias_payments_and_mock_notify` PASS——`/api/payments/{order_no}` 发起、`/api/trade/payment/{payment_no}/mock-notify` 回调、`/api/payments/{payment_no}` 详情读取均 200，状态 paid。

---

## 资金安全红线核对（独立子代理 review，经修复）

红线审查（review-screener 逐条）：

| 红线 | 结论 |
|------|------|
| R1 回调幂等（payment_no 唯一 + 条件更新） | ✅ 通过 |
| R2 回调成功单事务（payment/order/enroll/券 原子一致） | ✅ **修复 D1 后通过**（见下） |
| R3 线下转账无即时回调、mock 仅限模拟渠道 | ✅ 通过 |
| R4 对账无重复入账 | ✅ 通过 |
| R5 事务内 raw cursor tuple→dict、金额服务端重算 | ✅ 通过 |

**审查发现并修复**：
- **D1（高，R2 原子性漏洞）**：原先 order 非 pending 时 `order_changed=False` 仅跳过联动但仍 commit → 可能 payment=paid 而订单未 paid（资金入账但业务失败）。修复：`order_changed==False` → 整笔 `rollback` 返回 `applied=False`（可重试），确保 payment 置 paid 与 order 置 paid 同成败。**已加 D1 回归测试通过**：`[D1] 回调 applied=False, payment_status=pending`（取消后不再入账）。
- **D4（低，幂等回查 audit_pending 用错渠道）**：改为以已有 pending 支付的实际渠道判定 `audit_pending`，避免二次用他渠道 launch 误报非线下。

**评审判定为可接受并记录（不做改动，避免过度设计）**：
- D2：多明细订单只联动首个 order_item——本应用订单为单班次单明细（task17 下单固定单 cohort），域约束已限定，交接单注明。
- D3：mock_notify 对唯一键冲突 catch 过宽——条件更新+ON DUPLICATE 正常不抛 1062，该分支仅为防御性兜底，风险低。
- D5：cancel 对 failed/closed 返回 `cancelled=True` 语义欠精确——非资金风险，记录。

---

## 契约测试结果

| 套件 | 结果 |
|------|------|
| `tests/test_contract_task18.py` | **5/5 通过** |
| `tests/test_contract_task17.py`（回归） | **7/7 通过** |
| `tests/test_contract_middleware.py`（TEST_BASE=8003 回归） | **14/16 通过**（2 项为 `/api/auth/login` 10/min 限流竞争导致，非本任务改动） |
| 语法诊断（GetDiagnostics） | 全 payment 域 + rate_limit + main + tests + scripts 均 0 错误 |

> 附注：`test_contract_middleware.py` 默认连 8000（未起服），已用 `TEST_BASE=http://127.0.0.1:8003` 复跑确认响应壳/中间件契约不受影响；2 项 auth 失败系多次测试累计触发登录限流（10/min），与本任务改动无关。

---

## 验证命令

```bash
# 服务层资金安全校验（100 并发 + 原子一致 + 线下 + 券 + D1 回归）
.venv\Scripts\python scripts\_verify_task18.py        # 全部通过 [OK]

# HTTP 契约（需先起服，建议限流宽松）
$env:EDUAGENT_RATE_LIMIT_DEFAULT="1000000"
$env:EDUAGENT_TRADE_PAYMENT_LIMIT="1000000"
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8003
.venv\Scripts\python -m pytest tests/test_contract_task18.py -v
```

## 关键经验留痕（task12/14/16/17 → task18）
- repo SQL 逐表对照 edu.sql：`order` 保留字用反引号、`paid_amount` 列存在、payment_record 唯一键 `(institution_id, payment_no)`。
- 事务内 raw asyncmy cursor `fetchone()` 返回 **tuple**，需 `dict(zip([d[0] for d in cur.description], row))` 转 dict（首次并发即暴露 TypeError）。
- 幂等用唯一键 + 条件更新，100 并发实测。
- 契约对齐 api-request.md §6 + 双路径别名兜底旧称。
- 中间件改动（rate_limit env 覆写）后复跑契约套件（task17 教训⑤）。

> 说明：`scripts/_task18_result.txt` 由 `_verify_task18.py` 生成，为资金安全校验的机器可读留痕。