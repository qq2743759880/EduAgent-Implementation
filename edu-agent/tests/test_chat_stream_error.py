# -*- coding: utf-8 -*-
"""
W2 批判 C3 契约测试：流式 SSE 错误通道统一（router._map_stream_exception / token 段 / 落库段）。

验证目标（C-B SSE 契约外形不变，仅错误语义从静默→显式）：
  (a) 正常 token 流：start → retrieval → token → done，且 done 壳仍 {code:0, message:"ok", data:{...}}
  (b) 注入 token 迭代失败 → 流内 `event: error`，code 为可区分码（非固定 50000）
  (c) 注入落库失败（build_finalize 抛错） → 流内 `event: error` code=CHAT_PERSIST_FAIL（非静默），
      且随带 generated_tokens / 降级 done 兜底（不再静默 degraded_reason）。

实现：用 httpx ASGITransport 打真实路由 + monkeypatch chat_router.service_chat_stream，
不依赖 live backend（LLM/MySQL 全 mock）。
"""
from __future__ import annotations

import json
import types

import httpx
import pytest
from fastapi import FastAPI

from app.auth.dependencies import UserInfo, UserRole
from app.chat import router as chat_router
from app.chat.schemas import SseEventType
from app.common.error_codes import (
    CHAT_PERSIST_FAIL,
    LLM_AUTH,
    LLM_RATE_LIMIT,
    LLM_TIMEOUT,
    LLM_UNAVAILABLE,
    SERVICE_DOWNSTREAM,
)


# ============================================================
# 工具
# ============================================================
def _make_bundle():
    return types.SimpleNamespace(
        docs=[],
        graph_entities=[],
        raw_retrieved_count=0,
        rewrite_query="hi",
        degraded_reason=None,
    )


async def _ok_finalize(answer_text, *, degraded_extra=None):
    return {
        "session_id": None,
        "message_id": "m_ok",
        "retrieved_count": 0,
        "final_count": 0,
        "latency_ms": 12,
        "rewrite_query": "hi",
        "degraded_reason": None,
    }


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


async def _post_stream(monkeypatch, token_aiter, build_finalize=_ok_finalize):
    async def _fake_service(req, *, user_id, role):
        return None, _make_bundle(), [], token_aiter, build_finalize, []

    monkeypatch.setattr(chat_router, "service_chat_stream", _fake_service)

    app = FastAPI()
    app.include_router(chat_router.router)

    async def _fake_user():
        return UserInfo(
            user_id=2, nickname="stu", real_name="stu",
            mobile=None, email="stu@e.a", gender=None, avatar_url=None,
            role=UserRole.STUDENT,
        )

    app.dependency_overrides[chat_router.get_current_user] = _fake_user

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/chat/stream", json={"query": "hi", "use_mcp_tools": False})
        assert resp.status_code == 200, resp.text[:300]
        return _read_events(resp.text)


async def _token_gen(*payloads):
    for p in payloads:
        yield p


# ============================================================
# (a) 正常 token 流：start→retrieval→token→done，done 壳 {code:0,message:"ok",data:{...}}
# ============================================================
@pytest.mark.asyncio
async def test_stream_normal_flow_done_shell(monkeypatch):
    events = await _post_stream(monkeypatch, _token_gen("你", "好", "！"))

    names = [e[0] for e in events]
    assert names[0] == SseEventType.START.value, f"首帧应为 start：{names}"
    assert names[1] == SseEventType.RETRIEVAL_DONE.value, f"次帧应为 retrieval：{names}"
    # START/RETRIEVAL 先行帧不可丢
    token_ids = [i for i, n in enumerate(names) if n == SseEventType.TOKEN.value]
    assert token_ids, f"应有 token 帧：{names}"
    assert names[token_ids[0]] == SseEventType.TOKEN.value
    assert all(names[i] != SseEventType.ERROR.value for i in range(len(names))), "正常流不应有 error"

    done = events[-1]
    assert done[0] == SseEventType.DONE.value
    assert done[1]["code"] == 0, f"done 壳 code 必须为 0（契约外形不变）：{done[1]}"
    assert done[1]["message"] == "ok"
    assert "data" in done[1] and isinstance(done[1]["data"], dict)

    # token 帧 delta 累加 == 最终 answer（落库用了 join(buf)）
    merged = "".join(d.get("delta", "") for e, d in events if e == SseEventType.TOKEN.value)
    assert merged == "你好！"


# ============================================================
# (b) 注入 token 迭代失败 → 流内 error，code 可区分（非 50000 单调）
# ============================================================
@pytest.mark.asyncio
async def test_stream_token_error_maps_auth_code(monkeypatch):
    async def _fail_gen():
        yield "前半"
        raise RuntimeError("LLM HTTP 401: invalid api key")

    events = await _post_stream(monkeypatch, _fail_gen())

    err = [(e, d) for e, d in events if e == SseEventType.ERROR.value]
    assert err, f"应有流内 error 事件：{[e[0] for e in events]}"
    code = err[-1][1]["code"]
    assert code == LLM_AUTH, f"HTTP 401 应映射 LLM_AUTH={LLM_AUTH}，实际 {code}"
    assert code != "50000", "错误码不得再是固定 50000 单调"
    assert "message" in err[-1][1] and err[-1][1]["message"]
    # START/RETRIEVAL 仍在 error 之前发出，未丢帧
    names = [e[0] for e in events]
    error_idx = names.index(SseEventType.ERROR.value)
    assert names[:2] == [SseEventType.START.value, SseEventType.RETRIEVAL_DONE.value]


@pytest.mark.asyncio
async def test_stream_token_error_maps_timeout(monkeypatch):
    async def _fail_gen():
        yield "a"
        raise TimeoutError("LLM stream 60s 无增量，超时降级")

    events = await _post_stream(monkeypatch, _fail_gen())
    err = [(e, d) for e, d in events if e == SseEventType.ERROR.value]
    assert err and err[-1][1]["code"] == LLM_TIMEOUT


# ============================================================
# (b2) _map_stream_exception 映射表（纯单元，覆盖全部分支）
# ============================================================
def test_map_stream_exception_table():
    cases = [
        (TimeoutError("timeout"), LLM_TIMEOUT),
        (TimeoutError("60s 无增量"), LLM_TIMEOUT),
        (RuntimeError("LLM HTTP 401: bad key"), LLM_AUTH),
        (RuntimeError("LLM HTTP 403: forbidden"), LLM_AUTH),
        (RuntimeError("LLM HTTP 429: rate limited"), LLM_RATE_LIMIT),
        (RuntimeError("LLM HTTP 503: upstream down"), LLM_UNAVAILABLE),
        (ConnectionError("failed to connect to api"), LLM_UNAVAILABLE),
        (RuntimeError("unexpected downstream"), SERVICE_DOWNSTREAM),
    ]
    for exc, expected in cases:
        code, msg = chat_router._map_stream_exception(exc)
        assert code == expected, f"{exc!r} → {code}，期望 {expected}"
        assert msg
    # 任一错误码都不得是固定 50000
    for exc, _ in cases:
        code, _ = chat_router._map_stream_exception(exc)
        assert code != "50000"


# ============================================================
# (c) 注入落库失败 → 流内 error code=CHAT_PERSIST_FAIL（非静默）+ 降级 done 兜底
# ============================================================
@pytest.mark.asyncio
async def test_stream_persist_fail_emits_error_not_silent(monkeypatch):
    async def _fail_finalize(answer_text, *, degraded_extra=None):
        raise RuntimeError("mysql connection lost")

    events = await _post_stream(monkeypatch, _token_gen("答", "案"), build_finalize=_fail_finalize)

    err = [(e, d) for e, d in events if e == SseEventType.ERROR.value]
    assert err, "落库失败必须显式发 error（不得静默）"
    assert err[-1][1]["code"] == CHAT_PERSIST_FAIL
    assert err[-1][1]["generated_tokens"] == 2, "error 应回传已生成 token 计数"
    assert err[-1][1]["message_id"] is None

    # 兜底：随后一个带 degraded 的 done 做正常收束（不静默），done 壳外形仍 code:0
    done = [(e, d) for e, d in events if e == SseEventType.DONE.value]
    assert done, "落库失败后应有降级 done 兜底"
    assert done[-1][1]["code"] == 0
    assert done[-1][1]["data"]["degraded_reason"] and "落库失败" in done[-1][1]["data"]["degraded_reason"]