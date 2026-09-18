# W-NEXT-DEPLOY-HARD-001 完成报告（接手执行 + 编排者 C-01 独立实证）

> 任务：接手前任两次死亡（API 中断 + 宿主机崩溃）留下的半成品 `0f566ef`，消化
> W-NEXT-CHECKDEMO-PROD-001 P0-1/P0-4 与 W-NEXT-PRODUCTION-BUILD-001 P0-5，对
> `edu-agent/scripts/deploy/deploy.mjs` 完成端口参数化/部署环境门/可逆性子命令三线加固，
> 并按编排者要求做三态盲测独立实证。日期：2026-09-18。分支：feature/opt-waves。
>
> 本报告即 C-01 验收材料：commit hash、前任处置、三态盲测原始输出、往返恢复证据、P0 自批判、
> 批判承接核对、资产消费证据齐备。

---

## 0. 交付物与 commit

| 文件 | 归属 | 变更 |
|---|---|---|
| `edu-agent/scripts/deploy/deploy.mjs` | 本任务 | 基于前任 WIP 修复 4 处（见 §2），+8 行净增 |
| `deploy/README.md` | 本任务 | 前任已更新四条用法，本任务纠偏 2 处失真（见 §2.3） |
| `edu-agent/test-reports/WNEXTDEPLOYHARD1-completion-report.md` | 本任务 | 本报告 |

最终 commit：见 `git log` 本文件关联提交（W-NEXT-DEPLOY-HARD-001 收口提交，前任半成品 `0f566ef` 为其父链祖先）。
lock：`edu-agent/scripts/eval/wnextdeployhard1.lock` 沿用后于 commit 前删除。

## 1. 前任半成品处置（git show 0f566ef 审查结论）

**判定：复用为基线（不重写），审查发现 2 个实证级缺陷 + 2 个报告失真，全部修复。**

0f566ef（+235 行）已实现四项改造的代码层：① `--frontend-port`（默认 3000，start/stop/status/可逆子命令
全链路 + 透传 check-demo）；② `--prod-gate`（start 前跑 `deploy_env_gate.mjs`，exit!=0 中止不拉服务；
check-demo 断言段严格模式透传）；③ `stop-prod-and-restart-dev`；④ `status` 形态判别 + `[STATUS]` JSON。
结构、契约与上游资产签名核对全部正确（`deploy_env_gate.mjs [env路径]` exit 0/1；
`check-demo.mjs --frontend-port/--prod-gate`，WARN 不阻断 FAIL 才 exit 1），**但零实证**，且存在：

| # | 缺陷（0f566ef 原文） | 实证 | 修复 |
|---|---|---|---|
| F1 **P0** | 可逆子命令 ④ 的 next 入口写为 `FRONTEND_DIR/next/dist/bin/next`——该路径**不存在** | `ls edu-frontend/next/dist/bin/next` → No such file；活生产实例命令行实测 = `node node_modules/next/dist/bin/next start -p 3000` | 改为 `node_modules/next/dist/bin/next`（existsSync 守卫保留） |
| F2 P1 | stop-prod-and-restart-dev 在 taskkill 报成功后**立即** `portBusy` 探测——进程 teardown 有秒级窗口，盲测③首跑即误判「端口 3000 仍被占用——中止」exit 1（此时生产实例已被杀、dev 未起，环境半途悬挂） | 盲测③首跑输出（§3.5-a）；事后 netstat 复核 23760 已死、仅剩出站 TIME_WAIT | 杀后加有界等待：20×500ms 轮询端口释放，10s 未释放才中止 |
| F3 P1 | preflight Redis 探测硬编码 `edu-redis-standalone`——本机活容器已漂移（`prisma-ai-redis-container-1`，6377→6379），每次部署前置检查必假红且给错误处置指引 | `docker exec edu-redis-standalone redis-cli ping` → No such container；PONG 实际来自 prisma 容器 | 对齐 check-demo ②（W-NEXT-PROBE-001）同款端口反查：读 `.env REDIS_PORT`（回退 `REDIS_URL` 端口/6379）→ `docker ps --filter publish=<port>` 反查容器 → `docker exec redis-cli ping`；`stop --all` 提示同步去硬编码 |
| F4 P2 | `--env` 未与 `--prod-gate` 搭配时被静默忽略 | 代码走读 | 未搭配时显式 WARN 提示不生效 |

修复后 `node --check` 通过、无参用法 exit 0、非法端口 `--frontend-port notanum` exit 2（参数校验实证）。

### 1.1 README 纠偏（前任版本的两处失真）

- **回退路径失真**：前任写「反向（dev→生产）：`deploy.mjs start`（…约 5-10s 拉起）」，但 start 对已监听端口
  幂等跳过——dev 实例占着 3000 时单跑 start **切不回**生产形态。已改为盲测实证路径：先单清 3000 dev 实例
  （端口反查 taskkill）→ 再 `start --frontend-port 3000`（实测 ~4s 拉起 + check-demo 21/21）。
- **§1.1 防漂移段陈旧**：前任保留「check-demo ② 硬编码旧容器名待修」的过时建议（W-NEXT-PROBE-001 已修），
  已更新为两端口反查均已对齐的现状。

## 2. 三态盲测（独立实证，真实 HTTP/进程/端口，非 mock）

环境基线（测试前实测）：后端 8000 `{"status":"ok"}` PID 31484；前端 3000 生产形态（login=200、
`_buildManifest` dev 探针=404）PID 23760；3001 空闲；`.next-prod/BUILD_ID=K3LsKKGXPagAM6MLWHOFz`；
`.env` DEBUG=true（dev 形态，本机活环境口径）；Node v24.18.0。**3000 生产实例为活环境，全程按
「往返后恢复原生产形态」红线执行。**

### 2.1 盲测①：`start --frontend-port 3001` 全流程 — PASS

```
[ OK ] Redis 可达 — docker exec prisma-ai-redis-container-1 redis-cli ping = PONG(宿主端口 6377)   ← F3 修复生效
[WARN] 端口 8000 已有监听(PID 31484)——幂等跳过后端拉起                                          ← 后端零扰动
[ OK ] 前端生产产物已存在 .next-prod/BUILD_ID=K3LsKKGXPagAM6MLWHOFz(跳过 build)
[ OK ] 前端就绪 http://127.0.0.1:3001/login-register.html(5148ms)
=== ④ check-demo 断言(期望 9/9;--frontend-port 3001)===
[PASS] ⑤. 前端 3001 /login-register.html(+生产形态判别) (34ms)  生产 build 形态(_buildManifest dev 探针 404)   ← 端口透传实证
汇总: 绿 17/21,红项 ⑯,WARN ⑧、⑩、㉒ —— 请按上方指引处置后重跑 (检查耗时 216390ms)
EXIT=1
```

- 管线五段（门跳过提示→前置检查→后端幂等→前端 build+start 3001→check-demo 透传端口）全链路走通；
  ⑤ 实证 3001 为生产 build 形态（NEXT_PROD_DIST_DIR 机制成立）。
- exit 1 归因：红项仅 ⑯（8000 lifecycle 健壮性，独立子系统，与本任务改动无接触面）——**同一检查在随后两轮
  （②c 与恢复轮）均 5.4s PASS**，证明该红为偶发环境噪声而非端口改造回归；⑧ WARN 属 dev 后端预期（不阻断）。
- 清理：3001 按端口反查 taskkill /F /T（与 killPort 同机制），复核 3000/8000 PID 原样、3001 清零。

### 2.2 盲测②：`--prod-gate` 拦 DEBUG=true env — PASS（含门放行接线）

| 子测 | 命令 | 关键输出 | exit |
|---|---|---|---|
| ②a 真实 .env | `start --prod-gate` | `[DEPLOY_GATE] {"debug":true,"env_name":null,"decision":"deny_debug_true",…}` → `[FAIL] 部署环境门未通过(exit=1)——已中止部署,未拉起任何服务` | **2** |
| ②b 显式 --env | `start --prod-gate --env logs/_wngate_debug_true.env` | `[DEPLOY_GATE] {…,"decision":"deny_debug_true"…}` → 中止 | **2** |
| ②c 门放行接线 | `start --prod-gate --env logs/_wngate_debug_false.env --frontend-port 3001` | `[DEPLOY_GATE] {"debug":false,"env_name":"prod","decision":"allow"…}` → `部署环境门 PASS——继续部署` → 前端 3001 拉起 → check-demo 头部 `[prod-gate:⑧ WARN 升级 FAIL(部署门)]` → `[FAIL] ⑧ …WARN 已升级为 FAIL 阻断出包` | 1（预期严格行为） |

- ②a/②b 后端口复核：仅 3000/8000 原监听，3001 仍空闲，**无任何服务被拉起**（「不拉起任何服务」实证）。
- ②c 同时实证两个接线：gate PASS 分支不误杀部署（继续走完五段）；`--prod-gate` 透传后 ⑧ 从盲测①的
  WARN 升级为 FAIL（exit 1 为严格门正确行为——dev 后端运行时 + 部署门语义）。②c 后 3001 同法清理。
- 临时 env 文件（`logs/_wngate_debug_{true,false}.env`）均放 gitignored 的 `logs/`，**未触碰真实 `.env`**。

### 2.3 盲测③：stop-prod-and-restart-dev 往返 + 恢复原生产形态 — PASS

**③-a 往返首跑（F2 缺陷现场，如实登记）：**

```
[deploy] 停前前端 3000 形态: prod(_buildManifest dev 探针=404)      ← 停前形态如实记录（活生产实例）
[ OK ] 前端 端口 3000 PID 23760 已终止
[FAIL] 端口 3000 仍被占用——中止                                    ← F2：teardown 竞态误判
EXIT=1
```

**③-a 修复后重跑（完成生产→dev）：**

```
[deploy] 停前前端 3000 形态: down(fetch failed)                     ← 首跑已杀生产实例的如实快照
[ OK ] 端口 3000 已释放                                             ← F2 修复生效
[ OK ] 已删 dev 缓存 E:\…\edu-frontend\.next(生产产物 .next-prod 未动)
[deploy] next dev 拉起中(PID 30320,日志 logs/deploy-frontend-dev.log) …  ← F1 修复的真实入口
[ OK ] 前端 dev 就绪 http://127.0.0.1:3000/login-register.html 200(4353ms)
[ OK ] 形态复核: dev(_buildManifest dev 探针=200)——已从生产切回开发形态
EXIT=0
```

独立复核：login=200 + `_buildManifest`=200（dev 判据）；`.next-prod/BUILD_ID` 仍在（生产产物未动）；8000 ok。

**③-b 恢复原生产形态（回程）：**

```
回程① 单清 3000 dev 实例：taskkill /F /T（端口反查 PID 11008/23708）→ 3000 已无监听
回程② node scripts/deploy/deploy.mjs start --frontend-port 3000：
  [WARN] 端口 8000 已有监听(PID 31484)——幂等跳过后端拉起            ← 后端全程零重启
  [ OK ] 前端生产产物已存在 .next-prod/BUILD_ID=…(跳过 build)
  [ OK ] 前端就绪 http://127.0.0.1:3000/login-register.html(3729ms)
  汇总: 绿 21/21,WARN ⑧、⑩、㉒ —— 演示环境就绪 (检查耗时 177639ms)
  [ OK ] check-demo 9/9 全绿——演示环境就绪
EXIT=0
```

**恢复后终态复核（恢复证据）：**

```
TCP 0.0.0.0:3000  LISTENING  9092（命令行实证 = "node …next start -p 3000"）
TCP 127.0.0.1:8000 LISTENING 31484（与测试前完全相同——后端 0 次重启）
3000 login=200  buildManifest=404（404=生产判据）
{"status":"ok","app":"EduAgent","version":"0.3.0"}
logs/deploy.pids.json → {"frontend":{"pid":28124,"cmd":"next start -p 3000","form":"build+start(.next-prod)"}}
```

**status 子命令实证**（恢复后的生产实例上）：

```
[ OK ] 前端 3000 形态: prod(_buildManifest dev 探针=404) —— 生产 build 形态(_buildManifest dev 探针 404=生产判据)
[ OK ] 后端 8000 /health: ok
[STATUS] {"frontend_port":3000,"frontend_form":"prod","frontend_detail":"_buildManifest dev 探针=404","backend_health":"ok"}
[deploy] 透传执行 scripts/check-demo.mjs(status=check-demo 原样;--frontend-port 3000)…（透传段启动正常）
```

（status 透传段因验证管道 `head` 截断提前退出，形态判别段/JSON 行/透传启动均已取证；完整透传同口径
输出已由回程②的 check-demo 全量提供。截断后复核无孤儿 check-demo 进程残留。）

### 2.4 环境恢复结论

活环境完整还原：3000 = 生产 build 形态 200/404（`.next-prod` 同一 BUILD_ID，部署定义的生产形态）；
8000 = 原 PID 31484 全程未动（所有测试均走幂等跳过，后端 0 次重启）；3001 清零；`.next` dev 缓存由
next dev 重建属正常；`logs/deploy.pids.json` 记录与实际形态一致（记录值指向 spawn 包装层，见 S1）。

## 3. P0 自批判（5 条，含遗留登记）

1. **S1 recordPid 记 spawn 包装层 PID**：`startFrontend` 经 `cmd /c npx next start` 拉起，`pids.json` 记录的
   是 cmd 包装 PID（如 28124），真实监听 PID 是其孙进程（9092）——排障时记录与 netstat 对不上。清杀按端口
   反查不受影响（本任务盲测已实证），但记录语义失真属 taskC1 既有设计，本任务未改（改记录逻辑需拿到
  孙 PID，牵动 spawn 方式，超出本次范围）。**建议**：后续改 `recordPid` 时补记监听 PID。
2. **S2 stop 无「仅清前端」组合**：`stop` 固定连 8000 一起清，可逆往返的回程只能靠手动单清端口或接受后端
   重启——本任务用「端口反查 taskkill + start」实证了最短回程并写入 README，但**单命令回程仍缺失**
   （PRODUCTION-BUILD-001 P0-5 只要求 prod→dev 方向，此为超出交付面的遗留缺口）。**建议**：加
   `stop --keep-backend` 或 `start --replace-dev`。
3. **S3 startFrontend 幂等跳过不判形态**：端口被 dev 实例占用时 start 打印提示后仍以 exit 0 结束
   （check-demo ⑤ 对 dev 形态是 WARN）——用户可能误以为已处于生产形态。形态真相必须看 `status` 的
   `[STATUS]` JSON（本任务已实证该判别），但 start 侧不强制形态门是设计取舍：自动杀掉占用进程风险更大。
4. **S4 check-demo 21 项存在环境噪声**：盲测①中 ⑯ lifecycle 偶发红（35.4s FAIL），同日两轮复跑即 PASS
   （5.4s）——deploy 的断言段 exit code 会被这类噪声打成 1，验收读数必须逐项归因（本报告 §2.1 已归因），
   不能把「exit 1」一概当部署失败。⑯ 属 check-demo 子系统（红线禁碰），登记待其归属任务治理。
5. **S5 portBusy 只认「有监听」不认「是谁」**：若 3001 被非本项目进程占用，start 会把它当本项目前端幂等
   跳过（不校验进程身份）；盲测中 3001 均空闲未触发。**建议**：跳过前比对监听进程命令行含 `next`。
   另 S6（轻）：`detectFrontendForm` 首探 5s 超时对冷启动 dev 可能误报 abnormal（waitHttp 预热后的形态
   复核可纠正，③-a 实测未误报）。

## 4. 批判承接核对

- 本任务接收的上游批判项：**W-NEXT-CHECKDEMO-PROD-001 P0-1**（deploy 出包路径接部署环境门/严格模式，
  消化位置：deploy.mjs `cmdStart` ⓪ 段 + `runCheckDemoAssert` 透传，盲测②a/②b/②c 实证）、
  **P0-4**（deploy 侧端口跟随，消化位置：`FRONTEND_PORT` 全链路派生 + check-demo 透传，盲测① ⑤ 实证）、
  **W-NEXT-PRODUCTION-BUILD-001 P0-5**（生产→dev 可逆性子命令，消化位置：`cmdStopProdAndRestartDev`，
  盲测③ 实证）。
- **新承接项：无**。三份上游资产遗留的承接清单中无指向 deploy.mjs 的未了项；本任务自批判 5 条均为
  「登记 + 建议」，无一条要求下游任务在本任务验收前完成（S2 单命令回程缺口已超出 P0-5 字面交付面，
  归为建议级改进项，不构成本任务验收阻塞）。

## 5. 资产消费证据（具名路径 → 消费方式）

| 资产 | 消费方式 |
|---|---|
| `0f566ef`（前任 WIP） | `git show --stat` + 全量走读 → 判定复用为基线，修复 F1-F4（§1） |
| `edu-agent/scripts/eval/deploy_env_gate.mjs` | 只调用不改：签名核对（`[env路径]` exit 0/1、`[DEPLOY_GATE]` 末行）→ deploy.mjs `runDeployEnvGate` spawnSync 接线 → 盲测②三子测实证 |
| `edu-agent/scripts/check-demo.mjs` | 只调用不改：签名核对（`--frontend-port`/`--prod-gate`、WARN/FAIL 分级、exit 规则）→ deploy.mjs 透传接线 → 盲测①/②c/③-b 三轮全量断言输出消费 |
| `deploy/README.md`（task123 清单含 0.5 部署环境门行） | §0.5 门行与 §5 用法段核对 + 回退路径/防漂移两处纠偏（§1.1） |
| AGENTS.md | 教训 1（删 .next）、教训 6（DEBUG=false 红线）、测试账号、启动命令口径；往返设计按教训 1 只删 `.next` 不动 `.next-prod`（盲测实证产物完好） |
| `edu-agent/.env.example`/`next.config.ts`（只读核对） | `NEXT_PROD_DIST_DIR → distDir` 机制核实（next.config.ts:17），支撑 build/start 两侧接线判断 |

## 6. 红线遵守自查

- 仅改 `edu-agent/scripts/deploy/deploy.mjs`、`deploy/README.md`、本报告三文件；**未触碰** check-demo.mjs、
  scripts/eval/**（deploy_env_gate 只调用）、edu-frontend/**（含 public/）、app/**。
- 真实 `.env` 未做任何修改（盲测②经临时 env 文件注入 DEBUG=true，文件在 gitignored logs/，测试后留存备查）。
- 活环境 3000/8000 已完整恢复（§2.4），全程后端 0 次重启、无孤儿进程残留。
- lock `wnextdeployhard1.lock` 已于 commit 前删除。
