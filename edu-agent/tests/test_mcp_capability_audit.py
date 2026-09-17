# -*- coding: utf-8 -*-
"""W-NEXT-MCP-001 + W-NEXT-MCP-002 验收：capability_audit 跨模块对账 + 内置工具落审计 + 字段级脱敏。

对齐 kickoff 验收 GWT：
  MCP1-G1  audit_mcp_capability checked=10（7+跨模块3），virtual/broken 全空
  MCP2-G1  audit_mcp_capability checked=12（10+跨模块 +2 真接对账），含
            cross_module_virtual 第三态全空
  MCP1-G2  内置工具 calculator SUCCESS → mcp_tool_call_log 行 +1（含 operator_user_id/latency_ms/status）
  MCP1-G3  含 password 字段工具 → 落库 args_json 值 ***REDACTED***（不含明文）
  MCP2-G2  executor 5 处 import permission_gate 全「真调用」验证（5 个符号 call()+1 AST 间接路径）

G2/G3 以 monkeypatch 捕获落库入参，**离线、确定性、不依赖实时 DB**，直接验证 P0-②/P0-③
代码行为；真实 DB 端到端复现交给 check-demo.mjs ⑬ 健康门（打 live 8000 + MySQL，带自清）。
"""
from __future__ import annotations

import json

import pytest

from app.mcp import executor
from app.mcp.capability_audit import (
    _CAPABILITY_ROWS, _ast_build_denied_envelope_in_tool_calling_run,
    _ast_can_use_tool_in_gate_tool_call, _ast_can_use_tool_in_tool_calling_run,
    _ast_classify_tool_intent_in_is_write_class, _ast_permission_gate_in_tool_calling_run,
    _read, _strip_comments, audit_mcp_capability,
)


# ============================================================
# MCP1-G1 / MCP2-G1 / MCP3-G1：能力对账门（含跨模块行 + 真接对账行）
# ============================================================
class TestCapabilityAuditTristate:
    def test_checked_eq_17_no_virtual_broken(self):
        """MCP3-G1：checked==17（12+跨模块真接 +5），virtual/broken/cross_module_virtual 三态全空。"""
        res = audit_mcp_capability()
        assert res["checked"] == 17, f"checked 应为 17（12+跨权限门对账 +5），实测 {res['checked']}"
        assert res["checked"] == len(_CAPABILITY_ROWS)
        assert res["virtual"] == [], f"能力虚标应为空：{res['virtual']}"
        assert res["broken"] == [], f"引用断裂应为空：{res['broken']}"
        assert res["cross_module_virtual"] == [], (
            f"跨模块未实调应为空：{res['cross_module_virtual']}"
        )
        assert res["ok"] is True

    def test_cross_module_rows_present(self):
        """MCP2-G1 列表完整性：5 个跨模块真接对账行均存在。"""
        ids = [r[0] for r in _CAPABILITY_ROWS]
        for rid in (
            "permgate_is_write_class_called",         # W-NEXT-MCP-001
            "permgate_gate_tool_call_called",         # W-NEXT-MCP-001
            "permgate_resolve_role_called",           # W-NEXT-MCP-001
            "permgate_build_denied_envelope_called",  # W-NEXT-MCP-002 新增
            "permgate_can_use_tool_indirect_called",  # W-NEXT-MCP-002 新增（AST 间接路径）
        ):
            assert rid in ids, f"跨模块对账行缺失：{rid}"

    def test_cross_module_call_rows_have_call_mode(self):
        """MCP2-G1 严格口径：5 个跨模块行必须用「call」「can_use_tool_indirect」真接模式，
        不能用「grep」宽松口径（否则失去跨模块对账原意）。"""
        rows_by_id = {r[0]: r for r in _CAPABILITY_ROWS}
        for rid in (
            "permgate_is_write_class_called",
            "permgate_gate_tool_call_called",
            "permgate_resolve_role_called",
            "permgate_build_denied_envelope_called",
            "permgate_can_use_tool_indirect_called",
        ):
            mode = rows_by_id[rid][4]
            assert mode in ("call", "can_use_tool_indirect"), (
                f"{rid} 校验模式应为 call/can_use_tool_indirect，实测 {mode!r}"
            )


# ============================================================
# MCP2-G2：executor 5 处 import → 「真调用」严格验证（含 AST 间接路径）
# ============================================================
class TestCrossModuleRealCallDetection:
    def test_build_denied_envelope_real_call_in_executor(self):
        """MCP2-G2-④：executor 函数体里 build_denied_envelope( 真调用（非仅 import）。"""
        src = _read("app/mcp/executor.py")
        cleaned = _strip_comments(src)
        assert "build_denied_envelope(" in cleaned, (
            "executor 函数体未真调 build_denied_envelope( （仅 import 失接）"
        )

    def test_can_use_tool_indirect_path_via_gate_tool_call(self):
        """MCP2-G2-⑤：can_use_tool 不经 executor 直调，但 gate_tool_call 内部 AST 可见真调。"""
        gate_src = _read("app/ai/permission_gate.py")
        assert _ast_can_use_tool_in_gate_tool_call(gate_src), (
            "permission_gate.gate_tool_call 函数体未真调 can_use_tool（间接路径断裂）"
        )

    def test_ast_detector_rejects_comment_only_invocation(self):
        """AST 探测器必须区分注释里的同名 vs 真实调用（防「注释里写 can_use_tool 即过」伪修复）。"""
        fake = """
def gate_tool_call(role, tool_name):
    # decision = can_use_tool(role, tool_name)
    return None
"""
        assert _ast_can_use_tool_in_gate_tool_call(fake) is False

    def test_ast_detector_rejects_stub(self):
        """AST 探测器必须拒绝空 stub（即 gate_tool_call 改成不再真调的桩）。"""
        stub = """
def gate_tool_call(role, tool_name):
    return None
"""
        assert _ast_can_use_tool_in_gate_tool_call(stub) is False

    def test_cross_module_virtual_buckets_clean(self):
        """MCP2-G2：故意构造一个失接情形验证 cross_module_virtual 会被正确报出。"""
        # 临时注入一行「仅 import 不调」的 row，断言 cross_module_virtual 非空
        rows = list(_CAPABILITY_ROWS) + [
            ("phantom_unused_import", "this_is_a_fake_symbol",
             "app/mcp/executor.py", "app/ai/permission_gate.py", "call"),
        ]
        res = audit_mcp_capability(rows=rows)
        assert res["ok"] is False
        assert any("phantom_unused_import" in s for s in res["cross_module_virtual"]), \
            f"fake 失接应进 cross_module_virtual，实测: {res['cross_module_virtual']}"


# ============================================================
# MCP1-G2：内置工具落 mcp_tool_call_log（server_id=0）
# ============================================================
class TestBuiltinAuditLog:
    async def test_builtin_calculator_writes_log(self, monkeypatch):
        captured = []

        async def _fake_write(*, call_id, server_id, tool_name, args, result, content_text,
                               status, latency_ms, user_id, tenant_id, trace_id, error_message):
            captured.append(dict(call_id=call_id, server_id=server_id, tool_name=tool_name,
                                 status=status, latency_ms=latency_ms, user_id=user_id,
                                 tenant_id=tenant_id, trace_id=trace_id))

        monkeypatch.setattr(executor, "_write_call_log", _fake_write)
        resp = await executor._execute_builtin_attempt(
            tool_name="calculator", args={"a": 6, "b": 7, "op": "mul"},
            call_id="unit-g2-001", operator_user_id=1, tenant_id="ut", trace_id="g2",
        )
        assert resp.status.value == "SUCCESS"
        assert len(captured) == 1, "内置工具执行应恰好落 1 条审计"
        c = captured[0]
        assert c["server_id"] == 0, "内置工具 server_id 必须为 0（内置标识）"
        assert c["tool_name"] == "calculator"
        assert c["user_id"] == 1, "审计行必须带 operator_user_id"
        assert c["status"].value == "SUCCESS"
        assert c["latency_ms"] >= 0


# ============================================================
# MCP1-G3：字段级脱敏（args/result 敏感 key → ***REDACTED***）
# ============================================================
class TestFieldRedaction:
    async def test_password_redacted_in_args_json(self, monkeypatch):
        captured = {}

        async def _fake_execute_write(sql, params):
            captured["sql"] = sql
            captured["params"] = params

        monkeypatch.setattr(executor, "execute_write", _fake_execute_write)
        await executor._execute_builtin_attempt(
            tool_name="calculator",
            args={"a": 1, "b": 2, "op": "add", "password": "secret123"},
            call_id="unit-g3-001", operator_user_id=1, tenant_id="ut", trace_id="g3",
        )
        params = captured["params"]
        # params 顺序（见 executor._write_call_log）：call_id, server_id, tool_name, args_json,
        #   result_json, status, latency_ms, user_id, tenant_id, trace_id, error_message
        args_json = params[3]
        assert "secret123" not in args_json, "明文密码不得出现在落库 args_json"
        assert "***REDACTED***" in args_json, "password 字段值应被脱敏为 ***REDACTED***"
        assert '"password"' in args_json, "敏感 key 本身保留（仅值脱敏）"

    def test_redact_sensitive_helper(self):
        out = executor._redact_sensitive(
            {"user": "a", "api_key": "k1", "nested": {"token": "t1", "ok": 1}}
        )
        assert out["user"] == "a"
        assert out["api_key"] == "***REDACTED***"
        assert out["nested"]["token"] == "***REDACTED***"
        assert out["nested"]["ok"] == 1
        assert executor._redact_sensitive(["x", {"secret": "s"}]) == ["x", {"secret": "***REDACTED***"}]

    def test_truncate_json(self):
        big = "x" * 5000
        out = executor._truncate_json(big)
        assert out.endswith("...truncated") and len(out) == 4096 + len("...truncated")
        assert executor._truncate_json(None) is None


# ============================================================
# MCP2-G2 补充：直接验证 5 个跨模块符号在 executor 函数体里的「真调用」计数
# ============================================================
class TestFiveExecutorImportsAllCalled:
    """T12 P0-① + kickoff 任务要求：executor 5 处 import 必须每处有实调。

    5 个跨模块符号：is_write_class / build_denied_envelope / gate_tool_call /
                    resolve_role / can_use_tool（can_use_tool 走间接 → 不计 executor 直调）。
    """

    def test_five_symbols_real_invocation_counts(self):
        """5 个跨模块符号（含 1 个间接路径）各自的实调证据。"""
        executor_src = _read("app/mcp/executor.py")
        cleaned = _strip_comments(executor_src)
        # 4 个直调符号（call 形态）
        for sym in ("is_write_class(", "build_denied_envelope(", "gate_tool_call(", "resolve_role("):
            assert sym in cleaned, f"executor 函数体未真调 {sym}（失接）"
        # 1 个间接符号 can_use_tool（不经 executor 直调，仅在 permission_gate 内部）
        executor_can_use_tool = "can_use_tool(" in cleaned
        # can_use_tool 可在 executor 内零调用（gate_tool_call 已间接覆盖）
        # 这条断言只允许 executor 零直调（对账门本身不报虚拟），不强制正命中
        if executor_can_use_tool:
            # 若 executor 偶然也直调，AST 解析能再次确认吗_use_tool 是真调用
            import ast
            tree = ast.parse(executor_src)
            found = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    f = node.func
                    if isinstance(f, ast.Name) and f.id == "can_use_tool":
                        found = True
                        break
            assert found, "executor 文本里有 can_use_tool( 但 AST 解析找不到 → 命中注释/字符串伪命"
        # 关键：permission_gate 间接路径必须 AST 可证（独立断言以强调间接实调）
        gate_src = _read("app/ai/permission_gate.py")
        assert _ast_can_use_tool_in_gate_tool_call(gate_src), (
            "permission_gate.gate_tool_call 函数体未真调 can_use_tool（间接路径断裂）"
        )


# ============================================================
# W-NEXT-MCP-003：跨权限门对账（chat 路径 permission_gate 接线全覆盖）
# ============================================================
class TestCrossPermissionGateChatPath:
    """MCP3-G1/G4：5 个新对账行实证 + AST 真调用检测 + 4 个跨权限门 API 全覆盖。

    设计：
      - permission_gate.py 必须含 admin-only 工具清单结构（grep 实证）
      - tool_calling.run_chat_tool_calls 函数体真调 is_write_class（call + AST 链）
      - permission_gate.is_write_class 函数体真调 classify_tool_intent（契约意图判定）
      - tool_calling.run_chat_tool_calls 真调 gate_tool_call（间接 can_use_tool）
      - tool_calling.run_chat_tool_calls 真调 build_denied_envelope + 信封形态正确
      - tool_calling.run_chat_tool_calls 真调任一 permission_gate 符号（防"权限门做在错误位置"）
    """

    def test_admin_only_tools_class_exists_in_permission_gate(self):
        """MCP3-G1-⑥：permission_gate 内 _CLASS_ALLOWED_ROLES 字典含 admin_write 类别且允许角色仅 admin。"""
        src = _read("app/ai/permission_gate.py")
        assert "_CLASS_ALLOWED_ROLES" in src, (
            "permission_gate 缺 _CLASS_ALLOWED_ROLES 字典（admin-only 工具清单结构）"
        )
        # admin_write 类别允许角色仅 admin —— 结构存在即过
        import ast
        try:
            t = ast.parse(src)
        except SyntaxError:
            raise AssertionError("permission_gate.py 语法错")

        def _extract_elt_strings(node):
            """从 frozenset({...}) / set({...}) / Tuple 等字面量抽出字符串常量集合。"""
            out = set()
            # frozenset({"admin"}) 等：Call.func.id ∈ {frozenset,set}
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"frozenset", "set"}:
                if node.args and isinstance(node.args[0], ast.Set):
                    for e in node.args[0].elts:
                        if isinstance(e, ast.Constant) and isinstance(getattr(e, "value", None), str):
                            out.add(e.value)
                if node.args and isinstance(node.args[0], ast.List):
                    for e in node.args[0].elts:
                        if isinstance(e, ast.Constant) and isinstance(getattr(e, "value", None), str):
                            out.add(e.value)
            return out

        for node in ast.walk(t):
            value_node = None
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == "_CLASS_ALLOWED_ROLES":
                        value_node = node.value
                        break
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "_CLASS_ALLOWED_ROLES":
                    value_node = node.value
            if value_node is None:
                continue
            assert isinstance(value_node, ast.Dict), (
                f"_CLASS_ALLOWED_ROLES 应为 dict 字面量，实测 {type(value_node).__name__}"
            )
            # 查找 admin_write 键
            for k, v in zip(value_node.keys, value_node.values):
                if isinstance(k, ast.Constant) and getattr(k, "value", None) == "admin_write":
                    roles = _extract_elt_strings(v)
                    assert "admin" in roles, (
                        f"admin_write 类别允许角色集合缺 'admin'，实测 {roles}"
                    )
                    # 仅 admin 即「admin-only」语义；其他角色（如 manager/student）出现就告警
                    extra = roles - {"admin"}
                    assert not extra, (
                        f"admin_write 类别应为 admin-only，实测额外放行: {extra}"
                    )
                    return
            raise AssertionError("_CLASS_ALLOWED_ROLES 缺 admin_write 类别")
        raise AssertionError("permission_gate.py 找不到 _CLASS_ALLOWED_ROLES 赋值/注解")

    def test_tool_calling_uses_is_write_class_in_run(self):
        """MCP3-G1-⑦：tool_calling.run_chat_tool_calls 函数体真调 is_write_class( 。"""
        src = _read("app/chat/tool_calling.py")
        cleaned = _strip_comments(src)
        assert "is_write_class(" in cleaned, (
            "tool_calling.py 函数体未真调 is_write_class( （写类判定失接）"
        )
        # AST 校验：必须在 run_chat_tool_calls 函数体内（不是别的函数）
        import ast
        tree = ast.parse(src)
        run_fn = None
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "run_chat_tool_calls":
                run_fn = n
                break
        assert run_fn is not None, "tool_calling.py 缺 run_chat_tool_calls 函数"
        found = False
        for sub in ast.walk(run_fn):
            if isinstance(sub, ast.Call):
                func = sub.func
                if isinstance(func, ast.Name) and func.id == "is_write_class":
                    found = True
                    break
        assert found, "is_write_class( 在文本里有但 run_chat_tool_calls 函数体内 AST 不可见"

    def test_is_write_class_calls_classify_tool_intent(self):
        """MCP3-G1-⑦：permission_gate.is_write_class 函数体真调 classify_tool_intent（契约意图判定）。"""
        gate_src = _read("app/ai/permission_gate.py")
        assert _ast_classify_tool_intent_in_is_write_class(gate_src), (
            "permission_gate.is_write_class 函数体未真调 classify_tool_intent（契约意图判定断裂）"
        )

    def test_ast_classify_tool_intent_rejects_stub(self):
        """AST 探测器拒绝把 is_write_class 改成空 stub（必须保持 classify_tool_intent 调用）。"""
        stub = """
def classify_tool_intent(tool_name):
    return None

def is_write_class(tool_name):
    # 误以为仅用 is_write_class 自己就够 → 没真调 classify_tool_intent
    return False
"""
        assert _ast_classify_tool_intent_in_is_write_class(stub) is False

    def test_ast_classify_tool_intent_rejects_comment_only(self):
        """AST 探测器拒绝「注释里写 classify_tool_intent 即过」伪修复。"""
        stub = """
def classify_tool_intent(tool_name):
    return None

def is_write_class(tool_name):
    # cls = classify_tool_intent(tool_name)
    return False
"""
        assert _ast_classify_tool_intent_in_is_write_class(stub) is False

    def test_tool_calling_can_use_tool_indirect_chain(self):
        """MCP3-G1-⑧：tool_calling.run_chat_tool_calls 真调 gate_tool_call，
        且 permission_gate.gate_tool_call 真调 can_use_tool（chat 路径间接链路）。"""
        caller_src = _read("app/chat/tool_calling.py")
        def_src = _read("app/ai/permission_gate.py")
        assert _ast_can_use_tool_in_tool_calling_run(caller_src, def_src), (
            "chat 路径 gate_tool_call → can_use_tool 间接链路断裂"
            "（run_chat_tool_calls 未真调或 gate_tool_call 未真调 can_use_tool）"
        )

    def test_tool_calling_uses_build_denied_envelope_with_aci_envelope_shape(self):
        """MCP3-G1-⑨：tool_calling.run_chat_tool_calls 真调 build_denied_envelope，
        且 permission_gate.build_denied_envelope 返回值含 'code' 字段（ACI 信封形态）。"""
        caller_src = _read("app/chat/tool_calling.py")
        def_src = _read("app/ai/permission_gate.py")
        assert _ast_build_denied_envelope_in_tool_calling_run(caller_src, def_src), (
            "tool_calling 路径 build_denied_envelope 调用或 ACI 信封形态异常"
            "（run_chat_tool_calls 未真调或 build_denied_envelope 返回值不含 code 字段）"
        )

    def test_permission_gate_in_tool_calling_run(self):
        """MCP3-G1-⑩：permission_gate 至少 1 个符号在 run_chat_tool_calls 函数体内真调（防"权限门做在错误位置"）。"""
        caller_src = _read("app/chat/tool_calling.py")
        assert _ast_permission_gate_in_tool_calling_run(caller_src), (
            "tool_calling.run_chat_tool_calls 函数体未真调任一 permission_gate 符号"
            "（权限门做在错误位置 / 绕过 tool_calling 主路径）"
        )

    def test_ast_build_denied_envelope_rejects_stub(self):
        """AST 探测器拒绝 build_denied_envelope 改成返回非 dict（如 None）。"""
        # 构造一个 tool_calling.py stub 不调 build_denied_envelope
        caller_stub = """
async def run_chat_tool_calls(*, query):
    return [], "", None
"""
        def_src = _read("app/ai/permission_gate.py")
        assert _ast_build_denied_envelope_in_tool_calling_run(caller_stub, def_src) is False

    def test_ast_build_denied_envelope_rejects_no_code_field(self):
        """AST 探测器拒绝 build_denied_envelope 返回的 dict 不含 code 字段（非 ACI 信封形态）。"""
        caller_src = _read("app/chat/tool_calling.py")
        # def_file 改成不含 code 的字典返回（伪造 def_src）
        bad_def = """
def build_denied_envelope(role, tool_name, decision=None):
    return {"status": "denied", "tool_name": tool_name}  # 缺 code 字段
"""
        assert _ast_build_denied_envelope_in_tool_calling_run(caller_src, bad_def) is False

    def test_ast_permission_gate_in_run_rejects_empty(self):
        """AST 探测器拒绝 tool_calling.run_chat_tool_calls 不调任何 permission_gate 符号。"""
        empty_run = """
async def run_chat_tool_calls(*, query):
    return [], "", None
"""
        assert _ast_permission_gate_in_tool_calling_run(empty_run) is False

    def test_five_new_rows_in_rows_table(self):
        """MCP3-G1：5 个新对账行均存在于 _CAPABILITY_ROWS。"""
        ids = [r[0] for r in _CAPABILITY_ROWS]
        for rid in (
            "permission_gate_admin_only_tools_exist",
            "permission_gate_classify_tool_intent",
            "tool_calling_can_use_tool_indirect_called",
            "tool_calling_uses_build_denied_envelope",
            "permission_gate_in_tool_calling_module",
        ):
            assert rid in ids, f"新增对账行缺失：{rid}"

    def test_five_new_rows_have_distinct_auth(self):
        """MCP3-G1 严格口径：5 个新对账行 mode 不能全是 grep（必须跨 grep/call/AST 链 真接）。"""
        rows_by_id = {r[0]: r for r in _CAPABILITY_ROWS}
        for rid in (
            "permission_gate_admin_only_tools_exist",
            "permission_gate_classify_tool_intent",
            "tool_calling_can_use_tool_indirect_called",
            "tool_calling_uses_build_denied_envelope",
            "permission_gate_in_tool_calling_module",
        ):
            row = rows_by_id[rid]
            assert len(row) == 5, f"{rid} 应为 5 元组（带模式）"
            mode = row[4]
            assert mode in (
                "grep", "call", "can_use_tool_indirect",
                "is_write_class_chain", "gate_tool_call_chain",
                "build_denied_envelope_chain", "permission_gate_in_run",
            ), f"{rid} 模式未知: {mode!r}"
        # 至少 4 个新行用真接模式（非纯 grep）
        new_modes = [rows_by_id[r][4] for r in (
            "permission_gate_admin_only_tools_exist",
            "permission_gate_classify_tool_intent",
            "tool_calling_can_use_tool_indirect_called",
            "tool_calling_uses_build_denied_envelope",
            "permission_gate_in_tool_calling_module",
        )]
        non_grep = sum(1 for m in new_modes if m != "grep")
        assert non_grep >= 4, (
            f"5 个新对账行中至少 4 个应走真接模式（call/chain/indirect），实测 {new_modes}"
        )

    def test_phantom_chat_path_disconnect_caught(self):
        """MCP3-G4 负向证据：故意构造 chat 路径失接 → 应被推进 cross_module_virtual。"""
        # 注入一个 fake「chat 路径不调 is_write_class」的 row
        rows = list(_CAPABILITY_ROWS) + [
            ("phantom_chat_no_is_write_class", "this_does_not_exist_in_chat",
             "app/chat/tool_calling.py", "app/ai/permission_gate.py", "is_write_class_chain"),
        ]
        res = audit_mcp_capability(rows=rows)
        assert res["ok"] is False
        assert any("phantom_chat_no_is_write_class" in s for s in res["cross_module_virtual"]), (
            f"fake chat 失接应进 cross_module_virtual，实测: {res['cross_module_virtual']}"
        )

    def test_audit_returns_dict_with_serializable_values(self):
        """MCP3-G5：audit_mcp_capability 返回 dict[str, list[str] | int | bool]，
        全部 JSON serializable（供 check-demo 探针输出）。"""
        import json
        res = audit_mcp_capability()
        # 直接序列化：必须不抛 TypeError
        try:
            json.dumps(res, ensure_ascii=False)
        except TypeError as e:
            raise AssertionError(f"audit_mcp_capability 返回值非 JSON serializable: {e}")
        # 字段类型校验
        assert isinstance(res, dict)
        assert isinstance(res["virtual"], list)
        assert isinstance(res["broken"], list)
        assert isinstance(res["cross_module_virtual"], list)
        assert isinstance(res["checked"], int)
        assert isinstance(res["ok"], bool)
        assert all(isinstance(s, str) for s in res["virtual"])
        assert all(isinstance(s, str) for s in res["broken"])
        assert all(isinstance(s, str) for s in res["cross_module_virtual"])
