# -*- coding: utf-8 -*-
"""MCP-TRUTH 契约测试：能力对账门 + search_knowledge 接线 + 内置工具按名可达 + 四模块接线。

纯内存 / 纯函数 / 只读源码为主，无真实 DB / 无真实 MCP server / 无真实网络，可直接运行：
    cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_contract_mcptruth.py -q

对齐 kickoff-MCP-TRUTH 验收：
  - MT-G4  audit_mcp_capability() 差异全空 + pytest 契约测试绿
  - MT-G2  内置工具（calculator/search_knowledge）经 call_tool_with_retry 按名真实执行
  - MT-G1  set_search_knowledge_backend 注入后在 production 调用路径生效
"""
from __future__ import annotations

import json

import pytest

from app.mcp import executor, isolation
from app.mcp.capability_audit import audit_mcp_capability, _CAPABILITY_ROWS


# ============================================================
# MT-G4：能力对账门（声称能力 = 生产接线实况，差异必须为空）
# ============================================================
class TestCapabilityAuditGate:
    def test_all_claimed_capabilities_are_wired(self):
        res = audit_mcp_capability()
        assert res["virtual"] == [], f"能力虚标应为空，实测：{res['virtual']}"
        assert res["broken"] == [], f"引用断裂应为空，实测：{res['broken']}"
        assert res["ok"] is True
        assert res["checked"] == len(_CAPABILITY_ROWS)

    def test_audit_flags_virtual_when_claimed_but_unwired(self):
        # 模拟虚假声明：caller 脚本对该符号零引用 → 应判虚标
        rows = [("placeholder_cap", "no_such_symbol_xyz", "app/mcp/executor.py", "app/mcp/auth.py")]
        res = audit_mcp_capability(rows=rows)
        assert res["virtual"], "声称有能力但生产零引用必须被判虚标"
        assert res["ok"] is False

    def test_audit_flags_broken_when_call_refs_missing_def(self):
        # 模拟断裂：caller 引用了符号（_remote_auth_headers 在 executor.py 中真实存在），
        # 但声明其定义的文件 app/mcp/does_not_exist.py 不存在 → 应判断裂
        rows = [("broken_cap", "_remote_auth_headers", "app/mcp/executor.py", "app/mcp/does_not_exist.py")]
        res = audit_mcp_capability(rows=rows)
        assert res["broken"], "引用存在但模块缺失必须被判断裂"
        assert res["ok"] is False


# ============================================================
# MT-G2：内置工具经 call_tool_with_retry 按名真实执行（非入口 ERROR）
# ============================================================
class TestBuiltinByNameReachable:
    async def test_calculator_by_name_executes(self):
        resp = await executor.call_tool_with_retry(
            tool_name="calculator",
            args={"a": 6, "b": 7, "op": "mul"},
            operator_user_id=1,
            tenant_id="_test",
            trace_id="mcptruth-test",
        )
        # 按名直达真实处理器：去 JSON 壳（content_text 形式，server_id=0 内置）
        assert resp.status.value == "SUCCESS"
        assert resp.error_message is None
        body = json.loads(resp.content_text)
        assert body["result"] == 42.0 and body["tool"] == "calculator"

    async def test_search_knowledge_handler_with_injected_backend(self):
        # MT-G1：后台不可用时 handler 走确定性降级（非崩）
        saved = executor._SEARCH_KNOWLEDGE_BACKEND
        executor._SEARCH_KNOWLEDGE_BACKEND = None
        try:
            out = await executor._search_knowledge_handler({"q": "hello"})
            data = json.loads(out)
            assert data["degraded"] is True and data["results"] == [] and "未接入" in data["note"]
        finally:
            executor._SEARCH_KNOWLEDGE_BACKEND = saved

        # 注入真实后端后 → handler 返回真实结果（非空降级）
        async def fake_backend(q: str) -> str:
            return json.dumps({"results": [{"doc_id": 1, "query": q}], "degraded": False,
                               "note": "fake-backend"})

        executor.set_search_knowledge_backend(fake_backend)
        try:
            out2 = await executor._search_knowledge_handler({"q": "linear-algebra"})
            data2 = json.loads(out2)
            assert data2["degraded"] is False and data2["results"][0]["doc_id"] == 1
        finally:
            executor.set_search_knowledge_backend(saved)


# ============================================================
# 四模块接线：helper 在生产调用路径上的行为自证（auth / isolation）
# ============================================================
class TestFourModuleWiringHelpers:
    def test_remote_auth_headers_injects_api_key(self):
        # auth：配置 api_key → 生产 transport 注入认证头；无配置 → 零变化
        server = {
            "http_headers_json": json.dumps({"X-Trace": "t1"}),
            "auth_json": json.dumps({"auth_type": "api_key", "api_key": "k-42",
                                     "api_key_header": "X-API-Key", "api_key_prefix": ""}),
        }
        headers = executor._remote_auth_headers(server)
        assert headers["X-API-Key"] == "k-42"
        assert headers["X-Trace"] == "t1", "显式头应保留"

    def test_remote_auth_headers_unchanged_when_none(self):
        server = {"http_headers_json": json.dumps({"A": "1"}), "auth_json": "{}"}
        assert executor._remote_auth_headers(server) == {"A": "1"}

    def test_isolation_truncates_oversize_and_marks(self):
        # isolation：超限截断 + 标记；未超限原样
        text = "x" * (isolation.PER_TOOL_RESULT_MAX_CHARS + 100)
        out, truncated = executor._truncate_result_text(text)
        assert truncated is True and len(out) <= isolation.PER_TOOL_RESULT_MAX_CHARS + 60
        small, trunc2 = executor._truncate_result_text("ok")
        assert trunc2 is False and small == "ok"
        assert executor._truncate_result_text(None) == (None, False)

    def test_dynamic_update_sync_reports_diff(self):
        # dynamic_update：注册表同步返回差异（added/removed/updated）
        sid = 999001
        diff = executor._sync_dynamic_tools(sid, [{"tool_name": "a"}, {"tool_name": "b"}])
        assert sorted(diff["added"]) == ["a", "b"]
        diff2 = executor._sync_dynamic_tools(sid, [{"tool_name": "a"}, {"tool_name": "c"}])
        assert diff2["removed"] == ["b"] and diff2["added"] == ["c"]