# task33 验收批判（强制技术批判）

> 对象：task33 MCP 增强（Trae，commit f77e7d2）
> 结论：**验收通过**（GWT 全达成、批判承接核对、降级如实标注）。

## 实证结果
- commit `f77e7d2`（10 文件 +1103/-47）；description_reviewer/breaker/executor/registry/schemas/router/迁移/契约 交付。
- 单测 **9 passed** 实跑确认（纯函数+熔断器，无 LLM/无 DB）。
- GWT① 描述打分 6 项规则 + FAST 重写 + 审计日志；GWT② 连续 5 失败→OPEN→30s 半开→探针；GWT③ specs_for_access 过滤 admin_only + 只读 60s 缓存；GWT④ 契约 v1.0（解锁 task62）。
- 批判承接：task09 熔断 per-server、task27 权限复用、task29 缓存落地逐条核对；真实 LLM 重写如实标注窗口内预留。

## 批判 1（P2）：真实 FAST 重写未实测（窗口纪律约束），迁移未应用到 DB
- **问题**：description_reviewer 的 LLM 重写路径未真实触发（仅单测纯函数）；alembic 迁移未实际执行到 DB。
- **方案**：窗口内（12:00-14:00/18:00-9:00）安排一次真实 FAST 重写验收 + `alembic upgrade head` 应用迁移，验证 mcp_tool 新列与审计表落库。

## 批判 2（P2）：熔断半开放并发探针 + Redis 原子性边界
- **问题**：半开放探针并发限制（同刻多探针放行）与 Redis 状态原子性未加固（报告已披露）。
- **方案**：task39 压测或后续加固子代理补探针并发闸 + Redis 原子 check-and-set。

## 批判 3（P2）：只读缓存 key 稳定性依赖参数序列化，跨版本漂移风险
- **问题**：`_mcp_cache_key` 对参数 MD5，若工具入参 schema 变更，旧缓存 key 语义漂移。
- **方案**：缓存 key 附加 tool schema 版本或 API 版本，变更自动失效（对齐 task97 缓存监控）。

**结论**：三条为后续改进项，不阻塞 task33。