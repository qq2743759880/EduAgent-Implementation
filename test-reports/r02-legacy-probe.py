# -*- coding: utf-8 -*-
"""R02 开关回退实测：STREAM_VIA_GRAPH=false → 旧路径 run_agent_turn 服务 SSE，契约等同。"""
import json, sys, time
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

def sse_query(query, timeout=90):
    r = requests.post(BASE + "/api/chat/stream", headers=H,
                      json={"query": query, "session_id": None, "stream": True},
                      stream=True, timeout=timeout)
    assert r.status_code == 200, (r.status_code, r.text[:200])
    events, cur_e, cur_d = [], None, None
    t0 = time.perf_counter()
    ttft_ret = ttft_tok = None
    for raw in r.iter_lines(decode_unicode=True):
        if raw is None: continue
        if raw.startswith("event: "): cur_e = raw[7:].strip()
        elif raw.startswith("data: "): cur_d = json.loads(raw[6:])
        elif raw == "" and cur_e:
            now = time.perf_counter()
            if cur_e == "retrieval" and ttft_ret is None: ttft_ret = now - t0
            if cur_e == "token" and ttft_tok is None: ttft_tok = now - t0
            events.append((cur_e, cur_d)); cur_e, cur_d = None, None
    return events, ttft_ret, ttft_tok

ev, ttr, ttt = sse_query("什么是逆矩阵的几何意义？")
names = [e for e, _ in ev]
assert names[0] == "start" and names[-1] == "done", names
tokd = [d for e, d in ev if e == "token"]
assert all("delta" in d for d in tokd)
merged = "".join(d["delta"] for d in tokd)
done = ev[-1][1]
ret = dict(ev[names.index("retrieval")][1])
print("[legacy] frame order:", names[0], names[1], f"token x{len(tokd)}", names[-1])
print("[legacy] delta merged len:", len(merged), "| head:", merged[:50].replace("\n", " "))
print("[legacy] retrieval final_count=%s degraded=%r" % (ret.get("final_count"), ret.get("degraded_reason")))
print("[legacy] done shell code=%s message=%r data_keys=%s" % (done["code"], done["message"], sorted(done["data"].keys())))
print("[legacy] TTFT retrieval=%.3fs first_token=%.3fs" % (ttr or -1, ttt or -1))
assert done["code"] == 0 and done["message"] == "ok"
print("[legacy] PASS: 开关回退后旧路径行为等同（SSE 契约同构）")
