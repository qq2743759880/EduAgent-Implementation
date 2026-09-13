# taskC3 DEBUG=False 端到端验收报告

> 验收人：C 阶段生产形态验收工程师（独立 agent）｜日期：2026-09-13
> 验收方式：真实 HTTP + CDP 真实渲染 + 数据库实测（无 Playwright、无 DB 直写、无契约变更）
> 结论：**全部断言 PASS（17/17 API + 8/8 页 CDP + check-demo 8/8），发现 DEBUG 依赖项 1 项，已就地修复（commit `c208020`，工作量约 0.5h，预算 2 天内）**

---

## 1. 生产形态拉起（任务 1）

| 步骤 | 结果 |
|---|---|
| 原 .env 备份 | `logs/.env.c3-dev-backup`（gitignored），**结束后已还原并删除备份文件（密钥不落盘残留）** |
| scratch 生产 .env | `DEBUG=false`、`ENV_NAME=prod`、`JWT_SECRET=secrets.token_hex(32)`、`API_TOKEN=secrets.token_urlsafe(24)`（随机生成，不入库不入 git）、`CORS_ORIGINS`（见 §4）、`LOG_LEVEL=INFO`；其余键与 dev .env 逐字一致 |
| stop dev 态 | `node scripts/deploy/deploy.mjs stop`：8000(PID 35300)/3000(PID 3384) 清零 |
| 生产拉起 | `node scripts/deploy/deploy.mjs start`：后端 uvicorn 读 .env 形态原样（6.2s 就绪）+ 前端 `next start`（.next-prod/BUILD_ID=PjtNuRyHZRxdK-enVf5RQ，C2 产物，3.4s 就绪） |
| VM/Redis 前置 | 实测全部可达（**无 ENV_BLOCKED**）：MySQL 127.0.0.1:3306、Redis 容器 edu-redis-standalone(PONG)、VM 192.168.85.101 Milvus:19530/Mongo:27017/MinIO:9000/Neo4j:7687 |

## 2. 断言清单（逐项）

### ① 启动形态 —— **PASS**

- 生产段启动日志（logs/deploy-backend.log 12:53 JSON 段）**无** "默认 JWT_SECRET / 默认 API_TOKEN" 告警、无拒绝启动（`_security_guard` 强随机密钥通过；注意日志为追加式，12:44 段的密钥告警属于此前 dev 形态运行，非本次生产段）。
- P1-8 门禁：DEBUG=false 下门禁不触发，正常启动。
- **7 类存储初始化结果（lifespan 原文）**：
  ```
  {'mysql': 'ok', 'mysql_ro': 'ok', 'milvus': 'ok', 'mongodb': 'ok', 'minio': 'ok', 'neo4j': 'ok', 'redis': 'ok'}
  ```
  （Milvus pkg/v2.5.5；MinIO 192.168.85.101:9000；Neo4j bolt://192.168.85.101:7687——全部真实连通，无降级、无 ENV_BLOCKED。）
- 非阻断环境告警（如实记录，非 DEBUG 依赖）：BGE-M3 本地模型目录 C:\ai-models\bge-m3 不存在→云端兜底；reranker sidecar(8601) 未运行→进程内/规则兜底。

### ② 登录链路（双账号 login/me/refresh）—— **PASS**（8/8 子断言）

| 账号 | login | auth/me | refresh | me(新token) |
|---|---|---|---|---|
| admin `adm02test` | 200 code=0，双 token 齐全 | role=admin user_id=100003 | 200 code=0，新 access 可用 | role=admin |
| student `user000001` | 200 code=0，双 token 齐全 | role=student user_id=1 | 200 code=0，新 access 可用 | role=student |

- 观察（非缺陷）：refresh 返回的 refresh_token 与请求值相同（未轮换），与 7 天滑动过期设计一致，契约未变。

### ③ 无 token / 虚拟管理员探测（P1-8 核心）—— **PASS**（4/4）

| 断言 | 实测 |
|---|---|
| 无 token `GET /api/admin/users` | **401** `{"code":"40101","message":"缺少 Authorization 请求头"}` |
| 无 token `GET /api/users/me` | **401** 同上壳 |
| 虚拟管理员探测（admin/users + users/me + auth/me 三端点无 token） | **全部非 200 → 虚拟管理员不可用**（DEBUG=true 时 user_id=1 后门未触发） |
| `X-Force-Role: admin` + `X-Force-User-Id: 1`（无 token） | **401**——X-Force 头仅 DEBUG=true 生效，生产形态确认无效 |

### ④ 核心页 CDP 抽验 8 页 —— **PASS（修复后 8/8）**

页面：login-register / courses / course-detail?id=1 / dashboard / learning / me / achievements / admin-dashboard（headless Chrome CDP 真实导航，脚本 `test-reports/C3_pages_cdp.mjs`，截图 `page-verify-c3/*.png`）。

- 首轮（CORS_ORIGINS 仅 localhost:3000）：2/8 零错——**发现 DEBUG 依赖项**（见 §4）。
- 修复后：**8/8 渲染成功（bodyH/textLen 均 >0）+ console 零错**；course-detail 出现真实课程数据（h1=通用编程入门班·直播）、me 出现真实用户（h1=Adm02Test）、admin-dashboard 通过三段守卫进入（h1=平台运营总览）、login 后 token 注入可用、无 DEBUG 水印/虚拟管理员入口。

### ⑤ 50301 脱敏（可选，Redis 停机重测）—— **PASS（脱敏达标）**

- `docker stop edu-redis-standalone` 后实测（生产形态、持有效 token）：`/api/users/me`、`/api/recommend/next`、`/api/vocab/daily` 均 200（Redis 依赖**fail-open 降级**，不硬失败故未触发 50301 分支）；`/health` 200；登录 200。
- **脱敏核心断言**：所有响应体扫描 `redis:// / ConnectionRefused / 10061 / edu-redis` 等内部细节——**零泄露**；连接类异常若逃逸由 main.py 全局兜底判 50301 + 用户化 message（T19-3 机制在位）。
- 测后 `docker start` 恢复，redis-cli ping=PONG。

### ⑥ CORS 跨源实测 —— **PASS（含 1 项修复）**

| 场景 | 修复前 | 修复后 |
|---|---|---|
| 预检 Origin=http://localhost:3000（白名单） | 200，ACAO 回显 | 200，ACAO 回显 |
| 实际请求 Origin=http://localhost:3000 | 200，ACAO 回显 | 200，ACAO 回显 |
| 预检 Origin=http://127.0.0.1:3000 | **无 ACAO → 拒绝** | 200，ACAO=http://127.0.0.1:3000 |
| 预检/实际请求 Origin=http://evil.example.com | 无 ACAO（预检 400）——浏览器侧拦截 | 同左（白名单机制未放松） |

## 3. DEBUG 依赖项与修复登记

### fix-1：生产 CORS 源缺失 127.0.0.1（predicted 候选 1 命中）

- **现象**：生产形态 `CORS_ORIGINS=http://localhost:3000`（以及 main.py 生产回退单源）下，用户以 `http://127.0.0.1:3000` 访问前端时，页面所有 API 调用被预检拦截 → 8 页中 6 页 console 报错（数据全空），admin-dashboard 三段守卫失败跳登录。DEBUG 态 CORS=`*` 从未暴露。
- **修复**（commit `c208020`，`fix(c)/C3-debug-dep`，约 0.5h ≪ 2 天预算）：
  1. `app/main.py` `_cors_origins()` 生产回退改为 `["http://localhost:3000", "http://127.0.0.1:3000"]` 双源；
  2. `.env.example` 生产段 CORS 指引同步更新（标注"必须同时含 localhost 与 127.0.0.1 双源"）。
- **零契约变更**：CORS 中间件配置非 API 契约；`contracts/*.json` 未动。
- **复验**：修复重启后 CDP 8/8 零错 + API 断言 17/17 + evil.example.com 仍被拒。

## 4. 结束态（可逆性证明）

| 项 | 结果 |
|---|---|
| 原 dev .env 还原 | 逐字还原（DEBUG=true / JWT_SECRET=dev-secret-key-change-in-production / LOG_LEVEL=DEBUG 等）；备份文件已删除 |
| dev 服务恢复 | 后端 uvicorn:8000（DEBUG=true dev 形态）+ 前端 next dev:3000，双端口 LISTENING |
| 复跑 check-demo | **8/8 全绿**（含 ⑧ DEBUG 虚拟管理员探测：dev 形态下 AdminAuthMiddleware 对 /api/admin/* 匿名仍 401 拒绝） |
| Redis 容器 | 全程运行（仅 ⑤ 探测期间短暂 stop→已 start 恢复） |
| 生产 scratch 密钥 | 随机生成、未入库未入 git，报告不含明文 |

## 5. 产物与 commit

- `fix(c)/C3-debug-dep`：`c208020`（app/main.py + .env.example）
- `test(c)/C3-debugfalse-e2e`：本报告 + `test-reports/C3_api_assert.py` + `test-reports/C3_pages_cdp.mjs`（验证脚本，可复跑）
- CDP 截图：`test-reports/page-verify-c3/*.png`（8 页）

## 6. 上报项

- 无超预算项（唯一修复 0.5h）。无契约变更。无 ENV_BLOCKED。
- 备注（非阻断）：① BGE-M3/reranker 本地模型目录缺失属机器环境，生产部署需按 .env.example 指引配置或走云端通道；② refresh_token 未轮换为既有契约行为，建议后续批判批次评估轮换策略。
