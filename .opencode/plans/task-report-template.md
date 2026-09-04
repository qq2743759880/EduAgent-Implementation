# 任务完成结果报告模板（员工完工后必写，编排者验收唯一依据）

> 写入位置：项目根 `test-reports/{taskNN}-completion-report.md`
> 用户只需转告编排者："taskNN 做完了，报告已落盘"，编排者直接读此文件验收。
> 此模板供 Trae（后端）与 TraeWork（前端）通用，按实际填写，未涉及项写 N/A。

---

# taskNN 完成结果报告

| 项 | 内容 |
|----|------|
| 任务 | taskNN — <任务标题> |
| 执行者 | Trae / TraeWork |
| 完成时间 | YYYY-MM-DD HH:MM |
| 状态自评 | DONE / PARTIAL / BLOCKED |

## 1. 交付物清单

| 文件/产物 | 路径 | 说明 |
|----------|------|------|
| （例）重构 SQL | refactor_sql/xxx.sql | — |

## 2. 验收自查（对照 tasks/taskNN-*.md 的 Given/When/Then 逐条）

| # | 验收条目（GWT 摘要） | 结果 | 证据 |
|---|--------------------|------|------|
| 1 | （粘贴该任务 GWT 第一条） | PASS/FAIL | 测试输出/截图/命令结果路径 |
| 2 | ... | ... | ... |

## 3. 测试结果

- 测试命令与结果摘要（pytest / vitest / 冒烟 / EXPLAIN 等）
- 测试报告路径（test-reports/ 下）
- 失败项：无 / 有（列明，说明是否遗留及原因）

## 4. 契约交接单（仅契约冻结任务填）

- 交接单路径：`.opencode/handoffs/taskNN-contract.md`
- 冻结的端点/字段清单摘要（1-3 行）

## 5. 偏差与风险

- 与计划的偏差（无/有：说明）
- 遗留风险（无/有：说明）

## 6. 需要编排者决策的事项

- 无 / 有（BLOCKED 事项按「依赖谁/原因/期望」格式列明）

## 7. 收尾动作确认

- [ ] 已运行 `powershell -File D:\.ai-hub\sync.ps1` 同步记忆
- [ ] 已 git commit（commit hash: ____）
- [ ] 已通知编排者更新看板（或此报告即通知）

## 8. 下一任务建议

（依据 dev-plan 依赖图，建议编排者下一步派发：taskNN+1 / 解锁前端 taskMM / 等裁决）
