# task-S1 完工报告 · 全流程 HITL 护栏 + AI 审查 AI

**角色**：EduAgent 重构项目【后端+数据库开发者】
**任务**：task-S1（P12 HITL 单点审批 → 全流程护栏）
**对齐**：Claude 解释→提议→同意→行动 透明护栏；Codex auto-review（3 连续拒绝熔断）
**测试窗口**：FAST = 火山 ark plan/v3 deepseek-v4-flash；HITL-Gate 状态机随时可测；reviewer LLM 仅窗口内

---

## 一、验收项达成（AC1~AC5）

| AC | 要求 | 落地 | 验证 |
|---|---|---|---|
| **AC1** | 高风险动作（写文件/执行命令/网络/退款）执行前必过 HITL-Gate（explain→propose→approve），未批准零执行 | `run_hitl_gate` 四步状态机；`executor._run_hitl_seam` 在 `HITL_ENABLED=True` 时拦截写工具，未批准返回 `SKIPPED`，**执行器 0 调用** | `test_s1_ac1_pending_zero_execution`、`test_s1_seam_pending_skips_execution` |
| **AC2** | 四步审计：记录含 explain_text/propose_text/operator/trace_id，用户界面可见 | `hitl_approval` 表四字段 + `HitlResult`/`MCPToolTestResp.manual_guide` 透出 | `test_s1_ac2_four_audit_fields`、真实样例见 §三 |
| **AC3** | pending 超 `HITL_PENDING_TTL_S=600` 自动拒绝 | 双路径：①后台 `sweep_expired_pending` 扫描；②resume 时按**原始 created_at** 计算超时 | `test_s1_ac3_sweep_expired`、`test_s1_ac3_resume_after_ttl_rejected` |
| **AC4** | AI 审查 AI：`HITL_AI_REVIEW=True` 时 reviewer 子代理 verdict（approve/reject/escalate）；同动作类型 3 次 reject→第 4 次熔断升级（escalated 需管理员） | `run_hitl_gate` AI 审查分支 + `store.get_reject_count` 熔断；`_RedisRejectCounter`（Redis 不可用时降级内存） | `test_s1_ac4_ai_reject_escalated`、`test_s1_ac4_breaker_after_three_rejects`、`test_s1_seam_ai_review_escalates` |
| **AC5** | 回归：task28 退款 HITL 契约兼容；既有路径零行为变化 | 新模块纯逻辑零 IO；`executor` 接入受 `HITL_ENABLED`（默认 False）门控，关闭时无任何分支触发 | task28+taks-T1 = 14 passed；task33 = 9 passed |

---

## 二、变更文件清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `edu-agent/app/ai/hitl_gate.py` | **新增** | 全流程 HITL 护栏核心：四步状态机 + AI 审查 + 超时 + 熔断；`MemHitlStore`/`MysqlHitlStore`；reviewer 工厂（task92 fork）。纯逻辑、零 IO（IO 全惰性导入）。 |
| `edu-agent/app/mcp/executor.py` | 修改 | 新增 `_classify_hitl_action`（写/执行/网络/退款工具分类，只读工具如 `web_search` 不拦截）；`_run_hitl_seam` 接入点；`call_tool`/`call_tool_with_retry` 在 `HITL_ENABLED=True` 时过 Gate。 |
| `edu-agent/app/config.py` | 修改 | 新增 `【task-S1 新增段】`：`HITL_ENABLED`(默认False)/`HITL_RISK_THRESHOLD`/`HITL_PENDING_TTL_S=600`/`HITL_AI_REVIEW`/`HITL_REJECT_BREAKER=3`/`HITL_OPERATOR`。 |
| `refactor_sql/task-S1-create-hitl-approval.sql` | 新增 | `hitl_approval` 审计表 DDL（status enum pending/approved/rejected/executed/escalated + 四审计字段 + `yn` 软删）。 |
| `edu-agent/tests/test_contract_task_s1.py` | 新增 | 16 个契约测试（AC1~AC4 + seam 拦截/放行 + 分类）。 |

---

## 三、四步审计样例（AC2，来自 live 模块真实输出）

`run_hitl_gate(HitlAction(EXEC_COMMAND, 'rm -rf /data', {force:True}, operator='op-42', trace_id='trace-abc'), human_decision=None)` 落库记录：

```json
{
  "action_id": "hitl-exec_command-29dab2e5eee4",
  "action_type": "exec_command",
  "target": "rm -rf /data",
  "params_json": "{\"force\": true}",
  "risk_level": "L2",
  "status": "pending",
  "explain_text": "即将执行【执行命令】高风险操作（风险等级 L2）。目标：rm -rf /data；该操作可能产生不可逆的副作用。请在确认参数合法与权限充足后批准。",
  "propose_text": "执行方案：执行命令 → 目标 rm -rf /data；参数摘要：{\"force\": true}。批准后即按此方案执行，结果将记入审计。",
  "operator": "op-42",
  "approver": "",
  "trace_id": "trace-abc",
  "ai_verdict": "",
  "ai_reason": "",
  "ai_confidence": null,
  "reject_count": 0,
  "server_id": null,
  "created_at": 1000.0
}
```

UI 透出（executor seam 返回的 `MCPToolTestResp.manual_guide`）：`hitl_action_id` / `status` / `explain_text` / `propose_text` / `operator` / `trace_id` / `needs_admin` / `ai_verdict`。

---

## 四、超时拒绝样例（AC3）

**后台扫描路径**：pending 创建后，`sweep_expired_pending(now=99999, ttl_s=600)` → 返回 `{scanned, rejected:1}`，记录置 `rejected`（reason="审批超时自动拒绝（后台扫描）"）。

**resume 路径**：首次 `run_hitl_gate(action, human_decision=None, now=1000)` 生成 `action_id`；超时后续审 `run_hitl_gate(action_with_id, human_decision=True, now=10999)` → 按原始 `created_at=1000` 判定 9999>600 → `rejected`。**不重复建单**。

---

## 五、AI 审查样例（AC4，来自 live 模块真实输出）

reviewer 返回 `reject` 时落库 + 熔断计数：

```json
{
  "status": "escalated",
  "ai_verdict": "reject",
  "ai_reason": "不可逆命令，未提供备份证明",
  "needs_admin": true,
  "reject_count": 1
}
```

**3 连拒熔断**：同 `action_type` 连续 3 次被拒 → 拒绝计数达 `HITL_REJECT_BREAKER=3`；第 4 次调用**不再调 reviewer**，直接 `escalated`（`ai_verdict="breaker"`），需管理员 `force_approve` 放行。对齐 Codex auto-review 3 连续拒绝熔断。

**熔断降级**：Redis 不可用 → `_RedisRejectCounter` 自动降级进程内 dict，熔断逻辑不因 Redis 抖动崩。

---

## 六、与 task28 退款 HITL 的关系（AC5 兼容性）

- task28 的 `hitl_graph.py`（LangGraph interrupt + Command resume 退款 HITL）**未改动**；S1 是独立的「全流程工具级护栏」，作用于 `executor.call_tool`/`call_tool_with_retry`，二者正交。
- 默认 `HITL_ENABLED=False`，S1 拦截逻辑零触发，task28 退款契约回归全绿（见 §七）。
- 后续如需让退款动作也走 S1 Gate，只需在配置将退款工具纳入分类（已支持 `refund` 动作类型）并开启开关，无需改 task28。

---

## 七、测试汇总

| 套件 | 结果 |
|---|---|
| `tests/test_contract_task_s1.py`（S1 契约，AC1~AC4 + seam） | **16 passed** |
| `tests/test_contract_task_t1.py` + `tests/test_contract_task28.py`（回归） | **14 passed** |
| `tests/test_task33_mcp_desc_review.py`（per-server 熔断/缓存/审计回归） | **9 passed** |

> 全部零 DB / 零 LLM / 零 Redis 依赖（注入 `MemHitlStore` + 假 reviewer + 假 executor），符合测试窗口纪律。

---

## 八、运维待办（非阻塞，验收后实施）

1. **建表**：目标库发布前执行 `refactor_sql/task-S1-create-hitl-approval.sql`（`IF NOT EXISTS` 安全）。
2. **开护栏**：运维在 `.env` 设 `HITL_ENABLED=True` 并确认 `HITL_RISK_THRESHOLD`；建议先对 `exec_command`/`refund` 灰度，再扩到 `write_file`/`network_access`。
3. **写工具注册**：确保被拦截的写工具已在 `mcp_tool` 注册且 `server_id` 正确（seam 执行阶段需定位 server 执行）。
4. **AI 审查窗口**：`HITL_AI_REVIEW=True` 仅测试/灰度窗口内开启（reviewer 走 FAST 模型）；生产常态化开启前需评估额度与延迟。
5. **超时扫描**：`sweep_expired_pending` 由后台定时任务调用（建议间隔 ≤ `HITL_PENDING_TTL_S/2`），负责后台自动拒绝过期 pending。
6. **管理端**：提供 `force_approve(action_id, admin)` 入口供管理员放行 `escalated`/`pending`/`rejected`。

---

## 九、git / 交付纪律

- 单 commit，5 个 S1 文件；保护 prior-task（task93/95/96）已 staged 文件不触碰。
- 完工报告 → `sync.ps1` → 停下等验收。
