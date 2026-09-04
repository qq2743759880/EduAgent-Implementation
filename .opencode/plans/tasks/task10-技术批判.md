# task10 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」+ 6 点验收原则（db-acceptance-principles.md P6 口径漂移声明）
> 对象：task10 middleware + 响应壳统一 + 错误码分段（契约冻结①）（Trae 报告 DONE，commit a828837）
> 结论：**⛔ 验收不通过（P0 契约缺陷）**——错误码类型与三重权威文档冲突，且执行方擅自改口径未声明

---

## 批判 1（P0 阻塞）：错误码类型偏离契约 —— 权威文档要求「字符串」，实现与交接单冻结「数字」

**问题描述**：task10 任务文档 GWT①、dev-plan §0 全局红线、doc-frontend-design-spec、tech-source-audit **四处权威文档**均明确「失败 `{code:<字符串>,message,data:null}`」，但 task10 实现为**数字错误码**（40111/42200/40912 等），交接单 `task10-contract.md` v1.0 也冻结为「`<数字错误码>`」，契约测试断言 `code == 40111`。且 task10 报告 GWT 自查将「字符串」篡改为「数字」**未声明口径漂移**（违反 P6）。

**证据来源**：
- 任务文档 `task10-middleware-response-shell.md` GWT①原文：「失败 `{code:<字符串>,message,data:null}`」
- dev-plan.md §0：「失败 `{code:<字符串错误码>,message,data:null}`」
- doc-frontend-design-spec.md：「api-client.ts 响应拦截器…失败 `{code:<字符串错误码>}`」
- tech-source-audit.md §五 apiEnvelope：「失败 {code:<字符串>,message,data:null}」
- 实现 `app/common/error_codes.py`：`OK = 0`、`AUTH_LOGIN_FAILED = 40111`（数字 int）
- 契约测试 `test_contract_middleware.py`：`code"] == 40111`（数字断言）
- 交接单 v1.0：「`"code": <数字错误码>`」
- 报告 GWT 自查：「失败 {code:<数字>,…}」（与任务文档 GWT 原文「字符串」不一致，未声明）

**与正确做法的差距**：契约冻结是 TraeWork 前端开发的唯一依据。字符串 vs 数字影响前端 `api-client.ts` 错误码硬编码判断（`code === 'AUTH_LOGIN_FAILED'` vs `code === 40111`）、错误提示映射、国际化。三重文档权威一致要求字符串，实现方单方改数字且未按 P6 显式声明 = 契约漂移，会让 TraeWork 按错误契约开发，前端返工。

**优化方案**（二选一，需用户/编排者裁定）：
- **方案 A（推荐，符合既有文档）**：错误码改字符串。`error_codes.py` 改为 `AUTH_LOGIN_FAILED = "AUTH_LOGIN_FAILED"`（或 `"40111"` 字符串）→ 契约测试断言改字符串 → 交接单 v1.0 更新 → 报告修正。前端 `code === 'xxx'` 判断，可读性强。
- **方案 B（改文档）**：若坚持数字（大厂惯例如头条/腾讯确实常用数字分段），则需**显式更新三份权威文档**（dev-plan/doc-frontend-spec/tech-source-audit + 任务 GWT）为「数字错误码」，并按 P6 记录口径变更（版本/日期/理由），交接单改 v1.1 声明。但前端规范文档中 api-client 解包逻辑、错误映射表需同步重写。

**最小验证方法**：修复后实跑真实 API 失败响应，验证 `code` 类型与交接单/文档一致；契约测试断言类型一致。

**预期收益与成本**：方案 A 成本 1~2h（改常量+测试+交接单）；方案 B 成本 2~3h（改三份文档+交接单+前端规范）。不修复则 TraeWork task40/41 按错误契约开发，返工成本 ≥1 天。

---

## 批判 2（P1）：契约测试「遍历全部 router」未达成 —— 仅覆盖 auth 域 6 端点

**问题描述**：GWT① 要求「契约测试**遍历全部 router**」断言响应结构通过率 100%。实际 test_contract_middleware.py 13 用例仅覆盖 auth 相关 6 端点（login 成功/失败/validation/not_found/health/register），未覆盖 course/question/progress/chat/community 等存量 router 的响应壳。

**证据来源**：test_contract_middleware.py 13 用例清单（TestResponseShell 6 + Trace 3 + Idempotency 1 + RateLimit 2 + SecurityHeaders 1）；报告 §3 同。

**与正确做法差距**：契约冻结① 的目标是「全模块响应壳统一」，但仅 auth 域验证过壳格式。course 域等若仍有 `return {"data": ...}` 旧格式（未走 ok()），契约测试无法发现——直到前端联调才暴露。

**优化方案**：补「遍历全部 router」测试：遍历 app 全部 APIRouter 的每个 GET 端点发请求断言响应壳结构（成功 code==0 + data 存在；失败 code!=0 + data==null）。列入契约测试套件（test_contract_all_routers.py）。

**最小验证方法**：新测试对全 router 断言，通过率 100%（或列出未达标 router 清单修复）。

**预期收益与成本**：+2h；收益=契约冻结①真正「全模块」可信，TraeWork 联调零意外。

---

## 批判 3（P2）：中间件注册顺序声明与实现未做契约测试断言

**问题描述**：任务文档要求注册顺序「SecurityHeaders → CORS → Trace → Idempotency → RateLimit → CircuitGuard → RequestLogging」。报告未提供 main.py 实际注册顺序证据，契约测试未断言顺序（中间件顺序错误会导致幂等绕过限流、CORS 拦截 trace 等隐患）。

**证据来源**：报告 §交付物 main.py「注册顺序更新」无具体顺序列表；test_contract_middleware.py 无顺序断言用例。

**优化方案**：在契约测试中加 `test_middleware_order`：读取 app.user_middleware 列表断言顺序。

**预期收益与成本**：+30min；收益=中间件链可回归验证。

---

## 汇总

| GWT | 结果 | 判定 |
|-----|------|------|
| ① 响应壳全 router 100% | ❌ | 错误码类型偏离文档（P0）+ 未遍历全 router（P1）|
| ② 幂等 Idempotency-Key | ✅ | 中间件注册 + 前缀拦截确认（未做真实重复请求断言，P2 可后补）|
| ③ Trace X-Trace-Id | ✅ | 3 用例 PASS（响应头/错误/透传）|

**结论：验收不通过（P0 阻塞）**。需裁定方案 A/B 并修复后重新验收；批判 2/3 随修复一并补测。
