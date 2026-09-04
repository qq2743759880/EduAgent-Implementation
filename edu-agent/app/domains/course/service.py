"""
课程域服务层（task11）。

职责：
- 组装跨仓储聚合（列表分类名、详情价格区间、模块→课次→视频树）
- 404 语义：系列/班次不存在 → 抛 AppException("40400")（全局 handler 转 401/404 壳）
- 缓存点预留：task23 在此处包 get_or_load（如 list_series 首页热点页）
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from app.common.error_codes import NOT_FOUND
from app.common.exceptions import AppException
from app.core.cache import get_or_load
from app.domains.course.repository import (
    CohortRepo, ModuleRepo, SeriesRepo, SessionRepo, VideoRepo,
)
from app.domains.course.schemas import (
    Cohort, CohortDetail, CohortListData, CohortModulesData,
    Module, ModuleWithSessions,
    SeriesDetail, SeriesListItem, Session, SessionVideo,
)

_series_repo = SeriesRepo()
_cohort_repo = CohortRepo()
_module_repo = ModuleRepo()
_session_repo = SessionRepo()
_video_repo = VideoRepo()

# 合法交付模式（白名单校验，与库值域一致）
DELIVERY_MODES = {"online_live", "online_recorded", "offline_face_to_face"}


def _fix_time_columns(row: dict) -> dict:
    """asyncmy 将 MySQL TIME 列返回为 timedelta → 转 datetime.time（Pydantic time 校验）。

    S7（judge 裁定）：负 timedelta（脏数据）clamp 为 time(0,0) 不抛 500。
    """
    for col in ("start_time", "end_time"):
        val = row.get(col)
        if isinstance(val, timedelta):
            try:
                row[col] = (datetime.min + val).time()
            except OverflowError:
                row[col] = time(0, 0)
    return row


def _parse_json_columns(row: dict) -> dict:
    """series 表 JSON 列（asyncmy 返回 str）→ list。"""
    for col in ("target_learner_identity_codes", "target_learning_goal_codes", "target_grade_codes"):
        val = row.get(col)
        if isinstance(val, str):
            try:
                row[col] = json.loads(val)
            except (ValueError, TypeError):
                row[col] = None
    return row


async def list_series(
    *,
    category: str | None = None,
    delivery_mode: str | None = None,
    keyword: str | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    sort: str = "default",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """
    系列筛选列表。

    Returns:
        {total, page, page_size, items: [SeriesListItem]}（C2：外层 triple 唯一，无 page_meta）
    """
    # S5（judge 裁定）：价格区间倒置 → 422 壳，防止前端静默无结果
    if price_min is not None and price_max is not None and price_min > price_max:
        raise AppException(VALIDATION, "最低价不能高于最高价")

    # 分类名 → category_id 集合（启用分类筛选时）
    series_ids = None
    if category is not None:
        series_ids = await _series_repo.match_category_ids_by_name(category)

    rows, total = await _series_repo.list_series(
        series_ids=series_ids,
        delivery_mode=delivery_mode,
        keyword=keyword,
        price_min=price_min,
        price_max=price_max,
        sort=sort,
        page=page,
        page_size=page_size,
    )

    # 批量聚合分类名（避免 N+1）
    cat_names = await _series_repo.list_category_names_bulk([r["id"] for r in rows])

    items = []
    for r in rows:
        r = _parse_json_columns(r)
        r["category_names"] = cat_names.get(r["id"], [])
        items.append(SeriesListItem(**r))

    # C2: task115 C-B 权威外层 {total,page,page_size,items}（page_meta 双轨已删）
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


async def get_series_detail(series_id: int) -> SeriesDetail:
    """系列详情（全列 + 价格区间 + 分类 + 班次数）。

    缓存点（task23 灰度）：key=course:series:detail:{id}，TTL 300s（±10% 抖动）。
    读缓存命中直回（MySQL 主库 QPS 不随并发线性增长，GWT①）；写后精确 DEL（GWT②）。
    """
    async def _load() -> dict:
        row = await _series_repo.get_series(series_id)
        if row is None:
            raise AppException(NOT_FOUND, "系列不存在或已下架")
        price = await _series_repo.get_price_range(series_id)
        categories = await _series_repo.list_categories(series_id)
        cohort_count = await _series_repo.count_cohorts(series_id)
        row = _parse_json_columns(row)
        return SeriesDetail(
            **row,
            min_price=price["min_price"] if price else None,
            max_price=price["max_price"] if price else None,
            categories=categories,
            cohort_count=cohort_count,
        ).model_dump(mode="json")

    data = await get_or_load(f"course:series:detail:{series_id}", _load, ttl=300)
    return SeriesDetail(**data)


async def list_cohorts(series_id: int) -> CohortListData:
    """
    系列下班次列表（分页壳：全集量小，固定 page=1/page_size=total）。

    R2（judge 裁定）：统一分页壳，避免"裸数组 vs 声明"契约矛盾。
    全集填充语义：page=1, page_size=total（C2：外层 {total,page,page_size,items}，无 page_meta）。
    """
    if await _series_repo.get_series(series_id) is None:
        raise AppException(NOT_FOUND, "系列不存在或已下架")
    rows = await _cohort_repo.list_by_series(series_id)
    items = [Cohort(**r) for r in rows]
    total = len(items)
    return CohortListData(
        total=total,
        page=1,
        page_size=total,
        items=items,
    )


async def get_cohort_detail(cohort_id: int) -> CohortDetail:
    """班次详情（含模块列表，GWT③：模块挂 cohort）。

    缓存点（task23 灰度）：key=course:cohort:detail:{id}，TTL 300s（±10% 抖动）。
    """
    async def _load() -> dict:
        cohort_row = await _cohort_repo.get_cohort(cohort_id)
        if cohort_row is None:
            raise AppException(NOT_FOUND, "班次不存在或已下架")
        module_rows = await _module_repo.list_by_cohort(cohort_id)
        return CohortDetail(
            cohort=Cohort(**cohort_row),
            modules=[Module(**m) for m in module_rows],
        ).model_dump(mode="json")

    data = await get_or_load(f"course:cohort:detail:{cohort_id}", _load, ttl=300)
    return CohortDetail(**data)


async def get_cohort_seats(cohort_id: int) -> dict:
    """班次余位（current/max）。缓存点：key=course:cohort:seats:{id}，TTL 10s（余位实时性敏感，短 TTL）。"""
    async def _load() -> dict:
        row = await _cohort_repo.get_cohort(cohort_id)
        if row is None:
            raise AppException(NOT_FOUND, "班次不存在或已下架")
        return {"cohort_id": cohort_id, "current": int(row["current_student_count"] or 0),
                "max": int(row["max_student_count"] or 0)}

    return await get_or_load(f"course:cohort:seats:{cohort_id}", _load, ttl=10, null_ttl=5)


async def list_cohort_modules(cohort_id: int) -> CohortModulesData:
    """班次模块列表（每模块含课次 + 课次视频）。"""
    cohort_row = await _cohort_repo.get_cohort(cohort_id)
    if cohort_row is None:
        raise AppException(NOT_FOUND, "班次不存在或已下架")

    module_rows = await _module_repo.list_by_cohort(cohort_id)
    module_ids = [m["id"] for m in module_rows]

    # 批量聚合课次与视频（两级避免 N+1）
    sessions_map = await _session_repo.list_by_module_ids(module_ids)
    session_ids = [s["id"] for sess_list in sessions_map.values() for s in sess_list]
    videos_map = await _video_repo.list_by_session_ids(session_ids)

    modules: list[ModuleWithSessions] = []
    for m in module_rows:
        sessions = []
        for s in sessions_map.get(m["id"], []):
            videos = [SessionVideo(**v) for v in videos_map.get(s["id"], [])]
            sessions.append(Session(**_fix_time_columns(s), videos=videos))
        modules.append(ModuleWithSessions(**m, sessions=sessions))

    return CohortModulesData(cohort_id=cohort_id, modules=modules)
