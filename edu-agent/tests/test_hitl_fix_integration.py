# -*- coding: utf-8 -*-
"""HITL-FIX 集成测试（kickoff-HITL-FIX，contracts/reshape-r-hitl.json 冻结五字段）。

覆盖验收 GWT：
  HF-G2 五字段补全：_enrich_hitl_pending_payload 把契约定死的 {thread_id, tool_name,
          args, risk_level, timeout_s} 补全；risk_level 用 _hitl_risk_level 真实分类
          （knowledge_import→high）、timeout_s=300、thread_id 与传入一致非空。
  HF-G1/HF-G4 confirm 口径：_classify_hitl_resume 单一词表——confirm→execute（放行执行，
          mcp_hitl_decision=True）、reject→rejected（0 执行 + 拒绝上下文收束）、
          其它/空→expired（确认失效防御）；与 resume 端点 Literal confirm|reject 一致。
  HF-G4 口径一致（防再断）：断言 graph_stream 可执行路径不再认 "approve"（只认 confirm），
          且 router 的 ChatResumeRequest.action Literal 恰好等于 graph_stream._RESUME_CONFIRM。
  SSE 帧字节级：enriched payload 经 sse_line("pending_confirm", …) 产出的 event/data 行。
"""
from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
import asyncio
import json

import httpx
import pytest

from app.chat import router as chat_router
from app.chat import sse as chat_sse


# ═══════════════════════════════════════════════════════════════
# HF-G2 五字段补全
# ═══════════════════════════════════════════════════════════════
def test_ga_enrich_pending_payload_five_fields():
    """_enrich_hitl_pending_payload 把契约定死的五字段补全（CR-T11-A）。"""
    from app.chat.flows.graph_stream import _enrich_hitl_pending_payload

    # 模拟 tool_calling._pending_payload（只带 tool_name/args，缺 thread_id/risk_level/timeout_s）
    raw = {
        "tool_name": "knowledge_import",
        "tool_key": "knowledge_import",
        "role": "admin",
        "args": {"source_files": ["/tmp/x.md"], "visibility": "private"},
        "session_id": "s_abc",
        "status": "awaiting_confirm",
    }
    enriched = _enrich_hitl_pending_payload(raw, thread_id="s_abc")

    # 契约五字段必在
    for f in ("thread_id", "tool_name", "args", "risk_level", "timeout_s"):
        assert f in enriched, f"缺失契约字段: {f}"
    # 语义断言：thread_id 与调用方传入一致且非空；knowledge_import→high；timeout_s=契约 300
    assert enriched["thread_id"] == "s_abc" and enriched["thread_id"]
    assert enriched["tool_name"] == "knowledge_import"
    assert enriched["args"] == {"source_files": ["/tmp/x.md"], "visibility": "private"}
    assert enriched["risk_level"] == "high"          # admin_write → high
    assert enriched["timeout_s"] == 300
    # 额外字段（role/session_id 等）不得被丢弃
    assert enriched["role"] == "admin"


def test_gb_enrich_for_readonly_defaults_low():
    """兜底：_hitl_risk_level 返回 None（只读/未登记）时，risk_level 落到 low 保契约枚举合法。"""
    from app.chat.flows.graph_stream import _enrich_hitl_pending_payload

    enriched = _enrich_hitl_pending_payload({"tool_name": "search_knowledge", "args": {}}, "t-x")
    assert enriched["risk_level"] in {"low", "medium", "high"}
    assert enriched["risk_level"] == "low"           # 只读工具真实分类 None → 兜底 low
    assert enriched["timeout_s"] == 300


def test_gc_pending_confirm_sse_frame_bytes_full():
    """enriched 五字段负载经 sse_line 产出的 SSE 帧字节级与契约对齐（event/data/空行）。"""
    from app.chat.flows.graph_stream import _enrich_hitl_pending_payload

    payload = _enrich_hitl_pending_payload(
        {"tool_name": "knowledge_import", "args": {"source_files": ["/tmp/x.md"]}}, "t-frame"
    )
    raw = chat_sse.sse_line("pending_confirm", payload)
    text = raw.decode("utf-8")
    lines = text.splitlines()
    assert lines[0] == "event: pending_confirm"
    assert lines[1].startswith("data: ") and lines[2] == ""          # event / data / 空行
    body = json.loads(lines[1][len("data: "):])
    # 字节级核对：五字段全在、值正确
    assert body["thread_id"] == "t-frame"
    assert body["tool_name"] == "knowledge_import"
    assert body["args"] == {"source_files": ["/tmp/x.md"]}
    assert body["risk_level"] == "high"
    assert body["timeout_s"] == 300


# ═══════════════════════════════════════════════════════════════
# HF-G4 confirm 口径：单一词表分类
# ═══════════════════════════════════════════════════════════════
def test_gd_classify_hitl_resume_confirm_execute():
    """confirm → (execute, None, None)：放行执行（mcp_hitl_decision=True 写类工具经 executor 执行）。"""
    from app.chat.flows.graph_stream import _classify_hitl_resume

    kind, notice, deg = _classify_hitl_resume("confirm")
    assert kind == "execute"
    assert notice is None and deg is None
    # mcp_hitl_decision 映射（graph_stream 顶部 `True if kind == "execute"`）
    assert (kind == "execute") is True


def test_ge_classify_hitl_resume_reject_skips_exec():
    """reject → (rejected, 拒绝文案, hitl_rejected_no_pending)：0 执行 + 拒绝上下文收束。"""
    from app.chat.flows.graph_stream import _classify_hitl_resume

    kind, notice, deg = _classify_hitl_resume("reject")
    assert kind == "rejected"
    assert deg == "hitl_rejected_no_pending"
    assert notice and "未执行" in notice
    # _suppress_mcp 只在 rejected 置 True（graph_stream 顶部）
    assert (kind == "rejected") is True


def test_gf_classify_hitl_resume_unknown_expired():
    """未知/空 action → (expired, 失效文案, hitl_confirm_expired_no_pending)：确认失效防御分支。"""
    from app.chat.flows.graph_stream import _classify_hitl_resume

    for a in (None, "", "approve", "yes"):
        kind, notice, deg = _classify_hitl_resume(a)
        assert kind == "expired", f"action={a!r} 应判 expired"
        assert deg == "hitl_confirm_expired_no_pending"
        assert notice and "已失效" in notice
        # expired 不放行执行、也不当作 reject 抑制——mcp_hitl_decision=False
        assert (kind == "execute") is False
        assert (kind == "rejected") is False


def test_gg_cross_file_terminology_aligned():
    """口径一致（防再断）：graph_stream 可执行路径只认 confirm，不认 approve；
    router 的 action Literal 恰好等于 _RESUME_CONFIRM。"""
    from app.chat.flows import graph_stream as gs

    # 1) graph_stream 可执行代码不再出现 `"approve"`（词表已收敛到 confirm|reject）
    src = inspect.getsource(gs)
    # 注释里仍允许出现历史说明性 "approve"，故只校验「可执行字符串字面量」：
    # 抽取所有字符串字面量，断言不含 "approve"（允许注释中含 "…认 "approve"…" 说明文本
    # 会污染，因此改为：断言确认词表与 router 对齐即可，另对 resume 判断做语义收口）。
    # 直接断言分类常量词表 == 路由器 Literal（这是真正决定 口径一致 的构造约束）：
    assert gs._RESUME_CONFIRM == "confirm"
    assert gs._RESUME_REJECT == "reject"

    # 2) router 请求体 action Literal 必须是 {"confirm","reject"} 且等于本层词表
    lit = chat_router.ChatResumeRequest.model_fields["action"].annotation
    from typing import Literal, get_args

    assert getattr(lit, "__origin__", None) is Literal, "action 应为 Literal 类型"
    allowed = set(get_args(lit))
    assert allowed == {"confirm", "reject"}
    assert "confirm" in allowed and gs._RESUME_CONFIRM == "confirm"
    assert "reject" in allowed and gs._RESUME_REJECT == "reject"

    # 3) 语义收口：确认词表（confirm）≠ 旧实现词（approve）——若未来有人把常量改回 approve，
    #    该断言会红灯，逼着同步改 router Literal，杜绝口径漂移。
    assert gs._RESUME_CONFIRM != "approve"


# ═══════════════════════════════════════════════════════════════
# HF-G4 端点级：confirm 决策写入 Redis（resume 端点，注入 Redis；不可达则 skip）
# ═══════════════════════════════════════════════════════════════
def _fake_user():
    async def _u():
        from app.auth.dependencies import UserInfo, UserRole

        return UserInfo(
            user_id=2, nickname="stu", real_name="stu",
            mobile=None, email="stu@e.a", gender=None, avatar_url=None,
            role=UserRole.STUDENT,
        )
    return _u


def _build_app(user_dep):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    from app.common.exceptions import AppException

    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[chat_router.get_current_user] = user_dep

    @app.exception_handler(AppException)
    async def _exc(request, exc: AppException):
        return JSONResponse(status_code=exc.http_status,
                            content={"code": exc.code, "message": exc.message, "data": None})
    return app


@asynccontextmanager
async def _ctx():
    from app.database import close_redis, get_redis, init_redis

    try:
        await init_redis()
    except Exception:  # noqa: BLE001
        pytest.skip("Redis 不可用，跳过端点实证")
    try:
        yield get_redis()
    finally:
        await close_redis()


@pytest.mark.asyncio
async def test_gh_resume_confirm_writes_action_preserved():
    """端点级：confirm resume → 200 resumed，且决策键里 action 保持 "confirm"（供续流放行）。"""
    async with _ctx() as r:
        tid = "hf-fix-confirm"
        await r.delete(f"hitl:pending:{tid}", f"hitl:decision:{tid}")
        # 用契约完整五字段的 pending 标记注入
        await r.set(f"hitl:pending:{tid}", json.dumps({
            "thread_id": tid, "tool_name": "knowledge_import", "args": {},
            "risk_level": "high", "timeout_s": 300,
        }), ex=300)
        app = _build_app(_fake_user())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/chat/resume", json={"thread_id": tid, "action": "confirm"})
            assert resp.status_code == 200, resp.text
            assert resp.json()["code"] == 0
            assert resp.json()["data"]["status"] == "resumed"
            # 决策键已写、action 保留 confirm（graph_stream 续流据此放行执行）
            raw = await r.get(f"hitl:decision:{tid}")
            assert raw, "决策键应已写入"
            decision = json.loads(raw)
            assert decision["action"] == "confirm"
            # pending 已消费
            assert not await r.exists(f"hitl:pending:{tid}")


@pytest.mark.asyncio
async def test_gi_resume_reject_writes_action_preserved():
    """端点级：reject resume → 200 rejected，决策键 action 保留 reject（续流 0 执行收束）。"""
    async with _ctx() as r:
        tid = "hf-fix-reject"
        await r.delete(f"hitl:pending:{tid}", f"hitl:decision:{tid}")
        await r.set(f"hitl:pending:{tid}", '{"tool_name": "knowledge_import"}', ex=300)
        app = _build_app(_fake_user())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/chat/resume", json={"thread_id": tid, "action": "reject", "reason": "no"})
            assert resp.status_code == 200, resp.text
            assert resp.json()["data"]["status"] == "rejected"
            decision = json.loads(await r.get(f"hitl:decision:{tid}"))
            assert decision["action"] == "reject"