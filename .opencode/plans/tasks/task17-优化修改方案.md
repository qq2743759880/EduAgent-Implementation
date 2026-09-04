# task17 优化修改方案（基于技术批判，在现有产物上迭代）

> 依据：`task17-技术批判.md` 3 条批判 ｜ 原则：修复幂等中间件（非 order 业务逻辑）

## 方案总览

| # | 修改点 | 目标文件 | 优先级 | 工作量 |
|---|--------|---------|--------|--------|
| A | 幂等中间件缓存命中剔除 Content-Length 等头 | `app/middleware/idempotency.py` | **P1** | 20min |
| B | task10 契约测试补"重复 key 返回完整 body" | `tests/test_contract_middleware.py` | P1 | 20min |

---

## A. P1：幂等缓存命中剔除长度相关头

### 修改内容（`app/middleware/idempotency.py` 缓存命中分支）

```python
# 原（bug）：
data = json.loads(cached)
return JSONResponse(
    content=data["body"],
    status_code=data["status"],
    headers=data.get("headers", {}),   # 含原始 Content-Length → 与重建 body 不匹配 → IncompleteRead
)

# 改：
data = json.loads(cached)
_HOP_BY_HOP = {"content-length", "transfer-encoding", "content-encoding", "connection"}
headers = {k: v for k, v in data.get("headers", {}).items() if k.lower() not in _HOP_BY_HOP}
return JSONResponse(
    content=data["body"],
    status_code=data["status"],
    headers=headers,   # 剔除长度/编码头，JSONResponse 重新计算 Content-Length
)
```

### 关键点
- JSONResponse 会自动重算 Content-Length（基于 content 序列化后字节数）
- 剔除 transfer-encoding/content-encoding 避免双重编码

---

## B. P1：契约测试补幂等完整 body 断言

### 修改内容（`tests/test_contract_middleware.py`）

```python
def test_idempotency_repeat_full_body(self):
    """重复 Idempotency-Key 返回完整 body（无 IncompleteRead）。"""
    # 首次下单
    status, _, body = api("POST", "/api/trade/order", headers={"Idempotency-Key": "k1"},
                          body={"series_id": 1, "cohort_id": 1}, token=admin_token)
    assert status == 200
    first = body
    # 重复
    status2, _, body2 = api("POST", "/api/trade/order", headers={"Idempotency-Key": "k1"},
                            body={"series_id": 1, "cohort_id": 1}, token=admin_token)
    assert status2 == 200
    assert body2 == first  # 返回首次缓存响应，且 body 完整
```

---

## 量化指标（修复后）

- 幂等重复下单（同 Idempotency-Key）→ **200 + 完整 body**（无 IncompleteRead，Content-Length 正确）
- 返回内容与首次一致（order_no 相同）
- task10 契约测试全绿（含新增幂等 body 用例）

## 新风险与应对

| 风险 | 应对 |
|------|------|
| 其他 hop-by-hop 头（如 set-cookie）| set-cookie 是响应头，保留；只剔长度/编码类 |
| 缓存数据旧格式（无 headers）| data.get("headers", {}) 兜底 |

## 实施顺序

A（20min）→ B（20min）→ 重启 8003 → 实测幂等重复 200 完整 body → task10 契约测试回归
