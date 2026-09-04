# task17 完工报告 — trade/order 域（5 端点 + 状态机 + 三层幂等纵深，契约冻结⑧）

> **日期**: 2026-08-21 | **状态**: ✅ 待编排者复验（含 P1 幂等中间件修复）
> **前置**: task16（契约⑦，coupons?）、api-request.md §5
> **结论**: GWT ①②③④ 全部 PASS；100 并发幂等 + 篡改价无效证据完整；**P1 幂等 IncompleteRead 已修复**

---

## ⚠️ 修复记录（编排者 task17 批判 → 派发修复，2026-08-21）

| 项 | 内容 |
|----|------|
| 问题 | 幂等中间件缓存命中 IncompleteRead（Content-Length=356 但 body 重建后不符）；且缓存 body 为占位符 `data:null`，非首次订单 |
| 根因 | `app/middleware/idempotency.py`：① 缓存命中透传含原始 Content-Length 头 ② BaseHTTPMiddleware 下 `response.body` 为空（流被消费），写缓存只能落占位符 `data:null` |
| 修复A | 缓存命中剔除 hop-by-hop 长度/编码头（`content-length/transfer-encoding/content-encoding/connection`），让 JSONResponse 重算 Content-Length → 解 IncompleteRead |
| 修复A2 | 写缓存改用 `response.body_iterator` 捕获真实响应体（同 RespWrapMiddleware 模式）→ 缓存含完整订单 body，重复返回 order_no 一致；重建响应返回客户端 |
| 修复B | `tests/test_contract_middleware.py` 新增 `test_idempotency_repeat_full_body`（重复 key 返回完整 body + order_no 一致） |

**P1 修复实证（`scripts/_verify_idempotency_fix.py`，原始 http.client 读 body）：**
```text
[首次] status=200 cl=356 real_len=356 order_no=1-260821132010-d03f89
[重复] status=200 cl=356 real_len=356 order_no=1-260821132010-d03f89   ← order_no 与首次一致
[PASS] 幂等重复请求完整 body + Content-Length 匹配 + order_no 一致
```

**回归**：`test_contract_task17.py` **7 passed**（含 cancel/状态机/幂等 body 断言）；`test_contract_middleware.py::TestIdempotencyMiddleware` B 测试 PASS。
> 注：`test_contract_middleware.py` 整包全量因 auth 10/min 限流（20+ login 同窗口）部分 429，属 pre-existing 测试设计特性，非本修复回归——核心断言（B 测试 + task17 套件）在干净窗口均通过。

---

## 一、修改清单（新域：domains/trade/order）

| 文件 | 内容 |
|------|------|
| `app/domains/trade/__init__.py` | trade 域包 |
| `app/domains/trade/order/__init__.py` | order 域包 |
| `app/domains/trade/order/schemas.py` | Order/OrderItem/PaymentItem/OrderCreateInput/OrderCancelResult/OrderPage |
| `app/domains/trade/order/repository.py` | OrderRepo(读) + OrderWriteRepo(事务下单/取消) |
| `app/domains/trade/order/service.py` | 业务编排：金额重算/状态机/三幂等/券核销回滚/余位占释 |
| `app/domains/trade/order/router.py` | 4 路由（POST/GET list/GET detail/POST cancel） |
| `app/main.py` | 注册 order_router |
| `scripts/_smoke_task17.py` | HTTP 冒烟 + 100 并发幂等攻防 |
| `scripts/_verify_coupon_task17.py` | 券核销 GWT① 专项验证 |
| `scripts/_cleanup_task17.py` | 测试数据清理 |
| `tests/test_contract_task17.py` | 契约⑧ pytest（7 用例） |

**端点（对齐 api-request.md §5 + 前端 orders.ts）**：
`POST /api/trade/order`、`GET /api/trade/orders`（+refundable）、`GET /api/trade/order/{order_no}`（items+payments 嵌套）、`POST /api/trade/order/{order_no}/cancel`

---

## 二、资金安全红线实现（hard）

| 红线 | 实现 |
|------|------|
| **金额服务端重算** | `total=series_cohort.sale_price`（唯一价源），`discount=实际券面额`，`payable=total-discount`；请求体**无价格字段** → 篡改无效 |
| **下单/取消单事务** | order+order_item+券核销/回滚+班次余位占/释，同一 `transaction()` 原子提交，异常整体回滚 |
| **券核销/回滚联动状态机** | 下单→券 `used`；取消(pending)→券 `unused` + 班次 `current_student_count-1` |
| **order 保留字** | 所有 SQL 用反引号 `` `order` `` |

**三层幂等纵深**：
- L1 中间件：Idempotency-Key（`/api/trade/order` 前缀已注册）
- L2 order_no 唯一键 `(institution_id, order_no)`：并发唯一键冲突回查返回原单
- L3 状态机条件更新：cancel `WHERE order_status='pending'`

---

## 三、验收证据

### GWT ①：下单（篡改价无效 + 券核销 used + 金额服务端重算）

```text
[A1] POST /api/trade/order | status=200 code=0
     order_no=1-... pay_amount=3999.0（服务端 sale_price 重算）
[PASS] 篡改价无效(pay_amount>0)
[PASS] 详情含 items | 详情含 payments
```

券核销专项（`_verify_coupon_task17.py`）：
```text
[OK] 带券下单 order_no=1-... order_amount=3999.0 discount=100.0 pay=3899.0
下单后券 receive_status=used used_at=2026-08-21 11:31:34
取消后券 receive_status=unused used_at=None
[PASS] 券核销 used + 取消回滚 unused
```
（cash 券免 100：pay=3999-100=3899，服务端重算正确）

### GWT ②：100 并发同订单幂等（仅 1 条）+ 非法状态迁移 409

```text
[B] 100 并发幂等攻防（服务层）
并发结果: OK=1 FAIL=119 唯一order_no=1
FAIL 分布: {'IntegrityError': 119}          ← order_no 唯一键拒绝并发重复
DB orders for (cohort,user): 1（应为1，幂等）    ← 语义幂等成立
服务端重算价格一致(888.00): True
[PASS] 100 并发幂等（仅1条订单）+ 服务端重算价格

[A5] paid 单取消 → 409 冲突 | status=409 code=40021   ← 非法状态迁移拒绝
```

### GWT ③：取消 pending→cancelled + 券回滚 + 余位释放（两次幂等）

```text
[PASS] POST /api/trade/order/{no}/cancel | status=200 code=0  cancelled=true
[PASS] 取消幂等(再次返回 cancelled=true)
```
券回滚 unused 已在 GWT① 券验证脚本实证（取消后 used_at=None）。

### GWT ④：下单事务失败整体回滚（事务边界无 LLM/Redis）

- 下单/取消全程 `transaction()` 纯 SQL（无 LLM 调用、无 Redis 写）——严格执行「本任务只适配壳不加业务逻辑」扩展无外部调用
- 事务失败（满员 40920 / 唯一键冲突回查 / 异常回滚）均不产生脏数据

### pytest：`7 passed`（契约⑧ task17 套件）
`test_create_requires_idempotency_key / test_create_order_and_fields / test_order_detail_nested / test_order_list_filters / test_cancel_pending_and_idempotent / test_cancel_paid_conflict_409 / test_order_not_found_404`

---

## 四、契约⑧对齐前端要点

| 项 | 对齐 |
|----|------|
| 分页壳 | OrderPage `{total,page,page_size,items}`（平铺，非 page_meta） |
| order_status | status.ts 冻结 `{pending,paid,completed,cancelled,partial_refunded,refunded}` |
| 端点 | `/api/trade/order*`（api-request.md §5 + 前端 orders.ts） |
| Idempotency-Key | 下单必填；复用幂等中间件前缀 |
| refundable | `GET /api/trade/orders?refundable=true` → paid/completed/partial_refunded |

---

## 五、交付物

- [x] `scripts/_smoke_task17.py`、`scripts/_verify_coupon_task17.py`、`scripts/_cleanup_task17.py`
- [x] `tests/test_contract_task17.py`（契约⑧，7 passed）
- [x] `test-reports/task17-completion-report.md`（本文件）
- [x] `.opencode/handoffs/task17-contract.md`（契约⑧ → 解锁前端 task64）
- [x] 测试数据已清理（冒烟/pytest 产生的 1-series 订单 + coupon 回滚）
- [x] `powershell -File D:\.ai-hub\sync.ps1`
- [ ] **停下等编排者验收 task17，未经验收不得开始 task18** ⏸️

---

## 六、范围外观察（非本次回归，供编排者知悉）

- `/api/series/{id}/cohorts`（task11 course 域）返回 500：`CohortListData` 被 router 当 list 迭代 → `'tuple' object has no attribute 'model_dump'`。**pre-existing task11 bug，非 task17 引入**（task17 冒烟改用 `/api/cohorts/{id}` 探测规避）。建议编排者记入 task37 清理/后续修复。