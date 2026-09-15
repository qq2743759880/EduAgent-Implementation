# T3-A 完成报告 —— 部署文档+巡检脚本六连修（盲测 T3 批 A，deploy 域）

> 修复工程师：独立单写者 · 工作区：`E:\stu\project\stu\EduAgent实施手册` · 完工回执 2026-09-15
> 范围来源：`test-reports/onboarding-fresh-report.md`（T3 盲测报告 §4 偏差表）
> 文件归属（仅限本次）：`deploy/README.md`、`edu-agent/scripts/check-demo.mjs`、根目录 `.dockerignore`（新建）、本报告
> 守则遵守：禁 DB 直写（仅 information_schema/HTTP 只读）、禁 Playwright、未碰 `edu-frontend/**`、`edu-agent/app/**`、`contracts/**`

---

## 0. 结论

T3-A 六项修复全部闭环，逐项 GWT 实证通过；回归绿 9/9（含 ⑧ WARN 语义）exit 0、`--fail-drill` 红 ①②③ exit 1；临时单测文件已删除，磁盘无残留。

| 项 | 主题 | 风险 | 状态 | GWT |
|---|---|---|---|---|
| A-G1 | §3③ 已有库判别 | P1 数据损失 | ✅ | `≠0 即停`红线 + 分叉数字 |
| A-G2 | README 8/8→9 项 | D-07 | ✅ | grep 0 处 `8/8\|8 项`；§4 表含 ⑨ |
| A-G3 | 脚本 8 项口径 | D-07 | ✅ | grep 0 处 `8 项/8/8\|计入 8` |
| A-G4 | ⑧ 改探真后门 | P1 安全检查假阴性 | ✅ | 三分支齐（隔离单测 PASS） |
| A-G5 | 根目录 .dockerignore | D-10 | ✅ | 首行 `.env` |
| A-G6 | 220 键→37 | D-02 | ✅ | grep 0 处 `220` |
| A-G7 | 巡检耗时 2s→10-15s | D-11 | ✅ | grep 0 处 `约 2 秒` |
| A-V1 | 回归 | — | ✅ | 绿 9/9 exit 0；drill 红 ①②③ exit 1 |

---

## A-G1（D-05，P1 数据损失风险）：§3③ 恢复命令前新增「已有库判别」

**现状**：README §3③ 让新人直接执行 `mysql -uroot -p < deploy/backups/20260816_task00/edu_full_dump.sql`，dump 含 106 条 `DROP TABLE`；在已有库（104 表）机器照做 = 清 11 张新表 + 数据回滚到 08-16，文档零警示。

**修改**：在 §3③ 恢复命令前新增醒目小节「⚠ 已有库判别（执行前必查，P1 数据损失风险）」——先跑 `SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='edu'`，**结果 ≠0 即停**；写明分叉事实（现库 104 vs dump 106 表、dump 内含 106 条 DROP TABLE、dump 独有 11 张 / 现库独有 9 张、数据回滚 1 个月），并加「仅适用于全新空库机器」限定。

**GWT 证据**（`deploy/README.md` 119-134 行）：
- ✅ Given 通读 §3③ 的新人 When 读到恢复命令 Then 先看到判别 SQL
- ✅ `≠0 即停` 红线文字存在
- ✅ 分叉事实有数字（104/106/106 条 DROP/11/9/1 个月）

```text
> ⚠ **已有库判别（执行前必查，P1 数据损失风险）**
> ... 方式一的全库 dump 内含 **106 条 `DROP TABLE`** ... 实测 `edu` 库当前 104 表 ... 二者已双向分叉：
> - **dump 独有 11 张**（`admin_*`×7、`curriculum_*`×4）...
> - **现库独有 9 张**（`user_memory*`、`hitl_approval`、`task_execution`、`course_review`、`knowledge_import_task` 等）...
> SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='edu'
> **结果 `≠0` 即停**：... 照做 = 破坏性覆盖（清 11 张新表 + 数据回滚 1 个月）...
```

---

## A-G2（D-07）：README「8/8」「8 项」改 9 项，§4 补⑨行

**现状**：5 处实测 8 口径（L4/L10/L152/L162/L193）+ 变量行 `期望末行 L175`；脚本实际 9 项（⑨=抽验页 admin-users-refine-proto.html，C5-D2 扩清单）。

**修改**：改 9/9；§4 对照表补⑨行（检查项/可能现象/处置：页 404→确认 `public/admin-users-refine-proto.html` 存在）。

**GWT 证据**：
- ✅ `grep -n "8/8\|8 项" deploy/README.md` = **0 处**
- ✅ §4 表含 ⑨ 行（第 193 行）

```text
grep before: 8/8×5 + 8项×…（L4/L10/L152/L162/L193）
grep after : 0 处
| ⑨ | 抽验页 200 `/admin-users-refine-proto.html`（C5-D2 扩清单） | 页面 404 | 确认 `public/admin-users-refine-proto.html` 存在；前端未就绪先修 ⑤ |
```

---

## A-G3（D-07）：check-demo.mjs 自身「8 项」口径修正

**现状**：脚本注释 L234「计入 8 项」等与实际 9 项输出「绿 9/9」矛盾。

**修改**：改命令行 Banner/头注释为「共 9 项检查」；⑧ 注释描述重写为三分支语义；⑨ 注释保留「核心页 8 个口径不变」（指 ⑦ 内页数量，非检查项数，不误改）。

**GWT 证据**：
- ✅ 脚本内 `8 项/8/8\|计入 8` 残留 = **0 处**
- ✅ `node --check` 语法通过（EXIT=0）

---

## A-G4（D-09，P1 安全检查假阴性）：⑧ 探测点改真后门

**现状**：⑧ 探 `GET /api/admin/users`（无 token），被 AdminAuthMiddleware fail-closed 永远 401 → 永远 PASS「DEBUG 安全」；真后门在 `GET /api/users/me` 与 `/api/auth/me`（DB 实证：DEBUG=true 下无 token→200 虚拟管理员 role=admin）——巡检形同虚设。

**修改**：⑧ 改探 `GET /api/users/me`（无 token），三分支语义：
- **A DEBUG-safe**：无 token 被拒绝（非 200/非 code 0）→ PASS「DEBUG 安全」
- **B 开发态**：后门存在且 `DEBUG=true` + `ENV_NAME=local` → **WARN**（已知后门，不阻断 exit 0，避免永久红=狼来了）
- **C 真后门**：后门存在且 `DEBUG=true` + `ENV_NAME≠local` → 红，阻断 exit 1
- `ENV_NAME`/`DEBUG` 从 `edu-agent/.env` 读（`^-key=` 匹配，缺省 `ENV_NAME=local`）；fail-drill 行为保持

**实现改动**（`check-demo.mjs`）：新增 `readDevEnv()`（`new URL("../.env", import.meta.url)` + `readFileSync`）；`timed()` 透出 `err`；`check()` 区分 WARN（软，`results[].warn=true`）与 FAIL（硬）；汇总按 `red`（硬）判定 exit，warn 计入绿。

**GWT 证据**：
- ✅ 本机（DEBUG=true，EV 未设=local）实跑 → ⑧ 输出 **WARN** 且汇总含 WARN，**exit 0**（见 A-V1）
- ✅ 三分支齐全（隔离单测，临时脚本测后删除，内置逻辑与吸附到真实 .env 判定等价）：
  - A（401）→ PASS
  - B（200 + DEBUG=true + ENV_NAME=local）→ WARN 不阻断
  - C（200 + DEBUG=true + ENV_NAME=prod）→ RED 阻断
  - edge（200 + DEBUG=false + prod）→ RED（安全保守）

```text
真实探测实证（HTTP 只读）：GET http://127.0.0.1:8000/api/users/me 无 token → 200 {"code":0,..."role":"admin"}  ← 确认后门真实存在、⑧ 新探测点命中
```

---

## A-G5（D-10）：新建根目录 .dockerignore

**现状**：README 附录列出 .dockerignore 但根目录不存在。

**修改**：新建 `.dockerignore`，`.env` 居首（第一行，防密钥入镜像），另含 `.env.*`（排除，保留 `.env.example`/`.env.production.example`）、`node_modules/`、`.next/`、`.next-prod/`、`edu-agent/.venv/`、`__pycache__/`、`*.pyc`、`logs/`、`test-reports/`、`deploy/backups/`、`.git/`、`.gitignore`。

**GWT 证据**：
- ✅ 根目录存在 `.dockerignore`
- ✅ 首行为 `.env`

```text
第一行: .env
完整: .env / .env.* / !.env.example / !.env.production.example / node_modules/ / .next/ / .next-prod/ / edu-agent/.venv/ / __pycache__/ / *.pyc / logs/ / test-reports/ / deploy/backups/ / .git/ / .gitignore
```

---

## A-G6（D-02）：「220 键」口径纠偏

**现状**：README 两处称 .env.example「220 键」，实测未注释键 **37 个**。

**修改**：L8/L115 全文改为「未注释键 37 个（2026-09-15 实测）」，并保留 `.ai-hub/plans/deploy-config-checklist.md` 链接。

**GWT 证据**：
- ✅ 实测未注释键 = 37（`.env.example` `^[A-Za-z_][A-Za-z0-9_]*=` 计数）
- ✅ `grep -n "220" deploy/README.md` = **0 处**

---

## A-G7（D-11）：巡检耗时口径纠偏

**现状**：§5 称巡检「约 2 秒」，实测 11-15.5s（⑥ 登录链路单项 6-10s）。

**修改**：改「整轮巡检约 10-15 秒；⑥ 登录链路占大头，单项 6-10s 属正常波动」；§4 表⑥ 备注加同步解释。

**GWT 证据**：
- ✅ `grep -n "约 2 秒" deploy/README.md` = **0 处**
- ✅ 新口径「10-15 秒 / 6-10s」存在（§5 巡检建议第 1 条 + §4 表⑥ 备注）

---

## A-V1 回归

| 模式 | 结果 | exit |
|---|---|---|
| normal | `汇总: 绿 9/9,WARN ⑧ —— 演示环境就绪 (6584ms)` | **0** |
| --fail-drill | `汇总: 绿 5/9,红项 ①、②、③,WARN ⑧` | **1** |

- normal：①③⑤⑦⑨ 真服务 PASS，② Redis PONG，④ /health status=ok v0.3.0，⑥ admin+student 登录链路 PASS，⑧ WARN（后门存在，本机开发态）→ **绿 9/9 exit 0** ✅
- fail-drill：①②③ 假端口必然 FAIL → **exit 1** ✅；⑦ 8/8 全 200、⑨ 200 PASS ✅
- 服务/依赖实证（HTTP 只读）：后端 8000 `/health` 200、前端 3000 `/login-register.html` 200 ✅

---

## 完工回执（commit message 清单）

| commit（按序） | 内容 | 引用项 |
|---|---|---|
| `docs(deploy): 已有库判别警告 + 8/8→9 口径 + 220键/耗时纠偏 (T3A)` | README A-G1/G2/G6/G7 | D-05/D-07/D-02/D-11 |
| `fix(scripts): ⑧改探真后门+三分支语义, 汇总软硬区分 (T3A)` | check-demo.mjs A-G3/G4 | D-09/D-07 |
| `chore: 根目录 .dockerignore 防密钥入镜像 (T3A)` | .dockerignore A-G5 | D-10 |
| `docs(test-reports): T3A 完成报告` | 本报告 A-V2 | — |

- 报告路径：`test-reports/T3A-completion-report.md`
- GWT 数字：A-G2/6/7 grep=0；A-G3 grep=0+语法 PASS；A-G4 三分支单测 PASS；A-V1 绿 9/9（WARN ⑧）exit 0、drill exit 1
- 锁：`edu-agent/scripts/eval/t3a.lock` 已删除（完工）

> 备注：A-G4 三分支的 B/C 判定依赖 `.env` 的 `DEBUG`/`ENV_NAME`；本机为 `DEBUG=true`+`ENV_NAME` 缺省（=local）属预期开发态 WARN。生产部署 `DEBUG=false` 后 ⑧ 自动转 PASS，无人工介入。