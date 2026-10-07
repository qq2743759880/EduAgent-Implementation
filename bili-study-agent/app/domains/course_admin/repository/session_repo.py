"""Session（课次 = series_cohort_session）管理端仓储（task12-fix）。

表 `series_cohort_session` 按 edu.sql 权威结构：**无 yn 列**（列：id,
series_cohort_course_id, room_id, session_no, session_title, teaching_status,
checkin_required, teaching_date, start_time, end_time, created_at, updated_at）。
teaching_status 是教学状态（scheduled/in_progress/completed/cancelled），非软删标记
→ 删除用**物理 DELETE**。
UNIQUE KEY `uk_series_cohort_session_no` (series_cohort_course_id, session_no)。
"""
from __future__ import annotations
from typing import Optional

from app.database import fetch_all, fetch_one, execute_write


class SessionAdminRepo:
    """series_cohort_session 管理端仓储。"""

    async def get_by_id(self, session_id: int) -> Optional[dict]:
        return await fetch_one(
            "SELECT * FROM series_cohort_session WHERE id = %s",
            (session_id,),
        )

    async def list_by_module(self, module_id: int) -> list[dict]:
        """模块下课次列表（无 yn 过滤——该表无软删列）。"""
        return await fetch_all(
            "SELECT * FROM series_cohort_session WHERE series_cohort_course_id = %s "
            "ORDER BY session_no, id",
            (module_id,),
        )

    async def list_by_cohort(self, cohort_id: int) -> list[dict]:
        """班次下全部课次（JOIN 经模块表，task12-fix 批判②）。"""
        return await fetch_all(
            "SELECT s.* FROM series_cohort_session s "
            "JOIN series_cohort_course m ON m.id = s.series_cohort_course_id "
            "WHERE m.cohort_id = %s ORDER BY s.session_no, s.id",
            (cohort_id,),
        )

    async def get_by_session_no(self, module_id: int, session_no: int) -> Optional[dict]:
        """按 module_id+session_no 查唯一课次（唯一约束判断）。"""
        return await fetch_one(
            "SELECT * FROM series_cohort_session WHERE series_cohort_course_id = %s AND session_no = %s LIMIT 1",
            (module_id, session_no),
        )

    async def room_exists(self, room_id: int) -> bool:
        """F-7：教室存在且启用（org_classroom.yn=1），供 room_id 外键预校验。"""
        row = await fetch_one(
            "SELECT 1 AS ok FROM org_classroom WHERE id = %s AND yn = 1 LIMIT 1",
            (room_id,),
        )
        return row is not None

    async def insert(self, data: dict) -> int:
        return await execute_write(
            "INSERT INTO series_cohort_session (series_cohort_course_id, room_id, session_no, "
            "session_title, teaching_status, checkin_required, teaching_date, start_time, end_time, "
            "created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())",
            (
                data["series_cohort_course_id"], data.get("room_id"), data["session_no"],
                data["session_title"], data.get("teaching_status", "scheduled"),
                data.get("checkin_required", 0), data["teaching_date"],
                data.get("start_time"), data.get("end_time"),
            ),
        )

    async def update(self, session_id: int, data: dict) -> int:
        set_clauses = []
        args = []
        for key, val in data.items():
            set_clauses.append(f"{key} = %s")
            args.append(val)
        if not set_clauses:
            return 0
        set_clauses.append("updated_at = NOW()")
        args.append(session_id)
        return await execute_write(
            f"UPDATE series_cohort_session SET {', '.join(set_clauses)} WHERE id = %s",
            tuple(args),
        )

    # 引用 series_cohort_session 的子表单（实时 DB information_schema 实测，2026-09-04）
    _CHILD_TABLES = (
        "session_asset", "session_attendance", "session_exam", "session_homework",
        "session_homework_submission", "session_teacher_rel", "risk_alert_event",
        "teacher_compensation_item",
    )

    async def count_references(self, session_id: int) -> dict:
        """外键引用计数：全部子表中引用本课次的记录总数。

        >0 禁止物理删除（C-C 删除语义：绝不级联删子数据，避免 FK 500，如 risk_alert_event）。
        """
        sub = " + ".join(
            f"(SELECT COUNT(*) FROM {t} c WHERE c.session_id = %s)" for t in self._CHILD_TABLES
        )
        row = await fetch_one(
            f"SELECT {sub} AS total",
            tuple([session_id] * len(self._CHILD_TABLES)),
        )
        total = int(row["total"]) if row and row["total"] is not None else 0
        return {"total": total}

    async def hard_delete(self, session_id: int) -> int:
        """物理删除（表无软删列；删除前先清子表引用 session_asset，避免外键错误）。"""
        await execute_write(
            "DELETE FROM session_asset WHERE session_id = %s",
            (session_id,),
        )
        return await execute_write(
            "DELETE FROM series_cohort_session WHERE id = %s",
            (session_id,),
        )