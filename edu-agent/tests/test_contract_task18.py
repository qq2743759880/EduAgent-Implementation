# -*- coding: utf-8 -*-
"""task18 契约⑨测试：trade/payment 域（8 端点 + mock 回调 + 报名联动 + 并发攻防）。

GWT 覆盖：
① 同一 payment_no 的 mock 回调 100 并发 → 仅一次生效（其余条件更新 0 行幂等），
   order 只 paid 一次、报名仅 active 一次（券仅 used 一次）
② 支付成功 → order=paid / enroll_status=active / payment_status=paid 原子一致（单事务）
③ 线下转账渠道 → 状态停留 pending + audit_pending=true，无即时回调；mock 回调仅限模拟渠道
④ 对账任务 → 无重复入账记录（对账报告 ok=True）
⑤ 双路径别名（/api/payments + /payment-notifications/mock）与权威路径等价可通

直连 127.0.0.1:8003（可用 TEST_BASE 覆盖）；并发用 ThreadPoolExecutor 施压。
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pytest

pytestmark = pytest.mark.skip(reason="需要 live cohort 数据（可下单班次），默认 full-run 跳过")

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

BASE = os.environ.get("TEST_BASE", "http://127.0.0.1:8000")
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

ADMIN_ACCOUNT = "adm02test"
PASSWORD = "Test@123456"
_TOKEN: str | None = None
_TOKEN_LOCK = threading.Lock()


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


def login_token(account=ADMIN_ACCOUNT, password=PASSWORD):
    global _TOKEN
    if _TOKEN:
        return _TOKEN
    with _TOKEN_LOCK:
        if _TOKEN:
            return _TOKEN
        s, j = api("POST", "/api/auth/login", {"account": account, "password": password})
        assert s == 200, f"登录失败: {json.dumps(j, ensure_ascii=False)[:200]}"
        _TOKEN = j["data"]["access_token"]
    return _TOKEN


def _cohort():
    """探测一个可下单班次（cap 未满）。"""
    for cand in (7, 3, 1, 2, 4, 5):
        s, j = api("GET", f"/api/cohorts/{cand}", token=login_token())
        if s == 200:
            c = ((j.get("data") or {}).get("cohort") or {})
            cur = int(c.get("current_student_count", 0) or 0)
            mx = int(c.get("max_student_count", 0) or 0)
            if c.get("yn") == 1 and (not mx or cur < mx):
                return int(c.get("series_id")), cand
    raise RuntimeError("无可用班次")


def create_order(prefix="t18"):
    """建 pending 订单（无券），返回 order_no。"""
    series_id, cohort_id = _cohort()
    s, j = api("POST", "/api/trade/order",
               {"series_id": series_id, "cohort_id": cohort_id, "coupon_id": None},
               token=login_token(), headers={"Idempotency-Key": f"{prefix}-{int(time.time()*1000)}"})
    assert s == 200, f"下单失败: {json.dumps(j, ensure_ascii=False)[:200]}"
    assert j.get("code") == 0
    return j["data"]["order_no"]


def db_verify(sql, args):
    """直连 MySQL 校验（复用 app.database）。"""
    async def _run():
        from app.database import init_mysql, close_mysql, fetch_one, fetch_all
        await init_mysql()
        try:
            if sql.strip().upper().startswith(("SELECT", "SHOW")):
                rows = await fetch_all(sql, tuple(args))
                return [dict(r) for r in rows]
            return None
        finally:
            await close_mysql()
    return asyncio.run(_run())


class TestGWT1ConcurrentCallback:
    def test_100_concurrent_mock_callback_once(self):
        """GWT①：100 并发 mock 回调同一 payment_no → 仅 1 次 applied，order/enroll/支付 只生效一次。"""
        order_no = create_order("t18-cb")
        # 发起 mock 渠道支付
        s, j = api("POST", f"/api/trade/payment/{order_no}", {"pay_channel": "mock"},
                   token=login_token())
        assert s == 200 and j["code"] == 0, f"发起支付失败: {json.dumps(j, ensure_ascii=False)[:200]}"
        assert j["data"]["audit_pending"] is False
        payment_no = j["data"]["payment_no"]

        # 100 并发 mock 回调
        def _notify(_):
            return api("POST", "/payment-notifications/mock",
                       {"payment_no": payment_no, "third_party_trade_no": f"TRD-{payment_no}"},
                       token=login_token())
        applied = 0
        with ThreadPoolExecutor(max_workers=30) as ex:
            for st, rj in list(ex.map(_notify, range(100))):
                assert st == 200, f"回调异常 st={st}: {json.dumps(rj, ensure_ascii=False)[:200]}"
                if rj["data"]["applied"]:
                    applied += 1
        assert applied == 1, f"应仅 1 次生效, got {applied}"

        # 幂等复核：再回调一次 → applied=False
        s, j = api("POST", "/payment-notifications/mock", {"payment_no": payment_no},
                   token=login_token())
        assert s == 200 and j["data"]["applied"] is False

        # DB 证据：payment 仅 1 笔 paid；order 状态 paid；报名仅 1 条 active
        pays = db_verify(
            "SELECT p.payment_no, p.payment_status FROM payment_record p"
            " JOIN `order` o ON o.id=p.order_id WHERE o.order_no=%s",
            (order_no,))
        assert sum(1 for p in pays if p["payment_status"] == "paid") == 1, \
            f"paid 支付应 1 笔: {pays}"
        enrolls = db_verify(
            "SELECT scr.enroll_status FROM student_cohort_rel scr"
            " JOIN order_item oi ON oi.id=scr.order_item_id"
            " JOIN `order` o ON o.id=oi.order_id WHERE o.order_no=%s", (order_no,))
        assert sum(1 for e in enrolls if e["enroll_status"] == "active") == 1, \
            f"报名应仅 1 条 active: {enrolls}"
        od = db_verify("SELECT order_status, paid_at IS NOT NULL AS has_paid_at FROM `order` WHERE order_no=%s", (order_no,))
        assert od and od[0]["order_status"] == "paid", f"订单应 paid: {od}"
        self._order_no = order_no


class TestGWT2AtomicConsistent:
    def test_single_payment_atomic(self):
        """GWT②：先回调成功，再查三表 → 三者原子一致。"""
        order_no = create_order("t18-atomic")
        s, j = api("POST", f"/api/trade/payment/{order_no}", {"pay_channel": "mock"},
                   token=login_token())
        payment_no = j["data"]["payment_no"]
        s, j = api("POST", "/payment-notifications/mock", {"payment_no": payment_no},
                   token=login_token())
        assert s == 200 and j["data"]["applied"] is True

        # 支付详情
        s, j = api("GET", f"/api/trade/payment/{payment_no}", token=login_token())
        assert j["code"] == 0 and j["data"]["status"] == "paid"
        # 订单详情
        s, j = api("GET", f"/api/trade/order/{order_no}", token=login_token())
        assert j["code"] == 0 and j["data"]["status"] == "paid"
        # DB：enroll active 且三者一致
        pay = db_verify("SELECT payment_status FROM payment_record WHERE payment_no=%s", (payment_no,))
        od = db_verify("SELECT order_status FROM `order` WHERE order_no=%s", (order_no,))
        en = db_verify(
            "SELECT enroll_status FROM student_cohort_rel scr"
            " JOIN order_item oi ON oi.id=scr.order_item_id"
            " JOIN `order` o ON o.id=oi.order_id WHERE o.order_no=%s", (order_no,))
        assert pay and pay[0]["payment_status"] == "paid"
        assert od and od[0]["order_status"] == "paid"
        assert en and en[0]["enroll_status"] == "active"


class TestGWT3OfflineTransfer:
    def test_offline_transfer_pending_no_immediate_callback(self):
        """GWT③：线下转账 → 状态停留 pending + audit_pending=true，mock 回调被拒。"""
        order_no = create_order("t18-offline")
        s, j = api("POST", f"/api/trade/payment/{order_no}", {"pay_channel": "offline_transfer"},
                   token=login_token())
        assert s == 200, f"发起线下支付失败: {json.dumps(j, ensure_ascii=False)[:200]}"
        data = j["data"]
        assert data["status"] == "pending"
        assert data["audit_pending"] is True, "线下转账应提示到账审核中"
        payment_no = data["payment_no"]

        # 支付详情仍 pending（无即时回调）
        s, j = api("GET", f"/api/trade/payment/{payment_no}", token=login_token())
        assert j["code"] == 0 and j["data"]["status"] == "pending"

        # mock 回调仅限模拟渠道 → 线下渠道应拒绝（40021）
        s, j = api("POST", "/payment-notifications/mock",
                   {"payment_no": payment_no, "third_party_trade_no": "TRD-x"}, token=login_token())
        assert s == 400 and j["code"] == "40021"


class TestGWT4Reconcile:
    def test_reconcile_no_duplicate(self):
        """GWT④：对账任务 → 报告 ok=True，无重复入账。"""
        s, j = api("POST", "/api/trade/payments/reconcile", token=login_token())
        assert s == 200 and j["code"] == 0
        data = j["data"]
        assert "report_no" in data and isinstance(data["total_paid_payments"], int)
        assert data.get("ok") is True, f"对账应无异常: {json.dumps(data, ensure_ascii=False)[:300]}"


class TestAliasPaths:
    def test_alias_payments_and_mock_notify(self):
        """GWT⑤：/api/payments 别名 + /payment-notifications/mock 与权威路径等价。"""
        order_no = create_order("t18-alias")
        # 别名发起支付
        s, j = api("POST", f"/api/payments/{order_no}", {"pay_channel": "mock"},
                   token=login_token())
        assert s == 200 and j["code"] == 0
        payment_no = j["data"]["payment_no"]
        # 权威路径（/api/trade/payment/{payment_no}/mock-notify）也生效
        s, j = api("POST", f"/api/trade/payment/{payment_no}/mock-notify",
                   {"third_party_trade_no": "TRD-ALIAS"}, token=login_token())
        assert s == 200, f"权威 mock-notify 失败: {json.dumps(j, ensure_ascii=False)[:200]}"
        # 别名详情读取
        s, j = api("GET", f"/api/payments/{payment_no}", token=login_token())
        assert s == 200 and j["code"] == 0 and j["data"]["status"] == "paid"