# task25 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task25 AI 助手三层记忆 + 遗忘机制（Trae，commit 7f89d84）
> 结论：**✅ 验收通过**（GWT 实证全绿），2 条批判（P2 不阻塞）

---

## 实证结果

| 项 | 实测 |
|----|------|
| commit | ✅ `7f89d84`（15 文件 +1929，7 个 memory 模块）|
| 交付物 | ✅ memory 7 模块（persistence/queue/schemas/score/service/store/vector）+ graph/chat/config 接线 + DDL |
| 契约测试 | ✅ **task25 11/11 + task24/task92 回归 = 23 passed 实跑**（1 skipped 环境相关）|
| user_memory 表 | ✅ 真库核验：12 列 + 3 索引（idx_um_user_created/type/score）|
| 遗忘机制 | ✅ exp 衰减 + recency_bonus + importance（score.py）|
| R7 显式触发 | ✅ ingest.py（记住=9/目标=8/纠正=4/偏好=7）+ graph.py extract |
| 异步队列 | ✅ queue.py（异步 + 有界重试 max_retry=3）|
| Milvus 降级 | ✅ vector.py in-process 内存向量（DeterministicEmbedder）|

## 批判 1（P2）：Milvus 降级内存向量（外部 VM 不可达）——生产语义需确认

**问题描述**：外部 VM Milvus（192.168.85.101:19530）不可达 → 自动降级 in-process 内存向量（DeterministicEmbedder）。向量召回语义恒可用，但**降级向量仅本进程内有效**（重启丢失、跨实例不一致），生产多实例时需恢复真实 Milvus。

**证据来源**：vector.py（降级内存向量）；报告 §5 Milvus 降级；task21 同款（外部存储机不可用）。

**优化方案**：不阻塞（降级保语义可用，task21 同模式）。生产部署时恢复 Milvus 真实向量（VM 修复后）；task39 压测验证。

## 批判 2（P2）：三层记忆的 Working/Short-term 依赖 LangGraph state + Redis session，端到端未独立验证

**问题描述**：GWT①~④ 验证了 user_memory 落库/召回/遗忘/重试，但 **Working（LangGraph state）+ Short-term（Redis session 历史）与 Long-term（user_memory）的三层联动端到端**（会话内 Working→会话结束 Short-term→Long-term 沉淀）未在真实多轮会话中独立验证（依赖 graph 集成）。

**证据来源**：报告 GWT 验收（user_memory 链路）；三层记忆架构（state/Redis/MySQL）。

**优化方案**：不阻塞（各层已验证 + graph 接线 recall_memory/recall_profile）。task29（AI 评估）多轮会话端到端验证三层联动。

## 总评

| GWT | 结果 |
|-----|------|
| ① 偏好落库 + 异步不阻塞 | ✅ 入队 0.98ms + 真库 count=1 |
| ② 相关话题向量召回 top-3 | ✅ query 雅思 召回 top1 命中 |
| ③ 超 500 遗忘淘汰最低分 | ✅ soft_deleted=3 + 雅思保留 |
| ④ 写失败重试不影响应答 | ✅ max_retry=3 第 3 次成功 |

**结论：task25 验收通过。** 三层记忆 + 遗忘机制 + R7 显式触发完成。批判 1/2 均 P2（Milvus 降级转生产 / 三层联动转 task29）。
