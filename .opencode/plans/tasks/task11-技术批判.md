# task11 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task11 课程域改造（Trae，commit 3f2d237）
> 结论：**⛔ 验收不通过（P0）**——发现 RespWrap 中间件透传 bug（真实 HTTP 实证），安全补强 GWT ④ 不达标；契约冻结② 主体（5 端点/308/分页）验收通过

---

## 批判 1（P0 阻塞）：RespWrap S2 透传逻辑 bug —— 所有非 2xx 壳响应变 500

**问题描述**：匿名访问 `GET /api/admin/users` 实测返回 **500 + `{"code":"50000","data":"'list' object has no attribute 'items'"}`**，而非预期的 401 + `{"code":"40101"}`。根因在 `app/middleware/resp_wrap.py` dispatch 的 S2 分支（judge 裁定"以原始 (k,v) 列表透传 headers 保留多值头"）：

```python
raw_headers = [(k, v) for k, v in response.headers.items() if k.lower() not in _HOP_BY_HOP_HEADERS]  # list
return Response(content=body, status_code=..., headers=raw_headers, ...)  # Starlette 期望 dict
```

Starlette `Response.init_headers` 对 headers 调 `.items()`（dict 语义）→ list 无 `.items()` → AttributeError → 500。

**影响面**：任何"已是业务壳 + 非 2xx"的响应（**全部 401/403/429 鉴权限流失败**）经 RespWrap 透传时全部变 500。包括：AdminAuth 的 401、require_role 的 403、RateLimit 的 429。**这是全局性缺陷**，影响所有后续任务的鉴权/限流验证。

**证据来源**：
- 实跑（2026-08-18，task11 代码最新服务）：匿名 `/api/admin/users` → 500 `code=50000 data='list' object has no attribute 'items'`
- 服务 stderr：`resp_wrap.py:80 return Response(...)` → `AttributeError: 'list' object has no attribute 'items'`（`init_headers` 对 list 调 `.items()`）
- 响应头无 X-Trace-Id（异常在中间件链内部被吞，Trace 的响应头注入未完成）

**与正确做法差距**：Starlette `Response(headers=)` 接受 **dict**（`dict[str, str]`）或头元组列表（`Sequence[tuple[str, str]]`）？——查证：Starlette 实际接受 **dict** 或 **list of tuples**（两者都支持）。但这里 `raw_headers` 是 `[(k, v), ...]` **list of tuples**，Starlette 应支持……看异常栈：`init_headers` 里 `headers.items()` —— 说明 Starlette 版本对传入的 list 直接调 `.items()` 失败（版本差异）。**无论哪个 Starlette 行为，真实运行已证实崩**，必须修复。

**优化方案**（`resp_wrap.py` S2 分支）：
```python
# 方案①（推荐）：headers 传 dict（Starlette 最稳语义）
raw_headers = {
    k: v for k, v in response.headers.items()
    if k.lower() not in _HOP_BY_HOP_HEADERS
}
return Response(content=body, status_code=response.status_code,
                headers=raw_headers, media_type="application/json")

# 方案②：若需保留多值头，用 response.raw_headers（bytes 元组）直传
#   raw_headers = [(k, v) for k, v in response.raw_headers if ...]
```

**最小验证方法**：修复后匿名 `/api/admin/users` → 401 + `{"code":"40101","data":null}`；登录失败 → 40111 壳；限流触发 → 429 壳。契约测试 24/24 补"匿名 admin 401"用例。

**预期收益与成本**：收益=解除全局鉴权/限流 500 化；成本=30min。

---

## 批判 2（P2）：task11 sd-tester 26/26 未覆盖"匿名访问管理端点"路径

**问题描述**：sd-tester 声称 26/26 全绿，但未发现 RespWrap 的 P0 bug（契约测试 24/24 是 task10 验收时跑过，task11 加 AdminAuth+RespWrap S2 后未重跑全量）。测试覆盖缺口：管理端点匿名访问（401 预期）、非 2xx 壳透传（401/403/429）。

**证据来源**：task11-test-report.md（26 用例，聚焦 series 端点）；task11 完成后未重跑 task10 契约套件（test_contract_middleware.py 24 项）。

**与正确做法差距**：契约套件是回归基线，task11 改动中间件后必须重跑（CI 门禁 P4 本应拦截，但 CI 未接入本地——task98 未完成）。

**优化方案**：task11 修复时：①重跑 `test_contract_middleware.py` + `test_contract_all_routers.py` 全量 24 项；②新增"匿名管理端点 401"用例进契约套件；③RespWrap 修复后补 429/403 壳透传用例。

**最小验证方法**：修复后 24+ 用例全绿 + 新增 401 用例 PASS。

**预期收益与成本**：收益=防回归；成本=30min。

---

## 批判 3（P2）：契约回归套件受 login 限流 10/min 影响（报告已声明）

**问题描述**：报告声明"契约回归套件自身打满 login 限流 10/min 导致 10 项 FAIL（P2 既有）"。这使"26/26 全绿"与"10 项 FAIL"并存——测试结果口径不一致。

**证据来源**：task11 报告已知限制 2。

**优化方案**：契约测试 fixture 提供固定 admin token（登录一次复用），避免每用例重复登录打满限流；或测试专用限流豁免环境变量。

**最小验证方法**：重跑契约套件无限流 FAIL。

**预期收益与成本**：收益=测试确定性；成本=1h（task10 契约测试改造）。

---

## 汇总

| GWT | 结果 | 判定 |
|-----|------|------|
| ① /api/series 筛选+snake_case+分页+P95 | ✅ | 实测 200/code=0/page_meta/snake_case/151ms |
| ② 308 重定向参数保留 | ✅ | 实测 308 → /api/series?page=1 |
| ③ 四级查询层级 | ✅ | sd-tester 26/26 + 报告 |
| ④ 匿名 admin 401（安全补强）| ❌ | **500（RespWrap bug）** |

**结论：验收不通过（P0），需修复 RespWrap S2 后重验**。契约冻结② 主体（①②③）可先行解锁前端 task44/45/46，但④ 修复必须在 task12 开工前完成。
