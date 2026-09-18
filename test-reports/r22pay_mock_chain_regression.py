# -*- coding: utf-8 -*-
"""W-NEXT-PAYGATE-001 真实回归：mock 支付链路真实一轮 + 渠道闸门封存实证。

真 HTTP 直连 127.0.0.1:8000（requests/urllib，无 Playwright，对齐 AGENTS.md 教训②）：
  A. 下单 → 发起 mock 支付 → /payment-notifications/mock → applied=true（settle 200）
     → 支付/订单 DB 复核 paid；幂等二次回调 applied=false
  B. 渠道闸门封存证据（真实渠道未接线，闸门已生效）：
     - alipay 渠道支付单 + 缺 key 环境 → /payment-notifications/channel → HTTP 503 + code 50301
     - 渠道与支付记录不匹配（wechat 打 alipay 单）→ 40300
     - mock/未知渠道打渠道入口 → 42200
     - 全部拒绝后 alipay 支付单仍 pending（拒绝在落账之前，无副作用）

用法：edu-agent/.venv/Scripts/python.exe test-reports/r22pay_mock_chain_regression.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "edu-agent"))

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

BASE = os.environ.get("TEST_BASE", "http://127.0.0.1:8000")
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ADMIN_ACCOUNT = "adm02test"
STUDENT_ACCOUNT = "user000001"
PASSWORD = "Test@123456"

_results: list[dict] = []


def api(method, path, body=None, token=None, headers=None, timeout=30):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def record(step: str, ok: bool, evidence: dict):
    _results.append({"step": step, "ok": bool(ok), "evidence": evidence})
    print(f"[{'PASS' if ok else 'FAIL'}] {step}: {json.dumps(evidence, ensure_ascii=False)}")


def login(account):
    s, j = api("POST", "/api/auth/login", {"account": account, "password": PASSWORD})
    assert s == 200 and j.get("code") == 0, f"登录失败 {account}: {s} {json.dumps(j, ensure_ascii=False)[:200]}"
    return j["data"]["access_token"]


def _cohort(token):
    for cand in range(1, 16):
        s, j = api("GET", f"/api/cohorts/{cand}", token=token)
        if s == 200:
            c = ((j.get("data") or {}).get("cohort") or {})
            cur = int(c.get("current_student_count", 0) or 0)
            mx = int(c.get("max_student_count", 0) or 0)
            if c.get("yn") == 1 and (not mx or cur < mx):
                return int(c.get("series_id")), cand
    raise RuntimeError("无可用班次")


def create_order(token, prefix):
    series_id, cohort_id = _cohort(token)
    s, j = api("POST", "/api/trade/order",
               {"series_id": series_id, "cohort_id": cohort_id, "coupon_id": None},
               token=token, headers={"Idempotency-Key": f"{prefix}-{int(time.time()*1000)}"})
    assert s == 200 and j.get("code") == 0, f"下单失败: {s} {json.dumps(j, ensure_ascii=False)[:200]}"
    return j["data"]["order_no"]


def db_rows(sql, args):
    async def _run():
        from app.database import init_mysql, close_mysql, fetch_all
        await init_mysql()
        try:
            return [dict(r) for r in await fetch_all(sql, tuple(args))]
        finally:
            await close_mysql()
    return asyncio.run(_run())


def main():
    print(f"== W-NEXT-PAYGATE-001 live regression @ {BASE} ==")
    admin = login(ADMIN_ACCOUNT)
    print("admin login ok")

    # ── A. mock 支付链路真实一轮 ──────────────────────────────
    order_no = create_order(admin, "r22pay-mock")
    s, j = api("POST", f"/api/trade/payment/{order_no}", {"pay_channel": "mock"}, token=admin)
    payment_no = j["data"]["payment_no"]
    record("A1 发起 mock 支付", s == 200 and j["code"] == 0,
           {"http": s, "payment_no": payment_no, "audit_pending": j["data"].get("audit_pending")})

    s, j = api("POST", "/payment-notifications/mock",
               {"payment_no": payment_no, "third_party_trade_no": f"TRD-R22PAY-{payment_no}"}, token=admin)
    record("A2 mock 回调 settle", s == 200 and j["code"] == 0 and j["data"]["applied"] is True,
           {"http": s, "applied": (j.get("data") or {}).get("applied"),
            "message": (j.get("data") or {}).get("message")})

    s, j = api("GET", f"/api/trade/payment/{payment_no}", token=admin)
    pay_status = (j.get("data") or {}).get("status")
    s2, j2 = api("GET", f"/api/trade/order/{order_no}", token=admin)
    order_status = (j2.get("data") or {}).get("status")
    record("A3 支付/订单状态 paid", pay_status == "paid" and order_status == "paid",
           {"payment_status": pay_status, "order_status": order_status})

    pays = db_rows(
        "SELECT p.payment_no, p.payment_status, p.third_party_trade_no FROM payment_record p"
        " JOIN `order` o ON o.id=p.order_id WHERE o.order_no=%s", (order_no,))
    enrolls = db_rows(
        "SELECT scr.enroll_status FROM student_cohort_rel scr"
        " JOIN order_item oi ON oi.id=scr.order_item_id"
        " JOIN `order` o ON o.id=oi.order_id WHERE o.order_no=%s", (order_no,))
    record("A4 DB 复核：paid×1 + 报名 active",
           sum(1 for p in pays if p["payment_status"] == "paid") == 1
           and any(e["enroll_status"] == "active" for e in enrolls),
           {"payments": pays, "enrolls": enrolls})

    s, j = api("POST", "/payment-notifications/mock", {"payment_no": payment_no}, token=admin)
    record("A5 mock 回调幂等（二次）", s == 200 and j["data"]["applied"] is False,
           {"http": s, "applied": (j.get("data") or {}).get("applied"),
            "message": (j.get("data") or {}).get("message")})

    # ── B. 渠道闸门封存证据 ──────────────────────────────────
    order_no2 = create_order(admin, "r22pay-gate")
    s, j = api("POST", f"/api/trade/payment/{order_no2}", {"pay_channel": "alipay"}, token=admin)
    gate_payment = j["data"]["payment_no"]
    record("B1 发起 alipay 渠道支付（真实渠道，无真实流量）", s == 200 and j["code"] == 0,
           {"http": s, "payment_no": gate_payment})

    # B2 缺 key：PAY_MERCHANT_ID / PAY_ALIPAY_PUBLIC_KEY 均未配置 → 50301 fail closed
    s, j = api("POST", "/payment-notifications/channel",
               {"channel": "alipay", "payment_no": gate_payment,
                "payload": {"out_trade_no": gate_payment, "total_amount": "12.30"},
                "signature": "AAAA", "merchant_id": "2026000000000001",
                "notify_amount": "12.30"}, token=None)
    record("B2 缺 key 拒绝（无 JWT 也可打——闸门即鉴权）",
           s == 503 and str(j.get("code")) == "50301",
           {"http": s, "code": j.get("code"), "message": j.get("message")})

    # B3 渠道与支付记录不匹配（wechat 回调打 alipay 单）→ 40300
    s, j = api("POST", "/payment-notifications/channel",
               {"channel": "wechat_pay", "payment_no": gate_payment,
                "payload": {"out_trade_no": gate_payment}, "signature": "AAAA",
                "merchant_id": "m", "notify_amount": "12.30"})
    record("B3 渠道/记录不匹配拒绝", s == 403 and str(j.get("code")) == "40300",
           {"http": s, "code": j.get("code"), "message": j.get("message")})

    # B4 mock 渠道打渠道入口 → 42200
    s, j = api("POST", "/payment-notifications/channel",
               {"channel": "mock", "payment_no": gate_payment, "payload": {}, "signature": "x"})
    record("B4 mock 渠道不走渠道入口", s == 422 and str(j.get("code")) == "42200",
           {"http": s, "code": j.get("code"), "message": j.get("message")})

    # B5 未知渠道 → 42200
    s, j = api("POST", "/payment-notifications/channel",
               {"channel": "crypto_pay", "payment_no": gate_payment, "payload": {}, "signature": "x"})
    record("B5 未知渠道拒绝", s == 422 and str(j.get("code")) == "42200",
           {"http": s, "code": j.get("code"), "message": j.get("message")})

    # B6 拒绝无副作用：alipay 支付单仍 pending
    s, j = api("GET", f"/api/trade/payment/{gate_payment}", token=admin)
    st = (j.get("data") or {}).get("status")
    record("B6 拒绝后无副作用（仍 pending）", st == "pending", {"payment_status": st})

    ok = all(r["ok"] for r in _results)
    print(f"== RESULT: {'ALL PASS' if ok else 'HAS FAILURES'} ({sum(r['ok'] for r in _results)}/{len(_results)}) ==")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
