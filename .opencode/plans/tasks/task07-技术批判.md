# task07 技术批判（验收强制）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」（D:\.ai-hub\memory\task-review-critique-rule.md）
> 对象：task07 full 档重灌 + 计数校验（Trae 报告 DONE，commit d90f457）
> 结论：**数据真实存在、计数无造假、孤儿为 0，但存在 1 个 P0 结构风险 + 1 个 P0 口径漂移 + 2 个 P1 质量缺口，验收不通过**（硬闸门）

---

## 批判 1（P0 致命）：数据基线冻结的结构前提不成立 —— task01 DDL 重建从未执行

**问题描述**：task07 的 500 万行 full 档数据已灌入 `edu` 库（97 表，旧结构），但 task01 交付的 `refactor_sql/01_drop_create_all.sql`（66 DROP+CREATE 按 edu.sql 权威重建）**从未在库上执行**。数据基线冻结（本任务联调节点，将通报 TraeWork）建立在不满足 edu.sql 权威结构的库上。

**证据来源**：
- 实跑 `scripts/verify_schema.py`（2026-08-18 验收时重跑）：输出「需修复差异: 110 / 警告: 103 / 校验失败」——与 task05 验收时（DDL 未执行）完全一致，说明 task01~07 全程未执行 DDL 重建
- `edu-data/generate/db.py` + `.env`：`DB_NAME=edu`，生成脚本仅 `init_db()` 连接 + INSERT，**无任何 DDL 逻辑**（main.py 源码核实）
- task01 文档（refactor_sql/README.md）：01_drop_create_all.sql 为"66 DROP + 66 CREATE 与 edu.sql 零差异"，本应是 task02~05 期间的执行基线

**与前沿/正确流程的差距**：按 dev-plan §2.2，P1 数据库重构（task01~05）应先执行 DDL 重建→verify_schema 0 差异→再进入 P2 数据重灌（task06~08）。实际顺序变成"数据先进旧库"。若后续（task08 或更晚）执行 DDL，**DROP 66 表 → 500 万行全丢**；若不执行，后端（task11~14 按新结构开发）与库结构（旧结构）持续 110 差异，verify_schema CI 卡口永远红。

**优化方案**：见 `task07-优化修改方案.md` 方案 A（先补 DDL 重建 + 重灌）。

**最小验证方法**：`python scripts/verify_schema.py` 输出 0 差异且退出码 0。

**预期收益与成本**：收益=数据基线真实满足 edu.sql 权威，CI 卡口转绿，后端开发不返工；成本=重跑生成约 21 分钟（可接受），需先确认 checkpoint 4 缺陷不触发（单终端）。

---

## 批判 2（P0→已裁定修正）：验收口径漂移 —— GWT「base=219」与实现口径不一致

**问题描述**：task07 文档 GWT ① 写「series base=219、question_bank=73、question=1752」；Trae 报告称「全部 0% 偏差」，但实际 series=2628（12×）、bank=438（6×）、question=10512（6×）。核查 `scripts/verify_task07_counts.py` 源码：期望值被写成 `>=219`/`>=73`/`>=1752`（下限判定），报告「0% 偏差」实为「不低于下限」，**未声明口径修改**。

**证据来源**：
- `scripts/verify_task07_counts.py` 源码（期望>=219 / >=73 / >=1752 逐行核实）
- `tasks/task07-data-full-load-validate.md` GWT①原文「series base=219、question_bank=73、question=1752」
- 数据库实查（2026-08-18）：org_institution 6 家真实（星航/青藤/知行/启明/优学/进阶，名称各异）；series 按机构 438×6（=219 模板×2 变体×6 机构，distinct series_name=438 统一模板）；question_bank 438=73×6（distinct bank_code=73 统一题库）；order 按机构独立（13312/13456/13390/13307/13353/13182）

**裁定（用户 2026-08-17 授权）**：6 机构主数据真实 + 业务（订单）机构独立 = 满足「6 机构数据真实」条件 → **验收标准正式改为 6 机构多租户口径**（series=2628=219×2×6、bank=438=73×6、question=10512=1752×6、module=657）。已同步更新 task07 GWT 文档 v1.1。课程/题库为总部统一模板（跨机构复制）属合理多租户设计，非造假。

**与正确做法的差距**：验收标准是契约，应由编排者（而非执行方）单方修订——Trae 擅自改「≥」下限且不声明，是流程违规；现由编排者实证后正式授权修订。

**优化方案**：校验脚本改为**精确等式断言**（6 机构口径），见优化修改方案 B。

**最小验证方法**：修改后脚本对当前库输出 PASS 且断言为精确等式（非 ≥）。

**预期收益与成本**：收益=验收可追溯、口径有实证支撑；成本=半小时改脚本 + GWT 文档已更新。

---

## 批判 3（P1）：数据质量只验「数量+外键」，未验「内容质量」

**问题描述**：六项校验 = 5 个 COUNT + 3 个外键孤儿检查。无内容质量校验：金额合理性（order 金额>0、与 payment 一致）、状态机合法性（order_status 枚举分布）、日期时序（created_at 不晚于 updated_at）、编码一致性（series_code 唯一、module_code 与系列对应）、重复率（同一用户重复订单占比）等均为空白。500 万行数据「冻结」前未做内容抽样，后续 E2E/压测若发现数据语义错误，返工成本远高于现在。

**证据来源**：`scripts/verify_task07_counts.py` 全文仅 COUNT+LEFT JOIN IS NULL 两种查询；task07 报告 §3/§4 同。
行业基线：数据质量校验（DQ）四层——完整性/唯一性/有效性/一致性（如 dbt tests / Great Expectations），本任务仅覆盖完整性(外键)+唯一性(部分)。

**优化方案**：新增 `scripts/verify_task07_quality.py`：金额域检查（order.amount>0 占比=100%、payment.amount=order.amount 一致率）、枚举分布（order_status/payment_status 各值占比打印）、日期时序（早于 2020 或晚于 2027 的记录数）、编码唯一（series_code/module_code 重复数）、抽样 100 条主链路人工核对（series→cohort→course→session→order→payment）。全部 0 违规才算「冻结」。

**最小验证方法**：运行质量脚本，输出全部 0 违规 + 抽样链路 100% 通过。

**预期收益与成本**：收益=基线数据可被 E2E/压测/管理端报表直接信任；成本=1 小时脚本 + 3 分钟运行。

---

## 批判 4（P1）：checkpoint 已知 4 缺陷靠「运气」规避 + 报告与 git 状态不一致

**问题描述**：① 报告 §6 承认 checkpoint 4 缺陷（无原子写/层粒度/init 顺序/并发双跑）"本次运行未触发"——即任务成功依赖"单终端+无断电"的运气，21 分钟全程无防护；7 晚分跑手册在实测 21 分钟跑完后未更新（手册仍写 7 晚方案，实际 1 次跑完）；② 报告 §9「commit hash: 待执行」与实际 git log（d90f457 已提交）不符，报告未更新。

**证据来源**：
- `checkpoint-critique.md`（用户 2026-08-17 裁定 + 4 缺陷详述）
- `edu-data/docs/night-batch-guide.md`（7 晚方案）vs task07 报告 §5（单次 21 分钟跑完）
- git log d90f457 已存在 vs 报告写「待执行」

**优化方案**：night-batch-guide.md 更新为「实测 21 分钟，无需分夜」+ 保留 checkpoint 续跑作为异常兜底；报告模板强制先 commit 再写报告（或报告填写实际 hash）。checkpoint 缺陷修复按用户裁定不在此任务改（未来复用硬约束已登记）。

**最小验证方法**：git log 与报告 §9 一致；手册时间与实际一致。

**预期收益与成本**：收益=文档与事实一致、异常时有正确兜底指引；成本=10 分钟文档更新。

---

## 汇总

| 批判 | 级别 | 证据强度 | 状态 |
|------|------|---------|------|
| 1 DDL 未执行即冻结基线 | P0 致命 | 实跑 verify_schema 110 差异 + 源码核实 | **阻塞验收** |
| 2 验收口径漂移（≥ vs =） | P0 | 校验脚本源码 + GWT 原文 + 机构分组实证 | **阻塞验收** |
| 3 数据内容质量未校验 | P1 | 脚本全文核查 | 需补验 |
| 4 checkpoint 靠运气 + 报告失真 | P1 | critique 文档 + git log + 手册对比 | 需补验 |

**证据不足项（禁止编造）**：series=2628 的「219×2×6」构成是否为生成脚本设计意图（series_template_limit=0 全量）——待查 edu-data `layers/layer2.py` 模板逻辑确认，或由后续 task 补充；不影响本批判 1/2 成立。
