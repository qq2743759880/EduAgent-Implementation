# task-S1 — 全流程 HITL 护栏（非单点审批）

> 执行工具：**Trae** ｜ 依赖：task28（现状 hitl_graph） ｜ 状态：TODO
> 修订来源：`.opencode/plans/production-upgrade-plan.md` P12（HITL 单点审批）
> 核心定位：HITL 从"只在退款节点"升级为**全流程透明护栏**——高风险动作（写文件/执行命令/网络访问/退款）前统一过 `HITL-Gate`：**解释→提议→同意→执行**；可选 **AI 审查 AI**（reviewer 子代理决策，对齐 Codex auto-review）。

## 1. 任务卡片

- **类型/工具**：backend（安全护栏） / Trae
- **依赖**：task28（`app/domains/trade/refund/hitl_graph.py` 现状：退款 HITL 状态机）、task92（reviewer 子代理 fork 能力）
- **并行组**：W3（第三批 P2，与 task-T1/R1 并行）
- **工作量**：**M**
- **测试窗口纪律**：HITL-Gate 纯状态机随时可测；AI 审查 AI（reviewer LLM）仅窗口内

## 2. 选型依据（竞品实证，引用 production-upgrade-plan.md）

| 竞品 | 做法 | 参考 URL |
|---|---|---|
| **Codex auto-review** | 文件写入/网络/越权前经 reviewer 代理审查；**3 连续拒绝熔断** | https://developers.openai.com/codex/concepts/sandboxing/auto-review |
| **Claude** | 解释→提议→同意→行动透明护栏；permission 规则 | production-upgrade-plan.md P12 引述 |

## 3. 实现规划要点

### 3.1 统一 HITL-Gate（新增 `app/ai/hitl_gate.py`）

- `HitlGate` 统一护栏入口，四步状态机 `explain → propose → approve → execute`：

```python
class HitlGate:
    async def explain(self, action: HitlAction) -> dict: ...   # 生成风险解释（动作/影响/理由）
    async def propose(self, action: HitlAction) -> dict: ...   # 提议具体执行方案
    async def approve(self, action_id, decision: bool, operator) -> dict: ...  # 用户同意/拒绝
    async def execute(self, action_id) -> dict: ...            # 同意后执行 + 落审计
```

- `HitlAction` 数据契约：`{action_type∈{write_file,exec_command,network_access,refund}, target, params, risk_level∈{L1,L2,L3}, explain_text, propose_text, trace_id, operator}`；
- **高风险动作清单**（与既有 MCP `risk=write` 联动）：`app/mcp/executor.py` 写工具（write_*/create_*/delete_*/update_*/send_* 前缀）执行前、`app/domains/trade/refund` 退款、管理端越权操作（`admin_user_impersonate`）前，统一调用 `HitlGate`；
- 审批存储：MySQL `hitl_approval` 表（`action_id/action_type/params_json/risk_level/status∈{pending,approved,rejected,executed}/operator/trace_id/created_at`）+ Redis 缓存 pending 态（TTL `HITL_PENDING_TTL_S=600`，超时自动拒绝）；
- 与既有 `hitl_graph.py` 兼容：退款 HITL 状态机改为复用 `HitlGate` 内部状态（旧接口保留为薄封装）。

### 3.2 AI 审查 AI（可选 reviewer 子代理）

- 配置 `HITL_AI_REVIEW=True` 时：approve 前 fork task92 reviewer 子代理，对 `propose_text` 做风险审查（输出 `{verdict: approve|reject|escalate, reason, confidence}`）；
- **3 连续拒绝熔断**（对齐 Codex auto-review）：同一动作类型连续 3 次被 reviewer 拒绝 → 直接中断该动作并转人工升级（`status=escalated`），不反复尝试；
- reviewer 拒绝需显式 override 路径（管理员 `force_approve`，落审计）。

### 3.3 配置项

```python
HITL_ENABLED = True
HITL_RISK_THRESHOLD = "L2"        # ≥L2 动作必过 Gate；L1 只记审计
HITL_PENDING_TTL_S = 600
HITL_AI_REVIEW = True             # AI 审查 AI 开关
HITL_REJECT_BREAKER = 3           # 3 连续拒绝熔断
```

### 3.4 测试

- `tests/test_contract_task_s1.py`：四步状态机流转、pending 超时自动拒绝、reviewer 3 连续拒绝熔断 + 人工升级、force_approve override 审计、与退款 HITL 兼容回归。

## 4. 验收标准（Given/When/Then）

- **AC1（全流程护栏）**：Given 用户触发高风险动作（写文件/执行命令/网络访问/退款任一），When 动作执行前，Then 必过 HITL-Gate（explain→propose→approve），未批准前动作零执行。
- **AC2（解释→提议→同意→执行）**：Given 高风险动作进入 Gate，When 完成四步，Then 每一步都有审计记录（`hitl_approval` 表含 explain_text/propose_text/operator/trace_id），用户界面可见风险解释与执行方案。
- **AC3（超时拒绝）**：Given 审批 pending 超 `HITL_PENDING_TTL_S=600`，When 到期，Then 自动拒绝（status=rejected），动作不执行。
- **AC4（AI 审查 AI）**：Given `HITL_AI_REVIEW=True`，When 用户 approve 前，Then reviewer 子代理给出 verdict（approve/reject/escalate）+ reason；Given 同一动作类型连续 3 次 reject，When 第 4 次，Then 熔断中断转人工升级（status=escalated），需管理员 force_approve 才放行（含审计）。
- **AC5（兼容回归）**：Given task28 退款 HITL 既有契约测试，When 改造后运行，Then 全 PASS（退款状态机语义 pending/approved/rejected/refunded 不变）。

## 5. 交接与记忆

- **完工报告**：`test-reports/task-S1-completion-report.md`（四步状态机流转、超时拒绝、AI 审查熔断、退款兼容回归）。
- **记忆写入**：AI-Hub `trae-projects/EduAgent/project_memory.md` 追加"全流程 HITL-Gate：解释→提议→同意→执行 + AI 审查 AI（3 连续拒绝熔断）"安全护栏决策。
- **完成动作**：git commit → sync.ps1。

## 6. 批判承接

- **production-upgrade-plan.md P12**（HITL 单点审批）：只在退款节点，应贯穿风险行动前 → AC1/AC2 落实。
- **critique-backlog-tracker.md**：task28 批判①「72h 超时 escalation 触发可靠性」——本任务 HITL 超时自动拒绝与升级路径复用同一 TTL/幂等语义，task39 验收时覆盖；task16 热门榜/写库类 MCP 工具（risk=write）纳入 HITL 清单核对。

## 7. 与其他 task 关联

- **联动**：task-T1（工具闭环中写风险工具的人工指南若涉敏感操作先过 HITL-Gate）；task-M1（rewind 回滚属高风险写操作过 Gate）；task-O1（hitl_approval 事件埋点）；task-A1（harness 工具节点调用 Gate）。
- **执行顺序**：W3 第三批；需 task28 退款 HITL 现状稳定 + task92 reviewer 子代理就绪（AI 审查开关可后开）。