# 执行排序 / 契约冻结 / 集成 Gate（优化期 v1.0）

## 1. 执行排序总表

| 批次 | 内容 | 并行度 | 解锁条件 |
|---|---|---|---|
| S1 | task101（edu-api.js 加固） | 单线先行 | 分支 `feature/opt-w0` 建立；**用户确认 D1~D5 默认方案**（未确认时 S1 可先做与契约无关部分） |
| S2 | task102 + task103 + task104 | 3 线并行 | task101 合入 |
| S3 | task105~task110（6 线并行，受平台数约束取 2~3） | 并行 | task101 合入 |
| S4 | task113（BE 安全包） ∥ task114 ∥ task61（契约⑥已冻结） | 3 线并行 | task113 与 task114/115 无文件交集，可并行；task61 随时可开 |
| S5 | task115 ∥ task116 | 2 线并行 | task114 契约核验完成（同文件低风险，串行更稳则顺延） |
| S6 | task117（admin-courses CRUD） | 单线 | **task116 DONE**（完成依赖）+ C-C 契约已验收 |
| S7 | task118~task121 | 2~4 线并行 | task101 合入；task120 需在 task113 移除 correct 前或同 PR 完成判分切换 |
| S8 | task122 ∥ task123 | 2 线 | 各波次合入后收尾 |

每批次下发前重算可并行集（动态，不一次规划死）；"契约依赖"等契约单**经测试 agent 机械核验置"契约已验收"**即解锁，"完成依赖"（task117←task116）严格等 DONE。

## 2. 契约冻结清单

| 编号 | 冻结单 | 内容 | 写单方 | 核验方 | 解锁 |
|---|---|---|---|---|---|
| ⑥（既有） | handoffs/task36-contract.md | RAG 上传 6 端点 | task36 | 已冻结 | task61 ✅ 可开工 |
| C-A | handoffs/task114-contract.md | 全站响应壳统一 + `/api/users/me` 新契约 + DashboardOut 扩展（D4） | task114 | codex 独立 L1/CDC | task105 复核、task106/107 消费面回归 |
| C-B | handoffs/task115-contract.md | 全站分页 DTO 统一（D2）+ SSE `error` 事件结构 | task115 | codex | task103 分页、task106 复核、chat 前端错误分支 |
| C-C | handoffs/task116-contract.md | 系列删除语义（D3：软删+明示"已下架"+列表过滤） | task116 | codex | task117 |

契约状态机：待验收 → 已验收(解锁) → [上游改动] 契约变更单 → 待重验。契约变更 → 受影响下游退出 READY。验收要求契约单含**真实 curl 请求/响应示例**。

## 3. 集成 Gate（编排者独占）

- **L0 合并检查点（每批次必跑）**：`git diff` 两开发分支 changed-files 交集扫描，同文件双改 = 最高冲突信号 → 人工合并决策。
- **L1 契约 CDC**：C-A/C-B/C-C 冻结后 schemas diff vs 前端消费点 grep，差异 = 阻断。
- **L2 冒烟（每波次合入后）**：后端起 8000 跑 `python test-reports/interface_acceptance_final.py` 全绿；前端 `vitest` 491 用例全绿。
- **L3 变更影响回归**：涉及域的 pytest 契约测试子集。
- **L4 全量回归（里程碑，W4 后）**：全量 pytest + 137 端点冒烟 + 22 页渲染截图视觉验收。
- 部署 gate：task123 的 DEBUG=False 检查单全绿才允许出包（教训⑥）。

## 4. 产物落盘（引用传递）

| 产物 | 路径 | 谁写 |
|---|---|---|
| 完工报告 | test-reports/taskNN-completion-report.md | 开发 |
| 契约单 | handoffs/taskNN-contract.md | 开发（BE） |
| 验收报告 | test-reports/taskNN-fe-tester-report.md | codex |
| 技术批判 / 优化方案 | .ai-hub/plans/tasks/taskNN-技术批判.md / -优化修改方案.md | codex |
| 看板 | D:\.ai-hub\memory\project-handoff.md（唯一事实源） | 编排者 |

状态词汇：TODO / DOING / READY_FOR_FRONTEND / DONE / BLOCKED（+HTML 态不适用本期，无新设计页）。

## 5. 开工 prompt 要素（每任务派发时生成）

必读：本任务详档 `tasks/taskNN-*.md` + audit 对应证据条目 + 相关契约单 + `AGENTS.md`（教训②③④⑥）+ critique-backlog-tracker。硬性守则：不改契约权威 schemas.py（契约任务除外且走冻结流程）；静态页注入不重定义全局 `$`/`renderSides`；每任务独立 commit；完工报告附实际调用证据；等验收再接下一任务。
