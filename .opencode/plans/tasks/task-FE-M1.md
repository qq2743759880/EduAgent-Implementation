# task-FE-M1: 个人中心记忆历史/回滚页（前端消费 task-M1 新端点）

> **类型**：frontend ｜**执行工具**：TraeWork ｜**阶段**：P6 ｜**并行组**：W1（依赖 task-M1 契约）｜**工作量**：M
> **前置**：task-M1（后端记忆事件溯源契约冻结）、task54（个人中心现有页）｜**后置（联调节点）**：消费 task-M1 契约（/api/memory/history + /api/memory/rewind）
> **规范状态**：doc-frontend §二 P19 扩展（个人中心记忆 Tab 区块）

## 1. 选型依据
- task-M1 文档 §5（契约冻结：/api/memory/history + /api/memory/rewind 响应壳对齐契约①）
- production-upgrade-plan.md P1（记忆事件溯源/审计可查 → 前端"记忆历史"可视化为审计证据链的一部分）
- 前端现有模式：task54 me 页 Tab 结构可复用（candy-playful FROZEN）

## 2. 现状（重要）
- **当前前端无任何记忆历史/回滚页面**——task-M1/O1 新端点未同步到前端（2026-08-26 核查确认）
- 本任务**新建**前端页面承接，不改现有契约⑤ /me 响应结构
- 依赖 task-M1 后端契约冻结后开发（当前 task-M1 未开始）

## 3. 实现规划要点
- 个人中心新增「记忆管理」Tab 或入口：
  - **记忆历史列表**：`GET /api/memory/history/{entity_id}` 分页事件流，展示 event_type（create/update/delete/consolidate/rewind）+ 时间线 + valid_to 状态（当前有效/已废弃）
  - **记忆回滚**：`POST /api/memory/rewind`（body `{entity_id, target_event_id}`），回滚按钮 + 二次确认 + toast
  - **状态徽章**：当前有效（绿色）/已废弃（灰）/已巩固（candy 渐变）
  - **审计信息**：每行展示 operator（user/admin/dream）+ trace_id（可折叠）
- candy-playful token；grep 5 项全 0；导航含个人中心入口

## 4. 验收标准（Given/When/Then）
- Given 用户有记忆事件流，When 打开记忆管理 Tab，Then 分页展示事件时间线（event_type/时间/状态徽章/operator/trace_id）
- Given 某条历史记忆，When 点回滚，Then 二次确认 → POST /api/memory/rewind → 列表刷新显示 rewind 事件 + toast
- Given 后端未接线（task-M1 未冻结），When 页面加载，Then 契约缺口实披露不写 MOCK（与 task60 learning 端点同模式）

## 5. 交接与记忆
- 完成 → 看板 task-FE-M1=DONE → sync.ps1
- 交付物：记忆管理页 + React + 测试
- 契约依赖：task-M1 冻结后开发，缺契约则断点保存（同 task61 BLOCKED 模式）

## 6. 批判承接
- production-upgrade-plan.md P1（审计可查）：前端可视化事件流 = 用户自证"AI 记录了什么"的证据链