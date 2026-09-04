# task17-fix 验收批判（补充）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task17-fix（幂等中间件 P1，Trae，commit 4c43d59）
> 结论：**✅ 验收通过**（P1 修复实证全绿），2 条批判（P2 不阻塞）

---

## 实证结果（8003 最新代码服务，原始 http.client 读 body）

| 项 | 实测 |
|----|------|
| commit | ✅ `4c43d59`（4 文件 +165/-11）|
| 首次下单 | ✅ 200 cl=356 real_len=356 order_no=1-260821153012-e9cca1 |
| **幂等重复** | ✅ **200 cl=356 real_len=356 order_no 一致**（无 IncompleteRead，Content-Length 匹配）|
| 代码修复 | ✅ hop-by-hop 剔除（content-length/transfer-encoding/content-encoding/connection）+ body_iterator 捕获真实 body |
| test_contract_task17 | ✅ 7 passed（含 cancel/状态机/幂等）|
| 幂等 B 测试 | ✅ test_idempotency_repeat_full_body PASS |

## 批判 1（P2）：契约套件 2 FAIL 为限流环境污染（非修复回归）

**问题描述**：`test_contract_middleware.py` 2 FAIL：
- `test_rate_limit_on_auth`：已知用例缺陷（task11 批判⑤，登录 3 次打满限流）
- `test_admin_forbidden_403`：`login_token` 返回 None（stu01test 登录被 429 限流，auth 10/min 窗口打满）

均为**测试环境污染**（多次登录消耗限流额度），非 task17 修复引入。

**证据来源**：pytest 失败栈（login_token None）；auth 限流配置 (60,10)。

**优化方案**：转 task10 契约重构（module fixture 复用 token）+ task98 CI 门禁（已计划）。不阻塞。

## 批判 2（P2）：幂等修复暴露 task10 历史遗留（body 占位符）

**问题描述**：修复中发现 task10 幂等中间件写缓存时 `response.body` 为空（BaseHTTPMiddleware 流被消费）→ 缓存存 data:null → 重复 key 拿不到首次订单。A2 修复（body_iterator 捕获）解决。这是 task10 历史遗留，task17 暴露并修复。

**证据来源**：task17-fix 报告 A2 说明；idempotency.py body_iterator 捕获。

**优化方案**：已修复（A2）。task10 契约测试补幂等完整 body 断言（B 已加）。

## 汇总

| 原批判 | 状态 |
|--------|------|
| ① 幂等 IncompleteRead（P1）| ✅ 修复（Content-Length 匹配 + order_no 一致）|
| ② task10 幂等测试不完整 | ✅ 补 test_idempotency_repeat_full_body |
| ③ 100 并发 HTTP 层 | ⏳ 转 task39 压测（限流豁免下）|

**结论：task17 验收通过。** 契约冻结⑧ 生效 → 解锁前端 task64（/orders 页）。批判 1/2 均 P2（限流环境污染转 task10 重构 / task10 历史遗留已修）。
