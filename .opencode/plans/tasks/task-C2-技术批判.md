# task-C2 验收批判（强制技术批判）

> 对象：task-C2 缓存前缀达标（Trae，commit ebbdbe4）
> 结论：**验收通过**（AC1~AC5 全绿、契约红线安全、竞品对标完整）。

## 实证结果
- commit `ebbdbe4`（7 文件 +1473）；tool_specs/prompt_cache/agent/cache_meter 交付。
- 契测 **73 passed**（C2 19 + task27 35 + task95 + task97 19 回归）实跑确认，无回归。
- AC1 填充：209→1042、277→1110（≥1024 门槛，字节一致）；AC2 defer 桩零变化不整层失效；AC3 schema 按需展开不进前缀；AC4 命中率 0.7778 OK/0.0 SEV；AC5 回归全绿。
- 契约红线：/me /learning 未动；build_decision_prefix ≤300 不回归。
- 竞品对标：Claude 1024 门槛/DEV 填充注释/Glean 锚定。

## 批判 1（P2）：真实 LLM 命中率实测未做（窗口外，如实披露）
- **问题**：AC4 用 mock 计量，真实 provider cache_creation/read 计数未在窗口内跑 cache_meter.py。
- **方案**：18:00-9:00/12:00-14:00 跑一次 `python scripts/eval/cache_meter.py`（rounds≥6）补真实计数。

## 批判 2（P2）：TOOL_DEFERRED_MODE=True 决策 LLM 仅见 name+summary，准确率待灰度
- **问题**：决策模型看不到 input_schema，可能影响工具选择准确率（报告建议灰度）。
- **方案**：灰度观察决策准确率；若下降设 TOOL_DEFERRED_MODE=False 回退。

## 批判 3（P2）：schema_registry 进程内 dict，多实例不一致
- **问题**：多实例各自注册 schema，进程重启重建；跨实例一致性依赖 task-M2（Redis 共享）。
- **方案**：task-M2 完成后接入 Redis 共享 schema_registry。

**结论**：三条为后续验证/改进项，不阻塞 task-C2。

> ✅ **2026-08-28 已实测闭环**（真实 cache_meter 真实 LLM 验证通过，见 session-memory 九十三节）
