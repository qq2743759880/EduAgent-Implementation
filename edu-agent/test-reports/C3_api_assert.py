# -*- coding: utf-8 -*-
"""taskC3 DEBUG=False 端到端验收 —— API 断言脚本(②③⑥)。

断言清单:
  ② 登录链路: admin(adm02test)/student(user000001) login → auth/me → refresh → me(新token)
  ③ 无 token: /api/admin/users→401; /api/users/me→401; 虚拟管理员探测=不可用(P1-8);
              X-Force-Role 头生产态不生效(仅 DEBUG)
  ⑥ CORS: 生产 CORS_ORIGINS 配置下, 白名单源放行 / 非白名单源拒绝(实测记录)

用法: python test-reports/C3_api_assert.py [--cors-origin http://localhost:3000]
零新依赖: 仅 requests。不直写 DB;只读探测。
"""
import argparse
import json
import sys

import requests

BACKEND = "http://127.0.0.1:8000"
ADMIN = {"account": "adm02test", "password": "Test@123456"}
STUDENT = {"account": "user000001", "password": "Test@123456"}

results = []


def record(no, name, ok, detail):
    results.append((no, name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {no} {name}  {detail}")


def shell(j):
    """{code:0,message,data} 壳校验。"""
    return isinstance(j, dict) and j.get("code") == 0 and "data" in j


def login_flow(tag, cred, expect_role):
    r = requests.post(f"{BACKEND}/api/auth/login", json=cred, timeout=10)
    ok = r.status_code == 200
    j = r.json() if ok else {}
    ok = ok and shell(j)
    tok = (j.get("data") or {}).get("access_token", "")
    refresh_tok = (j.get("data") or {}).get("refresh_token", "")
    record("②", f"{tag} login", ok,
           f"HTTP {r.status_code} code={j.get('code')} has_access={bool(tok)} has_refresh={bool(refresh_tok)}")
    if not ok:
        return None

    # /api/auth/me
    r = requests.get(f"{BACKEND}/api/auth/me", headers={"Authorization": f"Bearer {tok}"}, timeout=10)
    j = r.json()
    role = (j.get("data") or {}).get("role")
    record("②", f"{tag} auth/me", r.status_code == 200 and shell(j) and role == expect_role,
           f"HTTP {r.status_code} role={role} user_id={(j.get('data') or {}).get('user_id')}")

    # refresh → 新双 token
    r = requests.post(f"{BACKEND}/api/auth/refresh", json={"refresh_token": refresh_tok}, timeout=10)
    ok = r.status_code == 200 and shell(r.json())
    j2 = r.json() if ok else {}
    new_access = (j2.get("data") or {}).get("access_token", "")
    new_refresh = (j2.get("data") or {}).get("refresh_token", "")
    record("②", f"{tag} refresh", ok and bool(new_access) and bool(new_refresh),
           f"HTTP {r.status_code} code={j2.get('code')} new_access={bool(new_access)} rotated={new_refresh != refresh_tok}")

    # 新 token /api/auth/me
    if new_access:
        r = requests.get(f"{BACKEND}/api/auth/me", headers={"Authorization": f"Bearer {new_access}"}, timeout=10)
        j3 = r.json()
        record("②", f"{tag} me(新token)", r.status_code == 200 and shell(j3)
               and (j3.get("data") or {}).get("role") == expect_role,
               f"HTTP {r.status_code} role={(j3.get('data') or {}).get('role')}")


def anon_assertions():
    # ③-1 无 token /api/admin/users → 401
    r = requests.get(f"{BACKEND}/api/admin/users", timeout=10)
    body = r.text[:120]
    record("③", "无token /api/admin/users→401", r.status_code == 401,
           f"HTTP {r.status_code} body={body}")

    # ③-2 无 token /api/users/me → 401
    r = requests.get(f"{BACKEND}/api/users/me", timeout=10)
    record("③", "无token /api/users/me→401", r.status_code == 401,
           f"HTTP {r.status_code} body={r.text[:120]}")

    # ③-3 虚拟管理员探测(P1-8 核心): 无 token 任何受保护端点都不得返回 200/数据
    virtual_admin_usable = False
    for path in ("/api/admin/users", "/api/users/me", "/api/auth/me"):
        r = requests.get(f"{BACKEND}{path}", timeout=10)
        if r.status_code == 200:
            virtual_admin_usable = True
    record("③", "虚拟管理员探测=不可用(P1-8)", not virtual_admin_usable,
           "三端点无 token 全部非 200" if not virtual_admin_usable else "存在无 token 200 端点——虚拟管理员后门存活!")

    # ③-4 X-Force 头生产态不生效(仅 DEBUG)
    r = requests.get(f"{BACKEND}/api/admin/users",
                     headers={"X-Force-Role": "admin", "X-Force-User-Id": "1"}, timeout=10)
    record("③", "X-Force-Role 生产态不生效", r.status_code == 401,
           f"HTTP {r.status_code}(期望 401,X-Force 仅 DEBUG=true 生效)")


def cors_assertions(allow_origin, deny_origin):
    # ⑥-1 白名单源: 预检 + 实际请求
    r = requests.options(f"{BACKEND}/api/auth/login", headers={
        "Origin": allow_origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"}, timeout=10)
    acao = r.headers.get("access-control-allow-origin", "")
    record("⑥", f"CORS 预检 白名单源 {allow_origin}", r.status_code in (200, 204) and acao == allow_origin,
           f"HTTP {r.status_code} ACAO={acao or '(无)'}")

    r = requests.post(f"{BACKEND}/api/auth/login", json=ADMIN,
                      headers={"Origin": allow_origin}, timeout=10)
    acao = r.headers.get("access-control-allow-origin", "")
    record("⑥", f"CORS 实际请求 白名单源 {allow_origin}",
           r.status_code == 200 and acao == allow_origin,
           f"HTTP {r.status_code} ACAO={acao or '(无)'}")

    # ⑥-2 非白名单源: 预检无 ACAO / 实际请求无 ACAO(浏览器将拦截)
    r = requests.options(f"{BACKEND}/api/auth/login", headers={
        "Origin": deny_origin, "Access-Control-Request-Method": "POST"}, timeout=10)
    acao = r.headers.get("access-control-allow-origin", "")
    record("⑥", f"CORS 预检 非白名单源 {deny_origin} 被拒", acao == "",
           f"HTTP {r.status_code} ACAO={acao or '(无,浏览器将拒绝)'}")

    r = requests.post(f"{BACKEND}/api/auth/login", json=ADMIN,
                      headers={"Origin": deny_origin}, timeout=10)
    acao = r.headers.get("access-control-allow-origin", "")
    record("⑥", f"CORS 实际请求 非白名单源 {deny_origin} 无 ACAO", acao == "" or acao != deny_origin,
           f"HTTP {r.status_code} ACAO={acao or '(无)'}(注: FastAPI 对非白名单源仍处理请求但不回 ACAO,浏览器侧拦截)")


def dependency_50301_probe():
    """⑤(可选): Redis 停止后依赖端点应返回 50301 脱敏壳(不泄露内部细节)。
    仅探测 /health 与一个轻依赖端点形态;不重复 stop/start(由验收窗口手工编排)。"""
    # 这里只做只读探测: /health 存活即可(50301 停 Redis 重测由外部编排,见报告)
    r = requests.get(f"{BACKEND}/health", timeout=10)
    record("⑤", "后端 /health 存活", r.status_code == 200 and r.json().get("status") == "ok",
           f"HTTP {r.status_code} status={r.json().get('status')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cors-origin", default="http://localhost:3000")
    ap.add_argument("--cors-deny-origin", default="http://evil.example.com")
    ap.add_argument("--skip-cors", action="store_true")
    args = ap.parse_args()

    login_flow("admin", ADMIN, "admin")
    login_flow("student", STUDENT, "student")
    anon_assertions()
    dependency_50301_probe()
    if not args.skip_cors:
        cors_assertions(args.cors_origin, args.cors_deny_origin)

    fails = [x for x in results if not x[2]]
    print(f"\n汇总: {len(results) - len(fails)}/{len(results)} PASS" + (f",FAIL 项: {[x[1] for x in fails]}" if fails else ""))
    sys.exit(1 if fails else 0)
