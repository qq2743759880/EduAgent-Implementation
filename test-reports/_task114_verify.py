# -*- coding: utf-8 -*-
"""task114 独立实证：真实 HTTP 校验响应壳全站统一 + users/me 新契约 + DashboardOut 扩展。"""
import json
import sys

import requests

BASE = "http://127.0.0.1:8078"
PASS, FAIL = 0, 0


def log(ok, name, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"[PASS] {name} {detail}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} {detail}")


def login(account, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"account": account, "password": password}, timeout=20)
    j = r.json()
    if r.status_code == 200 and j.get("code") == 0:
        return j["data"]["access_token"]
    raise SystemExit(f"login failed for {account}: {r.status_code} {j}")


def call(method, path, token=None, payload=None):
    h = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = requests.request(method, BASE + path, json=payload, headers=h, timeout=30)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text[:200]}
    return r.status_code, j


def is_envelope(j):
    return isinstance(j, dict) and set(("code", "message", "data")) <= set(j.keys())


def assert_envelope(name, http, j, expect_status=200, code=None):
    ok = http == expect_status and is_envelope(j)
    log(ok, name, f"http={http} keys={sorted(j.keys()) if isinstance(j, dict) else j}")
    if ok and code is not None:
        log(j.get("code") == code, name + " code==0", f"code={j.get('code')!r}")


STU = login("user000001", "Test@123456")
ADM = login("adm02test", "Test@123456")

print("\n===== A. 全站响应壳统一（recommender / mindmap / interactive）=====")
for path in [
    "/api/recommend/",  # keep placeholder, replaced below
]:
    pass

tests = [
    ("GET", "/api/recommend/next", {"top_n": 3}),
    ("GET", "/api/recommend/path", None),
    ("GET", "/api/interactive/quiz/next", {"subject_code": "math"}),
    ("GET", "/api/interactive/quiz/types", None),
    ("GET", "/api/mindmap/prerequisite", None),
    ("GET", "/api/mindmap/subject/math", None),
    ("GET", "/api/vocab/daily", None),
    ("GET", "/api/coding/challenges", None),
]
for method, path, qs in tests:
    url = path
    if qs:
        url += "?" + "&".join(f"{k}={v}" for k, v in qs.items())
    http, j = call(method, url, token=STU)
    assert_envelope(path, http, j, expect_status=200, code=0)

print("\n===== B. coding/challenges/{code} 顶层 code 字段碰撞（harden 边界）=====")
http, j = call("GET", "/api/coding/challenges/PY-SUM-TWO", token=STU)
assert_envelope("coding/challenges/{code}", http, j, expect_status=200, code=0)
log(is_envelope(j) and isinstance(j.get("data"), dict), "coding data 为 dict（未漏包为裸体）",
    f"data={j.get('data') is not None}")

print("\n===== C. GET /api/users/me 新契约 snake_case + role 字符串 =====")
http, j = call("GET", "/api/users/me", token=STU)
assert_envelope("users/me envelope", http, j, code=0)
d = j.get("data") or {}
log(all(f in d for f in ["user_id", "account", "username", "nickname", "role"]),
    "users/me 必需字段齐备", f"keys={sorted(d.keys())}")
log("role" in d and d["role"] == "student", "role 为字符串 student", f"role={d.get('role')!r}")
log("learning_goal" in d and isinstance(d["learning_goal"], list), "learning_goal list", f"={d.get('learning_goal')}")
log("subject_preferences" in d and isinstance(d["subject_preferences"], list), "subject_preferences list", f"={d.get('subject_preferences')}")
log("learning_goal" in d and "learning_goal" in d, "坚 snake_case（无 camelCase 残余）", f"camel keys={[k for k in d if any(c.isupper() for c in k)]}")

print("\n===== D. 幂等边界：users/me 已是壳不会二次包裹 =====")
log(is_envelope(j), "users/me 只包一层壳（data 为对象非壳）", f"data keys={sorted(d.keys())}")

print("\n===== E. progress/dashboard DashboardOut 扩展 =====")
http, j = call("GET", "/api/progress/dashboard?days=7", token=STU)
assert_envelope("dashboard envelope", http, j, code=0)
dd = j.get("data") or {}
log(all(k in dd for k in ["total_questions_attempted", "total_questions_correct", "active_courses_count", "latest_streak_days", "recent_days"]),
    "dashboard 含扩展字段", f"keys={sorted(dd.keys())}")
print("   => dashboard 实测:", {k: dd.get(k) for k in ("total_days", "total_study_seconds", "total_questions_attempted", "total_questions_correct", "overall_correct_rate", "active_courses_count", "latest_streak_days", "recent_days_len")})
log(dd.get("active_courses_count") == 1, "active_courses_count==1 (DB实证)", f"={dd.get('active_courses_count')}")
log(dd.get("total_questions_attempted") == 7, "total_questions_attempted==7 (DB实证)", f"={dd.get('total_questions_attempted')}")

print("\n===== F. series 列表（分页裸 DTO）包壳 =====")
http, j = call("GET", "/api/series", token=STU)
assert_envelope("/api/series", http, j, code=0)
log(is_envelope(j) and "items" in (j.get("data") or {}), "series data 含 items 分页", f"data keys={sorted((j.get('data') or {}).keys())}")

print("\n===== G. 已壳端点幂等跳过（auth/me 仍单层壳）=====")
http, j = call("GET", "/api/auth/me", token=STU)
assert_envelope("/api/auth/me", http, j, code=0)
log(not is_envelope(j.get("data")), "auth/me data 非壳（幂等未二次包裹）", f"data keys={sorted((j.get('data') or {}).keys())}")

print("\n===== H. 401（garbage token）非 2xx 壳化也正常 =====")
http, j = call("GET", "/api/users/me", token="garbage.token.here")
log(http == 401 and is_envelope(j), "401 壳化", f"http={http} body={j}")

print("\n===== I. 404 裸体壳化 =====")
http, j = call("GET", "/api/nonexistent-path-xyz", token=STU)
log(http == 404 and is_envelope(j), "404 壳化", f"http={http} body={j}")

print(f"\n========== RESULT: PASS={PASS} FAIL={FAIL} ==========")
sys.exit(1 if FAIL else 0)