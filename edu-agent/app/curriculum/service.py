"""
分级课程 —— 业务服务层。

只做读操作（P0-P 阶段只实现浏览/搜索/详情，新建/编辑留给 P7 管理端）。
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

from app.database import fetch_all, fetch_one
from app.curriculum.schemas import (
    Cohort, Module, Series, SeriesListItem,
    SeriesListResponse, SeriesTreeResponse, Session, SubjectCode, LevelCode,
)


# ============================================================
# 辅助：dict → Pydantic Model（因为我们用 aiomysql 原生 dict，不用 ORM）
# ============================================================
def _row_to_series(row: dict) -> Series:
    return Series(**row)


def _row_to_cohort(row: dict) -> Cohort:
    return Cohort(**row)


def _row_to_module(row: dict) -> Module:
    return Module(**row)


def _row_to_session(row: dict) -> Session:
    return Session(**row)


# ============================================================
# 1. 系列列表（支持学科/分级/关键词 三条件过滤 + 分页）
# ============================================================
async def list_series(
    subject_code: Optional[SubjectCode] = None,
    level_code: Optional[LevelCode] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> SeriesListResponse:
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    where = ["s.sale_status = 'on_sale'"]
    params: list = []
    if subject_code is not None:
        where.append("s.subject_code = %s")
        params.append(subject_code.value)
    if level_code is not None:
        where.append("s.level_code = %s")
        params.append(level_code.value)
    if keyword:
        where.append("(s.series_name LIKE %s OR s.description LIKE %s OR s.level_name LIKE %s)")
        like = f"%{keyword}%"
        params.extend([like, like, like])

    where_sql = " AND ".join(where)

    # 总数 + 列表 同时用一条主 SQL 避免多余查询
    count_sql = f"SELECT COUNT(*) AS total FROM curriculum_series s WHERE {where_sql}"
    total_row = await fetch_one(count_sql, params) or {"total": 0}
    total = int(total_row["total"])

    list_sql = f"""
        SELECT
            s.*,
            (SELECT COUNT(*) FROM curriculum_cohort c WHERE c.series_id = s.id AND c.yn = 1)
                AS cohort_count,
            IFNULL((
                SELECT COUNT(*)
                  FROM curriculum_module m
                  JOIN curriculum_session ss ON ss.module_id = m.id AND ss.yn = 1
                 WHERE m.series_id = s.id AND m.yn = 1
            ), 0) AS total_session_count
        FROM curriculum_series s
        WHERE {where_sql}
        ORDER BY s.sort_no ASC, s.id ASC
        LIMIT {page_size} OFFSET {offset}
    """
    rows = await fetch_all(list_sql, params) or []

    items: list[SeriesListItem] = []
    for row in rows:
        item = SeriesListItem(
            id=row["id"], series_code=row["series_code"],
            series_name=row["series_name"], subject_code=row["subject_code"],
            level_code=row["level_code"], level_name=row["level_name"],
            description=row.get("description"), cover_url=row.get("cover_url"),
            target_hours=row["target_hours"], sale_status=row["sale_status"],
            sort_no=row["sort_no"], created_by=row.get("created_by"),
            created_at=row["created_at"], updated_at=row["updated_at"],
            cohort_count=int(row.get("cohort_count") or 0),
            total_session_count=int(row.get("total_session_count") or 0),
        )
        items.append(item)

    return SeriesListResponse(total=total, page=page, page_size=page_size, items=items)


# ============================================================
# 2. 系列详情（不含班次/模块，留给 tree 接口返回）
# ============================================================
async def get_series(series_id: int) -> Optional[Series]:
    row = await fetch_one(
        "SELECT * FROM curriculum_series WHERE id = %s LIMIT 1",
        (series_id,),
    )
    return _row_to_series(row) if row else None


# ============================================================
# 3. 系列下全部班次
# ============================================================
async def list_cohorts(series_id: int) -> list[Cohort]:
    rows = await fetch_all(
        "SELECT * FROM curriculum_cohort WHERE series_id = %s AND yn = 1 ORDER BY start_date ASC, id ASC",
        (series_id,),
    ) or []
    return [_row_to_cohort(r) for r in rows]


# ============================================================
# 4. 系列下全部模块（不含课次）
# ============================================================
async def list_modules(series_id: int, include_sessions: bool = False) -> list[Module]:
    rows = await fetch_all(
        "SELECT * FROM curriculum_module WHERE series_id = %s AND yn = 1 ORDER BY stage_no ASC, id ASC",
        (series_id,),
    ) or []
    modules = [_row_to_module(r) for r in rows]
    if include_sessions and modules:
        sessions_by_module: dict[int, list[Session]] = await _get_sessions_grouped(
            [m.id for m in modules]
        )
        for m in modules:
            m.sessions = sessions_by_module.get(m.id, [])
    return modules


# ============================================================
# 5. 完整树形（系列 + 班次 + 模块→课次 + 统计摘要）
# ============================================================
async def get_series_tree(series_id: int) -> Optional[SeriesTreeResponse]:
    series = await get_series(series_id)
    if series is None:
        return None
    cohorts = await list_cohorts(series_id)
    modules = await list_modules(series_id, include_sessions=True)

    total_sessions = sum(len(m.sessions) for m in modules)
    total_hours = sum(
        (m.total_hours or Decimal("0")) for m in modules
    )

    return SeriesTreeResponse(
        series=series,
        cohorts=cohorts,
        modules=modules,
        summary_total_sessions=total_sessions,
        summary_total_hours=total_hours,
    )


# ============================================================
# 内部：批量查询课次并按 module_id 分组（少查 N 次）
# ============================================================
async def _get_sessions_grouped(module_ids: Iterable[int]) -> dict[int, list[Session]]:
    ids = list(module_ids)
    if not ids:
        return {}
    placeholders = ", ".join(["%s"] * len(ids))
    rows = await fetch_all(
        f"SELECT * FROM curriculum_session WHERE module_id IN ({placeholders}) AND yn = 1 "
        f"ORDER BY module_id ASC, session_no ASC",
        ids,
    ) or []
    grouped: dict[int, list[Session]] = {}
    for r in rows:
        mid = r["module_id"]
        grouped.setdefault(mid, []).append(_row_to_session(r))
    return grouped
