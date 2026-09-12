# task18 完工报告:演示前检查单 check-demo.mjs(reshape-a)

> 交付 agent:运维工具工程师(独立开发 agent) · 日期 2026-09-12 · 工作区 `E:\stu\project\stu\EduAgent实施手册`
> 产出:`edu-agent/scripts/check-demo.mjs`(262 行,Node ≥18,零新依赖)· 本报告
> 硬性守则遵守:未改任何现有文件/服务(全程只读探测),未 git commit(待编排者验收统一提交)。

## 0. 一句话结论

脚本落地七件套+⑧ DEBUG advisory,两遍实跑均 <1 分钟(15.8s / 9.8s);当前环境 VM 未开机、Docker 引擎未启动,如实记录 **绿 5/8、红 ①②③**,红色项处置指引经独立探测证实准确(`vmrun list`=0 台在跑 VM、docker pipe 不存在);`--fail-drill` 与 ⑧ WARN 分支( mock 后端)均实证 FAIL/WARN 输出+指引+exit 非 0 正确。

## 1. 资产消费证据(必读四件)

| 资产 | 消费点 |
|---|---|
| `AGENTS.md` | 教训 6(DEBUG=true 无 Authorization 头返回虚拟管理员 user_id=1)→ 直接催生检查项 ⑧(无 token GET /api/admin/users 探测);教训 8(真实契约优先)→ 登录请求/响应形状以 curl 实测为准而非页面注释;教训 2(禁 Playwright,独立实证)→ 全脚本用 fetch/socket/child_process;测试账号 `adm02test/Test@123456`、`user000001/Test@123456` 取自"测试账号(DB 已验证)"节 |
| `.ai-hub/plans/dev-plan-reshape-a.md` L35/L62 | task18 GWT 原文:**七项**全绿(Milvus/Redis/Mongo/8000/3000/登录链路/关键页200)+一键拉起指引(VMware/redis 容器),任一红项一句话处置;断链演练应准确报红;验收指标 **<1 分钟**;C16 可证伪判据=「检查单<1 分钟;断链演练给出准确处置指引」 |
| `edu-agent/scripts/verify_pages_w2.mjs` | 复用其模式:登录契约(`login.data.access_token`,body `{account,password}`)、`BASE=127.0.0.1:3000 / API=127.0.0.1:8000` 常量风格、Node 直跑 fetch 风格(本脚本无需 CDP,纯探活故未引入 Chrome 依赖) |
| `.ai-hub/plans/contract-change-reshape-a2.md` | 环境背景通读;确认 `/api/admin/users` 属真实 admin 域端点(⑧ 探测目标有效),变更单内容不改变本任务范围 |

## 2. 脚本设计要点

- **八项检查**:① Milvus socket `192.168.85.101:19530` ② `docker exec edu-redis-standalone redis-cli ping` ③ MongoDB socket `192.168.85.101:27017` ④ `GET :8000/health`(校验 `status=ok`)⑤ `GET :3000/login-register.html` ⑥ 登录链路(admin+student 各一次 `POST /api/auth/login` + `GET /api/auth/me`,并校验 role=admin/student 与 user_id)⑦ 8 个核心 html 200(login-register/courses/course-detail?id=1/dashboard/learning/admin-dashboard/admin-mcp/admin-rag-upload)⑧ advisory:无 token GET `/api/admin/users`,200/`code:0` → **红 WARN**「DEBUG=true 虚拟管理员漏洞,上线前必须 False」(教训 6),401 → 绿。
- **汇总/退出码**:`绿 x/8`;全绿才 `exit 0`,否则 `exit 1`。逐项 `PASS/FAIL/WARN + 耗时ms`,FAIL 附一句话处置指引(附失败原因方括号)。
- **处置指引(FAIL→)**:①③ `vmrun start "E:\tt\CentOS 7 64 位 的克隆 docker\CentOS 7 64 位 的克隆 docker.vmx" nogui,等 60s`(脚本运行时 `fs.existsSync` 复核 vmx 路径,缺失会追加提示;本机已 `ls` 实证该路径存在);② `docker start edu-redis-standalone`(引擎未运行时附加"先启动 Docker Desktop");④ `cd edu-agent && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`;⑤⑦ `cd edu-frontend && node node_modules/next/dist/bin/next dev -p 3000`;⑥ 先过④(账号失效查 DB 种子);⑧ DEBUG 必须 False。
- **耗时控制(<1 分钟 GWT)**:socket 探活 3s 超时(VM 关机时 SYN 无响应,防 Windows 默认 21s SYN 重传挂死)、HTTP 5s 超时、docker exec 8s 超时,串行总耗时被硬性钳制。
- **`--fail-drill`**:① → `127.0.0.1:19531`、② → 容器内 `redis-cli -p 6380 ping`(假端口)、③ → `127.0.0.1:27018`,必然失败但**不动真实服务**,验证 FAIL 输出/指引/exit 非 0。
- **工程细节**:零新依赖(net/fetch/spawn 内置);`spawn` 不用 `shell:true`(规避 DEP0190,docker.exe 经 PATH 解析已实证);`CHECK_DEMO_BACKEND` env 覆盖仅用于 ⑧ WARN 分支自测;TTY 自动着色、`--no-color` 纯文本。

## 3. 实跑环境前置探测(先探测,未重启任何服务)

- `ls E:\tt\CentOS 7 64 位 的克隆 docker\` → `CentOS 7 64 位 的克隆 docker.vmx` **存在**(指引路径准确)。
- `vmrun list` → `Total running VMs: 0`(VM 关机 → ①③ 必红)。
- `docker ps` → `open //./pipe/docker_engine: The system cannot find the file specified`(Docker 引擎未启动 → ② 必红)。
- `curl :8000/health` → `{"status":"ok","app":"EduAgent","version":"0.3.0"}`;`:3000/login-register.html` → 200。
- 无 token `GET /api/admin/users` → `401 {"code":"40101",...}`(当前 DEBUG 安全 → ⑧ 应绿)。

## 4. 实跑 1:正常模式(完整输出粘贴)

命令:`cd edu-agent && node scripts/check-demo.mjs --no-color`,wall `real 0m15.840s`,**EXIT=1**。

```text
=== EduAgent 演示前检查单 check-demo.mjs ===
模式: normal  时间: 2026/9/12 12:32:43

[FAIL] ①. Milvus 连通 192.168.85.101:19530 (3013ms)
       -> 开启 VMware 虚拟机: vmrun start "E:\tt\CentOS 7 64 位 的克隆 docker\CentOS 7 64 位 的克隆 docker.vmx" nogui,等 60s [连接超时(>3000ms),主机不可达]
[FAIL] ②. Redis(docker exec edu-redis-standalone redis-cli ping) (306ms)
       -> docker start edu-redis-standalone(若 docker 引擎未运行,先启动 Docker Desktop)[docker 引擎未运行(Docker Desktop 未启动)]
[FAIL] ③. MongoDB 连通 192.168.85.101:27017 (3013ms)
       -> 开启 VMware 虚拟机: vmrun start "E:\tt\CentOS 7 64 位 的克隆 docker\CentOS 7 64 位 的克隆 docker.vmx" nogui,等 60s [连接超时(>3000ms),主机不可达]
[PASS] ④. 后端 8000 /health (55ms)  status=ok v0.3.0
[PASS] ⑤. 前端 3000 /login-register.html (15ms)
[PASS] ⑥. 登录链路 login×2 + /api/auth/me×2 (9041ms)  adm02test(role=admin,user_id=100003) + user000001(role=student,user_id=1)
[PASS] ⑦. 关键页 200 × 8 (106ms)  8/8 全 200
[PASS] ⑧. advisory: DEBUG 虚拟管理员探测(无 token /api/admin/users) (16ms)  无 token 被 401 拒绝(DEBUG 安全)

汇总: 绿 5/8,红项 ①、②、③ —— 请按上方指引处置后重跑 (检查耗时 15565ms)
```

**如实记录**:当前环境非全绿——VM(0 台在跑)与 Docker 引擎(pipe 不存在)未起,①②③ 红。红色项恰为任务书预授权情形(「若 Milvus 又断了,如实记录红色项+指引有效性」);④-⑧ 全绿,总耗时 15.8s <1 分钟(即便 ⑥ 的 9.0s 系后端登录接口真实延迟 ~2.2s/请求,curl 实测复现,非脚本开销)。**指引有效性**:①③ 的 vmx 路径经 ls 实证存在、vmrun list 佐证 VM 确未开;② 的 docker 引擎诊断与 `docker ps` 实测错误一致。

## 5. 实跑 2:--fail-drill(完整输出粘贴)

命令:`cd edu-agent && node scripts/check-demo.mjs --fail-drill --no-color`,wall `real 0m9.837s`,**EXIT=1**。

```text
=== EduAgent 演示前检查单 check-demo.mjs ===
模式: fail-drill(假端口演练,结果仅验证失败路径)  时间: 2026/9/12 12:33:06

--fail-drill:① Milvus→127.0.0.1:19531 ② Redis→容器内 6380 假端口 ③ Mongo→127.0.0.1:27018(必然失败,验证 FAIL 输出与指引)

[FAIL] ①. Milvus 连通 127.0.0.1:19531 (3ms)
       -> 开启 VMware 虚拟机: vmrun start "E:\tt\CentOS 7 64 位 的克隆 docker\CentOS 7 64 位 的克隆 docker.vmx" nogui,等 60s [连接被拒绝]
[FAIL] ②. Redis(docker exec edu-redis-standalone redis-cli ping) (309ms)
       -> docker start edu-redis-standalone(若 docker 引擎未运行,先启动 Docker Desktop)[docker 引擎未运行(Docker Desktop 未启动)]
[FAIL] ③. MongoDB 连通 127.0.0.1:27018 (1ms)
       -> 开启 VMware 虚拟机: vmrun start "E:\tt\CentOS 7 64 位 的克隆 docker\CentOS 7 64 位 的克隆 docker.vmx" nogui,等 60s [连接被拒绝]
[PASS] ④. 后端 8000 /health (54ms)  status=ok v0.3.0
[PASS] ⑤. 前端 3000 /login-register.html (18ms)
[PASS] ⑥. 登录链路 login×2 + /api/auth/me×2 (9063ms)  adm02test(role=admin,user_id=100003) + user000001(role=student,user_id=1)
[PASS] ⑦. 关键页 200 × 8 (123ms)  8/8 全 200
[PASS] ⑧. advisory: DEBUG 虚拟管理员探测(无 token /api/admin/users) (4ms)  无 token 被 401 拒绝(DEBUG 安全)

汇总: 绿 5/8,红项 ①、②、③ —— 请按上方指引处置后重跑 (检查耗时 9575ms)
```

**FAIL 分支判定**:①③ 假端口 `ECONNREFUSED`(3ms/1ms),FAIL 标签+VM 拉起指引+exit 非 0 全部正确;② 落入 docker 引擎未运行分支(当前环境引擎确实未起,属该失败模式下的正确指引;`-p 6380` 假端口分支已实现,引擎启动后即沿 redis-cli 连接拒绝路径报红——诚实记录,未为此拉起 Docker 引擎以免污染共享环境)。

## 6. 附加自测:⑧ WARN 分支(mock 后端 18000,EXIT=1)

起 mock(18000 `/api/admin/users` 返回 200 `{"code":0,...}`,其余契约同形),`CHECK_DEMO_BACKEND=http://127.0.0.1:18000 node scripts/check-demo.mjs --no-color` → 摘录:

```text
[WARN] ⑧. advisory: DEBUG 虚拟管理员探测(无 token /api/admin/users) (18ms)
       -> DEBUG=true 虚拟管理员漏洞,上线前必须 False(settings.DEBUG=false 并重启后端) [无 token 返回 HTTP 200 有数据]
[FAIL] ⑥. 登录链路 login×2 + /api/auth/me×2 (36ms)
       -> 先过 ④ 后端: ... [user000001: role=admin 期望 student]

汇总: 绿 3/8,红项 ①、②、③、⑥、⑧ —— 请按上方指引处置后重跑 (检查耗时 6576ms)
```

- ⑧ 红色 **[WARN]** 标签+教训 6 指引+计入 x/8+阻止 exit 0:全部符合规格。同跑 ⑥ 红为 mock 产物(mock 对学生也返 role=admin),反向实证 ⑥ 的 role 校验真实生效。测毕 mock 已停止,真实服务零接触。

## 7. 三视角自检

**① Eng 正确性/契约**:登录 body `{account,password}`、响应壳 `{code:0,data}`、`data.access_token`、`/me` role/user_id 校验——与 curl 实测契约一致(教训 8);socket 3s/HTTP 5s/docker 8s 三级超时钳制总耗时;spawn 无 shell 规避 DEP0190;`node --check` 语法通过;⑧ 后端不可达时降级为"跳过(以④为准)"避免误导性 DEBUG 指引。
**② Ops 演示可用性/失败路径**:每个红项一句话处置(含可直接粘贴的命令);③ 个失败模式(假端口/引擎未运行/角色漂移/WARN)均实证;<1 分钟达标(15.8s/9.8s/6.6s);`--no-color` 供 CI/粘贴,TTY 自动着色。
**③ Review 可证伪与遗留**:C16 判据「检查单<1 分钟;断链演练给出准确处置指引」均给出实测数据。遗留两条如实登记:(a) **全绿 exit 0 未在本环境端到端演示**(VM/Docker 未起,①②③ 红是环境实况而非脚本缺陷;全绿判定 `pass===results.length?0:1` 代码 3 token 可审计,拉起 VM+Docker 后重跑即可证);(b) Redis drill 的容器内 6380 分支未在引擎运行态实证(分支已实现,当前引擎未起落入引擎诊断分支,指引仍正确)。

## 8. 结果摘要(任务书要求三行)

- 脚本:`E:\stu\project\stu\EduAgent实施手册\edu-agent\scripts\check-demo.mjs`(262 行,零新依赖)
- 报告:`E:\stu\project\stu\EduAgent实施手册\test-reports\task18-completion-report-reshape-a.md`
- 实跑 1 正常模式:绿 5/8,红 ①②③(VM 未开机/Docker 引擎未启动,环境实况如实记录,指引已验证),耗时 **15.8s**,exit 1
- 实跑 2 --fail-drill:绿 5/8,红 ①②③(假端口 19531/6380/27018,FAIL 分支+指引正确),耗时 **9.8s**,exit 1
- 附加 ⑧ WARN 自测(mock):红 ⑧ 正确触发教训 6 WARN+exit 1,耗时 6.6s
- GWT <1 分钟:三遍实跑全部达标
