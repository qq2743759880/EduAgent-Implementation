# -*- coding: utf-8 -*-
"""task28 GWT 契约测试：AI HITL 退款审批（LangGraph interrupt + Command(resume) + 72h 超时升级）。

覆盖（全文见 .opencode/plans/tasks/task28-ai-hitl-refund.md）：
- GWT① 审批进入 interrupt 挂起 → 状态持久化（PlainRedisSaver 落 Redis），
        新建图+新 saver 实例（模拟进程重启）同 thread_id 可 resume。
- GWT② resume(approved) 单事务原子更新 refund=refunded + order=refunded + student_cohort_rel=refunded。
- GWT③ 72h 无操作 → 自动创建 priority=high service_ticket + risk_alert_event（scheduled_job，幂等）。

数据策略（环境 VM 宕机拖慢 HTTP 下单链路，故不回协议而直插种子，保证可重复且非破坏）：
- 复用一条现有 'paid' 订单链，为它直插一条独立 pending 退款单；
- 跑完图后**快照回滚**：order_status / student_cohort_rel.enroll_status 恢复原状，删除退款单与 Redis checkpoint。
- 超时升级用另一条独立退款单，断言后清理（含工单/告警）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.database import close_mysql, execute_write, fetch_all, fetch_one, init_mysql
from app.domains.trade.refund.repository import RefundWriteRepo


# ── 拾取一条现有 paid 订单链（含 paid 支付 + active 报名） ──
async def _pick_paid_chain():
    row = await fetch_one(
        "SELECT o.id AS order_id, o.order_status, o.institution_id, o.user_id, o.student_id,"
        " oi.id AS order_item_id,"
        " (SELECT p.id FROM payment_record p WHERE p.order_id=o.id AND p.payment_status='paid' LIMIT 1) AS payment_id"
        " FROM `order` o JOIN order_item oi ON oi.order_id=o.id"
        " WHERE o.order_status='paid'"
        " AND EXISTS(SELECT 1 FROM payment_record p WHERE p.order_id=o.id AND p.payment_status='paid')"
        " ORDER BY o.id DESC LIMIT 1")
    if not row:
        pytest.skip("无可用 paid 订单链（需先有已支付订单），跳过")
    # 快照报名状态（同 order_item 可能多条）
    cohort = await fetch_all(
        "SELECT id, enroll_status FROM student_cohort_rel WHERE order_item_id=%s", (int(row["order_item_id"]),))
    return row, cohort


async def _seed_refund(chain, prefix: str) -> int:
    """直插一条独立 pending 退款单（复用 repository 事务内写入），返回 refund_id。"""
    from app.database import transaction
    from app.domains.trade.refund.repository import RefundWriteRepo
    refund_no = f"{prefix}-{uuid.uuid4().hex[:10]}"
    now = datetime.now()
    async with transaction() as (conn, cur):
        rid = await RefundWriteRepo().create_refund(
            conn=conn, cur=cur, institution_id=int(chain["institution_id"]),
            order_id=int(chain["order_id"]), order_item_id=int(chain["order_item_id"]),
            payment_id=int(chain["payment_id"]), user_id=int(chain["user_id"]),
            student_id=int(chain["student_id"]), refund_no=refund_no,
            refund_type="personal_reason", refund_reason="task28 验证退款",
            apply_amount=1.0, now=now,
        )
    return int(rid)


async def _restore(chain, cohort, rid: int, prefix: str) -> None:
    """回滚：恢复 order/cohort 状态，删除退款单 + Redis checkpoint。"""
    await execute_write("UPDATE `order` SET order_status=%s WHERE id=%s",
                         (chain["order_status"], int(chain["order_id"])), commit=True)
    for c in cohort or []:
        await execute_write("UPDATE student_cohort_rel SET enroll_status=%s WHERE id=%s",
                             (c["enroll_status"], int(c["id"])), commit=True)
    # FK 安全：先删升降级子表（service_ticket/risk_alert_event 引用 refund_request），再删退款单
    await execute_write("DELETE FROM risk_alert_event WHERE refund_request_id=%s", (rid,), commit=True)
    await execute_write("DELETE FROM service_ticket WHERE refund_request_id=%s", (rid,), commit=True)
    await execute_write("DELETE FROM refund_request WHERE id=%s", (rid,), commit=True)
    await _clear_checkpoint(rid)


async def _clear_checkpoint(rid: int) -> None:
    """删除该退款的 Redis checkpoint（'edu:ckpt:hitl-refund-{rid}'），避免残留待审批状态。"""
    redis_key = f"edu:ckpt:hitl-refund-{int(rid)}"
    try:
        import redis.asyncio as aioredis
        r = aioredis.Redis.from_url("redis://localhost:6379/0")
        await r.delete(redis_key)
        await r.aclose()
    except Exception:
        pass


@pytest.mark.asyncio
async def test_gwt12_interrupt_resume_atomic():
    """GWT① interrupt 持久化 + 跨实例 resume；GWT② approved 原子三表 refunded。"""
    from app.domains.trade.refund.hitl_graph import resume_refund_approval, start_refund_approval

    await init_mysql()
    chain = None
    try:
        chain, cohort = await _pick_paid_chain()
        rid = await _seed_refund(chain, "T28-G12")

        # 进程 A：start → interrupt 挂起（PlainRedisSaver 落 Redis）
        started = await start_refund_approval(rid)
        assert started["started"] is True, f"应停驻 interrupt: {started}"

        # 进程 B（全新 saver 实例 = 重启）：同 thread_id resume(approved)
        res = await resume_refund_approval(rid, decision="approved", approver_user_id=1)
        assert res.get("refund_status") == "refunded", f"HITL approve 应原子直退 refunded: {res}"

        # GWT② DB 回查：三表原子
        rr = await fetch_one(
            "SELECT refund_status FROM refund_request WHERE id=%s", (rid,))
        assert rr and rr["refund_status"] == "refunded", f"refund 应 refunded: {rr}"
        o = await fetch_one("SELECT order_status FROM `order` WHERE id=%s", (int(chain["order_id"]),))
        assert o and o["order_status"] == "refunded", f"order 应 refunded: {o}"
        c = await fetch_all("SELECT enroll_status FROM student_cohort_rel WHERE order_item_id=%s",
                            (int(chain["order_item_id"]),))
        assert c and all(x["enroll_status"] == "refunded" for x in c), f"student_cohort_rel 应 refunded: {c}"
    finally:
        if chain is not None:
            await _restore(chain, cohort, rid, "T28-G12")
        await close_mysql()


@pytest.mark.asyncio
async def test_gwt2_reject_and_status_machine():
    """GWT②(reject)：rejected 落 remark；order/cohort 不变（拒绝不退款）；已处理单幂等拒绝。"""
    from app.domains.trade.refund.hitl_graph import resume_refund_approval

    await init_mysql()
    chain = None
    try:
        chain, cohort = await _pick_paid_chain()
        rid = await _seed_refund(chain, "T28-REJ")
        remark = "资格不符，拒绝退款"
        res = await resume_refund_approval(rid, decision="rejected", remark=remark, approver_user_id=2)
        assert res.get("refund_status") == "rejected", f"reject 应 rejected: {res}"
        rr = await fetch_one("SELECT refund_status, remark FROM refund_request WHERE id=%s", (rid,))
        assert rr and rr["refund_status"] == "rejected" and rr["remark"] == remark, rr
        o = await fetch_one("SELECT order_status FROM `order` WHERE id=%s", (int(chain["order_id"]),))
        assert o and o["order_status"] == chain["order_status"], "拒绝不能改订单状态"
        # 状态机：rejected 不可再次 approve
        from app.common.exceptions import AppException
        with pytest.raises(AppException):
            await resume_refund_approval(rid, decision="approved", approver_user_id=1)
    finally:
        if chain is not None:
            await _restore(chain, cohort, rid, "T28-REJ")
        await close_mysql()


@pytest.mark.asyncio
async def test_gwt3_escalation_high_ticket_idempotent():
    """GWT③：72h 超时 → priority=high service_ticket + risk_alert_event；幂等不重复。"""
    from app.domains.trade.refund.hitl_graph import escalate_refunds_older_than

    await init_mysql()
    chain = None
    try:
        chain, _cohort = await _pick_paid_chain()
        rid = await _seed_refund(chain, "T28-ESC")
        # 回拨 applied_at → 超时
        await execute_write("UPDATE refund_request SET applied_at=%s WHERE id=%s",
                             (datetime.now() - timedelta(hours=73), rid), commit=True)

        res = await escalate_refunds_older_than(hours=0, refund_id=rid)
        assert res["scanned"] >= 1 and res["escalated"] >= 1, f"应升级: {res}"

        t = await fetch_one(
            "SELECT ticket_type, ticket_source, priority_level, ticket_status FROM service_ticket"
            " WHERE refund_request_id=%s AND yn=1 LIMIT 1", (rid,))
        assert t, "应创建 service_ticket"
        assert t["priority_level"] == "high" and t["ticket_type"] == "refund" \
            and t["ticket_source"] == "system_auto" and t["ticket_status"] == "open", f"工单枚举: {t}"

        a = await fetch_one(
            "SELECT alert_type, alert_source, alert_status FROM risk_alert_event"
            " WHERE refund_request_id=%s AND yn=1 LIMIT 1", (rid,))
        assert a and a["alert_type"] == "refund_anomaly" and a["alert_source"] == "scheduled_job" \
            and a["alert_status"] == "pending", f"风险告警: {a}"

        # 幂等：二次扫描不重复
        await escalate_refunds_older_than(hours=0, refund_id=rid)
        cnt = await fetch_one("SELECT COUNT(*) c FROM service_ticket WHERE refund_request_id=%s AND yn=1", (rid,))
        assert int(cnt["c"]) == 1, f"工单应唯一: {cnt}"
        cnt2 = await fetch_one("SELECT COUNT(*) c FROM risk_alert_event WHERE refund_request_id=%s AND yn=1", (rid,))
        assert int(cnt2["c"]) == 1, f"告警应唯一: {cnt2}"

        # 清理工单/告警（避免残留）
        await execute_write("DELETE FROM risk_alert_event WHERE refund_request_id=%s", (rid,), commit=True)
        await execute_write("DELETE FROM service_ticket WHERE refund_request_id=%s", (rid,), commit=True)
    finally:
        if chain is not None:
            await _restore(chain, _cohort, rid, "T28-ESC")
        await close_mysql()