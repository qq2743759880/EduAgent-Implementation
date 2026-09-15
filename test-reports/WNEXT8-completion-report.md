# W-NEXT-8 文档/数据治理批 完工报告（T5-C3/C4/C5/C6、T7-C2/C3、T8-C3、T9-C2）

> 执行者：W-NEXT-8 工程师（单写者，锁 `edu-agent/scripts/eval/wnext8.lock`）
> 批判源：`test-reports/critique-blind-t4-t9.md`
> 分支：`feature/opt-waves`；本批基线 HEAD `1c4dbd9`
> 文件归属（仅限）：`deploy/README.md`、`edu-agent/scripts/deploy/deploy.mjs`、`edu-agent/.env.example`、`AGENTS.md`、`edu-agent/app/domains/course_admin/router.py`（任务六显式授权）、`test-reports/WNEXT8-completion-report.md`、一次性清理脚本。**未动 `check-demo.mjs`（W-NEXT-5 领地）、前端、contracts、其它 `app/**`。**

---

## 0. 一句话结论

7 个任务中 **6 项闭环**（任务一/二/三/四/六/七），**任务五（3 条孤儿题软删）已完成只读复核 + 备份，`-Execute` 软删待人工确认**（脚本闸门默认 dry-run，不会误写库）。

---

## 1. 逐项 GWT + 证据

### 任务一【P2】README §3② 已有 .env 判别护栏（T5-C3）✅
- 改动：`deploy/README.md` §3② 命令块前插入 ⚠ 警示块（L99-116），含三点：① 备份命令 `cp .env .env.bak` / `copy .env .env.bak`；② `.env` 已被 `.gitignore` 忽略、**覆盖后无法从 git 恢复**；③ `.env.example` 是生产模板（实测 `DEBUG=false`、`ENV_NAME=prod`，6 个必填密钥全为 `REPLACE_ME_*`）→ 直接覆盖会让后端 `_security_guard` fail-fast 拒启。命令块行尾补「仅当 .env 不存在时用；已存在先备份再逐键改」。
- 实证：`Select-String '已有 .env 判别'` 命中 1 处；`REPLACE_ME_` 在 `.env.example` 命中 6 个键（MYSQL_PASSWORD/NEO4J_PASSWORD/MINIO_SECRET_KEY/LLM_API_KEY/JWT_SECRET/API_TOKEN）。
- **独立复核（子代理）**：三点齐备，无缺项 → PASS。

### 任务二【P2】§4⑥ 限流登记 + §5 红线回带（T5-C4）✅
- 改动：§4 ⑥ 处置**首句**改为「**先等 60 秒重跑**（登录限流 42900/60s 窗口，密集连跑必红，12-25ms 快失败即限流特征）」，并加「**勿直接恢复快照**——§3③ 仅适用全新空库，本机非空库执行＝破坏性覆盖＋数据回滚」；§5「数据安全红线」第 3 条回带 §3③「非空即停」（`information_schema.tables` 计数 ≠0 即停）。
- 实证：README L205 / L283 命中；错误码核证 `app/common/error_codes.py:41 RATE_LIMITED="42900"`。
- **独立复核**：PASS。

### 任务三【P3】deploy.mjs 9/9 + .env.example 键数 + 巡检耗时（T5-C5）✅（耗时口径按实测修正）
- `deploy.mjs`：4 处 `8/8` → `9/9`（头部注释、断言横幅、成功文案、usage）；`grep "8/8" deploy.mjs` = **0**（`9/9` × 4）；`node --check` 通过。
- `.env.example` 头注（L2-4）改为实测值。**自测数字**（正则口径）：`app/config.py` Settings 字段 **242**；模板键 **230**（含注释）/ 未注释 **37**；Settings 中未列入模板的 **15** 个（`STREAM_VIA_GRAPH`、`SIXNODE_*`×5、`GUARD_SLOT_TTL`、`MEMORY_*`×5、`TOOL_DECISION_*`×2、`RERANK_*`×2）。原「220 项」已不存在。
- README 巡检耗时：`10-15 秒` 残留 = **0**；改为「整轮巡检约 **2-7 秒**（实测样本 1.8s / 2.3s / 2.6s / 6.6s，全红快失败 <1s）；**最大单项在 ② Redis docker exec（0.5-1.3s）与 ⑥ 登录链路（1.0-1.2s）之间波动**」。⚠ **与批判给定的「最大项更正为②」有偏差**：本轮两方实测（本机 1843ms：② 510ms / ⑥ 985ms；独立验收员 2331ms：② 760ms / **⑥ 1227ms**）显示 ⑥ 可超 ②，故按实测写成「两者波动」，不写死 ②。
- **独立复核**：`8/8`=0、头注 242/230/37/15 全符、无「10-15」→ PASS；并给出上述耗时反例（已据其修正，见 §2）。

### 任务四【P3】§4 处置表对齐脚本 FAIL 输出（T5-C6）✅
- 改动：§4 表 9 行「处置」列全部重写为**逐字给出脚本原文指引**（`FIX` 表 / 各 `check()` 的 `__fix`），并在前后补前置判断；表头说明同步改为「每行「处置」**逐字引用** `check-demo.mjs` FAIL 时打印的 `-> …` 指引（`FIX` 表 / 各 `check()` 的 `__fix`，含原文半角标点），其前后按本机实测补充前置判断…⑤⑦⑨ 共用前端指引 `FIX.frontend`」。
- 对照结果（脚本当前版本，独立验收员逐行比对）：①③（`FIX.vm`）、②（`FIX.redis`）、④（`FIX.backend`）、⑧（`FIX.debug`）**逐字一致**；⑤（形态判别 fix 原文，含半角 `(验生产形态:deploy.mjs stop 后 start,先 build 再起)`）、⑥（`先过 ④ 后端: …uvicorn…(若账号失效查 DB 种子)`）、⑦（`FIX.frontend`）均已按原文回填。
- **逐字校验（可复跑）**：`Grep 'docker start edu-redis-standalone\(若 docker 引擎未运行,先启动 Docker Desktop\)'  deploy/README.md` → 命中 L201；`Grep 'next dev -p 3000\(验生产形态:deploy\.mjs stop 后 start,先 build 再起\)'` → 命中 L204；脚本侧对应原文在 `check-demo.mjs:162`（`FIX.redis`）与 `:228`（⑤ `__fix`）——两侧半角标点一致。
- 附带同步：`check-demo.mjs` 在本批执行期间被 **W-NEXT-5** 落地了 T5-C1/C2/C6（⑤ 新增「生产形态判别」WARN 分支、⑧ 分支 A 文案动态化、⑧ 分支 C 判据改为「ENV_NAME 缺省即非 local → 红」）。本批**只改 README**，按新语义同步了 §3⑤ 期望值、§4 ⑤/⑧ 行、§5 巡检告警说明。

### 任务五【P2】3 条历史孤儿题数据治理（T7-C2）⏸ 待人工确认
- ① 只读复核（两次独立执行，结果一致）：

| id | question_code | bank_id | q.yn | b.yn |
|---|---|---|---|---|
| 10537 | LIANQ-IMP-444227-1 | 452 | 1 | 0 |
| 10538 | LIANQ-IMP-444227-2 | 452 | 1 | 0 |
| 10539 | UI-IMP-777222-1 | 453 | 1 | 0 |

  孤儿计数 `SELECT COUNT(*) … WHERE q.yn=1 AND b.yn=0` = **3**（与批判锚点一致）。
- ② 备份已落盘：`deploy/backups/wnext8_orphan_questions_20260916_011018.sql`（3630 bytes，**无 BOM**，首 3 字节 `45,45,32`），含 `question` 10537-10539 与 `question_bank` 452/453 两条 `INSERT INTO`（`--where` 限定行，导入端可直接 source 回放）。备份目录已 .gitignore。
- ③ 一次性脚本：`edu-agent/scripts/eval/wnext8_orphan_questions_cleanup.ps1`（UTF-8 BOM，Windows PowerShell 5.1 中文注释安全）。安全设计经独立判读确认：默认 **dry-run 不写库**（`if (-not $Execute) { … exit 0 }` 在 UPDATE 之前）、UPDATE 带 `WHERE yn = 1 AND id IN (…)` **幂等**、备份为空即 `throw` 中止。实测 dry-run 输出：`孤儿题总数 = 3`、`预演 SQL … 预计影响 3 行`、备份落盘 ✓。
- ④ **软删未执行**（脚本未加 `-Execute`）：复核仍为 3 行（10537-10539 的 `yn` 全为 1）。**待人工确认后执行**：`powershell -File scripts\eval\wnext8_orphan_questions_cleanup.ps1 -Execute`。
- GWT 状态：备份存在 ✅；清理后 = 0 行 **待确认后复验**。

### 任务六【P3】课次删除 summary 与实现对齐（T7-C3）✅
- 改动：`course_admin/router.py:209` summary「管理端·软删课次（yn=0）」→「**管理端·删除课次（物理删除，不可恢复；被引用则 40908）**」。
- 实证：`service.py:428-443 delete_session` 为 `_session_repo.hard_delete()`（`series_cohort_session` 无 yn 列），引用>0 抛 40908 → 文案与实现一致；`py_compile` 通过。**未改实现**（真软删需变更单，本批不做）。

### 任务七【P2】记忆落库口径 + resume 401 登记（T9-C2 + T8-C3）✅
- `AGENTS.md` 关键教训新增第 11 条：默认 `MEMORY_EVENT_ENABLED=true`（`config.py:373`）→ 事实源 `user_memory_event`（append-only，工厂 `persistence.py:212`），**HEAD 判据 = `valid_to IS NULL AND event_type <> 'delete'`**（`event_persistence.py:68`），`user_memory` 是快照表、行数少不等于没落库。实测 2026-09-16：`user_memory_event` 16 行 / `user_memory` 2 行 / HEAD 2 行。
  > 注：初稿写「有效记录 = `event_type='create'` 且 `valid_to IS NULL`」，独立验收员指出代码 HEAD 判据是 `event_type <> 'delete'`，已按代码口径改正。
- `deploy/README.md` task123 检查单新增第 6 条：`POST /api/chat/resume` 无 token 必须 401，并登记「生产 DEBUG=false 的 401 行为待本检查单窗口实测」。**dev 态实测（本轮真 HTTP）**：无 token `POST /api/chat/resume` → **HTTP 404 + `{"code":"40450","message":"确认请求已超时或不存在…"}`**；同轮无 token `GET /api/users/me` → **200**（虚拟管理员）。**未改代码**（DEBUG 语义为既有设计）。

---

## 2. 独立实证验收（子代理，对抗式）与返工

独立验收员（另起子代理，只读 + 真跑命令）共两轮。**第 1 轮**结论：A/B/C/E/F 成立；**D 部分不成立、C 有反例、G 有表述偏差**。**第 2 轮复验**结论：2/3/4 与排他检查 PASS，任务四仍报 **FAIL（2 行未逐字命中）**，并追加一条耗时反例。已全部返工：

| 轮次 | 验收发现 | 处置 |
|---|---|---|
| 1 | D：§4 ⑥ 首句「先等 60 秒」不属脚本 FIX 原文，表头「逐字对齐」不成立；⑤⑦⑨ 文案有出入 | 表头改为「逐字引用脚本原文 + 前后补前置判断」；⑥ 行补脚本原文；⑦⑨ 明确标注 `FIX.frontend` 原文（保留 ⑥ 限流前置说明——任务二 GWT 要求） |
| 1 | C：实测样本 2331ms、最大单项是 ⑥（1227ms）而非 ②（760ms），「最大项是 ②」「约 3-7 秒」口径不实 | §5 与 §4⑥ 改为「约 2-7 秒」＋「最大项在 ②/⑥ 之间波动」，并列出实测样本 |
| 1 | G：AGENTS.md 第 11 条 `event_type='create'` 与代码 HEAD 判据（`event_type <> 'delete'`）不符 | 按 `event_persistence.py:68` 代码口径改写并标注行号 |
| 1 | E：孤儿题仍 3 行（软删未执行） | 属流程预期（人工确认闸门），已在 §1 任务五与本报告结论中显式登记 |
| 2 | **任务四 FAIL**：② 行 `FIX.redis` 指令命中但 4 处半角标点被写成全角（`(`→`（`、`,`→`，`、`)`→`）`）；⑤ 行后缀 `(验生产形态:deploy.mjs stop 后 start,先 build 再起)` 被改写为「（脚本指引＝dev 形态；验生产形态：`deploy.mjs stop` 后 `start`，先 build 再起）」（加反引号 + 全角标点 + 措辞重排） | ②⑤ 两行改为**逐字原文**（② `docker start edu-redis-standalone(若 docker 引擎未运行,先启动 Docker Desktop)`；⑤ `cd edu-frontend && node node_modules/next/dist/bin/next dev -p 3000(验生产形态:deploy.mjs stop 后 start,先 build 再起)`），表头自述同步补「含原文半角标点」（见 §1 任务四逐字校验） |
| 2 | 复验轮实测 `检查耗时 27208ms`（①④⑥ 红：VM/后端未起，④ 单项 5541ms 最大），§5「2-7 秒」只在全绿态成立，未注明红态 | §5 第 1 条补注：②/③ 走 socket 超时 3s、④-⑨ 走 HTTP 超时 5s，**红态整轮 10-30s 属正常**，并登记本例 27.2s / ④ 5.54s |

---

## 3. 交付物清单

| 文件 | 变更 |
|---|---|
| `deploy/README.md` | §3② 护栏；§3⑤ 期望值；§4 表 9 行处置逐行对齐；§5 耗时口径 + 红线3 回带；task123 检查单新增 resume 401 项 |
| `edu-agent/scripts/deploy/deploy.mjs` | `8/8` → `9/9`（4 处） |
| `edu-agent/.env.example` | 头注键数实测纠偏（220 → 242/230/37/15） |
| `edu-agent/app/domains/course_admin/router.py` | 课次删除 summary 对齐 hard_delete |
| `AGENTS.md` | 关键教训新增第 11 条（记忆落库口径） |
| `edu-agent/scripts/eval/wnext8_orphan_questions_cleanup.ps1` | 新增：孤儿题只读复核+备份+人工确认+幂等软删（默认 dry-run） |
| `deploy/backups/wnext8_orphan_questions_20260916_011018.sql` | 备份产物（gitignore，不入库） |
| `test-reports/WNEXT8-completion-report.md` | 本报告 |

**未做/未闭环**：任务五的 `UPDATE question SET yn=0`（待人工确认）；`check-demo.mjs`  分支 A 文案（W-NEXT-5 领地，其已完成）；README 之外任何前端/契约/`check-demo` 改动。

---

## 4. 环境事实登记（本轮实测）

- 开工时 **8000 后端未运行**（`/health` fetch failed），本批按 §4④ 原文手工拉起 `.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`（未改 .env；`DEBUG=true`、`ENV_NAME` 缺省）。3000 前端在跑（dev 形态）。
- 结果：`check-demo.mjs` = `绿 7/9,红项 ⑧,WARN ⑤ (1843ms)`。其中 ⑧ 红因 `.env` 未写 `ENV_NAME=local`（W-NEXT-5 新语义：缺省=非 local → 分支 C 红），⑤ WARN 因前端为 dev 形态——**均为本机 dev 形态的既有预期，非本批缺陷**。
- 单写者锁：`edu-agent/scripts/eval/wnext8.lock`（任务五闭环后删除）。

---

## 5. 交付 commit 列表（分支 `feature/opt-waves`）

| commit | 标题 | 文件 |
|---|---|---|
| `5542b5d` | `docs(w)/WNEXT8-readme-env-guard` | `deploy/README.md`、`AGENTS.md` |
| `3645e7a` | `chore(w)/WNEXT8-deploy-98` | `edu-agent/scripts/deploy/deploy.mjs`、`edu-agent/.env.example`、`edu-agent/app/domains/course_admin/router.py` |
| `69c5cdb` | `fix(w)/WNEXT8-orphan-questions` | `edu-agent/scripts/eval/wnext8_orphan_questions_cleanup.ps1`（新增） |
| `3da0ddb` | `docs(reports)/WNEXT8-completion-report` | 本报告 |

- 开工基线 HEAD `1c4dbd9`；本批执行期间仓库为**多写者共享**（W-NEXT-5/9 相继在 `feature/opt-waves` 落 commit，如 `35e98d7`/`677e763`/`df5f8ca`），故各 commit 的父节点非固定基线——已用 `git merge-base --is-ancestor` 逐条确认 4 个 commit 均在 HEAD 祖先链上。
- 仅 stage 本批归属文件；工作树中 W-NEXT-9 的 `edu-frontend/public/*.html` 等改动未被本批提交。
- 已知瑕疵（非内容问题）：首条 commit 消息中的 `§` 字符被 PowerShell 控制台编码吞掉（显示为 `S4`/`S5`），后续 commit 一律避免使用该字符；因系共享历史且其上已有他人 commit，未做 amend。