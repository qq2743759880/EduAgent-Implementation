# EduAgent 部署 README（运维 runbook 第一章 · taskC4）

> 面向读者：**从未接触过本项目的新运维/新人**。目标：照本文从零操作，把 EduAgent 在与本机同构的环境
> （Windows 主机 + VMware 虚拟机 Docker）里一键拉起，并通过 check-demo 8/8 验收（与 taskC5 同一验收态）。
>
> 事实来源（先读后写，本文一切命令/路径/行为与下列交付物一致）：
> - 一键脚本：`edu-agent/scripts/deploy/deploy.mjs`（taskC1）
> - 生产配置模板：`edu-agent/.env.example`（taskC0，220 键）；配置项清单 `.ai-hub/plans/deploy-config-checklist.md`
> - 生产形态端到端实测：`edu-agent/test-reports/C3-e2e-report.md`（taskC3）
> - 检查单：`edu-agent/scripts/check-demo.mjs`（8 项检查，FAIL 时逐项给一句话处置指引）
>
> 边界一句话：**本包 = 本机同构部署**；公网/HTTPS/容器化归 C 阶段全量（容器化路线见文末附录）。

---

## 1. 架构一页图

```
+-----------------------------------------------------------------------------+
| Windows 宿主机                                                               |
|                                                                             |
|  [MySQL 8]            [后端 uvicorn]           [前端 Next.js]                |
|  127.0.0.1:3306       127.0.0.1:8000            127.0.0.1:3000               |
|  业务库 edu（快照恢复） FastAPI，读 .env 原样     生产形态 build+start          |
|        ^                   ^    ^                ^        （.next-prod）     |
|        |                   |    +----------------+   用户浏览器打开 :3000    |
|  [Redis 容器] --------------+                                                |
|  edu-redis-standalone:6379                                                  |
|  （宿主 Docker Desktop）缓存/限流/会话/队列                                   |
+-----------------------------------------------------------------------------+
         |  VMware 虚拟网络 192.168.85.101
+--------v--------------------------------------------------------------------+
| VM（CentOS 7）Docker                                                         |
|  [Milvus]  :19530  向量检索主链路        [MongoDB] :27017  对话状态存储        |
|  [MinIO]   :9000   视频/课件/附件对象存储 [Neo4j]  :7687   知识图谱            |
+-----------------------------------------------------------------------------+
```

各组件职责一句话：

| 组件 | 位置 | 职责 |
|---|---|---|
| MySQL 8 | 宿主 3306（Windows 服务） | 业务主库（`edu` 库）；凭据在 .env `MYSQL_PASSWORD`（必填，无默认值） |
| 后端 uvicorn | 宿主 8000 | FastAPI 应用；**读 .env 的 DEBUG/ENV_NAME 形态原样启动**，脚本不做替换 |
| 前端 Next.js | 宿主 3000 | 生产形态 `build+start`（产物目录 `.next-prod`，缺失时 deploy 脚本自动 build） |
| Redis | 宿主 Docker Desktop 容器 `edu-redis-standalone`（6379） | 缓存/限流/会话/LLM 队列削峰 |
| Milvus | VM 192.168.85.101:19530 | 向量检索主链路 |
| MongoDB | VM 192.168.85.101:27017 | 对话状态存储 |
| MinIO | VM 192.168.85.101:9000 | 管理端视频/课件/习题附件对象存储 |
| Neo4j | VM 192.168.85.101:7687 | 知识图谱（P1/P4） |

> 注：MinIO/Neo4j 在 VM 上是 taskC3 实测事实（生产 .env 实际指向 192.168.85.101，
> lifespan 初始化 `'minio':'ok','neo4j':'ok'`，见 C3-e2e-report §2①）。

---

## 2. 前置清单

### 2.1 软件清单

| 软件 | 用途 | 备注 |
|---|---|---|
| MySQL 8 | 业务主库 | Windows 服务方式运行；空库不建表（见 §3 步骤③） |
| Node.js ≥ 18 | 部署脚本 / 前端 | deploy.mjs、check-demo.mjs 零新依赖（fetch/net/child_process 内置）；当前验证机 Node v24、next 16.3.0 |
| Python venv（3.11.x） | 后端运行时 | `edu-agent/pyproject.toml` 要求 `>=3.11,<3.12`；虚拟解释器路径固定为 `edu-agent\.venv\Scripts\python.exe`（deploy.mjs 硬编码查找）。依赖以 pyproject `[project].dependencies` 为真相源；venv 首次创建的安装命令历史未统一留存（**待验证**），常用 `python -m pip install -e .` |
| Docker Desktop | 宿主 Redis 容器 | 容器名 `edu-redis-standalone`；引擎未运行时 check-demo/deploy 会报「docker 引擎未运行」 |
| VMware + 虚拟机 | VM 内 Docker 跑 Milvus/Mongo/MinIO/Neo4j | VM 电源无法被脚本拉起（宿主 GUI 操作），脚本只探测 + 给指引 |

### 2.2 密钥准备（P5：密钥零入库，只写 .env，.env.example 仅占位）

```bash
# JWT_SECRET（强随机 32 字节 hex；DEBUG=false 下用默认值后端直接拒绝启动）
python -c "import secrets; print(secrets.token_hex(32))"

# API_TOKEN（随机值；同上硬校验）
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

| 密钥 | 来源 |
|---|---|
| `JWT_SECRET` | 上一条命令生成，粘进 .env |
| `API_TOKEN` | 上一条命令生成，粘进 .env |
| `MYSQL_PASSWORD` | 必填（无默认值），部署机 MySQL root（或专用账号）密码 |
| `LLM_API_KEY` | LLM 服务商控制台获取（DashScope / DeepSeek / 火山 Ark），只写 .env。`.env.example` 生产模板默认指向 `LLM_BASE_URL=https://api.deepseek.com`（模型 deepseek-v4-flash） |
| `NEO4J_PASSWORD` | 禁默认密码 `edu_neo4j_pwd_2026`；VM 内 Neo4j 容器 `NEO4J_AUTH` 与 .env 必须同步改（见 §4 已知项） |
| `MINIO_ACCESS_KEY/SECRET_KEY` | 生产勿用默认 `minioadmin/minioadmin` |

---

## 3. 部署步骤

### ① checkout

克隆仓库，保证 `edu-agent/` 与 `edu-frontend/` 为**工作区同级目录**（deploy.mjs 按此相对关系定位前端）。
首次部署需准备后端 venv（见 §2.1）与前端 `npm install`（node_modules 就绪）。

### ② 配置 .env（按 .env.example 生产段）

```bash
cd edu-agent
copy .env.example .env    # 然后编辑 .env
```

生产段最小必改项：

| 键 | 生产值 | 说明 |
|---|---|---|
| `DEBUG` | `false` | 生产硬要求；true 存在虚拟管理员后门（P1-8） |
| `ENV_NAME` | `prod` | P1-8 门禁判据：DEBUG=true 且 ENV_NAME≠local → 拒绝启动 |
| `JWT_SECRET` / `API_TOKEN` | §2.2 生成的强随机值 | DEBUG=false 下默认值直接拒绝启动（`_security_guard`） |
| `MYSQL_PASSWORD` | 部署机真实密码 | 必填无默认 |
| `LLM_API_KEY` | 服务商 key | 必填无默认 |
| `CORS_ORIGINS` | 建议留空或显式双源 | **必须同时含 `http://localhost:3000` 与 `http://127.0.0.1:3000` 双源**（C3 实证，详见 §4 已知项） |

其余 220 键逐键说明见 `.ai-hub/plans/deploy-config-checklist.md`（含每键默认值/必填性/生产值指引），本 README 不重复。

### ③ 数据库初始化（edu 库）

- **后端不会自动建库建表**：`app/database.py init_mysql()` 仅创建连接池（已核实源码）。
- 因此 `edu` 库与其 106 张业务表、种子数据（含测试账号）来自**快照恢复**：

```bash
# 方式一（推荐，有清单+恢复演练背书）：20260816_task00 全库 dump
#   dump 内含 CREATE DATABASE IF NOT EXISTS edu + USE edu，直接执行即可
mysql -uroot -p < deploy/backups/20260816_task00/edu_full_dump.sql
# 验证（期望 106 表）
mysql -uroot -p -e "SELECT COUNT(*) AS table_count FROM information_schema.tables WHERE table_schema='edu'"

# 方式二：更新快照 deploy/backups/edu_snapshot_20260913_preR0.sql（997MB，无清单文件；
#   恢复命令同上通用方式，是否含建库语句未核验——待验证）
```

- 快照背景见 `deploy/backups/20260816_task00/BACKUP_MANIFEST.md`（106 表、恢复演练 85.8s 关键表行数一致）。
- 测试账号随快照带入（§4 登录失败项）。

### ④ 一键拉起

```bash
# 在 edu-agent/ 目录下
node scripts\deploy\deploy.mjs start
```

start 依序执行：前置检查（MySQL/VM/Redis 探测，**只报告不阻塞**）→ 后端 uvicorn（读 .env 形态原样，
等 `/health` 就绪，超时 120s——CUDA 模型加载可能较慢）→ 前端 build+start（`.next-prod/BUILD_ID` 缺失时
自动 `npx next build`，约 1-2 分钟）→ 自动跑 check-demo 断言，exit code 透传。
幂等：端口已在监听则跳过对应服务并提示 PID。

### ⑤ 验收：check-demo 8/8

```bash
node scripts\check-demo.mjs        # 或 node scripts\deploy\deploy.mjs status
```

期望末行：`汇总: 绿 8/8 —— 演示环境就绪`。红项按 §4 故障对照表处置后重跑。

---

## 4. 故障对照表（逐项对齐 check-demo 8 项 + 已知项）

check-demo 检查项与序号一一对应；每行处置与脚本 FAIL 时输出的指引一致。

| # | 检查项 | 典型现象 | 处置 |
|---|---|---|---|
| ① | Milvus 连通 192.168.85.101:19530 | 连接超时/主机不可达 | 开启 VMware 虚拟机：`vmrun start "E:\tt\CentOS 7 64 位 的克隆 docker\CentOS 7 64 位 的克隆 docker.vmx" nogui`，等 60s；进 VM `docker ps` 确认 milvus 容器在跑。⚠ 该 vmx 路径是 `check-demo.mjs` 头部「配置段」的登记值，**脚本自检发现路径不存在会提示**——换机器后按实际 VM 路径修改 `VMX_PATH` |
| ② | Redis（`docker exec edu-redis-standalone redis-cli ping` 期望 PONG） | docker 引擎未运行 / 容器停 | 先启动 Docker Desktop，再 `docker start edu-redis-standalone` |
| ③ | MongoDB 连通 192.168.85.101:27017 | 同 ① | 同 ①（确认 mongo 容器在跑） |
| ④ | 后端 8000 `/health`（status=ok） | /health 不可达，或后端进程起后自杀 | 见下方「8000 拒启三分支」；日志 `logs/deploy-backend.log` |
| ⑤ | 前端 3000 `/login-register.html` | 拒绝连接 / 非 200 | `node scripts\deploy\deploy.mjs start`（会自动 build+start）；build 失败看 `logs/deploy-frontend-build.log` |
| ⑥ | 登录链路（admin+student 各 login + /api/auth/me） | 401 / 账号不存在 | 先过 ④ 后端；仍失败 = edu 库无种子数据，按 §3 步骤③ 恢复快照（测试账号见下表） |
| ⑦ | 关键页 200 × 8（login-register / courses / course-detail?id=1 / dashboard / learning / admin-dashboard / admin-mcp / admin-rag-upload） | 某些页非 200 | 前端未就绪先修 ⑤；页面能开但数据全空/console 报错 → 见「已知项 A：CORS 双源」 |
| ⑧ | advisory：DEBUG 虚拟管理员探测（无 token GET /api/admin/users） | 无 token 竟返回 200 有数据 | DEBUG=true 后门！上线前必须 `DEBUG=false` 并重启后端（settings.DEBUG=false） |

**测试账号（快照内种子，check-demo ⑥ 使用）**：

| 角色 | 账号 | 密码 |
|---|---|---|
| admin | `adm02test` | `Test@123456` |
| manager | `mgr01test` | `Test@123456` |
| student | `user000001` | `Test@123456` |

**8000 拒启三分支（生产形态 DEBUG=false 下启动即失败，全在 `logs/deploy-backend.log` 可见 ValueError/异常）**：

| 分支 | 触发条件 | 处置 |
|---|---|---|
| 密钥默认值（`_security_guard`） | DEBUG=false 且 JWT_SECRET=`dev-secret-key-change-in-production`/空，或 API_TOKEN=`edu-agent-dev-token`/空 | 按 §2.2 生成强随机值写入 .env，重启 |
| ENV_NAME+DEBUG 组合（P1-8 门禁） | DEBUG=true 且 ENV_NAME≠local（prod/staging/dev/qa 等） | 组合只有两种合法形态：dev=`DEBUG=true + ENV_NAME=local`；生产=`DEBUG=false + ENV_NAME=prod`。按此改 .env |
| 存储不可达（lifespan 硬校验） | DEBUG=false 下 MySQL/Milvus/MongoDB/MinIO/Neo4j/Redis **任一**连不通 | 逐个修 ①②③ 与 MinIO/Neo4j 连通性后重启（DEBUG=true 时仅降级不拒启，生产 false 必拒） |

**已知项（check-demo 8 项之外，C3 实测发现）**：

- **A. CORS 生产双源**（commit `c208020`）：DEBUG 态 CORS=`*` 从未暴露此问题；生产形态下若 CORS 白名单
  只有 `http://localhost:3000`，用户以 `http://127.0.0.1:3000` 访问前端时所有 API 被预检拦截
  （C3 首轮实测 8 页中 6 页 console 报错、admin-dashboard 守卫跳登录）。处置：`.env` 设
  `CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000`（或留空走 `app/main.py _cors_origins()`
  生产回退双源——回退已含双源）。
- **B. Neo4j 密码核对**（deploy-config-checklist §Neo4j 已标注）：`NEO4J_PASSWORD` 禁默认值
  `edu_neo4j_pwd_2026`；改密码时 VM 内 Neo4j 容器启动参数 `NEO4J_AUTH` 与 .env **必须同步改**，
  否则 lifespan 初始化 neo4j 失败 → 生产形态拒启。
- **C. 非阻断告警（无需处理）**：BGE-M3 本地模型目录（`C:/ai-models/bge-m3`）不存在 → 自动云端兜底；
  reranker sidecar(8601) 未运行 → 进程内/规则兜底。均为 C3 实测的非阻断降级。注意查询/入库 embedding
  必须同通道（EMBED_BACKEND 同值），不可一半 cuda 一半 cloud。

---

## 5. 日常运维

### 三命令

```bash
node scripts\deploy\deploy.mjs start    # 前置检查→后端→前端→check-demo 8/8 断言（幂等）
node scripts\deploy\deploy.mjs stop     # 按端口清 8000/3000（netstat→PID→taskkill /F /T）
node scripts\deploy\deploy.mjs stop --all   # 同上，附加 Redis 容器处置提示（容器本身不停）
node scripts\deploy\deploy.mjs status   # 透传 check-demo.mjs，exit code 一致
```

- `stop` **不停 Redis 容器**（缓存/限流/会话依赖它，一般无需停止）；确需停止：`docker stop edu-redis-standalone`，恢复 `docker start edu-redis-standalone`。
- PID 记录：`logs/deploy.pids.json`（stop 会清理陈旧记录）。
- 幂等提示：start 时若 3000 已被监听会跳过并提示「可能是 dev 形态，如需生产形态请先 stop」。

### 日志位置（均为追加式 append）

| 文件 | 内容 |
|---|---|
| `edu-agent/logs/deploy-backend.log` | 后端 uvicorn stdout/stderr（含启动形态 JSON 段、lifespan 存储初始化结果） |
| `edu-agent/logs/deploy-frontend.log` | 前端 next start 输出 |
| `edu-agent/logs/deploy-frontend-build.log` | next build 输出（产物缺失时自动 build 的落点） |

应用自身日志由 .env `LOG_DIR=./logs`、`LOG_ROTATION="100 MB"`、`LOG_RETENTION="7 days"` 控制（自动轮转）。

### 巡检建议

1. **每次演示/交付前**：`node scripts\deploy\deploy.mjs status` → 期望 8/8 全绿（约 2 秒）。
2. **每日**：Docker Desktop 在跑、`docker exec edu-redis-standalone redis-cli ping` = PONG；VM 在线（①③ 探测绿）。
3. **每周**：查看 `logs/` 磁盘占用（轮转/保留由 .env 控制）；`deploy-frontend-build.log` 是否有异常 build 重试。
4. Redis 容器未配置开机自启（是否配 restart 策略**待验证**），宿主机重启后需手动 `docker start edu-redis-standalone`。

### 数据安全红线

1. **禁 DB 直写**：一切业务数据变更必须走后端 API 或既有脚本，禁止手工 UPDATE/DELETE 业务表。
2. **操作前快照**：任何批量操作/升级/数据订正前，先做 MySQL 快照，落 `deploy/backups/`（该目录已进 .gitignore，快照不进 git）：

```bash
mysqldump -uroot -p --routines --triggers --single-transaction --set-gtid-purged=OFF edu > deploy/backups/edu_snapshot_<日期说明>.sql
```

3. **恢复**：按 §3 步骤③（全库 dump 含建库语句；恢复后用 information_schema 计数验证 106 表）。

---

## 6. 边界声明

- 本部署包 = **本机同构部署**（Windows 主机 + VMware VM Docker 一键拉起），验收口径 =
  干净进程环境一条命令拉起 + check-demo 8/8 + 核心页抽验；不含公网暴露/HTTPS/域名/Nginx 反代。
- 公网/HTTPS/容器化/Linux 归 **C 阶段全量**；容器化路线资产（docker compose + 前后端 Dockerfile）见下方附录。
- 脚本能力边界：VM 电源、Docker Desktop、Redis 容器的拉起**不在 start 脚本能力内**（脚本只探测 + 给指引）；
  .env 形态归用户所有，脚本读原样报告、不做替换。

---

## 附录：容器化部署（docker compose，C 阶段全量路线）

> 以下为原 deploy/README.md 的容器化资产说明，原样保留（与上文本机同构 runbook 相互独立）。

### 组成

| 文件 | 作用 |
|------|------|
| `docker-compose.yml` | 一键编排：MySQL + MinIO + etcd + Milvus + MongoDB + Neo4j + 后端 + 前端，含 healthcheck |
| `backend.Dockerfile` | 后端多阶段镜像（deps 缓存 + 非 root appuser + 健康检查） |
| `frontend.Dockerfile` | 前端 Next.js standalone 镜像（非 root nextjs） |
| （根目录）`.dockerignore` | 构建上下文排除（密钥/env/测试不进镜像） |

### 快速开始

```bash
# 1. 生产环境变量
cp edu-agent/.env.production.example .env.production
#    编辑 JWT_SECRET / API_TOKEN / MYSQL_PASSWORD / NEO4J_PASSWORD / LLM_API_KEY 等必填项

# 2. 启动（首次会构建镜像）
docker compose -f deploy/docker-compose.yml --env-file .env.production up -d --build

# 3. 状态
docker compose -f deploy/docker-compose.yml ps

# 4. 验证
curl -s http://localhost:8000/health
curl -s http://localhost:8000/health/detail   # 各存储 ok
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000   # 前端 200
```

### 服务器部署时前端指向后端

`NEXT_PUBLIC_*` 在 build 时内联，需用 build arg 注入：

```bash
NEXT_PUBLIC_API_BASE_URL=http://<服务器IP>:8000 \
  docker compose -f deploy/docker-compose.yml --env-file .env.production up -d --build
```

### 运维

```bash
# 查看日志
docker compose -f deploy/docker-compose.yml logs -f backend

# 重启单个服务
docker compose -f deploy/docker-compose.yml restart backend

# 停止
docker compose -f deploy/docker-compose.yml down

# 停止并删数据卷（慎用，会清库）
docker compose -f deploy/docker-compose.yml down -v
```

### 注意事项

- **生产密钥**：`JWT_SECRET`/`API_TOKEN` 用强随机值，否则后端 fail-fast 拒绝启动（P0-1 安全护栏）。
- **DEBUG**：compose 强制 `DEBUG=false`。
- **数据库迁移**：当前无 Alembic，表由后端 lifespan 启动时创建；首次启动后需导入种子数据（见 `部署上线指南.md` P2 路线图）。
- **MinIO**：`MINIO_ACCESS_KEY/SECRET_KEY` 生产勿用默认 `minioadmin/minioadmin`。

### DEBUG=False 部署前必跑检查单（task123，出包前必跑）

> 目的：关闭鉴权降级后门（`app/auth/dependencies.py` 中 `settings.DEBUG` 触发的虚拟管理员/`X-Force-Role` 后门），确保生产无匿名越权。以下任一不通过即阻断出包。

```bash
# 0) .env / .env.production 核对（config.py Settings）
#    - DEBUG 必须为 false（生产缺省即 false；确认未被显式写成 true）
#    - JWT_SECRET 必须是强随机值（非默认 dev-secret-key-change-in-production）
#      （config.py 582-606 已有 fail-fast：DEBUG=False 且 JWT_SECRET 为公开默认值 → 拒绝启动）

# 1) 无 token 访问 /api/users/me → 必须 401（禁虚拟管理员 / DEBUG_超级管理员）
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/users/me
#    期望：401

# 2) 伪造/垃圾 token → 必须 401
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer garbage.invalid.token" \
  http://localhost:8000/api/users/me
#    期望：401

# 3) X-Force-Role 头无效（DEBUG 后门手势在生产无效）→ 仍 401
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "X-Force-Role: admin" http://localhost:8000/api/users/me
#    期望：401（X-Force-* 后门仅 DEBUG=true 生效）
#    ⚠ 实证登记（task123）：/api/metrics/cache-context-dashboard 已 require_role([ADMIN,MANAGER]) 鉴权；
#      裸 /metrics（Prometheus 抓取端点）当前无 Depends 守护——若 task113 预期该端点也鉴权，需编排者确认
#      并补守卫（见 test-reports/task123-completion-report.md 自检发现）。

# 4) /api/metrics 鉴权生效（依赖 task113）：无 token 返回 401；仅 ADMIN/MANAGER 可读
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/metrics/cache-context-dashboard
#    期望：401

# 5) 死链扫描（W1-批判3 承接，C-17，L4/里程碑回归固定条目）：
#    跑通静态死链门禁 = 无死链 + 无伪孤立页（快照入 test-reports/critique-W1C3-completion-report.md）
#    已知盲区：变量拼接跳转（"/x.html?"+id）非静态可判，社区/详情 ID 动态页需人工走查。
node test-reports/scan-deadlinks.mjs
#    期望：最后一行「=== 死链总数: 0 ===」
```

### venv 依赖清单（task61 补装，出包前核对）

- **额外生产依赖**：`pdfplumber==0.11.10`（task61 契约⑥ PDF 解析真实成立；图表/PDF 导入链路依赖）。需在后端镜像 `backend.Dockerfile` 的依赖安装段与 `requirements*.txt`（如适用）中同步声明，勿遗漏。
