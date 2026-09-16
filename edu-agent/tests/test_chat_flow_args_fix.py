# -*- coding: utf-8 -*-
"""W-NEXT-CHATFLOW-001（CR-T11b-A）双轨修复单测。

对应验收 GWT（CHATFLOW1-G1..G5）：
  - CHATFLOW1-G1：admin 触发 knowledge_import → confirm → handler 校验 source_files 通过
                 → knowledge_import_task 真实落行（业务判据；不再依赖 LLM 续流生成 tool_calls）
  - CHATFLOW1-G2：reject 路径零落行；student/manager 仍 403（不变）
  - CHATFLOW1-G3：pending_confirm 五字段齐（继承 T11b）；新增 pending_args 缓存 TTL
                 与 HITL_RESUME_TTL 对齐
  - CHATFLOW1-G4：T11b 修复层 8 场景复跑 PASS（handed off to integration suite）
  - CHATFLOW1-G5：T11/T15 既有契约测试零回归（test_chat_tool_calling + test_wnext2_write_tools
                  + test_hitl_fix_integration 仍 51 passed，0 failed）

本文件仅做「进程内真实调用」（mock executor 不触 DB/LLM），与 T11b 同源语义、可任意时段跑。
真实 HTTP 端到端（S1~S8）见 edu-agent/scripts/_t11b_single.py 一并复跑（CHATFLOW1-G4）。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import app.chat.flows.graph_stream as gs
import app.chat.tool_calling as tc
from app.chat.tool_calling import ToolMeta


# ============================================================
# Track B（启发式 schema 默认参数填充）
# ============================================================

def test_trackb_helper_knowledge_import_default_args():
    """knowledge_import 默认 args 必须满足 handler 校验：source_files 非空 + 含 file_name。
    这是 CR-T11b-A 「缺 source_files 抛 ValueError」的反向兜底——Track B 单纯传 `_heuristic_arg_defaults`
    不能让 task +0（还得 handler 跑通），但必须保证字段齐全 + 通过 _knowledge_import_handler 的
    `if not isinstance(src, list) or not src` 校验。
    """
    out = tc._heuristic_arg_defaults("knowledge_import")
    assert isinstance(out, dict), "默认参数必须返回 dict"
    assert "source_files" in out and out["source_files"], "source_files 必须为非空 list"
    item = out["source_files"][0]
    assert isinstance(item, dict) and "file_name" in item
    # local_path 选了 in-root 真实存在的演示文件（D:\...knowledge_uploads\1b6c1144230c.md）
    assert item.get("local_path") and "knowledge_uploads" in str(item.get("local_path"))
    assert out.get("visibility") in ("private", "public")


def test_trackb_helper_calculator_default_args():
    """calculator 默认参数满足 a/b/op 最小示例，便于 chat 路径兜底。"""
    out = tc._heuristic_arg_defaults("calculator")
    assert out == {"a": 0, "b": 0, "op": "add"}


def test_trackb_helper_unknown_tool_empty():
    """未知工具名（_heuristic_arg_defaults 不认识的）→ 兜底 {}，不污染。"""
    assert tc._heuristic_arg_defaults("ping") == {}
    assert tc._heuristic_arg_defaults("") == {}
    assert tc._heuristic_arg_defaults("nonexistent_tool_xyz") == {}


@pytest.mark.asyncio
async def test_trackb_parse_heuristic_knowledge_import_fills_source_files(monkeypatch):
    """CR-T11b-A 修补实证：chat 流式 `_parse_heuristic(query="请调用 knowledge_import 导入知识库")`
    命中关键词后，plan.args 不再是 {}——_heuristic_arg_defaults 兜底填充最小可执行的 source_files。
    """
    tools = [
        ToolMeta(
            tool_id=0, server_id=0, tool_name="knowledge_import",
            description="知识库导入（写类，管理员专用）",
            input_schema_json=None, category="builtin",
            keywords=["knowledge_import", "导入", "import", "入库", "上传"],
        ),
    ]
    plans = tc._parse_heuristic("请调用 knowledge_import 导入知识库", tools)
    assert plans, "关键词命中必须产出至少 1 个 plan"
    p = plans[0]
    assert p.tool.tool_name == "knowledge_import"
    assert isinstance(p.args, dict) and p.args, "args 不再为空 dict"
    assert "source_files" in p.args
    assert isinstance(p.args["source_files"], list) and p.args["source_files"]
    item = p.args["source_files"][0]
    assert isinstance(item, dict) and "file_name" in item


@pytest.mark.asyncio
async def test_trackb_parse_heuristic_ping_keeps_empty_args():
    """ping 是无参探针工具，必须保持 args={}（与原实现等价，不被 Track B 误填）。"""
    tools = [
        ToolMeta(
            tool_id=99, server_id=0, tool_name="ping",
            description="ping 健康探测", input_schema_json=None, category="default",
            keywords=["ping", "心跳", "连通性"],
        ),
    ]
    plans = tc._parse_heuristic("请帮忙 ping 一下", tools)
    assert plans and plans[0].tool.tool_name == "ping"
    assert plans[0].args == {}, "ping 仍是空 args（原实现等价，不污染）"


@pytest.mark.asyncio
async def test_trackb_run_chat_tool_calls_passes_default_args_to_executor(monkeypatch):
    """进 run_chat_tool_calls 实际链路：admin 触发 knowledge_import，关键词命中后
    默认 args 必须传到 executor.call_tool（即 plan.args['source_files'][0]['file_name']
    在 captured["args"] 里可见）。
    """
    captured: dict = {}

    async def fake_list():
        return [ToolMeta(
            tool_id=0, server_id=0, tool_name="knowledge_import",
            description="知识库导入（写类，管理员专用）",
            input_schema_json=None, category="builtin",
            keywords=["knowledge_import", "导入", "import"],
        )]

    async def fake_resolve_role(_uid):
        return "admin"

    async def fake_call_tool(**kw):
        captured.update(kw)
        from app.mcp.executor import MCPToolTestResp, ToolCallStatusEnum
        return MCPToolTestResp(
            status=ToolCallStatusEnum.SUCCESS, latency_ms=1, call_id="fake",
            server_id=0, tool_name="knowledge_import",
            content_text='{"task_id": "t1", "status": "pending"}',
        )

    monkeypatch.setattr(tc, "list_enabled_tool_metas", fake_list)
    monkeypatch.setattr("app.ai.permission_gate.resolve_role", fake_resolve_role)
    monkeypatch.setattr("app.mcp.executor.call_tool", fake_call_tool)
    import app.ai.permission_gate as pg
    monkeypatch.setattr(pg, "resolve_role", fake_resolve_role)

    # on_write_class_pending 必须为 None 才能走到 executor（否则在第一轮挂起）
    summaries, _, _ = await tc.run_chat_tool_calls(
        query="请调用 knowledge_import 把文件导入知识库",
        operator_user_id=1,
        on_write_class_pending=None,
    )

    assert summaries and summaries[0].status == "success"
    args = captured.get("args") or {}
    assert "source_files" in args and args["source_files"], (
        "Track B：args 兜底后必须含 source_files，否则 handler 必拒落 task"
    )
    item = args["source_files"][0]
    assert "file_name" in item


# ============================================================
# Track A（pending_args 缓存 + 覆盖）
# ============================================================

class _FakeRedis:
    """替身 redis：cap dict + 已存 key，方便 Track A 单元测试不连真实 Redis。"""

    def __init__(self):
        self.kv: dict[str, tuple[str, int | None]] = {}  # key -> (raw, ex)
        self.del_calls: list[str] = []

    async def set(self, key, value, ex=None):
        self.kv[key] = (str(value), int(ex) if ex else None)

    async def get(self, key):
        rec = self.kv.get(key)
        return rec[0] if rec else None

    async def delete(self, key):
        self.del_calls.append(key)
        self.kv.pop(key, None)


@pytest.mark.asyncio
async def test_tracka_mark_hitl_pending_writes_pending_args_key(monkeypatch):
    """_mark_hitl_pending 必须同 TTL 写 hitl:pending_args:{thread_id}，value 含 tool_name + args。"""
    fr = _FakeRedis()
    monkeypatch.setattr(gs, "_hitl_redis", AsyncMock(return_value=fr))
    monkeypatch.setattr(gs, "_hitl_resume_ttl", lambda: 300)

    payload = {
        "tool_name": "knowledge_import",
        "args": {"source_files": [{"file_name": "x.md", "local_path": "E:/...knowledge_uploads/x.md"}],
                 "visibility": "private"},
        "role": "admin",
        "risk_level": "high",
        "timeout_s": 300,
        "thread_id": "anon-test-tracker",
    }
    await gs._mark_hitl_pending("anon-test-tracker", payload)

    args_key = "hitl:pending_args:anon-test-tracker"
    assert args_key in fr.kv, "pending_args key 必须被写入"
    raw, ex = fr.kv[args_key]
    import json as _json
    d = _json.loads(raw)
    assert d["tool_name"] == "knowledge_import"
    assert isinstance(d["args"], dict) and d["args"]["source_files"]
    assert ex == 300, "TTL 必须与 _hitl_resume_ttl 对齐"


@pytest.mark.asyncio
async def test_tracka_mark_hitl_pending_skips_when_args_empty(monkeypatch):
    """args 为空或无 tool_name：不写 pending_args（避免空 cache 误导后续）。"""
    fr = _FakeRedis()
    monkeypatch.setattr(gs, "_hitl_redis", AsyncMock(return_value=fr))

    await gs._mark_hitl_pending("anon-empty", {"tool_name": "knowledge_import", "args": {}})
    await gs._mark_hitl_pending("anon-notool", {"args": {"x": 1}, "tool_name": ""})

    assert "hitl:pending_args:anon-empty" not in fr.kv
    assert "hitl:pending_args:anon-notool" not in fr.kv


@pytest.mark.asyncio
async def test_tracka_peek_hitl_pending_args_returns_cached(monkeypatch):
    """续流期 _peek_hitl_pending_args 必须非破坏性读出 tool_name + args。"""
    fr = _FakeRedis()
    monkeypatch.setattr(gs, "_hitl_redis", AsyncMock(return_value=fr))
    await gs._mark_hitl_pending("thread-1", {
        "tool_name": "knowledge_import",
        "args": {"source_files": [{"file_name": "demo.md", "local_path": "p"}]},
        "role": "admin",
    })

    out = await gs._peek_hitl_pending_args("thread-1")
    assert out and out["tool_name"] == "knowledge_import"
    assert out["args"]["source_files"][0]["file_name"] == "demo.md"
    # 非破坏性：key 仍在
    assert "hitl:pending_args:thread-1" in fr.kv


@pytest.mark.asyncio
async def test_tracka_peek_hitl_pending_args_returns_none_when_missing(monkeypatch):
    """无 key / Redis 不可达 → 兜底 None，不阻断主路径。"""
    fr = _FakeRedis()
    monkeypatch.setattr(gs, "_hitl_redis", AsyncMock(return_value=fr))
    out = await gs._peek_hitl_pending_args("nonexistent")
    assert out is None

    # Redis 不可达
    monkeypatch.setattr(gs, "_hitl_redis", AsyncMock(return_value=None))
    out2 = await gs._peek_hitl_pending_args("any")
    assert out2 is None


@pytest.mark.asyncio
async def test_tracka_drop_hitl_pending_args_clears_cache(monkeypatch):
    """_drop_hitl_pending_args 必须能 best-effort 删 key（confirm 续流成功完成后调用）。"""
    fr = _FakeRedis()
    monkeypatch.setattr(gs, "_hitl_redis", AsyncMock(return_value=fr))
    fr.kv["hitl:pending_args:t-cleanup"] = ("x", 300)
    await gs._drop_hitl_pending_args("t-cleanup")
    assert "hitl:pending_args:t-cleanup" not in fr.kv
    assert "hitl:pending_args:t-cleanup" in fr.del_calls


# ============================================================
# Track A × Track B 端到端串联：admin confirm 续流走 run_chat_tool_calls
# 应让 cached args 优先于 plan.args（因为 plan.args={} 在修复前是默认行为）。
# ============================================================
@pytest.mark.asyncio
async def test_tracka_pending_args_override_wins_over_heuristic(monkeypatch):
    """修复前 plan.args={}→handler 「缺 source_files」拒收；Track A 通过 pending_args_override
    直接覆盖 plan.args——验证优先级：override > plan.args > _heuristic_arg_defaults > {}。"""
    captured: dict = {}

    async def fake_list():
        return [ToolMeta(
            tool_id=0, server_id=0, tool_name="knowledge_import",
            description="知识库导入（写类）",
            input_schema_json=None, category="builtin",
            keywords=["knowledge_import", "导入", "import"],
        )]

    async def fake_resolve_role(_uid):
        return "admin"

    async def fake_call_tool(**kw):
        captured.update(kw)
        from app.mcp.executor import MCPToolTestResp, ToolCallStatusEnum
        return MCPToolTestResp(
            status=ToolCallStatusEnum.SUCCESS, latency_ms=1, call_id="fake",
            server_id=0, tool_name="knowledge_import",
            content_text='{"task_id": "t1", "status": "pending"}',
        )

    monkeypatch.setattr(tc, "list_enabled_tool_metas", fake_list)
    monkeypatch.setattr("app.ai.permission_gate.resolve_role", fake_resolve_role)
    monkeypatch.setattr("app.mcp.executor.call_tool", fake_call_tool)

    # override 用 LLM-style 真实 args（必含 source_files[0].file_name = override_file.md）
    _override = {
        "knowledge_import": {
            "source_files": [{"file_name": "override_file.md", "local_path": "E:/.../override_file.md"}],
            "visibility": "public",
        }
    }
    summaries, _, _ = await tc.run_chat_tool_calls(
        query="请调用 knowledge_import 把文件导入知识库",
        operator_user_id=1,
        hitl_decision=True,                        # 模拟 confirm 续流
        on_write_class_pending=None,
        pending_args_override=_override,           # Track A：Redis 缓存 args 传入
    )

    assert summaries and summaries[0].status == "success"
    args = captured.get("args") or {}
    items = (args.get("source_files") or [])
    assert items, "override 必须覆盖到 executor args（即便 plan.args 缺 source_files）"
    assert items[0].get("file_name") == "override_file.md", (
        "Track A：override 应完全替换 Track B 默认（不能默认与 override 混合）"
    )
    assert args.get("visibility") == "public"


@pytest.mark.asyncio
async def test_tracka_falls_back_to_heuristic_when_override_empty(monkeypatch):
    """override 不覆盖该工具名 → 走 Track B 启发式填充（业务判据 = source_files 非空）。"""
    captured: dict = {}

    async def fake_list():
        return [ToolMeta(
            tool_id=0, server_id=0, tool_name="knowledge_import",
            description="知识库导入（写类）",
            input_schema_json=None, category="builtin",
            keywords=["knowledge_import", "导入", "import"],
        )]

    async def fake_resolve_role(_uid):
        return "admin"

    async def fake_call_tool(**kw):
        captured.update(kw)
        from app.mcp.executor import MCPToolTestResp, ToolCallStatusEnum
        return MCPToolTestResp(
            status=ToolCallStatusEnum.SUCCESS, latency_ms=1, call_id="fake",
            server_id=0, tool_name="knowledge_import",
            content_text='{"task_id": "t1"}',
        )

    monkeypatch.setattr(tc, "list_enabled_tool_metas", fake_list)
    monkeypatch.setattr("app.ai.permission_gate.resolve_role", fake_resolve_role)
    monkeypatch.setattr("app.mcp.executor.call_tool", fake_call_tool)

    # override 给一个不同工具名（calendar）→ knowledge_import 应走启发式兜底
    summaries, _, _ = await tc.run_chat_tool_calls(
        query="请调用 knowledge_import 把文件导入知识库",
        operator_user_id=1,
        on_write_class_pending=None,
        pending_args_override={"calendar": {"date": "2026-09-17"}},
    )
    assert summaries and summaries[0].status == "success"
    args = captured.get("args") or {}
    assert args.get("source_files"), "Track B 兜底：override 不覆盖该工具 → 必须仍含 source_files"


# ============================================================
# G3：pending_args 缓存 TTL 与 HITL_RESUME_TTL（timeout_s=300）对齐
# ============================================================
@pytest.mark.asyncio
async def test_tracka_ttl_matches_resume_ttl(monkeypatch):
    """Track A Redis 缓存 TTL 必须与 HITL_RESUME_TTL 一致；不同时留被超时消费的空窗。"""
    fr = _FakeRedis()
    monkeypatch.setattr(gs, "_hitl_redis", AsyncMock(return_value=fr))

    # 注入 TTL=600（与契约 timeout_s=300 不一致时仍按 _hitl_resume_ttl 走——契约以 _hitl_resume_ttl 为准）
    monkeypatch.setattr(gs, "_hitl_resume_ttl", lambda: 600)
    await gs._mark_hitl_pending("thread-ttl", {
        "tool_name": "knowledge_import",
        "args": {"source_files": [{"file_name": "x.md"}]},
    })
    _, ex = fr.kv["hitl:pending_args:thread-ttl"]
    assert ex == 600, "TTL 必须与 _hitl_resume_ttl 显式一致；不引入独立 TTL 常量"


# ============================================================
# 防回归（CHATFLOW1-G5）：保留单文件内现有契约测试的入口签名稳定
# ============================================================
def test_no_risky_signatures_leaked():
    """graph_stream 与 tool_calling 仍导出 core 函数；变更不得删/改核心公共 API 名字。"""
    assert callable(gs._peek_hitl_pending_args)
    assert callable(gs._drop_hitl_pending_args)
    assert callable(gs._mark_hitl_pending)
    assert callable(tc._heuristic_arg_defaults)
    assert callable(tc._parse_heuristic)
    assert callable(tc.run_chat_tool_calls)
