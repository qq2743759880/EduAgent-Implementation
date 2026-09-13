# -*- coding: utf-8 -*-
"""EduAgent 独立接口验收测试（be-tester 独立实证，不采信任何报告）。
用法: python interface_acceptance_sweep.py
输出: interface-acceptance.md
"""
import json
import time
import re
import os
import sys

import requests

BASE = "http://127.0.0.1:8000"
ROUTES_FILE = os.path.join(os.path.dirname(__file__), "_backend_routes.txt")
FRONT_FILE = os.path.join(os.path.dirname(__file__), "..", "edu-frontend", "test-reports", "_frontend_api.txt")
REPORT_FILE = os.path.join(os.path.dirname(__file__), "interface-acceptance.md")

SLEEP = 0.03
TOTAL_REQUESTS = 0
TOTAL_START = time.time()

# ── 真实素材 ID（已从 MySQL 只读验证）──────────────────────────
ID = {
    "series_id": "1",
    "cohort_id": "1",
    "module_id": "1",
    "session_id": "190",          # session_asset.id
    "video_id": "1",
    "bank_id": "439",
    "question_id": "1",
    "exam_id": "1",
    "server_id": "3",
    "log_id": "2",
    "refund_id": "1",
    "user_id": "2",               # user000002（非管理员本人）
    "post_id": "74",
    "comment_id": "1",
    "trace_id": "test-trace-abc",
    "subject_code": "math",
    "task_id": "nonexistent-task-id",
    "entity_id": "1",
    "tenant_id": "1",
    "payment_no": "P-1-260821164000-a4db85",
    "order_no": "ORD0000000001",
    "ticket_id": "1",
    "code": "PY-SUM-TWO",
    "custom_code": "PY-SUM-TWO",
}
# 后端参数名 → 值（覆盖默认映射）
PARAM_ALIAS = {
    "cohort_id": "1", "module_id": "1", "series_id": "1", "session_id": "190",
    "video_id": "1", "bank_id": "439", "question_id": "1", "exam_id": "1",
    "server_id": "3", "log_id": "2", "refund_id": "1", "user_id": "2",
    "post_id": "74", "comment_id": "1", "trace_id": "test-trace-abc",
    "subject_code": "math", "task_id": "no-such-task", "entity_id": "1",
    "tenant_id": "1", "payment_no": "P-1-260821164000-a4db85",
    "order_no": "ORD0000000001", "ticket_id": "1", "code": "PY-SUM-TWO",
    "custom_code": "PY-SUM-TWO",
}


def resolve_path(path):
    return re.sub(r"\{(\w+)\}", lambda m: PARAM_ALIAS.get(m.group(1), "1"), path)


def call(method, path, token=None, payload=None, raw_payload=False, timeout=15):
    """真实 HTTP 调用。返回 (http_status, body_or_text, ok_shell)"""
    global TOTAL_REQUESTS
    TOTAL_REQUESTS += 1
    url = BASE + path
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=timeout)
        elif method == "DELETE":
            r = requests.delete(url, headers=headers, timeout=timeout)
        else:
            data = payload if raw_payload else json.dumps(payload if payload is not None else {})
            r = requests.request(method, url, headers=headers, data=data, timeout=timeout)
    except requests.exceptions.RequestException as e:
        return 0, {"network_error": str(e)}, False
    try:
        body = r.json()
    except Exception:
        body = r.text[:300]
    ok_shell = isinstance(body, dict) and "code" in body and "message" in body and "data" in body
    time.sleep(SLEEP)
    return r.status_code, body, ok_shell


def classify(http, body):
    """返回 (verdict, note)"""
    if http == 0:
        return "NETERR", "网络错误"
    if not isinstance(body, dict):
        return "NONJSON", f"非 JSON: {str(body)[:60]}"
    if "code" not in body:
        return "NOSHELL", f"缺响应壳: {str(body)[:120]}"
    if body.get("code") == 0:
        return "OK", "成功 code=0"
    code = body.get("code")
    if isinstance(code, str):
        return "BIZ", f"业务错误 code={code}"
    return "BADCODE", f"code 类型异常: {code!r}"


def login(account, password):
    return call("POST", "/api/auth/login", payload={"account": account, "password": password})


def get_token(account, password):
    http, body, _ = login(account, password)
    if http == 200 and isinstance(body, dict) and body.get("code") == 0:
        return body["data"].get("access_token")
    return None


# ── 契约数据读取 ──────────────────────────────────────────────
def load_routes():
    routes = []
    with open(ROUTES_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(\w+)\s+(/\S+)$", line)
            if m:
                routes.append((m.group(1).upper(), m.group(2)))
    return routes


def load_front():
    out = []
    with open(FRONT_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(line)
    return out


# ═══════════════════════════════════════════════════════════
# 1. 登录鉴权（三种角色）
# ═══════════════════════════════════════════════════════════
def test_auth(rows):
    accounts = {
        "admin": ("adm02test", "Test@123456"),
        "manager": ("mgr01test", "Test@123456"),
        "student": ("user000001", "Test@123456"),
    }
    tokens = {}
    for role, (acc, pwd) in accounts.items():
        http, body, shell = login(acc, pwd)
        ok = http == 200 and shell and body.get("code") == 0 and body.get("data", {}).get("access_token")
        rows.append({
            "method": "POST", "path": "/api/auth/login", "role": role, "http": http,
            "code": body.get("code") if isinstance(body, dict) else None,
            "verdict": "OK" if ok else "FAIL", "note": f"access_token={'有' if ok else '无'}",
        })
        tokens[role] = get_token(acc, pwd) if ok else None

    # 错误密码 → 错误壳
    http, body, shell = call("POST", "/api/auth/login", payload={"account": "adm02test", "password": "wrongpass"})
    rows.append({
        "method": "POST", "path": "/api/auth/login(bad-pwd)", "role": "admin", "http": http,
        "code": body.get("code") if isinstance(body, dict) else None,
        "verdict": "OK" if shell and isinstance(body.get("code"), str) and body.get("data") is None else "FAIL",
        "note": "错误密码应返回错误壳 code=str,data=null",
    })
    # refresh 用无效 token
    http, body, shell = call("POST", "/api/auth/refresh", payload={"refresh_token": "bad.token.value"})
    rows.append({
        "method": "POST", "path": "/api/auth/refresh(bad-token)", "role": "-", "http": http,
        "code": body.get("code") if isinstance(body, dict) else None,
        "verdict": "OK" if shell and isinstance(body.get("code"), str) else "FAIL",
        "note": "无效 refresh token 应返回错误壳",
    })
    return tokens


# ═══════════════════════════════════════════════════════════
# 2. 管理端全接口遍历（admin token）
# ═══════════════════════════════════════════════════════════
ADMIN_WRITE_PAYLOAD = {
    "/api/admin/courses/series": {"institution_id": 1, "delivery_mode": "online_recorded",
                                  "series_code": "itest-series-1", "series_name": "ITest系列",
                                  "sale_status": "draft", "created_by": 100003},
    "/api/admin/courses/cohorts": {"institution_id": 1, "series_id": 1, "head_teacher_id": 100003,
                                   "cohort_code": "itest-cohort-1", "cohort_name": "ITest班次",
                                   "sale_price": 100, "max_student_count": 50},
    "/api/admin/courses/modules": {"cohort_id": 1, "module_code": "itest-mod-1", "module_name": "ITest模块",
                                   "lesson_count": 1, "total_hours": 1, "stage_no": 99},
    "/api/admin/courses/sessions": {"asset_code": "itest-sess-1", "asset_name": "ITest课次",
                                    "asset_type": "lecture"},
    "/api/admin/questions/banks": {"bank_code": "itest-bank-1", "bank_name": "ITest题库",
                                   "subject_code": "math", "question_count": 0},
    "/api/admin/questions/questions": {"bank_id": 439, "subject_code": "math", "question_type": "single_choice",
                                      "stem": "ITest题干", "options": [{"key": "A", "content": "a"}],
                                      "answer": ["A"], "difficulty": 3},
    "/api/admin/questions/exams": {"exam_code": "itest-exam-1", "exam_name": "ITest试卷",
                                   "subject_code": "math", "total_score": 100, "pass_score": 60,
                                   "duration_minutes": 60},
    "/api/admin/rag/presets": {"preset_code": "itest-preset-1", "preset_name": "ITest预设",
                               "prompt_template": "test", "chunk_size": 500, "overlap": 50},
    "/api/admin/users/{user_id}/role": {"role": "student"},
    "/api/admin/users/{user_id}/status": {"status": 1},
}


def test_admin(rows):
    routes = load_routes()
    admin_routes = [(m, p) for m, p in routes if p.startswith("/api/admin/")]
    for method, path in admin_routes:
        resolved = resolve_path(path)
        verdict_note = {}
        if method in ("POST", "PUT", "PATCH"):
            payload = ADMIN_WRITE_PAYLOAD.get(path, {"probe": "itest"})
            http, body, shell = call(method, resolved, token=None, payload=payload)
            verdict_note["noauth"] = (http, classify(http, body)[0])
            http, body, shell = call(method, resolved, token=TOKENS["admin"], payload=payload)
            v, n = classify(http, body)
            rows.append({
                "method": method, "path": path, "role": "admin", "http": http,
                "code": body.get("code") if isinstance(body, dict) else None,
                "verdict": v, "note": n,
            })
            # 破坏性/写操作的 noauth 记录单独汇总
            if verdict_note["noauth"][0] not in (401, 403):
                rows[-1]["note"] += f" | 无token={verdict_note['noauth'][0]}"
        elif method == "DELETE":
            # 用不存在的 id，避免破坏数据；仍能证明路由存在 + 壳
            resolved = re.sub(r"\d+$", "999999999", resolved)
            http, body, shell = call(method, resolved, token=None)
            na = classify(http, body)[0]
            http, body, shell = call(method, resolved, token=TOKENS["admin"])
            v, n = classify(http, body)
            rows.append({
                "method": method, "path": path, "role": "admin", "http": http,
                "code": body.get("code") if isinstance(body, dict) else None,
                "verdict": v, "note": n + (" | 无token=%s" % na if na not in ("OK", "BIZ") else ""),
            })
        else:  # GET
            http, body, shell = call("GET", resolved, token=TOKENS["admin"])
            v, n = classify(http, body)
            rows.append({
                "method": "GET", "path": path, "role": "admin", "http": http,
                "code": body.get("code") if isinstance(body, dict) else None,
                "verdict": v, "note": n,
            })
    return admin_routes


# ═══════════════════════════════════════════════════════════
# 3. 用户端接口（前端引用 + 用户相关）
# ═══════════════════════════════════════════════════════════
USER_ROUTES = [
    # (method, path, role)
    ("GET", "/api/auth/me", "student"),
    ("POST", "/api/auth/register", "student"),
    ("GET", "/api/coupons", "student"),
    ("GET", "/api/coupons/templates", "student"),
    ("GET", "/api/favorites", "student"),
    ("POST", "/api/favorites", "student"),
    ("DELETE", "/api/favorites/{series_id}", "student"),
    ("GET", "/api/progress/courses", "student"),
    ("GET", "/api/progress/dashboard", "student"),
    ("POST", "/api/progress/video/tick-batch", "student"),
    ("POST", "/api/progress/homework/submit", "student"),
    ("POST", "/api/progress/exam/submit", "student"),
    ("GET", "/api/gamification/me/badges", "student"),
    ("GET", "/api/gamification/me/points", "student"),
    ("GET", "/api/gamification/rankings", "student"),
    ("POST", "/api/gamification/me/check-badges", "student"),
    ("GET", "/api/community/posts", "student"),
    ("GET", "/api/community/posts/{post_id}", "student"),
    ("GET", "/api/community/posts/{post_id}/comments", "student"),
    ("POST", "/api/community/posts/{post_id}/like", "student"),
    ("POST", "/api/community/posts/{post_id}/favorite", "student"),
    ("GET", "/api/chat/sessions", "student"),
    ("POST", "/api/chat", "student"),
    ("POST", "/api/chat/search", "student"),
    ("POST", "/api/chat/sessions", "student"),
    ("GET", "/api/trade/orders", "student"),
    ("GET", "/api/trade/order/{order_no}", "student"),
    ("GET", "/api/trade/payments", "student"),
    ("GET", "/api/trade/after_sales/tickets", "student"),
    ("GET", "/api/trade/after_sales/ticket/{ticket_id}", "student"),
    ("POST", "/api/trade/coupon/receive", "student"),
    ("GET", "/api/users/me", "student"),
    ("GET", "/api/users/me/profile", "student"),
    ("PUT", "/api/users/me/profile", "student"),
    ("GET", "/api/users/me/student-profile", "student"),
    ("GET", "/api/users/me/learning-summary", "student"),
    ("GET", "/api/enrollments/me/cohorts", "student"),
    ("GET", "/api/enrollments/me/cohorts/{cohort_id}", "student"),
    ("GET", "/api/enrollments/me/cohorts/{cohort_id}/progress", "student"),
    ("GET", "/api/enrollments/me/cohorts/{cohort_id}/status", "student"),
    ("GET", "/api/series", "student"),
    ("GET", "/api/series/{series_id}", "student"),
    ("GET", "/api/series/{series_id}/cohorts", "student"),
    ("GET", "/api/cohorts/{cohort_id}", "student"),
    ("GET", "/api/cohorts/{cohort_id}/modules", "student"),
    ("GET", "/api/study/courses/{series_id}/outline", "student"),
    ("GET", "/api/study/courses/{series_id}/access", "student"),
    ("GET", "/api/study/sessions/{session_id}", "student"),
    ("POST", "/api/study/sessions/{session_id}/complete", "student"),
    ("GET", "/api/recommend/next", "student"),
    ("GET", "/api/recommend/path", "student"),
    ("GET", "/api/interactive/quiz/next", "student"),
    ("GET", "/api/interactive/quiz/types", "student"),
    ("POST", "/api/interactive/quiz/submit", "student"),
    ("GET", "/api/interactive/quiz/wrong-book", "student"),
    ("GET", "/api/coding/challenges", "student"),
    ("GET", "/api/coding/challenges/{code}", "student"),
    ("POST", "/api/coding/run", "student"),
    ("POST", "/api/coding/submit", "student"),
    ("POST", "/api/math/explain", "student"),
    ("GET", "/api/vocab/daily", "student"),
    ("GET", "/api/vocab/progress", "student"),
    ("POST", "/api/vocab/recall", "student"),
    ("GET", "/api/mindmap/me/{series_id}", "student"),
    ("GET", "/api/mindmap/course/{series_id}", "student"),
    ("GET", "/api/mindmap/subject/{subject_code}", "student"),
    ("GET", "/api/mindmap/prerequisite", "student"),
    # mcp / knowledge / memory / metrics → admin
    ("GET", "/api/mcp/servers", "admin"),
    ("GET", "/api/mcp/servers/{server_id}", "admin"),
    ("GET", "/api/mcp/tools", "admin"),
    ("GET", "/api/mcp/call-log", "admin"),
    ("GET", "/api/mcp/call-log/{log_id}", "admin"),
    ("GET", "/api/mcp/description-review-log", "admin"),
    ("GET", "/api/mcp/sessions", "admin"),
    ("POST", "/api/mcp/servers", "admin"),
    ("POST", "/api/mcp/health-scan", "admin"),
    ("POST", "/api/mcp/servers/{server_id}/discover", "admin"),
    ("GET", "/api/mcp/servers/{server_id}/tools", "admin"),
    ("GET", "/api/knowledge/partitions", "admin"),
    ("GET", "/api/knowledge/tasks", "admin"),
    ("POST", "/api/knowledge/admin/upload", "admin"),
    ("POST", "/api/knowledge/upload", "admin"),
    ("GET", "/api/memory/history/{entity_id}", "admin"),
    ("POST", "/api/memory/rewind", "admin"),
    ("GET", "/api/metrics/cache-context-dashboard", "admin"),
    ("GET", "/api/metrics/otel", "admin"),
    ("GET", "/api/metrics/trace/{trace_id}", "admin"),
    ("GET", "/api/refunds", "admin"),
    ("POST", "/api/refunds", "admin"),
    ("POST", "/api/refunds/{refund_id}/cancel", "admin"),
    ("GET", "/api/knowledge/status/{task_id}", "admin"),
    ("GET", "/api/admin/rag/collections", "admin"),
    ("POST", "/api/admin/rag/search", "admin"),
    ("GET", "/", "anon"),
    ("GET", "/health", "anon"),
    ("GET", "/health/detail", "anon"),
    ("GET", "/health/warmup", "anon"),
]

USER_PAYLOAD = {
    "/api/auth/register": {"account": "itest-newuser", "password": "Test@123456", "nickname": "ITest"},
    "/api/favorites": {"series_id": 2},
    "/api/progress/video/tick-batch": {"records": [{"session_id": 190, "seconds": 30}]},
    "/api/progress/homework/submit": {"homework_id": 1, "answers": [{"question_id": 1, "answer": "A"}]},
    "/api/progress/exam/submit": {"exam_id": 1, "answers": [{"question_id": 1, "answer": "A"}]},
    "/api/community/posts/{post_id}/like": {},
    "/api/community/posts/{post_id}/favorite": {},
    "/api/chat": {"message": "你好", "session_id": None},
    "/api/chat/search": {"query": "课程"},
    "/api/chat/sessions": {"title": "ITest会话"},
    "/api/trade/coupon/receive": {"coupon_id": 1},
    "/api/users/me/profile": {"nickname": "ITest昵称", "gender": "unknown"},
    "/api/interactive/quiz/submit": {"quiz_id": 1, "answers": [{"question_id": 1, "answer": "A"}]},
    "/api/coding/run": {"code": "print(1)", "language": "python"},
    "/api/coding/submit": {"code": "print(1)", "language": "python", "challenge_code": "PY-SUM-TWO"},
    "/api/math/explain": {"expression": "1+1"},
    "/api/vocab/recall": {"word_ids": [1]},
    "/api/mcp/servers": {"name": "itest-server", "server_url": "http://localhost:9/mcp",
                         "transport": "sse", "description": "itest"},
    "/api/mcp/servers/{server_id}/discover": {},
    "/api/knowledge/admin/upload": {"title": "itest-doc", "content": "test"},
    "/api/knowledge/upload": {"title": "itest-doc", "content": "test"},
    "/api/memory/rewind": {"entity_id": 1},
    "/api/refunds": {"order_no": "ORD0000000001", "reason": "itest"},
    "/api/admin/rag/search": {"query": "课程", "top_k": 5},
}


def test_users(rows):
    for method, path, role in USER_ROUTES:
        token = TOKENS.get(role)
        resolved = resolve_path(path)
        payload = USER_PAYLOAD.get(path, {"probe": "itest"})
        http, body, shell = call(method, resolved, token=token, payload=payload)
        v, n = classify(http, body)
        rows.append({
            "method": method, "path": path, "role": role, "http": http,
            "code": body.get("code") if isinstance(body, dict) else None,
            "verdict": v, "note": n,
        })


# ═══════════════════════════════════════════════════════════
# 4. 契约缺口对比
# ═══════════════════════════════════════════════════════════
def contract_gap():
    routes = load_routes()
    front = load_front()
    backend_paths = set()
    for m, p in routes:
        norm = re.sub(r"\{(\w+)\}", "{}", p)
        backend_paths.add(norm)
    front_norm = set()
    for p in front:
        norm = re.sub(r"\{(\w+)\}", "{}", p)
        front_norm.add(norm)
    missing_in_backend = sorted(front_norm - backend_paths)
    unused_by_front = sorted(backend_paths - front_norm)
    return missing_in_backend, unused_by_front


# ═══════════════════════════════════════════════════════════
# 5. 响应壳抽查（20 个端点）
# ═══════════════════════════════════════════════════════════
SAMPLE20 = [
    ("GET", "/api/admin/courses/series", "admin"),
    ("GET", "/api/admin/courses/cohorts/{cohort_id}", "admin"),
    ("GET", "/api/admin/courses/modules/{module_id}", "admin"),
    ("GET", "/api/admin/courses/sessions/{session_id}", "admin"),
    ("GET", "/api/admin/questions/banks", "admin"),
    ("GET", "/api/admin/questions/banks/{bank_id}/questions", "admin"),
    ("GET", "/api/admin/questions/exams", "admin"),
    ("GET", "/api/admin/questions/types", "admin"),
    ("GET", "/api/admin/users", "admin"),
    ("GET", "/api/admin/users/dashboard/metrics", "admin"),
    ("GET", "/api/admin/rag/collections", "admin"),
    ("GET", "/api/admin/refunds", "admin"),
    ("GET", "/api/auth/me", "student"),
    ("GET", "/api/coupons", "student"),
    ("GET", "/api/favorites", "student"),
    ("GET", "/api/gamification/me/points", "student"),
    ("GET", "/api/community/posts", "student"),
    ("GET", "/api/trade/orders", "student"),
    ("GET", "/api/users/me", "student"),
    ("GET", "/api/progress/dashboard", "student"),
]


def shell_sample(rows):
    ok_cnt = 0
    for method, path, role in SAMPLE20:
        token = TOKENS.get(role)
        http, body, shell = call("GET", resolve_path(path), token=token)
        code = body.get("code") if isinstance(body, dict) else None
        data_null = body.get("data") is None if isinstance(body, dict) else None
        if shell and code == 0 and not data_null:
            ok_cnt += 1
            verdict, note = "OK", f"成功壳 code=0 data非空"
        elif shell and isinstance(code, str) and data_null:
            verdict, note = "ERR-SHELL", f"错误壳 code={code} data=null"
        else:
            verdict, note = "FAIL", f"壳不合规 code={code!r} data_is_null={data_null} http={http}"
        rows.append({
            "method": method, "path": path, "role": role, "http": http,
            "code": code, "verdict": verdict, "note": note,
        })
    return ok_cnt


# ═══════════════════════════════════════════════════════════
# 无 token 鉴权抽查
# ═══════════════════════════════════════════════════════════
AUTH_SPOT = [
    ("GET", "/api/admin/courses/series"),
    ("GET", "/api/auth/me"),
    ("GET", "/api/users/me"),
    ("GET", "/api/trade/orders"),
    ("POST", "/api/chat"),
]


def test_noauth(rows):
    for method, path in AUTH_SPOT:
        http, body, shell = call(method, resolve_path(path), token=None)
        code = body.get("code") if isinstance(body, dict) else None
        ok = http in (401, 403) and shell and isinstance(code, str)
        rows.append({
            "method": method, "path": path + " (无token)", "role": "anon", "http": http,
            "code": code, "verdict": "OK" if ok else "FAIL",
            "note": f"应 401/403 错误壳，实际 http={http}",
        })


# ═══════════════════════════════════════════════════════════
# 安全写操作实证：创建→删除
# ═══════════════════════════════════════════════════════════
def test_safe_writes(rows):
    tok = TOKENS["admin"]
    # ① 创建 series → 修改 → 删除
    payload = {"institution_id": 1, "delivery_mode": "online_recorded",
               "series_code": "itest-sweep-%d" % int(time.time()), "series_name": "ITest验收系列",
               "sale_status": "draft", "created_by": 100003}
    http, body, shell = call("POST", "/api/admin/courses/series", token=tok, payload=payload)
    sid = body.get("data", {}).get("id") if isinstance(body, dict) else None
    rows.append({"method": "POST", "path": "/api/admin/courses/series", "role": "admin", "http": http,
                 "code": body.get("code") if isinstance(body, dict) else None,
                 "verdict": "OK" if http == 201 and shell and body.get("code") == 0 else "FAIL",
                 "note": f"创建series sid={sid}"})
    if sid:
        http, body, shell = call("PATCH", f"/api/admin/courses/series/{sid}", token=tok,
                                 payload={"series_name": "ITest验收系列-改"})
        rows.append({"method": "PATCH", "path": f"/api/admin/courses/series/{sid}", "role": "admin", "http": http,
                     "code": body.get("code") if isinstance(body, dict) else None,
                     "verdict": "OK" if http in (200, 201) and shell and body.get("code") == 0 else "FAIL",
                     "note": "修改series"})
        http, body, shell = call("DELETE", f"/api/admin/courses/series/{sid}", token=tok)
        rows.append({"method": "DELETE", "path": f"/api/admin/courses/series/{sid}", "role": "admin", "http": http,
                     "code": body.get("code") if isinstance(body, dict) else None,
                     "verdict": "OK" if http == 200 and shell and body.get("code") == 0 else "FAIL",
                     "note": "删除series（清理）"})
    # ② 收藏 → 取消收藏
    tok_s = TOKENS["student"]
    http, body, shell = call("POST", "/api/favorites", token=tok_s, payload={"series_id": 2})
    rows.append({"method": "POST", "path": "/api/favorites", "role": "student", "http": http,
                 "code": body.get("code") if isinstance(body, dict) else None,
                 "verdict": "OK" if shell and body.get("code") == 0 else "FAIL", "note": "添加收藏"})
    http, body, shell = call("DELETE", "/api/favorites/2", token=tok_s)
    rows.append({"method": "DELETE", "path": "/api/favorites/2", "role": "student", "http": http,
                 "code": body.get("code") if isinstance(body, dict) else None,
                 "verdict": "OK" if shell and body.get("code") == 0 else "FAIL", "note": "取消收藏"})
    # ③ 领券（幂等安全）
    http, body, shell = call("POST", "/api/trade/coupon/receive", token=tok_s, payload={"coupon_id": 1})
    rows.append({"method": "POST", "path": "/api/trade/coupon/receive", "role": "student", "http": http,
                 "code": body.get("code") if isinstance(body, dict) else None,
                 "verdict": "OK" if shell else "FAIL", "note": "领券（重复领取预期业务错误）"})


# ═══════════════════════════════════════════════════════════
# 报告生成
# ═══════════════════════════════════════════════════════════
def write_report(all_rows, missing_in_backend, unused_by_front, verdict_stats):
    lines = []
    A = lines.append
    A("# EduAgent 独立接口验收报告（be-tester）")
    A("")
    A("- 测试方式：真实 HTTP 请求独立实证（Python requests），不采信任何既有报告")
    A(f"- 后端：`http://127.0.0.1:8000` ｜ 前端：`http://127.0.0.1:3000`（静态页） ｜ 日期：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    A(f"- 总请求数：{TOTAL_REQUESTS} ｜ 耗时：{time.time() - TOTAL_START:.1f}s")
    A("")
    A("## 1. 概览")
    A("")
    A("| 分类 | 总数 | OK | BIZ(业务错误=路由存在) | 缺陷 |")
    A("|---|---|---|---|---|")
    cat = {"login": 0, "admin": 0, "user": 0, "shell": 0, "noauth": 0, "write": 0}
    ok_cnt = {"login": 0, "admin": 0, "user": 0, "shell": 0, "noauth": 0, "write": 0}
    for r in all_rows:
        key = r.get("cat", "other")
        cat[key] = cat.get(key, 0) + 1
        if r["verdict"] in ("OK", "ERR-SHELL"):
            ok_cnt[key] = ok_cnt.get(key, 0) + 1
    for k in ["login", "admin", "user", "shell", "noauth", "write"]:
        A(f"| {k} | {cat.get(k, 0)} | {ok_cnt.get(k, 0)} | - | - |")
    A("")
    A("### 角色 × 登录")
    A("")
    A("| 角色 | HTTP | code | 响应壳 | access_token |")
    A("|---|---|---|---|---|")
    for r in all_rows:
        if r["cat"] == "login" and r["path"] == "/api/auth/login":
            A(f"| {r['role']} | {r['http']} | {r['code']} | {'✓' if '有' in r['note'] else '✗'} | {r['note']} |")
    A("")
    A("## 2. 管理端接口明细表（/api/admin/*）")
    A("")
    A("| 方法 | 路由 | HTTP | code | 判定 | 说明 |")
    A("|---|---|---|---|---|---|")
    for r in all_rows:
        if r["cat"] == "admin":
            A(f"| {r['method']} | `{r['path']}` | {r['http']} | {r['code']} | {r['verdict']} | {r['note']} |")
    A("")
    A("## 3. 用户端/其他接口明细")
    A("")
    A("| 方法 | 路由 | 角色 | HTTP | code | 判定 | 说明 |")
    A("|---|---|---|---|---|---|---|")
    for r in all_rows:
        if r["cat"] in ("user", "noauth", "write", "shell"):
            A(f"| {r['method']} | `{r['path']}` | {r['role']} | {r['http']} | {r['code']} | {r['verdict']} | {r['note']} |")
    A("")
    A("## 4. 契约缺口清单")
    A("")
    A(f"前端引用共 {len(load_front())} 条，后端路由共 {len(load_routes())} 条（方法×路径）。")
    A("")
    A("### 4.1 前端引用但后端不存在")
    A("")
    if missing_in_backend:
        for p in missing_in_backend:
            A(f"- `{p}`")
    else:
        A("- 无")
    A("")
    A("### 4.2 后端有但前端未使用")
    A("")
    if unused_by_front:
        A(f"共 {len(unused_by_front)} 条：")
        for p in unused_by_front:
            A(f"- `{p}`")
    else:
        A("- 无")
    A("")
    A("## 5. 发现的真实缺陷")
    A("")
    defects = [r for r in all_rows if r["verdict"] in ("FAIL", "BADCODE", "NONJSON", "NOSHELL", "NETERR")]
    if defects:
        for r in defects:
            A(f"- **{r['method']} {r['path']}**（{r['role']}）：HTTP={r['http']} code={r['code']} 期望={r['note']}")
    else:
        A("- 未发现缺陷")
    A("")
    A("## 6. 结论")
    A("")
    ok_total = sum(1 for r in all_rows if r["verdict"] in ("OK", "ERR-SHELL"))
    rate = ok_total / len(all_rows) * 100 if all_rows else 0
    A(f"- 总执行 {len(all_rows)} 项，通过（含合规业务错误响应）{ok_total} 项，通过率 **{rate:.1f}%**")
    A(f"- 缺陷 {len(defects)} 项 ｜ 前端引用缺后端 {len(missing_in_backend)} 项 ｜ 后端未用 {len(unused_by_front)} 项")
    A(f"- 结论：**{'验收通过' if not defects else '验收不通过'}**")
    if defects:
        A("- 阻断项：")
        for r in defects[:20]:
            A(f"  - {r['method']} {r['path']} → {r['note']}（HTTP={r['http']}）")
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return REPORT_FILE


if __name__ == "__main__":
    all_rows = []

    # 1. 登录鉴权
    auth_rows = []
    _t = test_auth(auth_rows)
    for r in auth_rows:
        r["cat"] = "login"
    all_rows += auth_rows
    TOKENS = _t
    if not TOKENS.get("admin"):
        print("admin 登录失败，中止")
        sys.exit(1)

    # 2. 管理端
    admin_rows = []
    test_admin(admin_rows)
    for r in admin_rows:
        r["cat"] = "admin"
    all_rows += admin_rows

    # 3. 用户端
    user_rows = []
    test_users(user_rows)
    for r in user_rows:
        r["cat"] = "user"
    all_rows += user_rows

    # 4. 契约缺口
    missing_in_backend, unused_by_front = contract_gap()

    # 5. 壳抽查
    shell_rows = []
    shell_ok = shell_sample(shell_rows)
    for r in shell_rows:
        r["cat"] = "shell"
    all_rows += shell_rows

    # 6. 无 token 鉴权抽查
    noauth_rows = []
    test_noauth(noauth_rows)
    for r in noauth_rows:
        r["cat"] = "noauth"
    all_rows += noauth_rows

    # 7. 安全写操作
    write_rows = []
    test_safe_writes(write_rows)
    for r in write_rows:
        r["cat"] = "write"
    all_rows += write_rows

    path = write_report(all_rows, missing_in_backend, unused_by_front, {})
    print("REPORT:", path)
    print("TOTAL_REQUESTS:", TOTAL_REQUESTS)
    print("defects:", sum(1 for r in all_rows if r["verdict"] in ("FAIL", "BADCODE", "NONJSON", "NOSHELL", "NETERR")))
    print("missing_in_backend:", missing_in_backend)
    print("unused_by_front:", len(unused_by_front))
