# -*- coding: utf-8 -*-
"""
task39 独立压测器：对后端真实 HTTP 读型端点做并发压测，输出真实 P50/P95/P99/吞吐。

纪律：
- 真实契约为准、独立实证、不 mock 性能数据。
- 用 student token（user000001/Test@123456）走鉴权读路径。
- 只测读型端点（/api/series 列表 + 详情），不触 LLM/向量。
- 预热若干请求排冷启动，再计样本。
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import statistics
import time
import sys

import requests

BASE = os.environ.get("EDU_BASE", "http://127.0.0.1:8000")
ACCOUNT = os.environ.get("EDU_ACCOUNT", "user000001")
PASSWORD = os.environ.get("EDU_PASSWORD", "Test@123456")
RW = int(os.environ.get("RW", "4"))

s = requests.Session()


def login() -> str:
    r = s.post(f"{BASE}/api/auth/login", json={"account": ACCOUNT, "password": PASSWORD}, timeout=15)
    r.raise_for_status()
    body = r.json()
    assert body.get("code") == 0, f"login shell code!=0: {body}"
    tok = body["data"]["access_token"]
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return tok


def warmup() -> None:
    for _ in range(RW):
        r = s.get(f"{BASE}/api/series", timeout=15)
        r.raise_for_status()


def one_request(page: int):
    t0 = time.perf_counter()
    try:
        r = s.get(f"{BASE}/api/series", params={"page": page, "page_size": 20}, timeout=30)
        lat = (time.perf_counter() - t0) * 1000.0
        return {"status": r.status_code, "ms": lat, "err": None}
    except Exception as exc:  # noqa: BLE001
        return {"status": 0, "ms": (time.perf_counter() - t0) * 1000.0, "err": f"{type(exc).__name__}: {exc}"}


def perc(samples: list[float], q: float) -> float:
    if not samples:
        return 0.0
    x = sorted(samples)
    k = int(round(q * (len(x) - 1)))
    return float(x[k])


def stress(concurrency: int, total: int) -> dict:
    pages = [(i % 8) + 1 for i in range(total)]  # 复用少量分页参数，避免无谓 DB 变化干扰
    lat = []
    status = {}
    errs = []
    wall0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = [ex.submit(one_request, p) for p in pages]
        for f in concurrent.futures.as_completed(futs):
            res = f.result()
            lat.append(res["ms"])
            status[res["status"]] = status.get(res["status"], 0) + 1
            if res["err"]:
                errs.append(res["err"])
    wall = (time.perf_counter() - wall0) * 1000.0
    ok_count = status.get(200, 0)
    return {
        "concurrency": concurrency,
        "total": total,
        "wall_ms": round(wall, 1),
        "rps": round(total / (wall / 1000.0), 1),
        "ok": ok_count,
        "non200": {k: v for k, v in status.items() if k != 200},
        "err_count": len(errs),
        "p50_ms": round(perc(lat, 0.50), 1),
        "p90_ms": round(perc(lat, 0.90), 1),
        "p95_ms": round(perc(lat, 0.95), 1),
        "p99_ms": round(perc(lat, 0.99), 1),
        "mean_ms": round(statistics.mean(lat), 1) if lat else 0.0,
        "max_ms": round(max(lat), 1) if lat else 0.0,
        "err_sample": errs[:3],
    }


def main() -> None:
    tok = login()
    print(json.dumps({"login": "ok", "token_len": len(tok)}, ensure_ascii=False))
    warmup()
    result = {"endpoint": f"GET {BASE}/api/series", "auth": f"Bearer student {ACCOUNT} (sys)", "redis_gap": True}
    for conc, total in [(50, 500), (100, 1000)]:
        result[f"conc{conc}"] = stress(conc, total)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())