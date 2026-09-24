# TO-EXEC-TC3 — 手册更新 18 站（yy · P2 · 依赖 TC1/TC2 交回后开工）

> 分支 `feature/opt-waves`。owner 要求手册与实际 UI 逐站一致。**等 TC1、TC2 报告落盘后再开工**（需要它们的新站证据与实测数字）。

## 工作项

1. 通盘核对 `docs/面试演示-逐步点击手册.md`（现 16+ 站）与实际 UI：每站逐点击核对，删改失效步骤，补 4 个新站——
   - 基础设施页站（admin-infra.html：六卡+运行演示+数字变化）；
   - OTel/Jaeger 演示站（起容器命令 14318/16686、发问、UI 截图位置、停容器）；
   - HITL 确认卡站（TA6 零 ID 版话术：admin 只说课程名→卡→同意出课/拒绝不出课）；
   - 图谱推荐站补强（/api/recommend/next 的 graph_source=neo4j 现象+前端可见处）。
2. 急救包同步：后端死亡处置改为「先跑 start-eduagent.cmd；勿在 agent 会话内后台起服务」（三次无声死亡教训）；登录限流 60s/10 次提示。
3. 全站话术逐条实测：手册里每句触发话术今天必须真实跑过一次，失效即改。
4. `docs/用户使用手册.md` 同步 HITL/黄条/流式三节现状。

## 铁律

- 域：两本手册 + 报告。零代码改动；不 push；单 commit：`docs(demo)/tc3: 手册 18 站对齐实况(新四站+话术全量实测+急救包更新)`。
- 报告 `.ai-hub/plans/artifacts/dispatch/REPORT-TC3.md`：逐站核对表（OK/改了什么）、话术实测记录。

## owner 验收口径

Given owner 照手册从第 1 站点到最后一站，Then 每一步点击/话术与实际 UI 一致，无一处失效。
