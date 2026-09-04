# task-O1 验收批判（强制技术批判）

> 对象：task-O1 观测性基座（Trae，commit f287e8f）
> 结论：**验收通过**（AC1~AC5 全绿、handoff 契约完整、竞品对标到位）。

## 实证结果
- commit `f287e8f`（11 文件 +2211）；otel/{metrics,exporter}/core/trace/monitoring 交付。
- 契测 **35 passed**（O1 10 + observability 7 + G1 18 回归）实跑确认。
- AC1 trace 贯穿（四类事件同 trace_id）；AC2 5 维指标含 sources 溯源；AC3 JSONL/OTLP 双通道（失败降级）；AC4 会话级 trace；AC5 回归（X-Trace-Id 保持）。
- handoff 契约：GET /api/metrics/trace/{trace_id} 完整（供 task-FE-O1）。

## 批判 1（P2）：埋点调用点未全接入（memory/executor/compaction 各事件）
- **问题**：基座提供 record_* API，但 memory/executor/compaction 的具体埋点注入属 task-M1/C1/T1/R1 职责（报告如实披露）。
- **方案**：task-T1/R1 及后续接入时用 record_* 一行接入，避免重复实现。

## 批判 2（P2）：OTLP 用 JSON POST，非 protobuf 原生
- **问题**：OTLP/HTTP JSON 投递，protobuf 原生需 opentelemetry-exporter-otlp-proto-http（报告披露）。
- **方案**：接入真实 OTel 后端（ClickHouse）时按需增强。

## 批判 3（P2）：5 维指标进程内累加器，跨实例聚合待 OTel 后端
- **问题**：单进程检索/快照，多实例聚合留待 OTel 后端（报告披露）。
- **方案**：接入 Prometheus/OTLP 后端后跨实例聚合。

**结论**：三条为后续接入/增强项，不阻塞 task-O1。