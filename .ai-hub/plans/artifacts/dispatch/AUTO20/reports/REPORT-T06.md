# REPORT-T06 — 限流前缀收窄（AUTO20 #6）

- 分支：`feature/opt-waves`（开工前 `git branch --show-current` 已核验）
- 日期：2026-09-22
- 状态：✅ 闭环（代码 + 单测 + E2E 三重实证）

## 一、根因（实读代码 + 修复前复现）

**根因 1 — 前缀误伤**：`edu-agent/app/middleware/rate_limit.py` 的 `_get_limit_for_path` 用
`path.startswith(prefix)` 前缀匹配。规则 `"/api/trade/order": (60, 10)`（下单 10 次/60s）
误伤 `GET /api/trade/orders`（订单列表，openapi.json 权威的独立路由）。学生页连续拉订单列表
第 11 次起被 429。

**根因 2 — 429 丢 CORS 头**：`RateLimitMiddleware` 注册在 `CORSMiddleware` 内层（main.py
add_middleware 逆序，CORS 在外层）。限流短路 429 由内层 `JSONResponse` 直接返回，Starlette
CORS 中间件对简单响应不回显 `access-control-allow-origin`（请求头 Origin 命中 allowlist 时
本应回显）→ 浏览器把 429 报成 CORS 错误 → me 页 console-errors 假红（本轮出现 3 次）。

**修复前复现（真实 HTTP，Redis 6377 限流计数清零后）**：

```
GET /api/trade/orders x14 (student user000001):
[200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 429, 429, 429, 429]  ← 第 11 次起 429
Redis 计数器: rl:ip:127.0.0.1:/api/trade/orders = 14（误挂 order 规则直接证据）
429 headers: ['connection','content-length','content-type','date','retry-after','server','x-trace-id']
→ access-control-allow-origin MISSING（浏览器报 CORS 错误的根因）
```

## 二、修法（阈值/窗口一律未动，只改匹配语义 + 补头）

`edu-agent/app/middleware/rate_limit.py` 两处：

1. **匹配收窄**：新增 `_path_in_prefix_scope(path, prefix)`——精确路径或 `prefix + "/"` 子路径
   才命中（段边界匹配）；`_get_limit_for_path` 改为**最长前缀优先**。
   - `/api/trade/orders` 不再命中 `/api/trade/order` 规则 → 落 default(100/min) ✅
   - `/api/trade/order`、`/api/trade/order/{no}`、`/api/trade/order/{no}/cancel` 仍命中原规则 ✅
   - `/api/trade/coupon/receive` 最长前缀优先不被更短前缀截胡 ✅
   - 全部既有阈值/窗口原样保留
2. **429 补 CORS 头**：新增 `RateLimitMiddleware._cors_headers_for(request)`——按与 app 级
   `_cors_origins()` 完全同源的规则回显 `access-control-allow-origin`：
   - DEBUG=true → `*`（与 app 级行为一致，不额外放宽）
   - DEBUG=false → 仅回显 `CORS_ORIGINS` allowlist 命中的精确 Origin + `vary: Origin`；
     未命中 Origin 一律不带（不放宽 CORS 面）
   - 429 短路 JSONResponse headers 并入该结果

**死规则登记（不擅改）**：`"/api/trade/refund"`（实际退款路由是 `/api/refunds`）与
`"/api/after_sales/ticket"`（实际是 `/api/trade/after_sales/ticket*`）两条规则原前缀
永不命中（openapi.json 权威核实）——保留不删、阈值未动，注释内登记待后端统一路由命名时处置。

## 三、修复后实证（真实 HTTP E2E，干净窗口）

```
[1] student login OK (user000001 / Test@123456)
[2] GET /api/trade/orders x12: [200 ×12]  ← PASS：全 200 无 429（修复前第 11 次起 429）
[3] POST /api/trade/order x11: [422 ×10, 429] ← PASS：order 10/min 规则仍在（第 11 次起 429）
    （422 = 故意空 body 校验失败，但限流计数先行，规则语义实证成立）
[4] 429 headers: ACAO=* ACAC=true Retry-After=60 ← PASS：CORS 头不再丢
    （当前 DEBUG=true → *；DEBUG=false 回显精确 Origin 由单测覆盖）
[5] OPTIONS /api/trade/orders → ACAO=http://127.0.0.1:3322 ← PASS：预检不受影响
=== T6 E2E ALL PASS ===
```

对照组（修复前同口径）：orders x14 第 11 次起 429 且 429 无任何 access-control-* 头。

## 四、测试数字

- 新增 `edu-agent/tests/test_rate_limit_prefix_scope.py`：**19 passed**
  （段边界原语 4 / 规则解析 9（含 orders→default、order 子路径不变、coupon/receive 最长前缀、
  每条注册前缀解析回自身） / 中间件级 6（orders 12 连发不 429、order 第 11 次起 429、
  429 带 ACAO、未知 Origin 不补、200 仍带 X-RateLimit-*））
- 定向回归：`pytest tests/ -k "rate or limit or trade" -q` → **64 passed, 6 skipped, 1850 deselected**
  （修复前同口径基线 51 passed → 含新增 19 例中 13 例命中 filter + 既有 45 例零回归）
- 限流专项文件：`test_rate_limit.py + test_redis_outage_fastfail.py` → 修复前 27 passed，修复后同口径全过
- 限流三文件合集：`test_rate_limit_prefix_scope + test_rate_limit + test_redis_outage_fastfail` → **46 passed**
- 全量：`pytest tests/ -q` → **1737 passed, 5 failed, 167 skipped, 11 errors**（8m12s）。
  **失败/报错与本单无关（stash 验证）**：stash 掉本单改动后同 4 例仍失败——
  `test_check_demo_timeouts`（tristate timeout 60s 断言）、`test_febe_contract_check` ×2、
  `test_wnextint1a`（doc_chunk_count=738 数据态断言）；11 errors 全部是
  `TEST_BASE` 默认 127.0.0.1:8000 的存量 HTTP 契约测试（本机后端已迁 9988；
  `TEST_BASE=http://127.0.0.1:9988` 下 `test_course_admin_restore.py` 5 passed 复核）。
  定向口径（-k "rate or limit or trade"）零失败零回归。

## 五、资产消费证据

- 编排者实测根因（本单开工令）：`/api/trade/order` 规则误伤 `/api/trade/orders` + 429 无
  CORS 头 → me 页 console-errors 假红 3 次——与本单复现完全一致
- `queue.md` #6 行（唯一事实源任务定义）+ `AGENTS.md` 关键教训 2（接口验收须真实 HTTP 独立实证）
- openapi.json（`http://127.0.0.1:9988/openapi.json`）核实 `/api/trade/order`（POST）与
  `/api/trade/orders`（GET）为不同路由；退款/工单实际路由与规则前缀不符（死规则登记依据）

## 六、批判自检

- ✅ 阈值/窗口零改动（铁律 3）：仅 `_get_limit_for_path` 匹配语义 + 429 headers，规则表字面未动
- ✅ 死规则只登记不擅改（铁律 3）：`/api/trade/refund`、`/api/after_sales/ticket` 保留 + 注释登记
- ✅ CORS 面不放宽：DEBUG=false 仅回显 allowlist 命中 Origin；未知 Origin 单测断言无 ACAO
- ✅ 单测 mirror E2E：orders 12 连发 / order 第 11 次起 429 / 429 带 ACAO 三条均在单测层有镜像
- ✅ 环境治理顺带修复：本机 Redis 容器（prisma-ai-redis-container-1，6377）未运行会导致限流
  整体降级放行——已 docker start 恢复（否则复现/验收都不成立）
- ⚠️ 遗留登记（不阻塞）：`tests/test_contract_middleware.py` 的 `TestMiddlewareOrder` 是空壳类
  （只有 docstring 无用例），中间件顺序断言实际由 `test_contract_all_routers.py` 承担——本单未动
- ⚠️ `app/common/rate_limit.py`（Phase 1 旧实现，前缀匹配同款）未被 main.py 引用、仅被其自身
  测试 `tests/test_rate_limit.py` 引用——属死代码，本次未改（改其匹配语义会牵动 14 个旧单测，
  收益为零；登记待清理批次处置）

## 资产路径

- 代码：`edu-agent/app/middleware/rate_limit.py`
- 测试：`edu-agent/tests/test_rate_limit_prefix_scope.py`（新增）
- E2E 脚本：本会话内联（`/tmp/t6_e2e2.py` 口径已全文录入第三节）
