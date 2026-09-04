# 下一季（Season 2）任务对账与编排方案（2026-09-03）

> 回答"前面未开工的几十个 task 怎么编排"。结论先行：**v3.4 总计划 task00~99 绝大多数已 DONE**（看板 61 行任务表中 DONE 占绝大多数），真实存量按四类清点如下。第一类不需要"编排"，需要的是用户一个架构决策。

## 第一类：完工待验收（3 项，最高优先——已有人交工没人验）

| 任务 | 内容 | 证据位置 |
|---|---|---|
| task98 | verify.py 生产验收体系（schema/counts/quality/pytest 五命令，独立分支 feature/task98-db-acceptance） | test-reports/task98-completion-report.md，自称 verify.py all EXIT=0 |
| task99 | auth 补生成 100015 用户（bcrypt 校验 20/20 PASS，分支 feature/task44-courses） | test-reports/task99-completion-report.md |
| task-P1C | Neo4j/Redis 断连熔断（三路径接入，7/7+22/22 PASS） | test-reports/task-P1C-completion-report.md |

编排：三个**验收任务**（半张开工单的量）——新编排者按 tt §5.2 独立实证复现即可，通过则补 commit + 看板 DONE，不通过出返工单。

## 第二类：真未开工的后端任务（4 项）

| 任务 | 内容 | 前置 | 备注 |
|---|---|---|---|
| task35 | Neo4j 图谱重建（task34 重建知识库后 Neo4j 0 节点，图谱扩展通道空转） | VM 已恢复（08-31 确认） | 看板标注"下一后端任务" |
| task45 | 搜索（契约②已冻结） | 无 | 范围需先核对（前端搜索还是后端检索增强） |
| task66 | 退款状态机 | task19/28 已 DONE | backlog 遗留 |
| task92批判① | task24×task92 集成验证（子代理 runner 与 LangGraph 实链） | 两者均 DONE | 半张验收单 |

另：task39 遗留清单（压测 P95/escalation/真 Redis 分布式/冷启动预热）——按批判闸门逐条清算或显式降级。

## 第三类：React 前端线的待开工项（数量大头，押一个决策）

kanban 待办：task43（React dashboard）、task61（React 版 /admin/rag）、task70~91（管理端页面批，最多 ~14 页）、task-FE-M1（记忆历史/回滚页）、task-FE-O1（观测面板）。

**关键事实**：这些全是 React 线任务（edu-frontend React app + api-client.ts）。但 08-31 起**线上前端已切换为 fe-html 静态页**（commit 3e3817f + AGENTS.md），且本轮优化期把 fe-html 的对应能力补齐了大半（管理端 8 页接入/守卫/CRUD 接线中）。两条线并存 = 双倍维护。

**⬅ 用户决策点 S2-D1（✅ 2026-09-03 已拍板：方案 B——React 线继续）**：
- **方案 B（已选）**：先派 task114/115（C-A 响应壳统一 + C-B 分页统一）再批量做 React 页——React 页不做双壳解析；管理端 ~14 页按 6 页/批 × 3 批编排，每批契约先行 + 批判闸门；FE-M1/O1 随批派发。
- 执行序锁定：C-A/C-B（优化期 task114/115）→ React 管理端三批 + FE-M1/O1（Season 2 主体）。
- 派发约束：后端多线并行时各执行者用隔离端口自测（参照 task116 的 8077 模式），受管 8000 仅编排者在验收时重启。

## 第四类：优化期自身尾巴（本季内闭环）

task117（在途待回传）→ task114/115（派发时机同上）→ task122/123 → L4 全量回归 → W2 批判闸门 → 看板同步。另有 W1 批判遗留 C-15~C-18（tracker 已登记）。

## 编排纪律（沿用不变）

每批 ≤6 任务、契约先行（先冻结后消费）、开工单具名资产（A/B/C 分级）、独立实证验收、每批跑批判闸门、看板是唯一事实源。执行者分工沿用：前端 Trae、后端 Claude Code、验收复核 codex（均可换，流程不依赖平台）。

## 建议的派发顺序（Season 2 总序）

1. 三项完工验收（第一类，零开发量）
2. 问用户 S2-D1 → 顺手确认 C-A/C-B 是否随本轮做
3. task35 + task66 + task45（后端批，2~3 线并行）
4. 按决策结果派前端批（A：6~8 个 fe-html 增强；B：C-A/C-B → React 三批）
5. 全量回归 + 批判闸门 + 看板收口
