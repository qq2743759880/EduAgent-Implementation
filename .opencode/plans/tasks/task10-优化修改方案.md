# task10 优化修改方案（基于技术批判，在现有产物上迭代）

> 依据：`task10-技术批判.md` 3 条批判 ｜ 原则：现有代码迭代，不另起炉灶
> **默认采用方案 A（错误码改字符串）**——与既有三重权威文档一致；若用户裁定数字，则改为方案 B（改文档）。

## 方案总览

| # | 修改点 | 目标文件 | 状态 | 工作量 |
|---|--------|---------|------|--------|
| A1 | error_codes.py 改字符串常量 | `edu-agent/app/common/error_codes.py` | P0 必做 | 30min |
| A2 | 契约测试改字符串断言 + 全 router 遍历 + 中间件顺序 | `tests/test_contract_middleware.py` + 新增 `test_contract_all_routers.py` | P0 必做 | 2h |
| A3 | 交接单 v1.1 更新（字符串 + 全 router 证据 + 版本日志） | `.opencode/handoffs/task10-contract.md` | P0 必做 | 20min |
| A4 | 报告修正（GWT 自查原文一致 + P6 声明记录） | `test-reports/task10-completion-report.md` | P0 | 10min |
| A5 | 存量 ok()/fail() 调用兼容检查 | 全局 grep `fail(`/`ok(` | P1 | 30min |

---

## A1：error_codes.py 改字符串常量

```python
# 原：OK = 0 / AUTH_LOGIN_FAILED = 40111（int）
# 改：字符串业务码（保持码段语义，前端可读）
OK = "OK"                        # 成功（code===0 兼容：成功固定 0，失败字符串）
BAD_REQUEST = "40000"            # 通用参数错误
NOT_FOUND = "40400"
FORBIDDEN = "40300"
CONFLICT = "40900"
VALIDATION = "42200"
RATE_LIMITED = "42900"
INTERNAL_ERROR = "50000"
SERVICE_UNAVAILABLE = "50300"
AUTH_ACCOUNT_MISSING = "40011"
AUTH_TOKEN_INVALID = "40101"
AUTH_TOKEN_EXPIRED = "40102"
AUTH_LOGIN_FAILED = "40111"
AUTH_USER_DISABLED = "40312"
AUTH_USER_NOT_FOUND = "40413"
AUTH_ACCOUNT_EXISTS = "40912"
# ...（交易 4xx2x/售后 4xx3x/学习 4xx4x 同理字符串化）
```

**关键兼容点**：
- 成功 code 保持 `0`（int，前端 `code===0` 判断不变）
- 失败 code 全部字符串（前端 `code !== 0` 判失败，错误映射用字符串 key）
- 全局异常 handler + RespWrapMiddleware 的 `fail()` 调用自动跟随常量

## A2：契约测试修正 + 补测

```python
# 1) 断言改字符串（原 code == 40111 → code == "40111"）
def test_login_failure_format(self, client):
    resp = client.post("/api/auth/login", json={"account": "x", "password": "wrong"})
    assert resp.status_code == 200   # 壳包裹，HTTP 仍 200（业务失败在 code）
    body = resp.json()
    assert body["code"] == "40111"   # 字符串断言
    assert body["data"] is None

# 2) 新增 test_contract_all_routers.py：遍历全部 router
def test_all_routers_envelope(app):
    """遍历 app 全部 APIRouter 的 GET 端点，断言响应壳结构。"""
    for route in app.routes:
        if hasattr(route, "methods") and "GET" in route.methods and route.path.startswith("/api"):
            resp = client.get(route.path.replace("{", "").replace("}", ""))  # 或构造合法参数
            body = resp.json()
            assert "code" in body and "message" in body, f"{route.path} 无响应壳"
            assert (body["code"] == 0 and "data" in body) or body["data"] is None

# 3) 新增中间件顺序断言
def test_middleware_order(app):
    names = [m.cls.__name__ if hasattr(m, "cls") else str(type(m)) for m in app.user_middleware]
    # 断言 SecurityHeaders 在 Trace 前、RateLimit 在 RequestLogging 前等关键顺序
```

## A3：交接单 v1.1 更新

```markdown
# 契约冻结①：响应壳规范 + 错误码清单（v1.1）
> 版本：v1.1 ｜ 变更：错误码由数字改字符串（对齐 dev-plan/前端规范；P6 口径声明：
>   2026-08-18 编排者批判发现数字偏离权威文档，经裁定改字符串，TraeWork 按 v1.1 开发）
> 失败响应：{ "code": "<字符串错误码>", "message": "<用户可读信息>", "data": null }
> 错误码清单：40000/40101/40111/40912/42200/42900/50000 ...（字符串）
> 前端约定：code === 0 成功直接取 data；code !== 0 按字符串 key 映射错误提示
```

## A4：报告修正

- GWT 自查第 1 条改回「失败 {code:<字符串>,…}」（与任务文档一致）
- 新增「口径漂移记录」小节：数字→字符串，版本/日期/裁定者

## A5：全局 ok()/fail() 兼容检查

```bash
grep -rn "fail(" edu-agent/app --include="*.py" | wc -l   # 确认所有失败路径走 fail()
grep -rn "ok(" edu-agent/app --include="*.py" | wc -l      # 成功路径走 ok()
# 检查是否有直接 return {"code": 数字} 的散装响应（应统一改走 fail()）
```

---

## 验收标准（修复后）
① 契约测试全绿：字符串断言 + 全 router 遍历（新测试）+ 中间件顺序断言
② 实跑 API：失败响应 `code` 为字符串、`data:null`；成功 `code:0`
③ 交接单 v1.1 与实现/文档三方一致
④ verify_schema.py 0 差异（数据未动回归）

## 新风险与应对
| 风险 | 应对 |
|------|------|
| 字符串码破坏已有前端判断 | 前端尚未开工（task40 未启动），零成本切换窗口 |
| 第三方/存量代码依赖数字码 | A5 grep 排查 + 契约测试兜底 |
| SSE 事件内嵌壳未验证 | 补 SSE 端点测试（done/error 事件内 code 字符串）|

## 实施顺序
A1（30min）→ A2（2h）→ A3（20min）→ A4（10min）→ A5（30min）→ 重跑全部验收
