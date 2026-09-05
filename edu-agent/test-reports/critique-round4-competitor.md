# critique-round4 竞品对标批判报告（支付对账 + LLM 重试退避）

> 批次：2026-09-05 收口批
> 视角：从竞品（支付宝/微信支付、OpenAI/Anthropic 官方 SDK）对标复查 2 个领域
> 方法：源码缺陷精读 → 判定真缺陷/登记缺口（不硬造、真实契约优先）→ 最小修复 + 独立契约测试 → 基线确认无回归
> 测试：`tests/test_critique_round4.py`（12 passed）

---

## 一、支付对账金额比较 —— 分单位整数（对标支付宝/微信「金额以分为单位」对账口径）

### 背景
`PaymentReconcileRepo.run_reconcile()`（`edu-agent/app/domains/trade/payment/repository.py`）对账检测
`AMOUNT_MISMATCH` 金额一致性时，用：
```python
if float(r["amount"]) != float(r["payable_amount"]) ...
```
即**原生浮点相等比较**。

### 缺陷判定：P2 真缺陷（确定性误报路径）
- 金额经运算聚合（如 `0.1 + 0.05`）存 `amount`，其浮点表示是 `0.15000000000000002`；而直接存 `0.15` 的 `payable_amount` 是 `0.15`。二者 `!=` 恒真 → **同一笔真实一致的支付会被误报为 `AMOUNT_MISMATCH`**。
- 资金对账属于**误报代价极高**的场景（每次误报都需要人工核对/整改）；支付行业通行口径是「金额以分为单位做整数运算/比较」。
- 现行对账 0 测试覆盖（`rg run_reconcile` 仅 service/router/repository 三处，无测试），缺陷未被暴露。

### 修复
`run_reconcile` 内新增 `_cents(x) -> int`（`round(float(x) * 100)`），比较改为分单位整数：
```python
if _cents(r["amount"]) != _cents(r["payable_amount"]) and r["order_status"] not in ("partial_refunded", "refunded"):
```
- 仅影响对账**诊断阈值**，不改 DB schema、不改响应壳、不涉及既有冻结契约。
- 真实不一致（0.20 vs 0.15）仍被检出，无漏报。

### 独立实证（monkeypatch `fetch_all` 注入 crafted 数据）
| 用例 | 数据 | 旧实现 | 新实现 |
|---|---|---|---|
| 浮点求和 vs 直存 | amount=`0.1+0.05`, payable=`0.15` | ✗ 误报 Mismatch | ✓ 不误报 |
| 真实不一致 | amount=`0.20`, payable=`0.15` | ✓ 检出 | ✓ 仍检出 |
| 退款豁免 | refunded 单差异 | ✓ 豁免 | ✓ 仍豁免 |

### 真实契约校准（2026-09-05 环境完整后复跑）
- **STATUS_DRIFT 白名单并入 `completed`**：首次上真实 DB（54,564 笔 paid 支付）复验时，新增状态漂移检测把 `order_status=completed`（已结课，合法已收款态）误判为漂移。真实枚举为 `pending/paid/completed/partial_refunded/refunded/cancelled/closed`，合法已收款态含 `completed`。校准 `_ORDER_OK_AFTER_PAID={paid,completed,partial_refunded,refunded}` 后，`TestGWT4Reconcile::test_reconcile_no_duplicate` 对 54,564 行**0 误报**通过（提交 `c9cbda0`）。

---

## 二、LLM 重试退避 —— 尊重 `Retry-After` 响应头（对标 OpenAI/Anthropic 官方 SDK）

### 背景
`app/core/retry.py` `next_backoff()` 按错误类型固定退避：
- RATE_LIMIT(429) → 指数 `2^n` 秒（封顶 30s）+ jitter
- TIMEOUT → 线性 `base*n`
- MODEL_ERROR → 0s 立即切源

### 缺陷判定：P2 增强（对标差异 + 实际可观测收益）
- **OpenAI / Anthropic 官方 SDK 对 429/503 必读 `Retry-After` 响应头**，以其指令为准（fallback 到固定退避）；当前实现完全忽略该头，一律用 `2^attempt` 指数退避。
- 后果：服务方明确告知「x 秒后可重试」时，客户端要么提前重试（再次触发限流/白烧配额），要么过度推迟（白白等待、抬高端到端延迟）。

### 修复（纯函数 + 接线，向后兼容）
1. `retry.py`：`next_backoff`/`plan_retry` 新增可选参数 `retry_after: float | None = None`；
   任一类型下若提供该值，`wait = min(retry_after, cap)`（仍封顶防死等），叠加现有 jitter。
2. `generator.py`：
   - 新增 `_retry_after_from(resp)`：解析响应头 `Retry-After`（秒级数值；缺头/非法 → None）。
   - `call_chat` / `call_chat_stream` 两处非 200 抛错点，将解析到的 `retry_after` 附加到 `RuntimeError.retry_after`。
   - `call_chat_with_retry` / `call_chat_stream_with_retry` 两处退避调用点，`next_backoff(..., retry_after=getattr(exc, "retry_after", None))`。

### 独立实证（`tests/test_critique_round4.py`）
- `next_backoff("429", n, retry_after=5)` → 恒 `5.0`（尊重服务方）；`+jitter=1.0` → `[5,6]`。
- `next_backoff(..., retry_after=999, cap=30)` → `30.0`（封顶）。
- `next_backoff("timeout", 2, retry_after=3)` → `3.0`（503 超时也尊重）。
- 缺 retry_after → 回退指数 `2/4/.../30` 不变。
- `_retry_after_from`：`"7"`→`7.0`；缺头→None；`"HTTP-date-ish"`→None。
- `call_chat_with_retry` 集成：首调抛 429（`exc.retry_after=7`）→ 二次成功，断言 `sleep` 实参 == `7.0`。

---

## 三、登记缺口（不硬造、待真实渠道接入时前置）

### 支付回调验签 / 金额校验未实现对真实渠道
- 当前 `mock_notify` 仅接受 `mock` 模拟渠道校验；`settle_payment` 在回调成功时直接使用**记录内已有金额**，未校验「第三方回调金额 vs `payable_amount`」一致。
- 支付宝/微信规范要求：回调必须验签（RSA/SHA256）、验商户号、验金额，防篡改/伪造。
- **判定**：当前系统真实支付渠道（wechat_pay/alipay）回调通道**尚未接线**（仅 mock 模拟渠道），故验签/金额校验属「真实渠道接入前置需求」，登记为缺口而非既有缺陷；一旦接入真是渠道必须补齐 `verify_signature()` + `verify_amount()` 闸门。
- 落点：待真实支付渠道接入任务；本次不硬造验签实现（避免对不存在通道的空转代码）。

### 支付-订单状态漂移对账缺失
- `run_reconcile` 只检测「金额不一致/重复入账」，**未检测「payment_record=paid 但 order 非 paid」的状态漂移**（资金安全最值得关注的残差）。
- 判定为增强项：写入 backlog，建议后续对账补充状态漂移检测 SQL（`payment paid & (order pending|closed)`）。本次未实施以避免扩大对账变更面。

---

## 四、回归确认

- `tests/test_critique_round4.py`：12 passed（新增）。
- `tests/`（-k "retry or rate_limit or g1 or reconcile or payment"）：**62 passed**；剩余失败均为 live 后端依赖（HTTP 429 限流被去重实测打满 /「无可用班次」数据依赖），失败发生在下单 setup 阶段，未触达被改动代码，判定非本批回归。
- 改动不触碰既有冻结契约（响应壳/错误码/schema 均未变）。

## 五、资产消费证据

- 精读：`app/core/retry.py`、`app/domains/trade/payment/repository.py`、`app/domains/trade/payment/service.py`、`app/chat/generator.py`（call_chat / call_chat_stream / 两个 *_with_retry）。
- 探查（Explore subagent）：支付域状态机/回调幂等/对账、LLM 重试/限流/token 预算两份独立探查报告。
- 修复文件：`repository.py`（reconcile 分位比较）、`retry.py`（Retry-After）、`generator.py`（_retry_after_from + 抛错点 + 退避注入）。
- 测试：`tests/test_critique_round4.py` 12 项。