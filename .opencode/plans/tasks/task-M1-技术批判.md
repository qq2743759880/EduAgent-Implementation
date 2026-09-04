# task-M1 验收批判（强制技术批判）

> 对象：task-M1 记忆事件溯源 + Dream 巩固（Trae，commit 1f4e44b）
> 结论：**验收通过**（AC1~AC7 全绿、契约红线安全、竞品对标完整）。

## 实证结果
- commit `1f4e44b`（13 文件 +3024）；event_persistence/compactor/dream_lock/dream/router + patch_memory_event.sql 交付。
- 契测 **9 passed** 实跑确认（AC1~AC7 + API 鉴权，in-process Mem 变体 + mock llm）。
- AC1 双行+盖章 / AC2 废弃永不召回 / AC3 rewind 正确 / AC4 trace_id 审计 / AC5 压测 40→≤10 收敛 / AC6 Dream 升维（mock）/ AC7 SET NX EX 仅一实例。
- 契约红线：改动全在 app/ai/memory/*，未触碰 /me /learning 路由。
- 竞品对标：CortexDB（WAL append-only）/ ChronoMem（rewind 不物理删）/ Claude AutoDream（5会话+24h+锁）/ Ninad（禁 UPDATE+trace_id）/ VikingMem（TIME_COMPRESS）。

## 批判 1（P2）：真实 Dream LLM 升维未实测（窗口约束）
- **问题**：AC6 用 mock llm，真实 run_dream（LLM 输出 JSON 解析与升维质量）未在窗口内实测（报告如实披露）。
- **方案**：18:00-9:00 窗口内补一次真实 run_dream 实测（当前 16:xx 窗口外，合理）。

## 批判 2（P2）：SqlEventMemoryPersistence 仅代码级，未在 MySQL 实际建表冒烟
- **问题**：patch_memory_event.sql 建表幂等保证，但生产 MySQL 未跑一次冒烟（报告如实披露）。
- **方案**：数据库验收时执行 patch 脚本 + 验证 user_memory_event 真实读写。

## 批判 3（P2）：capacity 收敛上限硬编码（AC5 用 10），生产值未定
- **问题**：压测用容量上限 10，生产实际每用户容量阈值未配置化。
- **方案**：config 增加用户级容量配置，按用户活跃度动态调整（对齐"500 条/用户不真实"批判）。

**结论**：三条为后续验证/改进项，不阻塞 task-M1。

> ✅ **2026-08-28 已实测闭环**（真实 Dream 真实 LLM 验证通过，见 session-memory 九十三节）
