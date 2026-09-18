# W-NEXT-CHECKDEMO-HARD-002 完工报告（接手执行 agent）

> 任务 ID：W-NEXT-CHECKDEMO-HARD-002（check-demo 硬化第二批：PROBE-001 三条 P0 + DEBUG-DOC-001 P0-3）
> 子 agent：W-NEXT-CHECKDEMO-HARD-002（接手执行，前两任 API 中断留 WIP）
> 派单：C-01 orchestrator 主会话（逐断言独立实证验收）
> 完工日期：2026-09-18
> 代码 HEAD commit：**`ee89db9`**（fix(check)/W-NEXT-CHECKDEMO-HARD-002 接手收口:PROBE-001 P0-4a fail-drill 6380 边界单测+盲测态补全）
> 报告 commit：紧随 `ee89db9` 的独立报告提交
> 分支：feature/opt-waves

---

## 一、历任半成品处置（必读）

| 提交 | 内容 | 接手处置 |
| --- | --- | --- |
| `0be74b2` | 前任① API 中断留痕：check-demo.mjs（②⑧⑯ 加固，+117 行）+ hitl_realness_probe.py（⑫ 边界态，+100 行） | **采纳不重写**。逐行审查 diff 后确认实现与批判原文对齐（见 §三），以真实环境复跑实证 |
| `43e0480` | 前任②（TEST-BASE 外部代理）崩溃留痕：新增 `tests/test_wnextcheckdemohard2_guards.py`（435 行 13 例）+ `tests/_wnextcheckdemohard2_blind.mjs`（282 行 15 态），同提交另含 15 个 tests/ 其他文件（红线禁碰区，本批未动） | **采纳**。基线复跑：guards 13/13 PASS、blind 15/15 BLIND-ALL-OK；随后仅在该两文件内补缺口（+97 行） |
| `ee89db9` | **本提交（接手收口）**：PROBE-001 P0-4a 缺口补全——drill 假端口 6380 边界 guards 2 例 + blind 2 态 | 新增 |

> 工作区核对：`git diff 43e0480 HEAD -- <四文件>` 接手时为空（WIP 即工作区态）；本提交只动 `tests/test_wnextcheckdemohard2_guards.py` 与 `tests/_wnextcheckdemohard2_blind.mjs`，未触碰 deploy.mjs / edu-frontend/** / app/** / tests/ 其他文件。

## 二、批判承接核对（5/5 闭环，无遗留承接项）

批判资产消费来源（原文引用见 §六）：

| # | 批判条目 | 承接实现 | 实证 |
| --- | --- | --- | --- |
| 1 | PROBE-001 **P0-1**：detectRedisContainer 只走 publish/expose filter，自定义 network 漂移 0 匹配盲区 | 第 3 试 `docker ps -a --format {{.Names}}\t{{.Ports}}\t{{.State}}` 全表 ports 解析兜底，抽纯函数 `parseDockerPortTableMatches`（`[HARD2:FNSPLIT-END]` 锚点） | blind C1（filter 双 0→全表救回）+ guards `test_js_full_table_rescues_filter_zero_match`；真机 drill 6380 干净报错（§四.2） |
| 2 | PROBE-001 **P0-3**：`_stream_events` 只兜 HTTPError/URLError，ProtocolError/RemoteDisconnected/socket.timeout 穿透 | urlopen+读流两段按「timeout→HTTPException→ConnectionError/OSError→兜底」序捕获，转伪事件 `stream_timeout`/`stream_protocol_error`/`stream_connection_error`/`stream_read_error`，探针永不崩；main() 回显 `stream_boundary_events` 进契约 JSON | guards 9 类注入异常全转边界态（`test_stream_events_never_raises_on_injected_errors`）；except 排序静态锁（RemoteDisconnected 双继承、socket.timeout 先于 OSError） |
| 3 | PROBE-001 **P0-4**：回归覆盖三缺口——(a) 6380 边界无单测 (b) 多容器并存确定性 (c) ⑫ 细分 | (b) 命中列表 running 优先+组内表序稳定，5 连跑全等；(a) **接手补**：6380 两态单测+盲测（§四.3）；(c) 9 注入态已锁 | guards 15/15、blind 17/17 |
| 4 | DEBUG-DOC-001 **P0-3a**：⑧ 只测 /api/users/me，未覆盖 /api/admin/* DEBUG 旁路 | 双探点：新增 /api/admin/users 无 token 探测，**分支 0**（管理端护栏失效）任何环境（含 DEBUG=true）直接 FAIL 不吃 WARN 降级；文案同步「双探点」 | blind A 组 10 态（S01/S01b 管理端破→直红等）；真后端活体不变量：curl 无 token `/api/users/me`=200、`/api/admin/users`=401 `{"code":"40101","message":"缺少 Authorization 请求头"}`；guards `test_real_backend_admin_users_not_open_without_token` |
| 5 | DEBUG-DOC-001 **P0-3b**：⑯ 不感知 .env 改动，改 .env 不重启 ⑧ 可能误判 | ⑯ 输出后追加附注行（带 .env 最近修改时间锚点，明示「重启后端后重跑」），不做重启自动化（避免与 ⑯ 五轮 start/stop 竞态） | blind B 组 2 态（.env 在→打印含 mtime / .env 缺→静默跳过）；真机 run 输出实测行（§四.1） |

**承接结论：5/5 闭环，无承接项遗留。** 前任未覆盖的 P0-4(a) 由本提交补齐。

## 三、每改动 ≥2 态盲测（逐改动清单）

### 3.1 ② detectRedisContainer 全表兜底（前任采纳）
- blind 态 C1 `filter双0_全表救回running-redis` PASS、C2 `全0_干净报错含端口` PASS、C3 `同宿主端口并存_5连跑全等_running优先` PASS
- 真机两态：normal（.env REDIS_PORT=6377）→ `[PASS] ②... PONG(容器 prisma-ai-redis-container-1)`；drill（6380 假端口，全表无映射）→ FAIL 干净报错（§四.2）

### 3.2 ⑫ _stream_events 边界态（前任采纳）
- guards 注入 9 类异常（IncompleteRead/RemoteDisconnected/BadStatusLine/socket.timeout/ConnectionResetError/RuntimeError × urlopen/读流两段）全转对应伪事件、已收集事件保留、函数不 raise —— `9 例全输出` PASS
- except 排序静态锁 PASS（HTTPException 先于 ConnectionError/OSError；socket.timeout 先于 OSError）

### 3.3 ⑧ 双探点（前任采纳）
- blind A 组 10 态全 PASS：S01 管理端护栏失效任意环境直红 / S01b users_me 被拒仍直红 / S02 双拒+DEBUG=true 开关仍开 / S03 双拒 DEBUG=false 生产态正确 / S04 开发态后门 WARN / S05 ENV_NAME 非 local 直红 / S06 prod-gate 升级 FAIL / S07 DEBUG=false 真后门直红 / S08 后端不可达跳过 / S09 二探点网络异常不另立红项
- 真后端活体不变量 PASS（8000 在线，无 token /api/admin/users 不可达）

### 3.4 ⑯ .env 变更感知附注（前任采纳）
- blind B 组 2 态全 PASS（env 存在→附注打印含「最近修改」mtime；env 缺失→静默跳过）
- 真机 run 实测输出：`[⑯ 附注] .env 变更感知:后端 settings 仅启动时加载一次,⑧ 的 DEBUG/ENV_NAME 判据直读 .env(最近修改 2026/9/18 22:51:14)——若改过 .env 未重启 8000,⑧ 可能误判,请重启后端后重跑本检查单`

### 3.5 drill 假端口 6380 边界两态（**本提交新增，P0-4a**）
- blind 新增 2 态 PASS：
  - `drill假端口6380_全表无映射_干净报错3连跑全等_不跨端口误判`（detect×3 全等 `THREW: 未找到映射宿主端口 6380 的 Redis 容器(检查 docker ps 与端口映射)`，parse6380=[] 无 6377 泄漏）
  - `drill假端口6380_停机容器占口_具名诊断3连跑全等_不误判6377`（exited 容器占用 6380 → 具名命中 `squat-exited-redis`，P0-1 语义「诊断落到具体容器」）
- guards 新增 2 例 PASS：`test_js_fail_drill_6380_boundary_clean_and_deterministic`、`test_js_6380_squat_exited_container_named_diagnosis`
- 开发过程修正两处测试自身缺陷（均盲测抓出后重跑）：嵌套模板串 `\n` 未转义致生成文件 SyntaxError；生成代码段漏 6380 计算（runs=undefined）。无效取证作废重跑，未混入结论

## 四、真实环境独立实证（C-01）

### 4.1 终态 normal（EXIT=0）

```
汇总: 绿 21/21,WARN ⑧、⑩、㉒ —— 演示环境就绪 (检查耗时 173909ms)
```

- ⑧ WARN 详情含双探点语义：`[WARN 开发态虚拟管理员后门存在(DEBUG=true, ENV_NAME=缺省(=config.py 默认 local);无 token /api/users/me HTTP 200 可达;/api/admin/users 无 token 被 401 拒(admin Bearer 护栏在));两级判据:...]`
- ⑯ PASS：`5 轮 start 12ms / stop 6ms / 0 traceback / 0 CancelledError`
- ② PASS：`PONG(容器 prisma-ai-redis-container-1)`；⑤ 生产 build 形态；⑲ 12/12 PASS + dim0 backend=bge_m3

### 4.2 fail-drill（EXIT=1，失败路径验证）

```
汇总: 绿 16/21,红项 ①、②,WARN ⑧、⑩、㉒ —— 请按上方指引处置后重跑 (检查耗时 162944ms)
[FAIL] ①. Milvus 连通 127.0.0.1:19531
[FAIL] ②. Redis(按 .env REDIS_PORT=6380 反查容器 docker exec redis-cli ping)
       -> [未找到映射宿主端口 6380 的 Redis 容器(检查 docker ps 与端口映射)]
```

- ② 走新兜底路径后报错文案确定性保持（真 docker 全表无 6380 映射，兜底全空才报错）——PROBE-001 drill 语义未破坏
- ⚠️ ③ Mongo 127.0.0.1:27018 在本机 PASS：环境碰撞（本机 docker `prisma-ai-mongo-container-1` 恰好发布 `0.0.0.0:27018->27017`），非本批引入（③ drill 逻辑本批零改动），见自批判 P0-B

### 4.3 ⑯ 环境诊断记录（第一次 full run FAIL → 复跑 PASS）

- 第一次 full run：`绿 17/21,红项 ⑯`。诊断：`logs/lifecycle_real_2.log` 出现 `ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000)`——编排者常驻后端（PID 31484，22:51:59 起）占 127.0.0.1:8000，探针 5 轮中 4 轮日志 size=0（bind 失败瞬态竞态输 not-ready）→ gate FAIL
- 复跑探针直验：单轮 PASS（ready 15ms=借道外部后端 /health）→ 5 轮 5/5 PASS（`[LIFECYCLE] {"pass": true...gate: "PASS"}`）→ full check-demo ⑯ PASS
- 定性：环境瞬态竞态（常驻后端占用 + 探针 bind 冲突路径未定义语义），非本批代码回归；详见自批判 P0-A

### 4.4 单测终态

```
tests/test_wnextcheckdemohard2_guards.py  15 passed in 8.90s
node tests/_wnextcheckdemohard2_blind.mjs  盲测汇总: 17/17 绿  BLIND-ALL-OK
```

## 五、P0 自批判（4 条，≥3）

### P0-A：⑯ 探针 bind 冲突语义未定义，借道外部 /health 时「测的不是 lifecycle」（高危，环境级）
探针起 uvicorn 绑 127.0.0.1:8000；常驻后端在场时 bind 10048 失败，但 /health 轮询借外部后端即时 ready（0-15ms）、CTRL_BREAK 打在自己（已死）进程上、日志计数全 0 → gate PASS。即**占用态下 ⑯ 实际什么都没验**，且 ready 判定与「本进程 uvicorn 瞬死」存在竞态（本批实测：同环境一次 1/5 not-ready FAIL、一次 5/5 PASS）。`_lifecycle_real_verify.py` 不在本批文件归属内，未修。建议 W-NEXT-LIFECYCLE 承接：探针启动前 netstat 断言 8000 空口，被占用→ `env_blocked` WARN 而非带病竞态。

### P0-B：fail-drill ③ 假端口 27018 与真机 mongo 发布端口撞车（中危，环境耦合）
drill 假设 27018「必然失败」，本机 docker mongo 恰发布 0.0.0.0:27018→27017 → drill ③ PASS，三红少一红。本批未改 drill 语义（避免越权 + 基线冻结），但 drill 失败路径覆盖度因此打折。建议后续：假端口改用 IANA 保留段死端口，或 drill 前置 netstat 空口断言。

### P0-C：全表兜底正则不解析「端口段 publish」，filter 路径顺序依赖仍在（低危，残余盲区）
`parseDockerPortTableMatches` 只认 `host:port->` 单端口映射，`0.0.0.0:6370-6380->6370-6379/tcp` 形式的端口段发布不命中（redis 恰用端口段发布的场景极窄，但存在）；且第 1/2 试 filter 命中多容器时仍取 docker ps 表序首个，P0-4 的确定性保证只覆盖第 3 试全表路径。建议后续统一：filter 命中 >1 时也走全表解析重排。

### P0-D：`stream_read_error` 兜底把编程错误也吞成边界事件（低危，有意取舍）
⑫ 兜底 `except Exception` 将 TypeError 等代码缺陷也转为 `stream_read_error` 伪事件——「探针永不崩」与「缺陷可见性」冲突，当前取前者（回显进契约 JSON 可人工识别）。另 `boundary2` 未像首段一样排除字面 `stream` 事件名（当前后端事件集 start|retrieval|token|done|error 下无实际影响）。接受现状，登记语义。

## 六、资产消费证据

1. **PROBE-001 完工报告**（`test-reports/WNEXTPROBE1-completion-report.md` §4 P0 自批判，行 157-187）：
   - P0-1 原文：「detectRedisContainer() 只走 publish=<port> 与 expose=<port> 两个 docker filter，对自定义 network 别名 + 非默认 bridge 的容器仍可能 0 匹配」→ 本批第 3 试全表兜底承接
   - P0-3 原文：「SSE 流过程中的 urllib3.ProtocolError、http.client.RemoteDisconnected、socket.timeout 等仍会 raise」→ 本批四类伪事件承接
   - P0-4 原文：「未覆盖：detectRedisContainer 端口 6380 边界（fail-drill 路径已验证但无单测）；多 redis 容器多端口并存场景」→ (a)(b) 本批承接（(a) 由接手提交 ee89db9 补齐）
2. **DEBUG-DOC-001 完工报告**（`edu-agent/test-reports/WNEXTDEBUGDOC1-completion-report.md` §10 P0-3，行 142-151）：「当前 ⑧ 仅探测 /api/users/me，未覆盖 /api/admin/* 等其它 DEBUG 旁路」「⑯ …不感知 .env 改动…致 ⑧ 误判」→ 双探点分支 0 + ⑯ 附注行承接
3. **AGENTS.md 教训**：教训 6（DEBUG 虚拟管理员）、教训 2（禁 Playwright，验收用真实 HTTP+独立实证）、教训 8（真实契约优先——⑧ 分支 0 判据按 `app/middleware/auth_middleware.py` 实测 401 契约而非页面注释）
4. **编排者环境登记**：8000 七组件 ok（Redis 6377 修复）、3000 生产形态 200、基线 绿 21/21+WARN ⑧⑩㉒——本次 full run 复现一致

## 七、lock 与提交卫生

- lock：`scripts/eval/wnextcheckdemohard2.lock`（22:55:51 建，owner=W-NEXT-CHECKDEMO-HARD-002-takeover）→ commit 前 `rm`，`ls` 复核 **absent confirmed**；提交内容无此文件
- `ee89db9` 只 staged 两文件（显式 `git add` 路径，未 `git add -A`）；工作区他 agent 未跟踪文件（scripts/eval/_*.py 等）未触碰
- 红线复核：deploy.mjs / edu-frontend/** / app/** / tests/ 其他文件（含 43e0480 中 TEST-BASE 的 15 个文件）零改动

## 八、终态一句话

**check-demo 绿 21/21 + WARN ⑧⑩㉒（EXIT=0）复现达成；PROBE-001 P0-1/P0-3/P0-4 + DEBUG-DOC-001 P0-3 全部闭环并锁进单测（guards 15 例 / blind 17 态全绿）；fail-drill 失败路径 EXIT=1、①② 红文案确定性保持。**
