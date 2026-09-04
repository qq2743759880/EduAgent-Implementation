# 功能测试报告 task11（课程域改造）

> 测试人：sd-tester（独立测试，不参与开发）
> 被测服务：http://127.0.0.1:8000（uvicorn 运行中，未重启/未停止）
> 测试文件：`edu-agent/tests/test_course_domain.py`（新增，26 项）
> 测试时间：2026-08-18

## 第 1 次测试

### 判定：PASS

task11 验收标准（GWT①②③④）全部满足，无阻断性缺陷。以下为逐条证据与补充发现。

---

## 一、GWT 逐条验证结果

### GWT① 系列列表（筛选 + 壳契约 + snake_case + page_meta + P95）— ✅ 通过

请求：`GET /api/series?category=编程&delivery_mode=online_live&keyword=信息&page=1&page_size=20`
（库内无"Python"字样数据，keyword 用"信息"等价验证）

| 断言项 | 结果 | 证据 |
|---|---|---|
| 响应壳 | ✅ | `{"code": 0, "message": "ok", "data": {"items": [...], "page_meta": {...}}}`，HTTP 200 |
| sale_status=on_sale | ✅ | 返回项全部 `sale_status == "on_sale"` 且 `delivery_mode == "online_live"`，示例数据 id=2627「信息学竞赛入门班·直播」`min_price="2999.00"` |
| keyword 命中 | ✅ | 每项 `series_name/description/series_code` 三列之一含"信息"（如「信息学竞赛入门班·直播」，描述"校园成长线下的信息学竞赛入门班课程。"） |
| snake_case 字段 | ✅ | 全部字段名匹配 `^[a-z][a-z0-9_]*$`，无 camelCase；必备字段 id/institution_id/delivery_mode/series_code/series_name/sale_status/category_names/created_at/updated_at 齐全 |
| page_meta 五元组 | ✅ | `{page:1, page_size:20, total, total_pages, has_more}`，键集精确匹配，类型正确 |
| P95 < 200ms | ✅ | 实测（预热 2 次 + 采样 20 次）：`min=21.6ms P50=24.2ms P95=45.4ms P99=49.4ms max=49.4ms` |

pytest：`TestSeriesListGwt1` 4/4 PASSED。

### GWT② 旧端点 308 重定向（参数保留）— ✅ 通过

请求（禁自动重定向）：`GET /api/curriculum/series?category=编程&page=2`

| 断言项 | 结果 | 证据 |
|---|---|---|
| 状态码 308 | ✅ | `HTTPError status: 308`（uvicorn 原始响应，未跟随） |
| Location 参数保留 | ✅ | `location: /api/series?category=%E7%BC%96%E7%A8%8B&page=2`，URL 解码后为 `/api/series?category=编程&page=2`（百分号编码为 RFC 3986 规范形式，语义等价） |
| 多参数全量保留 | ✅ | `keyword=信息&sort=price_asc&page_size=50&page=3` → Location 解析后四参数逐一相等 |

全部 5 个旧端点 308 验证（均 PASSED）：

| 旧端点 | 状态码 | Location |
|---|---|---|
| `/api/curriculum/series?category=编程&page=2` | 308 | `/api/series?category=编程&page=2`（编码形式） |
| `/api/curriculum/series/5` | 308 | `/api/series/5` |
| `/api/curriculum/series/5/cohorts` | 308 | `/api/series/5/cohorts` |
| `/api/curriculum/series/5/modules` | 308 | `/api/series/5`（层级已变：模块挂 cohort，重定向到详情） |
| `/api/curriculum/series/5/tree` | 308 | `/api/series/5`（同上） |

pytest：`TestLegacy308Gwt2` 6/6 PASSED。

### GWT③ 层级语义 series→cohorts→modules(挂cohort)→sessions(挂模块)→videos — ✅ 通过

实测完整链路（series 2628「信息学竞赛入门班·录播」）：

```
GET /api/series/2628              → 200 code=0，sale_status=on_sale，cohort_count=3，categories 列表
GET /api/series/2628/cohorts      → 200，3 个班次，每条 cohort.series_id == 2628 ✓（班次挂 series）
GET /api/cohorts/7882             → 200，{cohort, modules}，每 module.cohort_id == 7882 ✓（模块挂 cohort）
GET /api/cohorts/7882/modules     → 200，{cohort_id: 7882, modules[3]}
   └ module 23644「竞赛规则与刷题方法」→ sessions[8]，每 session.series_cohort_course_id == 23644 ✓（课次挂模块）
       └ session0.videos[1]：{id:205699, asset_id:617097, video_code:"VID00617097",
          duration_seconds:7144, resolution_label:"1080p", transcode_status:"completed", ...}
```

关键断言全部通过：模块经 `cohort_id` 外键挂班次（非 series）；课次经 `series_cohort_course_id` 挂模块；视频内嵌课次且 `asset_id/video_code` 齐全。

pytest：`TestHierarchyGwt3` 3/3 PASSED。

### GWT④ Admin 强制鉴权 — ✅ 通过

| 场景 | 结果 | 证据 |
|---|---|---|
| 匿名 `GET /api/admin/users` | ✅ | `401` + `{"code": "40101", "message": "缺少 Authorization 请求头", "data": null}` |
| `Authorization: Basic ...`（非 Bearer） | ✅ | `401` + `code="40101"` + `data:null`，message「Authorization 格式应为: Bearer \<token\>」 |
| `Authorization: Bearer`（无 token） | ✅ | `401` + `code="40101"` + `data:null` |
| `Bearer invalid.token.value` | ✅ | `401` + `code="40101"` + `data:null`（fail-closed） |
| WWW-Authenticate 头 | ✅ | 401 响应含 `WWW-Authenticate: Bearer` |

pytest：`TestAdminAuthGwt4` 5/5 PASSED。

### 参数边界与 404 壳 — ✅ 全部通过

| 用例 | 结果 | 证据 |
|---|---|---|
| `page_size=101` | ✅ 422 壳 | `{"code": "42200", "message": "Input should be less than or equal to 100", "data": [{loc:["query","page_size"],...}]}` |
| `page_size=0` | ✅ 422 壳 | `code="42200"`，`greater_than_equal` 详情指向 `query.page_size` |
| `page=0` | ✅ 422 壳 | `code="42200"`（页码从 1 开始） |
| `delivery_mode=hybrid` | ✅ 422 壳 | `code="42200"`，`string_pattern_mismatch` 指向 `query.delivery_mode` |
| `sort=xxx;DROP TABLE series`（注入尝试） | ✅ 422 壳 | `code="42200"`，pattern 白名单拒绝（排序经 `_SORT_MAP` 白名单映射，无注入面） |
| `GET /api/series/99999999` | ✅ 404 壳 | `{"code": "40400", "message": "系列不存在或已下架", "data": null}` |
| `GET /api/series/99999999/cohorts` | ✅ 404 壳 | 同上 |
| `GET /api/cohorts/99999999` | ✅ 404 壳 | `{"code": "40400", "message": "班次不存在或已下架", "data": null}` |
| `GET /api/cohorts/99999999/modules` | ✅ 404 壳 | 同上 |

pytest：`TestValidation422` 5/5 + `TestNotFound404` 4/4 PASSED。

---

## 二、发现的问题（分级）

无 P0/P1 级阻断问题。以下为记录项：

### 架构薄弱点验证结果

| # | 薄弱点 | 是否命中 | 说明 |
|---|--------|---------|------|
| 1 | 契约回归测试套件 login 限流饱和（P2，既有问题，非 task11 引入） | 命中 | 见问题清单 #1 |
| 2 | 422 壳 data 非 null（P2，task10 既有全局 handler 行为） | 命中 | 见问题清单 #2 |

**问题清单：**

| # | 严重度 | 位置 | 原因 | 修改建议 |
|---|--------|------|------|----------|
| 1 | P2（轻微） | tests/test_contract_middleware.py + tests/test_contract_all_routers.py | 两文件单轮对 `/api/auth/login` 发起 15+ 次调用，而限流规则为 10 次/60s/IP（app/middleware/rate_limit.py:24），同 IP 跑套件必然在中途触发 429 并连锁 FAIL 10 项；与 task11 改造无关（已实验证实：等窗口清空后连打 12 次 login，第 1~10 次 200、第 11~12 次 429 + `Retry-After: 60`） | 契约测试改为模块级 fixture 登录一次复用 token，或测试环境放宽 login 限流 |
| 2 | P2（轻微） | app/handlers（全局 422 handler，task10 既有行为） | 契约文档表述"失败 {code,message,data:null}"，但 422 校验壳的 data 携带 FastAPI 校验详情数组而非 null；行为对前端无害（以 code 判失败），但与文档字面有出入，如实记录 | 在契约文档中补充"422 场景 data 为校验详情"的例外说明 |

**定性说明（问题 #1 根因链）**：`/api/auth/login` 限流 (60s, 10次) → 套件中途 login 返回 429 壳（无 access_token）→ test_contract_all_routers 6 项 `KeyError: 'access_token'` 连锁失败；同时 RateLimitMiddleware 短路在 Trace/SecurityHeaders 之前，429 响应缺 `x-trace-id`/`x-frame-options`/CSP 头 → 3 项中间件头断言连锁失败 + test_rate_limit_on_auth 直接 429。等待 70s 复跑结果相同（套件自身消耗即超限），证明为套件对服务限流状态的固有依赖，**非 task11 代码缺陷**。

---

## 三、pytest 汇总

**本轮新写测试（tests/test_course_domain.py，26 项全过）：**

```
tests/test_course_domain.py — 26 passed
```

**联合运行（task11 + 契约回归，首次）：**

```
.venv\Scripts\python.exe -X utf8 -m pytest tests\test_course_domain.py tests\test_contract_middleware.py tests\test_contract_all_routers.py -v
======================= 10 failed, 41 passed in 10.25s ========================
```

- `test_course_domain.py`：**26/26 PASSED**（GWT①②③④ + 边界全过）
- `test_contract_middleware.py`：11/13 PASSED，2 FAILED（login 限流 429 连锁，见问题 #1）
- `test_contract_all_routers.py`：4/11 PASSED，7 FAILED（同根因：login 429 → KeyError: access_token / 429 响应缺中间件头）

**契约回归 FAIL 原因注明**：10 项 FAIL 均由 `/api/auth/login` 限流（10 次/60s/IP）被测试套件自身打满引起，属服务运行状态依赖的既有测试套件问题，与 task11 改造代码无关（task11 新增的 AdminAuthMiddleware 与课程域端点均不调用 login；已用 12 次 login 连打实验确证限流边界）。

**测试环境**：Windows / Python 3.11.15 / pytest 8.4.2；直连 127.0.0.1:8000（urllib + `ProxyHandler({})` 禁系统代理 + NO_PROXY=127.0.0.1,localhost；308 测试禁自动重定向）。
