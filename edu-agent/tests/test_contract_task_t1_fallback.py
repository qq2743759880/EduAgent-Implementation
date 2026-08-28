"""task-T1-② 契约测试：备用工具 calculator/search_knowledge 注册为内置本地工具，
switch_tool 第 3 步命中即真实执行（非"未注册自然走人工指南"）。
"""
import asyncio
import json
import sys

sys.path.insert(0, ".")

from app.mcp.executor import _default_attempt_executor, _BUILTIN_TOOL_HANDLERS


def _run(name, args):
    return asyncio.run(_default_attempt_executor(
        name, args, call_id="t1", attempt=1,
        operator_user_id=0, tenant_id="x", trace_id="y",
    ))


def test_registered():
    assert "calculator" in _BUILTIN_TOOL_HANDLERS, "calculator 未注册为内置工具"
    assert "search_knowledge" in _BUILTIN_TOOL_HANDLERS, "search_knowledge 未注册为内置工具"


def test_calculator_real():
    out = _run("calculator", {"a": 2, "b": 3, "op": "mul"})
    assert out.ok, f"calculator 未命中真实处理器: {out.error_message}"
    data = json.loads(out.content_text)
    assert data["result"] == 6.0, f"calculator 结果错误: {data}"


def test_search_knowledge_resolves():
    # 后端未注入 → 降级返回（仍属"真实命中处理器"，不再走人工指南）
    out = _run("search_knowledge", {"q": "勾股定理"})
    assert out.ok, f"search_knowledge 未命中真实处理器: {out.error_message}"
    data = json.loads(out.content_text)
    assert data["degraded"] is True


if __name__ == "__main__":
    test_registered()
    test_calculator_real()
    test_search_knowledge_resolves()
    print("ALL OK: T1-② 备用工具注册为真实可执行工具")
