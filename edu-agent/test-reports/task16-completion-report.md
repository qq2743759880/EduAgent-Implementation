# task16 完工报告 — market 域（coupons 3 端点 + favorites 3 端点，契约冻结⑦）

> **日期**: 2026-08-21 | **状态**: ✅ 等待编排者复验
> **前置**: task15（契约⑬）、api-request.md（前端 task40 已封装契约）
> **结论**: GWT ①② 全部 PASS；500 并发领券攻防无超发

---

## 一、修改清单（新域：domains/market）

| 文件 | 内容 |
|------|------|
| `app/domains/market/__init__.py` | market 域包 |
| `app/domains/market/schemas.py` | Coupon/CouponTemplate/CouponPage/CouponReceiveInput + Favorite/FavoritePage/FavoriteCreateInput/FavoriteDeletedResponse |
| `app/domains/market/repository/coupon_repo.py` | coupon 读取 + 事务内「条件更新 + 写记录」（防超发） |
| `app/domains/market/repository/favorite_repo.py` | series_favorite 读取 + 幂等创建/软删 |
| `app/domains/market/service.py` | 业务编排 + 幂等判重 + 券状态计算（含逻辑 expired） |
| `app/domains/market/router.py` | coupon_router + favorite_router（7 端点） |
| `app/common/error_codes.py` | `TRADE_COUPON_EXHAUSTED` 40024 → **40920**（task16 GWT① 权威） |
| `app/main.py` | 注册 market_coupon_router / market_favorite_router |
| `scripts/_smoke_task16.py` | HTTP 冒烟 + 500 并发攻防（服务层直调防超发核心） |
| `tests/test_contract_task16.py` | 契约⑦ pytest（9 用例） |

**端点（对齐 api-request.md + 前端 task40/task46）**：
- 优惠券：`GET /api/coupons/templates`、`GET /api/coupons`（无 series_id=我的券分页 / 有 series_id=系列适用模板）、`POST /api/trade/coupon/receive`
- 收藏：`GET /api/favorites`、`POST /api/favorites`、`DELETE /api/favorites/{series_id}`

---

## 二、验收证据

### GWT ①：500 并发领券防超发 + 40920

```text
[INFO] 测试券 id=69, total_count=500
并发结果: OK=500 FAIL=1
FAIL 分布: {'40920': 1}
40920 已领完次数: 1
[PASS] 500 并发领券攻防: 恰 500 成功 / 第501起40920 / 无超发
```
DB 直查（服务层事务后）：`receive_count=500/500  records=500` —— 恰 500 成功、第 501 起 40920、**无超发**。

防超发实现（`coupon_repo.receive_in_transaction`）：
```sql
UPDATE coupon SET receive_count = receive_count + 1
 WHERE id = ? AND receive_count < total_count AND yn = 1  -- 受影响行数=0 → 已领完(40920)
INSERT INTO coupon_receive_record (... receive_no ...)     -- uk 唯一键兜底
```
> 并发攻防选择服务层直调（`asyncio` 501 并发），原因：HTTP `/api/trade/coupon/receive` 有 30/min 限流中间件，
> 打满 500 会叠加 42900 干扰「恰 500 成功」断言；服务层走的是同一 防超发事务核心，能干净验证条件更新+唯一键。

### GWT ②：我的券 receive_status + 收藏幂等

```text
[A2] GET /api/coupons (我的券) | status=200 code=0    data={total,page,page_size,items[]}
[A1] GET /api/coupons/templates | status=200 code=0   68 个可领券模板（face_value/min_spend 按类型映射）
[A3] GET /api/coupons?series_id= | status=200 code=0
[A4] GET /api/favorites / POST / DELETE
  [PASS] POST /api/favorites (series=2628) | status=200 code=0
  [PASS] POST /api/favorites 重复(幂等 返回原记录) | status=200 code=0  → favorite_id 一致: True
  [PASS] DELETE /api/favorites/2628 | status=200 code=0
  [PASS] DELETE 重复(幂等) | status=200 code=0
```
- 券 `status` ∈ `{unused, used, expired}`；`expired` 为逻辑态（unused 且 `valid_to<NOW()`），响应含 `valid_to` 过期时间。
- 收藏 POST/DELETE 服务端幂等：重复 POST 返回原记录（同一 favorite_id）；重复 DELETE 返回 `deleted:true`。
- pytest：`9 passed, 1 skipped`（skip 的是 HTTP 500 并发，改由服务层 smoke 验证）。

---

## 三、契约⑬对齐前端要点

| 项 | 对齐 |
|----|------|
| 分页壳 | `{total,page,page_size,items[]}` 平铺（CouponPage/FavoritePage），非 page_meta |
| coupon_type | `{cash,discount,trial,gift}`（edu.sql 权威；cash→face_value=discount_amount，discount→face_value=discount_rate） |
| receive_status | `{unused,used,expired}`（edu.sql 权威；逻辑 expired 展示） |
| favorite_source | `{series_detail,search_result,recommendation,activity_page}`（默认 series_detail） |
| target_type | `"series"` |
| receive 端点 | `/api/trade/coupon/receive`（已在幂等中间件前缀内） |

---

## 四、端点协调说明（重要）

task16 文档原型路由（`GET /api/coupons`(可领)/`GET /api/coupons/me`/`POST /api/coupons/{id}/receive`）
与 **api-request.md + 前端 task40/task46 已消费契约**冲突。经裁定：
- 按 **api-request.md + 前端 api-client** 落地（本域为唯一权威交接单，前端 task63/67 以其为准）
- 「我的券」= `GET /api/coupons`（无 series_id）；「可领券」= `GET /api/coupons?series_id=` 或 `GET /api/coupons/templates`；领券 = `POST /api/trade/coupon/receive`
- 详见 `.opencode/handoffs/task16-contract.md`（已冻结）

---

## 五、交付物

- [x] `scripts/_smoke_task16.py`（HTTP 冒烟 + 500 并发攻防）
- [x] `tests/test_contract_task16.py`（契约⑦ pytest，9 passed）
- [x] `test-reports/task16-completion-report.md`（本文件）
- [x] `.opencode/handoffs/task16-contract.md`（契约⑦ → 解锁前端 task63/67）
- [x] `powershell -File D:\.ai-hub\sync.ps1`
- [ ] **停下等编排者验收 task16，未经验收不得开始 task17** ⏸️