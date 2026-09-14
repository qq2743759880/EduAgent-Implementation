# -*- coding: utf-8 -*-
"""R02 8010 实例实测：task104 SSE 契约回归 + thread_id 隔离 + checkpoint 键实证 + TTFT。"""
import json, sys, time, uuid
import requests

BASE = "http://127.0.0.1:8010"
sys.path.insert(0, ".")

def login():
    r = requests.post(BASE + "/api/auth/login",
                      json={"account": "user000001", "password": "Test@123456"}, timeout=15)
    d = r.json()
    assert d["code"] == 0, d
    return d["data"]["access_token"]

tok = login()
H = {"Authorization": f"Bearer {tok}"}
print("login ok")

def sse_query(query, session_id=None, timeout=90):
    """POST /api/chat/stream，解析 SSE 帧序列；返回 (events, ttft_retrieval, ttft_first_token, total)。"""
    r = requests.post(BASE + "/api/chat/stream", headers=H,
                      json={"query": query, "session_id": session_id, "stream": True},
                      stream=True, timeout=timeout)
    assert r.status_code == 200, (r.status_code, r.text[:200])
    events = []
    cur_event, cur_data = None, None
    t0 = time.perf_counter()
    ttft_ret = ttft_tok = None
    for raw in r.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        if raw.startswith("event: "):
            cur_event = raw[7:].strip()
        elif raw.startswith("data: "):
            cur_data = json.loads(raw[6:])
        elif raw == "" and cur_event:
            now = time.perf_counter()
            if cur_event == "retrieval" and ttft_ret is None:
                ttft_ret = now - t0
            if cur_event == "token" and ttft_tok is None:
                ttft_tok = now - t0
            events.append((cur_event, cur_data))
            cur_event, cur_data = None, None
    return events, ttft_ret, ttft_tok, time.perf_counter() - t0

# ── ① task104 契约回归（knowledge 类，带检索）──
ev, ttr, ttt, total = sse_query("线性代数中特征值和特征向量的几何意义是什么？")
names = [e for e, _ in ev]
assert names[0] == "start", names
assert "retrieval" in names and "token" in names, names
assert names[-1] == "done", names
assert "error" not in names, names
tok_frames = [d for e, d in ev if e == "token"]
assert all("delta" in d for d in tok_frames), "token 帧字段必须是 delta"
merged = "".join(d["delta"] for d in tok_frames)
ret = dict(ev[names.index("retrieval")][1])
done = dict(ev[-1][1])
assert done["code"] == 0 and done["message"] == "ok" and isinstance(done["data"], dict)
print("[contract] frame order:", names[0], names[1], f"... token x{len(tok_frames)} ...", names[-1])
print("[contract] delta merged len:", len(merged), "| head:", merged[:60].replace("\n", " "))
print("[contract] retrieval: retrieved_count=%s final_count=%s rewrite=%r degraded=%r mcp=%s" % (
    ret.get("retrieved_count"), ret.get("final_count"), ret.get("rewrite_query"),
    ret.get("degraded_reason"), ret.get("mcp_tool_calls")))
print("[contract] done.data keys:", sorted(done["data"].keys()))
print("[contract] TTFT retrieval=%.3fs first_token=%.3fs total=%.3fs" % (ttr or -1, ttt or -1, total))
with open("/tmp/r02_sse_contract_capture.json", "w", encoding="utf-8") as f:
    json.dump({"names": names, "retrieval": ret, "done": done, "merged_head": merged[:400],
               "ttft_retrieval_s": ttr, "ttft_first_token_s": ttt, "total_s": total}, f, ensure_ascii=False, indent=1)

# ── ② thread_id 隔离：同用户两笔匿名请求 → Redis checkpoint 键不同 ──
import redis.asyncio as aioredis
from app.config import settings

async def ckpt_keys():
    r = aioredis.from_url(settings.REDIS_URL)
    keys1 = [k async for k in r.scan_iter(match="edu:ckpt:anon-*")]
    await r.aclose()
    return keys1

import asyncio
before = set(asyncio.run(ckpt_keys()))
ev1, *_ = sse_query("匿名问题一：什么是矩阵的秩？")
ev2, *_ = sse_query("匿名问题二：什么是逆矩阵？")
after = asyncio.run(ckpt_keys())
new_keys = sorted(set(after) - before)
print("[thread_id] new anon checkpoint keys after two anonymous streams:", len(new_keys))
for k in new_keys:
    print("   ", k)
assert len(new_keys) >= 2, "两笔匿名请求应产生 >=2 个独立 checkpoint 键"
print("[thread_id] GWT PASS: 两笔匿名请求 checkpoint 键不同（互不共享 task24-{user_id}）")
with open("/tmp/r02_ckpt_keys.json", "w", encoding="utf-8") as f:
    json.dump({"new_keys": [k.decode() if isinstance(k, bytes) else k for k in new_keys]}, f, indent=1)
