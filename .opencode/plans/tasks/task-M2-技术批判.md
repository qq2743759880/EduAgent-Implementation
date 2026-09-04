# task-M2 验收批判（强制技术批判）

> 对象：task-M2 Redis 共享向量降级链（Trae，commit e8956af）
> 结论：**验收通过**（AC1~AC5 全绿、ponytail 简化、Redis 状��如实披露）。

## 实证结果
- commit `e8956af`（5 文件 +741）；vector.py redis 档位 + invalidate + store 联动 交付。
- 契测 **18 passed**（M2 7 + task25 11 回归）实跑确认。
- AC1 跨实例一致（0.7715/0.1376 双侧一致）；AC2 内存兜底标注；AC3 失效联动（Dream 盖章移除索引）；AC4 并发写末写胜出；AC5 回归。
- 诚实披露：沙箱 Redis 拒绝连接，用共享内存 fake redis 模拟多实例（生产走 get_redis() 接口免改码）。
- 竞品对标 Claude Redis 共享向量 + rewind 横向扩展。

## 批判 1（P1，环境）：本机 Redis 6379 实际不可达，真实 Redis 验证未做
- **问题**：报告披露 127.0.0.1:6379 拒绝连接（与本机"已启动"记忆不符）；AC1/AC3/AC4 用 fake redis 模拟，未在真实 Redis ��证。
- **方案**：重启本机 Redis（edu-agent/tools/redis/redis-server.exe）后补一次真实 Redis 跨实例验证（AC1/AC3/AC4 重跑）。

## 批判 2（P2）：HSET 扫描式召回，未用 Redis Stack 向量索引
- **问题**：原生 Redis 无向量模块，HSET 扫描式（报告披露，留 SCAN_LIMIT 兜底）。
- **方案**：用户量级增长后评估升级 Redis Stack 向量索引。

## 批判 3（P2）：owner 反向 HSET 额外存储 + 一致性
- **问题**：owner 映射为 O(1) 删除，但多实例并发写 owner 映射需一致。
- **方案**：AC4 已测并发 upsert；owner 映射的删除一致性可后续加固。

**结论**：批判①为环境验证项（需重启 Redis 补测），批判②③为后续增强；task-M2 本体验收通过。

> ✅ **2026-08-28 已实测闭环**：真实 Redis（127.0.0.1:6379 重启）AC1 跨实例一致(0.7697/0.4266 双侧一致)/AC3 失效联动/AC4 并发写全绿（见 session-memory 九十七节）
