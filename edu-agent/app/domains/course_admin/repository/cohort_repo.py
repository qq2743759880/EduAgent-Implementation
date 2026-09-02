"""Cohort（班次）管理端仓储（task12）。
表 `series_cohort`（有 yn 列，软删 yn=0）。
"""
from __future__ import annotations

from typing import Optional

from app.database import fetch_all, fetch_one, execute_write


class CohortAdminRepo:
    """series_cohort 表管理端仓储。"""

    async def get_by_id(self, cohort_id: int) -> Optional[dict]:
        """按 ID 查班次（不限 yn，管理端可见全部）。"""
        return await fetch_one(
            "SELECT * FROM series_cohort WHERE id = %s",
            (cohort_id,),
        )

    async def get_by_code(self, institution_id: int, cohort_code: str) -> Optional[dict]:
        """按 institution_id + cohort_code 查班次（唯一约束校验）。"""
        return await fetch_one(
            "SELECT * FROM series_cohort WHERE institution_id = %s AND cohort_code = %s",
            (institution_id, cohort_code),
        )

    async def list_by_series(self, series_id: int, *, yn_only: bool = True) -> list[dict]:
        """系列下班次列表。yn_only=True 时仅返回 yn=1（默认，管理端常规列表）。"""
        if yn_only:
            return await fetch_all(
                "SELECT * FROM series_cohort WHERE series_id = %s AND yn = 1 ORDER BY start_date, id",
                (series_id,),
            )
        return await fetch_all(
            "SELECT * FROM series_cohort WHERE series_id = %s ORDER BY start_date, id",
            (series_id,),
        )

    async def insert(self, data: dict) -> int:
        """创建班次，返回自增 ID。"""
        return await execute_write(
            "INSERT INTO series_cohort (institution_id, series_id, campus_id, head_teacher_id, "
            "cohort_code, cohort_name, sale_price, max_student_count, current_student_count, "
            "yn, start_date, end_date, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s, NOW(), NOW())",
            (
                data["institution_id"], data["series_id"], data.get("campus_id"),
                data["head_teacher_id"], data["cohort_code"], data["cohort_name"],
                data["sale_price"], data["max_student_count"], data.get("current_student_count", 0),
                data["start_date"], data.get("end_date"),
            ),
        )

    async def update(self, cohort_id: int, data: dict) -> int:
        """更新班次字段。"""
        set_clauses = []
        args = []
        for key, val in data.items():
            set_clauses.append(f"{key} = %s")
            args.append(val)
        if not set_clauses:
            return 0
        set_clauses.append("updated_at = NOW()")
        args.append(cohort_id)
        return await execute_write(
            f"UPDATE series_cohort SET {', '.join(set_clauses)} WHERE id = %s",
            tuple(args),
        )

    async def soft_delete(self, cohort_id: int) -> int:
        """软删班次：yn = 0。"""
        return await execute_write(
            "UPDATE series_cohort SET yn = 0, updated_at = NOW() WHERE id = %s",
            (cohort_id,),
        )

    async def restore(self, cohort_id: int) -> int:
        """恢复班次：yn = 1。"""
        return await execute_write(
            "UPDATE series_cohort SET yn = 1, updated_at = NOW() WHERE id = %s",
            (cohort_id,),
        )