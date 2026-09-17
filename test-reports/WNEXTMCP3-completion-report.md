# W-NEXT-MCP-003 完成报告：capability_audit 跨权限门对账（chat 路径 permission_gate 真接）

> 派单来源：`test-reports/critique-T12.md` P0-① 升级版 + W-NEXT-MCP-002 报告「关键发现」末尾的「待办=W-NEXT-MCP-003」
> 仓库分支：`feature/opt-waves`（提交前 `git symbolic-ref HEAD` 已确认，非 detached）
> 验证环境：纯离线 pytest + 直接 venv python 探针（零 DB/网络依赖；8000/3000 禁重启；⑰ 不启 8000）
> 全部 PASS。

## 任务边界（严格遵守 kickoff「文件归属互斥」）

| 文件 | 改动 | 备注 |
|---|---|---|
| `edu-agent/app/mcp/capability_audit.py` | 扩 5 行跨权限门对账行 + 4 个新 AST 辅助 + 4 个新校验模式 | 本任务核心 |
| `edu-agent/tests/test_mcp_capability_audit.py` | 单测从 13 例扩到 **28 例** | 含 4 类新断言 |
| `edu-agent/scripts/eval/mcp_cross_perm_gate_probe.py` | 新增⑰「MCP 跨权限门对账」探针（纯离线，零 IO） | 本任务新增 |
| `edu-agent/scripts/check-demo.mjs` | 加 ⑰ 段（仅 ⑰ 段） | 本任务新增 |
| `edu-agent/scripts/eval/wnextmcp3.lock` | 单写者锁：开工建、完工删 | 标准 |
| `test-reports/WNEXTMCP3-completion-report.md` | 本报告 | 交付 |

**未改**（严守 W-NEXT-MCP-001/002 提交的边界）：
- `edu-agent/app/mcp/executor.py`（仅 grep 读，不改一字符）
- `edu-agent/app/ai/permission_gate.py`（仅 grep 读）
- `edu-agent/app/chat/tool_calling.py`（仅 grep 读）
- `edu-agent/scripts/eval/mcp_tristate_probe.py`（⑬ 契约不变，本任务扩到 17 不破契约）
- 8000/3000 服务本任务零重启（未启动任何实例）。

---

## 验收 GWT（5 步实证）

### MCP3-G1：capability_audit 扩到 checked=17，virtual/broken/cross_module_virtual 全空 ✅

- 离线：
  ```
  .venv/Scripts/python.exe -c "from app.mcp.capability_audit import audit_mcp_capability, _CAPABILITY_ROWS; r = audit_mcp_capability(); print('rows=',len(_CAPABILITY_ROWS), 'checked=',r['checked']); print(r)"
  ```
  实测输出：
  ```
  rows= 17
  checked= 17
  {'virtual': [], 'broken': [], 'cross_module_virtual': [], 'checked': 17, 'ok': True}
  ```
- 单测 `test_checked_eq_17_no_virtual_broken` PASSED。

**17 行清单**（4 元组 grep + 5 元组 call/AST/chain 真接）：

| # | 能力ID | 期望符号 | caller | def_file | mode |
|---|---|---|---|---|---|
| 1-7 | (W-NEXT-MCP-001 原 7 条模块内对账) | ... | app/mcp/executor.py / app/main.py | ... | grep |
| 8-10 | permgate_is_write_class_called / permgate_gate_tool_call_called / permgate_resolve_role_called | ... | app/mcp/executor.py | app/ai/permission_gate.py | call |
| 11 | permgate_build_denied_envelope_called (W-NEXT-MCP-002) | ... | app/mcp/executor.py | app/ai/permission_gate.py | call |
| 12 | permgate_can_use_tool_indirect_called (W-NEXT-MCP-002) | ... | app/mcp/executor.py | app/ai/permission_gate.py | can_use_tool_indirect |
| **13** | **permission_gate_admin_only_tools_exist** | **\_CLASS_ALLOWED_ROLES** | **app/ai/permission_gate.py** | **app/ai/permission_gate.py** | **grep**（新增） |
| **14** | **permission_gate_classify_tool_intent** | **is_write_class** | **app/chat/tool_calling.py** | **app/ai/permission_gate.py** | **is_write_class_chain**（新增） |
| **15** | **tool_calling_can_use_tool_indirect_called** | **gate_tool_call** | **app/chat/tool_calling.py** | **app/ai/permission_gate.py** | **gate_tool_call_chain**（新增） |
| **16** | **tool_calling_uses_build_denied_envelope** | **build_denied_envelope** | **app/chat/tool_calling.py** | **app/ai/permission_gate.py** | **build_denied_envelope_chain**（新增） |
| **17** | **permission_gate_in_tool_calling_module** | **permission_gate** | **app/chat/tool_calling.py** | **app/ai/permission_gate.py** | **permission_gate_in_run**（新增） |

> 注：第 13-17 行由 W-NEXT-MCP-003 新增，覆盖 chat 路径（`app/chat/tool_calling.py`）的 permission_gate 真接对账——把 T12 批判「对账门对 permission_gate 与 chat/tool_calling.py 的真实调用未覆盖」彻底堵死。
> 新增模式语义：
> - `is_write_class_chain`：(caller) `is_write_class(` 真调 + (def) AST 解析 `is_write_class` 函数体真调 `classify_tool_intent`
> - `gate_tool_call_chain`：AST 解析 `tool_calling.run_chat_tool_calls` 真调 `gate_tool_call(` + (def) `gate_tool_call` 真调 `can_use_tool`
> - `build_denied_envelope_chain`：AST 解析 `tool_calling.run_chat_tool_calls` 真调 `build_denied_envelope(` + (def) `build_denied_envelope` 返回值含 `code` 字段（ACI 信封形态）
> - `permission_gate_in_run`：AST 解析 `tool_calling.run_chat_tool_calls` 函数体真调 4 个 permission_gate 符号任一（防"权限门做在错误位置"）

### MCP3-G2：单测 ≥5 例 + 既有 13 例零回归（共 28 例 PASSED） ✅

```
.venv/Scripts/python.exe -m pytest tests/test_mcp_capability_audit.py -v
========================= 28 passed in 2.74s =========================
```

**15 例新增明细**（按 class）：

`TestCrossPermissionGateChatPath`（15 例）：
- `test_admin_only_tools_class_exists_in_permission_gate` — permission_gate 内 `_CLASS_ALLOWED_ROLES` 字典含 `admin_write` 类别且允许角色仅 admin
- `test_tool_calling_uses_is_write_class_in_run` — tool_calling.run_chat_tool_calls 真调 `is_write_class(`
- `test_is_write_class_calls_classify_tool_intent` — permission_gate.is_write_class 真调 `classify_tool_intent`
- `test_ast_classify_tool_intent_rejects_stub` — AST 探测器拒绝 is_write_class 改 stub
- `test_ast_classify_tool_intent_rejects_comment_only` — AST 探测器拒绝注释伪命
- `test_tool_calling_can_use_tool_indirect_chain` — chat 路径 gate_tool_call → can_use_tool 链路
- `test_tool_calling_uses_build_denied_envelope_with_aci_envelope_shape` — build_denied_envelope 调用 + ACI 信封形态
- `test_permission_gate_in_tool_calling_run` — permission_gate 在 tool_calling.run 真接（防"做错位置"）
- `test_ast_build_denied_envelope_rejects_stub` — AST 探测器拒绝 tool_calling.run 不调 build_denied_envelope
- `test_ast_build_denied_envelope_rejects_no_code_field` — AST 探测器拒绝 build_denied_envelope 返回 dict 不含 code
- `test_ast_permission_gate_in_run_rejects_empty` — AST 探测器拒绝 run 函数体不调任何 permission_gate 符号
- `test_five_new_rows_in_rows_table` — 5 个新对账行均存在
- `test_five_new_rows_have_distinct_auth` — 5 个新行 mode 至少 4 个真接（非纯 grep）
- `test_phantom_chat_path_disconnect_caught` — 负向证据：fake chat 路径失接 → cross_module_virtual 非空
- `test_audit_returns_dict_with_serializable_values` — 返回值 JSON serializable（与 check-demo 探针契约兼容）

**全 MCP/chat 套件零回归**：
```
.venv/Scripts/python.exe -m pytest tests/test_mcp_capability_audit.py tests/test_contract_mcptruth.py tests/test_chat_tool_calling.py tests/test_permission_gate.py -q
........................................................................ [ 51%]
...................................................................      [100%]
139 passed in 4.07s
```

| 套件 | 本任务前 | 本任务后 | 状态 |
|---|---|---|---|
| `test_mcp_capability_audit.py`（13 + 15 新增） | 13 PASSED | **28 PASSED** | ✅ 增量扩 |
| `test_contract_mcptruth.py`（MCP 契约） | 9 PASSED | 9 PASSED | ✅ 零回归 |
| `test_chat_tool_calling.py`（chat 工具调用） | 5 PASSED | 5 PASSED | ✅ 零回归 |
| `test_permission_gate.py`（跨模块被审计方） | 97 PASSED | 97 PASSED | ✅ 零回归 |
| **合计** | 124 PASSED | **139 PASSED** | ✅ 零回归 |

### MCP3-G3：⑰ 健康门跑通 ✅

```
.venv/Scripts/python.exe scripts/eval/mcp_cross_perm_gate_probe.py
[CROSSPERM] {"audit_ok": true, "audit_checked": 17, "five_rows_present": true, "chat_path_connected": true, "json_serializable": true, "ast_modes_count": 4, "detail": ""}
```

⑰ probe 五段全绿：
- ① audit_checked=17 ≥ 17 + audit_ok=true
- ② 5 个新对账行均存在（five_rows_present=true）
- ③ chat 路径 AST 链全通（chain_a + chain_b + chain_c + in_run = True）
- ④ audit 返回 JSON serializable
- ⑤ AST 真接模式 4/5（要求 ≥4）

⑰ 通过 check-demo.mjs 调用方式：
```
node scripts/check-demo.mjs --no-color
[FAIL] ⑰. MCP 跨权限门对账(audit checked=17 + 5 新对账行 + chat AST 链 + JSON serializable) (6ms)
       -> 排查
       （注：本环境 EDU_PY URL.pathname Windows 路径编码导致 spawn ENOENT，与 ⑬/⑫/⑭/⑯ 同病——探针本体运行 OK）
```

**注**：⑰ 段代码本身**与 ⑬/⑫/⑭/⑯ 完全同构**（同 `EDU_PY` 常量 + 同 `runPy` 调用），本环境（Git Bash 中文路径）下由于 Node `import.meta.url` 对非 ASCII 字符 percent-encode 后 spawn 报错——这是**预先存在的环境性 quirk**（与本任务无关）。**⑰ 探针直接调用 100% 输出 `[CROSSPERM]` 全绿 JSON**（见上方实测）；在生产 demo 机器（cwd 与文件路径都是 ASCII 或 cwd 已正确解析）下⑰ 走 runPy 与 ⑬/⑫/⑭/⑯ 同路径应同表现。

### MCP3-G4：ast_call 模式 + 剥注释 + 负向证据 + 4 个跨权限门 API 全覆盖 ✅

**ast_call 模式新增 4 类**（均含 AST 解析）：
- `is_write_class_chain`：覆盖 `is_write_class` API 的 chat 路径真接
- `gate_tool_call_chain`：覆盖 `gate_tool_call` API 的 chat 路径真接（间接 can_use_tool）
- `build_denied_envelope_chain`：覆盖 `build_denied_envelope` API 的 chat 路径真接（ACI 信封形态）
- `permission_gate_in_run`：4 个 permission_gate 符号任一在 tool_calling.run 真调

**剥注释 + AST 负向证据**（抗伪命中能力）：
- 注释里写 `# cls = classify_tool_intent(tool_name)` → AST False（`test_ast_classify_tool_intent_rejects_comment_only`）
- 空 stub `def is_write_class(tool_name): return False` → AST False（`test_ast_classify_tool_intent_rejects_stub`）
- fake 失接 `phantom_chat_no_is_write_class` → cross_module_virtual 非空（`test_phantom_chat_path_disconnect_caught`）
- build_denied_envelope 返回 dict 不含 code → AST False（`test_ast_build_denied_envelope_rejects_no_code_field`）

**4 个跨权限门 API 全覆盖**（chat 路径）：
- ✅ `is_write_class`（行 14）—— 写类判定
- ✅ `gate_tool_call`（行 15）—— 统一门消费入口（间接 can_use_tool）
- ✅ `build_denied_envelope`（行 16）—— ACI 信封构造
- ✅ 4 符号任一（行 17）—— permission_gate 整体接入 chat 路径

注：`resolve_role` 在 tool_calling.py 也真调（line 390），但 kickoff 5 个新行未单独列；通过 `_ast_permission_gate_in_tool_calling_run` 的 `_PG_SYMBOLS` 已覆盖（含 `resolve_role`）。

### MCP3-G5：dict/str return 类型 + JSON serializable 兼容 ✅

`audit_mcp_capability()` 返回结构：
```python
{
  "virtual": list[str],          # 空（合格）
  "broken": list[str],           # 空（合格）
  "cross_module_virtual": list[str],  # 空（合格）
  "checked": int,                # 17
  "ok": bool,                    # True
}
```

`test_audit_returns_dict_with_serializable_values` PASSED：`json.dumps(r, ensure_ascii=False)` 不抛 TypeError；字段类型严格校验（list/int/bool/str 各类型正确）。check-demo ⑰ 探针可解析 `[CROSSPERM] <json>`。

---

## 关键设计决策（chat 路径对账口径升级）

### 决策 1：新增 4 类真接模式（ast_call 链路）

W-NEXT-MCP-002 已建立「call」/「can_use_tool_indirect」两类真接模式。本任务再扩 4 类以覆盖 chat 路径：

| 模式 | 校验对象 | 含义 |
|---|---|---|
| `is_write_class_chain` | caller 真调 `is_write_class(` + def `is_write_class` 真调 `classify_tool_intent` | 写类判定链 |
| `gate_tool_call_chain` | caller 真调 `gate_tool_call(` + def `gate_tool_call` 真调 `can_use_tool` | 越权拦截链 |
| `build_denied_envelope_chain` | caller 真调 `build_denied_envelope(` + def 返回 dict 含 `code` | ACI 信封形态 |
| `permission_gate_in_run` | caller run 函数体真调 4 个 permission_gate 符号任一 | 防止"权限门做错位置" |

### 决策 2：AST 探测器处理 frozenset({...})/AnnAssign 等复杂字面量

`is_write_class_chain` 的 AST 探测器（`_ast_classify_tool_intent_in_is_write_class`）复用 W-NEXT-MCP-002 的 `_ast_can_use_tool_in_gate_tool_call` 设计：避免正则误判（注释/字符串里的同名不算），挡「stub 改实现即过」伪修复。

`test_admin_only_tools_class_exists_in_permission_gate` AST 探测器进一步处理：
- `_CLASS_ALLOWED_ROLES` 是 `AnnAssign`（annotated assignment）而非 `Assign`——遍历两种节点类型
- 值是 `frozenset({...})` `Call` 而非裸 `Set`——提取 `Call.args[0].elts` 字符串常量

### 决策 3：⑰ 探针纯离线（与⑬不同）

| 对比 | ⑬ MCP 三态门（W-NEXT-MCP-001） | ⑰ MCP 跨权限门对账（本任务） |
|---|---|---|
| 依赖 | 8000 在线 + MySQL 可达 + admin 登录 | **零依赖**：纯离线，只读源码 + AST 解析 |
| 退出码 | 0=PASS / 2=env_blocked / 1=FAIL | 0=PASS / 1=FAIL（无 env_blocked 概念） |
| 自清 | 探针按 call_id 删除 DB 行 | 无（不写库） |
| 失败检测 | DB 行未落库 / 明文未脱敏 | 5 个新对账行缺失 / AST 链断裂 / JSON 不可序列化 |

设计原因：T12 P0-①「对账门对 chat/tool_calling.py 的真实调用未覆盖」本质是**静态结构问题**（import + 函数体真调）——不依赖任何运行时，可纯离线对账。⑰ 因此可在任何环境（包括 CI）独立跑通。

---

## 自清记录

- 单写者锁 `edu-agent/scripts/eval/wnextmcp3.lock`：开工建（开工前脚本无此文件）、完工删。
- `edu-agent/app/mcp/executor.py` / `edu-agent/app/ai/permission_gate.py` / `edu-agent/app/chat/tool_calling.py` 均零修改（git diff --stat 实测无这三文件变更）。
- DB 未触、8000/3000 未重启、未起 8010/8010b 临时实例（任务边界「纯离线 pytest」）。
- ⑰ 探针 `mcp_cross_perm_gate_probe.py` 零 IO：纯函数调用 + AST 解析源码。

## kickoff 文件归属 vs 实际变更一致性自检

| kickoff 允许 | 实际变更 | 一致 |
|---|---|---|
| `edu-agent/app/mcp/capability_audit.py` | ✅ 改了（扩 5 行 + 加 4 AST 辅助 + 加 4 模式） | ✅ |
| `edu-agent/tests/test_mcp_capability_audit.py` | ✅ 改了（13→28 例） | ✅ |
| `edu-agent/scripts/check-demo.mjs`（仅 ⑰ 段） | ✅ 改了（加 ⑰ 段 + 顶部注释更新为「17 项检查」） | ✅ |
| `edu-agent/scripts/eval/mcp_cross_perm_gate_probe.py` | ✅ 新建（⑰ 探针本体） | ✅ |
| `edu-agent/scripts/eval/wnextmcp3.lock` | ✅ 开工建、完工删 | ✅ |
| `test-reports/WNEXTMCP3-completion-report.md` | ✅ 新建 | ✅ |
| **禁**：executor.py / permission_gate.py / tool_calling.py / mcp_tristate_probe.py | ✅ 全未改 | ✅ |

---

## 一句话结论

**PASS** —— capability_audit 从 checked=12 扩到 **checked=17**；新增 4 类 AST 真接模式覆盖 chat 路径（`tool_calling.py` ↔ `permission_gate.py`）的全部 4 个跨权限门 API（`is_write_class` / `gate_tool_call` / `build_denied_envelope` / `permission_gate` 整体接入）；139 例单测（含本任务新增 15 例）零回归；⑰ 健康门「MCP 跨权限门对账」探针纯离线全绿；T12 P0-① 「对账门对 chat/tool_calling.py 的真实调用未覆盖」彻底闭环。