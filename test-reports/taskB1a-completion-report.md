# taskB1a 完成报告：health-scan 异步化接口变更单

> 日期：2026-09-06。零生产代码（未改任何 .py/.html/.js）。未 git commit（按守则留给编排者）。
> 交付物：`.ai-hub/plans/contract-change-reshape-b-health-scan.md`（草案，待用户签字，P4'）。

## 1. 做了什么

按变更单五段结构（动机/新契约/兼容面/回滚/验收指标）起草 C18 承接变更单。**写文档前实读了全部涉及的后端与前端文件**，"现状"段全部以 文件:行号 落证，未转述批判文档。

## 2. 资产消费证据段

| 消费的资产 | 用途 | 实读核实结果 |
|---|---|---|
| `.ai-hub/plans/reshape-a-技术批判.md` C18 行 | 变更动机来源 | 批判声称三点全部在代码中实证（见下 §3），无一凭转述 |
| `.ai-hub/plans/dev-plan-reshape-a.md` taskB1a/B1 GWT + 批判承接核对表 C18 行 | 变更单范围与验收指标（单台 P95<500ms、50 并发不排队） | 变更单 §5 指标 1/2 逐条对应 |
| `edu-agent/app/mcp/router.py`（851 行，实读关键段 28-57/390-460） | 现状端点与鉴权 | `POST /health-scan` 同步等全量（:398-402）；router 级 ADMIN 鉴权（:40-43）；sessions 端点组齐全（:408-453）；console 内嵌页也调同步端点（:826） |
| `edu-agent/app/mcp/executor.py`（1963 行，实读关键段 212-290/1237-1307/1440-1500/1674-1733/1924-1963） | 现状行为与改造点 | 串行 for-await（:1938-1943）；stdio 每次 spawn（:234）；单台超时口径 connect_timeout+8s（:1248,1255-1257）；池本体/锁/GC 上限（:1443-1445,1478）；**池内收发通道 `_stdio_exchange_via_session` 已存在**（:1674-1733）→ 变更单 §2.3 改造点即基于它 |
| `edu-agent/app/mcp/schemas.py:323-338` | 新契约 result 复用 | MCPHealthScanResp 字段与任务要求 shape 完全一致，直接复用 |
| `edu-agent/app/common/error_codes.py:10-36` | 新错误码提案依据 | 404xx/409xx 分段规则 → 提案 `40450 MCP_SCAN_JOB_NOT_FOUND` |
| `edu-frontend/public/admin-mcp.html`（603 行，实读 :505-549/:598） | 兼容影响面 | 同步调用 + 按钮禁用（:515-521）；**`EAPI.TIMEOUT_MS=120000` 覆盖实证（:598）**——批判所说"120s 超时掩盖"逐字属实，且发现它牺牲了整页 15s 默认保护（edu-api.js:26） |

## 3. 关键核实发现（超出批判文档的新事实）

1. **批判口径偏保守**：批判写"15 台×5s 最坏 75s"，代码口径单台 stdio 最坏 = `max(2.0, connect_timeout_ms/1000) + 8.0`（executor.py:1248,1255-1257），默认配置下 ≈13s/台，理论上界 ≈195s；75s 只是 5s 超时近似。变更单 §1.1 如实写了双口径。
2. **池复用的通道函数已存在**（`_stdio_exchange_via_session`，executor.py:1674），C18 批判"建了不用"的"用"字比批判预想的更近——改造不需要新写收发层，主要是 health 检查专用会话注册 + 生命周期豁免 GC。变更单 §2.3 据此给出最小改造路径，并按 dev-plan Eng finding1 用"hc 专用会话独立注册表"回应池 GC 竞争。
3. **120s 超时是整页级的**：admin-mcp.html:598 的覆盖使该页所有 API 失去 15s 默认保护——异步化后可顺手恢复，写进变更单 §3 收益与 §5 指标 6。
4. http/sse 路径的健康检查（executor.py:1276-1295）每次新建 AsyncClient 但成本毫秒级，判定为非崩点不在本单改造（避免变更单范围蔓延）。

## 4. 变更单要点（速览）

- 新契约：`POST /api/mcp/health-scan-async` → 202 + `{job_id,status,created_ms,scanned_total}`（单飞行幂等：running 时返回现有 job_id）；`GET /api/mcp/health-scan/{job_id}` → `{status:running|done, progress, result=MCPHealthScanResp 同构}`；job 不存在 404+`40450`。
- 兼容：旧同步端点原样保留 30 天（自 B1 上线日），OpenAPI 标 Deprecated；admin-mcp.html 与 console 内嵌页两个消费方零破坏。
- 回滚：纯增量端点 + 池化开关 + 无 DB 变更；前端单点切回即恢复现状。
- 验收：单台 P95<500ms、扫描期 50 并发不排队、POST 提交 P95<200ms、窗口内旧端点回归一致、前端 15s 默认超时恢复后无误超时。
- 待用户签字定稿两项：单飞行幂等 vs 409、错误码 40450（B1b 冻结前）。

## 5. 自检发现

1. 变更单刻意**不含并行扫描**（15 台并发扫）：它不解决"阻塞请求"与"重复 spawn"两个崩点，塞进同一单会扩大签字面与回滚面——降级为 §5 指标 4 的 stretch 项，避免范围蔓延。
2. job 存储选了进程内存而非 Redis：理由（调试域/单实例/无持久价值）已写明，但与项目 R1-③/task39 的 Redis 先例存在路线张力——已在 §2.2 标注"B1 实施时可复核"，不是单方拍死。
3. `scanned_total` 是新契约里唯一不在现行 schema 中的新字段（进度分母），若用户要求零新增字段可退化为 progress 缺省——已留意 B1b 冻结时确认。
4. 未做任何运行时验证（零生产代码守则下未起后端复跑同步端点实测 75s）；现状耗时全部为代码口径推演 + 批判实测引用，变更单 §5 的验收脚本将在 taskB1 实施期补真实基线测量。
