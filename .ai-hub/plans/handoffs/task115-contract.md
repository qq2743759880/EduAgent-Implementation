# task115 契约冻结单（C-B）— 分页 DTO 全站统一 + chat SSE `error` 事件

- **域**：后端契约 ｜ 编号：**C-B** ｜ 状态：待验收 →（独立实证后）已实证
- **前置**：task114（C-A 壳统一）已合入 —— 本契约在 C-A 的 `{code,message,data}` 壳之上变更 `data` 内部分页结构 + SSE 错误分支
- **实证实例**：`MYSQL_HOST=127.0.0.1`、`DEBUG=true`、隔离端口 **8078**（托管 8000 由编排者复验）
- **改动文件（后端）**：
  - `app/domains/course/schemas.py`（`SeriesListData`/`CohortListData`）
  - `app/domains/course/service.py`（`list_series`/`list_cohorts`）
  - `app/chat/router.py`（`chat_stream_sse` 生成器 error 分支）
- **未改动**：`resp_wrap.py` / `users/router.py` / progress（C-A 成果，本轮未动）；schemas.py 无关域；前端静态页只读核对未改。

---

## 1. 分页 DTO 统一（课程域 `{items,page_meta}` → 全站 `{total,page,page_size,items}`）

### 1.1 统一前（C-A 基线，task114 契约 §4 已记录）
```json
// GET /api/series  → data 内（包在 C-A 壳里）
"data": { "items": [ {...} ], "page_meta": { "page":1, "page_size":20, "total":2628, "total_pages":132, "has_more":true } }
```

### 1.2 统一后（8078 实测 curl）
```bash
curl -s "http://127.0.0.1:8078/api/series?page=1&page_size=3" -H "Authorization: Bearer <student>"
```
```json
{
  "code": 0, "message": "ok",
  "data": {
    "total": 2628,            // ★权威字段（外层，与全站其余域一致）
    "page": 1,                // ★权威字段
    "page_size": 3,           // ★权威字段
    "items": [ { "id": 2628, "series_name": "信息学竞赛入门班·录播", ... } ],
    "page_meta": {            // 兼容窗口：同源派生，禁止改值；弃用时间表见 §3
      "page": 1, "page_size": 3, "total": 2628, "total_pages": 876, "has_more": true
    }
  }
}
```
**机器断言（PowerShell jq 等价）**：`data.total==data.page_meta.total`、`data.page==data.page_meta.page`、
`data.page_size==data.page_meta.page_size` → 三者均 `True`（实测通过）。

### 1.3 第二个分页端点 `/api/series/{series_id}/cohorts`（8078 实测）
```json
"data": { "total": 3, "page": 1, "page_size": 3,
          "items": [ {...3 个班次...} ],
          "page_meta": { "page": 1, "page_size": 3, "total": 3, "total_pages": 1, "has_more": false } }
```

### 1.4 权威字段语义
| 字段 | 类型 | 说明 | 是否含于 page_meta |
|---|---|---|---|
| `total` | int | 总记录数 | ✅（同源） |
| `page` | int | 当前页，从 1 起 | ✅ |
| `page_size` | int | 每页条数（请求值，1~100；cohorts 全集填充为总数） | ✅ |
| `items` | array | 列表项 | ❌ |
| `has_more` / `total_pages` | bool / int | 过渡期扩展字段，仅 page_meta 内；前端建议改为 `page*page_size < total` 计算 | 内置 |

**前端切换指引**：权威读 `{total,page,page_size,items}`；`has_more`、`total_pages` 不再下发到外层，
前端可用 `Math.ceil(total/page_size)` / `page*page_size < total` 自行计算（契约单明确）。

---

## 2. chat SSE `error` 事件（两段式错误模型）

### 2.1 两段式错误模型（写进契约）
| 阶段 | 触发点 | 响应形态 | 实证片段 |
|---|---|---|---|
| **第一段：连接前失败** | `service_chat_stream` 初始化抛错（鉴权失败 / 参数错 / 入参会话不存在等），**握手/建连之前** | 普通 HTTP 状态码 + JSON 壳（非 SSE），前端用 fetch `!resp.ok` 分支 | 见 §2.3 |
| **第二段：流中失败** | SSE 已建连、`start/retrieval` 已发，token 迭代抛未捕获异常（如 LLM 下游故障逃逸出 `generate_stream`） | 发 `event: error` + `data:{"code","message"}`，随后**安全收束**（返回，连接正常关闭，不再发 done、不悬挂） | 见 §2.4 |

### 2.2 SSE 事件结构（token/done 沿用 C-A / AGENTS 教训③）
- `token` 事件字段仍为 **`delta`**（非 `token`，AGENTS 教训③，本轮未改）；
- `done` 事件 data 仍为**嵌套壳** `{code:0, data:{...}}`（C-A 契约①例外，未改）；
- 新增 `error` 事件：`event: error` + `data:{"code":"50000","message":"答案生成失败：<异常类型>"}`；
  **code 常量复用 `INTERNAL_ERROR="50000"`**（error_codes 注册表），不新造野码。

### 2.3 第一段失败（真实 curl，8078）
```bash
curl -s "http://127.0.0.1:8078/api/chat/stream" -X POST -H "Content-Type: application/json" \
     -H "Authorization: Bearer garbage.invalid.token" -d '{"query":"x","stream":true}'
```
```text
HTTP 401
{"code":"40101","message":"登录凭证无效","data":"sub_code=AUTH_TOKEN_INVALID"}
```
→ **非 SSE**（无 `event:` 行），符合"连接前失败走普通 HTTP"。

### 2.4 第二段失败（SSE 抓包，隔离进程真实 ASGI HTTP，脱敏后）
> 触发方式：monkeypatch `service_chat_stream` 返回的 `token_aiter` 在 token 迭代中途抛 `RuntimeError`（模拟 LLM 下游故障），
> 请求打到**真实 router 生成器**。HTTP 200（SSE 已建连），流按序输出后终止、不悬挂。
```text
HTTP status    : 200
contains_error : True
contains_code  : True  (INTERNAL_ERROR=50000)
contains_done  : False  (error 分支不应再有 done)

event: start
data: {"session_id": "fake-sess", "query": "触发流式错误"}

event: retrieval
data: {"docs": [], "graph_entities": [], ...}

event: token
data: {"delta": "部"}

event: token
data: {"delta": "分内容"}

event: error
data: {"code": "50000", "message": "答案生成失败：RuntimeError"}
```
→ 连接在 `error` 后正常收束（无 done、无悬挂）。

### 2.5 与 C-A 壳的关系
- SSE 流是 C-A resp_wrap 中间件的**白名单透传类型**（`text/event-stream`，不包壳）；
  流内事件以 `event: X` + `data: JSON` 独立成帧，不套 `{code,message,data}` 外层（契约①已约定，SSE 例外）。
- 其中第一段（连接前）的失败仍走全局/中间件普通壳（HTTP 状态码 + JSON 壳）。
- `done` 事件 data 内嵌统一壳 `{code:0, message:"ok", data:{...}}` 是唯一"流内嵌壳"例外，与 C-A 幂等边界一致。

---

## 3. 兼容窗口与弃用时间表（写进契约，交 CDC 核验）

**策略**：课程域 `page_meta` 保留一个迭代期（值同源派生、只读），权威读外层 `{total,page,page_size,items}`。

| 阶段 | 时间 | page_meta 状态 | 说明 |
|---|---|---|---|
| 过渡期（本期，C-B 合入后） | 本迭代 | **保留**（同源派生） | 老前端 courses.html:597/admin-courses.html:643 仍读 page_meta，过渡期不坏；新前端切外层字段 |
| 弃用期（前端 task103 切换完成后） | 下一迭代 | **移除** | 删除 schemas 中 `page_meta` 字段与 service 派生逻辑；此时权威外层字段已全覆盖 |
| 终态 | 之后 | 不存在 | 全站唯一 `{total,page,page_size,items}` |

**防歧义红线**：双字段并存期内，`page_meta` 值一律由 `total/page/page_size` 派生，**禁止单独改值**，
否则"老读新"产生不一致（audit 风险点）。切换完成后必须删除 `page_meta`，不留双源。

---

## 4. 前端消费面核对（只读，未改 FE）
- **courses.html**（L597-599）：`const pm = d.page_meta; const total=pm.total; const tPages=pm.total_pages ?? ceil(...)` —— 兼容期读 page_meta，正常；后续切 `d.total/d.page_size`。
- **admin-courses.html**（L643-662）：`pm.total_pages`/`pm.page`/`d.page_meta.total` —— 同理兼容期可用。
- **chat.html**（L741/747/742）：`token`→`j.delta`、`error`→`er.message`、`done`→嵌套壳解包 —— 与本契约对齐，error 分支现真实可达。

---

## 5. 验收要点（codex L1 / CDC 核验清单）
1. 课程域 list/search 响应 `data` 层含权威 `{total,page,page_size,items}`（`/api/series`、`/api/series/{id}/cohorts`）。
2. 兼容窗口期 `page_meta` 存在且 `total/page/page_size` 与外层同源一致（实测断言全 True）。
3. `/api/chat/stream` 两段式错误：连接前失败普通 HTTP（401 实测）；流中失败 `event: error`+data{code,message} 后安全收束。
4. SS token 事件字段 **delta**、done 嵌套壳**未回退**（回归 token 冒烟通过）。
5. 回归：`interface_acceptance_final.py`（编排者 8000 复验）+ chat 流式冒烟（token 事件正常，8078 已实测）。
6. 兼容窗口弃用后删除 `page_meta`（时间表见 §3），不留双源。