# TO-EXEC-TB5 — Agent 协作自证包（yy 十点修复 · P1）

> 分支 `feature/opt-waves`。owner 批评 9："AI Agent 协作工程必须给我好好测，并给出我自己可以验证的方案"。开工令自包含。

## 背景

多 Agent 协作工程是本项目面试主打议题（派单制/C-01 独立验收/盲测队列/git 竞态取证等），证据散落在 `.ai-hub/plans/artifacts/dispatch/`（17 份 REPORT）、`.opencode/plans/critique-backlog-tracker.md`、`test-reports/`。owner 需要一个 ≤15 分钟亲手复现的入口。

## 工作项

1. **`docs/agent-collab-verify.md`**（面向 owner 的实操文档）：
   - 一图看懂执行模型（编排者写令/执行者交回/信使传递/C-01 逐断言验收）。
   - 5 个「亲手验证点」，每个 ≤3 分钟，含精确命令与预期输出：
     ① 派单→报告对账：`git log --oneline -- .ai-hub/plans/artifacts/dispatch/` 数开工令与 REPORT 数量并抽查一对（TO-EXEC-* ↔ REPORT-*）字段闭环；
     ② C-01 抽验示范：挑 REPORT-TA2 的 DB 断言，给出 owner 可直接跑的只读 SQL（参数绑定示例）；
     ③ 盲测队列：`.ai-hub/plans/artifacts/dispatch/AUTO20/blind-test-queue.md` 状态机走读（B1-B9 已验项）；
     ④ 门禁即协作产物：跑 `node scripts/gates/dom-hook-inventory.mjs --all --check` 现场看 PASS；
     ⑤ 多 agent git 竞态取证：讲 `git reflog` 一案例（引用既有记录，不现场制造事故）。
   - 明确「哪些证据是自动化可重跑的、哪些是过程记录不可重放」——禁吹。
2. **`verify-auto20.cmd`**（仓库根）：一键跑可机验子集（G3 门 + dispatch 对账统计 + 关键 pytest 契约子集如 `-k "chat or favorite or hitl"`），输出汇总 PASS/FAIL 面板；**命令集固定白名单，不引入新依赖**；总时长 ≤5 分钟。
3. 实测：cmd 在干净 shell 跑一遍，报告贴完整输出。

## 铁律

- 域：`docs/agent-collab-verify.md`（新）、`verify-auto20.cmd`（新）。禁碰其它一切。
- 文中引用的每个数字/命令必须现场验过一遍才许写（C-01 同款纪律）；不确定的标「过程记录，不可重放」。
- 不 push；单 commit：`docs(verify)/tb5: Agent 协作自证包(15 分钟亲手验证手册+一键复核脚本)`。
- 报告 `.ai-hub/plans/artifacts/dispatch/REPORT-TB5.md`：五个验证点各自实跑输出、cmd 完整输出。

## owner 验收口径

Given owner 照文档操作，Then ≤15 分钟亲手复现协作工程核心证据，每步输出与文档预期一致。
