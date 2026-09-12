# B1 完工报告：health-scan 异步化 + 单台健康检查复用 sessions 池

- 任务：B1（reshape-b 第一波 P0，开工单 = `.ai-hub/plans/dispatch-plan-reshape-b.md` §四-B1）
- 冻结契约：`contracts/reshape-b.json`（hash b6772f8d…，用户签字①幂等 / 签字②40450，**未改一字**）
- 变更单：`.ai-hub/plans/contract-change-reshape-b-health-scan.md`（C18 承接，用户已签字）
- 执行：独立后端 agent（ZCode），2026-09-12
- 分支：`feature/opt-waves`；commit：`feat(b)/B1-health-async`

---

## 0. 前置自证（开工单要求，实测通过）

| 项 | 实测 | 结果 |
|---|---|---|
| 服务探测 | 8000 运行中（旧代码，未重启）；3000 运行中；8001 空闲 | ✅ |
| 登录 | `POST /api/auth/login adm02test` → access_token | ✅ |
| 测试 MCP server | `POST /api/mcp/servers/1/health`（stdio-echodemo）→ `{ok:true, latency_ms:270}` | ✅ 满足开工条件 |

## 1. 资产消费证据

| 资产 | 消费方式 |
|---|---|
| `contracts/reshape-b.json`（冻结） | 端点/202/幂等/40450/兼容窗照实现；`health_p95_ms:500`、`scan_concurrent:50` 为验收线；零改动 |
| `contract-change-reshape-b-health-scan.md` | §2.1 job 结构（hs-前缀/status/created_ms/scanned_total/already_running message）、§2.2 TTL 10min 内存 job、§2.3 hc 专用注册表+GC 豁免、§2.4 30 天兼容窗+Deprecation 头、§④ 回滚开关 `MCP_HC_USE_POOL` 全部落进代码 |
| `app/mcp/executor.py` 池代码（`_SESSION_POOL`/`_SESSION_LOCK`/`session_create`/`_stdio_exchange_via_session`/`session_pool_gc`） | 健康检查改走池通道：复用 `session_create` 入池（新增可选参 `timeout_s_override`，调试语义默认不变）、复用 `_stdio_exchange_via_session` 发 ping |
| TT mcp spec 批判条目 C18 | "把 server 当一次性脚本反复 spawn" 的差距点即本任务消除对象 |

## 2. 实现清单（4 文件 + 1 测试）

| 文件 | 内容 |
|---|---|
| `edu-agent/app/config.py` | +`MCP_HC_USE_POOL: bool = True`（回滚开关，False=退一次性 spawn 旧路径）、`MCP_HC_SESSION_TTL_S: int = 600` |
| `edu-agent/app/mcp/executor.py` | ① hc 专用注册表 `_HC_SESSION_BY_SERVER` + 池化锁 `_HC_SESSION_LOCK`（锁序恒为 `_HC_SESSION_LOCK → _SESSION_LOCK`）+ per-server 交换锁 `_HC_XCHG_LOCKS`；② `health_check_server` stdio 分支改"先池后 spawn"，池故障回退旧路径（concluded 语义，池故障绝不误报不健康）；③ `session_pool_gc` 对 `hc_busy` 在检会话豁免（`force_all` 除外）；④ `scan_all_servers_health(+progress_cb)` 可选回调（旧调用零变化）；⑤ 进程内 job 表 `_HC_SCAN_JOBS`：single-flight 幂等、TTL 10min GC、超 32 摘最旧、runner 异常兜底落 done（不留永挂 running 毒化幂等） |
| `edu-agent/app/mcp/router.py` | +`POST /api/mcp/health-scan-async`（**202**，同参重复 POST 幂等复用 job_id，message=accepted/already_running）；+`GET /api/mcp/health-scan/{job_id}`（未知/过期 → **404 + code "40450"**，经 main.py `HTTPException` dict-detail 通道）；旧 `POST /health-scan` 原样保留 + `Deprecation: true`/`Sunset: Mon, 12 Oct 2026 00:00:00 GMT`/`Link rel="successor-version"` 头（30 天兼容窗，removal 预计 2026-10-12） |
| `edu-agent/app/mcp/schemas.py` | `MCPSessionItem` +`hc`/`hc_busy` 观测字段（加性，默认 False，零破坏） |
| `edu-agent/tests/test_contract_mcp_health_async.py` | 14 用例（见 §4） |

关键设计决策（偏离风险备案）：
- **建池失败=直接定论不健康**（变更单 §2.3 流程），不二次 spawn——首轮实测发现 hung server（challenge_dup）会吃满调试会话宽限公式 `(connect+call)/1000+5s`≈42s 再叠加旧路径重试达 45s，故 ① 给 `session_create` 加 `timeout_s_override`（hc 口径 `connect_timeout/1000+2s` 钳制，调试路径默认值不变），② 建池握手失败按旧路径同等证据直接定论。修复后单台 7s（≈before 同服务器量级），全扫描 11.8s vs before 11.0s 同量级。
- **同 server 并发检查串行化**（`_HC_XCHG_LOCKS`）：单条 stdio pipe 上并发读会互偷帧（StreamReader 消费语义），必须串行；并发 ping 每条 ~2ms，串行无感。
- job 存储为进程内存（变更单 §2.2 备案：调试域不值得跨实例持久化，不引 Redis）。

## 3. 验收指标（GWT 实测）

### 3.1 单台 health P95（验收线 <500ms）✅

测法：真 HTTP（urllib）打 `POST /api/mcp/servers/1/health`，3 轮 × 15 样本/轮，取轮内 P95 后三取中位。

| | before（8000 旧代码） | after（8001 新代码） |
|---|---|---|
| 轮 P95（墙钟） | 281 / 149 / **179**(中位) ms | 137 / 44 / **48**(中位) ms |
| 轮 P95（服务端 latency_ms） | ~108 ms（spawn+init+ping 全套） | **2 ms**（池内单条 ping，spawn/initialize 归零） |
| 全部 ok | 45/45 | 45/45 |

**P95：179ms → 48ms（墙钟 3.7×），服务端 108ms → 2ms（54×）**，远优于 500ms 验收线。注：before 实测远好于变更单 "~5s" 的批判口径（该口径为最坏超时上界；echodemo spawn 快），如实登记。

### 3.2 全量扫描总时长（对照，非硬验收线）

- before：`POST /health-scan` 同步 **10.97s**（15 台，12 ok / 3 err）
- after（异步 job `elapsed_ms`）：**11.77s**（15 台，12 ok / 3 err，结论逐台一致，无误报）——串行后台化，同量级、不占请求（变更单 §⑤-4 口径）

### 3.3 扫描期间 50 并发 GET 轮询 ✅（test_05）

job running 期间 50 线程并发 GET：**50/50 全 200、壳 code=0、零 500**；延迟 min=245ms / p50=453ms / p95=580ms / max=583ms（均在 2s 线内；大头为客户端 50 线程 GIL 争用，服务端 job 查询为纯内存快照 µs 级）。不排队、无超时交叉。

### 3.4 并发健康检查互不干扰 ✅（进程内 + live 双层）

- 进程内（`TestHcPoolPolicy`）：同 server 8 路并发 ping 实测**最大交换并发=1**（串行化生效）；hc_busy 会话对 GC 豁免、空闲后照常回收；池通道故障（会话僵死）→ 摘注册表回退旧路径，**不产生假阴性**。
- live（test_06）：10 并发 `POST /servers/1/health` 全 200 / 全 `ok:true` / server_id 零串扰 + 2 并发 id=6 结果独立。
- 池复用直接证据：`GET /sessions` 出现 11 条 `hc=true` 会话（每 stdio server 恰 1 条，single-flight 建池），server 1 会话累计 **76 次 ping**、`latency_ms=2`；`DELETE` 杀会话后下次检查 100ms 自动重建入池。

### 3.5 pytest 结果

```
cd edu-agent && TEST_BASE=http://127.0.0.1:8001 .venv/Scripts/python.exe -m pytest tests/test_contract_mcp_health_async.py -q -s
14 passed in 36.20s
```
- 进程内 7 用例（零外部依赖，无后端亦可跑）：job 未知→None / single-flight 同 job_id+扫描引擎仅起 1 次 / running→done result 同构 / TTL 过期→摘除 / runner 异常兜底落 done / GC 豁免 hc_busy / 同 server 串行 / 池故障回退。
- live 7 用例（真实后端，conftest 不可达自动 skip）：202 壳+hs- 前缀 / 并发幂等同 job_id / 轮询 running→done+result 与 `MCPHealthScanResp` 同构+scanned==scanned_total / 未知 job 404+"40450" / 50 并发轮询 / 并发单台互不干扰+hc 会话存在 / 旧同步端点兼容+Deprecation 头。
- MCP 相关存量回归：`test_contract_task95.py + test_task33_mcp_desc_review.py + test_contract_all_routers.py` → **40 passed**（加性改动零破坏）。

### 3.6 鉴权（继承 router 级 ADMIN guard，实测）

无 token：202 端点 401 / GET 端点 401；student token：**403**（与 `/api/mcp` 全域一致）。

## 4. 批判承接核对

| 批判条目 | 承接 |
|---|---|
| C18（MCP spec：stdio 应长连复用，非一次性 spawn） | 本任务主对象：健康检查 ping-only，spawn 归零（3.4 池证据） |
| 变更单 §1.3 前端 120s 超时迁就 | 后端根因已除（202 即返+轮询）；admin-mcp.html 前端迁移**不在本单范围**（edu-api.js/fe-html 冻结只修不增，属后续前端批），兼容窗内旧页面零破坏继续可用 |
| Eng finding1（GC 竞争） | hc 专用注册表与调试会话隔离 + hc_busy 豁免 + 池化锁锁序单向 |

## 5. 三视角自检

- **契约视角**：`contracts/reshape-b.json` 逐字段核对（202/job_id 幂等/40450/兼容窗）零偏离；result 复用 `MCPHealthScanResp` 同构（test_03 断言）；错误码走字符串 "40450"（与 error_codes.py 字符串码口径一致；`STATUS_TO_CODE` 404 兜底 "40400" 仅在未带 dict-detail 时触发，本端点显式携带 40450）。
- **破坏面视角**：改动全加性——`session_create` 新参有默认值、`scan_all_servers_health` 新参可空、旧同步端点行为+schema 未动（test_07 回归）、调试会话路径未动（task95/33/all_routers 40 passed）；对 DB 零直写（验收全程仅走 API；`write_server_health` 为应用自身既有写路径，行为未改）。
- **运维视角**：回滚三级（§④ 变更单）：①前端单点切回旧端点（兼容窗内可用）→②`MCP_HC_USE_POOL=False` 关池化（代码保留）→③ revert 单 commit；job 纯内存，无 DB schema 变更；**8000 生产实例需按发布窗口重启载入新代码**（本任务未动在跑服务，验收走 8001 临时实例，已关闭）。

## 6. 遗留与移交

1. admin-mcp.html 按钮切 `-async`+轮询、`EAPI.TIMEOUT_MS` 回 15s——待前端批（兼容窗 30 天内完成即可）。
2. 扫描内部仍串行（变更单明确并行化不在本单范围，stretch 项）。
3. 8000 实例重启后建议复跑：`TEST_BASE=http://127.0.0.1:8000 .venv/Scripts/python.exe -m pytest tests/test_contract_mcp_health_async.py -q`。
4. `MCP_SCAN_JOB_NOT_FOUND=40450` 未登记进 `error_codes.py` 值域表——为守"契约冻结禁改"边界，码值以冻结契约为准在端点处显式实现；值域表登记建议随 T19-3（50301）变更单批次的 error_codes 增补一并处理。
