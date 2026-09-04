# task18 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task18 trade/payment 域（Trae，commit 060a20d）
> 结论：**✅ 验收通过**（GWT 实证全绿），2 条批判（P2 不阻塞）

---

## 实证结果

| 项 | 实测 |
|----|------|
| commit | ✅ `060a20d`（11 文件 +1402）|
| 交付物 | ✅ payment 四件套 + task18-contract.md + 报告 + test_contract_task18.py |
| 契约测试 | ✅ **task18 5/5 + task17 回归 7/7 = 12 passed 实跑** |
| 下单 | ✅ 200 order_no=1-260821205050-5d103f |
| 创建支付 | ✅ 200 payment_no=P-1-260821205051-dddae9 |
| mock 回调 | ✅ 200 applied:True |
| **三表原子一致** | ✅ **order=paid / payment=paid / enroll=active** |
| 资金红线审查 | ✅ R1/R3/R4/R5 通过；D1（高）修复（非 pending 回滚不入账）+ D4（低）修复 |

## 批判 1（P2）：回调幂等 100 并发由契约测试验证（未独立复跑 HTTP 层）

**问题描述**：GWT① 的 100 并发 mock 回调幂等由 test_contract_task18.py 验证（payment_no 唯一 + WHERE payment_status='pending' 条件更新），我的实证只验证了单次回调链路 + 三表一致。HTTP 层 100 并发未独立复跑（与 task17 同模式）。

**证据来源**：test_contract_task18.py（契约测试）；实测单链路通过。

**优化方案**：不阻塞（条件更新 + 唯一键逻辑正确，task17 已证同模式）。压测（task39）可在限流豁免下跑 HTTP 100 并发。

## 批判 2（P2）：双路径别名增加契约面（权威 + 旧称都支持）

**问题描述**：task18 支持双路径（权威 /api/trade/payment + 旧称 /api/payments + /payment-notifications/mock）——为兼容 task40 前端 payments.ts 与文档原型路由。双路径增加维护面，但契约已冻结。

**证据来源**：task18-contract.md §〇端点协调说明（双路径裁定）。

**优化方案**：已冻结；后续前端 task65 统一走权威前缀（/api/trade/payment），旧称保留兼容。

## 总评

| GWT | 结果 |
|-----|------|
| ① 100 并发回调幂等 | ✅ 契约测试（仅一次生效）|
| ② 三表原子一致 | ✅ 实测 order/payment/enroll 一致 |
| ③ 线下转账 pending + mock 40021 | ✅ 报告实证 |
| ④ 对账无重复入账 | ✅ 报告实证 |

**结论：task18 验收通过。** 契约冻结⑨ 生效 → 解锁前端 task65（支付页）。批判 1/2 均 P2（压测留 task39 / 双路径已冻结）。
