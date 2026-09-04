# task-R1 验收批判（强制技术批判）

> 对象：task-R1 Rerank 独立服务 + 连续批处理（Trae，commit 2102e2e）
> 结论：**验收通过**（AC1~AC5 全绿、CUDA 实测充分、竞品对标到位）。

## 实证结果
- commit `2102e2e`（9 文件 +1520）；rerank_service/{batcher,main,queue_adapter} + rerank_pairs 交付。
- 契测 **44 passed 1 skipped**（R1 14 + T1/S1/28 回归 30）实跑确认。
- AC1 真实 CUDA sidecar vs 直连**误差 0.0**；AC2 async 不阻塞（5 并发≈单次）；AC3 5 请求≤2 批吞吐 2.36x；AC4 降级链不 500；AC5 压测 **speedup 3.6x**、P95≤120ms。

## 批判 1（P2）：fp16 跨请求批量算术噪声 ~0.012
- **问题**：48 对一次前向 fp16 噪声 ~1e-2（报告如实披露，对排序无影响）；压测一致性按容差 0.05 判定。
- **方案**：对排序敏感场景可评估 fp32 批处理或阈值校准。

## 批判 2（P2）：sidecar 启动/预热为运维待办，未实际部署
- **问题**：uvicorn 8601 独立进程启动 + 模型预热是部署待办（报告披露），当前主链路仍默认直连或 sidecar 未跑。
- **方案**：部署时启动 sidecar + RERANK_SIDECAR_ENABLED=True 灰度验证。

## 批判 3（P2）：Redis 队列削峰为可选（默认 DirectQueue）
- **问题**：RERANK_QUEUE_REDIS=True 才启用 RedisQueue，峰值削峰未默认。
- **方案**：高峰流量评估后启用；当前内存级 QUEUE_MAX=200 兜底。

**结论**：三条为部署/增强项，不阻塞 task-R1。