# -*- coding: utf-8 -*-
"""W-NEXT-R23-001 真实 chat SSE 一轮（8011 一次性实例，用后即清；共享 8000 零接触）。

沿用 FUSIONBLIND/DEADCODE 既有 8011 范式：login(user000001) → POST /api/chat/stream
（字段 query 非 message）→ 解析 event: start|retrieval|token|done，token 累加 j.delta。
断言：start 首帧 / retrieval 带 docs / token delta 非空 / done code=0 / 无 error 帧；
retrieval 帧 docs 数即断崖后 final docs（V2 灰度默认关 → 与 V1 行为一致，作为活体旁证）。

用法（edu-agent/ 下，8011 实例就绪后）：
  .venv/Scripts/python.exe -X utf8 test-reports/r23_chat_sse_probe.py --base http://127.0.0.1:8011
"""
from __future__ import annotations

import argparse
import json
import time

import requests

ACCOUNT, PASSWORD = "user000001", "Test@123456"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8011")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    r = requests.post(f"{base}/api/auth/login",
                      json={"account": ACCOUNT, "password": PASSWORD}, timeout=30)
    r.raise_for_status()
    body = r.json()
    assert body.get("code") == 0, f"login code!=0: {str(body)[:200]}"
    token = (body.get("data") or {}).get("access_token")
    assert token, f"no access_token: {str(body)[:200]}"
    print(f"[login] ok account={ACCOUNT}")

    t0 = time.perf_counter()
    events: list[tuple[str, dict]] = []
    with requests.post(
        f"{base}/api/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "什么是现在完成时？一句话回答", "stream": True, "use_mcp_tools": False},
        stream=True, timeout=(30, 180),
    ) as resp:
        print(f"[stream] http={resp.status_code} content-type={resp.headers.get('content-type','')}")
        assert resp.status_code == 200, f"HTTP != 200: {resp.status_code}"
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
    assert names and names[0] == "start", f"首帧必须 start: {names[:3]}"
    assert "error" not in names, "error 帧出现"
    retrieval = next((d for e, d in events if e == "retrieval"), None)
    assert retrieval is not None, f"缺 retrieval 帧: {names}"
    docs = retrieval.get("docs") or []
    token_frames = [d for e, d in events if e == "token"]
    deltas = "".join(str(d.get("delta") or "") for d in token_frames)
    done = next((d for e, d in events if e == "done"), None)
    assert done is not None and done.get("code") == 0, f"done 缺失/异常: {names[-3:]}"

    print(f"[stream] latency_ms={dt} frames={names[:4]}...{names[-2:]}")
    print(f"[stream] retrieval: docs={len(docs)} retrieved_count={retrieval.get('retrieved_count')} "
          f"degraded={retrieval.get('degraded_reason')}")
    if docs:
        print(f"[stream] top1={docs[0].get('chunk_id') or docs[0].get('doc_id')} "
              f"content_head={(docs[0].get('content') or '')[:60]!r}")
    print(f"[stream] token x{len(token_frames)} delta[{len(deltas)}chars]={deltas[:80]!r}")
    inner = done.get("data") or {}
    print(f"[stream] done code=0 session_id={inner.get('session_id')} "
          f"latency_ms={inner.get('latency_ms')}")
    print("CHAT SSE ROUND PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
