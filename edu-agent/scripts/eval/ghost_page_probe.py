# -*- coding: utf-8 -*-
"""GHOST 分页完整性探针：真实 HTTP 全页扫描，检测跨页重复/漏出（只读）。

用法: .venv\\Scripts\\python.exe scripts/eval/ghost_page_probe.py [base_url] [page_size] [rounds]
默认 http://127.0.0.1:8000 10 3
输出: JSON -> scripts/eval/.ghost_tmp/page_probe.json
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PAGE_SIZE = int(sys.argv[2]) if len(sys.argv) > 2 else 10
ROUNDS = int(sys.argv[3]) if len(sys.argv) > 3 else 3
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ghost_tmp", "page_probe.json")

# 本机 loopback 探测必须绕过 HTTP_PROXY（环境可能设了 http_proxy，会把 127.0.0.1 请求转出去变 502）
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(_OPENER)


def login(account: str, password: str) -> str:
    req = urllib.request.Request(
        f"{BASE}/api/auth/login",
        data=json.dumps({"account": account, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["data"]["access_token"]


def get(url: str, token: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"code": str(e.code), "message": e.read().decode("utf-8", "replace")[:200], "data": None}


def round_scan(token: str, board_code: str | None = None) -> dict:
    pages = []
    all_ids: list[int] = []
    total = None
    p = 1
    while p <= 40:
        url = f"{BASE}/api/community/posts?page={p}&page_size={PAGE_SIZE}"
        if board_code:
            url += f"&board_code={board_code}"
        j = get(url, token)
        d = j.get("data")
        if not d:
            pages.append({"page": p, "error": j})
            break
        total = d["total"]
        ids = [it["post_id"] for it in d["items"]]
        pages.append({
            "page": p, "total": d["total"], "n": len(ids), "ids": ids,
            "pinned_ids": [it["post_id"] for it in d["items"] if it["is_pinned"]],
            "titles": [it["title"] for it in d["items"]],
        })
        all_ids += ids
        if len(all_ids) >= d["total"] or not ids:
            break
        p += 1
    seen: dict[int, list[int]] = {}
    for i in all_ids:
        seen.setdefault(i, []).append(i)
    dup = {str(k): len(v) for k, v in seen.items() if len(v) > 1}
    tt = {}
    for pg in pages:
        for t in pg.get("titles") or []:
            tt[t] = tt.get(t, 0) + 1
    return {
        "pages": pages,
        "total": total,
        "fetched": len(all_ids),
        "distinct": len(seen),
        "cross_page_dup_ids": dup,
        "title_counts": {k: v for k, v in tt.items() if v > 1},
        "pinned_first_page": (pages[0]["pinned_ids"] if pages and "pinned_ids" in pages[0] else []),
    }


def main() -> int:
    token = login("user000001", "Test@123456")
    res = {"base": BASE, "page_size": PAGE_SIZE, "rounds": []}
    for r in range(ROUNDS):
        res["rounds"].append(round_scan(token))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    for idx, r in enumerate(res["rounds"], 1):
        print(f"round{idx}: total={r['total']} fetched={r['fetched']} distinct={r['distinct']} "
              f"cross_page_dup={r['cross_page_dup_ids']} title_dup={r['title_counts']} "
              f"pinned_page1={len(r['pinned_first_page'])}")
    print("out:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
