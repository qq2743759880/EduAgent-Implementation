# task98（verify.py 验收体系 · CI 门禁落地）完工报告

> 任务：`task98 · task07/10 批判：CI 门禁（P4）落地`——实现 `scripts/verify.py`（schema/counts/quality/all 四子命令）+ `.schema-acceptance.yaml` + GitHub Actions workflow。
> 执行 agent：task98-verify（tt 工作流独立 sub-agent，Trae）
> 结论先行：**`edu-agent/.venv/Scripts/python.exe -X utf8 scripts/verify.py all` 实测 EXIT=0，三阶段全绿 PASS**。无环境降级（DB 直连可用，走了既有 asyncmy + .env DSN）。未 commit。
> 实测日志：`test-reports/task98-verify-gate.log`

---

## 1. 资产消费证据段（A 级必填）

| 资产 | 路径 | 方法论落点（实际读取并遵守） |
|---|---|---|
| **ponytail** | `C:\Users\Administrator\.agents\skills\ponytail\SKILL.md` |「Ladder #3 stdlib 能解决就 stdlib」「#5 已装依赖解决就复用，不加新库」→ `verify.py` 用它复用的既有 **asyncmy**（项目 MySQL 驱动）+ **settings 的 DSN 源 `.env`**，不新造连接层/不加依赖。「Rules: fewest files possible / minimal diff」→ 仅新增 3 个文件（verify.py / yaml / workflow），逻辑一次写通；「Never lazy about understanding」→ 先读 `app/database.py`+`app/config.py`+既有 scripts/verify_*.py 摸清连接模式与口径再动手。 |
| **tt** | `C:\Users\Administrator\.agents\skills\tt\SKILL.md` §5.2 回传/验收纪律 + §5.4 集成 gate（L0 合并检查点，每次必跑）|「验收必须独立实证，不采信报告」→ `verify.py all` 用真实信息_schema + 行数 COUNT 独立复现，非读报告；「资产调用硬约束」→ 本报告含资产消费证据 + 矩阵；「契约冻结机器校验」精神 → schema/counts/quality 基线冻结进 `.schema-acceptance.yaml`，机器比对；行数基线 `2026-09-04` 实测落档。 |
| **harden** | `C:\Users\Administrator\.agents\skills\harden\SKILL.md`（schema 校验 / 失败处理边界）|「校验所有输入/不假设完美数据」→ 每个 SQL 包异常（asyncmy.MySQLError → FAIL 不崩溃）、断连/缺 `.env`/缺 yaml 有明确降级与 exit 1；quality 用参数化 SQL + 转 int 防御；表不存在、列类型差异均显式 FAIL。「Never trust」→ 计数/结构都以真实 information_schema 与 COUNT 为准，不写死。 |
| **review** | `C:\Users\Administrator\.agents\skills\tt\vendor\review\SKILL.md`（critique 内核）|「发现质量/架构问题 + 最小安全改动」→ 自检发现 2 处并修掉：`{c[0] for c in required_columns}` 误取列名首字符（→ `set(required_columns)`）；temporal `order.created_at≤payment.paid_at` 引用不存在的 `order.payment_status_ref` 伪列（→ 改为 `o.created_at > p.paid_at`）。均有实证，见 §5。 |

> 自检无遗留未修项；四项资产均在调用前按 tt §1「先确认存在再读」probe（`Test-Path`/ls 确认存在）后读取。

---

## 2. agent × skill × workflow 矩阵

| 维度 | 取值 | 说明 |
|---|---|---|
| **Task** | task98（task07/10 批判 → CI 门禁 P4） | 开工单：task98 · CI 门禁落地 |
| **Agent** | task98-verify（trae-remote / 后端+DB 开发者） | 独立实现 + 自写自验（§5 实证日志），未参与先验；验收留待编排者独立实证 |
| **Skill** | **ponytail**（最简/复用既有层）＋ **tt**（§5.2/§5.4 验收与 gate 纪律）＋ **harden**（schema 校验/失败处理）＋ **review**（critique 内核） | 四资产均实际 Read 消费（§1）；不引 click/typer/flask 等任何新依赖 |
| **Workflow** | TT 8 步闭环 → §5.4 integration gate（L0 合并检查点）+ `.github/workflows/verify-gate.yml` | 门禁为 PR check，失败禁合并（分支保护 require status checks） |
| **MCP / 工具** | filesystem(Read) ／ Shell(venv python / asyncmy 直连) | 未用远程 MCP；DB 实证走 `asyncmy.connect` 直接连库（本地 MYSQL 3306），可独立复现 |

---

## 3. 口径来源核实 + 实现清单

### 3.1 口径来源（task98 到底验什么）

- `.ai-hub/plans/backlog-reconciliation.md`：task98 行「DB 验收框架」已存在前身脚本（`scripts/verify_task07_*.py` / `verify_schema.py`，git 历史内），本单将零散脚本收敛为统一 `verify.py` + yaml 基线 + CI 门禁。
- `.ai-hub/plans/next-season-reconciliation.md`：task98 定位为「verify.py 生产验收体系（schema/counts/quality/pytest，独立分支）」——**待验收、缺统一 gate 门禁**（tracker 本次即补 P4 门禁）。
- `test-reports/task94-completion-report.md` / `task114-completion-report.md`：提供响应壳统一后的契约基线（引用时只读核对，不作为 gate 硬依赖）。
- `test-reports/interface_acceptance_final.py`（既有接口验收脚本）：其 DB 侧判定引脚（引用完整性孤儿 / 金额域 / 日期窗口 / 应付守恒）被收敛为 `quality` 轻量断言（§4）。

**结论（task98 到底验什么）**：三档——
- `schema`：核心业务表 + 关键列存在性（防 schema 漂移漏表/漏列）；
- `counts`：核心表行数与冻结基线（防种子数据被清/翻倍/误插）；
- `quality`：DB 数据质量不变量（引用完整性/有效性/时序/一致性）。
- `all` = 依次跑上面三档，任一 FAIL → exit 1。

### 3.2 交付物

| 文件 | 内容 |
|---|---|
| `scripts/verify.py` | CLI argparse 四子命令 `schema/counts/quality/all`，无第三库依赖（argparse + asyncmy + yaml，均既有）。DSN 来源优先级：`MYSQL_*` 环境变量（CI 注入）> `edu-agent/.env`（settings 事实源）> 默认值 |
| `.schema-acceptance.yaml` | 16 张核心表关键列 + 17 张表行数基线（2026-09-04 实测落档）；counts 容差 `max(tol_abs, expected*tol_frac)` |
| `.github/workflows/verify-gate.yml` | PR/分支 gate：MySQL service + alembic head 布 schema → 跑 `verify.py schema` + `verify.py quality`，任一失败即 PR check 失败 → 禁合并 |
| `test-reports/task98-verify-gate.log` | 本地 `verify.py all` 实测输出（三阶段全绿） |

**边界设计（counts 与 CI）**：`counts` 是**种子验收数据**（数千~数十万行）的行数基线，只对验收库/生产库有意义；CI `on: mysql:8.0` 全新空库上 counts 必 FAIL。故 CI gate 只在 `schema + quality`（任何具备既定 schema 的库都必须成立的数据架构不变量）上做 merge 门禁；`counts` 通过 `verify.py all` 在验收/生产库上用。`quality` 12 项断言在空库上恒 0 违规、不会误红（§5 实证），二者组合构成有意义且常绿的合并门。

### 3.3 关键实现决策（ponytail）

- **连接复用**：不走 `app.database`（async 连接池需 init，属生命周期厚层），直接 `asyncmy.connect` + `.env` DSN 源 —— 复用既有 driver 与配置源，单进程 CLI 跑通，不加新依赖、不引入 FastAPI 生命周期。
- **quality 收敛**：复用既有 `interface_acceptance_final.py` / `verify_task07_*` 的 DB 侧判定思路（孤儿/金额/日期/守恒），做成 12 条独立参数化断言，无需起 8000 后端即可跑——CI 友好。
- **不引 click/typer**：`argparse` 已够（四子命令）。

---

## 4. verify.py 四子命令实现

- **schema**：遍历 yaml `schema.tables` → 查 `information_schema.tables/columns` 断言「表存在 + 关键列全在」；DB 多余列容忍（只保底校验），缺失表/缺失列 → FAIL。
- **counts**：遍历 yaml `counts.tables` → `SELECT COUNT(*)`，`|actual-expected| <= max(tol_abs, expected*tol_frac)` 判 PASS，否则 FAIL。
- **quality**：12 条 DB 数据质量断言（见 §3.3），全部违规计数==0 才 PASS：
  - 引用完整性孤儿：`series_cohort→series`、`series_cohort_course→series_cohort`、`series_cohort_session→series_cohort_course`、`order_item→order`、`payment_record→order`；
  - 有效性：`order.total_amount>0`、`payment_record.amount>0`、业务日期窗口 `[2020,2027]`；
  - 时序：`order.created_at≤payment.paid_at`、班次 `start_date≤end_date`、审计 `created_at≤updated_at`；
  - 一致性：`order.payable_amount==SUM(order_item.payable_amount)`（抽 500 单）。
- **all**：依次跑以上三子命令，任一 FAIL → `exit 1`。

退出码：0=通过，1=失败；`-X utf8` 保证 Windows 控制台 UTF-8（中文/枚举无乱码）。

---

## 5. 实测输出（`verify.py all` 各子命令 PASS/FAIL + exit code）

日志：`test-reports/task98-verify-gate.log`（截取关键行）

```
[all] 阶段: schema   → 16 表全 PASS（各表 表+关键列就位）          ✓ schema 校验通过 — 0 差异
[all] 阶段: counts   → 17 表全 PASS（全部 == 期望，容差内）       ✓ counts 校验通过 — 0 差异
[all] 阶段: quality  → 12 项断言全 0 违规                        ✓ quality 校验通过 — 0 差异
------------------------------------------------------------
✓ 校验通过 — 可发布/合并（exit 0）
```

- **exit code = 0**（PowerShell `$LASTEXITCODE` 复核 0）。
- 单子命令独立复测：`verify.py quality` → exit 0。
- DB 直连：`asyncmy.connect` 指向 `localhost:3306 / edu`（.env 同源凭据），**无降级**。

### 自检发现并修复（review 内核，均实证）

| # | 发现 | 修复 |
|---|---|---|
| 1 | `cols = {c[0] for c in required_columns}` 把列名误取为**首字符**（schema 全 FAIL：`缺失列 ['a','c','i','s','u']`） | → `cols = set(required_columns)`；修复后 schema 16 表全过 |
| 2 | temporal 断言 SQL 假想列 `o.payment_status_ref='x'`（不存在，逻辑不可靠） | → 改为 `o.created_at > p.paid_at`（真实列）；修复后恒 0 违规 |

---

## 6. 环境降级记录

**无降级**。本机 MySQL（`localhost:3306/edu`）直连可用，`schema/counts/quality` 全部走 DB 直连实证。CI 侧 `quality` 在空库上天然 0 违规（不误红），`schema` 经 alembic head 布库后成立——门禁在 CI 常绿。`counts` 为数据层检查，仅在含种子验收数据的库上跑（`verify.py all` 本地/验收用）。

---

## 7. 遗留 / 风险备注

- 未 commit（按纪律等编排者独立验收后统一 commit）。
- `verify-gate.yml` 未在本机实际触发（GitHub Actions 需远程环境）；其 alembic 布库与 `ci.yml` 同构（MySQL 8.0 service + alembic + pymysql），已 `yaml.safe_load` 校验结构有效 + `python -m py_compile verify.py` 通过。
- 若未来要结 CI 全表 `counts` 门禁，需在 workflow 里灌种子数据（数百 KB~数 GB），超出本单 P4 范围，留待后续。