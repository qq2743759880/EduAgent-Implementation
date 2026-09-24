# TO-EXEC-TC1 — 26 主张全量重测矩阵（yy · P2）

> 分支 `feature/opt-waves`（开工前 `git log --oneline -3` 记基线）。owner 原始要求："26 个可测主张里就算报告✅的也有重测，全量重测"。**服务重启只准用仓库根 `start-eduagent.cmd`（独立窗口）；执行者会话内 run_in_background 起的服务会随会话退出被杀（2026-09-24 三次无声死亡根因）。**

## 背景

P0+P1 十四单已全部落地（流式打字机/黄条/HITL 卡/图谱推荐/Jaeger 瀑布/基础设施页/控制台 UX/TA5 并发槽/TA6 零 ID）。简历主张的旧证据多为此前日期，需要"今日实测数字+复现命令"的全量矩阵。

## 主张清单来源（按优先级）

1. **owner 随开工令附的简历原文**（信使转派时粘贴）——以此为准逐句拆主张；
2. 未附则以仓库权威清单合并去重：`docs/check-demo-21项详解.md` + `docs/面试演示-逐步点击手册.md` 全部站点 + `.opencode/plans/critique-backlog-tracker.md` 已闭环项。
目标 22~28 条主张，每条一行矩阵。

## 工作项

1. 逐条重测：每条主张给「今日实测数字 + 可复现命令（curl/pytest/gate/SQL 只读）/ PASS-PARTIAL-FAIL」。**数字必须今天亲跑产出**，禁抄旧报告；跑了但环境不允许的如实标 SKIP+原因。
2. 已知现状校准点（实测时留意）：① "三路融合"图谱路已真实接线（`/api/recommend/next` student 账号 `graph_source=neo4j`）——简历措辞可保留；② OTel+Jaeger 真瀑布已闭环（127.0.0.1:16686 有分层 span）——措辞可保留；③ 非流式 P95 14.8~19.7s 未变（推理模型下限），流式为准；④ `session_asset`/`session_video` 占位域仍冻结未清——简历如有相关表述给修订建议。
3. 措辞修订建议：凡实测与简历表述有出入的，给"建议改成"的替换句（可机验口径），汇总成矩阵末节。
4. 产物：`docs/简历实测矩阵.md`（矩阵表+修订建议节+复现命令附录）。

## 铁律

- 只写 `docs/简历实测矩阵.md`（新文件）+ 报告；零代码/配置改动。DB 断言只读+参数绑定。API key 禁入文档。
- 不 push；单 commit：`docs(verify)/tc1: 简历主张全量重测矩阵(今日实测+复现命令+措辞修订)`。
- 报告 `.ai-hub/plans/artifacts/dispatch/REPORT-TC1.md`：矩阵全文+跑批统计（PASS/PARTIAL/FAIL/SKIP 计数）。

## owner 验收口径

Given owner 拿到矩阵，When 抽 3 条按命令复跑，Then 输出与矩阵数字一致；FAIL/PARTIAL 项能指到具体证据。
