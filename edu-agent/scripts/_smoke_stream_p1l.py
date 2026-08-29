# -*- coding: utf-8 -*-
"""task-P1L 流式冒烟：验证 NameError 修复 + 测量 TTFT。"""
import json
import time
import urllib.request

token = json.load(open("scripts/_task39_users.json", encoding="utf-8"))[0][1]
body = json.dumps({"query": "现在完成时和过去时的区别", "stream": True, "use_hyde": False}).encode("utf-8")
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/chat/stream",
    data=body,
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
)
t0 = time.perf_counter()
with urllib.request.urlopen(req, timeout=120) as r:
    chunks = []
    first = None
    for line in r:
        line = line.decode("utf-8", errors="replace").strip()
        if line.startswith("data:") and first is None:
            first = time.perf_counter() - t0
        chunks.append(line)
n_data = len([c for c in chunks if c.startswith("data:")])
print(f"HTTP 200 | TTFT(首个data) {first:.1f}s | 总耗时 {time.perf_counter()-t0:.1f}s | data 行数 {n_data}")
