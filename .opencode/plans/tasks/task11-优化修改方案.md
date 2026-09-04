# task11 优化修改方案（基于技术批判，在现有产物上迭代）

> 依据：`task11-技术批判.md` 3 条批判 ｜ 原则：现有代码迭代，不另起炉灶

## 方案总览

| # | 修改点 | 目标文件 | 优先级 | 工作量 |
|---|--------|---------|--------|--------|
| A | RespWrap S2 headers 透传修复（list→dict） | `edu-agent/app/middleware/resp_wrap.py` | **P0 必做** | 30min |
| B | 契约测试补"匿名 admin 401"用例 + 重跑 24 项全量 | `tests/test_contract_all_routers.py` | P0 必做 | 30min |
| C | 契约回归限流豁免（固定 token 复用） | `tests/test_contract_middleware.py` | P1 | 1h |

---

## A. P0：RespWrap S2 headers 透传修复

### 修改内容（`edu-agent/app/middleware/resp_wrap.py` S2 分支）

```python
# 原（bug）：list of tuples → Starlette init_headers 调 .items() 崩溃
# raw_headers = [(k, v) for k, v in response.headers.items() if k.lower() not in _HOP_BY_HOP_HEADERS]
# return Response(content=body, status_code=response.status_code, headers=raw_headers, media_type="application/json")

# 修复：headers 传 dict（Starlette 最稳语义）
raw_headers = {
    k: v for k, v in response.headers.items()
    if k.lower() not in _HOP_BY_HOP_HEADERS
}
return Response(
    content=body,
    status_code=response.status_code,
    headers=raw_headers,
    media_type="application/json",
)
```

### 关键点
- `response.headers` 是 Starlette Headers（可 .items() 迭代出 (k,v) 对），转 dict 后 Starlette Response 内部 init_headers 走 dict.items() 正常
- 保留 S2 意图（多值头如 Set-Cookie 透传）：dict 对同名多值头只保留最后一个——若测试发现 Set-Cookie 丢失，改用 `response.raw_headers`（bytes 元组列表，Starlette 直接接受）

### 量化指标
- 匿名 `/api/admin/users` → **401 + {"code":"40101","data":null}**
- 登录失败 → 40111 壳；限流 → 429 壳；无 500

### 测试方案
- 新增契约用例：匿名 GET /api/admin/users → 401 + code="40101" + data=null
- 重跑 test_contract_middleware.py + test_contract_all_routers.py 全量

### 新风险与应对
| 风险 | 应对 |
|------|------|
| Set-Cookie 多值头丢失 | 若存在，改 raw_headers bytes 直传 |
| 其他非 2xx 壳路径 | 修复后全量契约测试覆盖 |

---

## B. P0：契约测试补匿名 401 用例 + 全量重跑

### 修改内容（`tests/test_contract_all_routers.py` 新增）

```python
def test_admin_anonymous_401(self):
    """安全补强（task11 批判⑥）：匿名访问管理端点 → 401 壳。"""
    status, _, body = api("GET", "/api/admin/users")
    assert status == 401, f"expected 401, got {status}"
    assert body["code"] == "40101"
    assert body["data"] is None

def test_admin_forbidden_403(self):
    """student 访问管理端点 → 403 壳（require_role）。"""
    # login as stu01test → GET /api/admin/users → 403 + code 字符串
```

### 验收
- 全量契约测试（原 24 + 新增 ≥2）全绿，无 500

---

## C. P1：契约回归限流豁免

### 修改内容（`tests/test_contract_middleware.py`）

```python
# fixture：模块级登录一次复用 token，避免每用例重复登录打满 login 10/min
@pytest.fixture(scope="module")
def admin_token():
    _, _, body = api("POST", "/api/auth/login", body={"account": "adm02test", "password": "Test@123456"})
    return body["access_token"]
# 各用例改用 admin_token，不再各自 login
```

---

## 实施顺序与依赖

```
A（30min）→ B（30min）→ C（1h，可与 A/B 并行）
→ 重启服务（最新代码）
→ 全量重跑：契约 24+2 用例 + task11 26 用例 + verify_schema（0 差异回归）
→ 补跑匿名 401 实测
```

**总工作量 ~2h。验收通过标准 = 匿名 admin 401 + 契约套件全绿 + 无 500。**
