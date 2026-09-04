# task-O1 — 观测性（trace_id + 5 维指标 + OTel 导出）

> 执行工具：**Trae** ｜ 依赖：task24/25/26/33（现状埋点） ｜ 状态：TODO
> 修订来源：`.opencode/plans/production-upgrade-plan.md` P8（观测性黑盒）
> 核心定位：解决"只有 logger.warning，无法查为什么用户 X 没召回 3 天前目标"。建 **trace_id 贯穿 + 5 维指标 + OTel 导出**，补 `/metrics` 端点与 trace 检索——成为后续 M1/C2/G1/T1/R1 的埋点基座。

## 1. 任务卡片

- **类型/工具**：backend（可观测基座） / Trae
- **依赖**：现状已有 `app/core/trace.py`（trace_id ContextVar + span）、`generator.py`/`executor.py`/`compaction.py` 埋点、`scripts/eval/cache_meter.py`
- **并行组**：W2（第二批 P1，与 task-C1/G1 并行）
- **工作量**：**L**
- **测试窗口纪律**：指标计数/导出逻辑随时可测；真实 LLM 埋点采样仅窗口内

## 2. 选型依据（竞品实证，引用 production-upgrade-plan.md）

| 竞品 | 做法 | 参考 URL |
|---|---|---|
| **Codex** | OTel log export：user prompt/approval 决策/工具结果/MCP 使用/网络策略事件；sandbox_outcome 遥测（denied/escalated/timed_out）；活动日志进 SIEM | https://openai.com/index/running-codex-safely/ 、https://github.com/openai/codex/pull/25955 |
| **Claude** | 缓存命中率当 uptime 监控，低即 SEV；状态行显示 cache_creation/read 计数 | https://code.claude.com/docs/en/prompt-caching |

## 3. 实现规划要点

### 3.1 trace_id 贯穿（改造 `app/core/trace.py` + 各埋点）

- `app/core/trace.py` 已有 `trace_id_var/get_trace_id/start_span`；补：
  - `current_span()` / `child_span(name)`（span 栈 ContextVar，支持嵌套 span 记 duration）；
  - 会话级 trace_id：一次会话内保持同 trace_id（现状是每请求新生成）——`chat/service.py` 会话入口生成并透传，记忆写/召回、LLM 调用、工具调用、压缩各环节消费同一 trace_id。
- 埋点接入点（已有部分，补全）：
  - 记忆写/召回：`memory/service.py` `enqueue_turn/recall_topk` → `memory_event`；
  - LLM 调用：`generator.py` `_ChatClient.call_chat`（已有 trace_id，补 usage 计量）；
  - 工具调用：`executor.py` `call_tool`（已有 trace_id/call_id，补 attempt/outcome 结构化事件，task-T1 复用）；
  - 压缩：`compaction.py` `compact_messages/context_edit` → `compaction_event`（压缩前后 token、丢轮数、触发策略）。

### 3.2 5 维指标（新增 `app/otel/` 包）

- 新增 `app/otel/metrics.py`：
  - `MemoryHitRate`（记忆命中率=召回被采纳/召回总数，按 user 维度）；
  - `CompactionEfficiency`（压缩效率=压缩前后 token 差、丢轮数、触发策略分布）；
  - `ToolSuccessRate`（工具调用成功率=SUCCESS/(SUCCESS+ERROR+TIMEOUT+REJECTION_LIMIT)）；
  - `CacheHitRate`（缓存命中率=cache_read/(cache_read+cache_miss)，模型×层维度；task-C2 汇入）；
  - `QueueTimeoutRate`（并发排队超时率=queue_timeout/acquire 总数，分级 L1~L3；task-G1 汇入）。
- 每个指标为内存累加器（进程内），可 `snapshot()` 导出；跨实例聚合留待 OTel 后端。

### 3.3 OTel 导出（新增 `app/otel/exporter.py`）

- 结构化事件 schema：`{ts, trace_id, span_id, event_type∈{tool_result,retry,sandbox_outcome,memory_event,compaction_event,llm_call}, payload, user_id, model, latency_ms}`；
- 导出目标：`OTEL_EXPORT_ENDPOINT` 配置（默认空=本地 JSONL 落盘 `logs/otel/`；配置后走 HTTP OTLP 灌 ClickHouse/Prometheus，用 `opentelemetry-exporter-otlp-proto-http`，可选依赖不阻塞）；
- 本地审计查询：`GET /api/metrics/trace/{trace_id}` 返回该 trace 全部事件（MySQL `otel_event` 表或 JSONL 检索）。

### 3.4 配置项

```python
OTEL_EXPORT_ENDPOINT = ""          # 空=JSONL 本地
OTEL_JSONL_DIR = "logs/otel"
OTEL_SAMPLE_RATE = 1.0             # 埋点采样率
TRACE_SESSION_LEVEL = True         # 会话级 trace_id
```

### 3.5 测试

- `tests/test_contract_task_o1.py`：trace_id 会话级透传、5 维指标计数正确、snapshot 格式、OTel 事件 schema、trace 检索端点。

## 4. 验收标准（Given/When/Then）

- **AC1（trace 贯穿）**：Given 用户 X 一次完整问答（含记忆召回+LLM+工具+压缩），When 按 trace_id 查询，Then 返回该 trace 全部事件（记忆写/召回、LLM usage、工具结果、压缩前后 token），可还原"为什么没召回 3 天前目标"。
- **AC2（5 维指标）**：Given 观察窗口内 N 次请求，When `snapshot()`，Then 输出记忆命中率/压缩效率/工具成功率/缓存命中率/排队超时率五个指标，每项含计数与比例且数据来源可溯源到事件。
- **AC3（OTel 导出）**：Given `OTEL_EXPORT_ENDPOINT` 为空，When 事件产生，Then 结构化 JSONL 落盘（字段含 ts/trace_id/event_type/payload）；Given 配置端点，Then 走 OTLP HTTP 导出（可选依赖缺失时降级 JSONL 不阻塞）。
- **AC4（会话级 trace）**：Given 会话内 3 次请求，When 检查 trace_id，Then 3 次请求共用同一会话级 trace_id（span_id 各异）。
- **AC5（回归）**：Given 既有 trace_id 中间件行为（每请求 X-Trace-Id 响应头），When 改造后，Then 响应头仍携带 trace_id，既有慢查询日志不受影响。

## 5. 交接与记忆

- **完工报告**：`test-reports/task-O1-completion-report.md`（trace 检索实测、5 维指标样例、JSONL 事件样本）。
- **记忆写入**：AI-Hub `trae-projects/EduAgent/project_memory.md` 追加"trace_id 会话级贯穿 + 5 维指标 + OTel JSONL/OTLP 双通道"观测基座决策。
- **完成动作**：git commit → sync.ps1。

## 6. 批判承接

- **production-upgrade-plan.md P8**（观测性黑盒）：只有 logger.warning 无法查召回归因 → AC1/AC2 落实。
- **critique-backlog-tracker.md**：task97（R5 缓存监控）的命中率指标归入本任务 5 维指标；task92 批判②（artifact 跨实例）通过 trace 检索可观察 artifact 读写路径。

## 7. 与其他 task 关联

- **联动**：task-M1/M2（memory_event 埋点）；task-C1/C2（压缩事件 + 缓存命中率）；task-G1（排队超时率）；task-T1（工具事件 + retry）；task-R1（rerank 延迟指标）。本任务是后续任务的**埋点基座**，建议先于 T1/R1 实施。
- **执行顺序**：W2 第二批；`app/otel/` 为新包，不阻塞既有代码。