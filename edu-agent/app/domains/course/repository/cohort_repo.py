"""班次仓储（series_cohort 表）。"""
from __future__ import annotations

from typing import Optional

from app.database import fetch_all, fetch_one


class CohortRepo:
    """series_cohort 表仓储（软删 yn=1 过滤）。"""

    async def list_by_series(self, series_id: int) -> list[dict]:
        """系列下全部在售班次（按开班日期升序）。"""
        return await fetch_all(
            "SELECT * FROM series_cohort "
            "WHERE series_id = %s AND yn = 1 "
            "ORDER BY start_date, id",
            (series_id,),
        )

    async def get_cohort(self, cohort_id: int) -> Optional[dict]:
        """
        班次单行（yn=1 且父系列在售）。

        S6（judge 裁定）：JOIN series 校验 sale_status='on_sale'——
        已下架系列的班次直达也 404，与 /api/series/{id} 口径一致（下架即整体不可见）。
        """
        return await fetch_one(
            "SELECT c.* FROM series_cohort c "
            "JOIN series s ON s.id = c.series_id AND s.sale_status = 'on_sale' "
            "WHERE c.id = %s AND c.yn = 1 LIMIT 1",
            (cohort_id,),
        )
