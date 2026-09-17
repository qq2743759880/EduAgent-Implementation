# KICKOFF 模板（W-NEXT-* 单写者任务派单标准格式）

> 单一事实源：`.ai-hub/plans/artifacts/kickoff-<TASK_ID>.md`；本模板用于派单侧快速复制。
> 编排者复制本文件 → 重命名 → 按需填空 → 下发；子 agent 单写者按文件归属/验收 GWT/Mimosa 约束闭环。

---

## 1. 任务 ID / 标题

```
任务 ID：<W-NEXT-XXX-NNN 或 fix(scope)/<scope>-<desc>>
标题：<一句话任务目标>
类型：fix | feat | refactor | docs | test
优先级：P0 | P1 | P2
单写者锁：<workspace>/<lockfile>
分支：feature/opt-waves（git symbolic-ref HEAD 必须 refs/heads/feature/opt-waves）
```

## 2. 起源（为什么做 / 编排者盲测 / 编排者发现）

```
盲测发现：<具体可复现的异常 / 阻断 / 红项>
实证路径：<报告或探针输出>
关联任务：<其它已闭环/进行中的任务>
风险评估：<是否生产路径 / 是否数据写入 / 是否需要 8000/3000 重启>
```

## 3. 文件归属（仅限，与其他并行任务互斥）

> 单写者强约束：**只动本表内文件**。其他文件即使相关也不碰（避免并行 agent 互相覆盖）。

| 文件 | 类型（新建/修改/只读）| 行数/字节 | scope 内 | 备注 |
|---|---|---|---|---|
|  |  |  | ✓ |  |
|  |  |  | ✓ |  |

## 4. 验收 GWT（5 步全绿才 PASS）

```
G1：<可机验 + 一手数字>
G2：<可机验 + 一手数字>
G3：<可机验 + 一手数字>
G4：<可机验 + 一手数字>
G5：既有 0 回归（<具体回归范围>）
```

## 5. 数据安全

```
- 只读 / 写 / 改路径：<具体>
- 是否动 .env：<否/是（具体哪几行）>
- 是否起停服务：<8000/3000/容器/etc>
- 是否写 DB：<否/是（具体表/字段）>
```

## 6. Mimosa 安全约束（三条必读）

```
① host 写死 127.0.0.1（仅本地后端；非 loopback 立即 SystemExit）
② DB 参数绑定（无字符串拼接 SQL；未来扩展一律 %s / ? 占位）
③ 密钥仅从环境变量读（绝不写死在源码 / 配置文件 / 日志输出）
```

## 7. Git 纪律

```
- commit 前：git symbolic-ref HEAD 必须 refs/heads/feature/opt-waves（非 detached）
- commit 后：git rev-parse HEAD 立即验证 SHA
- 若 unborn 或分支丢失：git update-ref refs/heads/feature/opt-waves <真 tip> 修复
- 单 commit 仅本任务文件（pre-commit hook 不入 commit 自身）
- 并行 agent 持续 git pack-refs --all 会剪松散 ref —— 必要时手动重挂 ref + 同步 packed-refs
```

## 8. 完工交付

```
- commits: <type(scope)/<TASK_ID>-<desc>>
- 报告: test-reports/<TASK_ID>-completion-report.md
- 锁文件: 完工即删
- 完工输出: commit 列表 + 报告路径 + 各 GWT 数字
```

## 9. 关键教训（防复发）

> 从 AGENTS.md / 历史 critique 报告 / 同类任务教训中摘录相关条目，每条 ≤1 句。

```
1. <教训标题> — <来源 + 简短说明>
2. ...
```

---

## 模板使用提示

- 派单时**直接复制本文件**到 `.ai-hub/plans/artifacts/kickoff-<TASK_ID>.md`，再按需改字段。
- 子 agent 开工前先读 AGENTS.md「当前架构」「关键教训」「待办」三段。
- 子 agent **绝不采信报告原文** —— 每条断言必须亲自查/读/grep 实证。
- 完工报告的「关键设计决策」「自清记录」两段务必填实，编排者据此验收。
