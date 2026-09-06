# task05 完成报告：coupons.html 优惠券+下单真实闭环（reshape-a）

- 日期：2026-09-06
- 执行：fe-html 接线独立 agent（task05）
- 范围：`edu-frontend/public/coupons.html`（仅此一文件改动，未触碰 course-detail.html，理由见"改动清单"末尾）
- 服务：8000/3000 未重启（遵守禁令），全部验证走真实 HTTP

---

## 1. 下单链路补验（决策点①）——结论：**通过**

后端只读核查（未改任何后端文件）：

- `edu-agent/app/domains/market/router.py`：GET `/api/coupons`（我的券分页/系列模板二合一）、GET `/api/coupons/templates`（可领模板）、POST `/api/trade/coupon/receive`
- `edu-agent/app/domains/trade/order/router.py`：POST `/api/trade/order`（**Idempotency-Key 头必填**）、GET `/api/trade/orders`、GET `/api/trade/order/{order_no}`、POST cancel
- 错误码：`error_codes.py` L80-85 → 40420 订单不存在 / 40021 状态&缺幂等头 / 40023 券过期/已用/门槛 / 40920 券已领完&班次满员

### curl 实测证据（user000001 / Test@123456，真实库）

| # | 请求 | 实测响应（摘要） |
|---|------|------|
| 1 | `GET /api/coupons?page=1&page_size=5` | `code:0`，data `{total:101,page:1,page_size:5,items:[{coupon_id:51121,coupon_template_id:71,coupon_name:"平台通用解锁券·减10000",coupon_type:"cash",face_value:10000.0,min_spend:0.0,status:"used",valid_from,valid_to,received_at,used_at,order_no}]}` |
| 2 | `GET /api/coupons/templates` | `code:0`，data **裸数组**：`[{coupon_template_id:1,coupon_name:"平台满减券01",coupon_type:"cash",face_value:100.0,min_spend:500.0,valid_from,valid_to,total_count:1000,received_count:737,per_user_limit:1}, ...]` |
| 3 | `POST /api/trade/coupon/receive` body `{"coupon_template_id":1}`（重复领取） | `code:0`，data 与原记录**同一 coupon_id=51001**（received_at 2026-08-21，服务端幂等返回原券记录，**非错误码**） |
| 4 | `GET /api/series?page=1&page_size=5` | `code:0`，total 2628，items `{id:2628,series_name:"信息学竞赛入门班·录播",sale_status:"on_sale",min_price:"1999.00"}` |
| 5 | `GET /api/series/2628/cohorts` | `code:0`，分页壳 `{total:3,...}`，items `{id:7884,cohort_code:"COH00262803",cohort_name:"信息学竞赛入门班·录播 202610期",sale_price:"1999.00",max_student_count:50,current_student_count:0,yn:1,start_date:"2026-10-02"}` |
| 6 | `POST /api/trade/order`（头 `Idempotency-Key: task05-verify-20260906-a1`，body `{"series_id":2628,"cohort_id":7884,"coupon_id":51001}`） | `code:0`，**订单号 `6-260906172441-86dcaa`**，order_amount 1999.0 / discount_amount 100.0 / pay_amount 1899.0 / coupon_id 51001 / status "pending"（券 51001 门槛 500≤1999，现金券抵 100，服务端重算） |
| 7 | `GET /api/trade/orders?page=1&page_size=3` | `code:0`，total 20，首条即上述订单 `{order_no:"6-260906172441-86dcaa",series_title:"信息学竞赛入门班·录播",cohort_id:7884,pay_amount:1899.0,status:"pending",coupon_id:51001}`；券 51001 同步出现在 `GET /api/coupons?status=used` |
| 8 | `POST /api/trade/order`（**不带** Idempotency-Key） | `code:"40021"`，message `"缺少 Idempotency-Key 请求头（下单必须幂等）"`，data null |
| 9 | 全量持券快照（2 页共 101 条）后 `POST receive {coupon_template_id:2}`（**未持有**） | 新记录 **coupon_id=51122**，received_at=2026-09-06T17:38:57（即时）→ 立即出现在 `?status=unused` 页；再 POST 一次 → 返回同一 51122，code 0（幂等复证） |

测试数据留痕：订单 `6-260906172441-86dcaa`（pending，未支付）；新券记录 51122（模板 2，unused）。

### 契约-计划偏差（按 AGENTS.md 教训 8"真实契约优先"，不 MOCK 不臆造）

1. **重复领取不是错误码**：计划 GWT 预期"重复领取按错误码提示"；实测服务端幂等返回 code=0 + 原券记录（market/service.py L120-123 幂等判重）。前端按真实契约实现：领取前取已持券快照 → 重复时诚实提示"该券已领取过：服务端幂等返回原券记录 #id"；错误路径仅剩真实错误码（40920 已领完等，由 EAPI 全局 toast 展示服务端原文）。
2. **EAPI.post 不支持自定义请求头**，而下单必须 `Idempotency-Key`：edu-api.js 属禁改文件 → 在 coupons.html 内实现局部 `postWithHeaders()`（shell 解包/401 语义与 EAPI.parseResponse 对齐，401 走 `EAPI.logout()`）。**edu-api.js 未改动一行**。

缺口上报：**无**（所有端点存在、字段与契约一致）。

---

## 2. 改动清单（全部在 `edu-frontend/public/coupons.html`，50428 bytes）

1. **顶部契约注释重写**：补录 templates/receive/order/orders/series/cohorts 七个端点的实测字段、幂等语义、错误码、face_value 语义、`postWithHeaders` 实现注（静态页顶部注释=接口契约来源）。
2. **领券中心新区块**（页头下、我的券上）：`GET /api/coupons/templates` 真实渲染（类型/面值/门槛/有效期/剩余张数/限领）；三态齐全（骨架 shimmer/空态/错误态+重试）；已领完（received≥total）与已过期模板按钮禁用态诚实；领取按钮真实 `POST /api/trade/coupon/receive`，成功→绿色 toast（含 coupon_id）+ `cp:refresh` 事件刷新我的券 tab/角标 + 静默重拉模板（received_count 更新）；重复领取按快照诚实提示；领取失败还原按钮（错误文案由 EAPI 全局 toast 承担，避免双 toast）。
3. **我的优惠券卡片**：`status==="unused"` 卡片新增"去下单使用"按钮 → 打开下单弹窗（携带整张券上下文）。
4. **下单弹窗（四步状态机）**：
   - step1 选课程系列：`GET /api/series`（keyword 搜索 + 分页，仅渲染 `sale_status==="on_sale"`），三态（mini 骨架/空态/错误态+重试）
   - step2 选班次：`GET /api/series/{id}/cohorts`（yn=1，余位=max-current，满员禁用"已满员"），三态同上
   - step3 确认+提交：系列/班次/价格/券抵扣预估/预估实付行；**未达 min_spend → 警示 + 提交禁用**；预估注"以下单接口服务端核算为准"；提交 `POST /api/trade/order`（Idempotency-Key 每次打开弹窗生成、同会话重试复用 + submitting 防重复提交），错误→弹窗内 err 态（服务端 message + 错误码）
   - step4 成功：🎉 + **真实订单号**（order_no 大字）+ 金额/券抵扣/实付/状态行 + "查看我的订单"（me.html 入口）+ 完成（关闭后列表已静默刷新，券移入"已使用"）
5. **我的订单入口**：页头右上 "🧾 我的订单（个人中心）" → `me.html`（me.html 归 task10，不越界，只做入口跳转）。
6. **主 IIFE 最小触点**：仅 2 处——unused 卡片按钮挂接（经 `window.couponsOrder.open`）、`cp:refresh` 事件监听（静默 reload 当前 tab）。原列表/分页/三态逻辑未动。
7. **视觉 token 零改动**：新增样式全部复用页面既有 `:root` token（candy 色板/3D 阴影/圆角/边框），无新 hex。

**未改 course-detail.html 的理由**：该页仍为 task46 效果图（mock 数据 + alert 演示态），属 task04 所有者正在接线的文件；本任务下单入口已在 coupons.html 内自闭环（选系列→选班次→下单），无需跨界改动，避免并行冲突。

---

## 3. 资产消费证据

- `contracts/reshape-a.json`（hash 30aeddbe…，冻结 2026-09-06）：消费 `GET /api/coupons`、`POST /api/trade/coupon/receive` 两个冻结端点；下单/订单端点不在冻结清单 endpoints 内 → 按 authority 字段指引回溯源 `edu-agent/app/schemas.py`（OrderCreateInput/Order）+ 只读 router 源码 + curl 实测补齐，未偏离响应壳 `{code,message,data}` 与分页壳 `{total,page,page_size,items}`。
- `.ai-hub/plans/dev-plan-reshape-a.md` task05 GWT：领券→下单→订单可见全链路真实库操作 ✓；"下单链路先 curl 补验再接前端（决策点①）" ✓（本报告 §1）。
- `edu-frontend/public/edu-api.js` 头部注释（task101-122 加固契约）：401 语义、错误钩子 toast、`EAPI.pageId`、禁静默 null——本页遵守；因自定义头需求走页内 postWithHeaders（edu-api.js 头注明确 chat SSE 亦有页面原生 fetch 先例）。
- 页面原顶部注释（curl 2026-09-05 契约）+ `market/schemas.py` CouponTemplate/Coupon/CouponReceiveInput + `trade/order/schemas.py` OrderCreateInput/Order：字段一一对应（coupon_id=领券记录 id 语义已在schemas 注释与实测 ⑥ 中闭环）。

---

## 4. 批判承接核对

无承接项（本任务无前置批判报告挂账的 task05 专属缺陷；`critique-backlog-tracker.md` 中无 task05 条目）。

---

## 5. 三视角自检

**Eng（工程）**：
- 禁改边界遵守：后端 0 改动（只读）、contracts/edu-api.js 0 改动、未重启服务；`git status` 确认仅 coupons.html 变更待提交。
- 禁 mock/alert/`.match(` 正则：全文 grep 0 命中（4 个 inline script `new Function` 语法校验全过）；取参一律 encodeURIComponent/URLSearchParams 语义（本次无 query 取参需求）。
- 幂等与并发：Idempotency-Key 弹窗会话内复用 + submitting 防重复提交 + 提交中禁关弹窗；cp:refresh 事件解耦两 IIFE（无全局污染，仅 `window.couponsOrder` 一个挂点）。
- 已知边界（诚实登记）：held 快照预取失败时退化为无法预判重复（POST 本身幂等，服务端仍返回原记录，提示口径退为"领取成功"）；postWithHeaders 无 EAPI 的单飞 refresh 重放（401 直接 logout 跳登录）。

**Design（体验）**：
- 三态齐全：领券区（骨架/空/错误+重试）、弹窗每个加载步骤（mini 骨架/空/错误+重试）、确认页门槛警示与禁用态、成功页。
- 视觉 token 冻结：仅复用 candy token，券卡/按钮/弹窗与既有 cp-card/state 体系同族；不重定义全局 `$`/`renderSides`；未动既有 tab/分页 DOM。
- 可达性：弹窗 role=dialog+aria-modal、关闭钮 aria-label、领取钮 aria-label 带券名、cp:toast role=status；提交中按钮禁用文案"提交中…"。

**QA（独立实证）**：
- 真实 HTTP 实证 9 组请求/响应（§1 表），含正向（下单成功+订单可见+券核销联动）、负向（缺幂等头 40021）、幂等（重复领取同 coupon_id）三面。
- 3000 静态服务 `GET /coupons.html → 200`，新标记（tplStage/omOverlay/postWithHeaders）18 处命中；重复 id 检查 0 命中。
- 无 Playwright（遵守禁令）；DOM 交互层以 Node `new Function` 语法门 + 结构标记断言代替，页面数据链路全部由 curl 等价复放覆盖。
