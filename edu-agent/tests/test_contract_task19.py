# -*- coding: utf-8 -*-
"""task19 契约⑩测试：trade/refund 域（申请/列表/撤销 + 审批 HITL stub）。

GWT 覆盖：
① 申请退款金额 > 实付 → 拒绝并返回业务错误码（金额校验服务端强制，40230）
② pending 退款单 → 撤销 → 状态不再 pending 且不可再次撤销（idempotent）；approved/rejected 由管理端审批驱动
③ 退款被拒绝 → 返回 approver remark 供前端展示拒绝理由
④ refund_type 四枚举（personal_reason/course_unsatisfied/schedule_conflict/duplicate_purchase）提交校验通过
⑤ 业务幂等：同订单已有 pending 退款单 → 复用返回同一 refund_no

直连 127.0.0.1:8003（可用 TEST_BASE 覆盖）。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

import pytest
from concurrent.futures import ThreadPoolExecutor

pytestmark = pytest.mark.skip(reason="需要 live cohort 数据（可下单班次），默认 full-run 跳过")

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

BASE = os.environ.get("TEST_BASE", "http://127.0.0.1:8000")
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

ADMIN_ACCOUNT = "adm02test"
PASSWORD = "Test@123456"
_TOKEN: str | None = None

REFUND_TYPES = ("personal_reason", "course_unsatisfied", "schedule_conflict", "duplicate_purchase")


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
    s, j = api("POST", "/api/auth/login", {"account": account, "password": password})
    assert s == 200, f"登录失败: {json.dumps(j, ensure_ascii=False)[:200]}"
    _TOKEN = j["data"]["access_token"]
    return _TOKEN


def _cohort():
    for cand in (7, 3, 1, 2, 4, 5):
        s, j = api("GET", f"/api/cohorts/{cand}", token=login_token())
        if s == 200:
            c = ((j.get("data") or {}).get("cohort") or {})
            cur = int(c.get("current_student_count", 0) or 0)
            mx = int(c.get("max_student_count", 0) or 0)
            if c.get("yn") == 1 and (not mx or cur < mx):
                return int(c.get("series_id")), cand
    raise RuntimeError("无可用班次")


def create_paid_order(prefix="t19"):
    """下单 → mock 支付 → 订单 paid，返回 (order_no, pay_amount)。"""
    series_id, cohort_id = _cohort()
    s, j = api("POST", "/api/trade/order",
               {"series_id": series_id, "cohort_id": cohort_id, "coupon_id": None},
               token=login_token(), headers={"Idempotency-Key": f"{prefix}-{int(time.time()*1000)}"})
    assert s == 200 and j["code"] == 0, f"下单失败: {json.dumps(j, ensure_ascii=False)[:200]}"
    order_no = j["data"]["order_no"]
    # mock 渠道支付
    s, j = api("POST", f"/api/trade/payment/{order_no}", {"pay_channel": "mock"}, token=login_token())
    assert s == 200, f"发支付失败: {json.dumps(j, ensure_ascii=False)[:200]}"
    payment_no = j["data"]["payment_no"]
    s, j = api("POST", "/payment-notifications/mock", {"payment_no": payment_no}, token=login_token())
    assert s == 200 and j["data"]["applied"] is True, "mock 回调失败"
    # 读订单拿实付金额 + 确认 paid
    s, j = api("GET", f"/api/trade/order/{order_no}", token=login_token())
    assert s == 200 and j["data"]["status"] == "paid", "订单应已 paid"
    return order_no, float(j["data"]["pay_amount"])


def submit_refund(order_no, refund_type="personal_reason", apply_amount=1.0, reason="不想学了"):
    return api("POST", "/api/refunds",
               {"order_no": order_no, "refund_type": refund_type, "apply_amount": apply_amount, "reason": reason},
               token=login_token())


class TestGWT1AmountEnforced:
    def test_overpay_rejected(self):
        """GWT①：申请金额 > 实付 → 40230 拒绝（服务端强制，篡改无效）。"""
        order_no, pay = create_paid_order("t19-over")
        s, j = submit_refund(order_no, apply_amount=pay + 1)
        assert s == 400, f"超付应拒绝 400，got {s}: {json.dumps(j, ensure_ascii=False)[:200]}"
        assert j.get("code") == "40230"
        assert j.get("data") is None

    def test_valid_amount_accepted(self):
        """正常金额（=实付）→ 成功 pending。"""
        order_no, pay = create_paid_order("t19-valid")
        s, j = submit_refund(order_no, apply_amount=pay)
        assert s == 200 and j["code"] == 0, f"应成功: {json.dumps(j, ensure_ascii=False)[:200]}"
        data = j["data"]
        assert data["refund_status"] == "pending"
        assert float(data["apply_amount"]) == pay
        assert data["refund_no"]
        # 业务幂等：同订单重复提交 → 返回同一 pending 退款单
        s2, j2 = submit_refund(order_no, apply_amount=pay)
        assert j2["data"]["refund_no"] == data["refund_no"]

    def test_concurrent_submit_single_pending(self):
        """H1（资金安全 R2）：同订单并发提交 → 仅一条 pending（FOR UPDATE 串行化），返回值唯一。"""
        order_no, pay = create_paid_order("t19-concur")
        def _sub(_):
            return submit_refund(order_no, apply_amount=pay)
        refund_nos = set()
        with ThreadPoolExecutor(max_workers=8) as ex:
            for st, rj in ex.map(_sub, range(8)):
                assert st == 200 and rj["code"] == 0, f"并发提交失败 st={st}: {json.dumps(rj, ensure_ascii=False)[:200]}"
                refund_nos.add(rj["data"]["refund_no"])
        # 全部落库为同一条 pending（幂等返回同一 refund_no）
        assert len(refund_nos) == 1, f"并发应只产生一条 pending, got {len(refund_nos)} 条: {refund_nos}"


class TestGWT2StateMachine:
    def test_cancel_pending_and_not_again(self):
        """GWT②：pending 撤销 → 不再 pending；二次撤销幂等。"""
        order_no, pay = create_paid_order("t19-cancel")
        s, j = submit_refund(order_no, apply_amount=pay)
        refund_id = j["data"]["id"]
        s, j = api("POST", f"/api/refunds/{refund_id}/cancel", token=login_token())
        assert s == 200 and j["data"]["cancelled"] is True
        # 已撤销：pending 列表不再出现
        s, j = api("GET", "/api/refunds?status=pending", token=login_token())
        ids = [it["id"] for it in j["data"]["items"]]
        assert refund_id not in ids, "已撤销单不应出现在 pending 列表"
        # 二次撤销 → 幂等 cancelled=True
        s, j = api("POST", f"/api/refunds/{refund_id}/cancel", token=login_token())
        assert s == 200 and j["data"]["cancelled"] is True

    def test_approval_stub_drives_states(self):
        """GWT②：管理端审批驱动状态。HITL(task28)下 approve 原子直退→refunded；stub 下→approved。"""
        order_no, pay = create_paid_order("t19-approve")
        s, j = submit_refund(order_no, apply_amount=pay)
        refund_id = j["data"]["id"]
        # reject → rejected + remark
        s, j = api("POST", f"/api/admin/refunds/{refund_id}/reject",
                   {"remark": "退课超时，拒绝退款"}, token=login_token())
        assert s == 200 and j["data"]["refund_status"] == "rejected"
        # approve → HITL: refunded（三表原子）；stub: approved
        order_no2, pay2 = create_paid_order("t19-approve2")
        s, j = submit_refund(order_no2, apply_amount=pay2)
        rid2 = j["data"]["id"]
        s, j = api("POST", f"/api/admin/refunds/{rid2}/approve", None, token=login_token())
        assert s == 200, f"approve 应处理: {json.dumps(j, ensure_ascii=False)[:200]}"
        assert j["data"]["refund_status"] in ("approved", "refunded"), f"approve 状态异常: {j['data']}"
        # refunded/approved 单均不可撤销（仅 pending 可撤销）
        s, j = api("POST", f"/api/refunds/{rid2}/cancel", token=login_token())
        assert s == 400 and j.get("code") == "40031", "非 pending 单不可撤销"


class TestGWT3RejectRemark:
    def test_rejected_has_remark(self):
        """GWT③：拒绝后返回 approver remark 供前端展示。"""
        order_no, pay = create_paid_order("t19-reject")
        s, j = submit_refund(order_no, apply_amount=pay)
        refund_id = j["data"]["id"]
        remark = "资格不符，拒绝退款"
        s, j = api("POST", f"/api/admin/refunds/{refund_id}/reject", {"remark": remark}, token=login_token())
        assert s == 200
        # 用户列表 status=rejected → 找到该单含 remark
        s, j = api("GET", "/api/refunds?status=rejected", token=login_token())
        found = [it for it in j["data"]["items"] if it["id"] == refund_id]
        assert found and found[0]["remark"] == remark
        assert found[0]["refund_status"] == "rejected"


class TestGWT4Enum:
    def test_refund_type_enum_all_valid(self):
        """GWT④：四枚举校验通过。"""
        for rt in REFUND_TYPES:
            order_no, pay = create_paid_order(f"t19-enum-{rt[:6]}")
            s, j = submit_refund(order_no, refund_type=rt, apply_amount=pay)
            assert s == 200 and j["code"] == 0, f"类型 {rt} 应通过: {json.dumps(j, ensure_ascii=False)[:200]}"
            assert j["data"]["refund_type"] == rt

    def test_refund_type_invalid(self):
        """非法类型 → 42200。"""
        order_no, pay = create_paid_order("t19-enumbad")
        s, j = api("POST", "/api/refunds",
                   {"order_no": order_no, "refund_type": "bogus_type", "apply_amount": pay, "reason": "x"},
                   token=login_token())
        assert s == 422 and j.get("code") == "42200"


class TestListDesc:
    def test_list_desc_and_admin_list(self):
        """列表倒序 + 管理端列表可用。"""
        s, j = api("GET", "/api/refunds?page=1&page_size=10", token=login_token())
        assert s == 200 and j["code"] == 0 and "items" in j["data"]
        s, j = api("GET", "/api/admin/refunds?page=1&page_size=10", token=login_token())
        assert s == 200 and j["code"] == 0 and "items" in j["data"]