"""
旧课程路由 → 308 永久重定向（task11：curriculum→series 迁移兼容层）。

契约（GWT②）：/api/curriculum/series → 308 → /api/series 且参数完整保留。
308（Permanent Redirect）与 301 的区别：保留原请求方法（GET/POST），语义为永久迁移，
前端/网关可缓存；浏览器与 fetch 均自动跟随。

层级语义变化说明：旧 /modules、/tree 端点基于「模块挂 series」的旧模型，
新层级为 series→cohort→module→session（模块挂 cohort），故统一重定向到系列详情，
由前端在详情页沿新层级逐级获取。
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter(
    prefix="/api/curriculum",
    tags=["curriculum · 旧路由重定向（308）"],
    include_in_schema=False,
)


def _redirect(request: Request, new_path: str) -> RedirectResponse:
    """构造 308 重定向，完整保留 query 参数。"""
    qs = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(url=f"{new_path}{qs}", status_code=308)


@router.get("/series")
async def legacy_series_list(request: Request):
    """旧系列列表 → /api/series（GWT② 验收端点）。"""
    return _redirect(request, "/api/series")


@router.get("/series/{series_id}")
async def legacy_series_detail(request: Request, series_id: int):
    """旧系列详情 → /api/series/{id}。"""
    return _redirect(request, f"/api/series/{series_id}")


@router.get("/series/{series_id}/cohorts")
async def legacy_series_cohorts(request: Request, series_id: int):
    """旧系列班次 → /api/series/{id}/cohorts。"""
    return _redirect(request, f"/api/series/{series_id}/cohorts")


@router.get("/series/{series_id}/modules")
async def legacy_series_modules(request: Request, series_id: int):
    """旧系列模块（层级已变：模块挂 cohort）→ 系列详情。"""
    return _redirect(request, f"/api/series/{series_id}")


@router.get("/series/{series_id}/tree")
async def legacy_series_tree(request: Request, series_id: int):
    """旧系列树（层级已变）→ 系列详情。"""
    return _redirect(request, f"/api/series/{series_id}")
