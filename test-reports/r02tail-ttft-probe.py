# -*- coding: utf-8 -*-
"""R02-tail TTFT 检索段优化 probe：8010 临时实例实测 start→retrieval / first_token。

用法：.venv/Scripts/python.exe ../test-reports/r02tail-ttft-probe.py [rounds]
（在 edu-agent/ 目录下运行，登录 student 账号，连发 N 笔 knowledge 流式请求）
"""
import json
import sys
import time

import requests

BASE = "http://127.0.0.1:8010"
ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
QUERY = "线性代数中特征值和特征向量的几何意义是什么？"


def login():
    r = requests.post(BASE + "/api/auth/login",
                      json={"account": "user000001", "password": "Test@123456"}, timeout=15)
    d = r.json()
    assert d["code"] == 0, d
    return d["data"]["access_token"]


def sse_query(H, query, timeout=120):
    r = requests.post(BASE + "/api/chat/stream", headers=H,
                      json={"query": query, "session_id": None, "stream": True},
                      stream=True, timeout=timeout)
    assert r.status_code == 200, (r.status_code, r.text[:200])
    names, t0 = [], time.perf_counter()
    ttft_ret = ttft_tok = None
    cur_event, cur_data = None, None
    ret_payload = None
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
                ret_payload = cur_data
            if cur_event == "token" and ttft_tok is None:
                ttft_tok = now - t0
            names.append(cur_event)
            cur_event, cur_data = None, None
    return names, ttft_ret, ttft_tok, time.perf_counter() - t0, ret_payload


def main():
    tok = login()
    H = {"Authorization": f"Bearer {tok}"}
    print("login ok")
    rows = []
    for i in range(ROUNDS):
        names, ttr, ttt, total, ret = sse_query(H, QUERY)
        ok = names[0] == "start" and "retrieval" in names and names[-1] == "done" and "error" not in names
        rows.append({"round": i + 1, "ok": ok, "ttft_retrieval_s": round(ttr, 3) if ttr else None,
                     "ttft_first_token_s": round(ttt, 3) if ttt else None, "total_s": round(total, 3),
                     "retrieved_count": (ret or {}).get("retrieved_count"),
                     "final_count": (ret or {}).get("final_count")})
        print(json.dumps(rows[-1], ensure_ascii=False))
        time.sleep(1.0)
    ok_rows = [r for r in rows if r["ok"] and r["ttft_retrieval_s"] is not None]
    if ok_rows:
        rets = sorted(r["ttft_retrieval_s"] for r in ok_rows)
        med = rets[len(rets) // 2] if len(rets) % 2 else (rets[len(rets)//2 - 1] + rets[len(rets)//2]) / 2
        print(f"[median] start->retrieval = {med:.3f}s over {len(ok_rows)} valid rounds")
    with open("r02tail-ttft-results.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
