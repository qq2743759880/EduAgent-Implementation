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