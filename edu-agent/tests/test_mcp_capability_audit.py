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
    _CAPABILITY_ROWS, _ast_can_use_tool_in_gate_tool_call, _read,
    _strip_comments, audit_mcp_capability,
)


# ============================================================
# MCP1-G1 / MCP2-G1：能力对账门（含跨模块行 + 真接对账行）
# ============================================================
class TestCapabilityAuditTristate:
    def test_checked_eq_12_no_virtual_broken(self):
        """MCP2-G1：checked==12，virtual/broken/cross_module_virtual 三态全空。"""
        res = audit_mcp_capability()
        assert res["checked"] == 12, f"checked 应为 12（10+跨模块真接 +2），实测 {res['checked']}"
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
