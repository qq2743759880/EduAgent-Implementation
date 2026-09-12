# 接口变更单：MCP health-scan 异步化（reshape-b / C18 承接 / taskB1a）

> 状态：**草案待用户签字**（dev-plan-reshape-a.md P4'：变更单→用户签字→B1b 冻结 `contracts/reshape-b.json`→B1 实施）。
> 起草：独立调研 agent（零生产代码），2026-09-06。
> 现状段落全部基于后端源码实读（文件:行号见各处标注），非批判文档转述。

---

## ① 动机（现状实证）

### 1.1 同步串行全量扫描，最坏分钟级阻塞

现行端点 `POST /api/mcp/health-scan`（`edu-agent/app/mcp/router.py:398-402`）在请求 handler 内同步等待全量扫描完成才返回：

```python
# router.py:398-402
@router.post("/health-scan", response_model=dict,
             summary="P8-15【调试】对所有 yn=1 的 MCP Server 做批量健康扫描")
async def p8_health_scan():
    result = await executor.scan_all_servers_health()
    return ok(MCPHealthScanResp.model_validate(result))
```

扫描实现是**严格串行**的 for-await（`edu-agent/app/mcp/executor.py:1938-1943`）：

```python
# executor.py:1938-1943（scan_all_servers_health）
for r in rows:
    sid = int(r["id"])
    try:
        hc = await health_check_server(sid)   # ← 一台等完才轮到下一台
```

单台 stdio 健康检查的最坏耗时上界（`executor.py:1248,1255-1257`）：

```python
# executor.py:1248  timeout_s = max(2.0, connect_timeout_ms/1000)   ← connect_timeout_ms 默认 5000 → 5s
# executor.py:1255-1257  asyncio.wait_for(_stdio_exchange_async(...), timeout=timeout_s + 8.0)
```

即 stdio 单台最坏 ≈ `connect_timeout_ms/1000 + 8` 秒（默认 5000ms 时 ≈13s）；对端无响应但端口挂死的典型失败 ≈5s 超时。http/sse 路径单台上界 = `call_timeout_ms/1000`（默认 15000ms → 15s，`executor.py:1275,1277`）。**15 台全 stdio 默认配置的超时串行扫描 ≈ 75s（批判口径）~195s（wait_for 上界口径）**，全程占用 event loop 内该请求，其他并发 health-scan 请求只能排队。

### 1.2 每次检查重新 spawn 子进程，sessions 池建了不用

stdio 健康检查每次调 `_stdio_exchange_async`，其中**每次都全新拉起子进程**再做 initialize+ping 三步握手，检查完即 shutdown/kill：

```python
# executor.py:234-240（_stdio_exchange_async 内）
proc = await asyncio.create_subprocess_exec(
    executable, *args_list,
    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE, cwd=cwd, env=env,
)
```

```
health_check_server (executor.py:1247-1258)
  → _stdio_exchange_async (executor.py:212) → create_subprocess_exec (:234) 每次新 spawn
  → initialize (:1250-1251) + notifications/initialized (:1252) + ping (:1253) 全套握手
  → graceful shutdown (:279-285) / 进程终止 → 下次检查再来一遍
```

而**同文件里 stdio 长连接会话池已经存在且可用**（"建了不用"实锤）：

- 池本体：`_SESSION_POOL` / `_SESSION_LOCK` / `_SESSION_GC_LIMIT=64`（`executor.py:1443-1445`）
- 建会话：`session_create`（`executor.py:1518`，spawn 于 :1552、initialize 握手入池于 :1569 附近）
- GC：`session_pool_gc`（`executor.py:1478-1479`，空闲 TTL + 超上限按最久空闲回收）
- **池内收发通道现成**：`_stdio_exchange_via_session(session_id, requests, timeout_s)`（`executor.py:1674-1733`）——通过池内长连子进程发 N 条 JSON-RPC，死会话自动清理（:1682-1685）、收尾在锁内更新 `last_used_ms/call_count`（:1727-1731）
- 会话端点组已在 router 暴露：`POST/GET /api/mcp/sessions`（`router.py:408,419`）、`GET /sessions/{id}`（:427）、`POST /sessions/{id}/touch`（:436）、`DELETE /sessions/{id}`（:446）

MCP 规范对 stdio 的意图本就是长生命周期连接 + initialize 复用（https://modelcontextprotocol.io/specification/2025-06-18/basic/transports ，2026-09-06 访问），当前实现把 server 当一次性脚本反复 spawn，正是 C18 批判的差距点。

### 1.3 前端被迫 120s 超时掩盖

`edu-frontend/public/admin-mcp.html:598`：

```js
EAPI.TIMEOUT_MS=120000;  /* 健康扫描/工具调用耗时可达 30-60s，默认 15s 会误超时 */
```

edu-api.js 全局默认超时是 15s（`edu-frontend/public/edu-api.js:26` `DEFAULT_TIMEOUT_MS = 15000`），admin-mcp 页把**整页所有 API** 的超时拉到 120s 来迁就这一个同步扫描端点——15s 默认超时对快速接口的保护在此页全面失效。前端按钮在扫描期间禁用并提示"扫描中…（Server 多时较慢）"（`admin-mcp.html:516-517`），用户面对的是无进度的分钟级白等。

### 1.4 鉴权现状（不变更项，备案）

`/api/mcp` 整个 router 挂 `dependencies=[Depends(require_role([UserRole.ADMIN]))]`（`router.py:40-43`）——新端点挂在同一 router 下自动继承 ADMIN 鉴权，无额外动作。

---

## ② 新契约提案

### 2.1 提交扫描任务

```
POST /api/mcp/health-scan-async          （202 Accepted 语义）
请求体：无（与现行 POST /health-scan 一致，无参数）
响应（HTTP 202，标准响应壳）：
{
  "code": 0, "message": "accepted",
  "data": {
    "job_id": "hs-a1b2c3d4e5f6",         // "hs-" + 12 位 hex（对齐 session_id "ms-" 前缀风格，executor.py:1612）
    "status": "running",
    "created_ms": 1757139000000,
    "scanned_total": 15                   // 提交时 yn=1 的 server 数，供前端算进度分母
  }
}
```

**单飞行（single-flight）语义**：已有 running job 时**不报错、不重复起任务**，直接返回现有 `job_id`（幂等，message=`"already_running"`）。理由：admin-mcp 是调试域，双击/多页签重复提交应收敛而非 409 噪音。（备选：409 + `40950 MCP_SCAN_IN_PROGRESS`；B1b 冻结时定，默认取幂等方案。）

### 2.2 轮询任务结果

```
GET /api/mcp/health-scan/{job_id}
响应（HTTP 200，标准响应壳）：
{
  "code": 0, "message": "ok",
  "data": {
    "job_id": "hs-a1b2c3d4e5f6",
    "status": "running" | "done",
    "created_ms": 1757139000000,
    "finished_ms": null | 1757139058000,
    "progress": {"scanned": 6, "total": 15},      // running 时增量可见（实现允许先退化：running 时 scanned=0）
    "result": null | {                             // done 时与现行 MCPHealthScanResp 完全同构（schemas.py:333-338）
      "scanned": 15, "ok_count": 12, "error_count": 3,
      "items": [ { "server_id":1, "server_code":"...", "display_name":"...",
                   "ok":true, "latency_ms":312, "reason":null, "last_health_at":"..." } ],
      "elapsed_ms": 52300
    }
  }
}
```

- `result` 复用现行 `MCPHealthScanResp` schema（`schemas.py:323-338`），**消费方字段零学习成本**。
- **job 不存在/已过期/服务重启丢失**：HTTP 404 + 壳 `code="40450"`（新增 `MCP_SCAN_JOB_NOT_FOUND`，域段 404xx，对齐 `app/common/error_codes.py:10,34` 分段；B1b 冻结时定稿，兜底可退 40400）。前端收到 404 语义 = "结果不可得，请重新发起扫描"，**不得**当成扫描失败污染上次结果。
- job 存储为进程内存 dict + TTL（建议 10 分钟，GC 复用 `session_pool_gc` 同款思路）；单实例演示架构下不引入 Redis 依赖（R1-③ 队列先例在，但调试域 job 不值得跨实例持久化；此决策 B1 实施时可复核）。
- 后台执行：`asyncio.create_task` 后台跑扫描循环；扫完写 job 终态。扫描内部仍串行（各台互不依赖，并行化是后续优化，不在本变更单范围——本单只解决"阻塞请求"与"重复 spawn"两个崩点）。

### 2.3 单台健康检查复用 sessions 池（性能改造点，随本变更单一并冻结）

`health_check_server` 的 stdio 路径改造为**先池后 spawn**：

1. 查 `_SESSION_POOL` 中该 server 的健康检查专用长连会话（新增内部注册表 `server_id → hc_session_id`，不与调试会话混用，避免 dev-plan Eng finding1 指出的 GC 竞争；`session_pool_gc` 对 hc 会话豁免或用独立 TTL）；
2. 命中且进程存活 → 走现成 `_stdio_exchange_via_session`（`executor.py:1674`）只发 `ping` 一条（initialize 已在入池时完成，省掉 spawn + initialize 两次大头的绝大部分耗时）；
3. 未命中/进程死 → 走一次 `session_create` 式完整握手入池（或退化为现行一次性 spawn，见 3.2 回滚开关）；
4. ping 超时/进程死 → 清理池条目，本次按不健康上报，下次重建。

http/sse 路径维持现状（每次新建 AsyncClient 成本为毫秒级，非崩点，不动）。

### 2.4 旧端点兼容窗口

- `POST /api/mcp/health-scan`（同步）**原样保留 30 天**（自 B1 上线日起算），行为与响应 schema 不变；OpenAPI summary 追加 `Deprecated: 请迁移 /health-scan-async， removal 预计 <日期>`。
- 窗口内监控旧端点调用量（现有 call-log 机制即可），归零 + 30 天期满后删除（删除走当期回归，不在本单内自动执行）。

---

## ③ 兼容性影响面

| 消费方 | 现状调用 | 影响 | 迁移动作 |
|---|---|---|---|
| `edu-frontend/public/admin-mcp.html` | `EAPI.post("/api/mcp/health-scan",{})`（:518，同步等待全量结果，:519 直接读 `scanned/ok_count/error_count/elapsed_ms`） | 旧端点保留期内**零破坏**；不改则继续 120s 白等 | 迁移到 POST `-async` + 每 1s 轮询 GET（建议 2s 间隔上限 60 次）；同时可把 `EAPI.TIMEOUT_MS=120000`（:598）降回默认 15s——这是本变更单的额外收益：整页 API 超时保护恢复 |
| `/api/mcp/console` 内嵌调试页 | 同步 health-scan 由页面 JS 调（`router.py:826`：`fetch(API_BASE+"/api/mcp/health-scan",{method:"POST"})`） | 同上，保留期内零破坏 | 窗口内择机迁移；不迁移则删除日一并处理 |
| 契约测试 / 回归脚本 | `test-reports/interface-acceptance.md` 记录的现行端点行为 | 旧端点行为不变 → 存量回归不动 | 新增异步两端点的契约用例（B1 DoD） |
| 未知第三方调用方 | 无（管理端调试域，无对外开放面） | 无 | 无 |

响应壳/分页壳：新端点沿用 `{code:0,message,data}` 壳（`ok()` 包装），不涉及分页 DTO；对 `edu-api.js` 客户端零改动。

## ④ 回滚方案

1. **代码级**：新端点为纯增量（新 route + 新 job 表 + `health_check_server` 内部池化分支带 `settings.MCP_HC_USE_POOL` 式开关），不修改旧同步端点任何行为。回滚 = ①前端按钮回指旧端点（admin-mcp.html 单点 :518）→ ②关池化开关（退回一次性 spawn 路径，代码保留）→ ③下个版本删除新端点。
2. **数据级**：job 状态纯进程内存，无 DB schema 变更、无迁移脚本；回滚零数据动作。`mcp_server` 表的 `last_health_ok/last_health_at` 写入路径（`executor.py:1306`）不变。
3. **行为级回退判据**：池化后若出现误判（池内会话僵死但 ping 假阳性/假阴性超阈值），关开关即回到现状语义，接受回到 ~5s/台串行（等于回滚到今天的行为，不更差）。
4. 兼容窗口本身就是回滚缓冲：30 天内旧端点始终可用，前端切回即恢复现状体验。

## ⑤ 验收指标（可证伪）

| # | 指标 | 现状基线（代码口径） | 目标 | 测法 |
|---|---|---|---|---|
| 1 | 单台 stdio health 延迟 P95 | ~5s 量级（spawn + initialize + ping 全套；批判实测口径 ~5s） | **< 500ms**（池内仅发一条 ping） | 真 Redis/真 server 环境 pytest 计时脚本，≥30 次采样取 P95（B1 GWT 原文判据） |
| 2 | 扫描期间并发不排队 | 50 并发 POST /health-scan = 50 次全量串行扫描（分钟级雪崩） | 50 并发混合请求（1 POST + 49 GET 轮询）全部 <100ms 返回；仅 1 个后台 job | asyncio + httpx 并发压测脚本，B1 DoD |
| 3 | 提交即时性 | POST 同步等全程 | POST /health-scan-async P95 < 200ms（202 立返） | 同上压测 |
| 4 | 全量扫描总时长 | 15 台串行 ≈75s+（超时放大可至 ~195s 上界） | ≤ max(单台上界) + 5s（并行化不在本单，串行后台化后总时长与现状同量级但**不占请求**；若顺带并行化则 15 台 < 20s，列为 stretch 不作验收线） | job `elapsed_ms` 字段实测 |
| 5 | 兼容窗口回归 | 现行 POST /health-scan 行为 | 窗口内逐次回归与 `test-reports/interface-acceptance.md` 记录一致（响应 schema 逐字段） | 现有 interface_acceptance 脚本扩展 |
| 6 | 前端体验 | 按钮分钟级禁用白等 | 轮询期按钮态可见进度；`EAPI.TIMEOUT_MS` 从 120000 恢复 15000 后整页无误超时 | CDP 手工走查（禁 Playwright）+ 页面 JS 无错 |

## ⑥ 签收

- [ ] 用户签字（P4'：签字后 B1b 冻结 `contracts/reshape-b.json`，hash 上看板）
- [ ] 错误码定稿：`40450 MCP_SCAN_JOB_NOT_FOUND` / 幂等 vs 409 单飞行语义（②.2 两个默认案的确认）
- [ ] 兼容窗口起算日 = B1 上线日（30 天）

---

### 附：本变更单证据文件清单（2026-09-06 实读）

| 文件 | 关键行 | 证据内容 |
|---|---|---|
| `edu-agent/app/mcp/router.py` | 40-44, 398-402, 408-453, 826 | router 前缀/ADMIN 鉴权、同步端点、sessions 端点组、console 页内嵌调用 |
| `edu-agent/app/mcp/executor.py` | 212-290, 1237-1307, 1443-1445, 1478-1479, 1518-1627, 1674-1733, 1928-1963 | 每次 spawn、单台超时口径、池本体、GC、session_create、池内收发通道、串行全量扫描 |
| `edu-agent/app/mcp/schemas.py` | 323-338 | MCPHealthScanItem/Resp（新契约 result 复用） |
| `edu-agent/app/common/error_codes.py` | 10-11, 34, 36 | 404xx/409xx 分段与通用码（新码 40450 提案依据） |
| `edu-frontend/public/admin-mcp.html` | 516-521, 598 | 现有同步调用与按钮行为、120s 超时覆盖 |
| `edu-frontend/public/edu-api.js` | 26, 295 | 默认 15s 超时（被 admin-mcp 覆盖的对照基线） |

## 用户签字(2026-09-06)
- ①并发语义:**幂等**——同参数重复 POST 返回同一 job_id
- ②错误码:**启用 40450**(job 不存在)
→ 据此冻结 B-contract,进入 B1b。
