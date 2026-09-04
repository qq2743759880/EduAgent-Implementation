# -*- coding: utf-8 -*-
"""enrollment 域 repository：student_cohort_rel 读写 + 进度聚合 + 满班并发。

资金/并发红线（task20 hard）：
- 满班并发控制：`UPDATE series_cohort SET current_student_count=current_student_count+1
  WHERE id=%s AND current_student_count < max_student_count` → 0 行 = 满班（GWT① 409）
- 报名记录正确：student_cohort_rel（enroll_status active）单事务，余位随报名递减（GWT③）
- 进度聚合真实（无 MOCK）：series_cohort_course（模块）+ series_cohort_session（课次）
  + session_homework_submission（提交表：submit_status='submitted' 判该生已完）
"""
from __future__ import annotations

from app.database import fetch_all, fetch_one


class EnrollmentRepo:
    """只读/聚合查询。"""

    async def get_cohort_for_enroll(self, cohort_id: int) -> dict | None:
        """取班次 + 关联系列（on_sale 校验）。"""
        return await fetch_one(
            "SELECT c.id AS cohort_id, c.institution_id, c.series_id, c.cohort_name,"
            " c.max_student_count, c.current_student_count, c.yn,"
            " s.series_name, s.delivery_mode, s.sale_status"
            " FROM series_cohort c JOIN series s ON s.id = c.series_id"
            " WHERE c.id=%s LIMIT 1",
            (cohort_id,),
        )

    async def get_enrollment(self, cohort_id: int, user_id: int) -> dict | None:
        """按 (cohort_id, user_id) 取报名记录（涉及 series_id）。

        注：edu.sql student_cohort_rel 无 yn 列，状态仅由 enroll_status 表达。
        """
        return await fetch_one(
            "SELECT scr.id AS enrollment_id, scr.institution_id, scr.user_id, scr.student_id,"
            " scr.cohort_id, scr.order_item_id, scr.enroll_status, scr.enroll_at,"
            " scr.completed_at, scr.cancelled_at, c.series_id"
            " FROM student_cohort_rel scr"
            " JOIN series_cohort c ON c.id = scr.cohort_id"
            " WHERE scr.cohort_id=%s AND scr.user_id=%s LIMIT 1",
            (cohort_id, int(user_id)),
        )

    async def get_enrollment_by_id(self, enrollment_id: int, user_id: int) -> dict | None:
        """按报名记录 id 取（详情，校验归属）。"""
        return await fetch_one(
            "SELECT id AS enrollment_id, institution_id, user_id, student_id, cohort_id,"
            " order_item_id, enroll_status, enroll_at, completed_at, cancelled_at"
            " FROM student_cohort_rel WHERE id=%s AND user_id=%s LIMIT 1",
            (enrollment_id, int(user_id)),
        )

    async def list_my_enrollments(
        self, user_id: int, *, enroll_status: str | None = None, series_id: int | None = None,
    ) -> list[dict]:
        """我的班次列表（status / series_id 过滤）。"""
        where = ["scr.user_id=%s"]
        args: list = [int(user_id)]
        if enroll_status:
            where.append("scr.enroll_status=%s")
            args.append(enroll_status)
        if series_id:
            where.append("c.series_id=%s")
            args.append(int(series_id))
        return await fetch_all(
            "SELECT scr.id AS enrollment_id, scr.cohort_id, scr.enroll_status, scr.enroll_at,"
            " scr.completed_at, scr.order_item_id,"
            " c.cohort_name, c.series_id, c.start_date,"
            " s.series_name, s.series_code, s.cover_url, s.delivery_mode, s.sale_status"
            " FROM student_cohort_rel scr"
            " JOIN series_cohort c ON c.id = scr.cohort_id"
            " JOIN series s ON s.id = c.series_id"
            f" WHERE {' AND '.join(where)} ORDER BY scr.id DESC",
            tuple(args),
        )

    async def get_progress_totals(self, cohort_ids: list[int]) -> dict[int, tuple[int, int]]:
        """班次教学结构总数：{cohort_id: (module_total, session_total)}（排除 cancelled 课次）。"""
        if not cohort_ids:
            return {}
        marks = ",".join(["%s"] * len(cohort_ids))
        rows = await fetch_all(
            "SELECT ccc.cohort_id, COUNT(DISTINCT ccc.id) AS module_total,"
            " COUNT(DISTINCT scs.id) AS session_total"
            " FROM series_cohort_course ccc"
            " LEFT JOIN series_cohort_session scs ON scs.series_cohort_course_id = ccc.id"
            " AND scs.teaching_status <> 'cancelled'"
            f" WHERE ccc.cohort_id IN ({marks})"
            " GROUP BY ccc.cohort_id",
            tuple(cohort_ids),
        )
        return {int(r["cohort_id"]): (int(r["module_total"]), int(r["session_total"])) for r in rows}

    async def get_progress_done(self, cohort_ids: list[int], user_id: int) -> dict[int, tuple[int, int]]:
        """已学进度：{cohort_id: (session_done, module_done)}。

        session_done = 该生已提交的 session 数（真实提交表）
        module_done  = 「模块内全部 session 均已提交」的模块数（与进度快照语义一致，R3 修复）
        """
        if not cohort_ids:
            return {}
        marks = ",".join(["%s"] * len(cohort_ids))
        session_rows = await fetch_all(
            "SELECT ccc.cohort_id, COUNT(DISTINCT shs.session_id) AS session_done"
            " FROM session_homework_submission shs"
            " JOIN series_cohort_session scs ON scs.id = shs.session_id"
            " JOIN series_cohort_course ccc ON ccc.id = scs.series_cohort_course_id"
            f" WHERE shs.user_id=%s AND shs.submit_status='submitted' AND ccc.cohort_id IN ({marks})"
            " GROUP BY ccc.cohort_id",
            tuple([int(user_id)] + cohort_ids),
        )
        # 模块全部 session 提交判定：逐模块（cohort 内）比较已提交 session 集是否覆盖全部非取消 session
        module_rows = await fetch_all(
            "SELECT ccc.cohort_id, ccc.id AS module_id,"
            " COUNT(DISTINCT scs.id) AS module_sessions,"
            " COUNT(DISTINCT CASE WHEN shs.id IS NOT NULL THEN scs.id END) AS module_done_sessions"
            " FROM series_cohort_course ccc"
            " LEFT JOIN series_cohort_session scs ON scs.series_cohort_course_id = ccc.id"
            "  AND scs.teaching_status <> 'cancelled'"
            " LEFT JOIN session_homework_submission shs ON shs.session_id = scs.id"
            "  AND shs.user_id=%s AND shs.submit_status='submitted'"
            f" WHERE ccc.cohort_id IN ({marks})"
            " GROUP BY ccc.cohort_id, ccc.id",
            tuple([int(user_id)] + cohort_ids),
        )
        out: dict[int, tuple[int, int]] = {}
        for r in session_rows:
            out[int(r["cohort_id"])] = (int(r["session_done"]), 0)
        for m in module_rows:
            cid = int(m["cohort_id"])
            total = int(m["module_sessions"])
            done = int(m["module_done_sessions"])
            if total > 0 and done == total:
                prev = out.get(cid, (0, 0))
                out[cid] = (prev[0], prev[1] + 1)
        return out

    async def get_progress_snapshot(self, cohort_id: int, user_id: int) -> tuple[list[dict], set[int]]:
        """进度快照：模块/课次明细 + 该生已提交 session_id 集合。"""
        modules = await fetch_all(
            "SELECT ccc.id AS module_id, ccc.module_name, ccc.stage_no,"
            " scs.id AS session_id, scs.session_no, scs.session_title, scs.teaching_status"
            " FROM series_cohort_course ccc"
            " JOIN series_cohort_session scs ON scs.series_cohort_course_id = ccc.id"
            " WHERE ccc.cohort_id=%s AND scs.teaching_status <> 'cancelled'"
            " ORDER BY ccc.stage_no, scs.session_no",
            (cohort_id,),
        )
        done_rows = await fetch_all(
            "SELECT DISTINCT shs.session_id FROM session_homework_submission shs"
            " JOIN series_cohort_session scs ON scs.id = shs.session_id"
            " JOIN series_cohort_course ccc ON ccc.id = scs.series_cohort_course_id"
            " WHERE shs.user_id=%s AND shs.submit_status='submitted' AND ccc.cohort_id=%s",
            (int(user_id), cohort_id),
        )
        return modules, {int(r["session_id"]) for r in done_rows}

    async def get_next_session(self, cohort_id: int, user_id: int) -> dict | None:
        """下次课（未提交的 scheduled/in_progress 课次，最早开课）。"""
        return await fetch_one(
            "SELECT ccc.cohort_id, ccc.id AS module_id, ccc.module_name,"
            " scs.id AS session_id, scs.session_title, scs.teaching_date, scs.start_time"
            " FROM series_cohort_course ccc"
            " JOIN series_cohort_session scs ON scs.series_cohort_course_id = ccc.id"
            " WHERE ccc.cohort_id=%s AND scs.teaching_status IN ('scheduled','in_progress')"
            " AND scs.id NOT IN ("
            "   SELECT shs.session_id FROM session_homework_submission shs"
            "   WHERE shs.user_id=%s AND shs.submit_status='submitted')"
            " ORDER BY scs.teaching_date, scs.start_time, scs.session_no LIMIT 1",
            (cohort_id, int(user_id)),
        )

    async def get_refund_by_order_item(self, order_item_id: int) -> dict | None:
        """报名关联退款单（refunded 态展示）。"""
        if order_item_id is None:
            return None
        return await fetch_one(
            "SELECT refund_no, apply_amount, refunded_at FROM refund_request"
            " WHERE order_item_id=%s AND refund_status IN ('approved','refunded') LIMIT 1",
            (order_item_id,),
        )