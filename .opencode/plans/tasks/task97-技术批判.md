# task97 验收批判（强制技术批判）

> 对象：task97 R5 缓存监控（Trae，commit 056fa1b）
> 结论：**验收通过**（GWT 全达成、批判承接全闭环、git 纪律正确）。

## 实证结果
- commit `056fa1b`（6 文件 +1442）；cache_monitor/graph/deferred/description_reviewer/generator/monitoring 交付。
- 契测 **53 passed**（task97 19 + task95/96 回归 34）实跑确认，无回归。
- GWT① 改写存延迟层+摘要稳定+admin_only+版本告警+60s 缓存；② 命中率 >50% 上报；③ MCP 变更不失效、模型切换记 model_switch；④ 联合看板（cache+context 水位）。
- 批判承接：task95③ deferred 端到端、task96② context_edit_node 接入 graph 真正消费（60→16 消息）、task96③ 真实多轮观测。
- git：基于最新 HEAD 单 commit（未用 read-tree --empty），纪律正确。

## 批判 1（P2）：命中率监控为进程内单例，多实例部署时指标不聚合
- **问题**：cache_monitor 进程内 threading.Lock 单例，多实例各报各的，Prometheus 需多实例拉取聚合。
- **方案**：task-O1（观测性）或后续接入多实例聚合（prometheus 多 target scrape）。

## 批判 2（P2）：HIT_RATE_ALERT_THRESHOLD=0.5 未接告警通知
- **问题**：低于 0.5 仅 `hit_rate_below_threshold()` 标记，未触发 SEV 通知（报告列为可选增强）。
- **方案**：接入告警渠道（邮件/钉钉/webhook）时补。

## 批判 3（P2）：/api/metrics/cache-context-dashboard 新端点未同步前端
- **问题**：联合看板端点已加，但前端无消费页面（task-FE-O1 观测面板规划但依赖 task-O1）。
- **方案**：task-FE-O1（观测面板）落地时接入本端点。

**结论**：三条为后续改进项，不阻塞 task97。