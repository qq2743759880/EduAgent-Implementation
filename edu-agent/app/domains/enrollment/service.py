# -*- coding: utf-8 -*-
"""enrollment 域（task20 契约⑪ 前段，只读）service。

判据（用户裁定 + GWT）：
- 只实现 4 个读端点：/me/cohorts 列表、详情、进度快照、状态查询（解锁 task47）
- 满班并发控制（GWT①）由既有下单路径（task17 occupy_seat 条件更新）承载，另以脚本并发验证
- 进度聚合真实（无 MOCK）：series_cohort_course（模块）+ series_cohort_session（课次总数）
  + session_homework_submission（该生提交判已完）
- 报名记录/余位由 task18 支付回调联动（GWT③），本域只读展示
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.common.exceptions import AppException
from app.domains.enrollment.repository import EnrollmentRepo
from app.domains.enrollment.schemas import (
    EnrolledCohort, EnrolledNextSession, EnrolledRefund, ProgressModule,
    ProgressSession, ProgressSnapshot,
)

logger = logging.getLogger(__name__)

_repo = EnrollmentRepo()

VALID_ENROLL_STATUS = {"active", "completed", "cancelled", "refunded"}


def _fmt_teaching_at(d: str, t) -> str:
    """合并 teaching_date + start_time → 前端展示时间（ISO datetime）。"""
    if not d:
        return ""
    s = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
    if t:
        ts = t.strftime("%H:%M:%S") if hasattr(t, "strftime") else str(t)
        return f"{s} {ts}"
    return s


async def _assemble(row: dict) -> EnrolledCohort:
    cohort_id = int(row["cohort_id"])
    series_id = int(row["series_id"])
    # 进度聚合（真实提交表）
    totals = await _repo.get_progress_totals([cohort_id])
    done = await _repo.get_progress_done([cohort_id], int(row["user_id"] or row.get("student_id") or 0))
    module_total, session_total = totals.get(cohort_id, (0, 0))
    session_done, module_done = done.get(cohort_id, (0, 0))
    overall = round(session_done / session_total * 100, 1) if session_total else 0.0
    # 下次课
    nxt = await _repo.get_next_session(cohort_id, int(row.get("user_id") or 0))
    next_session = None
    if nxt:
        next_session = EnrolledNextSession(
            series_id=series_id,
            module_id=int(nxt["module_id"]),
            module_title=nxt["module_name"],
            session_id=int(nxt["session_id"]),
            session_title=nxt["session_title"],
            teaching_at=_fmt_teaching_at(nxt["teaching_date"], nxt["start_time"]),
        )
    # 退款信息（refunded 态）
    refund = None
    if row.get("enroll_status") == "refunded":
        rr = await _repo.get_refund_by_order_item(row.get("order_item_id"))
        if rr:
            refund = EnrolledRefund(
                refund_no=rr.get("refund_no"),
                refund_amount=(str(rr["apply_amount"]) if rr.get("apply_amount") is not None else None),
                refunded_at=rr.get("refunded_at"),
            )
    return EnrolledCohort(
        enrollment_id=int(row["enrollment_id"]),
        cohort_id=cohort_id,
        cohort_name=row.get("cohort_name"),
        series_id=series_id,
        series_name=row.get("series_name"),
        series_code=row.get("series_code"),
        subject_code=row.get("subject_code"),
        level_code=row.get("level_code"),
        cover_url=row.get("cover_url"),
        delivery_mode=row.get("delivery_mode"),
        enroll_status=row["enroll_status"],
        overall_ratio=overall,
        module_done=module_done, module_total=module_total,
        session_done=session_done, session_total=session_total,
        next_session=next_session,
        finished_at=row.get("completed_at"),
        refund=refund,
    )


# ═══════════════════════════════════════════════════════
# 我的班次列表（GWT②）
# ═══════════════════════════════════════════════════════
async def list_my_enrollments(user_id: int, *, enroll_status: str | None = None,
                              series_id: int | None = None) -> list[EnrolledCohort]:
    if enroll_status and enroll_status not in VALID_ENROLL_STATUS:
        raise AppException("42200", f"非法报名状态：{enroll_status}")
    rows = await _repo.list_my_enrollments(user_id, enroll_status=enroll_status, series_id=series_id)
    out = []
    for r in rows:
        coerced = dict(r)
        # list 查询未含 user_id/refund_status，补 user_id
        coerced["user_id"] = user_id
        out.append(await _assemble(coerced))
    return out


# ═══════════════════════════════════════════════════════
# 报名详情（状态 + 进度）
# ═══════════════════════════════════════════════════════
async def get_enrollment_detail(user_id: int, cohort_id: int) -> EnrolledCohort:
    row = await _repo.get_enrollment(cohort_id, user_id)
    if row is None:
        raise AppException("40430", "未找到该班次报名记录")
    row["user_id"] = user_id
    return await _assemble(row)


# ═══════════════════════════════════════════════════════
# 进度快照（模块/课次明细）
# ═══════════════════════════════════════════════════════
async def get_progress_snapshot(user_id: int, cohort_id: int) -> ProgressSnapshot:
    row = await _repo.get_enrollment(cohort_id, user_id)
    if row is None:
        raise AppException("40430", "未找到该班次报名记录")
    modules, done_sessions = await _repo.get_progress_snapshot(cohort_id, user_id)
    # 结构化
    grouped: dict[int, dict] = {}
    for m in modules:
        mid = int(m["module_id"])
        grouped.setdefault(mid, {
            "id": mid, "name": m["module_name"], "stage": int(m["stage_no"]), "sessions": [],
        })
        done = int(m["session_id"]) in done_sessions
        grouped[mid]["sessions"].append(ProgressSession(
            session_id=int(m["session_id"]), session_no=int(m["session_no"]),
            session_title=m["session_title"], teaching_status=m["teaching_status"], done=done,
        ))
    module_list: list[ProgressModule] = []
    for g in grouped.values():
        s = g["sessions"]
        module_list.append(ProgressModule(
            module_id=g["id"], module_name=g["name"], stage_no=g["stage"],
            sessions=s, done_count=sum(1 for x in s if x.done), total_count=len(s),
        ))
    module_total = len(module_list)
    session_total = sum(m.total_count for m in module_list)
    session_done = sum(m.done_count for m in module_list)
    module_done = sum(1 for m in module_list if m.done_count == m.total_count and m.total_count > 0)
    overall = round(session_done / session_total * 100, 1) if session_total else 0.0
    return ProgressSnapshot(
        cohort_id=cohort_id, series_id=int(row.get("series_id") or 0),
        overall_ratio=overall, module_done=module_done, module_total=module_total,
        session_done=session_done, session_total=session_total, modules=module_list,
    )


# ═══════════════════════════════════════════════════════
# 状态查询
# ═══════════════════════════════════════════════════════
async def get_enrollment_status(user_id: int, cohort_id: int) -> dict:
    row = await _repo.get_enrollment(cohort_id, user_id)
    if row is None:
        raise AppException("40430", "未找到该班次报名记录")
    return {
        "enrollment_id": int(row["enrollment_id"]),
        "cohort_id": int(row["cohort_id"]),
        "enroll_status": row["enroll_status"],
        "enroll_at": row["enroll_at"],
        "finished_at": row.get("completed_at"),
    }