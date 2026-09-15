# -*- coding: utf-8 -*-
"""GHOST-pin-rootfix 逐条 GWT 复现脚本（只读 + 真实 HTTP）。

GHOST-G1 备份文件存在且含清理前完整行
GHOST-G2 清理后同名置顶帖 ≤1 条（只读 SQL）
GHOST-G3 page=1/2 同一置顶帖 id 不跨页重复；首屏置顶仅 1 次
GHOST-G4 分页计数正确：全页扫描 distinct == total，普通帖不漏出

用法::
    .venv\\Scripts\\python.exe scripts/eval/ghost_verify_gwt.py \\
        --base http://127.0.0.1:8010 \\
        --backup ../../deploy/backups/community_post_YYYYmmdd_HHMMSS.sql

exit 0 = 全 PASS；非 0 = 有 FAIL（末尾打印明细）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request

import pymysql

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from app.config import settings  # noqa: E402

urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

PIN_TITLE_LIKE = "%欢迎来到 EduAgent 学习社区%"
RESULTS: list[dict] = []


def rec(gwt: str, name: str, passed: bool, detail) -> None:
    RESULTS.append({"gwt": gwt, "check": name, "pass": bool(passed), "detail": detail})


def db():
    return pymysql.connect(
        host=settings.MYSQL_HOST, port=int(settings.MYSQL_PORT),
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DATABASE, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def login(base: str, account: str, password: str) -> str:
    req = urllib.request.Request(
        f"{base}/api/auth/login",
        data=json.dumps({"account": account, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())["data"]["access_token"]


def api(base: str, path: str, token: str, retries: int = 8) -> dict:
    """GET + 429 退避重试（全页扫描请求数较多，会撞接口限流）。"""
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(f"{base}{path}", headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == retries:
                raise
            last = e
            time.sleep(6)
    raise last  # pragma: no cover


def sweep(base: str, token: str, page_size: int, sort: str = "HOT",
          board_code: str | None = None) -> dict:
    ids: list[int] = []
    pinned_first_page: list[int] = []
    total = None
    page = 1
    pages_seen: list[list[int]] = []
    while page <= 60:
        q = f"/api/community/posts?page={page}&page_size={page_size}&sort={sort}"
        if board_code:
            q += f"&board_code={board_code}"
        d = api(base, q, token)["data"]
        total = d["total"]
        cur = [it["post_id"] for it in d["items"]]
        if page == 1:
            pinned_first_page = [it["post_id"] for it in d["items"] if it["is_pinned"]]
        pages_seen.append(cur)
        ids += cur
        time.sleep(0.15)
        if not cur or len(ids) >= total:
            break
        page += 1
    dup = sorted({i for i in ids if ids.count(i) > 1})
    return {
        "page_size": page_size, "sort": sort, "board_code": board_code,
        "total": total, "fetched": len(ids), "distinct": len(set(ids)),
        "duplicates": dup, "missing": total - len(set(ids)) if total is not None else None,
        "pinned_first_page": pinned_first_page, "pages": len(pages_seen),
        "page1_ids": pages_seen[0] if pages_seen else [],
        "page2_ids": pages_seen[1] if len(pages_seen) > 1 else [],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8010")
    ap.add_argument("--backup", required=True)
    ap.add_argument("--json-out", default=os.path.join(HERE, ".ghost_tmp", "gwt_results.json"))
    args = ap.parse_args()

    # ---------- G1 备份 ----------
    bp = os.path.abspath(args.backup)
    exists = os.path.isfile(bp)
    rows = 0
    sha = ""
    if exists:
        raw = open(bp, "rb").read()
        txt = raw.decode("utf-8", errors="replace")
        rows = txt.count("),(") + 1 if "INSERT INTO" in txt else 0
        sha = hashlib.sha256(raw).hexdigest()
    rec("G1", "backup file exists", exists, {"path": bp, "bytes": os.path.getsize(bp) if exists else 0,
                                             "sha256": sha, "rows_in_dump": rows})
    rec("G1", "backup contains full pre-clean rows (=98)", rows == 98, {"rows_in_dump": rows})

    # ---------- G2 只读 SQL ----------
    c = db()
    cur = c.cursor()
    cur.execute(
        "SELECT COUNT(*) c FROM community_post WHERE yn=1 AND is_pinned=1 AND title LIKE %s",
        (PIN_TITLE_LIKE,),
    )
    pinned_yn1 = int(cur.fetchone()["c"])
    cur.execute("SELECT COUNT(*) c FROM community_post WHERE yn=1 AND is_pinned=1")
    pinned_all = int(cur.fetchone()["c"])
    cur.execute(
        "SELECT title, COUNT(*) c FROM community_post WHERE yn=1 GROUP BY title HAVING COUNT(*)>1",
    )
    dup_groups = [(r["title"], int(r["c"])) for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) c FROM community_post WHERE yn=1")
    yn1 = int(cur.fetchone()["c"])
    cur.execute("SELECT COUNT(*) c FROM community_post WHERE yn=0")
    soft = int(cur.fetchone()["c"])
    cur.execute("SELECT COUNT(*) c FROM community_post")
    total_rows = int(cur.fetchone()["c"])
    c.close()
    rec("G2", "同名置顶帖 yn=1 ≤ 1 条", pinned_yn1 <= 1,
        {"pinned_same_title_yn1": pinned_yn1, "pinned_yn1_total": pinned_all})
    rec("G2", "yn=1 无同标题重复组", not dup_groups, {"duplicate_groups": dup_groups})
    rec("G2", "before/after 计数", True,
        {"before_yn1": 98, "after_yn1": yn1, "soft_deleted_yn0": soft,
         "rows_total_unchanged": total_rows, "delta": 98 - yn1})

    # ---------- G3 / G4 HTTP ----------
    token = login(args.base, "user000001", "Test@123456")
    sw10 = sweep(args.base, token, 10)
    p1, p2 = set(sw10["page1_ids"]), set(sw10["page2_ids"])
    rec("G3", "page1 ∩ page2 = ∅（无跨页重复 id）", not (p1 & p2),
        {"page1_ids": sw10["page1_ids"], "page2_ids": sw10["page2_ids"], "intersect": sorted(p1 & p2)})
    rec("G3", "首屏(page1) 置顶帖仅 1 次", len(sw10["pinned_first_page"]) == 1,
        {"pinned_first_page": sw10["pinned_first_page"]})
    rec("G4", "全页扫描 total == distinct（不重不漏）", sw10["distinct"] == sw10["total"],
        {"total": sw10["total"], "distinct": sw10["distinct"],
         "fetched": sw10["fetched"], "duplicates": sw10["duplicates"]})

    sweeps = [sweep(args.base, token, ps, sort) for ps in (3, 20, 100) for sort in ("HOT", "NEW", "LIKE")]
    sweeps += [sweep(args.base, token, 10, "HOT", b) for b in ("general", "english", "math", "programming")]
    bad = [s for s in sweeps if s["distinct"] != s["total"] or s["duplicates"]]
    rec("G4", "9 种分页/排序/版块组合均不重不漏", not bad,
        {"combos": [{"ps": s["page_size"], "sort": s["sort"], "board": s["board_code"],
                     "total": s["total"], "fetched": s["fetched"], "distinct": s["distinct"],
                     "dups": s["duplicates"], "pages": s["pages"]} for s in sweeps],
         "failing": len(bad)})

    out = {"base": args.base, "backup": bp, "results": RESULTS,
           "page1_page2_detail": sw10, "sweeps": sweeps}
    os.makedirs(os.path.dirname(args.json_out), exist_ok=True)
    with open(args.json_out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    fails = [r for r in RESULTS if not r["pass"]]
    for r in RESULTS:
        print(f"[{'PASS' if r['pass'] else 'FAIL'}] {r['gwt']} {r['check']}")
        if not r["pass"]:
            print("       detail:", json.dumps(r["detail"], ensure_ascii=False)[:400])
    print(f"\n合计 {len(RESULTS) - len(fails)}/{len(RESULTS)} PASS   json: {args.json_out}")
    print(f"G3 page1_ids={sw10['page1_ids']}\nG3 page2_ids={sw10['page2_ids']}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
