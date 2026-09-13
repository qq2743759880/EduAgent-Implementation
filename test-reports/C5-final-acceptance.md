# taskC5 终验收报告：干净环境一条命令 + 强制批判收口（C 阶段最小部署包）

> 验收人：C 阶段终验收 agent（独立）｜日期：2026-09-13
> 验收方式：真实进程编排（stop/start 授权循环）+ 真实 HTTP + CDP 真实渲染（无 Playwright、无 DB 直写、零契约变更、生产代码零改动）
> **判定：最小部署包 DONE**（dev 形态 .env 原样一条命令全绿；DEBUG=False 生产形态硬验收已由 taskC3 独立实证闭环，见 `edu-agent/test-reports/C3-e2e-report.md`）

---

## 1. 验收前状态（原态快照，供恢复对照）

| 项 | 状态 |
|---|---|
| 端口 8000 / 3000 | LISTENING（PID 31864 / 31612），dev 形态（uvicorn dev + next dev） |
| `.env` 形态 | dev 原样（DEBUG=true、ENV_NAME 未设），**脚本设计为读形态原样不做替换**，未动 |
| review-gate 脚本 | `D:\.ai-hub\skills\tt\scripts\review-gate.mjs` 在位（52121 bytes） |

## 2. 一条命令验收（任务 1）

### 2.1 stop 全清

```text
=== EduAgent deploy stop(清 8000/3000)===
[ OK ] 后端 端口 8000 PID 31864 已终止
[ OK ] 前端 端口 3000 PID 31612 已终止

stop 完成:8000/3000 已清零或原本无监听
EXIT=0
(netstat 复核: PORTS_CLEARED)
```

### 2.2 `node edu-agent/scripts/deploy/deploy.mjs start`（一条命令，完整输出）

```text
=== EduAgent deploy start(build+start 生产形态;幂等)===
后端目录: E:\stu\project\stu\EduAgent实施手册\edu-agent
前端目录: E:\stu\project\stu\EduAgent实施手册\edu-frontend

=== ① 前置检查(报告口径,不阻塞硬启——与 check-demo 同口径)===
[deploy] .env 形态原样: DEBUG=true  ENV_NAME=(未设置→config.py 默认 local)  (脚本不做替换)
[WARN] 当前为 dev 形态(DEBUG=true):存在虚拟管理员后门风险面(P1-8 门禁要求 DEBUG=true+ENV_NAME=local;生产交付前必须改 false,taskC3 硬验收)
[ OK ] MySQL 可达 — 宿主 MySQL 127.0.0.1:3306
[ OK ] Milvus 可达 — VM Milvus 192.168.85.101:19530
[ OK ] MongoDB 可达 — VM MongoDB 192.168.85.101:27017
[ OK ] Redis 可达 — docker exec edu-redis-standalone redis-cli ping = PONG

=== ② 后端(uvicorn 生产形态,读 .env 形态原样)===
[deploy] 后端拉起中(PID 33388,日志 logs/deploy-backend.log),等待 /health ...
[ OK ] 后端就绪 http://127.0.0.1:8000/health(14432ms)

=== ③ 前端(build+start 生产形态,C2 结论)===
[ OK ] 前端生产产物已存在 .next-prod/BUILD_ID=PjtNuRyHZRxdK-enVf5RQ(跳过 build)
[deploy] 前端拉起中(PID 19048,日志 logs/deploy-frontend.log),等待 /login-register.html ...
[ OK ] 前端就绪 http://127.0.0.1:3000/login-register.html(6010ms)

=== ④ check-demo 断言(期望 8/8)===
[PASS] ①. Milvus 连通 192.168.85.101:19530 (9ms)
[PASS] ②. Redis(docker exec edu-redis-standalone redis-cli ping) (4666ms)  PONG
[PASS] ③. MongoDB 连通 192.168.85.101:27017 (4ms)
[PASS] ④. 后端 8000 /health (81ms)  status=ok v0.3.0
[PASS] ⑤. 前端 3000 /login-register.html (30ms)
[PASS] ⑥. 登录链路 login×2 + /api/auth/me×2 (1785ms)  adm02test(role=admin,user_id=100003) + user000001(role=student,user_id=1)
[PASS] ⑦. 关键页 200 × 8 (133ms)  8/8 全 200
[PASS] ⑧. advisory: DEBUG 虚拟管理员探测(无 token /api/admin/users) (11ms)  无 token 被 401 拒绝(DEBUG 安全)

汇总: 绿 8/8 —— 演示环境就绪 (检查耗时 6719ms)
[ OK ] check-demo 8/8 全绿——演示环境就绪
EXIT=0
```

**断言结果：check-demo 8/8 全绿 + 双账号登录链路绿（admin adm02test/user_id=100003 + student user000001/user_id=1）+ EXIT=0。**

## 3. 抽验（三项全绿）

| 抽验项 | 命令/请求 | 实测 | 结论 |
|---|---|---|---|
| admin/users-refine | `GET http://127.0.0.1:3000/admin-users-refine-proto.html` | **HTTP 200**（47414 bytes, text/html）；`GET /api/admin/users?page=1&page_size=5`（admin token）→ **200 code=0** `{total,page,page_size,items}`；`GET /api/admin/users/dashboard/metrics` → 200 code=0 | **PASS** |
| dashboard | `GET http://127.0.0.1:3000/dashboard.html` | **HTTP 200**（54115 bytes, text/html） | **PASS** |
| /media 视频头 | `curl -I http://127.0.0.1:8000/media/videos/VID-20260913-A3DA351A.mp4` | **HTTP 200**，`content-type: video/mp4`，`accept-ranges: bytes`，`content-length: 3145728`，附 CSP/nosniff/X-Frame-Options 等安全响应头 | **PASS** |

登记（非缺陷）：任务书原文「admin/users-refine」无同名 API 路由（后端 `app/admin/user_admin/router.py` 实际路由为 `/api/admin/users` 系列）；对应交付物为前端页 `admin-users-refine-proto.html`，已按页 200 + 列表 API 200 双口径抽验，二者均绿。

## 4. 8 核心页 CDP 渲染抽验（dev-plan taskC5 GWT 补充口径）

复用 `edu-agent/test-reports/C3_pages_cdp.mjs`（headless Chrome + CDP，截图 `test-reports/page-verify-c5/`）：

```text
login-register / courses / course-detail?id=1(h1=通用编程入门班·直播) / dashboard(h1=你好，同学)
/ learning / me(h1=Adm02Test) / achievements(h1=成就与成长) / admin-dashboard(h1=平台运营总览)
汇总: 8/8 页渲染+console 零错 —— 全绿
```

## 5. 形态口径说明（判定依据）

- 本次终验收按 deploy.mjs 设计「.env 形态原样」执行，当前 .env 为 dev 形态——**这验证的是部署工具链与进程编排本身**（前置检查→后端→前端→check-demo 断言全链路）。
- **DEBUG=False 生产形态硬验收（P2）不在此重复**：taskC3 已于同日独立实证闭环（生产 .env 段拉起、7 类存储初始化全 ok、无默认密钥告警、双账号 login/me/refresh 8 断言、无 token 全 401 + X-Force 生产无效、8 页 CDP 零错、Redis 停机脱敏、CORS 双源），报告 `edu-agent/test-reports/C3-e2e-report.md`，修复登记 `c208020`。
- 两者合流即 GWT 完整口径：**工具链（本报告）× 生产形态（C3 报告）**。

## 6. 强制技术批判 + review-gate 机验（任务 2/3）

- 批判文档：`.ai-hub/plans/C5-技术批判.md`（**5 条**，≥3 达标；对标角度：①Supabase/Coolify/Dokku 一键部署体验 ②Twelve-Factor App 配置/日志/进程合规 ③Django deploy checklist 安全清单）
- 承接方案：`.ai-hub/plans/C5-优化修改方案.md`（5 条承接表 + 实施顺序 + 红线自查）
- review-gate 机验实录（`node D:\.ai-hub\skills\tt\scripts\review-gate.mjs --dir .ai-hub/plans --id C5 --auto-register --verify-urls`）：

```text
PASS 批判文档存在  5 条
PASS 有效批判≥3（含URL+日期）  有效 5/5
PASS 优化修改方案存在  存在
PASS tracker 已登记  含 C5
SKIP(幂等) ×5（此前已登记，幂等跳过）

[OK] C5 批判闸门通过 + 自动登记 0 条 / 生成任务文档 0 份 / 跳过重复 5 条

[URL 真验] 网络可用
  PASS  https://coolify.io/docs/get-started/installation/  (200)
  PASS  https://12factor.net/  (200)
  PASS  https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/  (200)
  PASS  https://supabase.com/docs/guides/self-hosting  (200)
[URL 真验] 有效批判 5 条：真实对标可达 5 / 无效 0（FAIL 的批判不计有效）
```

## 7. 终验收判定

## **最小部署包 DONE**

依据：①干净进程环境一条命令 start → check-demo 8/8 + 双账号登录 + EXIT=0；②三项抽验全绿；③8 核心页 CDP 渲染 console 零错；④C0（220 键配置模板）/C1（三件套脚本）/C2（next build+start）/C3（DEBUG=False 端到端+1 修复）/C4（runbook README）五交付物全部独立实证在案；⑤强制批判 5 条（对标 URL 全部机验 200）已登记 tracker 并有承接方案。P1~P6 前提红线零违反（零契约变更/密钥零入库/生产代码零改动）。

## 8. 遗留清单（移交后续批次）

### 代码侧（生产代码零改动守则下仅登记）
| # | 项 | 来源 | 处置建议 |
|---|---|---|---|
| K1 | `/api/metrics` 裸端点无鉴权护栏 | README 附录 task123 自检登记 | 并入批判 C5-4 security-check 子命令范围 |
| K2 | JWT_SECRET 无轮换/fallback 机制 | C5-4 批判 | `JWT_SECRET_FALLBACKS` 双密钥窗口方案（承接表 C5-4②，新增部署配置项需走用户逐条审） |
| K3 | 500 错误仅本地日志、无上报通道 | C5-4 批判 | error-stream 独立事件流 + 可选 ERROR_WEBHOOK_URL（承接表 C5-4③） |
| K4 | refresh_token 不轮换（7 天滑动过期契约行为） | C3 报告 §6 备注 | 契约行为，归后续批判批次评估 |

### 演示侧
| # | 项 | 说明 |
|---|---|---|
| D1 | BGE-M3 本地模型目录缺失（C:\ai-models\bge-m3）→ 云端兜底；reranker sidecar(8601) 未运行 → 进程内兜底 | 机器环境项，非代码缺口；生产部署按 .env.example 指引配置 |
| D2 | check-demo ⑦ 关键页清单未含 `admin-users-refine-proto.html` 等抽验页 | 已按 C5 抽验口径覆盖一次；是否扩清单归后续 |
| D3 | Redis restart 策略未实测（README 巡检第 4 条自注"待验证"） | 承接表 C5-3④ 一并收口 |

### 运维侧
| # | 项 | 说明 |
|---|---|---|
| O1 | **生产交付前必须切 .env 生产段**（DEBUG=false + ENV_NAME=prod + 强密钥 + CORS 双源），按 `deploy/README.md` §2 逐键配置——deploy.mjs 有形态 WARN 但无断言门 | 承接表 C5-2（`--profile prod` 形态断言门，P1） |
| O2 | 首次部署路径（venv/node_modules/edu 库快照恢复）无计时无演练，README 两处"待验证" | 承接表 C5-1（doctor 子命令 + 新机器全流程走查计时，P1） |
| O3 | 裸 spawn 无守护/强杀无优雅窗口/deploy-*.log 无轮转；宿主重启不自启 | 承接表 C5-3（--watch 守护 + SIGTERM 优雅停机 + 日志轮转，P1） |
| O4 | 附录 docker-compose 路线未端到端验证，与 deploy.mjs 双事实源 | 承接表 C5-5（附录横幅 + C 全量排期收口，P2） |
| O5 | 公网/HTTPS/CI-CD 明确超范围（P6 边界） | C 阶段全量另行规划 |

## 9. 结束态（可逆性）

| 项 | 结果 |
|---|---|
| 服务恢复 | stop 全清 → 重新拉起原 dev 形态（uvicorn:8000 + next dev:3000，与验收前原态一致） |
| 复跑 status | check-demo **8/8 全绿**（汇总：绿 8/8——演示环境就绪） |
| .env | 全程未动（dev 形态原样） |
| 生产进程 | 验收中的 next start(PID 19048)/uvicorn(PID 33388) 已 stop 清零 |
| Redis 容器 | 全程未动（PONG） |
| 本次授权操作 | stop/start 循环共 2 轮（验收 1 轮 + 恢复原态 1 轮），如实记录 |

## 10. 产物与 commit

- `test-reports/C5-final-acceptance.md`（本报告）
- `.ai-hub/plans/C5-技术批判.md`（5 条，URL 已机验）+ `.ai-hub/plans/C5-优化修改方案.md`（承接表）
- CDP 截图：`test-reports/page-verify-c5/`（8 页）
- start 完整输出留存：`edu-agent/logs/c5-start-output.txt`
- commit：`docs(c)/C5-final-acceptance`
