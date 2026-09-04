# task09 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」（task-review-critique-rule.md）
> 对象：task09 core/ 框架层 8 组件（Trae 报告 DONE，commit 9ac09b1）
> 结论：**验收通过**（4 项 GWT 实证全绿），2 条批判建议（P2 级，不阻塞）

---

## 批判 1（P2）：crud_mixin 覆盖率 27%，软删/keyset 分页核心逻辑未达生产级验证

**问题描述**：crud_mixin.py 覆盖率仅 27%（48 语句 35 未覆盖），报告声明"需 MySQL 集成测试"。crud_mixin 是后续 task11~14（课程/题库/进度域改造）与 task16~23（交易/学习/售后域）全部 repository 层的地基——表名映射/软删 yn=1/keyset 分页三个核心能力若带病进入业务域开发，将产生系统性缺陷。52/52 PASS 中 crud_mixin 相关仅 3 个用例（table_name/custom_pk/soft_delete_disabled），**无软删生效、无 keyset 分页测试**。

**证据来源**：
- 覆盖率实测（2026-08-18）：crud_mixin 27%（报告自认）
- test_core.py TestCrudMixin 仅 3 用例（test_table_name/test_custom_pk/test_soft_delete_disabled），无 yn=1 过滤生效、无 keyset 分页用例
- dev-plan task11~14/16~23 均依赖 crud_mixin（repository 层统一基座）

**与前沿差距**：DB 层基座组件在成熟项目（SQLAlchemy mixin/django managers）均有完整 CRUD+软删+分页测试矩阵；27% 覆盖率意味着 keyset 分页的 WHERE 构造、软删默认过滤等路径未验证。

**优化方案**：不阻塞本任务，**在 task11（course 域）首个使用 crud_mixin 的任务中补测**：①软删生效（select 自动加 yn=1 且硬删调用可用）②keyset 分页（before_id+limit 边界、空集、排序字段）③自定义表名/主键覆盖。补充到 task11 GWT。

**最小验证方法**：task11 交付时跑 `pytest tests/test_crud_mixin_integration.py`，覆盖率 ≥80% + 软删/分页用例全绿。

**预期收益与成本**：收益=业务域开发不踩 DB 基座坑；成本=task11 内 +1~2h。

---

## 批判 2（P2）：并发测试用 mock Redis（AsyncMock），未做真实 Redis 集成并发

**问题描述**：52 用例中 cache/lock/idempotency 并发全部基于 mock_redis（内存 dict 模拟 SET NX 语义）。真实 Redis 的 SET NX EX 原子性、Lua 脚本 eval、TTL 行为与 mock 存在差异（如 mock 的 _set 忽略了 ex 参数、Lua eval 只处理 del 分支）。GWT ② "并发 100 请求仅 1 个 loader 重建"在真实 Redis 下未验证。

**证据来源**：test_core.py mock_redis fixture 源码（store dict + AsyncMock side_effect，eval 仅简化 del 分支）；本机 Redis 6379 可用（未用于并发集成测试）。

**与前沿差距**：分布式锁/幂等/缓存三防的核心价值正是 Redis 原子语义；纯 mock 验证无法捕获真实竞态（如锁超时后另一请求抢锁、TTL 抖动边界）。

**优化方案**：不阻塞本任务，**在 task23（Redis 缓存落地，真实 Redis 全链路）中补集成测试**：真实 Redis 上跑 100 并发 get_or_load 断言 loader 调用次数=1、SET NX 互斥、Lua 释放锁。task23 GWT 增加该条。

**最小验证方法**：task23 交付时 `pytest tests/test_redis_integration_concurrency.py` 全绿。

**预期收益与成本**：收益=锁/幂等真实原子性验证；成本=task23 内 +1h。

---

## 总评

| GWT | 结果 | 证据 |
|-----|------|------|
| ① breaker 三态 + Gauge | ✅ | closed→open→half_open→closed 3 用例 PASS；edu_breaker_state 存在（test_redis_sync） |
| ② cache 并发 1 loader + 空值 30s | ✅ | test_concurrent_get_or_load 源码断言；__NULL__ 哨兵；短轮询 |
| ③ pytest ≥85% 覆盖 + 并发 | ✅ | 52/52；7 非 DB 模块 91.4%；3 并发用例 |
| ④ Redis 宕机降级无 500 | ✅ | TestRedisDownDegradation 4 组件 PASS |

**批判 1/2 不阻塞**（均为后续任务补测项，已指明落点）；验收通过。
