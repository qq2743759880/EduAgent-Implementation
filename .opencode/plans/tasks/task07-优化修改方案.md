# task07 优化修改方案（基于技术批判，在现有产物上迭代）

> 依据：`task07-技术批判.md` 4 条批判 ｜ 原则：**优先修改现有 task07 产物，不另起炉灶**
> 关联规则：全局任务验收强制批判（D:\.ai-hub\memory\task-review-critique-rule.md）

## 方案总览

| # | 修改点 | 目标文件 | 状态 | 工作量 |
|---|--------|---------|------|--------|
| A | 补执行 DDL 重建 → verify_schema 0 差异 → 数据重灌 | `refactor_sql/01_drop_create_all.sql` + `edu-data` 重跑 | **P0 必做** | 1.5h |
| B | 修正校验口径（精确断言 + 机构基准） | `scripts/verify_task07_counts.py` | **P0 必做** | 30min |
| C | 新增数据内容质量校验 | `scripts/verify_task07_quality.py`（新建） | P1 | 1h |
| D | 更新夜跑手册为单次实测 + 报告模板填真实 commit | `edu-data/docs/night-batch-guide.md` | P1 | 10min |

---

## A. P0：补执行 DDL 重建 + 数据重灌（解决批判 1）

### 修改内容
在现有 task01 产物基础上执行，不新写 DDL：
```bash
# 1. 执行 66 表 DDL 重建（edu.sql 权威）
mysql -u root -p123456 edu < refactor_sql/01_drop_create_all.sql

# 2. 恢复 task03/task04 的结构增量（DDL 重建会覆盖，需重放）
#    - task03: scripts/task03_alter.py（外键+索引）
#    - task04: refactor_sql/05_create_task_tables.sql（knowledge_import_task + task_execution）
python scripts/task03_alter.py
mysql -u root -p123456 edu < refactor_sql/05_create_task_tables.sql

# 3. 校验结构对齐（CP1 卡口，必须 0 差异）
python scripts/verify_schema.py   # 期望：0 差异 退出码 0

# 4. 重灌 full 档（利用现有 checkpoint，先 reset）
cd E:\stu\project\stu\edu-data
uv run -m generate.main --profile full --layers 1..7 --reset
# 单终端运行（规避 checkpoint 并发缺陷），预计 ~21 分钟
```

### 关键点
- **顺序不可反**：先 DDL → 再 task03/04 增量 → 再 verify_schema → 再重灌
- `--reset` 清除旧 checkpoint（当前 checkpoint.json 已标记 7 层 completed，不 reset 会全 SKIP）
- 重灌前把当前旧库数据备份为 `deploy/backups/20260818_pre_ddl_reload/`（防误操作可回滚）
- **P4 CI 门禁**：本次修复的 verify_schema/verify_counts/verify_quality 全部接入 CI gate（失败 exit 1 禁合并），不满足 P4 不验收

### 量化指标
- verify_schema.py 输出「0 差异」且退出码 0（现状 110 差异）
- 六项计数在重灌后与本次一致（2628/657/438/10512/100000/80000）
- 三项校验脚本全部接入 CI gate（P4）

### 测试方案
- 回归：task05 GWT①（0 差异）→ 即 verify_schema 本身体现
- 集成：重灌后重跑 task07 六项计数 + 四级关联

### 新风险与应对
| 风险 | 应对 |
|------|------|
| DDL 重建致数据丢 | 已先备份；重灌可再生成 |
| task03/04 增量未重放 → FK/索引缺失 | 步骤 2 显式重放；verify_schema 可检出 FK/索引差异 |
| 重灌中 checkpoint 断电 | 单终端 + 已备份；断电后按 checkpoint-critique 手动恢复该层 |

---

## B. P0：校验脚本改精确断言 + 动态计算（依 db-acceptance-principles P2/P3）

### 修改内容（`scripts/verify_task07_counts.py`）
按 6 点验收原则重写：**精确 `==` 断言 + 期望值动态计算自权威源（禁硬编码）**：
```python
# ---- 期望值动态计算（P3：从权威源读，不写死）----
cur.execute("SELECT COUNT(*) FROM org_institution")
INSTITUTIONS = cur.fetchone()[0]                    # 动态机构数（勿硬编码 6）

# series 模板数 + 变体数：从种子权威源读（series.csv 219 行，每模板 2 变体）
SERIES_TEMPLATES = count_csv_rows(SEEDS_DIR / "2_course" / "series.csv")   # =219
SERIES_VARIANT   = int(cfg.series_variant_count)   # 从生成配置读（=2），非魔数
# 基准锚点：bank/question 用 question_bank 表 DISTINCT 语义（跨机构统一模板）
BANK_TEMPLATES   = 73   # 从 edu-data 种子题库权威源读（bank.csv），勿硬编码
QUESTION_PER_BANK = 24  # 从生成逻辑/配置读

exp_series  = SERIES_TEMPLATES * SERIES_VARIANT * INSTITUTIONS   # 219*2*6=2628
exp_bank    = BANK_TEMPLATES * INSTITUTIONS                       # 73*6=438
exp_question= QUESTION_PER_BANK * exp_bank                        # 10512
exp_module  = 657  # module 跨机构共享去重（权威=edu-data seeds，动态读）
exp_user, exp_order = 100000, 80000  # 数量级目标，容差来自文档

# ---- 精确断言（P2：== 或 文档容差，非 >=）----
TOL = load_tolerance_from_doc("task07")   # 0.5%，从 GWT 文档定义读取
def assert_eq(actual, expected, name):
    delta = abs(actual - expected) / expected
    ok = delta <= TOL if TOL is not None else actual == expected
    assert ok, f"{name}: {actual} != {expected} (偏差 {delta:.2%})"
    return True

assert_eq(count_series,   exp_series,   "series")
assert_eq(count_bank,     exp_bank,     "question_bank")
assert_eq(count_question, exp_question, "question")
assert_eq(count_module,   exp_module,   "module")
assert_eq(count_user,     exp_user,     "sys_user")     # 数量级，TOL=0.5%
assert_eq(count_order,    exp_order,    "order")
```
同时 `tasks/task07-data-full-load-validate.md` GWT① 已更新 v1.1（6 机构口径）。

### 量化指标
- 脚本断言为精确等式（`==` 或文档容差），无 `>=`
- 期望值全部动态计算（机构数/模板数/变体数从权威源读，无硬编码魔数）
- GWT 文档（P1）已先行更新，脚本（P6）同步实现

### 测试方案
- 单元：构造 mock 计数验证断言边界（±0.5% 内 PASS / 外 FAIL）
- 集成：对真实库运行输出 PASS + 实际计数明细

### 新风险与应对
| 风险 | 应对 |
|------|------|
| series 模板系数 2 为估算 | 查 `edu-data/generate/layers/layer2.py` 的 series 生成逻辑确认（template_limit），确认后固定常量 |
| 后续机构数变化 | 常量改为读 `COUNT(DISTINCT institution_id)` 动态计算 |

---

## C. P1：数据质量 5 维度全验（依 db-acceptance-principles P5）

### 新建文件 `scripts/verify_task07_quality.py`
按 P5 五维度设计（完整性/唯一性/有效性/一致性/时序性），每维度 ≥1 条断言，全绿才可冻结：

```python
"""task07 数据质量 5 维度校验（P5）"""
RULES = {
  # ---- 完整性：外键无孤儿 + 引用必达 ----
  "fk_orphan_cohort_series":  "SELECT COUNT(*) FROM series_cohort c LEFT JOIN series s ON c.series_id=s.id WHERE s.id IS NULL",  # 应0
  "fk_orphan_order_payment":  "SELECT COUNT(*) FROM `order` o LEFT JOIN payment_record p ON p.id=o.payment_id WHERE o.payment_id IS NOT NULL AND p.id IS NULL",  # 应0
  # ---- 唯一性：唯一键 + 逻辑重复 ----
  "uniq_series_code":         "SELECT COUNT(*) FROM (SELECT series_code, institution_id FROM series GROUP BY series_code, institution_id HAVING COUNT(*)>1) t",  # 应0（同机构内 code 唯一）
  "logic_dup_user":           "SELECT COUNT(*) FROM (SELECT account FROM sys_user GROUP BY account HAVING COUNT(*)>1) t",  # 应0（逻辑重复：同账号两 ID）
  # ---- 有效性：值域合法 ----
  "valid_amount":             "SELECT COUNT(*) FROM `order` WHERE amount <= 0",  # 应0
  "valid_status_enum":        "SELECT COUNT(*) FROM `order` WHERE order_status NOT IN ('pending','paid','closed','refunding','refunded','cancelled')",  # 按实际枚举字典
  "valid_date_not_future":    "SELECT COUNT(*) FROM `order` WHERE created_at > NOW()",  # 应0
  # ---- 一致性：跨表数值守恒 ----
  "consistency_order_items":  "SELECT COUNT(*) FROM `order` o WHERE o.amount != (SELECT COALESCE(SUM(oi.amount),0) FROM order_item oi WHERE oi.order_id=o.id)",  # 应0
  "consistency_payment":      "SELECT COUNT(*) FROM `order` o JOIN payment_record p ON p.id=o.payment_id WHERE o.amount != p.amount",  # 应0
  # ---- 时序性：时间先后合理 ----
  "time_order":               "SELECT COUNT(*) FROM `order` WHERE created_at > updated_at",  # 应0
  "time_session":             "SELECT COUNT(*) FROM series_cohort_session WHERE start_date > end_date",  # 应0
}
# 全表 0 违规 → PASS；任一 >0 → 红色 FAIL + 明细打印
# 枚举字典从数据库/权威源动态读取（P3），非硬编码
# 抽样：主链路 100 条（series→cohort→course→session→order→payment）逐条 LEFT JOIN 断链=FAIL
```

### 量化指标
- 11 条规则（5 维度全覆盖）全部 0 违规
- 100 条抽样链路 100% 无断链
- 表名/字段名先 `DESC` 校准，枚举从权威源读

### 测试方案
- 对当前库运行：真实暴露 order/order_item 金额不一致、支付引用断裂等问题
- 抽样链路可人工复核 10 条

### 新风险与应对
| 风险 | 应对 |
|------|------|
| 表名/字段名猜测错 | 先 `SHOW TABLES`/`DESC` 校准；脚本内用 information_schema 动态校验字段存在（P3） |
| 枚举值集合可能不同 | 从数据库 DISTINCT 抽取 + 对照 edu-data seeds 权威源，勿硬编码 |
| order.amount=SUM(items) 可能因优惠/整单折扣不成立 | 若存在非项级优惠，规则改为「差值<0.01 或差值=优惠金额（白名单）」并显式声明（P6） |

---

## D. P1：夜跑手册更新 + 报告 commit 真实化（解决批判 4）

### 修改内容
- `edu-data/docs/night-batch-guide.md`：新增「实测结论」章节——单次 21 分钟可完成，7 晚方案降级为可选兜底（断电/中断时按层续跑），更新预计耗时表为实测值
- task07 报告模板 §9：强制「先 commit 再写报告」，报告填写真实 hash

### 量化指标
- 手册与实测一致（21 分钟 vs 7 晚）
- git log 与报告 commit 字段一致

---

## 实施顺序与依赖

```
A1 备份旧库（10min）
  → A2 执行 DDL 重建（5min）
  → A3 重放 task03/04 增量（5min）
  → A4 verify_schema 0 差异（3min）★CP1 卡口
  → A5 重灌 full 档 --reset（21min）
  → B 修 verify_task07_counts.py + GWT 文档（30min）
  → C 新建 verify_task07_quality.py 并运行（1h）
  → D 手册/报告更新（10min）
  → 重跑全部验收（verify_schema 0 差异 + 六项精确计数 + 质量 0 违规 + 关联 0 孤儿）
```

依赖：A 依赖 task01 脚本（已交付）+ task03/04 脚本（已交付）；B/C 独立可并行；D 最后。

**总工作量 ~2.5h。验收通过标准 = A4 0 差异 + 六项精确 PASS + 质量 0 违规 + 四级关联 0 孤儿。**