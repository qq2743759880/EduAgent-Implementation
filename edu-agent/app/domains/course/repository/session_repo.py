"""
课次仓储（series_cohort_course 模块表 + series_cohort_session 课次表）。

层级语义（task11 GWT③ 核心）：
- 模块挂 cohort（series_cohort_course.cohort_id），而非挂 series —— 修复旧 curriculum P3 层级问题
- 课次挂模块（series_cohort_session.series_cohort_course_id）
"""
from __future__ import annotations

from app.database import fetch_all


class ModuleRepo:
    """series_cohort_course（模块）表仓储。表无 yn 列。"""

    async def list_by_cohort(self, cohort_id: int) -> list[dict]:
        """班次下全部模块（按教学阶段排序）。"""
        return await fetch_all(
            "SELECT * FROM series_cohort_course "
            "WHERE cohort_id = %s "
            "ORDER BY stage_no, module_code, id",
            (cohort_id,),
        )


class SessionRepo:
    """series_cohort_session（课次）表仓储。表无 yn 列。"""

    async def list_by_module_ids(self, module_ids: list[int]) -> dict[int, list[dict]]:
        """批量取模块→课次列表（按课次号排序），避免 N+1。"""
        if not module_ids:
            return {}
        placeholders = ", ".join(["%s"] * len(module_ids))
        rows = await fetch_all(
            "SELECT * FROM series_cohort_session "
            f"WHERE series_cohort_course_id IN ({placeholders}) "
            "ORDER BY series_cohort_course_id, session_no, id",
            tuple(module_ids),
        )
        result: dict[int, list[dict]] = {mid: [] for mid in module_ids}
        for r in rows:
            result.setdefault(r["series_cohort_course_id"], []).append(r)
        return result
