# REPORT-TB2b —— OTel 真瀑布：扩域修复

- **分支**：`feature/opt-waves`（`.git/HEAD` = `ref: refs/heads/feature/opt-waves`，非 detached）
- **顺序依赖（工作项 4，硬性）**：`git log --oneline -8` 确认 **TA5 已在基线** ——
  `df26b39 fix(be)/ta5: chat 用户并发槽失败路径泄漏修复(finally 收口)` ✔
- **铁律遵守**：未改动 `app/chat/service.py` 并发槽逻辑（仅在外围包裹 span）；未触碰 TA6 executor 两 handler、TB1 recommender、前端。
- **闭环定义达成**：Jaeger UI 中**一条真实 chat 请求的分层瀑布**（非"export enabled 日志"）——见 §5 截图与原始 JSON。

---

## 1. 三层断点逐项修复证据

TB2 定因的三个断点，逐项给出「修复前现象 → 修复动作 → 修复后实测」。

### 断点① 导出路径缺 `/v1/traces` 后缀（裸 POST → 404）

| | |
|---|---|
| 修复前 | `.env` 中 **零 OTel 配置**（TB2 未改 .env）；手写导出打裸根 → Jaeger **404** |
| 修复动作 | 字节级补丁写入 `.env`（UTF-8+LF 保持，5417→6026 bytes；备份 `deploy/backups/.env.tb2b.bak`） |
| 修复后 | endpoint = `http://127.0.0.1:14318/v1/traces`，settings 加载已核对 |

```ini
# ============ OTel 真瀑布（TB2b） ============
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:14318/v1/traces
OTEL_EXPORT_ENDPOINT=          # 私有 JSON 路径显式停用（防双路 400 噪音）
```
> 端口说明：宿主 4318 被他人容器占用 → Jaeger OTLP HTTP 映射 **14318**，UI **16686**。

**对照实测**（同一 Jaeger，`urllib` 禁代理）：
```
POST http://127.0.0.1:14318/v1/traces  → 200 {"partialSuccess":{}}   ✔
POST http://127.0.0.1:14318/           → 404                        ← 断点① 的机制复现
```

### 断点② 导出体是私有 event dict，非 OTLP `resourceSpans` 信封

| | |
|---|---|
| 修复前 | `app/otel/exporter.py` 私有 dict → Jaeger **400 reject** |
| 修复动作 | 新增 `_event_to_envelope()`：私有事件 → 合法 `resourceSpans`（traceId/spanId 归一非零、`startTimeUnixNano = ts`、`endTimeUnixNano = ts + latency_ms`、kind=1、payload.* 落 attributes、失败→`status.code=2`）；保留开关 `OTEL_EXPORT_ENVELOPE`（`otlp` 默认 / `legacy` 旧行为，**仅调试**） |
| 修复后 | 同一 Jaeger 实测 **POST 200 `{"partialSuccess":{}}`** ✔ |

**取舍说明**：私有 JSON 通道**未删除、降级为 legacy 开关**。理由——它是 `app/observability/otlp.py` 的既有入口，可能有测试/脚本引用；直接删会造成域外破坏。默认关掉即消除双路噪音，保留开关便于回溯对比。

### 断点③ 「脚手架齐备、链路未接」——`child_span`/`start_span` 生产调用点 = 0

| | |
|---|---|
| 修复前 | 全仓生产调用点 **0**；仅有 2 个粗粒度入口且**无 parentSpanId**，Jaeger 上是散点 |
| 修复动作 | 新建 `app/observability/tracing.py`（真 OTel SDK 承接 span 生命周期）；在 router / graph_stream / sixnode 三处入口层埋点 |
| 修复后 | 端到端实测 **Depth 3 / Total Spans 4 / linked_children=3 roots=1** ✔ |

**埋点位置（均在入口层，不碰业务语义）**：

| span | kind | 位置 | 关键属性 |
|---|---|---|---|
| `chat.request` | server | `app/chat/router.py::chat_stream_sse` | user_id / role / session_id / query / channel / trace_id |
| `retrieval` | internal | `app/chat/flows/graph_stream.py` | nodes（六节点到达序）/ node_arrivals_ms / ttft_retrieval_ms / ttft_first_token_ms / answer_tokens / retrieved_count / final_count / graph_entities / degraded_reason |
| `llm_call` | client | `app/ai/harness/sixnode.py::answer` | **model（上游实际模型名）** / model_alias / stream / max_tokens / messages / answer_chars |
| `tool_calls` | internal | `app/chat/flows/graph_stream.py::_run_mcp` | user_id / query_len / hitl_decision / mcp_enabled / tool_count / tools |

**root span 的生命周期难点（值得记录）**：SSE 的 `body_iterator` 是在 handler `return` **之后**才被迭代的。若在 handler 里 `with` 收口，root 会在子 span 之前 end → 子 span 挂空。故 `chat.request` 的 span 上下文挂在响应体迭代器上，由 `_tb2b_close_root_span()` 包装后的 aiter 负责 end。

---

## 2. 探活升级：从「纯 socket 握手」到「真 OTLP POST」

| | |
|---|---|
| 修复前 | `otlp.py::_tcp_probe` 只做 `socket.connect` —— **恒 PASS**，实测 `start()=healthy` 而 `export()→False`（探活绿 ≠ 链路通） |
| 修复动作 | 新建 `app/observability/otlp_probe.py::probe_otlp_http()`：真发合法最小 `resourceSpans` 信封，2xx 才算绿；`otlp.py::start()` 按 `OTEL_EXPORTER_OTLP_PROBE_MODE` 分流（默认 `http`，`socket` 保留旧行为） |

**「绿 = 真通」复验**（后端启动日志）：
```
[OTLP-HTTP] 真探活通过 endpoint=http://127.0.0.1:14318/v1/traces status=200 5ms ✔
[OTLP] 启用 endpoint=.../v1/traces service=edu-agent headers=0条 HTTP 真探活5ms ✔（POST /v1/traces 2xx = 导出链路真通）
```

**额外防呆**：探活失败时会再做一次**裸根对照探测**，若裸根返回 404 则在 `detail.hint` 直接提示"配置的 endpoint 很可能缺少 `/v1/traces` 后缀"——把断点①的坑变成自解释错误。

---

## 3. 依赖变更说明

**结论：本次未新增任何 pip 包。** 三处需要澄清的事实：

1. `opentelemetry-*` 系列在本机 `.venv` **原本就已安装**（1.44.0，手写 envelope 时代就在用），**不是 TB2b 引入的**。
2. 但它们**一直没写进 `edu-agent/pyproject.toml`**（`grep opentelemetry pyproject.toml` 原本为空）——这是隐式依赖：换机重建 venv 会缺包，且缺包时 OTel 埋点**静默降级 no-op**（极难排查）。
3. 故本次**把「实际在用」的 3 个包补成显式声明**（`pyproject.toml` 的 dependencies）：

```toml
    # ── 可观测性（TB2b：分层 span → Jaeger 真瀑布） ──
    "opentelemetry-api>=1.20,<2.0",
    "opentelemetry-sdk>=1.20,<2.0",
    "opentelemetry-exporter-otlp-proto-http>=1.20,<2.0",
```

版本区间取 `>=1.20,<2.0`（兼容本机 1.44.0，不锁死小版本）。**零安装动作、零环境变更**，仅补齐声明。

---

## 4. 失败路径 span（status=error）证据

**注入方式**：把上游 LLM 指向不可达端口重启后端（不改代码）——
```
LLM_STRONG_BASE_URL=http://127.0.0.1:9/  uvicorn app.main:app --port 9988
```
再发一次真实提问。Jaeger 中 `llm_call` span 实测：

| 属性 | 值 |
|---|---|
| `otel.status_code` | **ERROR** |
| `otel.status_description` | `ConnectionError: HTTPConnectionPool(host='127.0.0.1', port=9): Max retries exceeded with url: //chat/completions (Caused by NewConnectionError(...Failed to esta…` |
| `error` | `true` |
| `degraded` | `true` |
| `model` / `model_alias` / `stream` | `deepseek-flash` / `strong` / `true` |

层级仍正确：`chat.request → retrieval → llm_call(ERROR)`，`linked_children=3 roots=1`。

**截图**：`test-reports/tb2b/shots/fail-error-span.png`（`llm_call` 带红色 ✗ 错误标记）。

> ⚠️ 附带发现并修正了一个**探针自身的读数 bug**（见 §6"踩坑"第 1 条）——早期探针读 `parentSpanID` 字段恒为 None，**误判"父子链断裂"**，实际 Jaeger 一直存得对。这直接解释了之前几轮"修了还是 4 个孤立 root"的假象。

---

## 5. Jaeger 瀑布截图与原始证据

| 证据 | 路径 |
|---|---|
| 正常路径瀑布截图 | `test-reports/tb2b/shots/ok-waterfall.png` |
| 失败路径 error span 截图 | `test-reports/tb2b/shots/fail-error-span.png` |
| 正常路径原始 JSON（Jaeger 返回 + 树 + SSE 时序） | `test-reports/tb2b/e2e_ok.json` |
| 失败路径原始 JSON | `test-reports/tb2b/e2e_fail.json` |

**终验 trace**：`984dd679cc6eb20e50c53b4d91299c11`（截图即此条；调试代码已全部移除后重跑）

```
== Jaeger trace 984dd679cc6eb20e50c53b4d91299c11 spans=4 ==
- chat.request           kind=server   status=-      dur= 20585.2ms  sid=2ad30e12
  - tool_calls             kind=internal status=-      dur=   111.0ms  sid=c386a819
      · tool_count=0
  - retrieval              kind=internal status=-      dur= 20422.2ms  sid=2490c2e5
      · nodes=route,skill,compact,context_edit,plan,fan_out,merge,reflect,answer
      · degraded_reason=Milvus 检索超时(8.0s)
    - llm_call               kind=client   status=OK     dur=  8391.3ms  sid=277a993f
        · model=deepseek-flash
        · answer_chars=943
[linkage] spans=4 linked_children=3 roots=1
```

Jaeger UI 页头显示 **`Duration 20.59s / Services 1 / Depth 3 / Total Spans 4`**，缩进层级即父子关系（`chat.request` → `retrieval` → `llm_call`；`tool_calls` 为其兄弟）。

**owner 验收口径（GWT）逐条核对**：

| GWT | 结果 |
|---|---|
| Given Jaeger UI 打开 | `http://127.0.0.1:16686` 在岗，页面渲染 21 行 timeline ✔ |
| When owner 发起一次提问 | student 真实 SSE 提问（`user000001`），事件 `start retrieval token done` ✔ |
| Then 完整分层 span 瀑布、retrieval/LLM 各段可指认 | `Depth 3`，4 span 命中 `chat.request/retrieval/llm_call/tool_calls`，瀑布中 `retrieval` 与 `llm_call` 两段色条可分别指认 ✔ |
| 断上游时 span 显示错误状态 | `llm_call` = `otel.status_code=ERROR` + 红色 ✗ 标记 ✔ |

---

## 6. 踩坑记录（可复用）

1. **Jaeger `/api/traces` 响应里没有 `parentSpanID` 字段** —— 父关系存在 `references[]` 中（`refType=CHILD_OF` 的 `spanID`）。早期探针读 `s.get("parentSpanID")` 恒为 `None`，**误判"父子链断裂"**，连做多轮无效排查。这是本次最大的时间浪费点。**教训：怀疑链路之前先验读数方式**（本项目"通用教训"里"先查数据再质疑逻辑"的翻版）。
2. **`use_span` 的 `end_on_exit` 默认 `False`** —— 不显式传 `True` 则 span 永不 `end()`，`SimpleSpanProcessor` 永不导出（内存导出器 `finished_spans=0`，Jaeger 一条都看不到）。
3. **`start_as_current_span(context=...)` 不会把该 context 设为 current**（只当作新 span 的父）→ 嵌套层级全部挂到最外层。改用 `tracer.start_span(name, context=base_ctx, kind=...)` + `use_span(...)` 手工管理。
4. **ContextVar 不跨 asyncio Task 继承** —— SSE 的 `body_iterator` 在独立 Task 中迭代，隐式 current span 取不到 → 父 span 必须**显式传递**（`set_span_in_context(parent._span)`）。实测这条其实通过 SDK 的隐式路径也work（`llm_call` 未传 parent 仍正确挂到 `retrieval`），但显式传递是唯一可靠做法，代码里两者都保留。
5. **`GeneratorExit` 不是失败** —— 异步生成器正常 `aclose()` 会抛 `GeneratorExit`（BaseException）。若不特判，每个正常收尾的 SSE 请求都会把 root span 标成 ERROR，使 Jaeger 上"错误"失去判别力。
6. **BatchSpanProcessor 会丢尾帧** —— 实测 4 个 span 丢失 3 个子 span，只剩 root（进程/生成器收尾早于导出线程 flush）。故默认取 `SimpleSpanProcessor`（同步导出、发问后立即可见）；`OTEL_TRACING_PROCESSOR=batch` 可切回。
7. **Windows PowerShell 工具的 stdout 在本会话被吞** —— 命令退出码 0 但无任何输出。变通：把结果 `Set-Content` 到文件再用 Read 读。`cd X && powershell -Command` 形式会被安全策略拦截，须用独立 PowerShell 工具。

---

## 7. 交付清单

**新增文件**
- `edu-agent/app/observability/tracing.py` —— 真 OTel SDK 分层 span 基建（`span()` / `SpanHandle` / `get_tracer` / `tracing_status` / `shutdown`）
- `edu-agent/app/observability/otlp_probe.py` —— OTLP HTTP 真探活（含裸根对照防呆）
- `test-reports/tb2b/e2e_ok.json`、`e2e_fail.json` —— 端到端原始证据
- `test-reports/tb2b/shots/ok-waterfall.png`、`fail-error-span.png` —— Jaeger 截图
- `_tb2b_e2e.py`、`_tb2b_shot.mjs` —— 可复跑探针（端到端 + 截图）

**修改文件**
- `edu-agent/.env` —— OTel 两行（endpoint 带 `/v1/traces`；私有路径置空）
- `edu-agent/app/config.py` —— 新增 `OTEL_EXPORT_ENVELOPE`、`OTEL_EXPORTER_OTLP_PROBE_MODE`
- `edu-agent/app/otel/exporter.py` —— `_event_to_envelope()` 私有事件 → 合法 OTLP 信封
- `edu-agent/app/observability/otlp.py` —— 探活升级为 HTTP 真探测 + `probe_mode`/`probe_detail`
- `edu-agent/app/chat/router.py` —— `chat.request` root span + `_tb2b_close_root_span()`
- `edu-agent/app/chat/flows/graph_stream.py` —— `retrieval` / `tool_calls` 子 span + 丰富属性
- `edu-agent/app/ai/harness/sixnode.py` —— `llm_call` 子 span（含上游模型名）
- `edu-agent/pyproject.toml` —— 补 3 个 OTel 依赖显式声明（**零安装**）
- `docs/面试演示-逐步点击手册.md` —— 新增「第 2.7 章：OTel 演示站」+ 服务全景表补 Jaeger 行

**未 push**（按令）；单 commit 已收口。
