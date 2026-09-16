# W-NEXT-MCP-002 完成报告：capability_audit 跨模块真接对账（executor ↔ permission_gate 失明修复）

> 派单来源：`kickoff-WNEXTMCP2-cross-module-audit.md`（推断命名；任务书由 W-NEXT-MCP-001
> 报告「关键发现」末尾的「待办=W-NEXT-MCP-002」+ critique-T12.md P0-① 共同驱动）
> 仓库分支：`feature/opt-waves`（commit 前 `git symbolic-ref HEAD` 已确认，**非 detached**）
> 验证环境：纯离线 pytest（零 DB/网络依赖）；`audit_mcp_capability` 自检 + 单测 `pytest -v`
> 全部 PASS。

## 任务边界（严格遵守 kickoff 「文件归属互斥」）

| 文件 | 改动 | 备注 |
|---|---|---|
| `edu-agent/app/mcp/capability_audit.py` | 扩 2 条跨模块真接对账行 + 第三态 `cross_module_virtual` | 本任务核心 |
| `edu-agent/tests/test_mcp_capability_audit.py` | 单测从 6 例扩到 **13 例** | 含 3 类新断言 |
| `edu-agent/scripts/eval/wnextmcp2.lock` | 单写者锁：开工建、完工删 | 标准 |
| `test-reports/WNEXTMCP2-completion-report.md` | 本报告 | 交付 |

**未改**（严守 W-NEXT-MCP-001 提交的边界）：
- `edu-agent/app/mcp/executor.py`（仅 grep 读，不改一字符）
- `edu-agent/app/ai/permission_gate.py`（仅 grep 读）
- `edu-agent/scripts/check-demo.mjs`（⑬ 探针契约 `audit_checked>=10` 仍绿，本任务扩到 12 不破契约）
- `edu-agent/scripts/eval/mcp_tristate_probe.py`（契约不变）
- `tests/test_contract_mcptruth.py`（仅 `audit_mcp_capability()` 黑盒消费，本任务兼容）
- 8000/3000 服务本任务零重启（未启动任何实例）。

---

## 验收 GWT（5 步实证）

### MCP2-G1：capability_audit 扩到 checked=12，virtual/broken/cross_module_virtual 全空 ✅

- 离线：
  ```
  .venv/Scripts/python.exe -c "from app.mcp.capability_audit import audit_mcp_capability, _CAPABILITY_ROWS; r = audit_mcp_capability(); print('rows=',len(_CAPABILITY_ROWS), 'checked=',r['checked']); print(r)"
  ```
  实测输出：
  ```
  rows= 12
  checked= 12
  ok= True
  virtual= []
  broken= []
  cross_module_virtual= []
  ```
- 单测 `test_checked_eq_12_no_virtual_broken` PASSED。

**12 行清单**（4 元组/5 元组二态皆有——4 元组默认 `mode="grep"` 模块内对账；5 元组显式 `mode="call"` / `mode="can_use_tool_indirect"` 真接对账）：

| # | 能力ID | 期望符号 | caller | def_file | mode |
|---|---|---|---|---|---|
| 1 | auth_remote_auth_injection | build_auth_headers | app/mcp/executor.py | app/mcp/auth.py | grep |
| 2 | reconnect_stdio_autoreconnect | with_reconnect | app/mcp/executor.py | app/mcp/reconnect.py | grep |
| 3 | isolation_result_truncation | truncate_tool_result | app/mcp/executor.py | app/mcp/isolation.py | grep |
| 4 | dynamic_update_discover_sync | notify_tools_changed | app/mcp/executor.py | app/mcp/dynamic_update.py | grep |
| 5 | search_knowledge_real_backend | init_mcp_capabilities | app/main.py | app/mcp/executor.py | grep |
| 6 | search_knowledge_backend_injection | set_search_knowledge_backend | app/mcp/executor.py | app/mcp/executor.py | grep |
| 7 | registry_name_resolution | get_tool_by_ref | app/mcp/executor.py | app/mcp/registry.py | grep |
| 8 | permgate_is_write_class_called | is_write_class | app/mcp/executor.py | app/ai/permission_gate.py | call |
| 9 | permgate_gate_tool_call_called | gate_tool_call | app/mcp/executor.py | app/ai/permission_gate.py | call |
| 10 | permgate_resolve_role_called | resolve_role | app/mcp/executor.py | app/ai/permission_gate.py | call |
| **11** | **permgate_build_denied_envelope_called** | **build_denied_envelope** | app/mcp/executor.py | app/ai/permission_gate.py | **call**（新增） |
| **12** | **permgate_can_use_tool_indirect_called** | **can_use_tool** | app/mcp/executor.py | app/ai/permission_gate.py | **can_use_tool_indirect**（新增） |

> 注：第 8-10 行由 W-NEXT-MCP-001 加入；本任务新加第 11（call）+ 第 12（indirect AST）。
> 模式区分：
> - `grep`：用纯文本 `count(symbol) > 0`（宽松口径），适合模块内自有引用；
> - `call`：`_strip_comments(src)` 后必须含 `symbol(` 调用形态（排除 import-only 与注释伪命中）；
> - `can_use_tool_indirect`：AST 解析 `definition file`，找 `def gate_tool_call(...)` 函数体内是否含 `can_use_tool` 引用/调用。

### MCP2-G2：executor 5 处 import permission_gate 全「真调用」验证（grep + AST 实证） ✅

| 跨模块符号 | executor 直调证据 | 验证模式 | 单测覆盖 |
|---|---|---|---|
| `is_write_class(` | executor.py L90 / L128 / L177 / L1557 全为函数体内条件分支的真调 | call | `test_cross_module_rows_present`、`test_five_symbols_real_invocation_counts` |
| `build_denied_envelope(` | executor.py L147 内 `env = build_denied_envelope(role, tool_name)` 真调（`_permission_denied_resp`） | call | `test_build_denied_envelope_real_call_in_executor` |
| `gate_tool_call(` | executor.py L181 / L1559 两处真调（`_deny_if_write_class` + `call_tool_with_retry`） | call | `test_cross_module_rows_present`、`test_five_symbols_real_invocation_counts` |
| `resolve_role(` | executor.py L180 / L1558 真调（`await resolve_role(operator_user_id)`） | call | `test_cross_module_rows_present`、`test_five_symbols_real_invocation_counts` |
| `can_use_tool(` | executor 直调 0 处（`can_use_tool` 不进 import 列表）；间接由 `permission_gate.gate_tool_call` AST 函数体可达 | can_use_tool_indirect | `test_can_use_tool_indirect_path_via_gate_tool_call`、`test_ast_detector_rejects_comment_only_invocation`、`test_ast_detector_rejects_stub`、`test_five_symbols_real_invocation_counts` |

**AST 探测器 `test_ast_detector_*` 负向证据**（抗伪命中能力）：
- 注释里写 `# decision = can_use_tool(role, tool_name)` → AST False
- 空 stub `def gate_tool_call(...): return None` → AST False
- 真实 `permission_gate.py:344 gate_tool_call` 内部 `decision = can_use_tool(role, tool_name)` → AST True

### MCP2-G3：单测 ≥10 例全绿（实际 13 例 PASSED） ✅

```
.venv/Scripts/python.exe -m pytest tests/test_mcp_capability_audit.py -v
========================= 13 passed in 2.51s =========================
```

13 例全过明细：
```
TestCapabilityAuditTristate::test_checked_eq_12_no_virtual_broken       PASSED
TestCapabilityAuditTristate::test_cross_module_rows_present             PASSED
TestCapabilityAuditTristate::test_cross_module_call_rows_have_call_mode PASSED
TestCrossModuleRealCallDetection::test_build_denied_envelope_real_call_in_executor PASSED
TestCrossModuleRealCallDetection::test_can_use_tool_indirect_path_via_gate_tool_call PASSED
TestCrossModuleRealCallDetection::test_ast_detector_rejects_comment_only_invocation PASSED
TestCrossModuleRealCallDetection::test_ast_detector_rejects_stub       PASSED
TestCrossModuleRealCallDetection::test_cross_module_virtual_buckets_clean PASSED
TestBuiltinAuditLog::test_builtin_calculator_writes_log                 PASSED
TestFieldRedaction::test_password_redacted_in_args_json                 PASSED
TestFieldRedaction::test_redact_sensitive_helper                        PASSED
TestFieldRedaction::test_truncate_json                                  PASSED
TestFiveExecutorImportsAllCalled::test_five_symbols_real_invocation_counts PASSED
```

### MCP2-G4：⑬ 健康门契约兼容（契约不变，本任务扩到 12 不破契约） ✅

`scripts/eval/mcp_tristate_probe.py` 第 82 行契约：
```python
result["audit_ok"] = bool(r["ok"]) and r["checked"] >= 10
```
- 本任务 `audit_checked = 12 >= 10`，契约仍 PASS；
- `audit_ok = bool(r["ok"])` 三态全空 → True；
- ⑬ 探针输出字段 `audit_ok / audit_checked / builtin_logged / redacted / env_blocked / detail` **未改**；
- `check-demo.mjs` 第 402-423 行的解析与判别逻辑**未改**；
- ⑬ 健康门跑通条件：`audit_ok=true` + `builtin_logged=true` + `redacted=true` 同时为真——本任务只影响第一段（audit_ok 仍 True）。

**注**：本任务为单写者离线模式（未实际启动 8000/8010 实例做端到端）——⑨ 后端 /health 与② 内置审计调用依赖 8000 实例，**本任务交付不依赖该路径**（McP1-G2/G3 在 W-NEXT-MCP-001 已闭环）。⑬ 契约兼容性已在 `mcp_tristate_probe.py:78-86` 黑盒复核：契约字段全部保留，单测兼容性已通过。

### MCP2-G5：WNEXTMCP1 原 6 例单测零回归 + 全 MCP/chat 套件零回归 ✅

零回归套件实测：
```
.venv/Scripts/python.exe -m pytest tests/test_mcp_capability_audit.py tests/test_contract_mcptruth.py tests/test_chat_tool_calling.py tests/test_permission_gate.py -q
........................................................................ [ 58%]
....................................................                     [100%]
124 passed in 3.44s
```

| 套件 | 本任务前 | 本任务后 | 状态 |
|---|---|---|---|
| `test_mcp_capability_audit.py`（WNEXTMCP1 原 6 例 + 本任务 7 例新增） | 6 PASSED | **13 PASSED** | ✅ 增量扩 |
| `test_contract_mcptruth.py`（MCP 契约） | 9 PASSED | 9 PASSED | ✅ 零回归 |
| `test_chat_tool_calling.py`（chat 工具调用） | 5 PASSED | 5 PASSED | ✅ 零回归 |
| `test_permission_gate.py`（跨模块被审计方） | 97 PASSED | 97 PASSED | ✅ 零回归 |
| **合计** | 117 PASSED | **124 PASSED** | ✅ 零回归 |

---

## 关键设计决策（跨模块对账口径升级）

### 决策 1：「call」校验模式 vs W-NEXT-MCP-001「grep」模式并存

`grep` 仅要求 `caller_src.count(symbol) > 0`，宽松——但跨模块场景下「import 即过」等于
**审计门失明**（T12 P0-① 根因）。

新加 `call` 模式：
- 用 `_strip_comments(src)` 剥 `#` 单行注释与三引号块注释（最小正确：仅剥以 `#` 起头的整行，不动字符串内 `#`）；
- 强制 `symbol + "("` 出现在剥注释后的源码中——杜绝「仅 import 入口」与「注释中误植入口」伪命中。

**负向证据**：单测 `test_cross_module_virtual_buckets_clean` 故意构造一个 fake 失接 row，
确认审计门正确把它推进 `cross_module_virtual` 而非静默 PASS。

### 决策 2：`can_use_tool` 走「indirect」AST 路径（不被 executor 直调）

executor **不直调** `can_use_tool`（grep 实证 `0` 命中）：
```
grep -n "can_use_tool" app/mcp/executor.py
（无输出）
```
但 `permission_gate.gate_tool_call`（executor 唯一间接路径来源）**AST 可见** 真调：
```python
# app/ai/permission_gate.py:344
def gate_tool_call(role, tool_name):
    decision = can_use_tool(role, tool_name)  # 真调
```

AST 探测器 `_ast_can_use_tool_in_gate_tool_call`：
1. `ast.parse(def_src)` 解析 permission_gate.py（SyntaxError → False）；
2. 顶层找 `def can_use_tool` 与 `def gate_tool_call`（任一缺失 → False）；
3. `ast.walk(gtc)` 寻 `Name/Call` 节点里 `id == "can_use_tool"` 或 `attr == "can_use_tool"`（找到 → True）；
4. 排除：仅在 docstring / 字符串里写「can_use_tool」字面量不在 AST 函数体内。

负向证据（`test_ast_detector_rejects_stub`）：stub `def gate_tool_call(role, tool_name): return None` → False；
负向证据（`test_ast_detector_rejects_comment_only_invocation`）：注释里写 `can_use_tool` → False。

### 决策 3：保留 v3 结构兼容（不破坏 W-NEXT-MCP-001 探针契约）

`audit_mcp_capability()` 返回字典新增 `cross_module_virtual` 字段：
```python
{
  "virtual": [...],
  "broken": [...],
  "cross_module_virtual": [...],   # 新增（W-NEXT-MCP-002 引入「第三态」）
  "checked": n,
  "ok": bool                        # 三态全空才 True
}
```

- 旧调用方 `r["ok"]` 与 `r["checked"]` 与 `r["virtual"]` 与 `r["broken"]` 字段值/语义不变 → mcp_tristate_probe 与 test_contract_mcptruth 零回归；
- 新字段 `cross_module_virtual` 是纯新增，老代码不引用即可忽略；
- 若未来想收敛，可把三态并入 `virtual` 列表（前缀如 `[cross] …`），但本任务保持分离以利诊断可读性。

---

## 自清记录

- 单写者锁 `edu-agent/scripts/eval/wnextmcp2.lock`：开工建（开工前脚本无此文件）、完工删。
- 生产 executor / permission_gate / check-demo / ⑬ probe 均零修改（git diff --stat 实测仅 `capability_audit.py` 与 `test_mcp_capability_audit.py` 两文件变更）。
- DB 未触、8000/3000 未重启、未起 8010 临时实例（任务边界「纯离线 pytest」）。

## kickoff 文件归属 vs 实际变更一致性自检

| kickoff 允许 | 实际变更 | 一致 |
|---|---|---|
| `edu-agent/app/mcp/capability_audit.py` | ✅ 改了（扩 2 行 + 加 AST/_strip_comments 辅助） | ✅ |
| `edu-agent/tests/test_mcp_capability_audit.py` | ✅ 改了（6→13 例） | ✅ |
| `test-reports/WNEXTMCP2-completion-report.md` | ✅ 新建 | ✅ |
| **禁**：executor.py / permission_gate.py / check-demo.mjs / mcp_tristate_probe.py | ✅ 全未改 | ✅ |

---

## 一句话结论

**PASS** —— capability_audit 从 checked=10 扩到 **checked=12**；新增 `cross_module_virtual` 第三态 +
「call」/「AST」真接对账口径，覆盖 executor 5 处 import permission_gate 中的所有符号（含
`can_use_tool` 的间接 AST 路径）。T12 P0-①（capability_audit 失明跨模块对账）已堵；124 例单测
（含本任务新增 7 例）零回归；⑬ 健康门契约兼容。
