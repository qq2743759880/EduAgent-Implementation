"""
app/core/ — 框架层（Phase 重构：task09）

提供：
- resp.py：统一响应壳 {code, message, data}
- cache.py：Redis 缓存分层（三防：穿透/击穿/雪崩）
- lock.py：Redis 分布式锁（SETNX + Lua 释放）
- idempotency.py：幂等性组件（SET NX EX 86400 + 响应缓存 24h）
- breaker.py：Polaris 式熔断器（三态 + Redis Hash 共享 + Gauge）
- trace.py：链路追踪（trace_id/span ContextVar）
- queue.py：Redis List 任务队列（BLPOP + 本地内存降级）
- crud_mixin.py：Repository 层基类（软删/分页/keyset）
"""