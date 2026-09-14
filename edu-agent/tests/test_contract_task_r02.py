# -*- coding: utf-8 -*-
"""R02 流式主路径进 LangGraph 契约测试（dev-plan-reshape-r W2）。

覆盖四件套验收面：
  1. 执行体切换：STREAM_VIA_GRAPH 开关分发（True→graph.astream 适配层；False→一键回旧路径）；
     图路径 SSE 五事件契约（start→retrieval→token→done/error，token delta 累加，done 壳 code:0）。
  2. guard 移植：流式路径 acquire/release 成对覆盖（含图执行异常路径）；Redis 槽 TTL 自愈
     （Lua 含 EXPIRE + GUARD_SLOT_TTL 参数）。
  3. thread_id（R02-c）：匿名请求独立 anon-{uuid} 线程，禁 task24-{user_id} 共享；
     GWT=同用户两笔匿名请求 checkpoint 线程键不同。
  4. 检索参数对齐：sixnode_retrieval_params() 默认对齐旧路径生产现值（hyde=True/top_k=12/5/0.40）；
     图内 search_knowledge 服务传参对齐 + retrieval capture 回填；run_agent 空 docs 修复（P1-5）。
  附：P2-9 chat_answer plan 作用域修复（USE_AGENT_LOOP=False 不再 UnboundLocalError）。

实现：httpx ASGITransport 打真实路由 + monkeypatch（不依赖 live backend/LLM/MySQL）。
"""
from __future__ import annotations

import json
import types

import httpx
import pytest
from fastapi import FastAPI

from app.ai import graph as ai_graph
from app.ai import guard as guard_mod
from app.chat import router as chat_router
from app.chat.flows import graph_stream as gs_mod
from app.chat.schemas import SseEventType
from app.common.error_codes import LLM_AUTH
from app.config import settings


# ============================================================
# 工具
# ============================================================
def _read_events(raw: str) -> list[tuple[str, dict]]:
    """把 SSE 文本解析为 [(event, data_dict), ...]。"""
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


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(chat_router.router)

    async def _fake_user():
        from app.auth.dependencies import UserInfo, UserRole

        return UserInfo(
            user_id=2, nickname="stu", real_name="stu",
            mobile=None, email="stu@e.a", gender=None, avatar_url=None,
            role=UserRole.STUDENT,
        )

    app.dependency_overrides[chat_router.get_current_user] = _fake_user
    return app


async def _post_stream(client: httpx.AsyncClient, payload: dict) -> list[tuple[str, dict]]:
    resp = await client.post("/api/chat/stream", json=payload)
    assert resp.status_code == 200, resp.text[:300]
    return _read_events(resp.text)


class SpyGuard:
    """guard 间谍：记录 acquire/release 配对。"""

    def __init__(self, *, ok: bool = True):
        self.ok = ok
        self.acquires = 0
        self.releases = 0
        self.request_metas = []

    async def acquire(self, user_id, *, request_meta=None, **kw):
        self.acquires += 1
        self.request_metas.append(request_meta)
        return {"ok": self.ok, "reason": "direct" if self.ok else "user_concurrent_over_limit",
                **({} if self.ok else {"message": "并发已达上限", "reason": "user_concurrent_over_limit"})}

    async def release(self, user_id):
        self.releases += 1


class FakeGraph:
    """假编译图：按脚本回放 (mode, payload) 流，记录 state/config。"""

    def __init__(self, events, *, raise_at=None):
        self._events = events
        self._raise_at = raise_at
        self.captured_states = []
        self.captured_configs = []

    async def astream(self, state, config, stream_mode=None):
        self.captured_states.append(dict(state))
        self.captured_configs.append(json.loads(json.dumps(config, default=str)))
        for i, (m, p) in enumerate(self._events):
            if self._raise_at is not None and i == self._raise_at:
                raise RuntimeError("LLM HTTP 401: invalid api key")
            yield (m, p)


@pytest.fixture()
def no_db_writes(monkeypatch):
    """隔离落库副作用：审计日志 no-op + 记忆 ingest no-op（graph_stream 收束路径）。"""

    async def _noop_audit(**kw):
        return None

    async def _noop_enqueue(*a, **k):
        return None

    import app.ai.memory.service as memsvc

    monkeypatch.setattr("app.chat.service._rag_insert_audit_log", _noop_audit)
    monkeypatch.setattr(memsvc, "enqueue_turn", _noop_enqueue)
    return True


# ============================================================
# 1) 执行体切换：开关分发
# ============================================================
@pytest.mark.asyncio
async def test_switch_on_routes_to_graph_adapter(monkeypatch, no_db_writes):
    """STREAM_VIA_GRAPH=True（默认）→ 走 graph_stream_sse，不走旧 service_chat_stream。"""
    monkeypatch.setattr(settings, "STREAM_VIA_GRAPH", True)
    called = {"graph": 0, "old": 0}

    async def _fake_graph_sse(req, *, user_id, role):
        called["graph"] += 1

        async def _gen():
            yield b"event: start\ndata: {}\n\n"
        from fastapi.responses import StreamingResponse
        return StreamingResponse(_gen(), media_type="text/event-stream")

    async def _old(req, *, user_id, role):
        called["old"] += 1
        return None, types.SimpleNamespace(docs=[], graph_entities=[], raw_retrieved_count=0,
                                           rewrite_query=None, degraded_reason=None), [], iter([]), None, []

    monkeypatch.setattr(gs_mod, "graph_stream_sse", _fake_graph_sse)
    monkeypatch.setattr(chat_router, "service_chat_stream", _old)

    app = _make_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/chat/stream", json={"query": "hi"})
    assert called["graph"] == 1 and called["old"] == 0


@pytest.mark.asyncio
async def test_switch_off_falls_back_to_legacy_path(monkeypatch, no_db_writes):
    """STREAM_VIA_GRAPH=False → 一键回旧路径（回退开关，行为等同历史版本）。"""
    monkeypatch.setattr(settings, "STREAM_VIA_GRAPH", False)
    called = {"graph": 0, "old": 0}

    async def _fake_graph_sse(req, *, user_id, role):
        called["graph"] += 1
        raise AssertionError("开关关闭时不得进入图适配层")

    async def _old(req, *, user_id, role):
        called["old"] += 1

        async def _tokens():
            yield "旧"
            yield "路径"

        async def _finalize(answer_text, *, degraded_extra=None):
            return {"session_id": None, "message_id": "m1", "retrieved_count": 0,
                    "final_count": 0, "latency_ms": 1, "rewrite_query": None,
                    "degraded_reason": None, "mcp_tool_calls": []}

        bundle = types.SimpleNamespace(docs=[], graph_entities=[], raw_retrieved_count=0,
                                       rewrite_query=None, degraded_reason=None)
        return None, bundle, [], _tokens(), _finalize, []

    monkeypatch.setattr(gs_mod, "graph_stream_sse", _fake_graph_sse)
    monkeypatch.setattr(chat_router, "service_chat_stream", _old)

    app = _make_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        events = await _post_stream(client, {"query": "hi"})
    assert called["old"] == 1 and called["graph"] == 0
    names = [e[0] for e in events]
    assert names[0] == SseEventType.START.value and names[-1] == SseEventType.DONE.value
    merged = "".join(d.get("delta", "") for ev, d in events if ev == SseEventType.TOKEN.value)
    assert merged == "旧路径"


# ============================================================
# 2) 图路径 SSE 契约（start→retrieval→token→done；delta 累加；done 壳）
# ============================================================
@pytest.mark.asyncio
async def test_graph_stream_sse_contract_knowledge_flow(monkeypatch, no_db_writes):
    """knowledge 流：route→fan_out(检索)→answer(token 流) → 帧序与字段契约。"""
    fake = FakeGraph([
        ("updates", {"route": {"intent": "knowledge", "effort": "L1", "nodes_executed": ["route"]}}),
        ("updates", {"skill": {"skill_context": "", "nodes_executed": ["route", "skill"]}}),
        ("updates", {"fan_out": {
            "subagent_results": [], "degraded_reason": None, "nodes_executed": ["route", "fan_out"],
            "retrieval": {
                "docs": [{"doc_id": "c1", "score": 0.9, "content": "片段"}],
                "graph_entities": [],
                "retrieved_count": 7,
                "rewrite_query": "改写后的query",
                "degraded_reason": None,
            },
        }}),
        ("custom", {"type": "token", "delta": "检索"}),
        ("custom", {"type": "token", "delta": "结果："}),
        ("custom", {"type": "token", "delta": "A"}),
        ("updates", {"answer": {"final_answer": "检索结果：A", "degraded_reason": None,
                                "nodes_executed": ["route", "answer"]}}),
    ])
    spy = SpyGuard()
    monkeypatch.setattr(guard_mod, "default_guard", lambda: spy)

    async def _fake_graph():
        return fake

    monkeypatch.setattr(gs_mod, "_ensure_agent_graph", _fake_graph)

    app = _make_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        events = await _post_stream(client, {"query": "什么是特征值", "session_id": None})

    names = [e[0] for e in events]
    # 帧序契约：start → retrieval → token… → done（retrieval 先于 token）
    assert names[0] == SseEventType.START.value
    assert names[1] == SseEventType.RETRIEVAL_DONE.value
    assert SseEventType.TOKEN.value in names
    assert names[-1] == SseEventType.DONE.value
    assert SseEventType.ERROR.value not in names

    start = events[0][1]
    assert start["session_id"] is None and start["query"] == "什么是特征值"

    ret = events[1][1]
    assert [d["doc_id"] for d in ret["docs"]] == ["c1"]
    assert ret["retrieved_count"] == 7 and ret["final_count"] == 1
    assert ret["rewrite_query"] == "改写后的query"
    assert "mcp_tool_calls" in ret  # 契约字段保持

    merged = "".join(d.get("delta", "") for ev, d in events if ev == SseEventType.TOKEN.value)
    assert merged == "检索结果：A", f"token delta 累加语义（j.delta）必须保持：{merged!r}"

    done = events[-1][1]
    assert done["code"] == 0 and done["message"] == "ok"
    assert done["data"]["final_count"] == 1 and done["data"]["retrieved_count"] == 7
    assert "latency_ms" in done["data"] and "degraded_reason" in done["data"]

    # guard 覆盖：acquire/release 各一次（成对）
    assert spy.acquires == 1 and spy.releases == 1
    # thread_id：匿名请求独立 anon-{uuid}，且经 configurable 传给图（stream_tokens 门控开）
    tid = fake.captured_configs[0]["configurable"]["thread_id"]
    assert tid.startswith("anon-") and "task24-" not in tid
    assert fake.captured_configs[0]["configurable"]["stream_tokens"] is True
    # 初始 state 只含当前 query（不串其他请求历史）
    assert fake.captured_states[0]["user_id"] == 2


@pytest.mark.asyncio
async def test_graph_stream_chitchat_emits_empty_retrieval_frame(monkeypatch, no_db_writes):
    """chitchat 直连（route→answer）：按旧路径口径发空 docs retrieval 帧后再流 token。"""
    fake = FakeGraph([
        ("updates", {"route": {"intent": "chitchat", "effort": "L0", "nodes_executed": ["route"]}}),
        ("custom", {"type": "token", "delta": "你"}),
        ("custom", {"type": "token", "delta": "好"}),
        ("updates", {"answer": {"final_answer": "你好", "degraded_reason": None, "nodes_executed": ["route", "answer"]}}),
    ])
    monkeypatch.setattr(guard_mod, "default_guard", lambda: SpyGuard())

    async def _fake_graph2():
        return fake

    monkeypatch.setattr(gs_mod, "_ensure_agent_graph", _fake_graph2)

    app = _make_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        events = await _post_stream(client, {"query": "你好呀"})
    names = [e[0] for e in events]
    assert names[:2] == [SseEventType.START.value, SseEventType.RETRIEVAL_DONE.value]
    ret = events[1][1]
    assert ret["docs"] == [] and ret["retrieved_count"] == 0
    merged = "".join(d.get("delta", "") for ev, d in events if ev == SseEventType.TOKEN.value)
    assert merged == "你好"


@pytest.mark.asyncio
async def test_graph_stream_token_before_retrieval_keeps_frame_order(monkeypatch, no_db_writes):
    """token 先于 retrieval 帧到达（如 MCP 慢）→ 缓冲重放，帧序契约不破。"""
    fake = FakeGraph([
        ("updates", {"route": {"intent": "knowledge", "effort": "L1", "nodes_executed": ["route"]}}),
        ("custom", {"type": "token", "delta": "早"}),  # fan_out 更新前到达的 token（异常序列）
        ("updates", {"fan_out": {"subagent_results": [], "degraded_reason": None,
                                 "nodes_executed": ["route", "fan_out"],
                                 "retrieval": {"docs": [], "graph_entities": [], "retrieved_count": 0,
                                               "rewrite_query": None, "degraded_reason": None}}}),
        ("custom", {"type": "token", "delta": "到"}),
        ("updates", {"answer": {"final_answer": "早到", "degraded_reason": None, "nodes_executed": ["route", "answer"]}}),
    ])
    monkeypatch.setattr(guard_mod, "default_guard", lambda: SpyGuard())

    async def _fake_graph3():
        return fake

    monkeypatch.setattr(gs_mod, "_ensure_agent_graph", _fake_graph3)

    app = _make_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        events = await _post_stream(client, {"query": "q"})
    names = [e[0] for e in events]
    assert names.index(SseEventType.RETRIEVAL_DONE.value) < names.index(SseEventType.TOKEN.value)
    merged = "".join(d.get("delta", "") for ev, d in events if ev == SseEventType.TOKEN.value)
    assert merged == "早到", "缓冲 token 必须按序重放，不丢不乱"


@pytest.mark.asyncio
async def test_graph_stream_flushes_state_answer_when_no_custom_tokens(monkeypatch, no_db_writes):
    """answer 节点静默回退阻塞生成（无 custom token）→ 适配层把 final_answer 补发为 token 帧。"""
    fake = FakeGraph([
        ("updates", {"route": {"intent": "knowledge", "effort": "L1", "nodes_executed": ["route"]}}),
        ("updates", {"fan_out": {"subagent_results": [], "degraded_reason": None,
                                 "nodes_executed": ["route", "fan_out"],
                                 "retrieval": {"docs": [], "graph_entities": [], "retrieved_count": 0,
                                               "rewrite_query": None, "degraded_reason": None}}}),
        # 无任何 ("custom", {...token...}) 事件：模拟 answer 节点回退阻塞生成
        ("updates", {"answer": {"final_answer": "阻塞兜底答案", "degraded_reason": "llm_stream_fallback",
                                "nodes_executed": ["route", "answer"]}}),
    ])
    monkeypatch.setattr(guard_mod, "default_guard", lambda: SpyGuard())

    async def _fake_graph5():
        return fake

    monkeypatch.setattr(gs_mod, "_ensure_agent_graph", _fake_graph5)

    app = _make_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        events = await _post_stream(client, {"query": "q"})
    merged = "".join(d.get("delta", "") for ev, d in events if ev == SseEventType.TOKEN.value)
    assert merged == "阻塞兜底答案", f"状态内 final_answer 必须补发为 token（实际 {merged!r}）"
    assert events[-1][0] == SseEventType.DONE.value


@pytest.mark.asyncio
async def test_graph_stream_error_maps_codes(monkeypatch, no_db_writes):
    """图执行中途异常 → 流内 error 帧可区分错误码（LLM_AUTH），guard 仍 release（成对）。"""
    fake = FakeGraph([
        ("updates", {"route": {"intent": "knowledge", "effort": "L1", "nodes_executed": ["route"]}}),
    ], raise_at=0)
    spy = SpyGuard()
    monkeypatch.setattr(guard_mod, "default_guard", lambda: spy)

    async def _fake_graph4():
        return fake

    monkeypatch.setattr(gs_mod, "_ensure_agent_graph", _fake_graph4)

    app = _make_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        events = await _post_stream(client, {"query": "q"})
    err = [(e, d) for e, d in events if e == SseEventType.ERROR.value]
    assert err, "应发流内 error"
    assert err[-1][1]["code"] == LLM_AUTH, f"HTTP 401 特征必须映射 LLM_AUTH（实际 {err[-1][1]['code']}）"
    assert err[-1][1]["message"]
    assert spy.acquires == 1 and spy.releases == 1, "异常路径 guard 必须成对 release"


@pytest.mark.asyncio
async def test_graph_stream_guard_reject_streams_busy_answer(monkeypatch, no_db_writes):
    """guard 拒绝：友好提示作为答案流出 + degraded_reason（与 graph.run_agent 拒绝语义一致）。"""
    spy = SpyGuard(ok=False)
    monkeypatch.setattr(guard_mod, "default_guard", lambda: spy)

    app = _make_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        events = await _post_stream(client, {"query": "q"})

    names = [e[0] for e in events]
    assert names[:2] == [SseEventType.START.value, SseEventType.RETRIEVAL_DONE.value]
    assert names[-1] == SseEventType.DONE.value
    merged = "".join(d.get("delta", "") for ev, d in events if ev == SseEventType.TOKEN.value)
    assert merged, "拒绝提示应作为 token 流出"
    done = events[-1][1]
    assert done["code"] == 0 and done["data"]["degraded_reason"] == "user_concurrent_over_limit"
    assert spy.acquires == 1 and spy.releases == 0, "拒绝=未持有闸位，不 release"


# ============================================================
# 3) thread_id 修复（R02-c / audit P2-8）
# ============================================================
def test_resolve_thread_id_anonymous_isolated():
    """GWT：同用户两笔匿名请求 checkpoint 线程键不同，互不可见对方历史。"""
    t1 = ai_graph.resolve_thread_id(None, 7)
    t2 = ai_graph.resolve_thread_id(None, 7)
    assert t1 != t2, "匿名请求必须每请求独立 thread_id"
    assert t1.startswith("anon-") and t2.startswith("anon-")
    assert "task24-" not in t1 + t2, "禁 task24-{user_id} 共享线程"


def test_resolve_thread_id_session_reused():
    assert ai_graph.resolve_thread_id("s_abc123", 7) == "s_abc123"


@pytest.mark.asyncio
async def test_run_agent_anonymous_requests_get_distinct_checkpoint_threads(monkeypatch):
    """run_agent：两笔同用户匿名请求 → 图收到不同 thread_id（checkpoint 键不同）。"""
    tids = []

    class _CapGraph:
        async def ainvoke(self, state, config):
            tids.append(config["configurable"]["thread_id"])
            return {"final_answer": "x", "intent": "knowledge", "nodes_executed": ["route"]}

    async def _fake_graph():
        return _CapGraph()

    monkeypatch.setattr(ai_graph, "_ensure_agent_graph", _fake_graph)
    monkeypatch.setattr(guard_mod, "default_guard", lambda: SpyGuard())

    await ai_graph.run_agent("q1", user_id=7, session_id=None)
    await ai_graph.run_agent("q2", user_id=7, session_id=None)
    assert len(set(tids)) == 2, f"两笔匿名请求 checkpoint 线程必须不同：{tids}"
    assert all(t.startswith("anon-") for t in tids)

    await ai_graph.run_agent("q3", user_id=7, session_id="s_fixed")
    assert tids[-1] == "s_fixed"


# ============================================================
# 4) 检索参数对齐 + run_agent 空 docs 修复（P1-5）
# ============================================================
def test_sixnode_retrieval_params_align_legacy_defaults():
    """图内检索参数默认对齐旧路径生产现值（R20-b 根因修复）。"""
    params = ai_graph.sixnode_retrieval_params()
    assert params == {"use_hyde": True, "enable_graph": True, "top_k": 12,
                      "final_max_k": 5, "cutoff_drop_ratio": 0.40}
    # 与请求 schema 生产默认逐项对齐（_BaseRagRequest）
    from app.chat.schemas import RagSearchOnlyRequest
    base = RagSearchOnlyRequest(query="x")
    assert params["use_hyde"] == base.use_hyde
    assert params["top_k"] == base.top_k
    assert params["final_max_k"] == base.final_max_k
    assert params["cutoff_drop_ratio"] == base.cutoff_drop_ratio
    assert params["enable_graph"] == base.enable_graph


@pytest.mark.asyncio
async def test_search_knowledge_service_uses_aligned_params_and_captures(monkeypatch):
    """图内 search_knowledge 工具服务：传参对齐 + retrieval capture 回填。"""
    captured_kwargs = {}

    class _Doc:
        def __init__(self, i):
            self._i = i

        def model_dump(self):
            return {"doc_id": f"c{self._i}"}

    class _Bundle:
        docs = [_Doc(1), _Doc(2)]
        graph_entities: list = []
        raw_retrieved_count = 9
        rewrite_query = "rw"
        degraded_reason = None

    async def _spy(query, **kwargs):
        captured_kwargs["query"] = query
        captured_kwargs.update(kwargs)
        return _Bundle()

    import app.chat.retriever as ret_mod
    monkeypatch.setattr(ret_mod, "retrieve_three_channel", _spy)

    capture: dict = {}
    services = ai_graph._build_tool_services(user_id=5, thread_id="t", capture=capture)
    out = await services["search_knowledge"]({"q": "测试问题"})

    assert captured_kwargs["use_hyde"] is True
    assert captured_kwargs["top_k"] == 12
    assert captured_kwargs["final_max_k"] == 5
    assert captured_kwargs["cutoff_drop_ratio"] == 0.40
    assert captured_kwargs["role"] is None  # 学员租户范围（不扩大搜索，R4 红线）
    assert [d["doc_id"] for d in out["docs"]] == ["c1", "c2"]
    assert capture["retrieval"]["retrieved_count"] == 9
    assert capture["retrieval"]["rewrite_query"] == "rw"


@pytest.mark.asyncio
async def test_run_agent_backfills_docs_from_graph_state(monkeypatch):
    """run_agent 返回体 docs/graph_entities 从图终态 retrieval 真实回填（P1-5 修复）。"""

    class _CapGraph:
        async def ainvoke(self, state, config):
            return {
                "final_answer": "答",
                "intent": "knowledge",
                "retrieval": {
                    "docs": [{"doc_id": "c1", "score": 0.9}],
                    "graph_entities": [{"entity_name": "特征值", "entity_type": "Keyword"}],
                    "retrieved_count": 5,
                },
                "nodes_executed": ["route", "fan_out", "answer"],
            }

    async def _fake_graph():
        return _CapGraph()

    monkeypatch.setattr(ai_graph, "_ensure_agent_graph", _fake_graph)
    monkeypatch.setattr(guard_mod, "default_guard", lambda: SpyGuard())

    res = await ai_graph.run_agent("q", user_id=7, session_id=None)
    assert res["docs"] == [{"doc_id": "c1", "score": 0.9}], "docs 不得再恒为空（P1-5）"
    assert res["graph_entities"] == [{"entity_name": "特征值", "entity_type": "Keyword"}]
    assert res["thread_id"].startswith("anon-")


# ============================================================
# 5) guard TTL 自愈（R20-b 崩溃残留槽缺陷）
# ============================================================
@pytest.mark.asyncio
async def test_guard_redis_slots_carry_ttl(monkeypatch):
    """Redis 并发槽（用户槽+全局闸）原子脚本必须带 EXPIRE 自愈 + GUARD_SLOT_TTL 参数。"""

    class FakeRedis:
        def __init__(self):
            self.eval_calls = []

        async def eval(self, script, numkeys, key, *args):
            self.eval_calls.append({"script": script, "key": key, "args": args})
            return 1

    fake = FakeRedis()
    guard = guard_mod.ConcurrencyGuard(redis=fake, global_limit=8, user_max=2)

    ok = await guard.acquire_user_slot(42)
    assert ok
    user_call = fake.eval_calls[-1]
    assert "EXPIRE" in user_call["script"], "用户槽脚本必须含 EXPIRE（崩溃残留自愈）"
    assert user_call["key"] == f"{settings.CONCURRENT_KEY_PREFIX}:42"
    assert int(user_call["args"][1]) == int(settings.GUARD_SLOT_TTL)

    fake.eval_calls.clear()
    await guard._try_gate_locked()
    gate_call = fake.eval_calls[-1]
    assert "EXPIRE" in gate_call["script"], "全局闸脚本必须含 EXPIRE"
    assert gate_call["key"] == settings.GLOBAL_CONCURRENT_KEY
    assert int(gate_call["args"][0]) == 8
    assert int(gate_call["args"][1]) == int(settings.GUARD_SLOT_TTL)


@pytest.mark.asyncio
async def test_guard_ttl_heals_stale_slot(monkeypatch, fakeredis=None):
    """真 Redis（可用时）：残留槽值在 TTL 到期后自愈；Redis 不可用则跳过。"""
    try:
        import redis.asyncio as aioredis

        # settings.REDIS_URL 已在 pydantic validator 归一 localhost→127.0.0.1（task39 口径）
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
    except Exception:
        pytest.skip("Redis 不可用（本地开发降级路径），TTL 集成实证由 8010 实例承担")

    key = f"{settings.CONCURRENT_KEY_PREFIX}:999999"
    await r.delete(key)
    # 模拟旧代码崩溃残留：值=2（=上限）且无 TTL
    await r.set(key, 2)
    guard = guard_mod.ConcurrencyGuard(redis=r, user_max=2)
    ok = await guard.acquire_user_slot(999999)
    assert not ok, "残留槽满时仍应拒绝（上限语义不破）"
    ttl = await r.ttl(key)
    await r.delete(key)
    assert 0 < ttl <= int(settings.GUARD_SLOT_TTL), f"拒绝路径也应刷新 TTL 自愈（实际 ttl={ttl}）"


# ============================================================
# 6) P2-9：chat_answer plan 作用域（USE_AGENT_LOOP=False 不再 UnboundLocalError）
# ============================================================
@pytest.mark.asyncio
async def test_chat_answer_use_agent_loop_false_no_unbound_local(monkeypatch):
    from app.chat import service as svc
    from app.chat.retriever import RetrievalBundle

    monkeypatch.setattr(settings, "USE_AGENT_LOOP", False)

    async def _fake_bundle(req, *, user_id, role):
        return RetrievalBundle(docs=[], raw_retrieved_count=0, graph_entities=[],
                               rewrite_query=None, degraded_reason=None)

    async def _fake_mcp(*a, **k):
        return [], "", None

    async def _fake_gen(**kw):
        return "回退答案", None

    async def _noop_audit(**kw):
        return None

    monkeypatch.setattr(svc, "_retrieve_and_bundle_for_chat", _fake_bundle)
    monkeypatch.setattr(svc, "run_chat_tool_calls", _fake_mcp)
    monkeypatch.setattr(svc, "generate_answer", _fake_gen)
    monkeypatch.setattr(svc, "_rag_insert_audit_log", _noop_audit)

    req = types.SimpleNamespace(
        query="q", session_id=None, use_hyde=True, top_k=12, final_max_k=5,
        cutoff_drop_ratio=0.4, enable_graph=True, use_mcp_tools=False, model="fast",
        include_history=0,
    )
    resp = await svc.chat_answer(req, user_id=2, role=svc.UserRole.STUDENT)
    assert resp.answer == "回退答案"
