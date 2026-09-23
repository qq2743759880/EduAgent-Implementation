#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TA4 回归探针: 以 admin 身份实测关键端点, 验证清理后演示面数据干净。"""
import os, json, urllib.request, urllib.error
from urllib.request import Request, build_opener, ProxyHandler

BASE = "http://127.0.0.1:9988"
OPENER = build_opener(ProxyHandler({}))  # 绕过 HTTP_PROXY, 避免 loopback 被吞

def req(method, path, token=None, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with OPENER.open(r, timeout=10) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:500]}

# 1) login
st, login = req("POST", "/api/auth/login", body={"account": "adm02test", "password": "Test@123456"})
print("LOGIN", st, "has_token=", bool(login.get("data", {}).get("access_token")))
tok = login.get("data", {}).get("access_token")
assert tok, "login failed"

def count_of(payload):
    # 兼容 {code,data:{items,total}} 或 {code,data:[...]} 或 直接 list
    d = payload.get("data")
    if isinstance(d, dict):
        if "total" in d:
            return d.get("total"), d.get("items") or d.get("list")
        if "items" in d:
            return len(d["items"]), d["items"]
    if isinstance(d, list):
        return len(d), d
    return None, d

checks = []
def probe(name, path, expect):
    st, p = req("GET", path, token=tok)
    total, items = count_of(p)
    ok = (total == expect) if isinstance(expect, int) else None
    print(f"[{name}] HTTP {st} total/len={total} expect={expect} -> {'PASS' if ok else 'CHECK'}")
    checks.append((name, st, total, expect, ok))

probe("RAG presets", "/api/admin/rag/presets", 3)
probe("MCP servers", "/api/mcp/servers", 1)
probe("MCP tools", "/api/mcp/tools", 4)
probe("MCP call-log", "/api/mcp/call-log", 0)
probe("MCP desc-review-log", "/api/mcp/description-review-log", 0)
probe("Knowledge tasks", "/api/knowledge/tasks", 136)

print("\n=== SUMMARY ===")
for c in checks:
    print(f"  {c[0]:20s} st={c[1]} got={c[2]} expect={c[3]} {'OK' if c[4] else '?'}")
