# task99（批量 auth 补生成）完工报告

- **任务**：EduAgent 重构项目后端 —— 批量补生成 `sys_user_auth`，让 10 万生成用户可登录
- **前置**：task07（数据冻结）、task08（auth 现状确认：仅 200 条）
- **来源**：task08-技术批判.md 批判②（P2）
- **性质**：**数据补漏**——不改 edu-data 生成脚本（避免重灌破坏冻结基线）
- **状态**：✅ 全部 GWT 通过。`sys_user_auth` **212 → 100,015**，仍缺 auth 用户 **0**
- **纪律**：基于最新 HEAD `2d43706`（task98 并行已落地）起 3 个独立 commit；未用 `read-tree`/`reset`；**未 push**，停下等验收

---

## 一、GWT 验收

### GWT① `scripts/backfill_auth.py`：bcrypt 预哈希批量生成
| 项 | 实现 | 验证 |
|---|---|---|
| 脚本 | `scripts/backfill_auth.py`（185 行，pymysql + bcrypt） | 实测跑通（dry-run / 小批 / 全量 / 重跑） |
| bcrypt 哈希逻辑 | 与 `scripts/restore_admin.py`、`app/auth/service.py` 一致：`bcrypt.hashpw(pwd, bcrypt.gensalt(rounds=12))`，`PASSWORD_HASH_ROUNDS=12` | 抽样 `bcrypt.checkpw` 全通过 |
| 批量写入 | 5000/批 `executemany` + `INSERT IGNORE` | 全量 99,700 条耗时 247.65s |

### GWT② 参数 `--limit` / `--role`；幂等 `INSERT IGNORE`
| 参数 | 行为 |
|---|---|
| `--limit N` | 默认**全量**补齐所有缺失用户；传 N 则只处理前 N 个（已实测 3 / 100 / 全量） |
| `--role` | 决定**写入的 role_code**（默认 `student`，可选 student/teacher/manager/admin）。注：`sys_user` 表**无角色列**，故 `--role` 无法按角色筛选用户，只能决定写入值 |
| `--password` | 统一默认密码，默认 `Test@123456`，仅以 bcrypt 哈希落库 |
| `--batch-size` / `--rounds` / `--sample` / `--per-user-salt` / `--dry-run` | 批次(5000) / bcrypt 轮次(12) / 抽样数(10) / 每条独立盐(默认关) / 只打印计划 |

**幂等实测（三重）**：
1. 全量跑完后再跑一次 → `待补生成 0 条`，`sys_user_auth` 仍 **100,015**（未翻倍）。
2. 直接对已存在的 `user_id=1` 再 `INSERT IGNORE` → `ROW_COUNT()=0`，**无唯一键冲突、无报错**，user 1 原哈希未被覆盖（`$2b$12$` 60 字符完好）。
3. 人工 `DELETE` 掉 `user_id=50000` 的 auth → 重跑脚本**精确恢复该 1 条**（100,014 → 100,015），证明可增量修补。

### GWT③ 抽样验证登录（bcrypt 校验）+ 报告含默认密码
- 脚本内置抽样：随机抽 N 条新记录，`bcrypt.checkpw` 校验密码 + 核对 role_code。
  - 小批 100：抽样 **10/10 PASS**；全量：抽样 **10/10 PASS**；`--per-user-salt` 3 条：**3/3 PASS**。
- **用项目真实校验函数复核**：`app.auth.service.verify_password`（login_user 内部所用）随机抽样 20 条 → **20/20 PASS**，role 均为 student。
- 角色分布：`student 100,004 / admin 5 / manager 3 / teacher 3`（= 100,015）。
- 默认密码见 §五。

### GWT④ 不改生成脚本 + `verify_schema.py` 回归
- **未修改任何 edu-data 生成脚本**（layer1~4 原样），仅新增 `scripts/backfill_auth.py`。
- `verify_schema.py` 重跑 → **需修复差异 0 ✅ 校验通过**（警告 12 项均为既有多余列/多余 FK/类型宽度，DDL 级、与本任务无关）。
  - ⚠️ 该脚本重跑时**先暴露了一个既有环境 Bug**：Windows 上 mysql CLI 按 GBK/cp936 输出中文表注释，与 `text=True` 的 UTF-8 解码冲突 → `UnicodeDecodeError`，脚本在列 information_schema 阶段即崩（与本次加行无关，本次只 INSERT 行未改 DDL）。
  - 修复：`MYSQL` 命令加 `--default-character-set=utf8mb4`，**仅改读出编码，未动任何比对逻辑**（独立 commit `ffee90d`）。修复后方可完成本条验收。

---

## 二、关键设计决策：bcrypt 性能取舍（实测驱动，重要）

**实测**（本机）：bcrypt rounds=12 单次哈希 **410 ms**。若逐用户独立哈希，99,803 条需：

```
99803 × 0.41s ≈ 11.4 小时   ← 不可行
```

**决策**：补生成的账号**共用同一默认密码**，故脚本**只计算一次 bcrypt 哈希并复用到所有行**。

| | 说明 |
|---|---|
| 安全性 | 仍是标准 bcrypt 哈希（`$2b$12$`，60 字符），**无任何明文**；`bcrypt.checkpw` / `verify_password` 均通过 |
| 为何不加 per-user 盐 | 所有账号明文口令相同，攻破一个即等于攻破全部 → per-user 盐**不增加任何安全性**，却要付 11.4 小时 |
| 保留退路 | `--per-user-salt` 可选开启（逐条独立盐），仅建议小批量（已实测 `--limit 3` 通过） |

全量实际耗时 **253s**，其中哈希仅 0.4s，其余 247s 为 99,700 行写入。

---

## 三、实测数据

| 指标 | 补生成前 | 补生成后 |
|---|---|---|
| `sys_user` | 100,015 | 100,015（未动） |
| `sys_user_auth` | **212** | **100,015** |
| 仍缺 auth 的用户 | **99,803** | **0** |
| `COUNT(DISTINCT user_id)` | — | 100,015（**无重复**） |
| 非 bcrypt 哈希（明文风险） | — | **0** |

> 与任务文档的偏差（如实标注）：文档写 `sys_user` 100003、`sys_user_auth` 200；实测为 **100015 / 212**——
> 差额来自 task08 及后续压测新增的 12 个特殊账号（`adm02test`/`mgr01test`/`stu01test`/`t15reg*`/`be01_del*`/`perf1~5`）。
> 本任务对**全部**缺失用户补齐，故最终 100,015。

---

## 四、安全红线核查

- ✅ **密码只以 bcrypt 哈希落库**：`SELECT COUNT(*) WHERE password_hash NOT LIKE '$2b$%' AND NOT LIKE '$2a$%' AND NOT LIKE '$2y$%'` → **0**（全表无明文/非 bcrypt 值）。
- ✅ 脚本内明文口令仅存在于内存与 `--password` 入参，落库前即 `bcrypt.hashpw`。
- ✅ 未修改 `sys_user` 任何既有数据；既有 admin/manager/teacher 记录未被覆盖（唯一键 `INSERT IGNORE` 保护）。

---

## 五、账号信息（E2E / 压测用）

| 项 | 值 |
|---|---|
| 用户名（account） | **`user000001` ~ `user100000`**（100,000 个生成用户） |
| 统一默认密码 | **`Test@123456`** |
| 角色 | `student`（100,004 条，含既有 201 条 student） |
| 既有特权账号 | `adm02test`(admin) / `mgr01test`(manager) / `stu01test` 等，密码同为 `Test@123456`（task08 已重置） |
| 特殊账号（非 user% 前缀，共 17 个） | `adm02test` `mgr01test` `stu01test` `t15reg87273283`… `be01_del_*` `perf1`~`perf5` |

登录校验入口：`app.auth.service.verify_password`（`bcrypt.checkpw`）。

---

## 六、git 交付（3 个独立 commit）

| commit | 内容 |
|---|---|
| `1288b92` | 新增 `scripts/backfill_auth.py`（GWT①②③） |
| `ffee90d` | `scripts/verify_schema.py` Windows 编码修复（GWT④ 前置） |
| `97b8ed0` | `backfill_auth.py` 账号区间改为回查真实 `account`（原按总行数臆造 `user000001~user100015`，实际 `user%` 区间为 `user000001~user100000` 另有 17 个特殊账号） |

HEAD = `97b8ed0`，三处 ref（HEAD / `.git/refs/heads/feature/task44-courses` / `.git/packed-refs`）已核对一致。**未 push。**

---

## 七、已知遗留 / 风险（如实标注）

1. **⚠️ 并行 agent 破坏了分支 ref（非本任务引入，但已影响提交链）**：提交 `1288b92` 时，`p1_commit.py` 报
   `packed-refs 中未找到分支行`——排查发现**并行任务（task98 侧）把 `refs/heads/feature/task44-courses`
   写成 7 字符缩写 `2d43706`**，git 判为 broken ref，导致 `git rev-parse HEAD` 一度退化为
   `'feature/task44-courses' does not have any commits yet`，我的提交对象悬空。
   已按项目修正纪律修复：写**完整 40 字符** SHA 到松散 ref + 同步 `packed-refs`，并重建
   `.git/refs/heads/feature/` 目录（该目录被反复剪除是本项目 HEAD 不前进的根因）。
   **建议同步给并行 agent：禁止写缩写 SHA、禁止 `git pack-refs --all`。**
2. **GWT① 的 HTTP 层登录未实测**：`--role=student` + JWT 200 的端到端验证需运行中的后端（8000/8003），
   当前环境后端未起（Redis 在 WSL 内不可用、VM `192.168.85.101` 上的 Milvus/Neo4j/Mongo/MinIO 不可达）。
   本任务按 GWT③ 括号内的指定口径完成——**bcrypt 层校验**（且用的是项目真实 `verify_password`）。
   后端起来后可直接用 §五 账号跑 HTTP 登录复验。
3. **全量写入 247s**：99,700 行 5000/批 `executemany`，可接受；如需更快可调大 `--batch-size`。
4. **未改 edu-data 生成脚本**：若将来重灌 full 档，仍需重新执行本脚本补齐 auth（或在 layer1 补写，另行评估）。

---

## 八、停下等验收

- 已停手，**未 `git push`**。
- 待验收：① GWT① 脚本+bcrypt ② GWT② 幂等三重验证 ③ GWT③ 20/20 `verify_password` + 默认密码入报告 ④ GWT④ `verify_schema.py` 0 需修复差异 ⑤ 安全红线 0 明文。
- 看板 `D:\.ai-hub\memory\project-handoff.md` 待更新 task99 状态（本会话停止，交由用户/验收方）。
</content>
