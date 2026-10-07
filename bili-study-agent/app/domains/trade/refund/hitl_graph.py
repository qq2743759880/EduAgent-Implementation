# -*- coding: utf-8 -*-
"""task28 AI HITL 退款审批：LangGraph interrupt + Command(resume) + 原子落库 + 72h 超时升级工单。

设计对齐 tech-source-audit §二 HITL（LangGraph 原生 human checkpoint，无需自研审批状态机）：
  - 审批图（approval → apply）：进入审批节点 `interrupt()` 挂起，状态持久化到 checkpointer
    （运行时 PlainRedisSaver 落 Redis；GWT① 进程重启后同 thread_id 可 resume）。
  - resume 用 `Command(resume=decision)`：approved → `approve_and_refund` 单事务原子执行
    refund=refunded + order=refunded + student_cohort_rel=refunded（GWT②，不绕过 task19 状态机/金额校验）；
    rejected → refund=rejected + approver remark（GWT③）。
  - 72h 无操作 → `escalate_refunds_older_than` 自动创建 priority=high 工单 + risk_alert_event 通知（GWT③，幂等）。
  - Redis/checkpointer 不可达时：resume 降级为「直接原子 DB apply」（不丢资金安全红线），记录降级。

state 字段：decision / approved_amount / remark / approver_user_id 为审批结果（经 Command(resume) 注入）。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.common.error_codes import TRADE_REFUND_STATUS_INVALID
from app.common.exceptions import AppException
from app.config import settings
from app.database import execute_write, fetch_all, fetch_one, transaction
from app.domains.trade.refund.repository import RefundRepo, RefundWriteRepo

logger = logging.getLogger(__name__)

_refund_repo = RefundRepo()
_refund_write = RefundWriteRepo()

HITL_THREAD_PREFIX = "hitl-refund"


class RefundApprovalState(TypedDict):
    """审批图状态。decision 及审批人字段由 resume 注入。"""

    refund_id: int
    decision: str
    approved_amount: Optional[float]
    remark: Optional[str]
    approver_user_id: Optional[int]
    refund_status: Optional[str]
    error: Optional[str]


def thread_id_of(refund_id: int) -> str:
    return f"{HITL_THREAD_PREFIX}-{int(refund_id)}"


def _make_saver() -> Any:
    """运行时 Redis durable checkpointer（PlainRedisSaver，持久化 interrupt 状态）。不可用返回 None。"""
    try:
        from app.ai.checkpoint_redis import PlainRedisSaver

        return PlainRedisSaver(redis_url=settings.REDIS_URL, ttl=getattr(settings, "CHECKPOINT_TTL", 604800))
    except Exception as exc:  # pragma: no cover - Redis 不可用时降级
        logger.warning(f"[HITL] Redis checkpointer 不可用（降级无持久化）: {type(exc).__name__}: {exc}")
        return None


# ═══════════════════════════════════════════════════════
# 原子 DB 应用（graph apply 节点 + Redis 不可达时的降级共用；不绕过 task19 金额校验）
# ═══════════════════════════════════════════════════════
async def _atomic_apply(
    refund_id: int,
    *,
    decision: str,
    approved_amount: Optional[float],
    remark: Optional[str],
    approver_user_id: Optional[int],
) -> dict:
    """按 decision 原子落库。approved → refunded（三表原子）；rejected → rejected + remark。

    返回 {refund_status, error}。金额服务端强制：approved_amount ∈ (0, apply_amount]（apply ≤ 实付由 task19 保证）。
    非 pending（已处理/并发竞态）→ 返回 error=status:...，不抛 500。
    """
    row = await _refund_repo.get_refund(refund_id)
    if row is None:
        return {"refund_status": None, "error": "refund_not_found"}
    if row["refund_status"] != "pending":
        return {"refund_status": row["refund_status"], "error": f"status:{row['refund_status']}"}
    now = datetime.now()
    decision = (decision or "rejected").lower()

    try:
        async with transaction() as (conn, cur):
            if decision == "approved":
                amt = float(approved_amount) if approved_amount is not None else float(row["apply_amount"])
                ctx = float(row["apply_amount"])
                if not (0 < amt <= ctx + 1e-6):
                    # 金额非法 → 抛业务错误码（任务19 红线），不进入写库
                    raise AppException("40230", "审批金额非法（须>0且≤申请金额）")
                approver = int(approver_user_id) if approver_user_id else None
                affected = await _refund_write.approve_and_refund(
                    conn=conn, cur=cur, refund_id=refund_id,
                    order_id=int(row["order_id"]), order_item_id=int(row["order_item_id"]),
                    approver_user_id=approver, approved_amount=amt, refund_amount=amt,
                    remark=remark, now=now,
                )
                return {"refund_status": "refunded", "error": None} if affected else {
                    "refund_status": row["refund_status"], "error": f"status:{row['refund_status']}"}
            # rejected
            approver = int(approver_user_id) if approver_user_id else None
            affected = await _refund_write.reject_refund(
                conn=conn, cur=cur, refund_id=refund_id,
                approver_user_id=approver, remark=remark, now=now,
            )
            return {"refund_status": "rejected", "error": None} if affected else {
                "refund_status": row["refund_status"], "error": f"status:{row['refund_status']}"}
    except AppException:
        raise
    except Exception as exc:
        logger.exception("[HITL] 原子退款落库异常：%s", exc)
        return {"refund_status": row["refund_status"], "error": str(exc)[:200]}


# ═══════════════════════════════════════════════════════
# 审批图节点
# ═══════════════════════════════════════════════════════
def approval_node(state: RefundApprovalState) -> dict:
    """审批节点：interrupt() 挂起，等待管理员（approved/rejected + 审批信息）。"""
    decision = interrupt({
        "action": "refund_approval",
        "refund_id": state["refund_id"],
        "options": ["approved", "rejected"],
        "pending": "awaiting_human",
    })
    payload = decision if isinstance(decision, dict) else {}
    decision_val = str(payload.get("decision") or "rejected").strip().lower()
    if decision_val not in ("approved", "rejected"):
        decision_val = "rejected"
    return {
        "decision": decision_val,
        "approved_amount": payload.get("approved_amount"),
        "remark": payload.get("remark"),
        "approver_user_id": payload.get("approver_user_id"),
    }


async def apply_node(state: RefundApprovalState) -> dict:
    """resume 后执行：approved 原子三表退款 / rejected 拒绝；返回 refund_status。"""
    return await _atomic_apply(
        int(state["refund_id"]),
        decision=state.get("decision") or "rejected",
        approved_amount=state.get("approved_amount"),
        remark=state.get("remark"),
        approver_user_id=state.get("approver_user_id"),
    )


def build_hitl_graph(checkpointer: Any | None = None) -> Any:
    """构建并编译 HITL 审批图（START → approval(interrupt) → apply → END）。"""
    w = StateGraph(RefundApprovalState)
    w.add_node("approval", approval_node)
    w.add_node("apply", apply_node)
    w.add_edge(START, "approval")
    w.add_edge("approval", "apply")
    w.add_edge("apply", END)
    return w.compile(checkpointer=checkpointer)


def _compile(saver: Any | None = None) -> Any:
    if saver is None:
        saver = _make_saver()
    return build_hitl_graph(checkpointer=saver)


def _cfg(refund_id: int) -> dict:
    return {"configurable": {"thread_id": thread_id_of(refund_id)}}


async def _graph_awaiting(graph: Any, cfg: dict) -> bool:
    """thread 是否停在被中断的节点（存在待审批 interrupt）。aget_state 是 async，须 await。"""
    try:
        snapshot, _ = await graph.aget_state(cfg)
        return bool(getattr(snapshot, "next", None))
    except Exception:
        return False


async def start_refund_approval(refund_id: int, *, saver: Any | None = None) -> dict:
    """启动审批（lazily）：图跑至 approval interrupt 挂起，状态持久化。返回是否停驻。"""
    row = await _refund_repo.get_refund(refund_id)
    if row is None:
        raise AppException("40420", "退款单不存在")
    if row["refund_status"] != "pending":
        return {"refund_id": refund_id, "started": False, "refund_status": row["refund_status"]}
    graph = _compile(saver)
    cfg = _cfg(refund_id)
    await graph.ainvoke({"refund_id": int(refund_id)}, cfg)
    return {"refund_id": refund_id, "started": True, "refund_status": "pending"}


async def resume_refund_approval(
    refund_id: int,
    *,
    decision: str,
    approved_amount: Optional[float] = None,
    remark: Optional[str] = None,
    approver_user_id: Optional[int] = None,
    saver: Any | None = None,
) -> dict:
    """审批通过/拒绝：Command(resume=...) 恢复被中断审批图 → 原子落库（GWT②）。

    - 首审（该 thread 无待审 interrupt）先 start 建 checkpoint，再 resume。
    - checkpointer 不可用（Redis 不可达）→ 直接 `_atomic_apply` 原子落库（资金红线不丢），记录降级。
    - 返回 {refund_id, refund_status, degraded?}；非 pending / 金额非法 → 业务码异常。
    """
    row = await _refund_repo.get_refund(refund_id)
    if row is None:
        raise AppException("40420", "退款单不存在")
    if row["refund_status"] != "pending":
        raise AppException(TRADE_REFUND_STATUS_INVALID, f"退款状态 {row['refund_status']} 不允许审批（需 pending）")

    if saver is None:
        saver = _make_saver()
    if saver is None:
        # 降级：直接原子 apply（不绕过金额校验/状态机），记录 degraded
        out = await _atomic_apply(
            refund_id, decision=decision, approved_amount=approved_amount,
            remark=remark, approver_user_id=approver_user_id,
        )
        if out.get("error"):
            raise AppException(TRADE_REFUND_STATUS_INVALID, f"退款未执行：{out['error']}")
        logger.warning("[HITL] Redis checkpointer 不可达，降级为直接原子落库 refund=%s", refund_id)
        return {"refund_id": refund_id, "refund_status": out["refund_status"], "degraded": True}

    graph = _compile(saver)
    cfg = _cfg(refund_id)
    # 首次审批：先 start（建 interrupt checkpoint），再 resume
    if not await _graph_awaiting(graph, cfg):
        try:
            await graph.ainvoke({"refund_id": int(refund_id)}, cfg)
        except Exception as exc:
            logger.warning(f"[HITL] start 审批失败，改用直接原子落库：{type(exc).__name__}: {exc}")
            out = await _atomic_apply(
                refund_id, decision=decision, approved_amount=approved_amount,
                remark=remark, approver_user_id=approver_user_id,
            )
            if out.get("error"):
                raise AppException(TRADE_REFUND_STATUS_INVALID, f"退款未执行：{out['error']}")
            return {"refund_id": refund_id, "refund_status": out["refund_status"], "degraded": True}

    payload = {
        "decision": decision,
        "approved_amount": approved_amount,
        "remark": remark,
        "approver_user_id": approver_user_id,
    }
    try:
        out = await graph.ainvoke(Command(resume=payload), cfg)
    except Exception as exc:
        logger.exception(f"[HITL] resume 审批异常，改用直接原子落库: {exc}")
        out = await _atomic_apply(
            refund_id, decision=decision, approved_amount=approved_amount,
            remark=remark, approver_user_id=approver_user_id,
        )
        if out.get("error"):
            raise AppException(TRADE_REFUND_STATUS_INVALID, f"退款未执行：{out['error']}")
        return {"refund_id": refund_id, "refund_status": out["refund_status"], "degraded": True}

    if out.get("error"):
        raise AppException(TRADE_REFUND_STATUS_INVALID, f"退款未执行：{out['error']}")
    return {"refund_id": refund_id, "refund_status": out.get("refund_status") or row["refund_status"]}


# ═══════════════════════════════════════════════════════
# 72h 超时升级（GWT③）：自动创建 priority=high 工单 + risk_alert 通知（幂等）
# ═══════════════════════════════════════════════════════
async def _has_escalation(cur, refund_id: int) -> bool:
    """幂等判定：该退款已存在 high 待处理退款超时工单或 scheduled_job 风险告警中 pending → 跳过。

    `cur` 为调用方事务内游标（配合 FOR UPDATE 原子 check-then-insert，防多 worker 并发重复建单）。
    """
    await cur.execute(
        "SELECT id FROM service_ticket WHERE refund_request_id=%s AND ticket_source='system_auto'"
        " AND priority_level='high' AND ticket_status='open' AND yn=1 LIMIT 1",
        (int(refund_id),),
    )
    if await cur.fetchone():
        return True
    await cur.execute(
        "SELECT id FROM risk_alert_event WHERE refund_request_id=%s AND alert_type='refund_anomaly'"
        " AND alert_source='scheduled_job' AND alert_status='pending' AND yn=1 LIMIT 1",
        (int(refund_id),),
    )
    return await cur.fetchone() is not None


async def escalate_refunds_older_than(*, hours: int | None = None, now: datetime | None = None,
                                      refund_id: int | None = None) -> dict:
    """扫描超时未审批退款 → 创建 high 工单 + 风险告警通知（幂等）。

    仅处理 `refund_status='pending' AND yn=1 AND applied_at < now-hours` 的单。
    `refund_id` 非空时仅扫描该单（测试/定向升级用，避免误伤其他 pending 单；缺省仍全局扫描=生产后台）。
    返回 {scanned, escalated, skipped}。

    并发安全（R3-P2-2）：对每条超时单，先 `SELECT ... FOR UPDATE` 锁定该退款行，再在同一事务内
    `_has_escalation`（check）+`_insert_escalation`（insert），多 worker 并发扫描时 InnoDB 行锁串行化，
    保证工单/告警唯一，杜绝 check-then-insert 竞态重复建单。
    """
    hours = int(hours if hours is not None else getattr(settings, "HITL_ESCALATION_HOURS", 72))
    now = now or datetime.now()
    cutoff = now - timedelta(hours=hours)
    if refund_id is not None:
        rows = await fetch_all(
            "SELECT id, institution_id, order_id, order_item_id, user_id, student_id, refund_no, apply_amount"
            " FROM refund_request WHERE id=%s AND refund_status='pending' AND yn=1 AND applied_at < %s",
            (int(refund_id), cutoff),
        )
    else:
        rows = await fetch_all(
            "SELECT id, institution_id, order_id, order_item_id, user_id, student_id, refund_no, apply_amount"
            " FROM refund_request WHERE refund_status='pending' AND yn=1 AND applied_at < %s",
            (cutoff,),
        )
    scanned = len(rows or [])
    escalated = 0
    skipped = 0
    for r in rows or []:
        rid = int(r["id"])
        # 事务内 FOR UPDATE 锁定该退款行 → 原子 check-then-insert（并发升级串行化）
        try:
            async with transaction() as (conn, cur):
                await cur.execute("SELECT id FROM refund_request WHERE id=%s FOR UPDATE", (rid,))
                if not await cur.fetchone():
                    skipped += 1
                    continue
                if await _has_escalation(cur, rid):
                    skipped += 1
                    continue
                now_row = datetime.now()
                ok = await _insert_escalation(
                    cur=cur, institution_id=int(r["institution_id"]), refund_id=rid,
                    user_id=int(r["user_id"]), student_id=int(r["student_id"]),
                    order_item_id=int(r["order_item_id"]), refund_no=r["refund_no"],
                    apply_amount=float(r["apply_amount"] or 0), hours=hours, now=now_row,
                )
        except Exception as exc:
            logger.warning(f"[HITL] 升级该单失败(事务级) refund={rid}: {type(exc).__name__}: {exc}")
            ok = False
        if ok:
            escalated += 1
        else:
            skipped += 1
    return {"scanned": scanned, "escalated": escalated, "skipped": skipped}


def _new_alert_no(institution_id: int) -> str:
    return f"A-{institution_id}-{datetime.now().strftime('%y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"


def _new_escalation_ticket_no(institution_id: int) -> str:
    return f"T-{institution_id}-{datetime.now().strftime('%y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"


async def _insert_escalation(
    *, cur, institution_id: int, refund_id: int, user_id: int, student_id: int,
    order_item_id: int, refund_no: str, apply_amount: float, hours: int, now: datetime,
) -> bool:
    """在调用方**已锁定的同一事务内**插入 high 工单 + scheduled_job 风险告警。

    `cur` 由 `escalate_refunds_older_than` 传入（已对该退款行 `FOR UPDATE`，事务由外层持有），
    双写在事务内原子，任一失败使事务整体回滚——由外层 `transaction()` 统一提交/回滚。
    返回 False 供调用方计 skipped。不在此再开事务（避免嵌套与死锁）。

    表结构对齐 edu.sql：
    - service_ticket.ticket_type∈{after_sales,complaint,refund}；ticket_source∈{user_app,customer_service,system_auto,admin_manual}
    - risk_alert_event.alert_source∈{...scheduled_job}；alert_type=refund_anomaly；detected_at NOT NULL
    """
    try:
        title = f"退款审批超时({hours}) — {refund_no}"
        await cur.execute(
            "INSERT INTO service_ticket (institution_id, ticket_no, user_id, student_id, order_item_id,"
            " refund_request_id, ticket_type, ticket_source, priority_level, ticket_status,"
            " title, ticket_content, yn, first_response_at, created_at, updated_at)"
            " VALUES (%s,%s,%s,%s,%s,%s,'refund','system_auto','high','open',%s,%s,1,NULL,%s,%s)",
            (institution_id, _new_escalation_ticket_no(institution_id), int(user_id), int(student_id),
             int(order_item_id), int(refund_id), title,
             f"退款申请超过 {hours} 小时未审批，已自动升级为高优工单。退款单:{refund_no}，金额:{apply_amount:.2f}",
             now, now),
        )
        await cur.execute(
            "INSERT INTO risk_alert_event (institution_id, alert_no, alert_type, risk_level,"
            " related_user_id, related_student_id, order_item_id, refund_request_id, alert_source,"
            " alert_reason, alert_status, yn, detected_at, created_at, updated_at)"
            " VALUES (%s,%s,'refund_anomaly','high',%s,%s,%s,%s,'scheduled_job',%s,'pending',1,%s,%s,%s)",
            (institution_id, _new_alert_no(institution_id), int(user_id), int(student_id),
             int(order_item_id), int(refund_id),
             f"退款审批超时升级为 high：refund_no={refund_no}，金额={apply_amount:.2f}",
             now, now, now),
        )
        return True
    except Exception as exc:
        logger.warning(f"[HITL] 升级工单写入失败 refund={refund_id}: {type(exc).__name__}: {exc}")
        return False


async def run_escalation_loop(stop_event: asyncio.Event | None = None) -> None:
    """后台超时扫描循环（main 启动时拉起）。stop_event 置位退出。"""
    interval = int(getattr(settings, "HITL_ESCALATION_INTERVAL", 1800))
    while True:
        try:
            res = await escalate_refunds_older_than()
            if res["escalated"]:
                logger.info(f"[HITL] 超时扫描：scanned={res['scanned']} escalated={res['escalated']}")
        except Exception as exc:
            logger.warning(f"[HITL] 超时扫描异常（不阻断）：{type(exc).__name__}: {exc}")
        if stop_event is not None:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
            if stop_event.is_set():
                return
        else:
            await asyncio.sleep(interval)


# 便捷：退还金额上限校验（复用 task19 语义，供 manager 兜底）
ENROLL_REFUNDED = "refunded"