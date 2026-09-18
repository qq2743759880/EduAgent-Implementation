# EduAgent 部署 README（运维 runbook 第一章 · taskC4）

> 面向读者：**从未接触过本项目的新运维/新人**。目标：照本文从零操作，把 EduAgent 在与本机同构的环境
> （Windows 主机 + VMware 虚拟机 Docker）里一键拉起，并通过 check-demo 9/9 验收（与 taskC5 同一验收态）。
>
> 事实来源（先读后写，本文一切命令/路径/行为与下列交付物一致）：
> - 一键脚本：`edu-agent/scripts/deploy/deploy.mjs`（taskC1）
> - 生产配置模板：`edu-agent/.env.example`（taskC0，未注释键 37 个，2026-09-15 实测）；配置项清单 `.ai-hub/plans/deploy-config-checklist.md`
> - 生产形态端到端实测：`edu-agent/test-reports/C3-e2e-report.md`（taskC3）
> - 检查单：`edu-agent/scripts/check-demo.mjs`（9 项检查，FAIL 时逐项给一句话处置指引）
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

### 1.1 Redis 部署位置（W-NEXT-REDIS-FIX，2026-09-17 闭环）

> 本节由 W-NEXT-REDIS-FIX 任务新增（独立闭环），用于消除**端口/容器名漂移**导致的部署脱节盲区。
> 任务起源：本机盲测发现 `edu-redis-standalone` 容器已被 `prisma-ai-redis-container-1` 替代，
> 宿主端口从 `6379` 漂移到 `6377`（容器内仍是 `6379`），而 `.env` 此前**没有显式 `REDIS_URL`**——
> 后端走 `app/config.py:79` 默认 `redis://localhost:6379/0`，与实际容器端口脱节，新人接手必踩。

| 项 | 当前值 | 历史值（已弃用） | 备注 |
|---|---|---|---|
| 容器名 | `prisma-ai-redis-container-1` | `edu-redis-standalone` | 旧容器名已停用，**不要**回退该命名 |
| 宿主端口 | `6377` | `6379` | Docker Desktop 端口映射 `0.0.0.0:6377->6379/tcp` |
| 容器内端口 | `6379` | `6379` | 未变（redis 默认端口） |
| `.env` 显式声明 | `REDIS_URL=redis://127.0.0.1:6377/0` + `REDIS_PORT=6377` | 无（隐式走 `config.py` 默认 `localhost:6379/0`） | `localhost` 已归一为 `127.0.0.1`（`config.py _normalize_loopback`） |

**对账/防漂移**（强制每次发版前跑）：

```bash
# 1) 看实际容器 + 端口
docker ps --filter "name=redis" --format "table {{.Names}}\t{{.Ports}}\t{{.Status}}"
#   期望：prisma-ai-redis-container-1  0.0.0.0:6377->6379/tcp  Up … (healthy)

# 2) 跑自检脚本对账 .env 与 docker 端口
python edu-agent/scripts/eval/redis_port_check.py
#   期望：末行 [PORT_CHECK] env_port=6377 docker_port=6377 status=PASS
#   不一致时 WARN（不阻断，但提示需改 .env）

# 3) 单测
pytest edu-agent/tests/test_redis_port_check.py -v
#   期望：≥1 例 PASS（对账逻辑回归保护）

# 4) check-demo ⑮ 门（演示前必跑）
node edu-agent/scripts/check-demo.mjs
#   期望：⑮ Redis 部署对账 PASS（实际 redis port 与 .env 一致）
```

**为什么 .env 必须显式 REDIS_URL 而不只靠 config.py 默认？**

1. `app/config.py:79` 默认是 `redis://localhost:6379/0`——这条历史默认值锁死了「Redis 一定在 6379」的隐含假设，
   漂移后**没有**任何代码层告警，仅在 lifespan `init_redis()` `ping()` 失败时才暴露（彼时 8000 已拒启/降级）。
2. 显式 `REDIS_URL` 是**单一事实源**（single source of truth）：配置漂移时运维/新人第一时间看到正确端口，
   避免再次出现「文档/代码/实际」三方不一致。
3. `REDIS_PORT` 是冗余键——与 `REDIS_URL` 解耦的明示端口，便于 `redis_port_check.py` 单独断言
   （不必正则解析 URL）。

**盲测/部署脱节历史（教训登记）**：

| 日期 | 事件 | 当时应对 | 根因 |
|---|---|---|---|
| ≤2026-09-15 | `edu-redis-standalone` 在跑，端口 6379，文档/代码/.env 三方一致 | 一切正常 | — |
| 2026-09-15 → 2026-09-17 | 容器重建为 `prisma-ai-redis-container-1`，端口漂到 6377（盲测期间发生） | 未登记文档/.env | **部署脱节**：容器/端口变更无审计记录 |
| 2026-09-17 W-NEXT-REDIS-FIX | `.env` 显式 `REDIS_URL=redis://127.0.0.1:6377/0` + `REDIS_PORT=6377`；本文新增 + `redis_port_check.py` + check-demo ⑮ 门 | 本任务闭环 | 见上「对账/防漂移」段 |

> **防漂移状态（2026-09-18 更新）**：
> - check-demo.mjs ② 已由 W-NEXT-PROBE-001 改为「按 .env REDIS_PORT 宿主端口反查容器名」（不再硬编码旧名）；
>   deploy.mjs 前置检查的 Redis 探测亦已在 W-NEXT-DEPLOY-HARD-001 对齐同款反查（本机实测 PONG=prisma-ai-redis-container-1:6377）。
> - 若再次发生容器/端口变更，请同步：(a) `edu-agent/.env` `REDIS_URL`/`REDIS_PORT` 两键；(b) 本节表格；
>   (c) `edu-agent/scripts/eval/redis_port_check.py` 期望值；(d) `test-reports/` 留一份变更说明。

---

## 2. 前置清单

### 2.1 软件清单

| 软件 | 用途 | 备注 |
|---|---|---|
| MySQL 8 | 业务主库 | Windows 服务方式运行；空库不建表（见 §3 步骤③） |
| Node.js ≥ 18 | 部署脚本 / 前端 | deploy.mjs、check-demo.mjs 零新依赖（fetch/net/child_process 内置）；当前验证机 Node v24、next 16.3.0 |
| Python venv（3.11.x） | 后端运行时 | `edu-agent/pyproject.toml` 要求 `>=3.11,<3.12`；虚拟解释器路径固定为 `edu-agent\.venv\Scripts\python.exe`（deploy.mjs 硬编码查找）。依赖以 pyproject `[project].dependencies` 为真相源；venv 首次创建安装命令（C5-O2 已实证收口，2026-09-13）：`python -m venv .venv` 后在 `edu-agent/` 下执行 `python -m pip install -e .`（pyproject `[build-system]` = hatchling，pip 按 PEP 517 自动拉取构建后端；当前 venv 实测为 editable 安装——site-packages 含 `_editable_impl_edu_agent.pth` + `edu_agent-0.3.0.dist-info`，`pip show edu-agent` 正常） |
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

> ⚠ **已有 .env 判别（执行前必查，配置文件不可恢复风险）**
>
> 若 `edu-agent/.env` **已存在**（例如本机正在运行的 dev 形态），**先备份再改**：
>
> ```bash
> cd edu-agent
> cp .env .env.bak    # Windows: copy .env .env.bak
> ```
>
> 两条硬事实：① `.env` 已被 `.gitignore` 忽略，**覆盖后无法从 git 恢复**；② `.env.example` 是
> **生产模板**（`DEBUG=false` + `ENV_NAME=prod`，6 个必填密钥 `MYSQL_PASSWORD`/`NEO4J_PASSWORD`/
> `MINIO_SECRET_KEY`/`LLM_API_KEY`/`JWT_SECRET`/`API_TOKEN` 全为 `REPLACE_ME_*` 占位），直接
> `copy .env.example .env` 覆盖现有 dev `.env` 后，后端会因 `_security_guard`（密钥默认值/占位值）
> fail-fast **拒绝启动**。只有**全新机器、尚无 .env** 时才能直接 copy。

```bash
cd edu-agent
copy .env.example .env    # ⚠ 仅当 .env 不存在时用；已存在先按上方备份，再逐键改而非整文件覆盖
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

其余未注释键逐键说明见 `.ai-hub/plans/deploy-config-checklist.md`（含每键默认值/必填性/生产值指引，`.env.example` 未注释键 37 个，2026-09-15 实测），本 README 不重复。

#### 平台自有 skill 根配置：`EDUAGENT_PLATFORM_SKILL_ROOTS`（WNEXT10/11）

> 默认留空即**安全缺省**，通常生产无需配置。行为对照：

| 形态 | 配置 | `skill_node`（平台 agent 系统提示 skill 段）行为 |
|---|---|---|
| **不配**（默认空） | `EDUAGENT_PLATFORM_SKILL_ROOTS=` | 只注入 `platform_capability_block()` 实物能力清单（源自 `permission_gate.TOOL_CLASS_MAP`，8 个真实工具）；**不**注入任何开发机 skill（`list_directory`/`read_file` 等 dev-host 工具绝不出现），也不注入平台自有 skill |
| **配**（平台有自维护 skill 根） | 指向该目录（`os.pathsep` 分隔多根） | 在实物能力清单之外，额外把这批平台自有 SKILL.md 的 body 注入 `skill_context`（供 agent 调取平台私有 skill） |

- 判定口径（`app/ai/skills/registry.py`）：只扫描本变量指向的根；`dev_default()` 仍扫开发机 AI-Hub（仅供离线/迁移/排查），两者**完全隔离**。
- 安全边界：**未配置绝不可能引入开发机 skill**（WNEXT10 F5-b 修复的正向保障）；误把该变量指向开发机 `D:\\.ai-hub\\skills` 会重新把 dev-host 工具泄漏进平台链路——**不要**在生产指向开发机库。
- 本字段与工具实物能力无关：无论配或不配，平台能力清单始终由 `TOOL_CLASS_MAP` 注入，不丢能力表述。

### ③ 数据库初始化（edu 库）

> ⚠ **已有库判别（执行前必查，P1 数据损失风险）**
>
> **下面两条恢复命令都是破坏性覆盖导入**：方式一的全库 dump 内含 **106 条 `DROP TABLE`**，在任何**已存在 `edu` 库**的机器上执行，都会先清空现库表再回滚到快照时刻。本仓库实测 `edu` 库当前 104 表，而 08-16 dump 为 106 表，**二者已双向分叉**：
>
> - **dump 独有 11 张**（`admin_*`×7、`curriculum_*`×4）——现有库执行后会被重建/覆盖；
> - **现库独有 9 张**（`user_memory*`、`hitl_approval`、`task_execution`、`course_review`、`knowledge_import_task` 等）——现有库执行后**整表丢失**，且现库 2026-09-13 以来的真实订单数据一并回滚。
>
> （分叉表完整清单见 `test-reports/onboarding-fresh-report.md` §3③。）
>
> **执行前必查（非空即停）：**
>
> ```bash
> mysql -uroot -p -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='edu'"
> ```
>
> **结果 `≠0` 即停**：说明这台机已不是干净空库，照做 = 破坏性覆盖（清 11 张新表 + 数据回滚 1 个月）。此时切换到「维护快照」或换一台干净空库机器部署；确认必须重置时，先按 §5 数据安全红线做完整 `mysqldump` 快照备份后再执行。

- **后端不会自动建库建表**：`app/database.py init_mysql()` 仅创建连接池（已核实源码）。
- 因此 `edu` 库与其 106 张业务表、种子数据（含测试账号）来自**快照恢复**（仅适用于全新空库机器）：

```bash
# 方式一（推荐，有清单+恢复演练背书）：20260816_task00 全库 dump
#   dump 内含 CREATE DATABASE IF NOT EXISTS edu + USE edu，直接执行即可
mysql -uroot -p < deploy/backups/20260816_task00/edu_full_dump.sql
# 验证（期望 106 表）
mysql -uroot -p -e "SELECT COUNT(*) AS table_count FROM information_schema.tables WHERE table_schema='edu'"

# 方式二：更新快照 deploy/backups/edu_snapshot_20260913_preR0.sql（997MB，无清单文件；
#   建库语句已核验（C5-O2，2026-09-13）：该快照为单库模式 dump，全文件 **不含** CREATE DATABASE / USE
#   语句（grep 全文 0 匹配，区别于方式一）——必须先建库再导入）
mysql -uroot -p -e "CREATE DATABASE IF NOT EXISTS edu DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
mysql -uroot -p edu < deploy/backups/edu_snapshot_20260913_preR0.sql
# 验证（期望 106 表，同方式一）
```

- 快照背景见 `deploy/backups/20260816_task00/BACKUP_MANIFEST.md`（106 表、恢复演练 85.8s 关键表行数一致）。
- 测试账号随快照带入（§4 登录失败项）。

### ④ 一键拉起

```bash
# 在 edu-agent/ 目录下
node scripts\deploy\deploy.mjs start
# 生产出包（推荐）：start 前先跑部署环境门（对 edu-agent/.env；exit!=0 中止，不拉起任何服务），
# 且 check-demo 断言段以 --prod-gate 严格模式跑（⑧ 开发态 WARN 升级红）
node scripts\deploy\deploy.mjs start --prod-gate
# 前端端口被占需 failover 时（start/stop/status/stop-prod-and-restart-dev 全链路生效，并透传 check-demo）
node scripts\deploy\deploy.mjs start --frontend-port 3001
```

start 依序执行：[--prod-gate 时先跑部署环境门 `scripts/eval/deploy_env_gate.mjs`（W-NEXT-DEPLOY-HARD-001，
承接 W-NEXT-CHECKDEMO-PROD-001 P0-1；`--env <文件>` 可指定 env 路径，默认 `edu-agent/.env`）] →
前置检查（MySQL/VM/Redis 探测，**只报告不阻塞**）→ 后端 uvicorn（读 .env 形态原样，等 `/health` 就绪，
超时 120s——CUDA 模型加载可能较慢）→ 前端 build+start（`.next-prod/BUILD_ID` 缺失时自动 `npx next build`，
约 1-2 分钟）→ 自动跑 check-demo 断言（透传 `--frontend-port`），exit code 透传。
幂等：端口已在监听则跳过对应服务并提示 PID。

> 部署环境门语义（`deploy_env_gate.mjs`，只调用不改）：`DEBUG=false`（或缺省）→ exit 0 放行；
> `DEBUG=true`（无论 ENV_NAME 是否缺省/local）→ exit 1 拒绝出包（部署门从严，P0-2：生产忘设
> ENV_NAME 时 DEBUG=true 即真后门）。本地开发日常把关用 check-demo ⑧（dev 态 WARN 不阻断）；
> 门不通过时 start 输出明确处置指引后以 exit 2 中止，**任何服务都不会被拉起**。

### ⑤ 验收：check-demo 9/9

```bash
node scripts\check-demo.mjs        # 或 node scripts\deploy\deploy.mjs status
```

> `deploy.mjs status`（W-NEXT-DEPLOY-HARD-001）在透传 check-demo 之前，先输出**前端 dev/prod 形态判别**
> （复用 check-demo ⑤ 同款 `_buildManifest` 探针：200=dev 形态，**404=生产 build 判据**）+ 后端
> `/health` 快探，并打一行机器可读 `[STATUS] {...}` JSON；随后照旧透传 check-demo（`--frontend-port`/
> `--prod-gate` 跟随透传，exit code 一致）。只想快速看形态时，看开头几行即可 Ctrl-C。

期望末行：`汇总: 绿 21/21 —— 演示环境就绪`（生产段 .env＝`DEBUG=false`+`ENV_NAME=prod` 下含 ⑧；若沿用 dev 形态 `DEBUG=true`：ENV_NAME 缺省/local → ⑧ WARN 不阻断（本机开发态）；ENV_NAME 显式非 local（prod/staging/dev/qa 等，P1-8 同口径）→ ⑧ 直接红（两级判据，W-NEXT-CHECKDEMO-PROD-001；`--prod-gate` 旗标可把 WARN 也升级为红）。红项按 §4 故障对照表处置后重跑。

---

## 4. 故障对照表（逐项对齐 check-demo 9 项 + 已知项）

check-demo 检查项与序号一一对应；每行「处置」**逐字引用** `check-demo.mjs` FAIL 时打印的 `-> …` 指引（`FIX` 表 / 各 `check()` 的 `__fix`，含原文半角标点），其前后按本机实测补充前置判断（⑥ 限流先等 60s、⑤ 形态判别的生产形态验法等）。⑤⑦⑨ 共用前端指引 `FIX.frontend`。

| # | 检查项 | 典型现象 | 处置 |
|---|---|---|---|
| ① | Milvus 连通 192.168.85.101:19530 | 连接超时/主机不可达 | `开启 VMware 虚拟机: vmrun start "E:\tt\CentOS 7 64 位 的克隆 docker\CentOS 7 64 位 的克隆 docker.vmx" nogui,等 60s`；进 VM `docker ps` 确认 milvus 容器在跑。⚠ 该 vmx 路径即 `check-demo.mjs` 头部「配置段」的 `VMX_PATH`（路径不存在时脚本自动追加「配置的 vmx 路径不存在」提示）——换机器后按实际 VM 路径改该常量 |
| ② | Redis（`docker exec edu-redis-standalone redis-cli ping` 期望 PONG） | docker 引擎未运行 / 容器停 | 脚本原文＝`docker start edu-redis-standalone(若 docker 引擎未运行,先启动 Docker Desktop)` |
| ③ | MongoDB 连通 192.168.85.101:27017 | 同 ① | 同 ①（脚本给同一条 `vmrun start …` 指引，确认 mongo 容器在跑） |
| ④ | 后端 8000 `/health`（status=ok） | `fetch failed`（后端未起）/ status≠ok | `cd edu-agent && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`；启动即自杀见下方「8000 拒启三分支」，日志 `logs/deploy-backend.log` |
| ⑤ | 前端 3000 `/login-register.html`（+生产形态判别） | 拒绝连接 / 非 200；或 dev 形态（`_buildManifest` dev 探针 200） | 脚本原文＝`cd edu-frontend && node node_modules/next/dist/bin/next dev -p 3000(验生产形态:deploy.mjs stop 后 start,先 build 再起)`。生产形态优先 `node scripts\deploy\deploy.mjs start`（自动 build+start `.next-prod`）；build 失败看 `logs/deploy-frontend-build.log`。⚠ dev 形态为 **WARN**（不阻断 exit），提示「生产形态未验收」 |
| ⑥ | 登录链路（admin+student 各 login + /api/auth/me） | 401 / `fetch failed` / 账号不存在 | **先等 60 秒重跑**（登录限流 42900/60s 窗口，密集连跑必红，12-25ms 快失败即限流特征）。脚本原文指引：`先过 ④ 后端: cd edu-agent && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000(若账号失效查 DB 种子)`。**勿直接恢复快照**——§3③ 仅适用全新空库，本机非空库执行＝破坏性覆盖＋数据回滚。耗时：约 1.0-1.3s，冷启动/限流重试时 6-10s（整轮巡检见 §5） |
| ⑦ | 关键页 200 × 8（login-register / courses / course-detail?id=1 / dashboard / learning / admin-dashboard / admin-mcp / admin-rag-upload） | 某些页非 200 | 脚本原文＝`cd edu-frontend && node node_modules/next/dist/bin/next dev -p 3000`（`FIX.frontend`，与 ⑦⑨ 同源；⑤ 另带生产形态判别后缀）；页面能开但数据全空/console 报错 → 见「已知项 A：CORS 双源」 |
| ⑧ | advisory：DEBUG 虚拟管理员探测（无 token GET /api/users/me，两级判据 + `--prod-gate`，W-NEXT-CHECKDEMO-PROD-001） | 无 token 返回 200；或 DEBUG=true 且 ENV_NAME 显式非 local | `DEBUG=true 虚拟管理员漏洞,上线前必须 False(settings.DEBUG=false 并重启后端);ENV_NAME 显式非 local 时属生产类环境直接禁止部署(P1-8 两级判据)`。四分支（与后端 P1-8 `_debug_env_gate` 同口径：ENV_NAME strip+lower ∈ {"", "local"}＝本机开发态）：**A** 被 401/403 拒绝 → PASS（DEBUG=true 时文案不再自称「安全」）；**B** 有数据 + DEBUG=true + ENV_NAME 显式非 local → **红，阻断 exit 1**（生产类环境 DEBUG=true 真后门）；**C** 有数据 + DEBUG=true + ENV_NAME 缺省/local → WARN 不阻断（本机 dev 态；`--prod-gate` 旗标下升级为红）；**D** 有数据 + DEBUG≠true → **红，阻断 exit 1**（真后门） |
| ⑨ | 抽验页 200 `/admin-users-refine-proto.html`（C5-D2 扩清单） | 页面 404 | 确认 `public/admin-users-refine-proto.html` 存在；前端未就绪先修 ⑤（脚本原文＝`FIX.frontend`：`cd edu-frontend && node node_modules/next/dist/bin/next dev -p 3000`） |

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

**已知项（check-demo 9 项之外，C3 实测发现）**：

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

### 四命令与旗标（三命令 + W-NEXT-DEPLOY-HARD-001 扩展）

```bash
node scripts\deploy\deploy.mjs start    # [--prod-gate:部署环境门]→前置检查→后端→前端→check-demo 断言（幂等）
node scripts\deploy\deploy.mjs start --prod-gate            # 生产出包形态：门不过即中止（不拉起任何服务）
node scripts\deploy\deploy.mjs start --prod-gate --env <文件>  # 门读取指定 env 文件（默认 edu-agent/.env）
node scripts\deploy\deploy.mjs stop     # 按端口清 8000/3000（netstat→PID→taskkill /F /T）
node scripts\deploy\deploy.mjs stop --all   # 同上，附加 Redis 容器处置提示（容器本身不停）
node scripts\deploy\deploy.mjs status   # ① dev/prod 形态判别（_buildManifest 探针，404=生产判据）② 透传 check-demo
node scripts\deploy\deploy.mjs stop-prod-and-restart-dev   # 生产→dev 可逆（见下）
```

通用旗标（四条命令全部生效，W-NEXT-DEPLOY-HARD-001）：

| 旗标 | 作用 | 承接 |
|---|---|---|
| `--frontend-port <N>` | 前端端口，默认 3000。start 拉起/stop 清杀/status 判别/可逆子命令全链路跟随，并透传 `check-demo --frontend-port`（探测侧与拉起侧同端口，防 failover 端口判错） | W-NEXT-CHECKDEMO-PROD-001 P0-4 |
| `--prod-gate` | start 前跑 `scripts/eval/deploy_env_gate.mjs`（exit!=0 立即中止并给处置指引，**不拉起任何服务**）；check-demo 断言段以 `--prod-gate` 严格模式跑（⑧ 开发态 WARN 升级红） | W-NEXT-CHECKDEMO-PROD-001 P0-1 |
| `--env <文件>` | 部署环境门读取的 env 文件路径（默认 `edu-agent/.env`；仅与 `--prod-gate` 搭配生效，方便对候选 .env 预检） | 同上 |

#### 可逆性：stop-prod-and-restart-dev（生产→dev，W-NEXT-PRODUCTION-BUILD-001 P0-5 收口）

```bash
node scripts\deploy\deploy.mjs stop-prod-and-restart-dev [--frontend-port 3000]
```

依序执行：① 停前形态探针（`_buildManifest`，如实记录被停的是什么形态）→ ② 按端口反查 PID
`taskkill /F /T` 停掉 <port> 上的前端实例 + **等待端口释放**（有界 10s 轮询——taskkill 报成功后进程
teardown/套接字关闭有秒级窗口，立即探测会误判"仍被占用"而中止，盲测实证后加）→ ③ **删 `.next` dev 缓存**
（AGENTS.md 教训 1：dev server 不热重载入口跳转，重启须删 `.next`；只删 `.next`，**不动 `.next-prod`
生产产物**，C2 两侧隔离）→ ④ 起 `next dev -p <port>`（真实入口
`node_modules/next/dist/bin/next`，实证活生产实例命令行同源，日志 `logs/deploy-frontend-dev.log`）→
⑤ 健康探测 `/login-register.html` 200 → ⑥ 形态复核（`_buildManifest` 期望 200=dev）。

反向（dev→生产，2026-09-18 盲测实证路径）：**先清掉 <port> 上的 dev 实例再 start**——`start` 对已在
监听的端口是幂等跳过（不会替换 dev 实例），单跑 `start` 切不回生产形态。单清前端端口 =
`for /f "PID" %p in ('netstat -ano -p tcp ^| findstr ":3000.*LISTENING"') do taskkill /F /T /PID %p`
（或 `taskkill /F /T /PID <dev PID>`）；`stop` 也可用但**会连 8000 后端一起清**。随后
`node scripts\deploy\deploy.mjs start --frontend-port 3000`：8000 在跑则幂等跳过、3000 空闲则
`.next-prod/BUILD_ID` 在即跳过 build（实测 ~4-5s 拉起）并自动跑 check-demo 断言。

- `stop` **不停 Redis 容器**（缓存/限流/会话依赖它，一般无需停止）；容器名按 .env `REDIS_PORT` 宿主端口反查（不要按旧名硬编码），确需停止：`docker stop <反查容器名>`，恢复 `docker start <同容器名>`。
- PID 记录：`logs/deploy.pids.json`（stop 会清理陈旧记录；记录的是 spawn 包装层 PID，实际监听 PID 以 `netstat -ano` 为准——清杀一律按端口反查，不依赖该记录）。
- 幂等提示：start 时若 3000 已被监听会跳过并提示「可能是 dev 形态，如需生产形态请先 stop」。
- 可逆性三态盲测（--frontend-port 3001 全流程 / --prod-gate 拦 DEBUG=true / 往返后恢复生产 21/21）实证记录：`edu-agent/test-reports/WNEXTDEPLOYHARD1-completion-report.md`。

### 日志位置（均为追加式 append）

| 文件 | 内容 |
|---|---|
| `edu-agent/logs/deploy-backend.log` | 后端 uvicorn stdout/stderr（含启动形态 JSON 段、lifespan 存储初始化结果） |
| `edu-agent/logs/deploy-frontend.log` | 前端 next start 输出 |
| `edu-agent/logs/deploy-frontend-build.log` | next build 输出（产物缺失时自动 build 的落点） |
| `edu-agent/logs/deploy-frontend-dev.log` | next dev 输出（`stop-prod-and-restart-dev` 拉起的 dev 实例落点，W-NEXT-DEPLOY-HARD-001） |

应用自身日志由 .env `LOG_DIR=./logs`、`LOG_ROTATION="100 MB"`、`LOG_RETENTION="7 days"` 控制（自动轮转）。

### 巡检建议

1. **每次演示/交付前**：`node scripts\deploy\deploy.mjs status` → 期望 9/9 全绿（整轮巡检约 **2-7 秒**，脚本末行自带 `检查耗时 …ms`；实测样本 1.8s / 2.3s / 2.6s / 6.6s，全红快失败时 <1s）。**最大单项在 ② Redis `docker exec`（0.5-1.3s）与 ⑥ 登录链路（1.0-1.2s）之间波动**（后端/容器冷启动时 ② 常居首）；⑥ 单项 6-10s 仅见于冷启动或限流重试，非卡死。⚠ dev 形态下 ⑤ 报 WARN（非生产 build）、⑧ 按分支 C 报红属预期，见 §3⑤。⚠ **红态耗时会成倍拉长**：②/③ 走 socket 超时 3s、④-⑨ 走 HTTP 超时 5s，VM 关机或后端/前端未起时逐项等满超时才失败（实测一例 VM+后端+前端全缺：整轮 27.2s，④ 单项 5.54s 最大，①④⑥ 红）——**红态整轮 10-30s 属正常，不要按卡死处理**。
2. **每日**：Docker Desktop 在跑、`docker exec edu-redis-standalone redis-cli ping` = PONG；VM 在线（①③ 探测绿）。
3. **每周**：查看 `logs/` 磁盘占用（轮转/保留由 .env 控制）；`deploy-frontend-build.log` 是否有异常 build 重试。
4. Redis 容器开机自启（C5-D3 已实证收口，2026-09-13）：`docker inspect edu-redis-standalone` RestartPolicy.Name = `unless-stopped`（容器 Running=true），宿主机重启后 Docker 自动拉起容器，无需手动 `docker start`；但 Docker Desktop 本身需设为开机自启（Windows 设置 → 启动项）。

### 数据安全红线

1. **禁 DB 直写**：一切业务数据变更必须走后端 API 或既有脚本，禁止手工 UPDATE/DELETE 业务表。
2. **操作前快照**：任何批量操作/升级/数据订正前，先做 MySQL 快照，落 `deploy/backups/`（该目录已进 .gitignore，快照不进 git）：

```bash
mysqldump -uroot -p --routines --triggers --single-transaction --set-gtid-purged=OFF edu > deploy/backups/edu_snapshot_<日期说明>.sql
```

3. **恢复**：按 §3 步骤③（全库 dump 含建库语句；恢复后用 information_schema 计数验证 106 表）。⚠ **恢复前必读 §3③「非空即停」**：既存 `edu` 库执行恢复＝破坏性覆盖（本机实测 104 表 ≠ 08-16 dump 106 表，双向分叉），先查 `information_schema.tables` 计数，`≠0` 即停，改走快照/换干净空库。

---

## 6. 边界声明

- 本部署包 = **本机同构部署**（Windows 主机 + VMware VM Docker 一键拉起），验收口径 =
  干净进程环境一条命令拉起 + check-demo 9/9 + 核心页抽验；不含公网暴露/HTTPS/域名/Nginx 反代。
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

# 0.5) 部署环境门（W-NEXT-CHECKDEMO-PROD-001，机验两级判据，出包前必跑）：对真实 .env 把关
node scripts/eval/deploy_env_gate.mjs
#    期望：末行 [DEPLOY_GATE] decision=allow +「部署门 PASS」exit 0
#    DEBUG=true → exit 1 阻断出包（含 ENV_NAME 缺省/local 的本机 dev 形态——部署门从严，P0-2：
#    生产忘设 ENV_NAME 时 DEBUG=true 即真后门）；ENV_NAME 显式非 local + DEBUG=true 同样 exit 1（P1-8 同口径）。
#    本地开发日常把关用 check-demo ⑧（对本机 dev 态为 WARN 不阻断）；CI 已对 .env.example 跑同门（必须 exit 0）。
#    自回归：node scripts/eval/test_deploy_env_gate.mjs（期望 10/10 PASS）

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

# 6) HITL resume 端点鉴权（W-NEXT-8 登记，承接批判 T8-C3）→ 无 token 必须 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  -H "Content-Type: application/json" \
  -d "{\"thread_id\":\"probe-nonexistent\",\"action\":\"confirm\"}" \
  http://localhost:8000/api/chat/resume
#    期望：401（未鉴权即拒）。
#    ⚠ 本机 dev 态（DEBUG=true + ENV_NAME 缺省=local）W-NEXT-8 实测为 **404 {"code":"40450"}
#      CHAT_HITL_THREAD_NOT_FOUND（HTTP 404）而非 401**：DEBUG 虚拟管理员通道使无 token 请求也进入
#      业务逻辑（批判 T8-C3 锚点；同轮无 token GET /api/users/me = 200 虚拟管理员）。生产
#      DEBUG=false 下的 401 行为**待本检查单窗口实测登记**（W-NEXT-8 登记在案，未改代码——DEBUG 语义为既有设计）。
```

### venv 依赖清单（task61 补装，出包前核对）

- **额外生产依赖**：`pdfplumber==0.11.10`（task61 契约⑥ PDF 解析真实成立；图表/PDF 导入链路依赖）。需在后端镜像 `backend.Dockerfile` 的依赖安装段与 `requirements*.txt`（如适用）中同步声明，勿遗漏。
