# -*- coding: utf-8 -*-
"""F-3/F-5 SSE 信封契约测试——钉死 POST /api/chat/stream 现行帧形状，防漂移（零线变更）。

现状（2026-09-15 curl/源码实证，前端 edu-api.js 已按此解析，**改线=破坏性**，本测试只钉不改）：
  - start     裸帧：data 恰好 {"session_id": ..., "query": ...}（无 message_id_pre）
  - retrieval 裸帧：data 恰好 7 键
        {docs, graph_entities, retrieved_count, final_count,
         rewrite_query, degraded_reason, mcp_tool_calls}
  - token     裸帧：data 恰好 {"delta": ...}（累加 delta=最终答案；token 字段已弃用）
  - done     信封帧：data 恰好 {"code": 0, "message": "ok", "data": {最终产物...}}
  - error    裸帧：data {"code": <字符串>, "message": ...}（不套 code/message/data 壳）
两条产生路径（旧 service_chat_stream 路径 + 默认 graph.astream 适配层）必须逐帧同构。
另钉 ``sse_line`` 线格式（event 行/data 行/空行 + ensure_ascii=False 中文不转义）。
"""
from __future__ import annotations

import json
import types

import httpx
import pytest
from fastapi import FastAPI

from app.auth.dependencies import UserInfo, UserRole
from app.chat import router as chat_router
from app.chat import sse as chat_sse
from app.chat.flows import graph_stream as gs
from app.chat.schemas import SseEventType
from app.config import settings

# 帧字段集合（冻结现状；任何改动必须先改本测试并经契约评审）
START_KEYS = {"session_id", "query"}
RETRIEVAL_KEYS = {
    "docs", "graph_entities", "retrieved_count", "final_count",
    "rewrite_query", "degraded_reason", "mcp_tool_calls",
}
TOKEN_KEYS = {"delta"}
DONE_TOP_KEYS = {"code", "message", "data"}
DONE_DATA_KEYS = {
    "session_id", "message_id", "retrieved_count", "final_count",
    "latency_ms", "rewrite_query", "degraded_reason",
}


def _read_events(raw: str) -> list[tuple[str, dict]]:
    out = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):].strip()
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if event is not None:
            out.append((event, data))
    return out


def _fake_user():
    async def _u():
        return UserInfo(
            user_id=2, nickname="stu", real_name="stu",
            mobile=None, email="stu@e.a", gender=None, avatar_url=None,
            role=UserRole.STUDENT,
        )
    return _u


async def _client_post(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/chat/stream", json={"query": "你好", "use_mcp_tools": False})
        assert resp.status_code == 200, resp.text[:300]
        return _read_events(resp.text)


def _assert_frame_envelope(events: list[tuple[str, dict]]) -> None:
    """对帧序列做信封一致性断言（start/retrieval 裸、token=delta、done 带壳）。"""
    by_name: dict[str, list[dict]] = {}
    for name, data in events:
        by_name.setdefault(name, []).append(data)

    # 帧序：start → retrieval → token(n) → done，且无 error
    names = [n for n, _ in events]
    assert names[0] == SseEventType.START.value
    assert names[1] == SseEventType.RETRIEVAL_DONE.value
    assert names[-1] == SseEventType.DONE.value
    assert SseEventType.ERROR.value not in by_name

    # start 裸帧：键集合恰好 {session_id, query}，query 原样回显
    start = by_name[SseEventType.START.value][0]
    assert set(start.keys()) == START_KEYS, f"start 帧漂移：{set(start.keys())}"
    assert start["query"] == "你好"

    # retrieval 裸帧：7 键，不带统一壳 code/message
    retrieval = by_name[SseEventType.RETRIEVAL_DONE.value][0]
    assert set(retrieval.keys()) == RETRIEVAL_KEYS, f"retrieval 帧漂移：{set(retrieval.keys())}"
    assert "code" not in retrieval and "message" not in retrieval

    # token 裸帧：每帧恰好 {"delta": 非空串}；拼接即最终答案
    tokens = by_name[SseEventType.TOKEN.value]
    assert tokens, "至少应有一个 token 帧"
    for tk in tokens:
        assert set(tk.keys()) == TOKEN_KEYS, f"token 帧漂移（期望仅 delta）：{set(tk.keys())}"
        assert isinstance(tk["delta"], str) and tk["delta"]
    assert "".join(tk["delta"] for tk in tokens) == "你好"

    # done 唯一带信封帧：顶层恰好 code/message/data，data 为最终产物
    done = by_name[SseEventType.DONE.value][0]
    assert set(done.keys()) == DONE_TOP_KEYS
    assert done["code"] == 0 and done["message"] == "ok"
    assert DONE_DATA_KEYS <= set(done["data"].keys()), f"done.data 漂移：{set(done['data'].keys())}"


# ============================================================
# 路径 A：旧路径（STREAM_VIA_GRAPH=False → service_chat_stream）
# ============================================================
async def test_old_path_envelope_shapes(monkeypatch):
    async def _token_gen():
        yield "你"
        yield "好"

    async def _finalize(answer_text, *, degraded_extra=None):
        return {
            "session_id": None, "message_id": "m_old",
            "retrieved_count": 0, "final_count": 0, "latency_ms": 12,
            "rewrite_query": "你好", "degraded_reason": None,
        }

    async def _fake_service(req, *, user_id, role):
        bundle = types.SimpleNamespace(
            docs=[], graph_entities=[], raw_retrieved_count=0,
            rewrite_query="你好", degraded_reason=None,
        )
        return None, bundle, [], _token_gen(), _finalize, []

    monkeypatch.setattr(chat_router, "service_chat_stream", _fake_service)
    monkeypatch.setattr(settings, "STREAM_VIA_GRAPH", False)

    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[chat_router.get_current_user] = _fake_user()
    _assert_frame_envelope(await _client_post(app))


# ============================================================
# 路径 B：默认图路径（STREAM_VIA_GRAPH=True → flows/graph_stream.graph_stream_sse）
# 用桩替换会话校验/图执行/guard/MCP/finalize，但 SSE 帧由真实 graph_stream 产生
# ============================================================
async def test_graph_path_envelope_shapes(monkeypatch):
    monkeypatch.setattr(settings, "STREAM_VIA_GRAPH", True)

    async def _fake_ensure_owner(session_id, user_id, role):
        return None

    async def _fake_run_mcp(query, operator_user_id, session_id, use_mcp_flag):
        return [], "", None

    def _fake_finalize_factory(**kwargs):
        async def _finalize(answer_text, *, degraded_extra=None):
            return {
                "session_id": None, "message_id": "m_graph",
                "retrieved_count": 0, "final_count": 0, "latency_ms": 9,
                "rewrite_query": "你好", "degraded_reason": None,
            }
        return _finalize

    class _FakeGraph:
        async def astream(self, state, config, stream_mode=None):
            yield ("updates", {"fan_out": {"retrieval": {
                "docs": [], "graph_entities": [], "retrieved_count": 0,
                "rewrite_query": "你好", "degraded_reason": None,
            }}})
            yield ("custom", {"type": "token", "delta": "你"})
            yield ("custom", {"type": "token", "delta": "好"})

    async def _fake_ensure_graph():
        return _FakeGraph()

    class _FakeGuard:
        async def acquire(self, uid, request_meta=None):
            return {"ok": True, "message": None, "reason": None}

        async def release(self, uid):
            return None

    monkeypatch.setattr(gs, "_ensure_session_owner", _fake_ensure_owner)
    monkeypatch.setattr(gs, "resolve_thread_id", lambda *a, **k: "f3-thread")
    monkeypatch.setattr(gs, "_empty_state", lambda query, user_id, session_id: {"query": query})
    monkeypatch.setattr(gs, "_ensure_agent_graph", _fake_ensure_graph)
    monkeypatch.setattr(gs, "make_stream_finalize", _fake_finalize_factory)
    monkeypatch.setattr("app.ai.guard.default_guard", lambda: _FakeGuard())
    monkeypatch.setattr("app.chat.tool_calling.run_chat_tool_calls", _fake_run_mcp)

    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[chat_router.get_current_user] = _fake_user()
    _assert_frame_envelope(await _client_post(app))


# ============================================================
# 原语：sse_line 线格式 + error 帧也是裸帧（不套统一壳）
# ============================================================
def test_sse_line_wire_format_and_utf8():
    raw = chat_sse.sse_line(SseEventType.START.value, {"session_id": None, "query": "你好"})
    assert raw == (
        'event: start\n'
        'data: {"session_id": null, "query": "你好"}\n\n'
    ).encode("utf-8"), "SSE 帧线格式/ensure_ascii=False 漂移"


def test_error_frame_is_naked_not_enveloped():
    raw = chat_sse.sse_line(SseEventType.ERROR.value, {"code": "LLM_TIMEOUT", "message": "超时"})
    event, payload = _read_events(raw.decode("utf-8"))[0]
    assert event == "error"
    assert set(payload.keys()) == {"code", "message"}  # 非 {code,message,data} 壳
    assert payload["code"] == "LLM_TIMEOUT" and payload["message"]
