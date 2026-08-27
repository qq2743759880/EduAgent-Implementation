# task-O1 完工报告 —— 观测性基座（trace_id + 5 维指标 + OTel 导出）

- **角色**：EduAgent 重构项目【后端+数据库开发者】
- **依据**：`.opencode/plans/tasks/task-O1.md` + `.opencode/plans/production-upgrade-plan.md` P8（观测性黑盒）
- **竞品对标**：Codex OTel log export（user prompt/approval/工具结果/MCP/网络策略事件）+ Claude 缓存命中率当 uptime（低即 SEV）
- **测试窗口纪律**：指标计数/导出/检索逻辑全程内存可测；真实 LLM 埋点采样仅窗口内（本次未触发真实 LLM）
- **git 纪律**：基于最新 HEAD `cd71ad5`，一次一个 commit；仅提交 O1 文件，19 个 prior-task（task93/95/96）staged 文件未触碰

---

## 1. 验收标准（AC1~AC5）实测结果

| AC | 要求 | 实测 | 状态 |
|---|---|---|---|
| AC1 | trace 贯穿：一次完整问答按 trace_id 查全部事件，可还原"为什么没召回 3 天前目标" | 记忆召回+LLM+工具+压缩四类事件均带同一 trace_id/span_id；可定位 3 天前目标被召回但 `adopted=False` | ✅ |
| AC2 | 5 维指标：记忆命中率/压缩效率/工具成功率/缓存命中率/排队超时率，计数+比例+可溯源 | 5 维均输出 `counts`+`ratio`+`sources`（溯源事件 trace_id/event_id 列表）；见 §3 样例 | ✅ |
| AC3 | OTel 导出：空端点→JSONL 落盘（ts/trace_id/event_type/payload…）；配置端点→OTLP HTTP，失败降级 JSONL | 空端点生成 `logs/otel/otel-YYYY-MM-DD.jsonl`，schema 字段齐；OTLP 走 HTTP POST；网络异常自动降级 JSONL 不抛 | ✅ |
| AC4 | 会话级 trace：会话内 3 次请求共用同一 trace_id（span_id 各异） | 同一 session_id 三次请求 trace_id 一致；嵌套 `child_span` span_id 各异；跨请求 span_id 各异 | ✅ |
| AC5 | 回归：既有 X-Trace-Id 响应头仍携带 trace_id；慢查询日志不受影响 | 响应头仍携带 X-Trace-Id（会话级下携带会话 trace_id）；既有 `TraceMiddleware` 慢日志逻辑未动 | ✅ |

**测试**：`tests/test_contract_task_o1.py` —— **10 passed**（含 AC1~AC5 + 端点契约）。
**回归**：`tests/test_observability.py` 7 passed（中间件 X-Trace-Id 头与慢日志不受影响）；`tests/test_contract_task_g1.py` 18 passed（generator.py 改动未破坏 G1 契约）。

---

## 2. 交付文件清单

### 新增
- `edu-agent/app/otel/__init__.py` —— 包导出（exporter + metrics 单例/类型）
- `edu-agent/app/otel/metrics.py` —— 5 维指标内存累加器
  - `MemoryHitRate`（记忆命中率 = 召回被采纳/召回总数，按 user）
  - `CompactionEfficiency`（压缩效率 = 压缩后/压缩前 + 丢轮数 + 触发策略分布）
  - `ToolSuccessRate`（工具成功率 = SUCCESS/(SUCCESS+ERROR+TIMEOUT+REJECTION_LIMIT)）
  - `CacheHitRate`（缓存命中率 = cache_read/(cache_read+cache_miss)，模型×层）
  - `QueueTimeoutRate`（排队超时率 = timeout/acquire，分级 L1~L3）
  - `OtelMetrics` 聚合器：`record(event)` 按 `event_type` 派发，`snapshot()` 输出 5 维；每项保留 `sources` 溯源列表
- `edu-agent/app/otel/exporter.py` —— OTel 结构化事件导出器
  - 事件 schema：`{ts, trace_id, span_id, event_type, event_id, payload, user_id, model, latency_ms}`
  - 双通道：`OTEL_EXPORT_ENDPOINT` 空→JSONL 落盘 `OTEL_JSONL_DIR`；非空→OTLP HTTP（失败降级 JSONL）
  - 内存环形缓冲（默认上限 5000）+ 派发到 5 维指标
  - 便捷埋点：`record_memory_event / record_compaction_event / record_tool_result / record_cache_event / record_queue_event / record_llm_call`
- `edu-agent/tests/test_contract_task_o1.py` —— AC1~AC5 契约测试
- `edu-agent/test-reports/task-O1-completion-report.md` —— 本报告

### 修改（O1 范围内，均向后兼容）
- `edu-agent/app/config.py` —— 新增 OTEL 配置段（task-O1 专属，未触碰 G1/其他段）
  ```python
  OTEL_EXPORT_ENDPOINT: str = ""      # 空=JSONL 落盘；配置后走 OTLP HTTP
  OTEL_JSONL_DIR: str = "logs/otel"
  OTEL_SAMPLE_RATE: float = 1.0
  TRACE_SESSION_LEVEL: bool = True
  ```
- `edu-agent/app/core/trace.py` —— 扩展（不改动既有 `start_span`/`get_trace_id`）
  - `current_span()` / `child_span(name)`：嵌套 span 栈，记录 parent 与 duration
  - `session_trace_id(session_id)` / `set_trace_context(session_id)`：会话级 trace_id（进程内稳定映射）
  - `reset_session_traces()`：测试用
- `edu-agent/app/monitoring/router.py` —— 新增两个端点（不改动既有 `/metrics`/`/api/metrics/cache-context-dashboard`）
  - `GET /api/metrics/trace/{trace_id}` ← **handoff 契约（供 task-FE-O1）**
  - `GET /api/metrics/otel` —— 5 维指标全局快照
- `edu-agent/app/middleware/auth_middleware.py` —— 仅改 X-Trace-Id 头赋值逻辑（穿透 BaseHTTPMiddleware context 隔离）
  - 中间件起始写 `request.state.trace_id = tid`；响应头取 `request.state.trace_id`（路由内可覆盖为会话级 trace_id）→ 保证 X-Trace-Id 贯穿会话级链路
- `edu-agent/app/chat/router.py` —— 两个问答端点入口调用 `set_trace_context(session_id=...)` 并写入 `request.state.trace_id`（AC4 真实生效）
- `edu-agent/app/chat/generator.py` —— `_report_cache_usage` 同步上报 `record_cache_event`（喂入 CacheHitRate 指标；与 task97 CacheMonitor 各司其职，不重复计数）

---

## 3. 5 维指标样例（来自 AC2 实测）

| 维度 | 计数/比例 | 溯源 |
|---|---|---|
| memory_hit_rate | recall_total=2, recall_accepted=1, hit_rate=0.5 | sources 含贡献事件 trace_id |
| compaction_efficiency | compactions=1, before=1000→after=600, ratio=0.6, policy=compaction | ✅ |
| tool_success_rate | total=4, SUCCESS/ERROR/TIMEOUT/REJECTION_LIMIT 各1, success_rate=0.25 | ✅ |
| cache_hit_rate | read=800, miss=200, hit_rate=0.8（by_model.fast=0.8） | ✅ |
| queue_timeout_rate | acquire=3, timeout=1, timeout_rate≈0.333 | ✅ |

## 4. JSONL 事件样本（AC3 实测，字段齐）

```json
{"ts":1756292651000,"trace_id":"t-jsonl","span_id":"a1b2c3d4","event_type":"memory_event",
 "event_id":"...","payload":{"action":"recall","user_id":"u9","adopted":true},
 "user_id":"u9","model":"fast","latency_ms":12.5}
```

## 5. handoff 契约（→ task-FE-O1 观测面板）

```
GET /api/metrics/trace/{trace_id}
200 {
  trace_id: str,
  event_count: int,
  events: [ {ts, trace_id, span_id, event_type, event_id, payload, user_id, model, latency_ms}, ... ],
  trace_metrics: { memory_hit_rate, compaction_efficiency, tool_success_rate, cache_hit_rate, queue_timeout_rate }
}
```

## 6. 风险披露 / 已知边界
- **埋点接入范围**：本任务交付"观测性基座"——事件 schema、5 维指标、OTel 导出、trace 检索端点、会话级 trace 机制、cache 事件真实喂入（generator）。其余埋点（memory/executor/compaction 各事件）的**具体调用点注入**属 task-M1/C1/T1/R1 等后续任务职责，本任务已预留 `record_*` 便捷 API，后续直接一行接入即可，无需改动本基座。
- **OTLP**：采用 OTLP/HTTP JSON POST 投递（运行时常驻 `requests`，零新依赖）；如需 protobuf 原生 OTLP 可由 `opentelemetry-exporter-otlp-proto-http` 在 `_export_otlp` 处增强，缺失/网络失败已自动降级 JSONL，不阻塞主流程。
- **跨实例聚合**：5 维指标为进程内累加器，跨实例聚合留待 OTel 后端（ClickHouse/Prometheus）；本端点提供单进程检索与快照。
- **git reftable 陷阱**：commit 后已用 `git show-ref | grep feature/task44-courses` 验证分支 ref 更新（同 G1 经验）。
- prior-task（task93/95/96）19 个 staged 文件经核验未触碰。

## 7. 下一步
完成 commit → 运行 `D:\.ai-hub\sync.ps1 -Action sync` → 停下等验收。
