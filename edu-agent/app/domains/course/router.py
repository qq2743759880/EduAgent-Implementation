"""
课程域路由（task11 契约冻结② —— C 端 5 端点，匿名可访问）。

契约：
- 响应壳沿用契约①：成功 ok() / 失败 AppException → 全局 handler
- 筛选参数：category（分类名模糊）/ delivery_mode（白名单）/ keyword / price_min / price_max
- 排序白名单：default / newest / price_asc / price_desc
- 分页：page ≥ 1，page_size 1~100
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.core.resp import ok
from app.domains.course import service as svc
from app.domains.course.service import DELIVERY_MODES

router = APIRouter(tags=["course · 课程系列（C 端）"])


# ============================================================
# 1. 系列列表（浏览/搜索主入口）
# ============================================================
@router.get("/api/series", summary="系列列表（学科分类/交付模式/关键词/价格区间/排序/分页）")
async def list_series(
    category: Optional[str] = Query(None, description="分类名（模糊，如：编程/数学/考研）", max_length=64),
    delivery_mode: Optional[str] = Query(
        None,
        description=f"交付模式，可选值：{'/'.join(sorted(DELIVERY_MODES))}",
        pattern=r"^(online_live|online_recorded|offline_face_to_face)$",
    ),
    keyword: Optional[str] = Query(None, description="关键词（名称/简介/编码模糊）", min_length=1, max_length=64),
    price_min: Optional[float] = Query(None, ge=0, allow_inf_nan=False, description="最低价（按班次最低价过滤）"),
    price_max: Optional[float] = Query(None, ge=0, allow_inf_nan=False, description="最高价"),
    sort: str = Query("default", pattern=r"^(default|newest|price_asc|price_desc)$", description="排序"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数，1~100"),
):
    data = await svc.list_series(
        category=category,
        delivery_mode=delivery_mode,
        keyword=keyword,
        price_min=price_min,
        price_max=price_max,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    # data 为 {total,page,page_size,items:[BaseModel]}，FastAPI jsonable_encoder 自动展开
    return ok(data=data)


# ============================================================
# 2. 系列详情
# ============================================================
@router.get("/api/series/{series_id}", summary="系列详情（全列 + 价格区间 + 分类 + 班次数）")
async def get_series_detail(series_id: int):
    detail = await svc.get_series_detail(series_id)
    return ok(data=detail.model_dump(mode="json"))


# ============================================================
# 3. 系列 → 班次列表
# ============================================================
@router.get("/api/series/{series_id}/cohorts", summary="系列下全部在售班次")
async def list_series_cohorts(series_id: int):
    # task39 压测采样发现：svc.list_cohorts 自 R2 裁定起返回 **CohortListData 分页壳**
    # （外层 {total,page,page_size,items}，C2 删 page_meta），不再是裸列表。直接迭代
    # pydantic 模型得到的是 (字段名, 值) 元组 → 元组无 .model_dump() → 该接口**无条件 500**。
    # 出口形态与 get_series_detail / get_cohort_detail 对齐。
    cohorts = await svc.list_cohorts(series_id)
    return ok(data=cohorts.model_dump(mode="json"))


# ============================================================
# 4. 班次详情（含模块 —— 模块挂 cohort，GWT③ 层级语义）
# ============================================================
@router.get("/api/cohorts/{cohort_id}", summary="班次详情（含模块列表）")
async def get_cohort_detail(cohort_id: int):
    detail = await svc.get_cohort_detail(cohort_id)
    return ok(data=detail.model_dump(mode="json"))


# ============================================================
# 5. 班次 → 模块列表（含课次 + 视频）
# ============================================================
@router.get("/api/cohorts/{cohort_id}/modules", summary="班次模块列表（每模块含课次与视频）")
async def list_cohort_modules(cohort_id: int):
    data = await svc.list_cohort_modules(cohort_id)
    return ok(data=data.model_dump(mode="json"))
