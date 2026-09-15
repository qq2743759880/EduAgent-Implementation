# 新人视角交接报告 —— EduAgent 部署健康巡检（T3 盲测）

> 执行角色：刚接手项目的新同事（除 deploy/README.md、根 AGENTS.md、被巡检的代码/脚本本身外，未读任何历史报告/验收文档）。
> 执行会话：`executionSessionId = 20260915_151126_a9b7e8`，model `ark-code-latest`，Hermes 独立会话。
> 巡检时间：2026-09-15 15:25–16:10（中国标准时间）。HEAD = `0deed7e`（feature/opt-waves），工作区 151 个未跟踪文件（未清理、未改动任何代码/配置）。
> 证据标注：[实测]=本会话真实执行输出；[代码佐证]=读到的源码 file:line；[推演]=由已证事实推断；[未验证]=本轮未覆盖；[文档原文]=deploy/README.md 原文。

---

## 0. 结论（先看这里）

1. **照文档执行，系统可以拉起来并全绿**：`deploy.mjs start` 一条命令实测通过，check-demo **9/9 绿**（exit 0），登录/课程/社区/个人中心数据都是活的。
2. **但文档口径与实物有多处漂移**（15 项，见 §4），其中 3 项会直接误导新人：快照恢复口径（106 vs 现库 104 表）、check-demo 项数（8 vs 实际 9）、⑧ 项探测点已失真（永远绿，测不出真实存在的 DEBUG 虚拟管理员）。
3. **新人视角最扎眼的缺陷**：`dashboard.html` 漏引 `/edu-api.js`，整页静默死壳（HTTP 200、零报错、零数据），check-demo ⑦ 却给它放行——"绿"不等于"能用"。
4. 部署资产本身质量不低：幂等、失败路径（--fail-drill）、Redis 开机自启等承诺均实测兑现。

---

## 1. 环境基线（巡检起点实况）

| 项 | 实测值 | 来源 |
|---|---|---|
| Node / npm | v24.18.0 / 11.16.0 | `node --version` [实测] |
| 后端 venv Python | 3.11.15（edu-agent/.venv，`pip show edu-agent` = 0.3.0） | [实测] |
| MySQL | mysqld.exe，PID 6484，0.0.0.0:3306 监听 | netstat [实测] |
| Redis | Docker Desktop 引擎 24.0.6，容器 `edu-redis-standalone` Up 6h，ping=PONG，RestartPolicy=`unless-stopped` running=true | [实测] |
| VM 192.168.85.101 | Milvus:19530 / Mongo:27017 socket 可达 | [实测] |
| 后端 8000 | **巡检前已在运行**（PID 16552，2026-09-15 10:32:20 启动，命令行 `python -m uvicorn app.main:app --port 8000`，解释器为 uv 托管 cpython 3.11，**不是** `.venv\Scripts\python.exe`） | 进程取证 [实测] |
| 前端 3000 | **巡检前已在运行**（PID 35016，`node next/dist/bin start-server.js`——**dev 形态**，`.next-prod/` 不存在、`.next/BUILD_ID` 不存在） | 进程取证 [实测] |
| .env 形态 | `DEBUG=true`（dev），`ENV_NAME` 未设（默认 local），`JWT_SECRET=dev-secret-key-change-in-production`（默认值），`EMBED_BACKEND=cuda`；.env 有 50 键，模板 .env.example 有 37 个未注释键 | [实测] |
| 后端健康 | `/health` ok v0.3.0；`/health/detail` 全组件 ok（BGE-M3 cuda 已加载 26.5s；reranker sidecar 连接拒绝→进程内兜底 ok，warmup 43.1s） | [实测] |

> 新人须知：本次是"半空降"巡检——四个服务里两个已经在跑。文档没写"如何判断系统是否已在运行"，这是 §4 偏差 D-01。

---

## 2. 部署步骤逐条对照表（文档说的 vs 实际发生的）

### §2 前置清单

| 文档原文 | 实际 | 判定 |
|---|---|---|
| Node ≥ 18（当前验证机 Node v24、next 16.3.0） | v24.18.0 / next 16.3.0 | ✅ 一致（文档自报版本与实物吻合） |
| Python venv 3.11.x，路径 `edu-agent\.venv\Scripts\python.exe`（deploy.mjs 硬编码） | 存在，3.11.15 | ✅ 一致 |
| venv 首次创建命令（`python -m venv .venv` + `pip install -e .`） | 未复跑（venv 已存在） | ➖ [未验证]（文档写了可操作的命令与 C5-O2 收口背书，但新人只能"信"） |
| Docker Desktop + 容器 `edu-redis-standalone` | 一致，引擎/容器均在跑 | ✅ |
| VMware VMX 路径 `E:\tt\...\docker.vmx` | 文件存在 | ✅（check-demo.mjs:15 登记路径本机有效） |
| `.env.example`（taskC0，**220 键**） | 实际未注释键 **37 个**；全文无"220"字样（227 是把注释行也算上的 grep 数） | ⚠️ D-02 数字对不上 |
| 220 键逐键说明在 `.ai-hub/plans/deploy-config-checklist.md` | 该文件存在（45KB）但未逐键核对 | ➖ 部分核实 |
| §2.2 密钥生成两条 python 命令 | 未执行（.env 已存在）；**文档没有任何"校验现有 .env 是否已是强密钥"的手段**，check-demo 也不查 | ⚠️ D-03（本机 .env 的 JWT_SECRET 就是文档明令禁止的默认值，但没有任何巡检会红） |

### §3① checkout

| 文档原文 | 实际 | 判定 |
|---|---|---|
| `edu-agent/` 与 `edu-frontend/` 工作区同级 | 一致 | ✅ |
| 首次部署需 venv + 前端 `npm install` | node_modules 就绪 | ✅（安装命令文档未给——新人视角="npm install 是我猜的"） |

### §3② 配置 .env

| 文档原文 | 实际 | 判定 |
|---|---|---|
| `copy .env.example .env` 然后改最小必改项 | 本机 .env 与模板分叉明显：模板有而 .env 缺 7 键（API_TOKEN、CORS_ORIGINS、ENV_NAME、HOST、PORT、REDIS_URL、WORKERS）；.env 另有 13+ 个模板没有的键（LLM_FAST_*/LLM_STRONG_*/HITL_*/EMBEDDING_* 等） | ⚠️ D-04：照模板复制**不能复现当前运行系统**的 .env；文档没说"本机已有 .env 时怎么办" |
| 生产最小必改 6 键（DEBUG/ENV_NAME/JWT/API_TOKEN/MYSQL_PASSWORD/LLM_API_KEY/CORS 双源） | 与 config.py 护栏吻合：`_security_guard`（config.py:660）+ P1-8 门禁（config.py:691）+ `_cors_origins()` 生产回退双源（app/main.py:242-249） | ✅ [代码佐证] |

### §3③ 数据库初始化（edu 库）——本轮最大风险区

| 文档原文 | 实际 | 判定 |
|---|---|---|
| "后端不会自动建库建表"（database.py init_mysql 仅建连接池） | 与运行态一致（库/表确由快照带入） | ✅（源码未复读，[文档原文]+运行态旁证） |
| 方式一：`mysql -uroot -p < deploy/backups/20260816_task00/edu_full_dump.sql`，"验证（期望 **106 表**）" | **现库 edu 实际 104 表**。dump 内确有 106 个 CREATE TABLE（SHA256 与 BACKUP_MANIFEST 一致：8cd6930c…）。表级差异双向：dump 有而现库无 11 张（admin_* 7 张、curriculum_* 4 张）；现库有而 dump 无 9 张（course_review、hitl_approval、knowledge_import_task、task_execution、user_memory* 等）。dump 含 106 条 DROP TABLE | ⚠️ **D-05（最重要）**：文档口径对"全新机器"成立，但没警告"已有库的机器"——新人若照做，DROP TABLE 会清掉现库 11 张新表并把数据回滚到 08-16（现库存在 2026-09-13 的真实订单）。文档只有 §5 数据安全红线一句泛泛的"操作前快照"，§3③ 页面内无警示 |
| 方式二快照"全文件不含 CREATE DATABASE / USE" | grep 全文 0 匹配，实锤 | ✅ 文档自证信息准确 |
| "测试账号随快照带入" | 登录链路实测通过（adm02test/user000001） | ✅（本机种子来自历史恢复，非本轮操作） |
| mysql 客户端 | PATH 可用（C:/Program Files/MySQL/MySQL Server 8.0） | ✅ |

**处置记录：本轮未执行任何恢复**——现库在跑、dump 是破坏性导入（DROP TABLE），且守则禁止改动数据。这本身即报告素材：**文档让新人做的第一步数据库操作，在本机上执行=事故**，而文档没有提供"如何判断我该不该执行"的检查步骤。

### §3④ 一键拉起（`node scripts\deploy\deploy.mjs start`）

实测执行，全程 48 秒（15:33:49 → 15:34:37），逐段对照：

| 文档承诺 | 实际输出 | 判定 |
|---|---|---|
| 前置检查：MySQL/VM/Redis 探测，只报告不阻塞 | MySQL/Milvus/Mongo 三项 OK；**Redis 项 FAIL："docker exec … redis-cli ping [退出码 null]"** | ⚠️ D-06：preflight 的 Redis 探测 8s 超时假阴性——**同一个 start 内**随后 check-demo ② 用同一容器同一命令 4 秒拿到 PONG。文档没说 preflight 会"狼来了" |
| 后端 uvicorn（读 .env 形态原样） | 幂等跳过："端口 8000 已有监听(PID 16552)" | ✅ 与文档幂等承诺一致 |
| 前端 build+start（.next-prod 缺失自动 build） | 幂等跳过："可能是 dev 形态，如需生产形态请先 stop"——**提示完全命中现实**（3000 确实是 dev 形态） | ✅（build 路径本轮未走 → [未验证]；`deploy-frontend-build.log` 不存在旁证该路径从未在本机走过） |
| 自动 check-demo 断言 | 横幅写"期望 **8/8**"，脚本实际 9 项、输出"绿 9/9" | ⚠️ D-07 |
| exit code 透传 | EXIT=0 | ✅ |
| 日志/PID 记录 `logs/deploy.pids.json` | 本次运行**没有生成** pids 文件（只在真正 spawn 时写入）；deploy-backend.log 最后写入停在 9-13，当前后端写的是 app.log | ⚠️ D-08（小） |

> 佐证：PID 16552 的 stdout 并不进 deploy-backend.log（该日志 9-13 后未再更新），而 start 又以"端口已监听"跳过——**文档没有任何手段能让新人发现"在跑的服务不是 deploy 起的、解释器不是 venv 的"**。

### §3⑤ 验收 check-demo

```text
node scripts/check-demo.mjs   → 绿 9/9，exit 0，11.0s [实测]
--fail-drill                  → 绿 6/9，红①②③，exit 1，6.4s [实测，同命令组捕获退出码]
```

逐项结果与偏差见 §3。fail-drill 的失败输出与逐项处置指引与 README §4 表格文字一一对应——**文档"FAIL 时逐项给一句话处置指引"的承诺兑现**。

---

## 3. check-demo 巡检结果（9 项，文档只写了 8 项）

| # | 检查项 | 结果 | 耗时 | 备注/偏差 |
|---|---|---|---|---|
| ① | Milvus 192.168.85.101:19530 | PASS | 5ms | — |
| ② | Redis docker exec ping | PASS | 4042ms | preflight 同口径检查刚假阴性过（D-06） |
| ③ | MongoDB 192.168.85.101:27017 | PASS | 3ms | — |
| ④ | 后端 /health | PASS | 95ms | status=ok v0.3.0 |
| ⑤ | 前端 /login-register.html | PASS | 402ms | — |
| ⑥ | 登录链路 admin+student | PASS | **10474ms** | adm02test(role=admin,user_id=100003) + user000001(role=student,user_id=1)；单项 10.5s，文档脚本注释自称"总耗时 <1 分钟"的 GWT 口径没提单项会这么慢（drill 轮 6.5s，波动大） |
| ⑦ | 关键页 200 × 8 | PASS | 337ms | **只验 HTTP 200**：dashboard.html 死壳照样绿（见 §5-2） |
| ⑧ | advisory DEBUG 虚拟管理员探测（无 token GET /api/admin/users） | PASS："无 token 被 401 拒绝(DEBUG 安全)" | 131ms | **探测点已失真（D-09）**：本机 .env 明明 DEBUG=true，虚拟管理员后门真实存在（无 token GET /api/users/me → 200，role=admin user_id=1 "小柚子同学" [实测]），但 /api/admin/* 有独立 fail-closed 中间件（app/main.py:263 AdminAuthMiddleware）→ ⑧ 永远 401 永远绿。**⑧ 的"安全"结论此刻是假阴性** |
| ⑨ | 抽验页 /admin-users-refine-proto.html | PASS | 22ms | README §4 表格**没有⑨这一行**（脚本注释称 C5-D2 扩清单）→ D-07 同源 |

文档"约 2 秒"的巡检预期（§5 巡检建议 1）：实测 11-15.5s——量级无碍但数字过时 [实测]。

---

## 4. 新人视角抽查（浏览器实测，student 账号登录态）

操作序列统一为：登录页输入文档测试账号 → 登录 → 逐页打开 → 读正文/看数据/记录现象。共 7 页（要求 5 页）。

### 1) login-register.html —— ✅ 能看懂，功能可用
- 双表单（登录/注册分离），placeholder 清晰；用 `user000001/Test@123456` 一次登录成功，跳 dashboard.html。
- 现象：页面标题含"task42 原型 · /login + /register 认证页 + / 根路由"——**开发任务号直接暴露给最终用户** [实测]。

### 2) dashboard.html —— ❌ **整页死壳（本轮最严重发现）**
- 现象序列：登录成功跳入 → 页面只剩问候语"你好，同学 👋"+两句介绍+两个按钮，**正文仅 179 字符**；介绍承诺的"学习时长/学科能力/积分/排行榜"内容一个都没有。
- 根因实锤：`document.EAPI === undefined`、performance 里 **0 个 API 请求**、0 个 canvas/svg 图表 [实测]；对照源码——**dashboard.html 全文只有两个内联 `<script>`，没有任何一行引入 `/edu-api.js`**（其余 23 个公共页全部引入）[代码佐证]。页内 470-684 行的完整接线逻辑（task11 注释自称"全量真实接线"）第一行 `if (!window.EAPI) return;` 静默退出。
- 讽刺点：登录守卫代码也在同一个 IIFE 里，于是"未登录→诚实登录引导"与"已登录→拉数据"**两个分支都不存在**，页面永远停在静态骨架。
- check-demo ⑦ 给它 200 放行 [实测]——**绿 ≠ 能用**。

### 3) courses.html —— ⚠️ 数据是活的，但混着假数据与开发标注
- 活数据：15 门真实课程（名称/价格"¥2,999 起"/3 个班次/学过人数），来自 `GET /api/series` 契约 [实测]。
- 假数据实锤：顶部"连续打卡 **7** 天 / **Lv.5** / **120 XP** / 累计 **1,280 XP**"为 HTML 写死（courses.html:370-372）[代码佐证]；同一登录态真实积分 API 返回 **Lv.1「萌新」351 分** [实测]。新人"看不出这是假的"，会当真。
- 开发标注泄漏：页面上渲染着"契约① GET /api/series · 效果图 v4 · 两级导航 · 学中玩"这行规格文字 [实测]。

### 4) community.html —— ✅ 活数据，一处明显瑕疵
- 真实帖子（total=98，真实浏览/点赞/回帖数）[实测]。
- 瑕疵：首屏**同标题"👋 欢迎来到 EduAgent 学习社区！"置顶帖连渲染 3 遍**（浏览数 166/129/…各不相同）[实测]——分页或去重逻辑问题，新人能一眼看出"这不对吧"。

### 5) me.html —— ✅ 本轮最佳页面
- 7 个真实 API（users/me、learning-summary、gamification/me/points、profile、trade/orders、coupons、favorites）[实测]；昵称"小柚子同学"、**积分 Lv.1·351 与 API 字节级一致**、真实订单 33 笔（真实单号/金额/状态）[实测]。
- 亮点：未建成页面诚实标注"售后工单页暂未上线（后端工单端点已有，页面待接）"。
- 同样泄漏开发规格文字："GET /api/trade/orders · 分页壳 {total,page,page_size,items} · 状态筛选真实下发"、"本页下方真实订单列表（task10 接线）"[实测]。

### 6) chat.html —— ✅ 可用
- 打开即调 3 个真实 API（users/me、chat/sessions、history）[实测]；欢迎对话气泡为写死（"脚本与自动化编程方向…" chat.html:380-382，时间 10:02 也是死的）[代码佐证]——新人第一眼会以为是自己的会话。

### 7) favorites.html —— ✅ 活数据（5 条真实收藏）[实测]

**抽查小结**：7 页里 6 页"能看懂是干什么的"，5 页数据是活的；1 页死壳（dashboard）、1 处假数据（courses XP 条）、多处开发规格文字直接面向用户。全部页面 0 报错弹窗——问题全是"静默"的，这正是 check-demo 抓不到的那类。

---

## 5. 文档质量评分（deploy/README.md 逐章）

| 章 | 评分 | 依据 |
|---|---|---|
| §1 架构一页图 | **准确**（9/10） | 8 个组件端口/职责全部与实测吻合；MinIO/Neo4j 在 VM 由 /health/detail minio=ok neo4j=ok 旁证 [实测+推演] |
| §2 前置清单 | **基本准确**（7/10） | 软件/路径全对；"220 键"数字失实（D-02）；无"校验已有 .env"手段（D-03） |
| §3 部署步骤 | **中**（5/10） | ①②④⑤ 可照做且幂等承诺兑现；③ 恢复口径与现库不符且无破坏性警示（D-05，最高风险）；"期望 106 表"在既有机器上必然对不上 |
| §4 故障对照表 | **中**（5/10） | ①-⑦ 处置指引与脚本实测一致、已知项 A/C 与运行态吻合；⑧ 探测点失真永远绿（D-09）；缺⑨行（D-07）；已知项 B 未验证 [未验证] |
| §5 日常运维 | **良好**（8/10） | Redis 自启（unless-stopped）实锤兑现；日志位置准确；"约 2 秒"巡检过时（实测 11-15.5s）；pids.json 小偏差（D-08）；stop 未执行（守则禁止杀现有服务）[未验证] |
| §6 边界声明 | **准确**（9/10） | 与脚本能力边界一致（VM/Redis 拉起不在 start 内，实测确只探测） |
| 附录（容器化 + task123 + venv 清单） | **基本准确**（7/10） | compose/Dockerfile/.env.production.example 均存在；**`.dockerignore` 文档列出但根目录不存在**（D-10）；pdfplumber 0.11.10 实测在 venv ✅；task123 检查单未跑（前提=生产形态后端，当前是 dev 形态）[未验证] |

### 文档偏差清单（汇总 15 项）

| # | 偏差 | 影响 | 证据 |
|---|---|---|---|
| D-01 | 缺"系统是否已在运行/什么形态"的判别步骤 | 新人无法区分"deploy 起的"与"手工起的"；本次 8000 是非 venv 解释器、3000 是 dev 形态，文档无感知手段 | 进程取证 [实测] |
| D-02 | ".env.example 220 键"数字失实（实际未注释 37 键） | 轻微；配置核查口径混乱 | grep [实测] |
| D-03 | 无 .env 健康校验手段；本机 JWT_SECRET 即为文档禁用默认值，无任何检查会红 | 安全隐患潜伏 | [实测] |
| D-04 | 本机 .env 与模板双向分叉；"copy 模板"复现不了现系统 | 新人二选一都会困惑 | [实测] |
| D-05 | **快照恢复无"已有库勿执行"警示；106 vs 现库 104 表双向分叉未记录** | 照做=DROP 掉现库 11 张表+数据回滚 1 个月 | dump grep + information_schema [实测] |
| D-06 | preflight Redis 探测假阴性（退出码 null），同轮 check-demo 却 PONG | 新人会误判 Redis 坏了，文档无解释 | start 输出 [实测] |
| D-07 | 文档通篇 8 项口径，脚本实为 9 项（⑨ C5-D2 扩清单未进文档）；脚本内部横幅也仍写 8/8 | 文档、脚本横幅、实际输出三者不一致 | check-demo.mjs:8,253 [代码佐证] |
| D-08 | pids.json 仅在真实 spawn 时生成；幂等跳过时无任何记录 | "PID 记录"承诺与实际不符 | [实测] |
| D-09 | **⑧ 探测点（/api/admin/users）被 fail-closed 中间件保护，永远 401；真正的 DEBUG 后门暴露面（/api/users/me、/api/auth/me 无 token 200 role=admin）测不到** | "DEBUG 安全"结论失真，安全巡检形同虚设 | curl [实测] + main.py:263 [代码佐证] |
| D-10 | 附录资产 `.dockerignore` 不存在 | 容器化路线照做会缺文件 | ls [实测] |
| D-11 | 巡检"约 2 秒"过时（实测 11-15.5s，⑥ 一项 6-10s） | 预期管理 | [实测] |
| D-12 | ⑥ 登录链路单项耗时波动大（6.5-10.5s），无解释 | 新人会怀疑卡死 | [实测] |
| D-13 | README 完全没提 dashboard 级别的页面质量门（⑦ 只验 200） | 死壳页全绿通过 | §5-2 [实测] |
| D-14 | §2.1 说"依赖以 pyproject 为真相源"，但未写前端 install 命令、未写 MySQL 客户端从哪来（本机 PATH 恰好有） | 新人要么猜要么卡 | [实测] |
| D-15 | deploy-backend.log 与实际运行后端的 stdout 无关联（当前后端写 app.log） | 按文档看日志会看错文件 | log mtime [实测] |

---

## 6. 如果你是下一位新人，最想提醒 TA 的 3 件事

1. **§3③ 的快照恢复命令，在这台"已经跑着系统"的机器上是禁手。** dump 是 DROP-TABLE 式全量恢复，现库（104 表）和快照（106 表）已经双向分叉——直接执行会清掉 11 张新表、把订单数据回滚到 8 月 16 日。执行前先 `SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='edu'`，只要不是干净空库，就先停下来问人。
2. **check-demo 9/9 全绿 ≠ 系统健康。** ⑧ 的"DEBUG 安全"测的是被中间件死守的 /api/admin/users，而真正的虚拟管理员后门在 /api/users/me（无 token 200）；⑦ 只验 HTTP 200，dashboard.html 漏引 edu-api.js 整页死壳也是绿的。绿了之后，请用浏览器拿测试账号把核心页点一遍——尤其 dashboard。
3. **别相信"端口通=服务正常=deploy 管着它"。** 本次巡检时 8000 是裸 python 起的（不是 .venv 解释器）、3000 是 dev 形态、deploy-backend.log 根本不是当前后端写的日志。判断形态：看进程命令行、看 `.next-prod/BUILD_ID`、再看日志文件 mtime；`deploy.mjs start` 只会幂等跳过并轻描淡写提一句"可能是 dev 形态"。

---

## 7. 本轮未覆盖项（如实登记）

- 快照恢复两条命令**均未执行**（破坏性+守则禁止），106 表期望值仅在 dump 文件层面核验。
- `deploy.mjs stop` / `stop --all` 未执行（会杀现有服务）；`npx next build`（.next-prod 生产 build 路径）未触发。
- 已知项 B（Neo4j 密码同步）无 VM 凭据，未验证。
- 附录 task123 DEBUG=False 检查单未跑（前提：生产形态后端；当前后端 DEBUG=true）。
- `.ai-hub/plans/deploy-config-checklist.md` 未逐键核对（220 键口径本身已失实，逐键核对价值存疑）。
- 一次未复现的瞬时现象：抽查中途 localStorage 的 token 曾消失（浏览器仍显示登录态），受控复现（登录→chat→favorites）token 全程存活；后端日志窗口内无 401 刷新失败记录。存疑不判死，登记待观察。
- 本轮未读取任何历史验收/巡检报告（独立性约束）；守则遵守：未重启/杀任何进程，未改任何代码与配置，未执行任何写库操作。

--- 完（报告文件即唯一交付物，单 commit 仅含本文件）
