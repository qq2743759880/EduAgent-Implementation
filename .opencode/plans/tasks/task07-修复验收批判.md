# task07 修复验收批判（补充）

> 依据：全局规则「任务审核验收强制技术批判」+ 6 点验收原则（db-acceptance-principles.md）
> 结论：**验收通过**（4 项卡口全绿，实证复核），1 条补充批判转 task98 处理。

## 批判 5（P1，转 task98）：CI 门禁（P4）未在本任务落地

**问题描述**：修复报告交付物清单无 CI workflow 更新。现有 `.github/workflows/ci.yml` 的 "Verify table count" 步骤仍是旧逻辑：`assert n >= 100`（违反 P2 的 `>=` 下限）且只数表数量、不跑三项校验脚本（verify_schema/counts/quality）。即本次修复的校验脚本**未接入 CI gate**，仅本地手工可跑。

**证据来源**：
- `.github/workflows/ci.yml` "Verify table count" 步骤源码（`assert n >= 100, f"expected >=100 tables"`，pymysql 连 edu_ci 库）
- 修复报告交付物清单（5 项：verify_schema/counts/quality/手册/task03_alter + 备份，无 CI 文件）

**与原则差距**：P4「CI 是门禁，不是提示——校验失败，禁止合并」未满足。

**优化方案**：已规划进 task98（生产可复用验收体系）：`verify.py all` 作为 CI gate 入口 + 废弃旧 `assert n >= 100`（改用精确表数断言 97）。本任务不阻塞（task07 是数据基线，task98 紧随其后做基础设施）。

**最小验证方法**：task98 完成后 CI workflow 调用 `verify.py all`，人为注入一行坏数据 → CI 变红拒绝合并。

**预期收益与成本**：收益=后续改表/新功能自动门禁；成本=已计入 task98（L 工作量）。

## 修复质量总评
| 项 | 结果 |
|----|------|
| 常规验收（4 项卡口） | ✅ verify_schema 0 差异 / counts 精确 / quality 5 维度 / 关联 0 孤儿，exit 全 0 |
| P2 精确断言 | ✅ series/bank/question 精确期望（偏差≤0.5% 文档容差），无 `>=` 下限 |
| P3 动态计算 | ✅ `org_count=SELECT COUNT(DISTINCT id) FROM org_institution`，期望 219*2*org_count / 73*org_count / 1752*org_count，无硬编码 6 |
| P5 5 维度 | ✅ quality 脚本覆盖完整性(外键+引用)/唯一性(编码+逻辑)/有效性(金额枚举日期)/一致性/时序性(实测分布打印) |
| 修复真实 bug | ✅ verify_schema 4 解析 bug + task03_alter sys_user 列缺失（DDL 重建后补 account/username/status） |
| 备份 | ✅ 956MB pre_ddl_reload 备份 |
| P4 CI 门禁 | ⚠️ 缺口 → 转 task98 |