# task16 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task16 market 域（coupons+favorites，Trae，commit c447724）
> 结论：**✅ 验收通过**（GWT 实证全绿），2 条批判（P2 不阻塞）

---

## 实证结果

| 项 | 实测 |
|----|------|
| commit | ✅ `c447724`（13 文件 +1240）|
| 交付物 | ✅ domains/market + task16-contract.md + 报告 + 测试 |
| error_codes | ✅ `TRADE_COUPON_EXHAUSTED = "40920"` |
| 防超发核心 | ✅ repo 条件更新 `receive_count=receive_count+1 WHERE id=? AND receive_count<total_count` + receive_no 唯一键 |
| 领券 | ✅ 200 + code=0 + coupon_id=51001 落库 |
| 我的券 | ✅ 200 + 壳 |
| **收藏幂等** | ✅ 重复 POST 返回相同 fav_id=30010 |
| favorites 列表 | ✅ 200 |
| 500 并发防超发 | ✅ 报告 smoke：恰 500 成功 + 1 个 40920，DB receive_count=500/500，无超发 |

## 批判 1（P2）：500 并发攻防由服务层 smoke 验证（非 HTTP 层）

**问题描述**：GWT① 的 500 并发防超发由 `_smoke_task16.py` 服务层验证（因 HTTP 层 30/min 限流无法 500 并发），报告提供 DB receive_count=500/500 实证。HTTP 层并发未直接验证（受限流限制），但服务层条件更新 + 唯一键逻辑正确。

**证据来源**：报告 §验收（500 并发 → 500 成功 + 1×40920，DB 500/500）；pytest 1 skipped 说明。

**优化方案**：不阻塞（服务层已证）。未来压测（task39）可在 Redis 限流豁免下做 HTTP 层 500 并发。

## 批判 2（P2）：task16 文档原型路由与 api-request.md 冲突，已按 api-request.md 落地

**问题描述**：task16 文档原型路由（GET /api/coupons 等）与 api-request.md + 前端 task40/46 已消费契约冲突——Trae 按 **api-request.md + 前端 api-client** 落地（我的券=GET /api/coupons 无 series_id；可领=?series_id= 或 /templates；领券=POST /api/trade/coupon/receive），并在交接单明确冻结。这是**正确的契约对齐**（前端先消费，后端跟前端），但 task16 文档未同步更新路由说明。

**证据来源**：task16 报告 §契约协调说明；api-request.md §3/4。

**优化方案**：task16-contract.md 已冻结正确路由；task16 任务文档路由说明建议更新（不阻塞，已由交接单权威覆盖）。

## 总评

| GWT | 结果 |
|-----|------|
| ① 500 并发防超发（无超发）| ✅ 条件更新 + 唯一键 + DB 500/500 实证 |
| ② /api/coupons/me 按 receive_status + 收藏幂等 | ✅ 我的券 200 + 收藏幂等 fav_id 一致 |

**结论：task16 验收通过。** 契约冻结⑦ 生效 → 解锁前端 task63/67（coupons/favorites 页）。批判 1/2 均 P2（压测 HTTP 层留 task39 / 文档路由已由交接单权威覆盖）。
