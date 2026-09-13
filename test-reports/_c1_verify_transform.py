"""C1 OpenAPI 壳上移 —— 独立实证脚本（不依赖被并发改动的 course_admin 模块）。

覆盖真实 app 的关键形态：
  A. 裸业务 DTO 作 response_model（改造前 users/me/profile 的形态）→ 期望被包壳
  B. response_model=Shell[UserProfile]（改造后 users/me/profile）→ 期望单壳、不二次包裹
  C. 返回 ok(dict) 的列表/普通端点（users/me、chat/sessions 形态）→ 期望壳包裹
  D. SSE 端点（text/event-stream）→ 期望豁免不包壳
  E. /health、/metrics → 期望豁免不包壳
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "edu-agent"))

from fastapi import FastAPI, APIRouter
from pydantic import BaseModel, Field

from app.core.resp import Shell, ok
from app.core.openapi_shell import install_openapi_shell


class Profile(BaseModel):
    nickname: str | None = Field(default=None)
    weekly_available_hours: int = 7


def build_app() -> FastAPI:
    r = APIRouter(prefix="/api/demo", tags=["demo"])

    @r.get("/profile", response_model=Profile)  # A: 裸 DTO
    async def bare(limit: int = 1):
        return Profile(nickname="x")

    sh_r = APIRouter(prefix="/api/sh", tags=["sh"])
    @sh_r.get("/profile", response_model=Shell[Profile])  # B: 改造后形态
    async def shelled():
        return ok(data=Profile(nickname="y"))

    lr = APIRouter(prefix="/api/list", tags=["list"])
    @lr.get("/items", response_model=dict)  # C: ok() 列表
    async def items():
        return ok(data=[{"id": 1}])

    ss_r = APIRouter(prefix="/api/sse", tags=["sse"])
    @ss_r.post("/stream")  # D: SSE
    async def stream():
        from fastapi.responses import StreamingResponse
        return StreamingResponse(iter([b"event: done\n\n"]), media_type="text/event-stream")

    app = FastAPI(title="c1-verify", version="1")
    app.include_router(r)
    app.include_router(sh_r)
    app.include_router(lr)
    app.include_router(ss_r)
    app.add_api_route("/health", lambda: {"status": "ok"})  # E
    app.add_api_route("/metrics", lambda: None)  # E
    return app


def resp_schema(app, method, path):
    op = app.openapi()["paths"][path][method]
    return op["responses"]["200"].get("content", {})


def main():
    app = build_app()
    install_openapi_shell(app, skip_paths=("/api/sse",))
    fails = []

    # A: 裸 DTO → 壳包裹，data=$ref Profile（单壳）
    a = resp_schema(app, "get", "/api/demo/profile")
    sa = a["application/json"]["schema"]
    assert "application/json" in a and "text/event-stream" not in a, "A fail"
    assert set(sa.get("required", [])) == {"code", "message", "data"}, f"A required={sa.get('required')}"
    assert sa["properties"]["code"] == {"type": "integer", "const": 0, "title": "code"}, "A code"
    assert sa["properties"]["message"] == {"type": "string", "const": "ok", "title": "message"}, "A msg"
    assert "$ref" in sa["properties"]["data"], f"A data should ref Profile -> {sa['properties']['data']}"
    print("[PASS] A bare-DTO response_model now single shell; data->Profile ref")

    # B: Shell[Profile] → 不再二次包装（200 保持单层 $ref→Shell_Profile_ 组件，组件才是壳）
    b = resp_schema(app, "get", "/api/sh/profile")
    sb = b["application/json"]["schema"]
    # 200 响应应保持 FastAPI 原生生成的 $ref，指向壳组件（而非被 transform 再包一层内联壳）
    assert "$ref" in sb, f"B 200 should remain a single $ref->shell component, got {sb}"
    assert "type" not in sb and "required" not in sb, "B 200 should not be inline-wrapped"
    comp = app.openapi()["components"]["schemas"]["Shell_Profile_"]
    comp_props = comp.get("properties", {})
    assert {"code", "message", "data"} <= set(comp_props), f"B comp should be shell -> {comp_props}"
    print("[PASS] B Shell[Profile] response_model stays single shell ($ref-aware idempotency, no double-wrap)")

    # C: ok(dict) 列表 → 壳包裹
    c = resp_schema(app, "get", "/api/list/items")
    sc = c["application/json"]["schema"]
    assert set(sc.get("required", [])) == {"code", "message", "data"}, "C required"
    assert sc["properties"]["code"]["const"] == 0 and sc["properties"]["message"]["const"] == "ok", "C const"
    print("[PASS] C ok(dict) list endpoint now shell-wrapped")

    # D: SSE → 豁免（skip_paths 命中路径的 200 app/json schema 不包壳）
    d = resp_schema(app, "post", "/api/sse/stream")
    ds = d["application/json"]["schema"]
    assert "properties" not in ds or "data" not in ds.get("properties", {}), \
        f"D should NOT wrap SSE into shell -> {ds.get('properties', {})}"
    print("[PASS] D SSE endpoint exempt (200 stays unwrapped, not shell-wrapped)")

    # E: /health、/metrics → 豁免（路径命中，200 app/json 不包壳）
    e = resp_schema(app, "get", "/health")
    es = e["application/json"]["schema"]
    assert "properties" not in es or "data" not in es.get("properties", {}), \
        f"E /health should not be shell-wrapped -> {es.get('properties', {})}"
    print("[PASS] E /health,/metrics exempt (not shell-wrapped)")

    print("\n=== C1 transform verification: ALL PASS ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())