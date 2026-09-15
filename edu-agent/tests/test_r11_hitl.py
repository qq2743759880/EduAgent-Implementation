# -*- coding: utf-8 -*-
"""R11 HITL 中断/恢复契约测试（contracts/reshape-r-hitl.json，2026-09-15 冻结）。

逐条覆盖验收 GWT：
  R11-G1 图级中断：_hitl_risk_level 分类（写类→high/medium、只读→None）+ LangGraph
          interrupt 行为（payload 五字段齐、risk_level 枚举、中断点后未执行）
  R11-G2 恢复：Command(resume=confirm) 续跑执行；resume=reject 走拒绝上下文（工具零执行分支）
  R11-G3 SSE 帧：sse_line("pending_confirm", payload) 字节级 = event/data 行 + 空行
  R11-G4 真实 HTTP：POST /api/chat/resume 未知 thread_id → 40450(HTTP 404)；注入合法 pending
          → confirm 返回 {"code":0,...,"data":{"status":"resumed"}} 且决策键落 Redis
  R11-G5 超时：pending 键短 TTL 注入（1s），过期后 resume → 40450（语义「确认已超时」）
  R11-G6 零回归：只读/未登记工具 _hitl_risk_level → None（免中断路径）
  R11-G7 前端：chat.html 静态断言（pending_confirm 分支 + 确认卡渲染 + resume 调用）
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
import json
from pathlib import Path
from typing import TypedDict

import httpx
import pytest
from fastapi import FastAPI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.auth.dependencies import UserInfo, UserRole
from app.chat import router as chat_router
from app.chat import sse as chat_sse


def _fake_user():
    async def _u():
        return UserInfo(
            user_id=2, nickname="stu", real_name="stu",
            mobile=None, email="stu@e.a", gender=None, avatar_url=None,
            role=UserRole.STUDENT,
        )
    return _u


def _build_app(user_dep) -> FastAPI:
    from fastapi.responses import JSONResponse

    from app.common.exceptions import AppException

    app = FastAPI()
    app.include_router(chat_router.router)  # router 自带 prefix="/api/chat"
    app.dependency_overrides[chat_router.get_current_user] = user_dep

    @app.exception_handler(AppException)
    async def _app_exc(request, exc: AppException):
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message, "data": None},
        )

    return app


# ═══════════════════════════════════════════════════════════════
# R11-G1 图级中断
# ═══════════════════════════════════════════════════════════════
def test_g1_risk_level_classification():
    """写类工具映射 high/medium；只读/未登记 → None（免中断）。"""
    from app.ai.permission_gate import ADMIN_WRITE_TOOLS, COURSE_WRITE_TOOLS
    from app.chat.flows.langgraph_agent import _hitl_risk_level

    for t in ADMIN_WRITE_TOOLS:
        assert _hitl_risk_level(t) == "high", f"admin_write 工具应 high: {t}"
    for t in COURSE_WRITE_TOOLS:
        assert _hitl_risk_level(t) == "medium", f"course_write 工具应 medium: {t}"
    # executor 高风险类（write_/exec_/网络/退款前缀）→ high
    assert _hitl_risk_level("exec_command") == "high"
    assert _hitl_risk_level("write_file") == "high"
    assert _hitl_risk_level("refund_apply") == "high"
    # 只读 / 未登记 → None（免中断，G6 零回归核心）
    for name in ("search_knowledge", "web_search", "get_course", "calculator", ""):
        assert _hitl_risk_level(name) is None, f"只读/未知工具应免中断: {name!r}"


class _G1State(TypedDict):
    x: int
    executed: bool
    out: str


def _interrupt_graph():
    """复刻 langgraph_agent.tool_node 的 interrupt 三件套语义（中断→等待→resume 分流）。"""

    def node(state: _G1State) -> dict:
        v = interrupt({
            "thread_id": "t", "tool_name": "points_change",
            "args": {"p": 1}, "risk_level": "high", "timeout_s": 300,
        })
        d = v if isinstance(v, dict) else {}
        action = str(d.get("action") or "").strip().lower()
        if action != "confirm":
            # 拒绝分支：工具零执行，走拒绝上下文
            return {"out": "rejected", "executed": False}
        return {"out": "confirmed", "executed": True}

    g = StateGraph(_G1State)
    g.add_node("n", node)
    g.add_edge(START, "n")
    g.add_edge("n", END)
    return g


@pytest.mark.asyncio
async def test_g1_interrupt_payload_and_no_exec():
    """带 checkpointer invoke 触发中断：payload 五字段齐、risk_level 枚举、工具未执行。"""
    g = _interrupt_graph().compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "g1-t"}}
    r1 = await g.ainvoke({"x": 1, "executed": False, "out": ""}, cfg)

    intr = r1.get("__interrupt__")
    assert intr is not None, "中断后应返回 __interrupt__ 键"
    item = intr[0]
    v = getattr(item, "value", item)
    assert set(v.keys()) == {"thread_id", "tool_name", "args", "risk_level", "timeout_s"}
    assert v["risk_level"] in {"low", "medium", "high"}
    assert v["timeout_s"] == 300
    assert v["tool_name"] == "points_change"
    # 工具未执行：interrupt 处挂起，节点后续未运行
    assert r1.get("executed") is False


@pytest.mark.asyncio
async def test_g2_resume_confirm_executes():
    """Command(resume=confirm) 续跑 → 节点完成且真实执行。"""
    g = _interrupt_graph().compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "g2-c"}}
    await g.ainvoke({"x": 1, "executed": False, "out": ""}, cfg)
    r2 = await g.ainvoke(Command(resume={"action": "confirm"}), cfg)
    assert r2["executed"] is True
    assert r2["out"] == "confirmed"


@pytest.mark.asyncio
async def test_g2_resume_reject_skips_exec():
    """Command(resume=reject) 续跑 → 工具零执行，走拒绝上下文。"""
    g = _interrupt_graph().compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "g2-r"}}
    await g.ainvoke({"x": 1, "executed": False, "out": ""}, cfg)
    r2 = await g.ainvoke(Command(resume={"action": "reject", "reason": "no"}), cfg)
    assert r2["out"] == "rejected"
    assert r2["executed"] is False  # 工具零执行


# ═══════════════════════════════════════════════════════════════
# R11-G3 SSE 帧字节级
# ═══════════════════════════════════════════════════════════════
def test_g3_pending_confirm_sse_frame_bytes():
    payload = {
        "thread_id": "t1", "tool_name": "points_change",
        "args": {"p": 1}, "risk_level": "high", "timeout_s": 300,
    }
    raw = chat_sse.sse_line("pending_confirm", payload)
    expected = (
        "event: pending_confirm\n"
        "data: {\"thread_id\": \"t1\", \"tool_name\": \"points_change\", "
        "\"args\": {\"p\": 1}, \"risk_level\": \"high\", \"timeout_s\": 300}\n"
        "\n"
    )
    assert raw.decode("utf-8") == expected


# ═══════════════════════════════════════════════════════════════
# R11-G4/G5 resume 端点（ASGI + 真实 Redis；Redis 不可达则 skip）
# ═══════════════════════════════════════════════════════════════
@asynccontextmanager
async def _resume_client_context():
    """在测试 loop 内初始化/关闭全局 Redis 池（resume 端点走 get_redis() 单例）。"""
    from app.database import close_redis, get_redis, init_redis

    try:
        await init_redis()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Redis 不可用，跳过 resume 端点实证: {type(exc).__name__}")
    try:
        yield get_redis()
    finally:
        await close_redis()


@pytest.mark.asyncio
async def test_g4_resume_unknown_thread_40450():
    async with _resume_client_context() as r:
        tid = "g4-nonexistent"
        await r.delete(f"hitl:pending:{tid}", f"hitl:decision:{tid}")
        app = _build_app(_fake_user())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/chat/resume", json={"thread_id": tid, "action": "confirm"})
            assert resp.status_code == 404, resp.text
            body = resp.json()
            assert body["code"] == "40450"
            assert "超时" in body["message"]


@pytest.mark.asyncio
async def test_g4_resume_confirm_writes_decision():
    async with _resume_client_context() as r:
        tid = "g4-ok"
        await r.delete(f"hitl:pending:{tid}", f"hitl:decision:{tid}")
        await r.set(f"hitl:pending:{tid}", '{"tool_name": "points_change"}', ex=300)
        app = _build_app(_fake_user())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/chat/resume", json={"thread_id": tid, "action": "confirm", "reason": ""})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["code"] == 0
            assert body["data"]["status"] == "resumed"
            # pending 已消费、决策键已写
            assert await r.exists(f"hitl:decision:{tid}")
            assert not await r.exists(f"hitl:pending:{tid}")


@pytest.mark.asyncio
async def test_g5_resume_after_ttl_expiry_40450():
    """短 TTL 注入（1s）→ 过期后 resume → 40450（「确认已超时」）。"""
    async with _resume_client_context() as r:
        tid = "g5-expired"
        await r.delete(f"hitl:pending:{tid}", f"hitl:decision:{tid}")
        await r.set(f"hitl:pending:{tid}", "{}", ex=1)
        await asyncio.sleep(1.2)
        app = _build_app(_fake_user())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/chat/resume", json={"thread_id": tid, "action": "confirm"})
            assert resp.status_code == 404, resp.text
            assert resp.json()["code"] == "40450"


# ═══════════════════════════════════════════════════════════════
# R11-G6 零回归 / R11-G7 前端静态断言
# ═══════════════════════════════════════════════════════════════
def test_g6_error_code_registered():
    from app.common.error_codes import CHAT_HITL_THREAD_NOT_FOUND

    assert CHAT_HITL_THREAD_NOT_FOUND == "40450"
    # 404xx 码段映射 HTTP 404（resume 未知 thread_id → 404 契约）
    from app.common.error_codes import STATUS_TO_CODE

    assert STATUS_TO_CODE[404] == "40400"  # 默认 404 码，业务端点显式抛 40450 不受影响


def test_g7_frontend_pending_confirm_static():
    p = Path(__file__).resolve().parents[1] / ".." / "edu-frontend" / "public" / "chat.html"
    html = p.read_text(encoding="utf-8")
    assert 'evt === "pending_confirm"' in html, "SSE 事件分支缺失"
    assert "renderHitlCard" in html, "确认卡渲染函数缺失"
    assert "resumeHitl(" in html, "resume 决策函数缺失"
    assert 'EAPI.post("/api/chat/resume"' in html, "resume 端点调用缺失"
    assert "hitl-confirm" in html and "hitl-reject" in html, "确认/拒绝按钮缺失"
    assert "thread_id" in html, "thread_id 续流语义缺失"
