# critique-C3 完工报告：SSE 错误通道统一

- 日期：2026-09-04

- 角色：tt 工作流 · 后端批判落地子 agent

- 范围：`edu-agent/app/chat/router.py`（`chat_stream_sse`）+ `app/common/error_codes.py`（登记）+ `tests/test_chat_stream_error.py`（新增契约测试）

- 不 commit（契约未验收，按 tt 纪律等待统一 commit）

## 背景与问题（W2 批判 C3 复述）

`chat_stream_sse` 此前三通道并存、可观测性不足：

1. 连接前（`service_chat_stream` 抛错）→ 同步 HTTP——**C3.1 认可为合理取舍**，保留。
2. 流内 token 迭代失败 → `event: error` 但 code **硬编码** **`INTERNAL_ERROR`(50000)**，各种下游失败（auth/timeout/限流）不可区分。
3. 落库（`build_finalize`）失败 → **静默**只塞进 `done.degraded_reason`，对用户透明，前端可观察 error 分支永远不可达。

目标：token/落库两类「流已建连」失败统一转 `event: error`，且带**可区分错误码**，不再 50000 单调或静默。

## 改了什么契约语义（关键）

- **契约外形未变**：done 事件仍内嵌 `{code:0, message:"ok", data:{...}}`；token 事件字段仍为 `delta`；start→retrieval→token 帧序不变。

- **错误语义从静默→显式**：

  - token 迭代失败：`code` 从固定 `50000` → 可区分下游码（`LLM_AUTH`/`LLM_TIMEOUT`/`LLM_RATE_LIMIT`/`LLM_UNAVAILABLE`/`SERVICE_DOWNSTREAM`）。

  - 落库失败：新增显式 `event: error`（`code=CHAT_PERSIST_FAIL`，附 `generated_tokens`/`message_id` 占位），并补一个带 `degraded_reason` 的 done 兜底——不再对用户静默。

  - 连接前失败仍走同步 HTTP（保持双通道取舍），**新增两段式契约注释明确**「连接前→HTTP；建连后（token/落库）→流内 error」，防止后人误改。

## 改动清单

`app/common/error_codes.py`（新增 5001x 问答/LLM 下游段）：

| 码                    | 值     | 语义                                          |
| -------------------- | ----- | ------------------------------------------- |
| `LLM_AUTH`           | 50011 | LLM 下游鉴权/密钥失效（401/403/auth/invalid api key） |
| `LLM_TIMEOUT`        | 50012 | LLM 下游超时（无增量 60s/timeout）                   |
| `LLM_RATE_LIMIT`     | 50013 | LLM 下游限流/额度（429/rate limit/quota）           |
| `LLM_UNAVAILABLE`    | 50014 | LLM 下游不可达（连接失败/下游 5xx）                      |
| `SERVICE_DOWNSTREAM` | 50015 | 生成期其它下游未归类兜底                                |
| `CHAT_PERSIST_FAIL`  | 50016 | 流式答案已生成但落库失败                                |

`app/chat/router.py`：

- 导入改为（去掉不再使用的 `INTERNAL_ERROR`，新增 `re` 与 6 个码）。

- 新增 `_map_stream_exception(e) -> (code, message)`（约 40 行）：匹配顺序为 ①Timeout 特征词 → ②LLM HTTP 状态码（`re.search(r"http\D{0,4}(\d{3})")`，401/403→AUTH，429→RATE\_LIMIT，≥500→UNAVAILABLE）→ ③语义/类型特征 → ④兜底 SERVICE\_DOWNSTREAM。

- 连接前 except：新增「两段式错误模型 · 第一段」注释（C3.1 取舍）。

- token 迭代 except：`code, msg = _map_stream_exception(e)`（原固定 50000）。

- 落库失败 except：显式 `event: error`（`CHAT_PERSIST_FAIL` + `generated_tokens` + `message_id:None`）+ 降级 done 兜底，均新增。

- **修复**：补回被编辑过程误删的「正常路径 done 事件」（`done 壳 {code:0...}`），确保非错误流仍以 done 收尾。

`tests/test_chat_stream_error.py`（新增 5 用例）：用 httpx ASGITransport 打真实路由 + monkeypatch `chat_router.service_chat_stream`，不依赖 live backend（LLM/DB 全 mock）。

## 资产消费证据（tt 纪律·硬约束）

- **加载 skill**：`harden`（Skill 工具）。路径 `C:\Users\Administrator\.agents\skills\harden`。

- **方法论**：harden 的「Error Handling / Graceful degradation / Edge cases」三块。

  - 「Graceful degradation：核心功能不因辅助功能失败而全挂」→ 驱动**落库失败保留已生成 token 计数 + 降级 done 兜底**，不让整个流静默哑掉。

  - 「API errors：区分 401/429/500 等，各自处理」→ 驱动 `_map_stream_exception` 按状态码/类型**可区分映射**，替代 50000 单调。

  - 「Network errors / timeout：说明发生了什么、提供重试」→ 驱动 error message 保留可读信息（`type(e).__name__` + 场景），供前端展示与排查。

- **落在哪些改动点**：错误码映射函数 `_map_stream_exception`（router）、落库错误事件设计（保留 `generated_tokens`）、token 错误 message 可读化、连接前/建连后两段式契约注释。

## pytest 实证（chat 域 + error\_codes 域，全绿）

`tests/test_chat_delete.py tests/test_error_codes.py tests/test_chat_stream_error.py` → **23 passed**：

- 新增 5 用例（4 async via ASGITransport + 1 纯单元）全部通过：

  - `test_stream_normal_flow_done_shell`：start→retrieval→token→done，done 壳 `code:0`。**（a）**

  - `test_stream_token_error_maps_auth_code`：注入 `RuntimeError("LLM HTTP 401: invalid api key")` → error 事件、code=`LLM_AUTH`、≠50000、start/retrieval 先行未丢。**（b）**

  - `test_stream_token_error_maps_timeout`：注入 `TimeoutError` → code=`LLM_TIMEOUT`。**（b）**

  - `test_map_stream_exception_table`：8 组映射全对 + 均 ≠50000。**（b2）**

  - `test_stream_persist_fail_emits_error_not_silent`：注入 `build_finalize` 抛 `RuntimeError("mysql connection lost")` → 显式 error `CHAT_PERSIST_FAIL` + `generated_tokens=2` + 降级 done（`code:0` + degraded\_reason 含「落库失败」）。**（c）**

## curl SSE 冒烟（真实 HTTP，POST /api/chat/stream，登录态）

- 登录 `user000001 / Test@123456` → 真实 `POST /api/chat/stream`（`{"query":"什么是特征向量","top_k":2,"use_mcp_tools":false,"use_hyde":false,"enable_graph":false}`）。

- 观测：`HTTP_STATUS=200`；`EVENT_SEQUENCE = start -> retrieval -> token -> done`；`TOTAL_EVENTS=118`；`TOKEN_FRAMES=115`；`DONE_OK_WITH_CODE0=True`。

- done 壳（原文）：`event: done / data: {"code": 0, "message": "ok", "data": {"session_id": null, "message_id": null, "retrieved_count": 0, "final_count": 0, "latency_ms": 9843, "rewrite_query": null, "degraded_reason": "Milvus 检索跳过（MilvusException）", "mcp_tool_calls": []}}` → **C-B 契约外形未变**。

## 对既有 C-B SSE 契约影响确认

- **外形未破坏**：done 壳 `{code:0,...}`、token 字段 `delta`、帧序 start→retrieval→token→done 均经 curl 实测复用如上。

- **仅错误语义增强**：建连后各类失败由「50000 单调 / 静默 degraded\_reason」→「可区分 `event: error` subcode + 显式落库错误」。

- **新增码为增量注册**（5001x 新段），不影响既有 4xx/5xx 值域与 `STATUS_TO_CODE`/`SUBCODE_MAP`（未改动）。

## 遗留/说明

- token 迭代在真实路径中多被 `generate_stream` 内捕获并降级为规则答案，故真实环境此分支较少触发；故错误映射用「可选 mock 注入」实测（契约要求允许），纯单元表覆盖全部分支。

- 落库「答案已生成但未入库」属数据一致性风险：本轮按要求仅升级为显式错误通知（前端可提示），未引入补偿/重试机制（超出 C3 范围），可另开任务。

- 未 commit。

