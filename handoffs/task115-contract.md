# 契约冻结单 C-B · task115 — 分页 DTO 全站统一 + chat SSE `error` 事件

> 状态：**FROZEN（冻结）** ｜ 域：后端契约 ｜ 编号：C-B ｜ 前置：task114（C-A）已合入
> 实证实例：`127.0.0.1:8000`（托管实况，DEBUG=true）、登录态 student `user000001`。
> 收口说明（客观、不夸大）：本契单归档的实质契约变更已在历史 commit 落地——
> C2 分页 `page_meta` **双轨移除** `155b4b0`（后端删双字段）+ `35b94fe`（前端迁外层 triple）、C3 chat SSE
> 错误统一 `65b31a2`（`_map_stream_exception` + 两段式 error）；本次仅补契单归档 + curl 实测复验。
> 全部"真实输出"证据来自 live 8000 抓包 + 契约单测（`test_chat_stream_error.py`，W2 C3 SSE 契约测试）。

---

## §0 验证约束

- 端口 **8000** 当前实况；请求均带真实 `Bearer`。
- 分页需不带 token 的 DEBUG 虚拟管理员**不得**作为证据——一律走真实 student token + urllib 抓包（`test-reports/_probe_114_115.py`）。

---

## §1 分页 DTO 统一（课程域权威 `{total, page, page_size, items}`，page_meta 已移除）

### 1.1 权威结构（实测 curl）
```bash
GET /api/series?page=1&page_size=2
```
```json
{
  "code": 0, "message": "ok",
  "data": {
    "total": 2628,          // ★权威字段
    "page": 1,              // ★权威字段
    "page_size": 2,         // ★权威字段
    "items": [ { "id": 2628, "series_name": "信息学竞赛入门班·录播", ... }, ... ]
    // 无 page_meta —— C2 已移除，双轨不复存在
  }
}
```

### 1.2 权威字段语义
| 字段 | 类型 | 说明 |
|---|---|---|
| `total` | int | 总记录数 |
| `page` | int | 当前页，从 1 起 |
| `page_size` | int | 每页条数（请求值，1~100） |
| `items` | array | 列表项 |

### 1.3 机器断言（`_probe_114_115.py` 实证，PASS）
`data.total==2628 >=0`、`data.page==1`、`data.page_size==2`、`data.items` 为数组、`"page_meta" not in data` —— **全 PASS**。

### 1.4 `page_meta` 移除时间表（写进契约，C2 已移除，声明不再二轨）
> C2 批判后，`page_meta` 双字段已**直接从 schemas + service 派生逻辑删除**（`155b4b0`），前端已迁外层
> `{total,page,page_size,items}`（`35b94fe`）。**不再存在兼容双窗口**，唯一权威即外层三元组。
> 旧 `.ai-hub/plans/handoffs/task115-contract.md` 草案里的"page_meta 兼容期"已过时作废，以本契单为准。

---

## §2 chat SSE `error` 事件（两段式错误模型，C3 落地）

### 2.1 两段式错误模型（写进契约）
| 阶段 | 触发点 | 响应形态 | 实证 |
|---|---|---|---|
| **第一段：连接前失败** | `service_chat_stream` 初始化抛错（鉴权失败 / 参数错 / 入参会话不存在），SSE 尚未握手 | 普通 HTTP 状态码 + JSON 壳（**非 SSE**），前端 `!resp.ok` 分支 | §2.3 |
| **第二段：流中失败** | SSE 已建连、START/RETRIEVAL 已发，token 迭代抛未捕获异常（LLM 下游故障逃逸出 `generate_stream`） | 发 `event: error` + `data:{"code","message"}`，随后**安全收束**（return 关流，不再发 done、不悬挂） | §2.4（用契约单测注入触发，不破坏性打 live） |
| **第三段：落库失败** | 生成成功但 `build_finalize` 抛错 | `event: error` code=`CHAT_PERSIST_FAIL`，随后降级 `done`（带 `degraded_reason`）兜底，不静默 | §2.4 测试 (c) |

### 2.2 SSE 事件结构（token/done 沿用）
- `token` 事件字段为 **`delta`**（非 `token`，AGENTS 教训③，未回退）。
- `done` 事件 data 仍为嵌套壳 `{code:0, message:"ok", data:{...}}`（C-A 契约① SSE 例外）。
- 新增 `error` 事件：`event: error` + `data:{"code":"<LLM_*|CHAT_PERSIST_FAIL>","message":"<可读原因>"}`；
  code 取自 `_map_stream_exception`（`LLM_AUTH`/`LLM_TIMEOUT`/`LLM_RATE_LIMIT`/`LLM_UNAVAILABLE`/`SERVICE_DOWNSTREAM`），
  **不再固定 50000 单调**（audit P1-10 / W2 C3 提升）。

### 2.3 第一段失败（真实 curl，8000 实测）
```bash
POST /api/chat/stream  body={"query":"x","stream":true}  Authorization: Bearer garbage.token
```
```text
HTTP 401   Content-Type: application/json
{"code":"40101","message":"登录凭证无效","data":"sub_code=AUTH_TOKEN_INVALID"}
```
**非 SSE**（无 `event:` 行），符合"连接前失败走普通 HTTP"。

### 2.4 第二/三段失败（契约单测注入，不破坏性打 live）
**未强制破坏性触发 live LLM 故障**（避免污染 8000 实况），改用既有 W2 C3 契约测试 `tests/test_chat_stream_error.py`
（httpx ASGITransport 打真实 router + monkeypatch `service_chat_stream` 注入故障）实证：
- (a) 正常 token 流：`start → retrieval → token{delta} → done{code:0,...}`，无 error（PASS）。
- (b) 注入 token 迭代抛 `RuntimeError("LLM HTTP 401 ...")` → 流内 `event: error` code=`LLM_AUTH`≠50000（PASS）；
  注入 `TimeoutError` → code=`LLM_TIMEOUT`（PASS）；`_map_stream_exception` 全分支映射表（PASS）。
- (c) 注入落库失败 → `event: error` code=`CHAT_PERSIST_FAIL` + `generated_tokens` 回传 + 降级 `done` 兜底（PASS）。
- 验收运行：`pytest tests/test_chat_stream_error.py tests/test_contract_task116.py tests/test_contract_task113.py` → **29 passed**。

### 2.5 与 C-A 壳的关系
- SSE 流是 `resp_wrap` 中间件**白名单透传类型**（`text/event-stream`，不包壳），流内事件独立成帧。
- 其中第一段（连接前）失败仍走全局/中间件普通壳（HTTP 状态码 + JSON 壳）。
- `done` 事件内嵌壳是唯一"流内嵌壳"例外，与 C-A 幂等边界一致（router.py:349-354）。

---

## §3 消费方核对（只读，未改 FE）

- **courses.html**（L573-575）：`const items = d.items; const total = d.total` —— 已迁外层 `{total,page,page_size,items}`，**无 page_meta 引用**。
- **admin-courses.html**（L658-684）：`d.page_size` / `d.items` / `d.total` —— 读外层三元，**无 page_meta 引用**。
- 全 `public/*.html` grep `page_meta` → **0 处**（C2 前端迁移完成，外层 triple 消费，无残留）。
- **chat.html**：`token→j.delta`、`error→er.message`、`done→嵌套壳解包`（C-A 教训③ + §2.2 对齐），error 分支真实可达。

---

## §4 Files（实现载体）

| 文件 | 说明 |
|---|---|
| `app/domains/course/schemas.py`（41-47 `SeriesListData`、100-106 `CohortListData`） | 分页仅 `{total,page,page_size,items}`，标注"C2 已删 page_meta 双轨" |
| `app/domains/course/service.py` | `list_series`/`list_cohorts` 派生外层三元，无 page_meta |
| `app/chat/router.py`（256-364 `chat_stream_sse`） | 两段式错误：连接前 try/except→同步 HTTP；`_gen()` 内 token 段 catch→`event:error`；`build_finalize` 段→`CHAT_PERSIST_FAIL`+降级 done |
| `app/chat/router.py`（89-129 `_map_stream_exception`） | 错误码映射表（LLM_* 可区分，非 50000 单调） |
| `app/chat/schemas.py` `SseEventType` | `start/retrieval/token/done/error` 事件枚举 |

---

## §5 验收要点（CDC 核验清单）

1. `/api/series?page=1&page_size=N`：`data` 含权威 `{total,page,page_size,items}`，**无 page_meta**（实测 6 断言 PASS）。
2. `/api/chat/stream` 两段式错误：连接前失败普通 HTTP（401 实测非 SSE）；流中失败 `event: error`+data{code,message} 后安全收束。
3. token 事件字段 **delta**、done 嵌套壳**未回退**（`test_chat_stream_error.py` (a) PASS）。
4. error code 不再固定 50000 单调：`LLM_AUTH/LLM_TIMEOUT/LLM_RATE_LIMIT/LLM_UNAVAILABLE/SERVICE_DOWNSTREAM/CHAT_PERSIST_FAIL` 可区分（映射表 PASS）。
5. 前端消费方已迁外层 triple（0 处 page_meta），chat.html delta/error 对齐。