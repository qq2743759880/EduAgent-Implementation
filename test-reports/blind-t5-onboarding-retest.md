# 盲测 T5：新人上手重走部署（onboarding re-test）

- **executionSessionId**：`20260915_184507_fbd48a`
- **身份设定**：一名刚接手 EduAgent 运维的新同事。**仅**持有 `deploy/README.md` + `AGENTS.md` 与可读源码，**未读任何历史报告/验收文档**。
- **禁读清单（本次实际遵守）**：`test-reports/onboarding-fresh-report.md`（T3 盲测报告）、`test-reports/C3-e2e-report.md`、`test-reports/task123-completion-report.md`、`test-reports/critique-*`、任何 `verify/ACCEPTANCE*`。仅**检查过** `onboarding-fresh-report.md` 的**存在性**（README §3③ 引用它），未读取其内容。
- **允许并已读的书面文档 / 被测代码**：`deploy/README.md`、`AGENTS.md`、`edu-agent/scripts/check-demo.mjs`、`edu-agent/scripts/deploy/deploy.mjs`、`deploy/backend.Dockerfile`、`edu-agent/app/config.py`、`edu-agent/app/main.py`、`edu-agent/.env.example`、`edu-agent/pyproject.toml`、各静态页 HTML。
- **手段纪律**：未使用 Playwright；接口一律 curl；未做任何 DB 直写（仅 `SELECT`/`information_schema` 只读查询）；测试数据自建自清（临时脚手架已删、模拟服务已杀、限流窗口已等待复位）。
- **标注图例**：`[实测]` 本机亲手跑出的原始输出 ｜ `[代码佐证]` 源码行号可查 ｜ `[文档原文]` 引自 README/模板原文 ｜ `[推演]` 由前两者推导 ｜ `[未验证]` 本轮未取得证据。

---

## 0. 结论摘要（TL;DR）

| 问题（编排者指定） | 结论 |
|---|---|
| §3③「已有库判别」警示是否醒目到不会误执行 | **是**。警示块位置靠前、带 ⚠、给出可执行判别命令与「≠0 即停」，且**场景描述经我独立实测完全为真**（现库 104 表、分叉 9/11 张、dump 含 106 条 DROP TABLE）。详见 §A-③ |
| §4 故障表是否有 ⑨ 行 | **有**，且与脚本第 9 项逐字对得上（`admin-users-refine-proto.html`）。详见 §A-4 |
| 文档项数（9 项）是否已纠偏 | **已纠偏**。README 写 9，脚本实为 ①–⑨ 共 9 项，`[实测]` 输出 `绿 9/9`。但 `deploy.mjs` 内部仍打 **8/8**（残留）。详见 §C-D3 |
| 220 键是否已纠偏 | **未纠偏**。README 引用的「未注释键 37 个」`[实测]` 正确（37），但 `.env.example` 自身头部仍写「对齐 Settings 全字段，**220 项**」；实测 Settings 为 **242** 字段、模板键行 **230** 行。详见 §C-D2 |
| 巡检耗时口径是否已纠偏 | **未纠偏**。README 两处仍写「整轮 10-15 秒」「⑥ 单项 6-10s 属正常波动」；实测整轮 **2.5–3.2s（脚本内部）/ 4.6–5.1s（wall）**、⑥ **1.0–1.4s**。详见 §C-D1 |
| check-demo 是否绿 9/9 | **是**，`绿 9/9,WARN ⑧ —— 演示环境就绪`，exit 0。详见 §B |
| ⑧ 现在输出什么 | **真语义 WARN**：`[WARN 开发态虚拟管理员后门存在(DEBUG=true,ENV_NAME=local);部署前必须 DEBUG=false,见 P1-8 ENV_NAME 门]`，不再是旧的假「DEBUG 安全」。**但上游发现 ⑧ 分支 C 存在假绿缺陷（见 §B-⑧ / §C-D0，本轮最高优先级发现）** |

**本轮最高优先级发现（1 条 P1 + 7 条 P3）**

> **P1（⑧ 分支 C 假绿）**：`check-demo.mjs` 注释声明「C) DEBUG=true + ENV_NAME≠local → 红，阻断 exit 1」，但**实现把所有分支都标为 WARN**（`{__warn: true}` 挂在函数上，见 `check-demo.mjs:277`），导致**生产形态误配（DEBUG=true + ENV_NAME=prod，即真实匿名管理员后门）被判为 WARN、不计红项、exit 0，并打印「绿 9/9 —— 演示环境就绪」**。`[实测]` 复现见 §B-⑧。

---

## A. 部署步骤对照表（照 README 逐步走）

| 步骤 | README 说法 | 我的实测结果 | 判定 |
|---|---|---|---|
| §1 架构 | MySQL/后端/前端在宿主；Milvus/Mongo/MinIO/Neo4j 在 VM `192.168.85.101` | `[实测]` socket 全通：Milvus 19530 / Mongo 27017 / MinIO 9000 / Neo4j 7687 全部 OK | ✅ 一致 |
| §2.1 Python | `pyproject.toml` 要求 `>=3.11,<3.12`；解释器固定 `.venv\Scripts\python.exe` | `[实测]` `requires-python = ">=3.11,<3.12"`；`.venv` 存在且可跑 | ✅ 一致 |
| §2.1 Node/前端 | deploy/check-demo 零新依赖；当前验证机 next 16.3.0 | `[实测]` `edu-frontend/package.json` → `next: 16.3.0` | ✅ 一致 |
| §2.1 Docker/Redis | 容器名 `edu-redis-standalone`；引擎未运行时脚本报「docker 引擎未运行」 | `[实测]` 容器 `Up`；`docker exec ... redis-cli ping` = PONG | ✅ 一致 |
| §2.2 密钥 | 强随机 JWT_SECRET/API_TOKEN；DEBUG=false 下默认值拒启 | `[实测]` 本机 `.env` 现状为 **dev 形态**：`DEBUG=true`、**无 `ENV_NAME` 行**、`JWT_SECRET` = 公开默认值 `dev-secret-key-change-in-production`（len=35）、**`API_TOKEN` 缺失**、**无 `CORS_ORIGINS`** | ⚠️ 现状与「生产段」不符，属**预期**（本机是 dev）；但说明"照 §3② 配生产"时必须改 3 项以上 |
| §3① checkout | `edu-agent/` 与 `edu-frontend/` 必须同级 | `[实测]` 二者同级；`deploy.mjs:27` `FRONTEND_DIR = BACKEND_DIR/../edu-frontend` 印证 | ✅ 一致 |
| §3② 配置 .env | `cd edu-agent` → `copy .env.example .env`（然后编辑） | `[实测+代码佐证]` **本机 `.env` 已存在且是能跑的 dev 形态**；`.env.example` 是 **prod 模板**（`DEBUG=false`/`ENV_NAME=prod`/全部密钥为 `REPLACE_ME_*`）。本机 `.env` 被 `edu-agent/.gitignore:1:.env` 忽略 → **覆盖后无法从 git 恢复** | ❌ **隐患**（见 §C-D6）：README 对「已有 .env」**零警示**，与 §3③ 的强警示形成刺眼反差 |
| §3③ 数据库初始化 | ⚠ 已有库判别（执行前必查，≠0 即停）+ 两条恢复命令 | `[实测]` 判别命令原样跑出 **104**（≠0 → 正确触发「即停」）。分叉数据独立复核见下表 | ✅ **警示有效且事实为真** |
| §3④ 一键拉起 | `node scripts\deploy\deploy.mjs start`（前置检查→后端→前端 build+start→自动 check-demo） | `[实测]` 命令可跑通；但**本机 8000/3000 均已被占用 → 走幂等路径跳过前后端**，脚本**完全没有触碰 `.next-prod`**，随后照常跑 check-demo 并报绿 | ⚠️ **假绿陷阱**（见 §C-D13）：照做≠验到生产形态 |
| §3⑤ 验收 | `node scripts\check-demo.mjs` → 期望 `汇总: 绿 9/9 —— 演示环境就绪` | `[实测]` 逐字命中 | ✅ 一致 |
| §4 故障表 | ①–⑨ 行 + 三分支 + 已知项 A/B/C | `[实测]` ⑨ 行存在且与脚本第 9 项对齐；① 的 VMX 路径**真实存在**；⑨ 的 html 文件**真实存在**；§已知项 C（BGE-M3 目录缺失、8601 未运行）为非阻断降级 | ✅ 结构完整（但处置指引与脚本输出不一致，见 §C-D4） |
| §5 三命令 | `start` / `stop` / `stop --all` / `status` | `[实测]` `status` 跑通（exit 0，透传 check-demo）；`start` 跑通（幂等路径）；`deploy.mjs` 入口确有 `start/stop/status` 三支 + `--all` 开关 | ✅ 一致 |
| §5 巡检建议 4 | `docker inspect edu-redis-standalone` → `RestartPolicy.Name = unless-stopped` | `[实测]` `/edu-redis-standalone RestartPolicy=unless-stopped Running=true` | ✅ 一致 |
| §5 数据安全红线 | 禁 DB 直写；操作前快照；恢复按 §3③ 并验 106 表 | `[实测]` 措辞自洽；但"恢复"这一条**未回带 §3③ 的「非空即停」警示** | ⚠️ 小缺口（见 §C-D5） |
| §6 边界 | 本机同构、不含公网/HTTPS | `[文档原文]` 表述清晰 | ✅ |
| 附录 容器化 | compose + 两 Dockerfile + `.dockerignore`；`pdfplumber==0.11.10` 需在 backend.Dockerfile 同步声明（勿遗漏） | `[实测]` compose/Dockerfile/`.dockerignore` 均存在；**`backend.Dockerfile` 依赖段无 pdfplumber**，且 `edu-agent/requirements*.txt` **不存在** | ❌ **未落地**（见 §C-D9）。注：本机 venv 内 pdfplumber 0.11.10 **已装**，故本机路线不受影响 |
| 附录 出包检查单 | ①无 token→401 ②伪 token→401 ③X-Force-Role→401 ④/api/metrics→401 ⑤死链扫描 | `[实测]` ②→401 ✅、④→401 ✅、⑤脚本存在 ✅；但①→**200**、③→**200**（因本机 DEBUG=true）。检查单第 0 步已声明前置是 DEBUG=false，故逻辑自洽 | ⚠️ 本机现状跑该单会有 2 项红，新人易误判（见 §D 忠告 3） |

### A-③ 已有库判别——事实独立复核（我自己算的，没引用任何报告）

| 断言（README §3③ 原文） | 我的复核 | 判定 |
|---|---|---|
| 两条恢复命令都是**破坏性覆盖导入** | `[代码佐证]` dump 内 `CREATE DATABASE IF NOT EXISTS edu` + `USE edu` + 全表先 DROP | ✅ |
| dump 内含 **106 条 `DROP TABLE`** | `[实测]` `grep -cE "^DROP TABLE"` = **106** | ✅ 准确 |
| 本仓库实测 `edu` 库当前 **104 表** | `[实测]` `information_schema` = **104** | ✅ 准确 |
| **dump 独有 11 张**（`admin_*`×7、`curriculum_*`×4） | `[实测]` 集合差 = **11 张**，恰好 `admin_*`×7 + `curriculum_*`×4 | ✅ **精确命中** |
| **现库独有 9 张**（`user_memory*`、`hitl_approval`、`task_execution`、`course_review`、`knowledge_import_task` 等） | `[实测]` 集合差 = **9 张**：`_rwtest`、`course_review`、`hitl_approval`、`knowledge_import_task`、`mcp_tool_description_review_log`、`task_execution`、`user_memory`、`user_memory_entity_seq`、`user_memory_event`（README 点名的 7 张全在其中，另 2 张由「等」覆盖） | ✅ 准确 |
| 交集自洽（106−11 = 95 = 104−9） | `[实测]` 交集 = **95** | ✅ 算术自洽 |
| 现库 2026-09-13 以来的真实订单数据一并回滚 | `[实测]` `order` 表 80377 行，跨度 `2024-09-03` → **`2026-09-15 01:25:55`**（即今天）；`created_at >= 2026-09-13` 共 **19 条** | ✅ 准确（dump 为 08-16，等于回滚约 1 个月） |

> **新人视角（原样记录）**：作为第一次拿到这份 runbook 的人，我读到 §3③ 时**确实停下来了**——它不是一行小字注释，而是独立的 `>` 引用块、带 ⚠、标题里直接写「执行前必查，P1 数据损失风险」，并且**把判别命令给了出来**（不是「请自行确认库是否为空」这种空话）。我照抄命令跑出 104，块内明写「结果 ≠0 即停」，于是我没有执行下面的 `mysql < ...edu_full_dump.sql`。**这条警示达到了目的。**
>
> 唯一让我犹豫的是括注「（清 11 张新表 + 数据回滚 1 个月）」：11 张是 **dump 独有**的表（现库根本没有，恢复是**新建**它们），说成「清 11 张新表」在字面上是反的；真正会**丢失**的是那 **9 张现库独有表**。结论方向不错，但新手若细读会短暂困惑。

---

## B. check-demo 逐项（原样输出 + ⑧ 新语义）

命令：`cd edu-agent && node scripts/check-demo.mjs`（复跑 6 次，含 `deploy.mjs status` / `start` 内嵌各 1 次）

```
=== EduAgent 演示前检查单 check-demo.mjs ===
[PASS] ①. Milvus 连通 192.168.85.101:19530 (7ms)
[PASS] ②. Redis(docker exec edu-redis-standalone redis-cli ping) (1334ms)  PONG
[PASS] ③. MongoDB 连通 192.168.85.101:27017 (4ms)
[PASS] ④. 后端 8000 /health (83ms)  status=ok v0.3.0
[PASS] ⑤. 前端 3000 /login-register.html (37ms)
[PASS] ⑥. 登录链路 login×2 + /api/auth/me×2 (1037ms)  adm02test(role=admin,user_id=100003) + user000001(role=student,user_id=1)
[PASS] ⑦. 关键页 200 × 8 (78ms)  8/8 全 200
[WARN] ⑧. advisory: DEBUG 虚拟管理员探测(无 token /api/users/me,三分支) (32ms)
       -> DEBUG=true 虚拟管理员漏洞,上线前必须 False(settings.DEBUG=false 并重启后端) [WARN 开发态虚拟管理员后门存在(DEBUG=true,ENV_NAME=local);部署前必须 DEBUG=false,见 P1-8 ENV_NAME 门]
[PASS] ⑨. 抽验页 200 /admin-users-refine-proto.html(C5-D2) (7ms)

汇总: 绿 9/9,WARN ⑧ —— 演示环境就绪 (检查耗时 2619ms)   ← exit code 0
```

**逐项**：①–⑦、⑨ 全部 PASS `[实测]`；⑧ 为 WARN（软，不阻断 exit）。项目数 ①–⑨ = **9 项**，与 README §5 口径一致。

### B-⑧ 新语义确认

`[实测]` 输出**不再是**旧的假「DEBUG 安全」，而是点名了真实后门与所需动作：
`WARN 开发态虚拟管理员后门存在(DEBUG=true,ENV_NAME=local);部署前必须 DEBUG=false,见 P1-8 ENV_NAME 门`

并已由我独立验证后门**真实存在**（非文案）：

| 探测 | 结果 | 判定 |
|---|---|---|
| `GET /api/users/me` 无 token | `[实测]` **HTTP 200**，body `{"code":0,...,"user_id":1,"role":"admin","nickname":"小柚子同学","email":"debug@edu.agent","real_name":"调试用户"}` | 虚拟管理员后门**活** |
| `GET /api/users/me` + `X-Force-Role: admin`（无 token） | `[实测]` **HTTP 200**，`"email":"debug_admin@edu.agent"`、`"real_name":"调试用户(admin)"` | X-Force 后门**也活** |
| `GET /api/users/me` + 伪 token | `[实测]` **401** `{"code":"40101"}` | 伪 token 路径正常 |
| `GET /api/metrics/cache-context-dashboard` 无 token | `[实测]` **401**（与附录检查单④期望一致） | ✅ |
| 裸 `GET /metrics` 无 token | `[实测]` **200**（README 附录已自行登记该盲区） | ✅ 文档诚实 |

### B-⑧ 三分支真实输出矩阵

| 分支 | 条件 | 取得方式 | 原始输出 | exit |
|---|---|---|---|---|
| **A（安全）** | 无 token 被 401/403 | `[实测-合成]` 隔离 harness（临时目录，脚本副本 + 合成 `.env`）+ 本机 401 模拟后端（8099，测毕即杀）。**真机无法取得**：本机 DEBUG=true，后端必返 200 | `[PASS] ⑧ ...  无 token 被 401 拒绝(DEBUG 安全)` | 0 |
| **B（开发态）** | DEBUG=true + ENV_NAME=local（或缺省） | `[实测-真机]` 本机真实 `.env`（DEBUG=true，无 ENV_NAME → 缺省 local）+ 真后端 | `[WARN] ... WARN 开发态虚拟管理员后门存在(DEBUG=true,ENV_NAME=local);部署前必须 DEBUG=false,见 P1-8 ENV_NAME 门` | **0** |
| **C（危险）** | DEBUG=true + ENV_NAME≠local（真后门） | `[实测-半合成]` 后端用**真机 8000**（真 200），仅 `.env` 的 `ENV_NAME` 由我合成 `prod` | `[WARN] ... [无 token 返回 HTTP 200 有数据(DEBUG=true,ENV_NAME=prod);上线前必须 DEBUG=false]`，汇总仍 `绿 9/9,WARN ⑧ —— 演示环境就绪` | **0** ❗ |

> ❗ **⑧ 分支 C 与脚本自身声明矛盾 → 假绿（本轮 P1）**
> - `[代码佐证]` `check-demo.mjs:253` 注释：「C) 返回 200/有数据且 DEBUG=true + ENV_NAME≠local → **红,阻断 exit 1**(真后门/非本地即危险)」
> - `[代码佐证]` 但 `check-demo.mjs:277` 把 `{ __warn: true, __fix: FIX.debug }` 绑在 **`debugCheck` 函数本身**；`check-demo.mjs:142` `isWarn = fn.__warn && !r.ok` ⇒ **三个分支一律 isWarn=true**；`check-demo.mjs:290` 只把「非 ok 且非 warn」计入 `red`；`check-demo.mjs:300` `process.exit(red.length === 0 ? 0 : 1)`。
> - `[实测]` 结果：分支 C 打印 `[WARN]`（而非 `[FAIL]`）、汇总报 `绿 9/9 —— 演示环境就绪`、**exit 0**。
> - **影响**：最该拦住的那一种误配（生产环境挂着活的后门）被静默降级，CI/巡检无法据此拦截。这正是本次任务点名的「200 也绿 / 静默降级」同类问题，只不过发生在**检查脚本自己**身上。

### B-⑦/⑨「只验 200」的边界（按任务要求单独交代）

`[代码佐证]` ⑦ 仅对 8 个 URL 逐一断言 HTTP 200（`check-demo.mjs:238-247`），⑨ 同（`:282-284`）。**9/9 绿 ≠ 页面数据是活的**。

为不让本轮结论停在「200 即过」，我另做了**数据活性**验证（curl + 真 token，未用 Playwright）：

| 页面 | 页面所依赖 API（从 HTML 抽取） | 带真实 token 实测 |
|---|---|---|
| dashboard | `/api/users/me`、`/api/progress/dashboard`、`/api/gamification/me/{points,badges,rankings}` | `[实测]` 全 200 且有值：`total_days=1`、`total_study_seconds=6664`、`total_questions_attempted=14`、`total_points=351`、`level_title="萌新"`、`badges total=8/unlocked=3` |
| courses | `/api/series`、`/api/users/me`、`/api/gamification/me/points`、`/api/progress/dashboard` | `[实测]` `/api/series` 200，`total=2628`，返回 12.5KB 真实 items |
| learning | `/api/enrollments/me/cohorts`、`/api/study/courses/{id}/outline`、`/api/progress/dashboard` | `[实测]` `/api/enrollments/me/cohorts` 200（1178B，真实 `enrollment_id=68939`）。注：我一开始用裸 `/api/study/courses/` 探得 404 —— 核对页面源码后确认**页面从不调该路径**（只调 `{id}/outline`、`{id}/access`），属我自己的探针错误，非缺陷 |
| admin-dashboard / admin-mcp | `/api/auth/me`、`/api/mcp/servers`、`/api/mcp/tools` | `[实测]` 200，`/api/mcp/servers` 5814B、`/api/mcp/tools` 2021B |
| admin-rag-upload | `/api/knowledge/{partitions,tasks,status}` | `[实测]` 200，`partitions` 146B、`tasks` 8527B |

`[实测]` 页面源码确实引用 `edu-api.js`（1–2 处）并含 5–30 处 `/api/...` 调用 ⇒ **非静态死壳**。
**结论**：本机 9/9 绿**确有活数据背书**；但 **⑦/⑨ 这个门本身分辨不出死活**，README 仅在 §4 ⑦ 用「页面能开但数据全空 → 见已知项 A」侧面提示，未明说「⑦ 是纯 200 断言」。`[文档原文]`

### B-⑥ 限流陷阱（实测踩到，未在文档登记）

`[实测]` 我在 60 秒内连续多跑 check-demo（含 harness 复跑）后，⑥ 立刻转红且**仅耗 12–25ms**：

```
[FAIL] ⑥. 登录链路 login×2 + /api/auth/me×2 (12ms)
汇总: 绿 7/9,红项 ⑥,WARN ⑧ —— 请按上方指引处置后重跑
```

直接探测登录接口求真因：`[实测]` `HTTP 429` `{"code":"42900","message":"请求过于频繁，请 60 秒后再试"}`。
等待 65s 后单跑 → **恢复 `绿 9/9`**、⑥ 耗时回到 1424ms。

`[代码佐证]` ⑥ 的 FAIL 指引为「先过 ④ 后端…（若账号失效查 DB 种子）」，**完全未提限流**；README §4 ⑥ 更进一步写「仍失败 = edu 库无种子数据，**按 §3 步骤③ 恢复快照**」。⇒ 形成一条**危险误导链**：重复跑 → ⑥ 红 → 顺着指引 → 走到 §3③ 的破坏性恢复。§3③ 的「非空即停」是这条链上唯一的拦阻。

---

## C. 残留偏差清单（我自己扫出来的；不引用任何历史报告）

> 说明：编排者提到的 `D-01/D-03/D-04/D-06/D-08/D-12/D-14/D-15` 是 **T3A 报告内部的编号池**。本轮为盲测（禁读该报告），**无法做 ID 级对账** —— 以下为我独立扫描得到的**全部**残留偏差，编号 `D#` 为本轮自定义。P3 池「应仍在」的预期**得到支持**（存量偏差确实仍可复现），但**哪些编号仍在，本轮无法声明**。

| # | 严重度 | 偏差 | 证据 |
|---|---|---|---|
| **D0** | **P1** | **check-demo ⑧ 分支 C 假绿**：注释声明「红/阻断 exit 1」，实现因 `__warn:true` 全分支软化为 WARN，生产误配（DEBUG=true+ENV_NAME≠local）仍报「绿 9/9 演示环境就绪」exit 0 | `[代码佐证]` `:253` vs `:277`/`:142`/`:290`/`:300`；`[实测]` §B-⑧ 分支 C |
| **D1** | P3 | **巡检耗时口径未纠偏**：README §4 ⑥「单项 6-10s 属正常波动」、§5.1「整轮巡检约 10-15 秒」。实测 6 次：脚本内部 **2543–3232ms**、wall **4561–5114ms**；⑥ **1035–1426ms**；且耗时最大项实为 **②（docker exec 1021–1558ms）**，与「⑥ 占大头」不符 | `[实测]` 6 次运行 |
| **D2** | P3 | **「220 键」未纠偏**：`.env.example:2` 仍写「对齐 app/config.py Settings 全字段，**220 项**」。实测 **Settings 类字段 = 242**（`config.py` 行 16–743）、模板键行 **230**（未注释 37 + 注释 193）。README §intro/§3② 引用的「未注释键 37 个」正确，但模板自身头注与实际三方都对不上 | `[实测]` 计数；`[代码佐证]` `config.py:16` |
| **D3** | P3 | **`deploy.mjs` 内部仍打 8/8**，同一屏与 check-demo 的 9/9 直接冲突：`=== ④ check-demo 断言(期望 8/8)===` → check-demo 打 `绿 9/9` → `[ OK ] check-demo 8/8 全绿——演示环境就绪`。文件头注释（行 9）与用法文案（行 333）同病 | `[实测]` §A §3④ 运行记录 |
| **D4** | P3 | **README §4 行 181「每行处置与脚本 FAIL 时输出的指引一致」不成立**。④ 脚本给手动 uvicorn 起法 / README 指向三分支；⑤ 脚本给 **`next dev`**（dev 形态！）/ README 给 `deploy.mjs start`（生产形态）；⑥ 脚本「查 DB 种子」/ README「按 §3③ 恢复快照」 | `[代码佐证]` `check-demo.mjs:157-163`；`[文档原文]` README:181,189,190 |
| **D5** | P3 | **§4 ⑥ 的处置未登记限流（429）**，且把「仍失败」导向 §3③ 破坏性恢复快照；§5 红线第 3 条「恢复」也未回带 §3③ 的「非空即停」警示 | `[实测]` 429 复现；`[文档原文]` README:190,268 |
| **D6** | **P2** | **§3② 无「已有 .env 判别」**：`copy .env.example .env` 会**覆盖**本机可用的 dev `.env`（`.env` 已被 `edu-agent/.gitignore` 忽略 ⇒ 覆盖不可恢复），而模板是 **prod 形态 + 全 `REPLACE_ME_*` 密钥** ⇒ 覆盖后后端直接拒启。**与 §3③ 煞费苦心的「已有库判别」形成鲜明对比：数据库有护栏，配置文件没有** | `[实测]` `.env` / `.env.example:41,43,63,380,404`；`[实测]` `git check-ignore` → `edu-agent/.gitignore:1:.env` |
| **D7** | P3 | §3③ 括注「（清 11 张新表 + 数据回滚 1 个月）」表述反了：11 张是 **dump 独有**（恢复后是**新建**），真正**丢失**的是 **9 张现库独有表** | `[实测]` §A-③ 集合差 |
| **D8** | P3 | README 附录引 `config.py 582-606` 有 fail-fast；实际 `_security_guard` 在 **`:665`**，公开密钥集合在 **`:674-675`** ⇒ 行号漂移、照行号翻不到 | `[代码佐证]` `config.py:665,674,675` |
| **D9** | P3 | 附录「`pdfplumber==0.11.10` 需在 `backend.Dockerfile` 与 `requirements*.txt` 同步声明，勿遗漏」**未落地**：`backend.Dockerfile` 依赖段（行 17–48）无 pdfplumber；`edu-agent/requirements*.txt` 不存在（「如适用」句兜了一半）。本机 venv 已装 0.11.10 ⇒ 只影响容器化路线 | `[实测]` grep + `backend.Dockerfile` 全文 |
| **D10** | P3 | `check-demo.mjs:1` 头注释仍写「task18 **七件套** + DEBUG advisory」，与自身「共 9 项检查」（`:9`）矛盾 | `[代码佐证]` `:1` vs `:9` |
| **D11** | P3 | ⑧ 分支 A 的 PASS 文案**硬编码**「(DEBUG 安全)」，即便 `DEBUG=true` 也照打 ⇒ 会让人误以为「DEBUG 无需关」 | `[代码佐证]` `:267`；`[实测]` §B-⑧ 分支 A |
| **D12** | P2 | **§3④「照做即验收」是假绿**：本机 8000/3000 已被占用 ⇒ `deploy.mjs start` 走幂等跳过，**从不 build/start `.next-prod`**，却照跑 check-demo 报绿。且当前 3000 实测是 **`next dev` 开发形态**（`/_next/static/development/_buildManifest.js` → **200**，prod 应为 404） ⇒ README §2.1/§3④ 所声明的「生产形态 build+start」**从未被这个验收门覆盖** | `[实测]` §3④ 运行记录；`[实测]` dev/prod 判别 |
| **D13** | P3 | 模板注释「DEBUG 回退 `"*"`」在 wire 层不成立：本机 DEBUG=true，实测响应头为 **回显具体 origin**（`access-control-allow-origin: http://127.0.0.1:3000`）+ `allow-credentials: true`（Starlette 对 `*`+credentials 的常规处理）。语义（宽松）无误，措辞不准 | `[实测]` 响应头；`[代码佐证]` `main.py:281-296` |
| **D14** | P3 | README §4 ⑧ 行让读者「见脚本注释三分支语义」，而该注释恰恰与实现相反（即 D0）⇒ 文档把新人引向了一个不可信的注释 | `[文档原文]` README:192 |
| **D15** | 提示 | `logs/deploy.pids.json` 在 README §5 被描述为 PID 记录点，但本机**不存在**（因为前后端非 deploy.mjs 拉起）；走 §3④ 幂等路径也不会生成 ⇒ 新人按 §5 找该文件会扑空 | `[实测]` |

**未发现偏差（已核对为真，记下以免后续误改）**：§4 ① 的 VMX 路径存在；§4 ⑨ 的 `admin-users-refine-proto.html` 存在；`§5.4` Redis `unless-stopped` 为真；§2.1 next 16.3.0 为真；`requires-python` 为真；CORS **双源回退实测有效**（`localhost:3000` 与 `127.0.0.1:3000` 均被正确允许）；`.env` 密钥零入库（gitignore）为真。

---

## D. 给下一位同事最该知道的 3 件事

1. **别以为在「已跑着的机器」上走一遍 §3④ 就等于验收了生产形态。**
   `deploy.mjs start` 遇到 8000/3000 已监听会**幂等跳过**前后端、**根本不碰 `.next-prod`**，然后照样打出「全绿」。本机实测 3000 是 **`next dev` 开发形态**（`/_next/static/development/_buildManifest.js` 返回 200，生产应为 404）。要真正验生产形态，必须先 `node scripts\deploy\deploy.mjs stop` 再 `start`；并且**别信 `deploy.mjs` 打印的「8/8」，它以 check-demo 的 `9/9` 为准**（同一个脚本里的数字是旧的）。

2. **check-demo 的 ⑥ 一旦变红，先等 60 秒，不要动数据库。**
   ⑥ 红最常见的原因不是「种子数据没了」，而是**登录限流**（实测 `HTTP 429 / code 42900`，限流窗口 60s / 同 IP 同路径）。间隔太近连跑两次就会红，且失败快得离谱（12–25ms）。而 §4 ⑥ 的处置会把你引向 §3③ 的**破坏性恢复快照** —— 本机 `edu` 库是**非空**的 104 表、`order` 表有到今天的 80377 行数据。**先等 60 秒重跑；仍红再查账号。**

3. **绝对不要执行 `copy .env.example .env`。**
   本机 `.env` 是**能跑起来的 dev 形态**且已被 gitignore ⇒ **覆盖后无法从 git 恢复**；而 `.env.example` 是 **prod 模板**（`DEBUG=false` / `ENV_NAME=prod` / `JWT_SECRET`、`API_TOKEN`、`MYSQL_PASSWORD`、`LLM_API_KEY` 全是 `REPLACE_ME_*`），覆盖后后端会 fail-fast 直接拒启。§3② 对「已有 .env」**没有任何警示**——这与 §3③ 对「已有库」的强力拦截完全不对称，请自己补上这一道判断（改前先 `cp .env .env.bak`）。
   *附带提醒*：本机 `.env` 里 `JWT_SECRET` 仍是**公开默认值**、`API_TOKEN` **缺失**、`ENV_NAME` **未设置** —— 一旦要转生产形态（`DEBUG=false`），这 3 项不补后端必然拒启（§4「8000 拒启三分支」第 1 行）。

---

## 附录：本轮用到的关键命令（可复跑）

```bash
# ① 已有库判别（README §3③ 原样）
mysql -uroot -p -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='edu'"   # →104（≠0 即停）

# ② dump 与现库分叉（我自己算的复核口径）
grep -cE "^DROP TABLE" deploy/backups/20260816_task00/edu_full_dump.sql                          # →106
mysql -uroot -N -e "SELECT table_name FROM information_schema.tables WHERE table_schema='edu'" | sort > live.txt
grep -oE "^DROP TABLE IF EXISTS \`[^\`]+\`" .../edu_full_dump.sql | sed 's/.*`\(.*\)`/\1/' | sort > dump.txt
comm -23 live.txt dump.txt   # 现库独有 → 9 张     comm -13 live.txt dump.txt   # dump 独有 → 11 张

# ③ check-demo（含耗时/exit code）
cd edu-agent && node scripts/check-demo.mjs; echo "exit=$?"

# ④ ⑧ 后门真实性（不经脚本）
curl -s --noproxy '*' http://127.0.0.1:8000/api/users/me                 # →200 虚拟管理员（无 token！）
curl -s --noproxy '*' -H "X-Force-Role: admin" http://127.0.0.1:8000/api/users/me   # →200 debug_admin

# ⑤ dev / prod 形态判别（无需 Playwright）
curl -s --noproxy '*' -o /dev/null -w "%{http_code}\n" \
  http://127.0.0.1:3000/_next/static/development/_buildManifest.js       # →200 说明是 next dev

# ⑥ 限流窗口复位
sleep 65 && cd edu-agent && node scripts/check-demo.mjs                   # →恢复 绿 9/9
```

**自清声明**：临时脚手架目录 `%TEMP%\cdtest_t5\`（脚本副本 + 合成 `.env` + 401 模拟后端）**已删除**；模拟后端 8099 **已杀且端口已释放**；限流窗口**已等待复位**（末次为 `绿 9/9`）；未对 `.env`、`.env.example`、数据库、后端/前端进程做任何写操作。仓库内**仅新增本报告**一个文件。
