# 对抗性测试报告 Task11（课程域 · 新端点攻防）

> 测试人：sd-challenger（对抗测试工程师，只读攻击，不修复）
> 目标服务：http://127.0.0.1:8000（运行中，未重启）｜运行模式：**DEBUG=true**（GET / 确认）
> 攻击脚本：`edu-agent/scripts/_challenge_task11.py`（一次性，留盘作证）
> 原始证据：`test-reports/task11-challenge-raw.json`（56 项逐请求记录）
> 测试时间：2026-08-18

## 第 1 次测试

### 判定：FAIL

**汇总：56 项攻击 → 攻陷 6 类（有效缺陷），壳违规 3 类。SQL 注入 0 攻陷、数据库完好。**

严重度映射：P0=致命（立即利用/数据破坏）｜P1=严重（越权/安全旁路）｜P2=一般（可用性/契约破绽）｜P3=轻微（行为怪癖/规范偏差）

---

## 一、攻击矩阵

### 1. SQL 注入（10 项，0 攻陷 ✅）

| # | 攻击 | 请求（摘要） | 结果 | 攻陷 | 严重度 |
|---|------|------|------|------|--------|
| CA-01 | keyword 恒真注入 | `keyword=' OR 1=1 --` | 200 空列表（仅当字面量） | 否 | - |
| CA-02 | keyword 通配符 | `keyword=%` | 200 全表 LIKE，125.9ms | 否（性能面见 §四） | - |
| CA-03 | category DROP 注入 | `category='; DROP TABLE series;--` | 200 空列表 | 否 | - |
| CA-04/05 | sort 注 SQL 片段 | `sort=price_asc;DROP TABLE series--`、`sort=id DESC--` | 422 壳 `42200`（router regex + repo 白名单双防） | 否 | - |
| CA-06 | page 注入 | `page=1) UNION SELECT 1--` | 422 壳 | 否 | - |
| CA-07 | delivery_mode 注入 | `online_live' OR '1'='1` | 422 壳（pattern 白名单） | 否 | - |
| CA-08 | 时间盲注 | `keyword=_' AND SLEEP(5)--` | 200、42ms（无延迟，未拼接） | 否 | - |
| CA-09 | LIKE 转义符 | `keyword=\` | 200（字面量处理） | 否 | - |
| CA-10 | 数值夹带布尔 | `price_min=0 OR 1=1` | 422 壳 | 否 | - |

**结论**：`series_repo.py` 全部占位符参数化 + `_SORT_MAP` 白名单（series_repo.py:17-22,108）+ router 层 Query pattern 双层防御，注入面未被突破。

### 2. 特殊 ID / 深分页（11 项，1 项行为怪癖）

| # | 攻击 | 结果 | 攻陷 | 严重度 |
|---|------|------|------|--------|
| CA-11/12/13 | id=0 / -1 / 999999999999 | 均稳 404 壳 `40400` | 否 | - |
| CA-14/15 | id=abc / 1.5 | 422 壳 `42200` | 否 | - |
| **CA-16** | **id=" 1 "（URL `%201%20`）** | **200 → 命中 id=1 详情**（Pydantic 宽松 int 解析首尾空白） | **是（行为怪癖）** | **P3** |
| CA-17/18 | cohort abc / -1 | 422 / 404 壳 | 否 | - |
| CA-19 | id=26 位超大整数 | 404 壳 `40400`（合规；脚本初判预期过严，已修正） | 否 | - |
| CA-20 | page=999999（OFFSET≈2000 万） | 200、109ms | 否（2628 行小表；放大风险见 §四） | - |
| CA-21 | page=2147483647&page_size=100 | 200、110.6ms | 否 | - |

### 3. 类型混淆（8 项，1 项攻陷 ⚠️）

| # | 攻击 | 结果 | 攻陷 | 严重度 |
|---|------|------|------|--------|
| CA-22 | price_min=abc | 422 壳 | 否 | - |
| CA-23 | price_min=-1 | 422 壳（ge=0 生效） | 否 | - |
| **CA-24** | **price_min=1e309（float inf）** | **500**：`Pydantic ge=0 对 inf 恒真放行 → inf 直达 SQL → 驱动抛 "inf can not be used with MySQL"**；且 DEBUG=True 下 `data` 字段原文回显该驱动错误（信息泄露面） | **是** | **P2** |
| CA-25 | price_min=nan | 422 壳（ge=0 对 NaN 判 False） | 否 | - |
| CA-26 | 区间倒置 price_min=99999999&price_max=0 | 200、total=0（空集，未报错） | 否 | - |
| CA-27 | page_size=1e2 | 422 壳 | 否 | - |
| CA-28/29 | page=0 / page_size=101 | 422 壳 | 否 | - |

**CA-24 复盘**：`router.py:35` `price_min: Optional[float] = Query(None, ge=0)` 未加 `allow_inf_nan=False`，`inf >= 0` 恒真 → 校验穿透；`price_max` 同款参数同样暴露。同一缺陷模式存在于所有 float 型 Query 参数。

### 4. 参数炸弹（5 项，0 攻陷）

| # | 攻击 | 结果 | 攻陷 |
|---|------|------|------|
| CA-30 | keyword 5000 字符 | 422 壳（max_length=64 拒） | 否 |
| CA-31/32 | 基线 20 条/页 vs 满页 100 条 | 95.4ms vs 100.8ms（无放大） | 否 |
| CA-33/34/35 | category=%、64×%、%_×32 | 132.8 / 125.2 / 115ms（通配符全表 LIKE 未转义，当前可承受） | 否 |

### 5. 308 重定向滥用（5 项，0 攻陷 ✅，1 项壳语义豁免）

| # | 攻击 | 结果 | 攻陷 |
|---|------|------|------|
| CA-36 | `?url=https://evil.com` | 308 → `Location: /api/series?url=https://evil.com`（仅作 query 透传，指向未被劫持） | 否 |
| CA-37 | `?next=//evil.com` | 308 → Location 恒相对路径 `/api/series?...`，无开放重定向 | 否 |
| CA-38 | CRLF `%0d%0a` 注头 | 308，Location 中 CRLF 保持编码态，无头注入 | 否 |
| CA-39 | 重定向层 `/abc` | 422 壳（int 校验前置） | 否 |
| CA-40 | `/api/curriculum/series/..%2f..%2fevil` | 404（uvicorn 解码后无路由匹配，**未穿越**；但 404 为裸 `{"detail":...}` 见 §6） | 否 |

**结论**：`curriculum/router.py:24-27` Location 由固定相对路径 + 原 query 拼接，重定向目标不可控，无开放重定向。308 本身无 JSON 体（RedirectResponse 语义），不判壳违规（契约 GWT② 仅要求 308+参数保留）。

### 6. 鉴权绕过（11 项，2 项攻陷 ⚠️⚠️）

| # | 攻击 | 结果 | 攻陷 | 严重度 |
|---|------|------|------|--------|
| CA-41 | 匿名 /api/admin/users | 401 壳 `40101`（fail-closed 基线成立） | 否 | - |
| CA-42 | /API/ADMIN/users（大小写） | 404（路由大小写敏感，未越权） | 否 | - |
| CA-43 | /api/admin/../admin/users | 401（中间件前缀已命中） | 否 | - |
| CA-44 | /api/x/../admin/users（绕前缀穿越） | 404（Starlette 不归一化 `..`，无路由匹配，未越权） | 否 | - |
| CA-45 | /api%2Fadmin%2Fusers（编码变体） | 401（uvicorn 解码后仍被中间件拦截） | 否 | - |
| CA-46 | X-Original-URL 伪造 | 401（无网关头信任逻辑） | 否 | - |
| CA-47 | X-Force-Role: admin → /api/admin/* | 401（**AdminAuthMiddleware 确实堵死 DEBUG 后门**，auth_middleware.py:120-143） | 否 | - |
| CA-48 | 坏 token + X-Force-Role 双打 | 401 | 否 | - |
| **CA-49** | **X-Force-Role: admin → /api/mcp/servers** | **200**（require_role 依赖层被 dependencies.py:78-102 DEBUG 后门击穿；响应为裸分页 dict，无壳） | **是** | **P1** |
| **CA-50** | **完全匿名 → /api/mcp/servers** | **200**（dependencies.py:116-127：DEBUG=true 且无 Authorization → 直接返回虚拟超级管理员） | **是** | **P1** |
| CA-51 | /api/admin/（裸前缀） | 401 | 否 | - |

**CA-49/50 复盘（task11 批判⑥ 补强的盲区）**：AdminAuthMiddleware 的保护面是 `ADMIN_PREFIX = "/api/admin/"`（auth_middleware.py:118），而同为**管理员专用**的 `/api/mcp/*`（mcp/router.py:36-40 `require_role([ADMIN])` 整路由）不在其列，仅靠依赖层鉴权——依赖层又被 DEBUG 虚拟用户规则②和 X-Force-Role 规则①旁路。当前服务以 DEBUG=true 运行，**任何人无凭证即可枚举 MCP Server 注册表**（含 server_code/transport/创建人等管理面数据；若列表含凭证类字段则升级 P0）。向上抽象：凡是"不在 /api/admin/ 前缀下、又依赖 get_current_user/require_role 的管理员端点"，在该 DEBUG 运行形态下全部裸奔。

### 7. 响应壳一致性（全量校验 + 4 项专项，3 类违规 ⚠️）

| # | 攻击 | 结果 | 攻陷 | 严重度 |
|---|------|------|------|--------|
| CA-52 | GET /api/nonexistent | 404 → **裸 `{"detail":"Not Found"}`**（FastAPI Router 默认响应，不经 main.py 的 HTTPException handler） | **是** | **P2** |
| CA-53 | POST /api/series（405） | 405 → **裸 `{"detail":"Method Not Allowed"}`** | **是** | **P2** |
| CA-42/44/40 | 大小写/穿越/编码变体落空路由 | 同上裸 `{"detail":...}` | 并入上行 | - |
| **CA-55** | 连发 110 请求触发限流 | 429 → `{code: 42900(int), message, data}` — **code 为数字，违反契约①"code 字符串"**（rate_limit.py:126） | **是** | **P3** |
| CA-49/50 | mcp 越权响应 | 裸 `{items,page,page_size,total}` 无壳（P8 旧路由未实施 task10 壳） | 并入 §6 | - |
| — | 其余全部 4xx/500 | 均为 `{code:<str>, message, data}` 合规壳 | 否 | - |

**壳复盘**：main.py:240-256 注册的 `http_exception_handler` 只覆盖**路由匹配后抛出**的 HTTPException；Starlette Router 对**未匹配路由**的 404/405 直接给默认响应，不经过任何 app 级 handler，RespWrapMiddleware 又是纯透传占位（resp_wrap.py:30-37"当前版本仅做透传"）→ task10"100% 统一壳"验收在 404/405 维度存在盲区。

---

## 二、数据完整性验证（攻击后）

```
mysql> SELECT COUNT(*) FROM series;              → 2628（与基线一致 ✅）
mysql> SELECT COUNT(*) FROM dim_course_category; → 96
mysql> SELECT COUNT(*) FROM series_cohort;       → 7884
```

DROP/UNION/SLEEP 全部注入发出后表结构与行数完好 → 只读攻击承诺兑现，无数据破坏。

## 三、验收标准盲区（dev-plan task11）

- 验收① 只写"全筛选参数可用 + P95<200ms"，**未定义非法参数域**（inf/NaN/超大 int/通配符%）→ CA-24 类 500 直接漏网。
- 验收② "层级语义与 edu.sql 一致" 未约束**输入规范化**（" 1 " ≡ 1）与深分页上界（page 无 le）。
- 批判⑥ 补强只盯着 `/api/admin/*` 前缀，**未盘点全部管理员端点的路由前缀分布** → /api/mcp/* 旁路。

## 四、架构级提示（当前未爆、放大后悬崖）

1. **LIKE 通配符未转义**（series_repo.py:35,82）：`%`/`_` 直进 LIKE。2628 行 ~130ms；行数×1000 后 `%%` 前缀无法走索引，列表主入口将退化为全表扫描。
2. **OFFSET 深分页**：page 无上限。当前 110ms；数据放大后 OFFSET 扫描成本线性增长，建议 keyset 分页或 page 上限。

## 五、结论与问题清单

| # | 缺陷 | 位置 | 严重度 | 建议（供修复方参考，本角色不实施） |
|---|------|------|--------|------|
| 1 | DEBUG 虚拟管理员/X-Force-Role 旁路 `/api/mcp/*` 管理员端点，匿名 200 | dependencies.py:78-127 + mcp/router.py:36-40 | **P1** | AdminAuthMiddleware 保护面前缀化枚举所有管理端点；或 DEBUG 后门按环境开关收敛为仅测试钩子 |
| 2 | `price_min/price_max=1e309`(inf) → 500，且 DEBUG 下回显驱动错误文本 | domains/course/router.py:35-36 | **P2** | Query 增加 `allow_inf_nan=False`（或改 Decimal），422 前置拒绝 |
| 3 | 未匹配路由 404/405 返回裸 `{"detail":...}`，破统一壳契约 | main.py 路由层默认响应 + resp_wrap.py 占位透传 | **P2** | 404/405 响应壳化（自定义 Router 默认 handler 或 RespWrapMiddleware 落地实包） |
| 4 | 429 限流壳 code=42900 为 int 非字符串 | middleware/rate_limit.py:126 | **P3** | 改 `"42900"` 字符串 |
| 5 | `" 1 "` 宽松解析为 id=1（同资源多 URL 别名） | Pydantic int 路径参数默认行为 | **P3** | 可接受；如需严格可加 conint/regex 路径约束 |
| 6 | LIKE 通配符未转义 + page 无上限（放大后性能悬崖） | series_repo.py:35,82 / router.py:38 | **P3（当前）** | 转义 `%`/`_`；page 设 le 上限或 keyset 分页 |

**判定 FAIL**：存在 P1 越权 1 项、P2 缺陷 2 项、P3 缺陷 3 项。SQL 注入与开放重定向防线经攻击验证成立；鉴权补强（批判⑥）在自身覆盖面内成立、但覆盖面选择失当。

— sd-challenger 署
