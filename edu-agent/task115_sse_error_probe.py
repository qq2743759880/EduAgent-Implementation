# -*- coding: utf-8 -*-
"""task115 C-B 实证探测：SSE `error` 事件（两段式错误模型第二段）。

在隔离 python 进程中加载真实 app，monkeypatch `service_chat_stream` 令其在
token 迭代中途抛异常 → 验证 router 生成器发出 `event: error` + data{code,message}
并安全收束（连接正常关闭，不悬挂），且返回内容不是 done。
"""
import asyncio
import os
import sys
from types import SimpleNamespace

os.environ.setdefault("MYSQL_HOST", "127.0.0.1")
os.environ.setdefault("DEBUG", "true")

import httpx

import app.main as main_mod
import app.chat.router as chat_router

app = main_mod.app


async def _fake_token_aiter():
    yield "部"
    yield "分内容"
    raise RuntimeError("forced-stream-error")  # 模拟 LLM 下游故障逃逸出 generate_stream


async def _fake_build_finalize(answer_text, *, degraded_extra):
    return {"session_id": "fake-sess", "message_id": None,
            "retrieved_count": 0, "final_count": 0, "latency_ms": 0,
            "rewrite_query": "q", "degraded_reason": None}


async def _fake_service_chat_stream(*a, **k):
    bundle = SimpleNamespace(
        docs=[],
        graph_entities=[],
        raw_retrieved_count=0,
        final_count=0,
        rewrite_query="q",
        degraded_reason=None,
    )
    return (
        SimpleNamespace(session_id="fake-sess"),
        bundle,
        [],
        _fake_token_aiter(),
        _fake_build_finalize,
        [],
    )


async def main():
    # 打桩 service 层：仅替换 router 侧引用的服务，触发真实 router 生成器逻辑
    chat_router.service_chat_stream = _fake_service_chat_stream

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        # DEBUG 模式：无 Authorization 头 → 虚拟管理员 user_id=1
        resp = await client.post(
            "/api/chat/stream",
            json={"query": "触发流式错误", "stream": True},
        )
        status = resp.status_code
        body = resp.text
        has_error = "event: error" in body
        has_code = "50000" in body
        has_done = "event: done" in body
        print(f"HTTP status    : {status}")
        print(f"contains_error : {has_error}")
        print(f"contains_code  : {has_code}  (INTERNAL_ERROR=50000)")
        print(f"contains_done  : {has_done}  (error 分支不应再有 done)")
        print("----- SSE 抓包 -----")
        print(body)


if __name__ == "__main__":
    asyncio.run(main())