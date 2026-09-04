# task27 验收批判（强制技术批判）

> 对象：task27 tool_specs + token 优化（Trae，commit 4f99249）
> 结论：**验收通过**。

## 实证结果
- commit 4f99249 存在；tool_specs/decision_validator/prompt_cache 交付。
- task27 + task24/task25/task92 + agent_loop：**48 passed，1 skipped**（仅真 Redis 依赖测试，Redis 不可达）。
- ToolSpec 七字段、稳定排序、admin 过滤、parallel_safe 并行执行存在；非法 JSON 重试1次+need_search保守回退；system/project/conversation 三层缓存与失效原因记录存在。

## 批判 1（P2）：缓存命中/失效真实 provider 语义待验证
- **问题**：三层缓存与命中率逻辑已实现，但真实 provider 的 cache_read/cache_creation 语义依赖运行环境，当前 Redis/外部模型环境未完整实测。
- **证据**：prompt_cache.py + 1 skip 的 Redis 依赖测试。
- **差距**：未量化真实缓存命中率和 token 节省。
- **方案**：task29 评估中加入多轮相同前缀 benchmark，记录 cache_read/cache_creation、延迟、成本。
- **最小验证**：同输入运行10轮，前缀字节一致，命中率与 token 指标落报告。
- **收益/成本**：可量化缓存收益；成本 task29 增加一个 benchmark。

## 批判 2（P2）：非法 JSON fallback 的保守策略需业务评估
- **问题**：校验失败重试1次后固定 need_search=true，能避免500，但可能在无需检索的问题上增加一次检索成本/延迟。
- **证据**：decision_validator.py + 契约测试。
- **差距**：没有按意图/风险等级区分 fallback。
- **方案**：task29 评估 fallback 命中率、额外延迟和 token 成本；必要时按 query 分类选择 direct-answer 或 safe-search。
- **最小验证**：构造闲聊/知识/工具三类非法 JSON，比较准确率、P95、成本。
- **收益/成本**：降低无效检索；成本为评估集与多轮运行。

**结论**：两条为后续评估项，不阻塞 task27。
