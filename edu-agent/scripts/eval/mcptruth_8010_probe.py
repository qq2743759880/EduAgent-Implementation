# -*- coding: utf-8 -*-
"""MCP-TRUTH 8010 实测：MT-G1 search_knowledge 真实检索 + MT-G2 内置工具按名可达。"""
import json
import urllib.request

BASE = "http://127.0.0.1:8010"


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]


# 1) admin 登录
st, login = call("POST", "/api/auth/login", {"account": "adm02test", "password": "Test@123456"})
if st != 200:
    print("LOGIN_FAIL", st, login)
    raise SystemExit(1)
token = login["data"]["access_token"] if login["data"].get("access_token") else login["data"]["token"]
print("LOGIN_OK token_head=", str(token)[:12])

# 2) 内置工具按名可达（MT-G2）：calculator
st2, resp2 = call("POST", "/api/mcp/tools/test",
                  {"tool_name": "calculator", "args": {"a": 2, "b": 3, "op": "add"}}, token)
print("CALC_RAW=", json.dumps(resp2, ensure_ascii=False)[:800])
data2 = (resp2 or {}).get("data") if isinstance(resp2, dict) else {}
print("CALCULATOR status=", data2.get("status"), "content=", data2.get("content_text"))
assert data2.get("status") == "SUCCESS", f"calculator 非 SUCCESS: {data2}"

# 3) search_knowledge 真实检索（MT-G1）：非「未接入」空降级
st3, resp3 = call("POST", "/api/mcp/tools/test",
                  {"tool_name": "search_knowledge", "args": {"q": "线性代数 矩阵"}}, token)
data3 = (resp3 or {}).get("data") if isinstance(resp3, dict) else {}
print("SEARCH_KNOWLEDGE status=", data3.get("status"))
body = None
if data3.get("content_text"):
    try:
        body = json.loads(data3["content_text"])
    except Exception:
        body = {"_raw": data3["content_text"]}
print("SEARCH_BODY=", json.dumps(body, ensure_ascii=False)[:600])
assert body is not None, "search_knowledge 无返回体"
note = body.get("note", "")
assert "未接入" not in note, f"search_knowledge 仍空壳（{note}）"
print("RESULT_PASS")