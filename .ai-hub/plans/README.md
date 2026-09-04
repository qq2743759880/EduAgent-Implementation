# EduAgent 前后端一致性优化 · 计划索引（v1.0，2026-09-02）

> 编排者：ZCode 会话（tt 闭环第 1~5 步产物）。第 7 步（并行派单）待用户确认决策点后启动。
> 本目录是**本轮优化**的唯一计划事实源；上游总计划 `.opencode/plans/dev-plan.md`（v3.4，建设期 100 任务）继续有效，两计划编号不重叠（本轮 task101+，沿用 task61）。

## 文档清单

| 文档 | 内容 |
|---|---|
| [audit-20260902.md](audit-20260902.md) | 实证审计：前端 22 页逐页结论、后端路由面缺陷、**前后端契约不符清单 X1~X9**、遗留 L1~L21 |
| [prd-optimization-v1.md](prd-optimization-v1.md) | 修改规划：目标 O1~O5、非目标、阶段、**决策点 D1~D5（待用户确认）**、风险回滚 |
| [dev-plan.md](dev-plan.md) | 任务总纲：前提挑战、5 波次 22 任务、依赖图、**规划自审（三视角）** |
| [task-agent-matrix.md](task-agent-matrix.md) | 7 平台角色分配 + 任务×agent×skill 矩阵 + 验收链 |
| [orchestration-execution.md](orchestration-execution.md) | 执行排序 S1~S8、**契约冻结清单（C-A/C-B/C-C + 复用⑥）**、集成 Gate L0~L4 |
| tasks/taskNN-*.md | 22 个任务详档（每任务：目标/证据/改动点/GWT 验收/风险） |

## 全局决策（一句话版）

1. 架构不动：fe-html 静态页 + 8000 FastAPI。
2. 优先级：**W0 动线阻断（P0）→ W1 契约对齐 → W2 安全与契约统一 → W3 功能完善 → W4 卫生收尾**。
3. 三项契约变更走冻结流程：C-A 响应壳统一、C-B 分页+SSE error、C-C 删除语义；冻结单含真实 curl 示例，测试 agent 核验后才解锁下游。
4. 验收纪律：requests/curl + pytest 独立实证，禁 Playwright；前端结构断言 + 渲染截图视觉验收；每任务独立 commit。
5. 部署门：DEBUG=False 检查单（task123）全绿才出包。

## 启动前待用户确认（阻塞 S1 之前）

- [ ] D1~D5 默认方案（PRD §5）：壳统一 / 分页并入 / 删除=软删下架 / DashboardOut 扩展 / 孤儿模块归档。
- [ ] 波次范围是否接受（22 任务 ≈ 5 个批次）；是否裁剪 W3。
- [ ] 派单平台：默认 trae=FE、claude=BE、codex=验收（可覆写）。

## 状态看板

| 批次 | 任务 | 状态 |
|---|---|---|
| S0 | 计划编制（本目录） | ✅ v1.0 |
| S1 | task101 | TODO（待确认 D1~D5） |
| S2 | task102/103/104 | TODO |
| S3 | task105~110 | TODO |
| S4 | task113/114/61 | TODO |
| S5 | task115/116 | TODO |
| S6 | task117 | TODO（依赖 task116） |
| S7 | task118~121 | TODO |
| S8 | task122/123 | TODO |

> 跨会话看板同步：派单启动时由编排者把上表同步至 `D:\.ai-hub\memory\project-handoff.md`（唯一事实源），本轮规划阶段不改写看板。
