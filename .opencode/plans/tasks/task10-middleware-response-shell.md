# task10: middleware/ 目录 + 响应壳全模块统一 + 错误码分段

> **类型**：backend ｜**执行工具**：Trae ｜**阶段**：P3 ｜**并行组**：W2 ｜**工作量**：XL
> **前置**：task09 ｜**后置（联调节点）**：**契约冻结① → 前端 task40（api-client 解包）**；task11~23 全部依赖

## 1. 选型依据
- tech-source-audit.md §一（响应壳 {code,message,data} = 字节网关惯例）
- tech-source-audit.md §四（幂等三层纵深第一层中间件；限流滑动窗口）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev + be-validator | middleware 迁入 + 逐点 ok() 改造 + 错误码分段 |
| 测试 | sd-tester + sd-challenger | 契约测试遍历全部 router |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
| 工具 | context7 MCP | Starlette BaseHTTPMiddleware |
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
- middleware/：auth_middleware、rate_limit（IP+user_id 双维度 + 交易档 order 10/min/payment 30/min/refund 5/min）、trace_middleware（X-Trace-Id 透传 + 慢查询日志带 trace_id）、circuit_breaker（轻量打标）、idempotency（/api/trade/order|payment|refund|coupon/receive|after_sales/ticket 前缀）
- error_codes.py 分域段码：400xx 参数/401xx 认证/403xx 越权/404xx/409xx/422xx/429xx/5xxxx + 交易 4xx2x/售后 4xx3x/学习 4xx4x
- 全局异常 handler `{code,message,data:null}`（detail 仅 DEBUG）；RespWrapMiddleware 兜底（白名单跳过 SSE/文件流）
- 中间件注册顺序：SecurityHeaders → CORS → Trace(融合 Auth) → Idempotency → RateLimit → CircuitGuard → RequestLogging

## 5. 验收标准（Given/When/Then 全文）
- Given 契约测试遍历全部 router，When 对每个端点断言响应结构，Then 成功 `{code:0,message:"ok",data}`、失败 `{code:<字符串>,message,data:null}`，SSE 端点 done/error 事件内嵌统一壳，通过率 100%
- Given 幂等中间件上线，When 同一 Idempotency-Key 重复 POST /api/trade/order，Then 第二次返回首次缓存的响应（含相同 order_no），业务仅执行一次
- Given TraceMiddleware 生效，When 触发一次慢 SQL 与一次 LLM 调用，Then 两处日志携带同一 trace_id（X-Trace-Id 响应头与日志一致）

## 6. 交接与记忆（契约冻结①）
- 完成 → 写 `E:\stu\project\stu\EduAgent实施手册\.opencode\handoffs\task10-contract.md`：响应壳规范 + 错误码清单（字符串）+ 真实 curl 成功/失败示例 + SSE 事件壳示例
- 看板 task10=READY_FOR_FRONTEND（解锁 TraeWork task40）→ sync.ps1
- 交付物：middleware/ 5 件 + error_codes.py + 契约测试套件 + 交接单
