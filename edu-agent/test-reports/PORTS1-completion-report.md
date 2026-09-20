# W-NEXT-PORTS-001 完成报告 — 端口迁移 8000→9988 / 3000→3322

- 任务：W-NEXT-PORTS-001（C-01 编排者逐断言独立实证验收）
- 用户裁定（2026-09-20）：后端 **8000→9988**，前端 **3000→3322**；交付一键启动脚本；同步 AGENTS.md 启动命令
- 代码 commit：**`f26e8a5c592acd9327e0ec6c229d44e1d65b7d25`**（分支 feature/opt-waves，11 文件 +215/−70）
- 本报告 commit：见 `git log` 中本文件提交
- 执行时间：2026-09-20 11:17 ~ 12:05

---

## 1. 逐文件 diff 摘要（commit f26e8a5）

| # | 文件 | 改动摘要 |
|---|---|---|
| 1 | `edu-agent/app/config.py:43` | `PORT: int = 8000` → `9988`（1 行） |
| 2 | `edu-agent/.env` | 追加 `CORS_ORIGINS=http://127.0.0.1:3322,http://localhost:3322`（LC_ALL=C sed 追加，96→97 行仅增一行；该文件非 git 跟踪、含历史乱码字节，未动其他行） |
| 3 | `edu-frontend/public/edu-api.js` | 首行注释 8000→9988；第 8 行级联描述 `:3000→:8000`→`:3322→:9988`、默认 `127.0.0.1:8000`→`9988`；`DEFAULT_BASE`→9988；级联实现 `/:3000$/`→`/:3322$/`、`.replace(":3000",":8000")`→`:3322`/`:9988`（残留 3000 仅 toast 计时器 3000ms/z-index，非端口） |
| 4 | `edu-frontend/src/lib/api-client.ts:81` | 默认 API 基址 `"http://127.0.0.1:8000"`→`9988`（真实 baseURL 定义点；`NEXT_PUBLIC_API_BASE_URL`/`API_BASE_URL` env 覆盖链不变） |
| 5 | `edu-frontend/src/lib/api/admin.ts:5` | 注释 `baseURL=http://127.0.0.1:8000`→`9988` |
| 6 | `edu-frontend/.env.local`（新，git-ignored） | `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:9988`。**注**：任务书写 `NEXT_PUBLIC_API_BASE`，实读代码（api-client.ts:80）变量名为 `NEXT_PUBLIC_API_BASE_URL`，按真实变量名写入否则是死配置 |
| 7 | `edu-agent/scripts/check-demo.mjs` | 顶部新增 `BACKEND_PORT = parseInt(process.env.BACKEND_PORT \|\| "9988")` 与 FRONTEND_PORT 机制对齐；`BACKEND` 改模板派生；`--frontend-port` CLI 默认 3000→**3322**；④检查名/FIX.backend/FIX⑥/FIX⑬/⑯名称全部 BACKEND_PORT 模板化；`process.env.CHECK_DEMO_BACKEND = BACKEND` 写回传导给子探针（⑩ febe_contract_check、⑫ hitl_realness_probe 均读此 env）；⑬ mcp_tristate_probe 以 argv 显传 BACKEND；残留 8000 仅为 watchdog_8000.py 文件名、SOCKET/DOCKER 超时常量（3000/8000ms 非端口）与历史注释 |
| 8 | `edu-agent/scripts/eval/febe_contract_check.py:53-58` | `BACKEND`/`ALLOWED_PORT` 由写死 8000 改为 `CHECK_DEMO_BACKEND` env 派生（默认 9988）；SSRF 守卫语义不变（仍强制 127.0.0.1 loopback + 锁定所配单端口）。⑩ 与 ⑱（febe_health_gate_probe 复用本模块）一并修复 |
| 9 | `edu-agent/scripts/watchdog_8000.py` | `PORT = 9988`（docstring 首行注明「端口 2026-09-20 起 9988，文件名不改」）；`RESTART_OK` 日志与 argparse 描述随 PORT 模板化；历史取证叙述保留 |
| 10 | `AGENTS.md` | 架构三条（前端 3322/后端 9988/api-client 默认 9988+CORS 3322→9988）+ 启动命令两处 `--port 9988`/`-p 3322` + 端口变更日期注记 + 一键脚本指引 |
| 11 | `deploy/README.md` | 全部端口提及同步（8000→9988、3000→3322，watchdog_8000.py 文件名保护不改）；顶部加端口变更注记 + deploy.mjs 默认仍 8000/3000 的警示 |
| 12 | `start-eduagent.cmd`（新，仓库根，100 行） | 纯 ASCII + CRLF；①探 VM 192.168.85.101:19530（PS TcpClient 4s 超时，不通→打印「请先启动 VMware 虚拟机 CentOS 7 64 位」并 pause）②`docker start prisma-ai-redis-container-1 2>nul` ③后端 9988 判重拉起（`start /MIN /D` + `>> logs\uvicorn_9988.log`）④前端 3322 判重拉起（`NEXT_PROD_DIST_DIR=.next-prod`，缺 BUILD_ID 报错退出）⑤等 20s 后轮询探活（后端最长 150s，因 BGE-M3/CUDA 冷启动实测 >60s）打印 [OK]/[FAIL] 清单 ⑥末尾打印「体检：cd edu-agent 后执行 node scripts\check-demo.mjs」 |
| 13 | `stop-eduagent.cmd`（新，仓库根，26 行） | 按监听端口杀 9988/3322（netstat→taskkill /F /T），杀后回显残留 |

### 锁与红线执行
- `edu-agent/scripts/eval/ports1.lock`：任务开始时创建，**commit 前已删除**（不在提交中）
- 未触碰：`contracts/**`（迁移后 grep 8000/:3000 = 0 命中，本就干净）、retriever、`tests/` 断言（残留只登记，见 §5）

---

## 2. check-demo 新端口全绿输出（默认即 9988/3322，exit 0）

命令：`cd edu-agent && node scripts/check-demo.mjs`（2026-09-20 11:57~12:00，耗时 195.8s）

```
[PASS] ①. Milvus 连通 192.168.85.101:19530 (5ms)
[PASS] ②. Redis(按 .env REDIS_PORT=6377 反查容器 docker exec redis-cli ping) (697ms)  PONG(容器 prisma-ai-redis-container-1)
[PASS] ③. MongoDB 连通 192.168.85.101:27017 (1ms)
[PASS] ④. 后端 9988 /health (70ms)  status=ok v0.3.0
[PASS] ⑤. 前端 3322 /login-register.html(+生产形态判别) (29ms)  生产 build 形态(_buildManifest dev 探针 404)
[PASS] ⑥. 登录链路 login×2 + /api/auth/me×2 (1051ms)  adm02test(role=admin,user_id=100003) + user000001(role=student,user_id=1)
[WARN] ⑧. advisory: DEBUG 虚拟管理员探测（双探点,两级判据） —— 开发态已知后门，不阻断（教训 6，.env DEBUG=true）
[PASS] ⑨. 抽验页 200 /admin-users-refine-proto.html(C5-D2) (7ms)
[WARN] ⑩. 契约对账门 febe_contract_check.py —— 待接 72/未冻结仅后端 0（WARN，不阻断，治理 backlog 与迁移前同口径）
[PASS] ⑪. VEC-LOCK embed 一致性(edu_knowledge 元数据) (2240ms)  3388 行 model=bge-m3@26159e7a 混写=无 => PASS
[PASS] ⑬. MCP 三态门（能力对账+内置落审计+脱敏） (1385ms)  审计checked=17 内置落库✔ 脱敏✔
[PASS] ⑫. HITL 真实性(confirm 续流不再 42200) (12353ms)  模型未触发 knowledge_import,跳过(单测已覆盖)
[PASS] ⑭. 内部可见性(student 0 内部命中 / admin >0) (16769ms)  student=0 admin=24（5 query 全过）
[PASS] ⑮. Redis 部署对账(.env REDIS_PORT vs docker 宿主端口) (520ms)  .env=6377 docker=6377
[PASS] ⑯. 9988 lifecycle 健壮性(start+stop×5,无 CancelledError traceback) (56245ms)  5 轮 start 5280ms / stop 4930ms / 0 traceback / 0 CancelledError
[PASS] ⑰. MCP 跨权限门对账 (332ms)  checked=17 5行✔ chat链✔ JSON✔ AST真接4/5
[PASS] ⑱. febe root path 闭环(febe_contract_check --quiet unfrozen_only=0) (1199ms)  unfrozen_only=0 断点=0 在用未冻结=0
[PASS] ⑲. VEC-LOCK 守门(veclock_verify.py 12 维 + dim0 backend=bge_m3) (99360ms)  12/12 PASS + dim0 backend=bge_m3（锁定）
[PASS] ⑳. OTLP 链路健康(endpoint 解析 + 探活 + SSRF 守门) (531ms)  state=disabled
[WARN] ㉒. object_key 复用历史审计 (2088ms) —— 历史覆盖无法回填，软告警（迁移前既有）
汇总: 绿 21/21,WARN ⑧、⑩、㉒ —— 演示环境就绪 (检查耗时 195797ms)
EXIT=0
```

三个 WARN 均为迁移前既有口径（⑧ 开发态 DEBUG 后门告警、⑩ 待接 72 治理 backlog、㉒ MinIO 历史 key 复用），非本次迁移引入。

### 过程红项修复记录（第一轮 check-demo）
首轮（与 pytest 并发跑）⑩⑫⑯ 红：⑩⑫ 根因=子探针写死 8000（后端已在 9988）→ 按 §1#7/#8 接线修复；⑯ 根因=并发资源竞争（独立复跑 5 轮 start 5.3s/stop 4.8s 全过 PASS），非迁移回归。修复后干净重跑 21/21 绿。

---

## 3. curl 核心回归 + CORS 证据（真实 HTTP 独立实证）

### 3.1 核心 API（全部打 127.0.0.1:9988）
| 断言 | 证据 |
|---|---|
| health | `GET /health` → `{"status":"ok","app":"EduAgent","version":"0.3.0"}` |
| 登录×2 admin | `POST /api/auth/login` {adm02test/Test@123456} → `{"code":0,...,"access_token":"eyJ...role":"admin"...}` |
| 登录×2 student | 同上 {user000001/Test@123456} → `code:0` + student token |
| series | `GET /api/series`（student Bearer）→ `{"code":0,"data":{"total":2628,"page":1,"page_size":20,...}}`；旧路径 `/api/curriculum/series` 308→`/api/series` 重定向链完好 |
| kg path | `GET /api/kg/course/1/path?from=1.1&to=1.3` → `{"code":"40462","message":"知识点不存在：1.1"}`（路由/参数校验/业务查库全链路活着；40462 为正常业务响应） |

### 3.2 CORS（3322 源，9988 后端）
```
A. OPTIONS /api/auth/login  -H "Origin: http://localhost:3322"（预检）
   → HTTP/1.1 200 OK
   → access-control-allow-origin: http://localhost:3322
   → access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
   → access-control-allow-headers: content-type

B. GET /api/series  -H "Origin: http://127.0.0.1:3322"
   → HTTP/1.1 200 OK
   → access-control-allow-origin: http://127.0.0.1:3322
```
双源均被 .env `CORS_ORIGINS` 显式放行，预检通过，无拒。

### 3.3 旧源放行定性（非回归）
`Origin: http://127.0.0.1:3000` 仍被回显放行——根因 `app/main.py:_cors_origins()` 在 `DEBUG=true` 时返回 `["*"]`（开发态通配，check-demo ⑧ 已 WARN 此态）；生产态（DEBUG=false）走 `.env CORS_ORIGINS`（3322 双源）优先于 `main.py:353` 的 3000 硬编码回退（该回退仅 CORS_ORIGINS 为空时触达，见 §5 残留 R4）。

---

## 4. 看门狗与端口腾退

| 断言 | 证据 |
|---|---|
| 旧任务终止 | `schtasks /End /TN EduAgent-Watchdog` → 成功；`watchdog_8000.py --stop` → pid 12724 已死（/End 先杀），pid 文件已清 |
| 重注册 | `install_watchdog_task.ps1 -Force` → 任务重建（Boot+5min 触发，动作=watchdog_8000.py loop） |
| 新看门狗探 9988 | `schtasks /Run` 后事件日志 `[11:35:27] WATCHDOG_START pid=34780`；`watchdog_8000.py --once` → **`health=OK detail=ok listener_pid=13392`**（HEALTH_URL=f"http://127.0.0.1:{PORT}/health"，PORT=9988） |
| 端口腾退 | 迁移验证完成后 8000（pid 17972）/3000（pid 8220）已 taskkill；终态 netstat 仅 `127.0.0.1:9988 LISTENING` + `0.0.0.0:3322 LISTENING`，8000/3000 无监听 |

---

## 5. 残留 8000/3000 清单（只登记不修改——红线）

| # | 位置 | 性质 | 影响 |
|---|---|---|---|
| R1 | `edu-agent/tests/`：41 个 .py 含 "8000"，其中 23 个使用 live `127.0.0.1:8000`（conftest `_LIVE_HOSTS=[(127.0.0.1,8000),(8000/8001/8003)]`、test_contract_* 系列等） | live_backend 标记探 8000 | 迁移后这些 live 集成测试 **skip 而非 fail**（覆盖静默流失，需后续把 conftest 探测口加 9988）；8010/8011 自起实例类不受影响 |
| R2 | `edu-agent/scripts/deploy/deploy.mjs`：`BACKEND_PORT=8000` const（无 CLI 覆盖）+ `--frontend-port` 默认 3000 | **活跃部署路径**（P0 残留） | 迁移后若跑 `deploy.mjs start` 会在 8000 起后端 → 端口回退陷阱；已在 deploy/README 顶部警示，正路=仓库根 start-eduagent.cmd |
| R3 | `edu-agent/.env.example`：`PORT=8000` + 3000 CORS 注释 | 配置模板陈旧 | 新机照抄模板会让后端回 8000（P1，需模板同步） |
| R4 | `edu-agent/app/main.py:353`：生产 CORS 回退硬编码 localhost:3000/127.0.0.1:3000 | 兜底分支 | 仅 CORS_ORIGINS 为空时触达；当前 .env 已显式 3322 双源，不生效 |
| R5 | `edu-agent/app/config.py:38` 注释「生产 → http://localhost:3000」 | 注释陈旧 | 无行为影响 |
| R6 | `edu-agent/scripts/_lifecycle_real_verify.py`（check-demo ⑯ 探针）：自起 uvicorn `--port 8000` ×5 | 自包含实例 | 8000 已腾退故当前正常；若未来有服务占 8000 则 ⑯ 误红 |
| R7 | `edu-agent/scripts/` 下 ~20 个历史一次性验收脚本（verify_pages_*.mjs、_smoke_*、probe_one.mjs、hitl/chat_delete 等硬编码 8000） | 惰性历史工件 | 不在运行面，无影响 |
| R8 | `edu-agent/scripts/deploy/install_watchdog_task.ps1`：任务 XML Description 文字 "8000 uvicorn watchdog" | 纯文案 | 实际行为由 watchdog_8000.py PORT=9988 决定（§4 已实证） |
| R9 | 前端：`chat.test.ts:31`（vitest mock 值 8000）、`e2e/*.spec.ts`（Playwright，AGENTS.md 教训 2 已禁用） | 测试断言/禁用域 | 按「tests 端口语义只登记不修改」红线登记；mock 值无运行影响 |
| R10 | 仓库根 `run_regression.ps1`、`scan_next.py` 等历史运维脚本含 8000/3000 | 惰性工件 | 无运行影响 |
| R11 | 看门狗文件名/pid/log 名保留 `watchdog_8000.*` | 任务书明示不改名 | 仅为名称，探活/拉起已是 9988 |

`contracts/` 目录：grep 8000/:3000 = **0 命中**，无需处理。

---

## 6. 一键启动/停止脚本实证记录

| 轮次 | 操作 | 结果 |
|---|---|---|
| 1 | 首版 UTF-8+chcp 65001 脚本 | **失败**：cmd 批处理解析器在 chcp 切码后按错位字节续读（'ORTS-001'/'ons' 等碎行）→ 复盘后重写为纯 ASCII+CRLF，中文消息改 PowerShell `[char]` 转义输出（消息渲染已单独验证：「请先启动 VMware 虚拟机 CentOS 7 64 位，再重新运行本脚本。」） |
| 2 | start（冷启动，服务全停） | 全流程 ①~⑥ 走通；曾因 Git-Bash PATH 里 GNU `timeout` 抢占 cmd 内建 + 静态 20s 不够后端 BGE-M3 预热（实测冷启动 30~90s）→ 改 `%SystemRoot%\System32\ping.exe` 计时（stdin 无关）+ 后端探活轮询（20s 首等后每 5s×30 次上限 150s）→ **backend/health HTTP 200 + frontend/login-register.html HTTP 200 双 [OK]** |
| 3 | stop | 9988（pid 18072）+ 3322（pid 16504）双杀，端口腾退复验通过 |
| 4 | start（再冷启动） | 判重跳过逻辑 + 轮询探活双 200，脚本幂等 |
| 5 | 服务已起再跑 start | ③④ 均 [SKIP]（判重生效），探活双 [OK] |

前端生产形态：改 edu-api.js/api-client.ts 后已重跑 `NEXT_PROD_DIST_DIR=.next-prod next build`，9988 已编入 static/server chunks（grep 实证，无 8000 残留）；3322 实际服务的 `/edu-api.js` 含 `DEFAULT_BASE="http://127.0.0.1:9988"` 与 `:3322→:9988` 级联（curl 实证）。

## 7. 回归测试

- `pytest tests/test_wnextcheckdemohard2_guards.py tests/test_check_demo_timeouts.py tests/test_wnextprobe1_probe_fixes.py` → **36 passed, 1 skipped**（首轮 1 红：盲测 harness 抽取 ⑯附注 try 块独立执行，我的 `${BACKEND_PORT}` 插值在抽取块外未定义 → ReferenceError 被 catch → printed=false；按红线不改测试，改回静态字面量 "9988"（原实现即静态 "8000" 风格）后复跑全绿）
- 终态：14 passed, 1 skipped（skip 为既有条件跳过）

---

## 8. P0 自批判（≥3）

1. **【范围越界-已论证】febe_contract_check.py 不在 8 项清单内却被改**。任务书「照单执行勿自行扩散」与验收项 9「check-demo 全绿」冲突：⑩/⑰⑱ 的子探针把后端写死 8000（含 SSRF 守卫 `ALLOWED_PORT=8000`），不改则全绿物理不可达。采取最小改法（env 派生 + 默认 9988，守卫仍 loopback-only），但**守卫的端口白名单从独立常量变为随配置派生**——防 SSRF 的「端口独立锁定」强度下降（host 仍强制 127.0.0.1 兜底）。若裁定不可接受，回滚方案：探针加 `--port` CLI 而非 env，或恢复写死并改 9988。
2. **【P0 残留-deploy.mjs 端口回退陷阱】**。deploy.mjs `BACKEND_PORT=8000` 无 CLI 覆盖，迁移后任何人跑 `deploy.mjs start` 会在 8000 复活一个后端（与 9988 双实例、数据面/看门狗错位）。红线禁碰未改，仅 README 警示 + 一键脚本引流。建议下一单补 `--backend-port` CLI + 默认 9988。
3. **【测试覆盖静默流失】**。tests/ 23 个 live 8000 语义文件 + conftest `_LIVE_HOSTS` 探 8000 → 迁移后 live 集成测试全部 **skip 不报错**，「全绿」表象下覆盖缩水且无告警。红线禁止改 tests（正确），但需明确登记为待办：conftest 探测口补 9988。
4. **【.env.example 模板陷阱】**。模板仍 `PORT=8000`：新机按 deploy/README §2 流程 `cp .env.example .env` 会直接把后端带回 8000（config.py 默认 9988 被 .env 覆盖）。属部署一致性 P1，未在本单清单，登记 R3。
5. **【一键脚本对任务书字面的两处偏离，均有因】**：(a) 「纯 ASCII」vs「打印✓/✗/中文提示」矛盾 → 文件保纯 ASCII，✓/✗ 用 [OK]/[FAIL]，中文经 PowerShell [char] 转义；(b) 「等 20s 逐项探活」→ 后端冷启动实测 >60s，静态 20s 必假红，扩为 20s 首等+150s 轮询。首轮 UTF-8+chcp 版被 cmd 解析器撕裂是本次唯一返工，教训：批处理文件必须纯 ASCII+CRLF，任何非 ASCII 输出走子进程转义。
6. **【⑯ 首轮红的误判风险】**。首轮 ⑯ 红（shutdown 计时超限）恰与并发 pytest 同窗，独立复跑 5/5 PASS——若不独立复跑即归因「迁移破坏 lifecycle」会误报；反之若不深查直接放过，也可能漏真缺陷。取证路径（逐轮日志 0 traceback + 独立复跑计时）已留档。

## 9. 资产消费证据（编排者资产 → 实际使用）

| 资产 | 消费方式 |
|---|---|
| 逐文件改动清单（8 项） | 逐项照单执行，触点/行号全部命中（config.py:43、edu-api.js 8/24 行、watchdog:45、admin.ts:5 等与侦察一致，无自行扩散文件——febe_contract_check.py 越界已 §8.1 论证） |
| AGENTS.md 启动命令/架构记忆 | 后端启动命令式（uvicorn app.main:app）、前端 next\dist\bin\next 形态、`NEXT_PROD_DIST_DIR=.next-prod` 构建纪律、改静态页必须重 build——全部沿用 |
| AGENTS.md 测试账号 | adm02test/user000001 + Test@123456 用于 curl 登录×2 与 check-demo ⑥（role=admin/user_id=100003、role=student/user_id=1） |
| AGENTS.md 教训 2（禁 Playwright） | 全程 curl/requests/pytest 实证，未启浏览器 |
| AGENTS.md 教训 11 / deploy/README §1.1 | Redis 端口反查口径（6377→容器 prisma-ai-redis-container-1）在 check-demo ②⑮ 与 start 脚本 ② 中复用 |
| check-demo FIX 处置指引 | ⑯ 红时按 FIX 走 `_lifecycle_real_verify.py 5` 复跑定位为资源竞争 |
| install_watchdog_task.ps1（OPS-001 资产） | 按原样 `-Force` 重注册，其「--once 不拉起」设计差异声明被尊重（任务动作用 loop 模式） |
| deploy/README 端口表/巡检表 | README 同步时逐处对齐（§1 架构图、§4 巡检表、§6 参数表、§8 curl 速查） |

## 10. 终态快照（2026-09-20 12:05）

- 后端：`127.0.0.1:9988` LISTENING（uvicorn，pid 13392，日志 `edu-agent/logs/uvicorn_9988.log`）
- 前端：`0.0.0.0:3322` LISTENING（next start 生产形态 .next-prod，pid 18500，日志 `edu-frontend/next-3322.log`）
- 看门狗：EduAgent-Watchdog 计划任务「正在运行」，探 9988（--once health=OK）
- 8000/3000：无监听（已腾退）
- check-demo：21/21 绿，EXIT=0
