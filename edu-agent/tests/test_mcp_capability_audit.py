# -*- coding: utf-8 -*-
"""W-NEXT-MCP-001 三态验收：capability_audit 跨模块对账 + 内置工具落审计 + 字段级脱敏。

对齐 kickoff 验收 GWT：
  MCP1-G1  audit_mcp_capability checked=10（7+跨模块3），virtual/broken 全空
  MCP1-G2  内置工具 calculator SUCCESS → mcp_tool_call_log 行 +1（含 operator_user_id/latency_ms/status）
  MCP1-G3  含 password 字段工具 → 落库 args_json 值 ***REDACTED***（不含明文）

G2/G3 以 monkeypatch 捕获落库入参，**离线、确定性、不依赖实时 DB**，直接验证 P0-②/P0-③
代码行为；真实 DB 端到端复现交给 check-demo.mjs ⑬ 健康门（打 live 8000 + MySQL，带自清）。
"""
from __future__ import annotations

import json

import pytest

from app.mcp import executor
from app.mcp.capability_audit import audit_mcp_capability, _CAPABILITY_ROWS


# ============================================================
# MCP1-G1：能力对账门（含跨模块 3 行）
# ============================================================
class TestCapabilityAuditTristate:
    def test_checked_eq_10_no_virtual_broken(self):
        res = audit_mcp_capability()
        assert res["checked"] == 10, f"checked 应为 10（7+跨模块3），实测 {res['checked']}"
        assert res["checked"] == len(_CAPABILITY_ROWS)
        assert res["virtual"] == [], f"能力虚标应为空：{res['virtual']}"
        assert res["broken"] == [], f"引用断裂应为空：{res['broken']}"
        assert res["ok"] is True

    def test_cross_module_rows_present(self):
        ids = [r[0] for r in _CAPABILITY_ROWS]
        for rid in ("permgate_is_write_class_called", "permgate_gate_tool_call_called",
                    "permgate_resolve_role_called"):
            assert rid in ids, f"跨模块对账行缺失：{rid}"


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
