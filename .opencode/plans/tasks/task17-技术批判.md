# task17 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task17 trade/order 域（Trae，commit fee42de）
> 结论：**⛔ 验收不通过（P1）**——资金安全红线/下单/取消全过，但**幂等中间件缓存命中 IncompleteRead**（HTTP 层幂等路径损坏）

---

## 实证结果（8003 最新代码服务）

| 项 | 实测 | 判定 |
|----|------|------|
| ① 下单 + 篡改价无效 | ✅ order_no=1-260821122219-e319b4, pay_amount=4999.0（sale_price 服务端重算，非篡改 1）| 通过 |
| ③ 取消 pending→cancelled | ✅ cancelled:True + order_no 回显 | 通过 |
| orders 列表 | ✅ 200 + total=2 | 通过 |
| **② 幂等（同 Idempotency-Key 重复）** | ❌ **IncompleteRead(37/319)**——缓存命中响应 Content-Length 与 body 不匹配 | **P1 不通过** |
| 资金安全红线代码 | ✅ sale_price 唯一价源 / payable 服务端算 / 请求体无价格 / order_no 唯一键 / 保留字反引号 | 通过 |
| 100 并发幂等 | ✅ 报告 smoke：DB 唯一键拒绝重复（仅 1 条）——但这是**服务层**，HTTP 层中间件缓存有问题 | 部分 |

## 批判 1（P1 阻塞）：幂等中间件缓存命中 IncompleteRead（Content-Length 不匹配）

**问题描述**：`Idempotency-Key` 重复下单时，幂等中间件命中缓存返回：
```python
data = json.loads(cached)
return JSONResponse(content=data["body"], status_code=data["status"], headers=data.get("headers", {}))
```
`data["headers"]` 是首次响应存的 `dict(response.headers)`，**含原始 `Content-Length: 356`**——但重建 body 序列化后长度 ≠ 356（或 JSONResponse 重新编码）→ 客户端按 Content-Length=356 读取，实际收到 37 字节 → **IncompleteRead**。

**证据来源**：
- 实测：首次下单 200 len=356 content-length=356；幂等重复 IncompleteRead(37 bytes read, 319 more expected)
- idempotency.py 源码（缓存命中 headers 透传未剔除 Content-Length）

**与正确做法差距**：缓存命中重建响应时，**必须剔除 Content-Length/Content-Encoding/Transfer-Encoding 等 hop-by-hop 头**，让 JSONResponse 重新计算长度；或改用 `data["body"]` 直接回写。

**优化方案**（idempotency.py，~20min）：
```python
# 缓存命中时剔除长度相关头
import itertools
skip = {"content-length", "transfer-encoding", "content-encoding", "connection"}
headers = {k: v for k, v in data.get("headers", {}).items() if k.lower() not in skip}
return JSONResponse(content=data["body"], status_code=data["status"], headers=headers)
```

**最小验证方法**：幂等重复下单 → 200 + 完整 body（无 IncompleteRead）。

**预期收益与成本**：收益=HTTP 层幂等路径可用（task10 幂等中间件也受益）；成本=20min。

## 批判 2（P2）：task10 幂等中间件同款问题（历史遗留）

**问题描述**：task10 验收时幂等测试（test_idempotency_key_present）只验证"key 存在"未验证"缓存命中返回完整响应"——同款 Content-Length bug 自 task10 就存在，task17 暴露。

**证据来源**：task10 契约测试（仅断言 idempotency key 相关，未做重复请求 body 完整性）。

**优化方案**：修复 idempotency.py（批判 1）后，task10 契约测试补"重复 key 返回完整 body"断言。

## 批判 3（P2）：报告声称 100 并发幂等通过（服务层），但 HTTP 层中间件幂等路径损坏未暴露

**问题描述**：报告"100 并发同订单仅 1 条"是**服务层 DB 唯一键**验证（正确），但**未验证 HTTP 层幂等中间件缓存命中**（IncompleteRead 未发现）。两层幂等都要验证。

**证据来源**：报告 §验收证据（100 并发 DB）；实测 HTTP 幂等 IncompleteRead。

**优化方案**：修复后补 HTTP 层幂等重复测试（同 key 返回原单 + 完整 body）。

## 汇总

| GWT | 结果 |
|-----|------|
| ① 单事务下单 + 篡改价无效 + 券核销 | ✅ 实测 pay_amount=4999 服务端重算 |
| ② 并发同 order_no 幂等 + 非法迁移 409 | ⚠️ 服务层 DB 唯一键 ✓，但 HTTP 层中间件 IncompleteRead ❌ |
| ③ 取消 + 券回滚 + 余位释放 | ✅ cancelled 实测 |
| ④ 事务回滚 | ✅ 纯 SQL 无 LLM/Redis |

**结论：task17 验收不通过（P1 幂等中间件 IncompleteRead）**。修复 idempotency.py（剔除 Content-Length）+ 补 HTTP 幂等测试后复验。契约冻结⑧ 暂缓解锁前端 task64。
