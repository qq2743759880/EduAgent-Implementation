# task09: core/ 框架层（resp/cache/lock/idempotency/breaker/trace/queue）

> **类型**：backend ｜**执行工具**：Trae ｜**阶段**：P3 ｜**并行组**：W2 ｜**工作量**：XL
> **前置**：无（与 P1/P2 并行启动）｜**后置（联调节点）**：task10（middleware 依赖）、task23（缓存）、task24/33（AI/MCP）

## 1. 选型依据
- tech-source-audit.md §一（FastAPI 全异步、模块化单体分层）
- tech-source-audit.md §四（缓存三防：空值 30s/SETNX 互斥/TTL 抖动；Polaris 三态熔断：min_requests=20/error_rate=0.5/open 30s/探针 3；幂等三层纵深之第一层；Redis 多角色）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev + be-architect | core 模块设计与实现 |
| 测试 | sd-tester + sd-challenger 并行 | 并发/故障注入用例（100 并发 gather） |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | SARIF |
| 加固 | harden skill | 组件降级路径审查 |
| 工具 | context7 MCP | FastAPI/pydantic v2 文档 |
| 提交 | commit skill | — |

## 3. 执行方式（Trae 手动调度，无 Workflow API）

Trae Code 无 opencode 专属的 `Workflow()` API，按 `D:\.ai-hub\workflows\dev-standard.mjs` 的 8 阶段**手动调度**（效果等价）：
```
1. 开发阶段   -> 调 sd-dev + be-architect + be-validator（读任务文档 + tech-source-audit）
2. 测试阶段   -> 调 sd-tester（+ sd-challenger 对抗）；数据库校验用 RunCommand 跑 mysql CLI / Python 脚本（无 mysql MCP）
3. 修正阶段   -> 据测试报告回 sd-dev 修复
4. 审查阶段   -> 调 review-screener-1/2/3 -> review-moderator -> review-judge（SARIF）
5. 提交阶段   -> git commit（message 含 task 编号）
```

mysql MCP 未在 Trae 环境注册（当前 MCP 仅 integrated_code_mode / integrated_goal）：
- 数据库校验改用 **RunCommand + mysql CLI / Python 脚本**（先例：scripts/verify_schema.py、scripts/verify_task07_counts.py）
- 或手动在 设置->MCP 按 `D:\.ai-hub\mcp\index.json` 模板添加 mysql


## 4. 实现规划要点
- resp.py：RespModel {code,message,data} + ok()/fail()
- cache.py：get_or_load 三防（空结果 30s 哨兵/SETNX 互斥重建/TTL ±10% 抖动 + Lua 释放锁校验 token）
- lock.py：SETNX+Lua 分布式锁
- idempotency.py：SET NX EX 86400 + 响应缓存 24h
- breaker.py：closed/open/half_open + Redis Hash 共享（breaker:{name}）+ 100ms 本地缓存 + edu_breaker_state Gauge
- trace.py：trace_id_var/span_id_var ContextVar + start_span
- queue.py：Redis List BLPOP 任务队列
- crud_mixin.py：表名/软删 yn=1/keyset 分页
- 每个组件显式降级路径（Redis 挂→缓存直通/幂等放行/checkpoint 本地暂存）

## 5. 验收标准（Given/When/Then 全文）
- Given breaker 组件完成，When 模拟 50% 错误率注入，Then closed→open 自动切换、open 期快速失败抛 CircuitOpenError、半开放行探针恢复 closed；`edu_breaker_state` Gauge 指标可观测
- Given cache.get_or_load 完成，When 并发 100 请求同一过期热点 key，Then 仅 1 个 loader 实际重建（互斥锁生效），其余返回旧值或短轮询；loader 返回 None 时写入 30s 空值缓存
- Given 全组件完成，When 运行 pytest 单测套件，Then 覆盖率 ≥85% 且含并发场景（asyncio.gather 100 并发）用例
- Given Redis 宕机注入，When 各组件调用，Then 走降级路径不抛 500（故障注入用例随组件交付）

## 6. 交接与记忆
- 完成 → 看板 task09=DONE → sync.ps1
- 交付物：app/core/ 8 模块 + 单测套件（含并发/故障注入）
