# task-FE-O1: 管理端观测面板（前端消费 task-O1 新端点）

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W2（依赖 task-O1 契约）｜**工作量**：M
> **前置**：task-O1（后端观测性契约冻结）、task55（admin/dashboard 现有管理端框架）｜**后置（联调节点）**：消费 task-O1 契约（/api/metrics/* + /api/metrics/trace/{trace_id}）
> **规范状态**：doc-frontend §二 P18 扩展（管理端监控面板区块）

## 1. 选型依据
- task-O1 文档：5 维指标（记忆命中率/压缩效率/工具调用成功率/缓存命中率/并发排队超时率）+ `/api/metrics/trace/{trace_id}` trace 检索
- production-upgrade-plan.md P8（观测性：Codex OTel 实践 → 前端可视化 = 运维/排障入口）
- 前端现有模式：task55 admin-dashboard 图表体系（echarts + chart-palette 8 色）可复用

## 2. 现状（重要）
- **当前前端无观测面板页面**——task-O1 新端点未同步到前端（2026-08-26 核查确认）
- 本任务**新建**管理端页面承接，不影响现有管理端 6 项导航
- 依赖 task-O1 后端契约冻结后开发（当前 task-O1 未开始）

## 3. 实现规划要点
- 管理端新增「观测面板」页（admin/observability）：
  - **5 维指标卡**：记忆命中率 / 压缩效率（压缩前后 token、丢轮数）/ 工具调用成功率 / 缓存命中率 / 并发排队超时率（echarts 折线/柱状）
  - **trace 检索**：输入 trace_id → `GET /api/metrics/trace/{trace_id}` 展示事件链（LLM 调用/工具调用/记忆事件/压缩记录，时间线）
  - **告警态**：缓存命中率低 / 排队超时率升高 → 醒目告警色（对齐 Claude 缓存命中 SEV 实践）
  - **审计视角**：trace 事件链含 memory_event/tool_result/retry 结构化展示
- candy-playful token；grep 5 项全 0；管理端 6 项导航含观测入口

## 4. 验收标准（Given/When/Then）
- Given 管理端打开观测面板，When 加载，Then 5 维指标卡真实数据渲染（echarts 8 色板）
- Given 输入有效 trace_id，When 检索，Then 展示该 trace 全事件链（类型/时间/耗时/结果）
- Given 缓存命中率 < 阈值，When 面板加载，Then 告警态醒目提示
- Given 后端未接线（task-O1 未冻结），When 页面加载，Then 契约缺口实披露不写 MOCK（同 task60 模式）

## 5. 交接与记忆
- 完成 → 看板 task-FE-O1=DONE → sync.ps1
- 交付物：观测面板页 + React + 测试
- 契约依赖：task-O1 冻结后开发，缺契约则断点保存

## 6. 批判承接
- production-upgrade-plan.md P8（观测性黑盒）：前端可视化面板 = 运维排障的"为什么用户 X 没召回记忆"的查询入口