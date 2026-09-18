# -*- coding: utf-8 -*-
"""W-NEXT-DEADCODE-001 真实 HTTP 回归：死代码删除后 chat 双路径活体实证。

1. 非流式 POST /api/chat（六节点图 run_agent）→ 200 + {code:0,...} + answer 非空
2. 流式 POST /api/chat/stream（R02 graph_stream 主路径）→ SSE 帧序 start → retrieval → token(delta)... → done
   （AGENTS.md 口径：token 事件累加 j.delta）

直接运行：python test-reports/_wnextdeadcode1_http_check.py
"""
from __future__ import annotations

import json
import sys
import time

import requests

BASE = "http://127.0.0.1:8000"
ACCOUNT, PASSWORD = "user000001", "Test@123456"


def login() -> str:
    r = requests.post(f"{BASE}/api/auth/login", json={"account": ACCOUNT, "password": PASSWORD}, timeout=30)
    r.raise_for_status()
    body = r.json()
    assert body.get("code") == 0, f"login code!=0: {body}"
    token = (body.get("data") or {}).get("access_token")
    assert token, f"no access_token: {body}"
    print(f"[login] ok account={ACCOUNT}")
    return token


def nonstream_chat(token: str) -> None:
    t0 = time.perf_counter()
    r = requests.post(
        f"{BASE}/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "用一句话说明什么是现在完成时", "use_mcp_tools": False},
        timeout=180,
    )
    dt = int((time.perf_counter() - t0) * 1000)
    print(f"[non-stream] http={r.status_code} latency_ms={dt}")
    assert r.status_code == 200, f"非流式 HTTP != 200: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert body.get("code") == 0, f"非流式 code!=0: {str(body)[:300]}"
    data = body.get("data") or {}
    answer = str(data.get("answer") or "")
    assert answer.strip(), f"answer 为空: {str(body)[:300]}"
    print(f"[non-stream] code=0 answer[{len(answer)}chars]={answer[:80]!r} docs={len(data.get('docs') or [])}")


def stream_chat(token: str) -> None:
    t0 = time.perf_counter()
    events: list[tuple[str, dict]] = []
    with requests.post(
        f"{BASE}/api/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "什么是现在完成时？一句话回答", "stream": True, "use_mcp_tools": False},
        stream=True,
        timeout=(30, 180),
    ) as resp:
        print(f"[stream] http={resp.status_code} content-type={resp.headers.get('content-type','')}")
        assert resp.status_code == 200, f"流式 HTTP != 200: {resp.status_code}"
        assert "text/event-stream" in resp.headers.get("content-type", ""), "非 SSE 响应"
        cur_event, data_buf = None, []
        for raw in resp.iter_lines(decode_unicode=True):
            if raw is None:
                continue
            line = raw.strip()
            if line.startswith("event:"):
                if cur_event is not None and data_buf:
                    events.append((cur_event, json.loads("\n".join(data_buf) or "{}")))
                cur_event, data_buf = line.split(":", 1)[1].strip(), []
            elif line.startswith("data:"):
                data_buf.append(line.split(":", 1)[1].strip())
            elif not line and cur_event is not None:
                events.append((cur_event, json.loads("\n".join(data_buf) or "{}")))
                cur_event, data_buf = None, []
        if cur_event is not None and data_buf:
            events.append((cur_event, json.loads("\n".join(data_buf) or "{}")))
    dt = int((time.perf_counter() - t0) * 1000)

    names = [e for e, _ in events]
    print(f"[stream] latency_ms={dt} frames={names}")
    assert names, "SSE 零事件"
    assert names[0] == "start", f"首帧必须是 start: {names[:3]}"
    assert "retrieval" in names, f"缺 retrieval 帧: {names}"
    token_frames = [d for e, d in events if e == "token"]
    assert token_frames, f"缺 token 帧: {names}"
    deltas = "".join(str(d.get("delta") or "") for d in token_frames)
    assert deltas.strip(), "token 帧全部无 delta"
    done = next((d for e, d in events if e == "done"), None)
    assert done is not None, f"缺 done 帧: {names}"
    assert done.get("code") == 0 and done.get("message") == "ok", f"done 壳异常: {done}"
    inner = done.get("data") or {}
    assert "error" not in names, "error 帧出现"
    print(f"[stream] start→retrieval→token×{len(token_frames)}→done ok; answer[{len(deltas)}chars]={deltas[:80]!r}")
    print(f"[stream] done.data: session_id={inner.get('session_id')} latency_ms={inner.get('latency_ms')} degraded={inner.get('degraded_reason')}")


if __name__ == "__main__":
    tk = login()
    nonstream_chat(tk)
    stream_chat(tk)
    print("ALL HTTP CHECKS PASSED")
    sys.exit(0)
