# O1-② / O1-③ 独立实证报告（本地真实 OTLP 收集端）

> 批次：2026-09-05 环境恢复后补完
> 状态：两项 ⚠️ 环境依赖项 → 以**本地真实 OTLP HTTP 接收端**实证闭环
> 方法：真实 HTTP POST 投递 + 真实 http.server 收集端 + 运行中后端端点校验
> 脚本：`_verify_otel_tmp.py`（实证后已清理）

---

## O1-② OTLP 投递成功（原 ⚠️ 待真实后端 → 已实证）

本地起真实 OTLP HTTP 接收端（`http.server`，记录 POST body），两个 `OtelExporter` 实例打同一端点。

| 断言 | 结果 |
|---|---|
| 5 类事件（memory/compaction/tool/cache/queue）真实投递收集端 | 5/5 全部收到 PASS |
| payload / trace_id / event_id 无损回读 | memory_event：action=recall、adopted=True、user_id=u1、trace_id=TA-abc 全吻合 PASS |
| 端点不可达 → 自动降级 JSONL 落盘且不阻塞主流程 | 落盘 `otel-*.jsonl` 且 `record()` 不抛异常 PASS |

结论：`OTEL_EXPORT_ENDPOINT` 配置后走 OTLP HTTP 投递真实生效；不可达自动降级 JSONL 的兜底路径也实测无阻塞。

## O1-③ 跨实例收集端聚合 + 指标端点

| 断言 | 结果 |
|---|---|
| 同一收集端聚合实例 A(3) + 实例 B(2) = 5 条 | trace 前缀 TA=3 / TB=2 精确聚合 PASS |
| 5 维指标事件类型在收集端全覆盖 | {memory,compaction,tool,cache,queue} 全命中 PASS |
| `GET /api/metrics/otel`（admin）返回 5 维快照 | 外壳 `{code:0}`,data 含 memory_hit_rate/compaction_efficiency/tool_success_rate/cache_hit_rate/queue_timeout_rate 五键 PASS |
| `GET /api/metrics/trace/{id}`（admin）契约形态 | {trace_id,event_count,events,trace_metrics} 齐备 PASS |

结论：收集端（对标真实 OTLP/Prom 后端行为）聚合多实例事件成立；应用侧指标快照端点与 trace 溯源端点在运行中后端上契约形态正确。**注：进程内 5 维累加器仍为单实例语义，生产多实例聚合应由 Prometheus/OTLP 后台抓取 `/metrics` + OTLP 收集端完成——本报告证明收集端聚合层已可用。**

## 判定
- O1-② ✅ 闭环（投递 + 降级兜底实证）
- O1-③ ✅ 闭环（收集端跨实例聚合 + 端点契约实证）