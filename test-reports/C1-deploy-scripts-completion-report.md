# taskC1 一键脚本三件套（start/stop/status）— 完成报告

- 日期：2026-09-13
- 执行：C 阶段部署工具工程师（独立 agent，真实进程编排 + check-demo 独立实证）
- 产出：`edu-agent/scripts/deploy/deploy.mjs`（Node ≥18，**零新依赖**，与 check-demo 同栈同口径）
- commit：`feat(c)/C1-deploy-scripts`

## 1. 交付物与设计要点

| 要素 | 实现 |
|---|---|
| start | ①前置检查（MySQL 3306 / VM Milvus+Mongo socket / Redis docker ping，**只报告不阻塞硬启**，与 check-demo 同口径；Redis 失败给「docker start edu-redis-standalone（若引擎未运行先启 Docker Desktop）」指引）②后端 `.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000`（**读 .env 的 DEBUG/ENV_NAME 形态原样，不做替换**，启动前打印形态报告）③前端 **build+start 生产形态**（C2 结论：`NEXT_PROD_DIST_DIR=.next-prod`；`.next-prod/BUILD_ID` 缺失时自动先 `npx next build`）④拉起后自动跑 check-demo 断言 8/8，exit code 透传 |
| stop | 按端口 netstat→PID→`taskkill /F /T` 清 8000/3000；`--all` 附加 Redis 容器处置提示（**容器本身不停**，只提示）；顺带清理陈旧 `logs/deploy.pids.json` 记录 |
| status | 透传执行 `scripts/check-demo.mjs`（stdio inherit，exit code 透传） |
| 日志 | `edu-agent/logs/deploy-backend.log` / `deploy-frontend.log` / `deploy-frontend-build.log`（追加式）；PID 记录 `logs/deploy.pids.json` |
| 幂等 | 端口已在监听则跳过对应服务并提示 PID（前端跳过时提示"可能是 dev 形态，如需生产形态请先 stop"） |
| 形态约束 | 脚本不代替 .env 生产段配置：DEBUG=false 时明确报告 lifespan 硬校验约束（存储任一不可达即拒启 + JWT_SECRET/API_TOKEN 默认值拒启，见 `deploy-config-checklist.md` §0） |

## 2. 现状自证与验证前提

- 验证前实测：`.env` 为 **dev 形态**（DEBUG=true、JWT_SECRET=dev-默认值、无 ENV_NAME 行）；在跑服务 8000（PID 31696）/ 3000（PID 33916）。
- 环境前提探测（脚本前置检查同口径实测）：MySQL 3306 OK、VM Milvus 19530 / Mongo 27017 / MinIO 9000 / Neo4j 7687 全 OK、Redis `docker exec edu-redis-standalone redis-cli ping` = PONG。**本次验证无环境前提红项。**
- 脚本按任务要求不做 .env 替换；本次演示以 .env 原样（dev 形态）跑通生产**进程形态**（uvicorn 直启 + next start）。check-demo 8/8 实测通过——⑧ 虚拟管理员探测在 DEBUG=true 下实测仍被 401 拒绝（与脚本初版注释"必 WARN"不符，已按实测修正脚本措辞，遵循教训 8"真实契约优先于注释"）。

## 3. 验证记录（编排者授权的 stop-then-start 演示中断，结束态已恢复）

### 3.1 stop（清掉现有 dev 服务 —— **此为编排者授权的演示中断**，见 §3.5 恢复）

```text
=== EduAgent deploy stop(清 8000/3000)===
[ OK ] 后端 端口 8000 PID 31696 已终止
[ OK ] 前端 端口 3000 PID 33916 已终止

stop 完成:8000/3000 已清零或原本无监听
EXIT=0
(netstat 复核: PORTS_CLEARED)
```

### 3.2 start（生产形态全栈，第一次）

```text
=== EduAgent deploy start(build+start 生产形态;幂等)===
=== ① 前置检查(报告口径,不阻塞硬启——与 check-demo 同口径)===
[deploy] .env 形态原样: DEBUG=true  ENV_NAME=(未设置→config.py 默认 local)  (脚本不做替换)
[WARN] 当前为 dev 形态(DEBUG=true):存在虚拟管理员后门风险面(P1-8 门禁要求 DEBUG=true+ENV_NAME=local;生产交付前必须改 false,taskC3 硬验收)
[ OK ] MySQL 可达 — 宿主 MySQL 127.0.0.1:3306
[ OK ] Milvus 可达 — VM Milvus 192.168.85.101:19530
[ OK ] MongoDB 可达 — VM MongoDB 192.168.85.101:27017
[ OK ] Redis 可达 — docker exec edu-redis-standalone redis-cli ping = PONG

=== ② 后端(uvicorn 生产形态,读 .env 形态原样)===
[deploy] 后端拉起中(PID 13544,日志 logs/deploy-backend.log),等待 /health ...
[ OK ] 后端就绪 http://127.0.0.1:8000/health(6203ms)

=== ③ 前端(build+start 生产形态,C2 结论)===
[ OK ] 前端生产产物已存在 .next-prod/BUILD_ID=PjtNuRyHZRxdK-enVf5RQ(跳过 build)
[deploy] 前端拉起中(PID 34012,日志 logs/deploy-frontend.log),等待 /login-register.html ...
[ OK ] 前端就绪 http://127.0.0.1:3000/login-register.html(4453ms)

=== ④ check-demo 断言(期望 8/8)===
[PASS] ① Milvus ② Redis PONG ③ MongoDB ④ 后端 /health status=ok v0.3.0
[PASS] ⑤ 前端 /login-register.html ⑥ 登录链路 adm02test(role=admin,user_id=100003) + user000001(role=student,user_id=1)
[PASS] ⑦ 关键页 200 × 8 (8/8 全 200) ⑧ 无 token 被 401 拒绝(DEBUG 安全)
汇总: 绿 8/8 —— 演示环境就绪
[ OK ] check-demo 8/8 全绿——演示环境就绪
EXIT=0
```

### 3.3 start（第二次，幂等验证）

```text
=== ② 后端 ===
[WARN] 端口 8000 已有监听(PID 26472)——幂等跳过后端拉起
=== ③ 前端 ===
[WARN] 端口 3000 已有监听(PID 5160)——幂等跳过前端拉起(注意:可能是 dev 形态,如需生产形态请先 stop)
=== ④ check-demo 断言 === 汇总: 绿 8/8 —— 演示环境就绪
EXIT=0
```

### 3.4 stop --all（Redis 容器不停，只提示）

```text
[ OK ] 后端 端口 8000 PID 26472 已终止
[ OK ] 前端 端口 3000 PID 5160 已终止
[--all] Redis 容器 edu-redis-standalone 保留运行(不停)——缓存/限流/会话依赖它,一般无需停止;
        如确需停止: docker stop edu-redis-standalone(重启: docker start edu-redis-standalone;docker 引擎未运行先启动 Docker Desktop)
stop 完成:8000/3000 已清零或原本无监听
EXIT=0
(netstat 复核: PORTS_CLEARED；docker exec edu-redis-standalone redis-cli ping = PONG —— 容器确实未受影响)
```

### 3.5 status（恢复 dev 态后复核 = check-demo 原样透传）

```text
=== EduAgent 演示前检查单 check-demo.mjs ===
[PASS] ① Milvus ② Redis PONG ③ MongoDB ④ 后端 /health ⑤ 前端登录页
[PASS] ⑥ 登录链路 ×2 ⑦ 关键页 8/8 全 200 ⑧ 无 token 被 401 拒绝(DEBUG 安全)
汇总: 绿 8/8 —— 演示环境就绪 (检查耗时 1674ms)
EXIT=0
```

### 3.6 结束态声明（编排者裁决项）

- **已恢复 dev 态**：后端 uvicorn `app.main:app --port 8000`（.env 原样 dev 形态）+ 前端 `next dev -p 3000`，最终 `deploy.mjs status` = check-demo **8/8 全绿**（2026-09-13 12:47:09）。
- 演示中的生产形态进程（uvicorn 生产直启 + next start）已全部 stop 清零，Redis 容器全程未动。
- 备忘：AGENTS.md 启动命令中 `node next\dist\bin\next dev` 为路径简写，实际可执行路径为 `edu-frontend/node_modules/next/dist/bin/next`（首次按简写拉起 MODULE_NOT_FOUND，已按 check-demo 指引路径纠正；建议中心库同步时修正该简写）。

## 4. 边界与登记

1. **未动 .env**：start 读 DEBUG/ENV_NAME 原样并报告；8/8 在 dev 形态 .env 下实测通过。DEBUG=false 生产段配置的端到端硬验收归 taskC3（P2）。
2. **未验证 next build 分支**：`.next-prod/BUILD_ID` 已存在（C2 产物）故跳过 build；build 分支逻辑（缺失时自动 build、失败落 `deploy-frontend-build.log` 并中止 start）为代码路径审查+日志落点设计，端到端触发留待产物失效场景（删除 .next-prod 后重跑 start 即可复验）。
3. **禁重启在跑服务守则**：8000/3000 的 stop-then-start 均为编排者授权的演示中断，已按 §3.6 恢复原 dev 形态并独立实证（check-demo 8/8）。
4. 前置检查四项全为"报告口径"（WARN 不阻塞硬启），与 check-demo 同口径；生产形态（DEBUG=false）下真正的拒启判定交由后端 lifespan 硬校验（P1-8 门禁 + _security_guard + 存储初始化），脚本只负责提前给出人话指引。
5. 日志与 PID 文件（`logs/deploy-*.log`、`deploy.pids.json`）不入库；本报告与 `scripts/deploy/` 一并提交。

## 5. DoD 对照

| GWT（dev-plan taskC1） | 结果 |
|---|---|
| Given 干净进程环境（全 kill）；When `node deploy.mjs start` | 实测：stop 全清后 start 依序拉起 Redis（前置报告，容器已在跑）→ 后端（生产 env 形态）→ 前端（build/start 形态） |
| Then check-demo 8/8 | 实测 8/8 全绿（§3.2） |
| `stop` 全端口清零 | 实测 8000/3000 清零（§3.1/§3.4） |
| `status`=check-demo 原样 | 实测透传 + exit code 一致（§3.5） |
