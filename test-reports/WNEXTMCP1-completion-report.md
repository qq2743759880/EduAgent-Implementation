# W-NEXT-MCP-001 完成报告：三态能力审计 + 内置工具落审计 + 字段级脱敏

> 派单来源：`kickoff-WNEXTMCP1-mcp-tristate-builtin-log.md`
> 仓库分支：`feature/opt-waves`（提交前 `git symbolic-ref HEAD` 已确认，非 detached）
> 验证环境：后端 8000 在线（禁重启）；代码验证用 **8010 临时实例**（`MYSQL_HOST=127.0.0.1`，跑完关闭）；
> unit 验证用 `edu-agent/.venv/Scripts/python.exe -m pytest`（离线、确定性）。

## 交付文件（仅限本 kickoff 文件归属）

| 文件 | 改动 | 对应步骤 |
| --- | --- | --- |
| `edu-agent/app/mcp/capability_audit.py` | 新增 3 条跨模块对账行（permission_gate↔executor 接线） | 步骤1 (P0-①) |
| `edu-agent/app/mcp/executor.py` | `_execute_builtin_attempt` 落 `mcp_tool_call_log`；`_write_call_log` 加字段级脱敏+截断 | 步骤2 (P0-②) + 步骤3 (P0-③) |
| `edu-agent/scripts/check-demo.mjs` | 新增 ⑬「MCP 三态」健康门 | 步骤4 |
| `edu-agent/scripts/eval/mcp_tristate_probe.py` | ⑬ 探针（audit + 真实 calculator 调用 + DB 核验 + 自清） | 步骤4 |
| `edu-agent/tests/test_mcp_capability_audit.py` | 新建单测（G1/G2/G3 离线权威验证） | 步骤5 |
| `test-reports/WNEXTMCP1-completion-report.md` | 本报告 | 交付 |

**未改** `permission_gate.py`（跨模块接线已存在，本 kickoff 只新增审计行，不改动权限门本体）、
`tool_calling.py`/`graph_stream.py`/其他 MCP 模块（与 SURFACED1-FIX 文件互斥，严守纪律）。

## 验收 GWT（编排者一手复现）

### MCP1-G1 — capability_audit checked=10（7+跨模块3），virtual/broken 全空 ✅
- 离线：`audit_mcp_capability()` → `checked=10, virtual=[], broken=[], ok=True`
- 8010 实时：探针 `audit_ok=true, audit_checked=10`
- 新增 3 行：`permgate_is_write_class_called` / `permgate_gate_tool_call_called` / `permgate_resolve_role_called`
  （用「调用形态」符号 `is_write_class(` 等，确保是真调用而非仅 import）

### MCP1-G2 — 内置工具 calculator SUCCESS → mcp_tool_call_log 行 +1（server_id=0, operator_user_id）✅
- 离线（monkeypatch 捕获 `_write_call_log` 入参）：恰好 1 条， `server_id==0`、`tool_name=='calculator'`、`user_id==1`、`status==SUCCESS`、`latency_ms>=0`
- 8010 实时：探针 `builtin_logged=true`（calculator 调用后按 call_id 在 `mcp_tool_call_log` 查到 server_id=0 行）

### MCP1-G3 — 含 password 字段 → 落库值 ***REDACTED***（不含明文）✅
- 离线（monkeypatch 捕获 `execute_write` 参数）：`args_json` 含 `***REDACTED***`、不含 `secret123`、敏感 key 本身保留
- 8010 实时：探针 `redacted=true`（calculator 带 `password=secret123` → 落库 `args_json` 值脱敏、明文不可见）
- 脱敏在公共落库入口 `_write_call_log` 只一层（key 命中 `password|token|secret|api_key|authorization` 大小写不敏感 → 值替 `***REDACTED***`；单字段 JSON >4KB 截断 + `...truncated`），内置/远程双路径统一覆盖

### MCP1-G4 — ⑬ 健康门三段均绿 ✅
- 8010 实时 `check-demo` ⑬ 解析探针输出：`{"audit_ok":true,"audit_checked":10,"builtin_logged":true,"redacted":true,"env_blocked":false}`，`EXIT=0`
- 探针对每次验证写入的测试行按 `call_id` 自清（验证后 `mcp_tool_call_log` 中 `calculator/server_id=0` 行数 = 0，无污染）

### MCP1-G5 — MCP + chat 套件全绿（零回归）✅
- MCP 套件：`pytest tests/test_contract_mcptruth.py` → **9 passed**；`pytest tests/test_mcp_capability_audit.py` → **6 passed**
- chat 套件（T11 4 场景对应实现）：`pytest tests/test_chat_tool_calling.py` → **5 passed**（离线、进程内 mock executor，不触 DB/LLM）
  —— 验证 chat → 内置工具链路（`run_chat_tool_calls` → `executor.call_tool`）仍走通，`executor.py` 模块导入与内置执行路径未被本次改动破坏。
- **合计 20 passed，零回归**（MCP 15 + chat 5）。本段由续跑补齐：初版报告因环境抖动未重跑 chat 套件、标 ➖，现以离线单测实证闭环。

## 关键发现（kickoff 前提校正）

kickoff 步骤1 文字称 executor 有「5 处 import（含 can_use_tool）」接 permission_gate。实测当前
`executor.py`（W-NEXT-2 后）**真实接线的跨模块符号是 4 个**：`is_write_class` / `build_denied_envelope`
/ `gate_tool_call` / `resolve_role`；**`can_use_tool` 不经 executor 直调**，而是 `gate_tool_call` 内部调用
间接可达。因此 P0-① 审计行只验证「真被接线的执行链」（is_write_class→写类判定、gate_tool_call→统一门
消费入口、resolve_role→角色解析），`build_denied_envelope` 与 `gate_tool_call` 同址同调亦已接线（不单列）。
审计门反映真实接线，避免造出会失败的虚标行（virtual 非空 → G1 失败）。

## 自清记录

- 8010 临时实例已关闭（` TaskStop YDou27`）。
- `mcp_tool_call_log`：探针按 `call_id` 删除本次写入的 2 行测试数据，复验 `calculator/server_id=0` 行数 = 0。
- 单写者锁 `edu-agent/scripts/eval/wnextmcp1.lock`：开工建、完工删。
