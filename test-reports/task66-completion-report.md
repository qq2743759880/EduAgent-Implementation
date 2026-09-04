# task66 前端退款页（refund.html）完工报告 · 真实契约版

> 交付物：`edu-frontend/public/refund.html`（新增，单文件，内联 JS + CSS，无新依赖）
> 对接真实后端 8000，全程无 MOCK（仅一个已标记的静态降级角标）。不 commit。

---

## 1. 资产消费证据段 + agent×skill×workflow 矩阵

### 资产消费证据（开工前必读资产已全部消费）

| 资产（路径） | 消费动作 | 自检发现并落实 |
|---|---|---|
| `C:\Users\Administrator\.agents\skills\ponytail` | 按"梯子"最小化：不新引依赖、不复用不了既有组件、不建抽象基类，单文件自包含 | 只新建 1 个 `refund.html`；未引任何第三方库；分页/选择/表单全部用原生 DOM + `edu-api.js`；**金额校验信任服务端**（前端仅友好提示），符合"资金/金额路径留一手只管握手不越权"；提交按钮 loading 态防双击 |
| `C:\Users\Administrator\.agents\skills\tt\SKILL.md` §5.2 | 回传/资产消费硬约束/完工前自检三视角 | 本报告含「资产消费证据」段；产物含资产锚点；完工前用 critique 三视角（交互态/边界/错误反馈）自查：pending 状态文字、撤销仅 pending、分页空态、金额超限提示、工单必填校验均已覆盖 |
| `C:\Users\Administrator\.agents\skills\harden` | 金额/越权/幂等/分页/错误分流 | 角色守卫三段（无 token→跳登录、非学生→跳回 dashboard、auth/me 失败→跳登录）；服务端强制 ≤ 实付，前端也做 ≤ 校验并提示；分页按裸壳 `{total,page,page_size,items}`（禁 page_meta）；空态/加载态/错误态齐全；文本 XSS 转义 `esc()`；默认错误 toast（教育 API 客户端自带） |

### agent×skill×workflow 矩阵

| 环节 | agent | skill | workflow / 纪律 |
|---|---|---|---|
| 资产整合 | 本 task 执行 agent | ponytail + tt(§5.2) + harden | tt 闭环 §1 先盘点资产、开工前读必调资产 |
| 契约冻结核对 | 本 agent（对照后端源码） | — | tt §5.3 契约独立核验（读 router/schemas/service 三处源码，回源确认字段/枚举，不采信注释） |
| 实现 | 本 agent（静态页注入 + IIFE） | ponytail（最简可用） | fe-html 静态页注入模式：`</body>` 前引 `/edu-api.js` + IIFE，先判 `EAPI.store.getToken()` 静默降级，不重定义全局 `$` |
| 独立实证验收 | 本 agent（真实 HTTP requests 打 8000） | harden（错误分流/金额校验） | tt §5.2 验收必须独立实证、不采信报告；本报告附真实响应 |
| 完工 | 本 agent | — | 不 commit（纪律） |

---

## 2. 页面功能清单 + 真实端点对照 + 独立实证

### 页面功能清单（`refund.html`）
1. **我的退款列表**：`GET /api/refunds`（倒序分页），展示退款号/关联订单/申请金额/批准金额/状态(pending=到账审核中、approved=已批准·待退款、rejected=已拒绝、refunded=已退款)/申请时间/处理备注；外层分页 `{total,page,page_size,items}`。
2. **发起退款**：下拉选已支付可退订单 → 填金额/四枚举类型(personal_reason/course_unsatisfied/schedule_conflict/duplicate_purchase)/原因 → `POST /api/refunds`。金额前端 ≤ 实付校验 + 服务端硬约束兜底（超出被 400 拦截并 toast 服务端 message）。
3. **撤销退款**：pending 态显示「撤销申请」按钮 → `POST /api/refunds/{id}/cancel`；撤销后列表不再展示该项。
4. **问题反馈工单**：简化表单 → `POST /api/trade/after_sales/ticket`（类型 refund/appeal/consult，可关联订单号）。
5. **角色守卫** `bootRefund()`：三段式，见 §3。

### 真实端点对照表
| 页面动作 | 真实端点（后端源码权威） | 契约核对文件 |
|---|---|---|
| 取消申请 | `POST /api/refunds` | `trade/refund/router.py`、`schemas.py::RefundCreateInput` |
| 我退款列表 | `GET  /api/refunds?page&page_size` | `trade/refund/router.py`、`schemas.py::RefundPage`（裸壳，非 page_meta） |
| 撤销 | `POST /api/refunds/{id}/cancel` | `trade/refund/router.py` |
| 可退订单 | `GET  /api/trade/orders?refundable=true` | `trade/order/router.py`、`schemas.py::Order` |
| 反馈工单 | `POST /api/trade/after_sales/ticket` | `after_sales/router.py`、`schemas.py::TicketCreateInput` |
| 身份 | `GET  /api/auth/me` | `auth/schemas.py::UserInfo`（role 判定） |

### 独立实证（真实 HTTP，requests 打 `http://127.0.0.1:8000`，student `user000001/Test@123456`）
> 路径：先给测试学生造一笔已支付订单（下单 → `pay_channel=mock` 发起支付 → mock 回调到账），再跑退款闭环。关键响应逐条实录：

1. **登录**：`POST /api/auth/login` → `HTTP 200 {"code":0,...,"data":{"access_token":...,"user":{"role":"student"}}}` ✅
2. **造可退订单**：
   - `POST /api/trade/order {series_id:1,cohort_id:2}`（Idempotency-Key）→ `HTTP 200 code:0`（data 为空，order_no 以查询为准）
   - `POST /api/trade/payment/{order_no} {pay_channel:"mock"}` → `HTTP 200 {"payment_no":"P-1-260904101925-589ba5","status":"pending"}`
   - `POST /api/trade/payment/{payment_no}/mock-notify` → `HTTP 200 {"applied":true,"message":"支付成功"}`
   - `GET /api/trade/orders?refundable=true` → `total:1`，订单 `status:"paid", pay_amount:2999.0` ✅
3. **金额超限被拦（硬约束）**：`POST /api/refunds {apply_amount: 2999+10000}` → **HTTP 400 `{"code":"40230","message":"退款金额超出实付金额（实付 2999.00）"}`** ✅ 前端 ≤ 校验 + 服务端拦截双保险
4. **发起退款（合法）**：`POST /api/refunds {apply_amount:2999, refund_type:"course_unsatisfied", ...}` → `HTTP 200 {"id":22580,"refund_no":"1-260904101934-ab9fdf","refund_status":"pending","apply_amount":2999.0}` ✅
5. **列表可见**：`GET /api/refunds` → `total:1`，`items[0].id==22580` 命中 ✅（返回值含 refund_type/apply_amount/applied_at 等，页面字段齐全）
6. **撤销 pending**：`POST /api/refunds/22580/cancel` → `HTTP 200 {"cancelled":true,"refund_no":"1-260904101934-ab9fdf"}` ✅
7. **撤销后列表不再展示**：`GET /api/refunds` → `total:0` ✅（软删 yn=0，符合契约 `cancelled:true`）

**实证结论：退款闭环（申请→列表可见→金额超限被拦→撤销→消失）全部通过。**

> ⚠️ 附带发现（非本页问题，供编排者知悉）：`POST /api/trade/after_sales/ticket` 实证时后端抛 **HTTP 500** `(1064 ... near 'DISTINCT FROM 1 LIMIT 1')` —— 属 `after_sales/service.py` 既有 SQL 语法缺陷，非本任务前端改动引入、属后端契约外问题，本页仍按 router/schemas 契约接线；需后端单独排（超 task66 范围，未改）。

---

## 3. 角色守卫 / 购买力降级说明

**守卫三段（`bootRefund`，纪律 lesson10）**
- 无 token：`location.replace(/login-register.html?redirect=...)`（用 `EAPI.buildLoginUrl` 安全构造，站内相对路径防开放跳转）。
- 有 token：`GET /api/auth/me` → `role==="student"` 才注入真实数据；`admin/manager/teacher` → 全屏提示"无权访问退款中心"并 `location.replace(/dashboard.html)`。
- auth/me 失败（停机/网络/agent 异常）无法确认身份 → 按未授权跳登录，**不静默放行**（防 DEBUG 降级绕过）。

**购买力 / 数据降级**
- **只用登录态真实数据**：无任何硬编码假退款/假订单兜底；可退订单下拉、退款列表均来自真实接口。
- 纯静态打开（未加载 `edu-api.js`）：无 token，守卫走 `if(!window.EAPI) return;` 静默退出 + 右下角「演示数据」角标注标演示态（与既有页面 task122 惯例一致），不弹错不假数据。
- 空数据态：无可退订单、无退款记录分别显示友好空态 + 下一步引导。
- 金额超限/非可退订单/撤销失败等：toast 展示服务端真实 message（如 `退款金额超出实付金额（实付 2999.00）`），覆盖前端乐观校验兜不住的服务端拒绝。

---

## 附：交付文件
- 页面：`E:\stu\project\stu\EduAgent实施手册\edu-frontend\public\refund.html`
- 本报告：`test-reports/task66-completion-report.md`
- 未 commit。