# -*- coding: utf-8 -*-
"""task114/115 契约冻结 C-A/C-B 真实 HTTP 抓包（首次，trust-but-verify）。port 8000 实况。"""
import json
import sys
import urllib.request
import urllib.parse

BASE = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0


def log(ok, name, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"[PASS] {name} {detail}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} {detail}")


def req(method, path, token=None, body=None, raw_out=False):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            status = resp.status
            ct = resp.headers.get("Content-Type", "")
            text = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status = e.code
        ct = e.headers.get("Content-Type", "")
        text = e.read().decode("utf-8", "replace")
    if raw_out:
        return status, text, ct
    try:
        return status, json.loads(text), ct
    except Exception:
        return status, {"__raw__": text[:300]}, ct


def is_shell(j):
    return isinstance(j, dict) and {"code", "message", "data"} <= set(j.keys())


def shell_ok(name, status, j, expect=200):
    ok = (status == expect) and is_shell(j) and j.get("code") == 0
    log(ok, name, f"http={status} keys={sorted(j.keys()) if isinstance(j,dict) else j} code={j.get('code') if isinstance(j,dict) else None}")
    return j.get("data") if ok else None


# ---- login ----
s, j, _ = req("POST", "/api/auth/login", body={"account": "user000001", "password": "Test@123456"})
assert j.get("code") == 0, f"login fail {s} {j}"
TOK = j["data"]["access_token"]
print(f"== login ok, token len={len(TOK)}\n")

print("===== A. C-A 响应壳全站 =====")
_s, _j, _ = req("GET", "/api/users/me", token=TOK)
d = shell_ok("/api/users/me (student)", _s, _j)
if d:
    log(all(k in d for k in ["user_id","account","username","nickname","role"]),
        "users/me 必需字段", f"keys={sorted(d.keys())}")
    log(d.get("role") == "student", "role string=student", f"role={d.get('role')!r}")
    log(isinstance(d.get("learning_goal"), list), "learning_goal list", f"={d.get('learning_goal')}")
    log(isinstance(d.get("subject_preferences"), list), "subject_preferences list", f"={d.get('subject_preferences')}")
    log(not any(c.isupper() for c in "".join(d.keys())), "no camelCase keys", "")

# interactive quiz: probe the REAL path variant
print("\n-- interactive quiz 真实前缀判定 --")
for p in ["/api/interactive/quiz/next?subject_code=math", "/api/quiz/next?subject_code=math"]:
    s, j, _ = req("GET", p, token=TOK)
    print(f"  probe {p} -> http={s} code={j.get('code') if isinstance(j,dict) else None} keys={sorted(j.keys())[:8] if isinstance(j,dict) else j}")
s, j, _ = req("GET", "/api/interactive/quiz/types", token=TOK)
shell_ok("/api/interactive/quiz/types", s, j)
s, j, _ = req("GET", "/api/vocab/daily", token=TOK)
shell_ok("/api/vocab/daily", s, j)
s, j, _ = req("GET", "/api/recommend/next?top_n=2", token=TOK)
shell_ok("/api/recommend/next", s, j)
s, j, _ = req("GET", "/api/mindmap/course/1", token=TOK)
shell_ok("/api/mindmap/course/1", s, j)
s, j, _ = req("GET", "/api/progress/dashboard?days=7", token=TOK)
dd = shell_ok("/api/progress/dashboard", s, j)
if dd:
    log(all(k in dd for k in ["total_questions_attempted","total_questions_correct","active_courses_count"]),
        "dashboard 扩展字段", f"keys={sorted(dd.keys())}")
    print(f"    dashboard 值: total_questions_attempted={dd.get('total_questions_attempted')} active_courses_count={dd.get('active_courses_count')}")

# 普通壳端点对照（已 ok() 的 auth/me）不应二次包裹
s, j, _ = req("GET", "/api/auth/me", token=TOK)
dme = shell_ok("/api/auth/me", s, j)
if dme:
    log(not is_shell(dme), "auth/me data 非嵌套壳（幂等）", f"data keys={sorted(dme.keys())[:6]}")

print("\n===== B. C-B 分页 + SSE =====")
s, j, _ = req("GET", "/api/series?page=1&page_size=2", token=TOK)
d = shell_ok("/api/series?page=1&page_size=2", s, j)
if d:
    log(isinstance(d.get("total"), int) and d.get("total") >= 0, "total int>=0", f"total={d.get('total')}")
    log(d.get("page") == 1, "page==1", f"page={d.get('page')}")
    log(d.get("page_size") == 2, "page_size==2", f"page_size={d.get('page_size')}")
    log(isinstance(d.get("items"), list), "items is array", f"len={len(d.get('items'))}")
    log("page_meta" not in d, "NO page_meta (C2 已移除)", "")

# SSE 第一段（连接前失败）：garbage token → 同步 HTTP 401 非 SSE
s, text, ct = req("POST", "/api/chat/stream", token="garbage.token.here",
                  body={"query": "x", "stream": True}, raw_out=True)
log(s == 401 and "event:" not in text and "code" in text, "SSE 第一段: 连接前失败=同步HTTP401",
    f"http={s} ct={ct.split(';')[0]} body={text[:120]}")

# SSE 第二段（建连后 error 事件）不易在 live 稳定触发：用既有契约单测 + 代码证据登记
print("\n  [note] SSE 第二段 error 事件（建连后）无法在 live 8000 稳定注入 LLM 故障 → 由契约单测 + router 代码证据覆盖（见 task115 §2.4/§2.5 标注'未强制破坏性触发'）")

print(f"\n========== RESULT: PASS={PASS} FAIL={FAIL} ==========")
sys.exit(1 if FAIL else 0)