# -*- coding: utf-8 -*-
"""MCP 能力对账门（MCP-TRUTH 步骤4，对齐 R15-b audit_registry 思想，防「能力虚标」复发）。

对账「声称的 MCP 能力清单」vs「生产接线实况」：
  - **虚标（virtual）**：声称有能力，但生产调用方文件对宣称的入口符号零引用 → 必须为空；
  - **断裂（broken）**：生产调用方引用了宣称的入口符号，但定义它的模块文件不存在 → 必须为空。
  - **跨模块未实调（cross_module_virtual）**：跨模块 import 但调用方函数体未真调用（仅 import 即失接）→ 必须为空。

与「R15-b 只对账名字存在性」不同，本门对账的是**声称能力 = 生产真实接线**，杜绝
「grep 仅定义文件自身引用/空壳注入点零调用」这类能力虚标（audit-rag #3/#5/#6）。

用法（独立命令，零 DB/网络依赖，只读源码）：
    cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_contract_mcptruth.py -q
    # 或直接跑：
    .venv/Scripts/python.exe -c "from app.mcp.capability_audit import audit_mcp_capability;
                                 print(audit_mcp_capability())"
"""
from __future__ import annotations

from pathlib import Path

# edu-agent/ 项目根（app/mcp/capability_audit.py → 上溯三级）
_BASE = Path(__file__).resolve().parent.parent.parent


# ============================================================
# 声称能力清单 → 生产接线实况（数据驱动）
# ------------------------------------------------------------
# 每行：(能力ID, caller_script 期望引用的入口符号, 生产调用方脚本(相对 edu-agent/), 定义该符号的文件, [可选]校验模式)
#   virtual            = caller_script 未引用入口符号（声称有能力但零接线）
#   broken             = caller_script 引用了入口符号但定义文件不存在（引用断裂）
#   cross_module_virtual = 跨模块 import 入口存在但函数体未真调用（仅 import 即失接，W-NEXT-MCP-002 新增）
# 校验模式（默认 "grep"）：
#   - "grep"（默认）：caller_script 文本中含入口符号（保证「import + 形参」即过；适合模块内同包）
#   - "call"：caller_script 文本中含「入口符号(」调用形态（保证真调用；适合跨模块 import 真接对账）
#   - "ast_call"：caller_script 文本中含「入口符号(」调用形态 **且** 定义文件内 AST 解析可见
#                   入口符号在「被 import 的同路径函数内」也被引用——挡「import 但零调用」类的
#                   失接（W-NEXT-MCP-002 新口径）
# ============================================================
_CAPABILITY_ROWS: list[tuple] = [
    # ---- MCP-TRUTH 原始 7 条（模块内对账） ----
    # #5 auth：executor 远程（sse/http）传输经 _remote_auth_headers → build_auth_headers 注入认证头
    ("auth_remote_auth_injection", "build_auth_headers", "app/mcp/executor.py", "app/mcp/auth.py"),
    # #5 reconnect：executor stdio 健康检查经 with_reconnect 自动指数退避重连
    ("reconnect_stdio_autoreconnect", "with_reconnect", "app/mcp/executor.py", "app/mcp/reconnect.py"),
    # #5 isolation：executor 工具结果超限经 truncate_tool_result 截断
    ("isolation_result_truncation", "truncate_tool_result", "app/mcp/executor.py", "app/mcp/isolation.py"),
    # #5 dynamic_update：executor discover 经 notify_tools_changed 同步动态工具注册表
    ("dynamic_update_discover_sync", "notify_tools_changed", "app/mcp/executor.py", "app/mcp/dynamic_update.py"),
    # #6 search_knowledge 空壳：应用启动（main.lifespan）调用 init_mcp_capabilities 注入真实后端
    ("search_knowledge_real_backend", "init_mcp_capabilities", "app/main.py", "app/mcp/executor.py"),
    # #6 注入点本身要有生产调用方：executor.init_mcp_capabilities 内 set_search_knowledge_backend(...)
    ("search_knowledge_backend_injection", "set_search_knowledge_backend", "app/mcp/executor.py", "app/mcp/executor.py"),
    # #3 按名解析：executor 默认执行器经 get_tool_by_ref(None,None,tool_name) 按名直达 DB 工具
    ("registry_name_resolution", "get_tool_by_ref", "app/mcp/executor.py", "app/mcp/registry.py"),
    # ---- W-NEXT-MCP-001 步骤1（P0-①）：跨模块对账 —— executor ↔ permission_gate 真接线（grep 调用形态） ----
    # T12 批判 P0-①：MCP-TRUTH 的 7 条声明全在 app/mcp/* 内，0 条覆盖 permission_gate 跨模块对账，
    # 造成「executor 虽已接权限门，但审计门对其失明」。以下 3 行比对「权限门跨模块能力 = executor
    # 真实调用」，杜绝该盲区。用「调用形态」符号（带 "("）确保是真调用而非仅 import。
    # 实测事实（2026-09-16）：executor 经 W-NEXT-2 真实接线的跨模块符号是
    #   is_write_class（写类判定，多处）/ gate_tool_call（统一门消费入口）/ resolve_role（角色解析）；
    #   build_denied_envelope 与 gate_tool_call 同址同调（:144/:173）亦已接线，不单列。
    #   can_use_tool 不经 executor 直调，而是 gate_tool_call 内部调用间接可达 → 不单列 import 行。
    ("permgate_is_write_class_called", "is_write_class", "app/mcp/executor.py", "app/ai/permission_gate.py", "call"),
    ("permgate_gate_tool_call_called", "gate_tool_call", "app/mcp/executor.py", "app/ai/permission_gate.py", "call"),
    ("permgate_resolve_role_called", "resolve_role", "app/mcp/executor.py", "app/ai/permission_gate.py", "call"),
    # ---- W-NEXT-MCP-002 步骤（P0-① 补救）：补 2 行跨模块真接对账，达标 checked=12 ----
    # 用调用形态("("后缀)挡住「仅 import 入口却不在函数体里真调」类的失接：
    # ④ builder_denied_envelope：executor.py:145 import + :147 真调（_permission_denied_resp ACI 信封）
    ("permgate_build_denied_envelope_called", "build_denied_envelope",
     "app/mcp/executor.py", "app/ai/permission_gate.py", "call"),
    # ⑤ can_use_tool（间接调用）：executor 不直调，但 gate_tool_call 内部真调 →
    #    AST 解析 permission_gate.gate_tool_call 函数体，确认 can_use_tool 在内被引用
    #    （挡「executor 把 can_use_tool 重命名但 gate_tool_call 改了实现」的失接）
    ("permgate_can_use_tool_indirect_called", "can_use_tool",
     "app/mcp/executor.py", "app/ai/permission_gate.py", "can_use_tool_indirect"),
    # ---- W-NEXT-MCP-003（P0-① 二次补救）：扩 5 行跨权限门对账，达标 checked=17 ----
    # ⑥ admin-only 工具清单结构存在：permission_gate.py 内含 _CLASS_ALLOWED_ROLES["admin_write"] 类别
    #    的允许角色定义（即"admin-only"白名单结构）—— 挡"声称有 admin-only 工具但清单不存在"虚标。
    ("permission_gate_admin_only_tools_exist", "_CLASS_ALLOWED_ROLES",
     "app/ai/permission_gate.py", "app/ai/permission_gate.py", "grep"),
    # ⑦ chat 路径真用 classify_tool_intent 判定 student/manager 越权：tool_calling.py 的
    #    run_chat_tool_calls 函数体内含 is_write_class( 直调（call 形态），且 AST 解析
    #    permission_gate.is_write_class 函数体必须真调 classify_tool_intent —— 挡
    #    「is_write_class 改实现不走契约意图」的失接。
    ("permission_gate_classify_tool_intent", "is_write_class",
     "app/chat/tool_calling.py", "app/ai/permission_gate.py", "is_write_class_chain"),
    # ⑧ tool_calling 真用 can_use_tool 拒绝越权：tool_calling.py 的 run_chat_tool_calls
    #    函数体内含 gate_tool_call( 直调（call 形态），且 AST 解析 permission_gate.gate_tool_call
    #    函数体必须真调 can_use_tool —— 挡「流式路径绕过 can_use_tool」的失接（HITL-FIX 子 agent 提）。
    ("tool_calling_can_use_tool_indirect_called", "gate_tool_call",
     "app/chat/tool_calling.py", "app/ai/permission_gate.py", "gate_tool_call_chain"),
    # ⑨ executor 调 build_denied_envelope 输出 ACI 信封（hitl fix 子 agent P0 关联）：
    #    与 W-NEXT-MCP-002 permgate_build_denied_envelope_called 等价的「chat 路径」覆盖 ——
    #    tool_calling.py run_chat_tool_calls 函数体内含 build_denied_envelope( 真调；
    #    同时 AST 解析 permission_gate.build_denied_envelope 函数体返回 dict（三字段信封）。
    ("tool_calling_uses_build_denied_envelope", "build_denied_envelope",
     "app/chat/tool_calling.py", "app/ai/permission_gate.py", "build_denied_envelope_chain"),
    # ⑩ permission_gate 在 chat 工具调用路径上被真接：tool_calling.py run_chat_tool_calls
    #    函数体内至少有一处 permission_gate 符号（is_write_class / gate_tool_call /
    #    build_denied_envelope / resolve_role）的真调 —— 挡"权限门做在错误位置"
    #    （如有人把权限门判定写在了 generator.py 而绕过 tool_calling 主路径）。
    ("permission_gate_in_tool_calling_module", "permission_gate",
     "app/chat/tool_calling.py", "app/ai/permission_gate.py", "permission_gate_in_run"),
]


def _read(rel_path: str) -> str:
    """读取相对 edu-agent/ 的源码文本；不存在返回空串（供断裂判别）。"""
    p = (_BASE / rel_path).resolve()
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def _strip_comments(src: str) -> str:
    """剥除源码注释（# 单行 + 三引号）以防注释中的标识符误判为调用。

    仅用于跨模块「call」/「ast_call」模式：模块内对账照旧可被注释触发，
    但跨模块 import 真接对账必须避免「import 即可」的伪命中。
    """
    import re
    # 删 # 单行注释（保留字符串里的 # 不在这里处理，按行剥最安全）
    out_lines = []
    for line in src.splitlines():
        # 剥掉「第一个不在字符串内的 #」。工程代码注释多用 #，实现最小正确：
        # 仅当整行首字符或紧跟空白后为 # 时整行视为注释（禁字符串内 # 误杀——本门
        # 跨模块 audit 入口函数名不会有「整行以 # 开头」的字符串场景）
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out_lines.append(line)
    no_hash = "\n".join(out_lines)
    # 删 """...""" 块注释（docstring）
    no_hash = re.sub(r'"""[\s\S]*?"""', "", no_hash)
    no_hash = re.sub(r"'''[\s\S]*?'''", "", no_hash)
    return no_hash


def _ast_can_use_tool_in_gate_tool_call(def_src: str) -> bool:
    """AST 解析 permission_gate.py：校验 can_use_tool 是否在 gate_tool_call 函数体内被真调用。

    用 `ast` 模块避免正则误判（注释/字符串里的同名不算）；失败（语法错/找不到函数）→ False。
    """
    import ast
    try:
        tree = ast.parse(def_src)
    except SyntaxError:
        return False
    # 1) 在 module 顶层找 `def can_use_tool(...)` 与 `def gate_tool_call(...)`
    func_names = {
        n.name: n
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
    }
    if "can_use_tool" not in func_names or "gate_tool_call" not in func_names:
        return False
    # 2) gate_tool_call 函数体里是否引用 can_use_tool（任意形式：直接调用 / 赋值 / 参数透传）
    gtc = func_names["gate_tool_call"]
    for sub in ast.walk(gtc):
        if isinstance(sub, ast.Name) and sub.id == "can_use_tool":
            return True
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name) and func.id == "can_use_tool":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "can_use_tool":
                return True
    return False


def _ast_classify_tool_intent_in_is_write_class(def_src: str) -> bool:
    """AST 解析 permission_gate.py：校验 classify_tool_intent 是否在 is_write_class 函数体内被真调用。
    is_write_class 不直调 classify_tool（那是 can_use_tool 用）——它走 classify_tool_intent（契约意图），
    保证契约挂起工具也能正确判定为写类。挡「is_write_class 改实现不再走契约意图」的失接。
    """
    import ast
    try:
        tree = ast.parse(def_src)
    except SyntaxError:
        return False
    func_names = {
        n.name: n
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
    }
    if "is_write_class" not in func_names or "classify_tool_intent" not in func_names:
        return False
    iwc = func_names["is_write_class"]
    for sub in ast.walk(iwc):
        if isinstance(sub, ast.Name) and sub.id == "classify_tool_intent":
            return True
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name) and func.id == "classify_tool_intent":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "classify_tool_intent":
                return True
    return False


def _ast_can_use_tool_in_tool_calling_run(caller_src: str, def_src: str) -> bool:
    """AST 解析 tool_calling.py：校验 run_chat_tool_calls 函数体真调 gate_tool_call，
    且 permission_gate.gate_tool_call 真调 can_use_tool（chat 路径间接链路）。"""
    import ast
    # 1) tool_calling.py 有 run_chat_tool_calls 函数 + 函数体内真调 gate_tool_call
    try:
        ctree = ast.parse(caller_src)
    except SyntaxError:
        return False
    run_fn = None
    for n in ctree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "run_chat_tool_calls":
            run_fn = n
            break
    if run_fn is None:
        return False
    run_calls_gate_tool_call = False
    for sub in ast.walk(run_fn):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name) and func.id == "gate_tool_call":
                run_calls_gate_tool_call = True
                break
            if isinstance(func, ast.Attribute) and func.attr == "gate_tool_call":
                run_calls_gate_tool_call = True
                break
    if not run_calls_gate_tool_call:
        return False
    # 2) permission_gate.gate_tool_call 真调 can_use_tool（复用 W-NEXT-MCP-002 探测器）
    return _ast_can_use_tool_in_gate_tool_call(def_src)


def _ast_build_denied_envelope_in_tool_calling_run(caller_src: str, def_src: str) -> bool:
    """校验 chat 路径真调 build_denied_envelope 输出 ACI 信封（HITL-FIX 子 agent P0）。

    两段证据：
      ① tool_calling.py run_chat_tool_calls 函数体内真调 build_denied_envelope( —— 产出信封；
      ② permission_gate.build_denied_envelope 函数体返回 dict（ACI 信封三字段：code/message/tool_name 或 action_hint）—— 形态正确。
    """
    import ast
    # ①
    try:
        ctree = ast.parse(caller_src)
    except SyntaxError:
        return False
    run_fn = None
    for n in ctree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "run_chat_tool_calls":
            run_fn = n
            break
    if run_fn is None:
        return False
    found_call = False
    for sub in ast.walk(run_fn):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name) and func.id == "build_denied_envelope":
                found_call = True
                break
            if isinstance(func, ast.Attribute) and func.attr == "build_denied_envelope":
                found_call = True
                break
    if not found_call:
        return False
    # ② permission_gate.build_denied_envelope 函数体含 dict 字面量返回（含 code 等 ACI 字段）
    try:
        dtree = ast.parse(def_src)
    except SyntaxError:
        return False
    bde_fn = None
    for n in dtree.body:
        if isinstance(n, ast.FunctionDef) and n.name == "build_denied_envelope":
            bde_fn = n
            break
    if bde_fn is None:
        return False
    # 函数体内找 dict literal Return 或赋值 —— 含至少一个 'code' 字符串 key 即视为 ACI 信封形态
    for sub in ast.walk(bde_fn):
        if isinstance(sub, ast.Dict):
            for k in sub.keys:
                if isinstance(k, ast.Constant) and getattr(k, "value", None) == "code":
                    return True
        if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Dict):
            for k in sub.value.keys:
                if isinstance(k, ast.Constant) and getattr(k, "value", None) == "code":
                    return True
    return False


def _ast_permission_gate_in_tool_calling_run(caller_src: str) -> bool:
    """校验 permission_gate 在 tool_calling.py 工具调用路径上被真接（防"权限门做在错误位置"）。

    要求 tool_calling.py run_chat_tool_calls 函数体里至少真调 1 个 permission_gate 符号
    （is_write_class / gate_tool_call / build_denied_envelope / resolve_role 中的任一）。
    """
    import ast
    _PG_SYMBOLS = ("is_write_class", "gate_tool_call", "build_denied_envelope", "resolve_role")
    try:
        ctree = ast.parse(caller_src)
    except SyntaxError:
        return False
    run_fn = None
    for n in ctree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "run_chat_tool_calls":
            run_fn = n
            break
    if run_fn is None:
        return False
    for sub in ast.walk(run_fn):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name) and func.id in _PG_SYMBOLS:
                return True
            if isinstance(func, ast.Attribute) and func.attr in _PG_SYMBOLS:
                return True
    return False


def audit_mcp_capability(*, rows=None) -> dict:
    """对账声称能力 vs 生产接线实况。

    返回 {"virtual": [...], "broken": [...], "cross_module_virtual": [...],
           "checked": n, "ok": bool}：
      - virtual       非空 = 能力虚标（声称了但生产零接线）→ 必须为空才算通过；
      - broken        非空 = 引用断裂（生产调用了不存在的模块/符号）→ 必须为空才算通过；
      - cross_module_virtual 非空 = 跨模块 import 但函数体未真调用 → 必须为空才算通过。

    「checked」= 数据驱动行数；ok=三态全空。
    """
    rows = rows if rows is not None else _CAPABILITY_ROWS
    virtual: list[str] = []
    broken: list[str] = []
    cross_module_virtual: list[str] = []
    for row in rows:
        # 兼容 4 元组（旧）和 5 元组（带模式）
        if len(row) == 4:
            cap_id, symbol, caller, def_file = row
            mode = "grep"
        else:
            cap_id, symbol, caller, def_file, mode = row
        caller_src = _read(caller)
        def_src = _read(def_file)
        if not def_src:
            broken.append(f"{cap_id}: 定义文件 {def_file} 不存在（无法验证入口）")
            continue
        if mode == "grep":
            # 模块内对账：出现入口符号即过（导入 + 用法足够；不强制 call 形态）
            caller_refs = caller_src.count(symbol) > 0
            if not caller_refs:
                virtual.append(f"{cap_id}: 声称有能力但生产调用方 {caller} 零引用 {symbol}（虚标）")
        elif mode == "call":
            # 跨模块真接对账：剥注释后必须含「symbol(」调用形态，杜绝「import 即过」伪命中
            cleaned = _strip_comments(caller_src)
            caller_refs = (symbol + "(") in cleaned
            if not caller_refs:
                cross_module_virtual.append(
                    f"{cap_id}: 跨模块 import 但 {caller} 函数体未真调用 {symbol}(（仅 import 失接）"
                )
        elif mode == "can_use_tool_indirect":
            # 跨模块间接调用对账：executor 直调看 can_use_tool 的间接路径——
            #   路径 = executor 不调 can_use_tool，但 gate_tool_call 内部调 can_use_tool
            #   AST 解析 definition file 里 gate_tool_call 函数体有 can_use_tool 调用即过
            if not _ast_can_use_tool_in_gate_tool_call(def_src):
                cross_module_virtual.append(
                    f"{cap_id}: gate_tool_call 函数体未真调 can_use_tool（间接路径断裂）"
                )
        elif mode == "is_write_class_chain":
            # W-NEXT-MCP-003：chat 路径真用 classify_tool_intent 判定 student/manager 越权。
            #   路径 = tool_calling.py 直调 is_write_class( → permission_gate.is_write_class
            #   函数体真调 classify_tool_intent（保证契约挂起工具也能命中写类）
            cleaned = _strip_comments(caller_src)
            caller_calls = (symbol + "(") in cleaned
            if not caller_calls:
                cross_module_virtual.append(
                    f"{cap_id}: 跨模块 import 但 {caller} 函数体未真调 {symbol}(（仅 import 失接）"
                )
            elif not _ast_classify_tool_intent_in_is_write_class(def_src):
                cross_module_virtual.append(
                    f"{cap_id}: is_write_class 函数体未真调 classify_tool_intent（chat 路径契约意图判定断裂）"
                )
        elif mode == "gate_tool_call_chain":
            # W-NEXT-MCP-003：tool_calling 真用 can_use_tool 拒绝越权（HITL-FIX 子 agent P0）。
            #   tool_calling.run_chat_tool_calls 直调 gate_tool_call( → permission_gate.gate_tool_call
            #   内部真调 can_use_tool（间接链路）。
            if not _ast_can_use_tool_in_tool_calling_run(caller_src, def_src):
                cross_module_virtual.append(
                    f"{cap_id}: chat 路径 gate_tool_call → can_use_tool 间接链路断裂"
                    "（run_chat_tool_calls 未真调或 gate_tool_call 未真调 can_use_tool）"
                )
        elif mode == "build_denied_envelope_chain":
            # W-NEXT-MCP-003：tool_calling 真调 build_denied_envelope 输出 ACI 信封
            #   + permission_gate.build_denied_envelope 返回 dict 含 code（ACI 信封形态）。
            if not _ast_build_denied_envelope_in_tool_calling_run(caller_src, def_src):
                cross_module_virtual.append(
                    f"{cap_id}: chat 路径 build_denied_envelope 调用或 ACI 信封形态异常"
                    "（run_chat_tool_calls 未真调或 build_denied_envelope 返回值不含 code 字段）"
                )
        elif mode == "permission_gate_in_run":
            # W-NEXT-MCP-003：permission_gate 在 chat 工具调用路径上被真接（防"权限门做在错误位置"）
            if not _ast_permission_gate_in_tool_calling_run(caller_src):
                cross_module_virtual.append(
                    f"{cap_id}: tool_calling.run_chat_tool_calls 函数体未真调任一 permission_gate 符号"
                    "（权限门做在错误位置 / 绕过 tool_calling 主路径）"
                )
        else:
            raise ValueError(f"未知校验模式: {mode!r}")
    return {
        "virtual": virtual,
        "broken": broken,
        "cross_module_virtual": cross_module_virtual,
        "checked": len(rows),
        "ok": (not virtual) and (not broken) and (not cross_module_virtual),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(audit_mcp_capability(), ensure_ascii=False, indent=2))
