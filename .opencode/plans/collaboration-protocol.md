# 前后端开发者工作对接守则（Trae(后端) ↔ TraeWork(前端) ↔ opencode(编排)）

> 定位：三工具并行开发时，如何保证接口/业务逻辑不乱、记忆不混乱。
> 原则：**单点事实源、契约先行、记忆分区、冲突上浮**。

## 一、角色与边界（谁写什么，绝不越界）

| 工具 | 角色 | 可写范围 | 禁止写 |
|------|------|---------|--------|
| **Trae** | 后端+数据库开发者 | `edu-agent/**`（Python）、`.opencode/plans/` 只读、MySQL/Milvus/Neo4j/Redis DDL 与数据 | `edu-frontend/**`、前端测试报告 |
| **TraeWork** | 前端开发者 | `edu-frontend/**`（TS/TSX）、`test-reports/fe-html/**`、前端测试报告 | `edu-agent/**`、数据库 DDL、Milvus/Neo4j 操作 |
| **opencode** | 编排者/仲裁者 | `.opencode/handoffs/**`、`.opencode/plans/**`、AI-Hub 交接状态、双方冲突裁决 | 业务代码（除非仲裁后派单） |

**越界规则**：任何一方需要修改对方文件（如 TraeWork 发现后端 schema 字段名写错）→ 不直接改 → 写 `.opencode/handoffs/taskMM-discrepancy.md` → 编排者仲裁 → 派单给对方工具执行。

## 二、接口契约纪律（业务逻辑不乱的根）

1. **契约唯一权威 = 后端 Pydantic schemas.py**。前端 API 客户端类型必须与之一一对应（snake_case）。
2. **契约冻结制**：后端每个域完成即冻结（写入 `handoffs/taskNN-contract.md`，含真实 curl 请求/响应示例）。冻结后字段变更必须走「契约变更单」：改后端 → 通知编排者 → 编排者同步更新 TraeWork 侧类型 → 双方一起改。
3. **前端不自行造接口**：页面需要新端点 → 写 `.opencode/handoffs/api-request.md`（需求/入参/出参期望）→ 编排者评估 → 派单 Trae 实现 → 契约冻结后 TraeWork 再写页面。
4. **错误码唯一权威**：`edu-agent/app/common/error_codes.py`（字符串错误码分段）。前端 `ApiError.code` 只消费不定义。
5. **每次交接前跑契约一致性检查**：`scripts/contract-diff.py`（对比 schemas.py 与 src/lib/api/*.ts 字段集；差异=阻断交接）。

## 三、AI-Hub 记忆分区（如何不混乱）

> 中心库 `D:\.ai-hub\`，按工具分区注入，**同一主题两处都记**（交叉引用，不复制冲突内容）。

### 3.1 记忆文件分区图

```
D:\.ai-hub\memory\
├── trae-projects\-e-stu-...-EduAgent-...\project_memory.md   ← Trae 事实源（后端/数据库记忆）
├── trae-global-memory.md / trae.md                           ← Trae 全局渲染
├── trae-global-memory.md / trae-global-memory.md                         ← TraeWork 全局渲染
├── agent-memory\<agent>\*.md                                 ← 各子代理记忆
├── project-handoff.md                                        ← 【新增】跨工具交接状态看板（唯一事实源）
└── opencode-global-memory.md                                 ← opencode 编排记忆
```

### 3.2 记忆写入规则（谁写什么）

| 记忆内容 | 写入者 | 写入位置 |
|---------|--------|---------|
| 数据库表结构/DDL/重灌进度/后端契约 | Trae | `trae-projects/.../project_memory.md` |
| 前端页面/组件/tokens/HTML 审核进度 | TraeWork | `trae-global-memory.md`（或新建 `traework-projects/...` 分区，规则同 trae-projects） |
| 跨工具状态（任务看板/契约冻结/冲突裁决） | opencode | `D:\.ai-hub\memory\project-handoff.md` |
| 共享事实（edu.sql 权威、环境速查、VM 根因） | 双方都写 | 各自分区各写一份（内容相同允许，交叉校验） |

### 3.3 同步节奏与冲突处理

1. 每完成一个 task（或契约冻结）→ 各自跑 `powershell -File D:\.ai-hub\sync.ps1`
2. sync 方向：**trae-projects 以 Trae 侧为事实源**（编辑 Trae 侧 `C:\Users\Administrator\.trae-cn\memory\projects\...` 后 sync 回 Hub）；opencode 直接写 Hub 侧 `project-handoff.md`
3. 冲突上浮：双方记忆对同一事实记录不一致 → 编排者以 `project-handoff.md` + 代码实体（schemas.py/实际 DDL）裁决
4. 每日开工三步：① 读 `project-handoff.md` 看板 ② 读本工具分区最新记忆 ③ 读对方最新契约交接单

### 3.4 环境配置速查（开工前确认）

| 项 | 值 |
|----|----|
| Trae 规则文件 | `C:\Users\Administrator\.trae-cn\user_rules\ai-hub.md`（AI-Hub 已渲染） |
| TraeWork 配置 | `C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\User\ai-hub.md`（AI-Hub 已渲染，mem0 只读） |
| opencode 全局 | `C:\Users\Administrator\.config\opencode\AGENTS.md`（AI-Hub 已渲染） |
| 共享 MCP | `D:\.ai-hub\mcp\index.json`（mem0/serena/context7/playwright/mysql） |

**⚠️ Trae 环境限制（2026-08-18 实测，任务执行必须遵守）**：

| 限制 | 影响 | 替代方案 |
|------|------|---------|
| `Workflow()` API 为 opencode 专属，Trae Code 无此 API | 无法脚本化拉起 8 阶段流程 | 读 `dev-standard.mjs` 按 8 阶段**手动调度**子代理（开发→测试→修正→审查→提交），效果等价；任务文档 §3 已统一改为手动调度说明 |
| mysql MCP 未在 Trae 环境注册（当前仅 integrated_code_mode / integrated_goal） | 测试无法走 mysql MCP 直查 | 测试子代理改用 **RunCommand + mysql CLI / Python 校验脚本**（先例 verify_schema.py / verify_task07_counts.py）；或手动在 设置→MCP 按 `D:\.ai-hub\mcp\index.json` 模板添加 |


## 四、沟通协议（不阻塞的最小开销）

1. **异步为主**：一切通过 `project-handoff.md` + `handoffs/*.md` 交接，不要求同时在线。
2. **同步窗口**：每日一次对账（编排者核对看板与实际代码状态）。
3. **阻塞上报格式**：`BLOCKED: taskMM 依赖 taskNN，原因：xxx，期望：xxx` 写入看板 → 编排者 30 分钟内响应。
4. **验收裁决**：Given/When/Then 验收由执行工具自查 + 编排者抽查；E2E（task69）为最终裁决依据。

## 五、回传机制（员工 → 用户 → 编排者）

1. **员工完工必写报告**：每任务完成后，按 `.opencode/plans/task-report-template.md` 模板写入 `test-reports/{taskNN}-completion-report.md`（GWT 逐条自查 + 证据 + 偏差 + 待决策项），并跑 sync.ps1。
2. **用户只转告一句话**：员工说干完了 → 用户只需告诉编排者"taskNN 做完了"，编排者直接读报告文件验收（不必转发大段对话）。
3. **验收结论三选一**：
   - 通过 → 编排者更新看板 + 给出下一任务开工指令（交用户转贴给对应员工）
   - 有条件通过 → 编排者写修正意见（读哪份报告哪个 FAIL 项）→ 交用户转贴给原员工返工
   - 退回 → 编排者说明原因，员工按意见重做并重写报告
4. **HTML 原型审核例外**：前端页面任务的 HTML 原型阶段，员工直接在会话中提示"原型已产出"，用户查看/给图后把修改点转告编排者，由编排者转成返工指令。

## 六、开工检查单（每个工具每任务开工前）

- [ ] 读 `D:\.ai-hub\memory\project-handoff.md` 确认前置任务 DONE
- [ ] 读本工具分区最新记忆
- [ ] 前端任务：确认依赖契约交接单存在且 READY
- [ ] 后端任务：确认数据基线/表结构版本匹配
- [ ] 跑契约一致性检查（前端）/ pytest（后端）
- [ ] 完成后：写 `test-reports/{taskNN}-completion-report.md` 完工报告 + 跑 sync.ps1
