"""Module（模块 = series_cohort_course）管理端仓储（task12-fix）。

表 `series_cohort_course` 按 edu.sql 权威结构：**无 yn 列**（列：id, cohort_id,
module_code, module_name, description, lesson_count, total_hours, stage_no,
start_date, end_date, created_at, updated_at）。无状态字段 → 删除用**物理 DELETE**
（软删需改表结构，不推荐动权威表；可恢复性由 task13 或运维备份承担）。
"""
from __future__ import annotations

from typing import Optional

from app.database import fetch_all, fetch_one, execute_write


class ModuleAdminRepo:
    """series_cohort_course 管理端仓储。"""

    async def get_by_id(self, module_id: int) -> Optional[dict]:
        return await fetch_one(
            "SELECT * FROM series_cohort_course WHERE id = %s",
            (module_id,),
        )

    async def list_by_cohort(self, cohort_id: int) -> list[dict]:
        """班次下模块列表（无 yn 过滤——该表无软删列）。"""
        return await fetch_all(
            "SELECT * FROM series_cohort_course WHERE cohort_id = %s "
            "ORDER BY stage_no, module_code, id",
            (cohort_id,),
        )

    async def get_by_stage(self, cohort_id: int, stage_no: int) -> Optional[dict]:
        """按 cohort_id+stage_no 查唯一模块（唯一约束判断）。"""
        return await fetch_one(
            "SELECT * FROM series_cohort_course WHERE cohort_id = %s AND stage_no = %s LIMIT 1",
            (cohort_id, stage_no),
        )

    async def get_by_module_code(self, cohort_id: int, module_code: str) -> Optional[dict]:
        """按 cohort_id+module_code 查唯一模块（唯一约束判断）。"""
        return await fetch_one(
            "SELECT * FROM series_cohort_course WHERE cohort_id = %s AND module_code = %s LIMIT 1",
            (cohort_id, module_code),
        )

    async def insert(self, data: dict) -> int:
        return await execute_write(
            "INSERT INTO series_cohort_course (cohort_id, module_code, module_name, description, "
            "lesson_count, total_hours, stage_no, start_date, end_date, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())",
            (
                data["cohort_id"], data["module_code"], data["module_name"],
                data.get("description"), data["lesson_count"], data["total_hours"],
                data["stage_no"], data["start_date"], data["end_date"],
            ),
        )

    async def update(self, module_id: int, data: dict) -> int:
        set_clauses = []
        args = []
        for key, val in data.items():
            set_clauses.append(f"{key} = %s")
            args.append(val)
        if not set_clauses:
            return 0
        set_clauses.append("updated_at = NOW()")
        args.append(module_id)
        return await execute_write(
            f"UPDATE series_cohort_course SET {', '.join(set_clauses)} WHERE id = %s",
            tuple(args),
        )

    async def hard_delete(self, module_id: int) -> int:
        """物理删除（表无软删列，删除前先清子表引用 series_cohort_session）。"""
        # 先删子表：series_cohort_session（外键 fk_series_cohort_session_course）
        await execute_write(
            "DELETE FROM series_cohort_session WHERE series_cohort_course_id = %s",
            (module_id,),
        )
        return await execute_write(
            "DELETE FROM series_cohort_course WHERE id = %s",
            (module_id,),
        )