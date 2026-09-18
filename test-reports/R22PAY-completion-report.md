# R22PAY / W-NEXT-PAYGATE-001 完成报告——真实支付渠道回调验签闸门

- **任务**：W-NEXT-PAYGATE-001（C-01 逐断言独立实证验收）
- **承接**：critique-backlog-tracker.md L346「支付回调验签/金额校验缺真实渠道实现（登记缺口，待真实渠道接入）」
- **分支**：feature/opt-waves；**代码 commit**：见下文「一、commit」
- **日期**：2026-09-18

---

## 一、commit

- 代码+测试+实证文件：commit `062704a97143c6417f21409cf5baa5dc7d35609e`（feature/opt-waves，commit 前 symbolic-ref=refs/heads/feature/opt-waves + rev-parse 复核通过）
- 本报告随后续 commit 入库（报告需引用代码 commit hash，故分两笔）

## 二、交付物与文件归属（红线核对）

| 文件 | 变更 | 说明 |
|---|---|---|
| `edu-agent/app/domains/trade/channel_verify.py` | **新增** | 闸门模块（验签/验金额/验商户/编排/审计） |
| `edu-agent/app/domains/trade/payment/service.py` | 修改（最小 diff +69/-13） | ① 事务体提取为 `_settle_once`（与原 mock_notify 事务体逐行等价）；② 新增 `channel_notify` 分派；③ 导入闸门符号 |
| `edu-agent/app/domains/trade/payment/router.py` | 修改 | 新增 `POST /payment-notifications/channel` 端点 + docstring 登记 |
| `edu-agent/app/domains/trade/payment/schemas.py` | 修改 | 新增 `ChannelNotifyInput` |
| `edu-agent/app/config.py` | **仅追加** 3 个 key 字段（默认空） | `PAY_ALIPAY_PUBLIC_KEY` / `PAY_WECHAT_API_V3_KEY` / `PAY_MERCHANT_ID` |
| `edu-agent/tests/test_r22pay_channel_verify.py` | **新增** | 34 用例（离线单测，无真实后端依赖） |
| `test-reports/r22pay_mock_chain_regression.py` + `_r22pay_mock_chain_out.txt` | 新增（实证资产） | 真实 HTTP 回归脚本 + 输出 |
| `test-reports/_r22pay_pytest_out.txt` | 新增（实证资产） | 34 用例逐条 PASSED |

**禁碰核对**：`settle_payment`（repository.py）**零改动**（diff 为空）；其他域零改动；`_SIMULATION_CHANNELS`/mock 回调鉴权（B2：DEBUG 或 ADMIN/MANAGER）零改动；error_codes.py 零改动（复用既有 50301/40300/42200/40420/40021）；tracker 文件未动（承接核对见 §七）。

### notify 分派点改动逐处清单（最小 diff 声明）

1. `service.py` L18：新增 1 行 import（`GATE_CHANNELS, audit_reject, run_channel_gates`）。
2. `service.py` `mock_notify`：事务体**原样提取**到 `_settle_once(payment_no, order_no, third_party_trade_no)`；`mock_notify` 本体保留 40420/40021 两道原检查后改为调用 `_settle_once`。行为等价性由测试 `TestMockNotifyCompat`（4 用例）+ 真实回归 A1–A5 证明（含幂等 1062/duplicate 兜底路径）。唯一文案差异：内部异常日志前缀 `[payment] mock 回调事务失败` → `[payment] 回调事务失败`（两入口共用，日志语义更准确）。
3. `service.py` 新增 `channel_notify`：入口白名单（audit `ENTRY_CHANNEL_NOT_ALLOWED` → 42200）→ 记录存在（40420）→ 渠道与记录一致（audit `CHANNEL_RECORD_MISMATCH` → 40300）→ 闸门三关 → `_settle_once`。
4. `router.py`：新增 1 个端点（公开——渠道服务器无法持 JWT，鉴权=闸门三关，实测缺 key 时无凭证也只得到 50301，见 §四 B2）。
5. `schemas.py`：新增 1 个请求体模型。

## 三、闸门四关清单（确定性策略：任何一关不过 = 拒绝 + 审计，无旁路）

| 关 | 函数 | 规则 | 失败码 |
|---|---|---|---|
| ① 渠道白名单 | `GATE_CHANNELS={alipay,wechat_pay}`（service 入口 + `verify_signature` 双重校验） | mock/未知/线下渠道拒绝；mock 走既有 mock-notify 端点（鉴权语义零变化） | 42200 |
| ② 验商户 | `verify_merchant(merchant_id)` | 回调 merchant_id 与 `settings.PAY_MERCHANT_ID` 精确串匹配；**期望值未配置 → 50301 fail closed** | 40300 / 50301 |
| ③ 验签 | `verify_signature(channel,payload,signature)` | RSA2 = SHA256withRSA（PKCS1v15）；待签串按支付宝官方规则规范化（排除 sign/sign_type/空值，key ASCII 升序，`&` 连接）；公钥 `settings.PAY_*`，支持 PEM / base64-DER；**缺 key/公钥损坏 → 50301，绝不放行**；base64 非法/验签不过/任何意外 → 全路径拒绝 | 40300 / 50301 / 42200 |
| ④ 验金额 | `verify_amount(notify_amount,payable_amount)` | 分单位整数比较：`Decimal(str(x))*100` ROUND_HALF_UP（与对账 `_cents=round(float*100)` 同口径，亚分级浮点尾差不误报，整分级差异永不跨舍入边界）；非法/负数拒绝；0 元单（全额券）允许 0==0 | 42200 |

编排 `run_channel_gates`：确定性顺序 ②商户→③签名→④金额；`payable_amount` 取自 `get_payment` JOIN 订单的 `o.payable_amount`（repository 未改）。settle 只在四关全过后发生，且复用幂等条件更新（GWT①）。

审计：所有拒绝路径统一 `[PAY-GATE-AUDIT] {"event":"PAY_NOTIFY_REJECT","reason":...}` 单行 JSON（channel/record_channel/payment_no/canonical_head 等上下文），`audit_reject` 序列化失败不阻断拒绝主流程。

## 四、实测输出（独立实证）

### 4.1 单测（34/34 全绿；RSA 密钥对测试内嵌生成，不入 env/.env）

```
$ .venv/Scripts/python.exe -m pytest tests/test_r22pay_channel_verify.py -v --no-header
...
TestVerifySignature::test_tampered_payload_rejected PASSED        # payload 篡改(12.30→99.99)→40300+SIGNATURE_TAMPERED
TestVerifySignature::test_tampered_signature_rejected PASSED      # 伪造签名→40300
TestVerifySignature::test_wrong_key_signature_rejected PASSED     # 换私钥签发→40300
TestVerifySignature::test_missing_key_50301_fail_closed PASSED    # 缺 key→50301(http 503)+KEY_NOT_CONFIGURED
TestVerifySignature::test_corrupted_key_50301_fail_closed PASSED  # 公钥损坏→50301
TestVerifyAmount::test_off_by_one_cent_rejected PASSED            # 12.30 vs 12.31 差 1 分→42200+AMOUNT_MISMATCH
TestVerifyAmount::test_float_tail_pass PASSED                     # 0.1+0.05 vs 0.15→通过(对账口径一致)
TestVerifyMerchant::test_mismatch_rejected PASSED                 # 商户不匹配→40300
TestVerifyMerchant::test_expected_not_configured_50301 PASSED     # 商户未配置→50301
TestChannelNotifyDispatch::test_tampered_notify_never_settles PASSED  # 篡改→拒绝且 settle 零调用
TestMockNotifyCompat::test_non_mock_channel_rejected_40021 PASSED     # mock 原红线保持
（全部 34 条逐条清单见 test-reports/_r22pay_pytest_out.txt）
============================= 34 passed in 2.76s ==============================
```

回归联动：`tests/test_critique_round4.py`（对账口径）14 用例全绿（合计 48 passed）。

### 4.2 mock 支付链路真实一轮（真 HTTP 直连 127.0.0.1:8000，无 Playwright，遵循 AGENTS.md 教训②）

后端重启加载新代码后执行 `test-reports/r22pay_mock_chain_regression.py` → **11/11 ALL PASS**（全文 `_r22pay_mock_chain_out.txt`）：

```
[PASS] A1 发起 mock 支付: {"http": 200, "payment_no": "P-1-260919023805-ba32d2", "audit_pending": false}
[PASS] A2 mock 回调 settle: {"http": 200, "applied": true, "message": "支付成功"}
[PASS] A3 支付/订单状态 paid: {"payment_status": "paid", "order_status": "paid"}
[PASS] A4 DB 复核：paid×1 + 报名 active: {"payments": [{"payment_no": "P-1-260919023805-ba32d2",
         "payment_status": "paid", "third_party_trade_no": "TRD-R22PAY-…"}], "enrolls": [{"enroll_status": "active"}]}
[PASS] A5 mock 回调幂等（二次）: {"http": 200, "applied": false, "message": "已处理（幂等）"}
[PASS] B1 发起 alipay 渠道支付（真实渠道，无真实流量）: {"http": 200, "payment_no": "P-1-260919023808-70245b"}
[PASS] B2 缺 key 拒绝（无 JWT 也可打——闸门即鉴权）: {"http": 503, "code": "50301", "message": "支付渠道依赖未配置，请稍后重试"}
[PASS] B3 渠道/记录不匹配拒绝: {"http": 403, "code": "40300", "message": "回调渠道与支付记录渠道不匹配"}
[PASS] B4 mock 渠道不走渠道入口: {"http": 422, "code": "42200", …}
[PASS] B5 未知渠道拒绝: {"http": 422, "code": "42200", …}
[PASS] B6 拒绝后无副作用（仍 pending）: {"payment_status": "pending"}
== RESULT: ALL PASS (11/11) ==
```

B2 为关键封存证据：**无 Authorization 头、缺 key 环境下打真实渠道端点 → HTTP 503 + 50301**（闸门即鉴权且 fail closed），同时 B6 证明拒绝无任何落账副作用。

### 4.3 审计日志实测（后端 uvicorn 日志）

```
[PAY-GATE-AUDIT] {"event": "PAY_NOTIFY_REJECT", "reason": "MERCHANT_NOT_CONFIGURED", "channel": "alipay"}
[PAY-GATE-AUDIT] {"event": "PAY_NOTIFY_REJECT", "reason": "CHANNEL_RECORD_MISMATCH", "channel": "wechat_pay", "record_channel": "alipay", "payment_no": "P-1-260919023808-70245b"}
[PAY-GATE-AUDIT] {"event": "PAY_NOTIFY_REJECT", "reason": "ENTRY_CHANNEL_NOT_ALLOWED", "channel": "mock", "payment_no": "P-1-260919023808-70245b"}
[PAY-GATE-AUDIT] {"event": "PAY_NOTIFY_REJECT", "reason": "ENTRY_CHANNEL_NOT_ALLOWED", "channel": "crypto_pay", "payment_no": "P-1-260919023808-70245b"}
```

### 4.4 trade 域套件回归

- `tests/test_r22pay_channel_verify.py` + `tests/test_critique_round4.py`：**48 passed**
- `tests/test_contract_task113.py` + `tests/test_contract_task28.py` + `tests/test_contract_task18.py`：**20 passed, 5 skipped**（skip 为既有默认标注，如 task18 需 live cohort 的 full-run 标注；非本任务引入）
- trade 域合计：**68 passed / 5 skipped / 0 failed**

## 五、P0 自批判（≥3，实质性）

1. **P0-1 重放/时间窗防护未实现（接线前必须补）**：闸门验签绑定了报文内容（篡改必拒）+ settle 幂等（同单重放 applied=false），但**没有 notify_id 去重与时间戳窗口校验**。残余场景：retry 后复用同 payment_no 重新 pending 时，一条历史合法签名回调可再次结算。真实渠道接线时 adapter 必须透传 notify_id/timestamp 并在闸门加时间窗（支付宝默认建议校验）或平台侧去重表；当前封存态（缺 key 全拒）无风险敞口。
2. **P0-2 审计仅落 logger，无 DB 审计表/告警接线**：`[PAY-GATE-AUDIT]` 依赖 uvicorn stdout + 本地 logs 文件，轮转可丢证据；拒绝风暴时亦无告警。建议接 ERROR_WEBHOOK_URL（C5-K3 已有机制）或仿 rag_audit_log 建 payment_notify_audit 表（本轮未做：新表超出本任务文件归属红线）。
3. **P0-3 微信 APIv3 验签为「同构 seam」而非官方报文级实现**：微信 v3 官方验签 message = `timestamp\nnonce\nbody\n` + 平台证书（带序列号轮换 `Wechatpay-Serial`）。当前闸门对两渠道统一用支付宝式 canonical 规范化 + 单 key。真实接线时 wechat adapter 须按官方 message 计算签名并在 payload 语义上对齐（或扩展 verify_signature 支持 per-channel canonicalizer + 证书序列号轮换）。单商户口径（单 PAY_MERCHANT_ID）同样需在多商户时扩展。
4. **P0-4 渠道端点无限流/防刷专项**：`/payment-notifications/channel` 公开可达，缺 key 时每次请求都会走 50301（可能被刷日志）。建议接线窗口前叠加既有 429 限流中间件规则或按源 IP 限速；本轮未独改中间件（避免越域红线）。
5. **P0-5 mock 链路仍受 DEBUG 管辖**：mock-notify 的 B2 收敛（DEBUG 或 ADMIN/MANAGER）未变；生产 DEBUG=false + 渠道 key 配置后，闸门成为渠道回调唯一防线，P0-1/P0-4 属接线前的硬前置。

## 六、契约与红线自检

- 响应壳 `{code,message,data}` 零变更；失败码全部复用既有值域（50301 脱敏契约：message 面向用户、detail 恒 null、原始异常仅入日志——`DependencyUnavailableError` 直接复用）。
- AGENTS.md Mimosa 硬约束：测试/回归 host 钉 127.0.0.1（NO_PROXY 显式）；SQL 全参数绑定（未新增裸拼 SQL）；凭据只从 env/settings 读取（测试 RSA 密钥对内嵌生成，不写 env）；DEBUG=False 生产语义未触碰。
- lock：`edu-agent/scripts/eval/r22pay.lock` 已于 commit 前删除。

## 七、批判承接核对（本轮即承接 tracker 346）

tracker 原文（.opencode/plans/critique-backlog-tracker.md L346）：

> **支付回调验签/金额校验缺真实渠道实现（登记缺口，待真实渠道接入）**：`mock_notify` 仅校验 mock 渠道；`settle_payment` 用记录内金额，未验「第三方回调金额 vs payable_amount」。支付宝/微信规范要求验签（RSA/SHA256）+验商户号+验金额。当前真实渠道回调未接线，属「接入前置需求」非既有缺陷；接入时必须补 `verify_signature()+verify_amount()` 闸门。落点：真实支付渠道接入任务。

逐句承接：

| tracker 断言 | 本轮闭环 |
|---|---|
| `mock_notify` 仅校验 mock 渠道 | 保持不动（原逻辑+鉴权零变化，回归 A1–A5）；新增 `channel_notify` 按 channel 分派 |
| `settle_payment` 用记录内金额，未验回调金额 vs payable_amount | `verify_amount(notify_amount, o.payable_amount)` 闸门先于 settle，分单位整数比较（§三④），篡改金额实测被拒且 settle 零调用 |
| 验签（RSA/SHA256）+验商户号+验金额 | 三关齐备 + 渠道白名单第四关（§三） |
| 「接入时必须补 verify_signature()+verify_amount() 闸门」 | **闸门先建好、接入即生效**：公钥/商户号从 env 注入（默认空=50301 全拒），实测封存态 B2 |
| 落点：真实支付渠道接入任务 | 本任务为该落点的接入前置；真实渠道 adapter（P0-1/P0-3 项）仍在 tracker 原条目管辖，复选框由编排者核对后关闭 |

## 八、资产消费证据（具名路径）

1. `.opencode/plans/critique-backlog-tracker.md` L346 原文（§七引用）。
2. `edu-agent/app/domains/trade/payment/service.py`（全读：mock_notify/分派点/settle 调用链）；`repository.py`（全读：`settle_payment` GWT①② 语义与幂等条件更新——未改）；`router.py`/`schemas.py`（全读：端点与请求体契约）。
3. `edu-agent/app/common/error_codes.py`（50301 DEPENDENCY_UNAVAILABLE 定义与脱敏契约说明）；`app/common/exceptions.py`（`DependencyUnavailableError`：detail 恒 None、http 503）。
4. `edu-agent/app/config.py`（Security 段追加 PAY_* 三字段）。
5. `tests/conftest.py`（monkeypatch settings 范式）；`tests/test_critique_round4.py`（离线 repo 测试范式 + 对账 `_cents` 分单位口径——闸门金额口径与其对齐）；`tests/test_contract_task18.py`（GWT/端到端/幂等范式——回归脚本 A 段同构）。
6. AGENTS.md：教训②（禁 Playwright，回归用真 HTTP）、教训⑧（真实契约优先）、Mimosa 硬约束（host 127.0.0.1 / SQL 参数绑定 / 凭据只从 env）。
7. 复跑入口：`edu-agent/.venv/Scripts/python.exe -m pytest tests/test_r22pay_channel_verify.py tests/test_critique_round4.py -v`；`edu-agent/.venv/Scripts/python.exe test-reports/r22pay_mock_chain_regression.py`（需 8000 后端存活）。
