"""课程系列评价域 service（Season-2 需求 B）。

业务规则：
- POST 评价：必须已报名该系列（active）才可评价；同 user+series 已存在（yn=1）→ 409 防刷；
  仅存软删（yn=0）行 → 复活更新（yn=1）。
- 管理端删除：软删 yn=0（C-C 语义）。
"""
from __future__ import annotations

from app.common.error_codes import STUDY_REVIEW_DUPLICATE
from app.common.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.domains.review.repository import repo
from app.domains.review.schemas import ReviewPage, ReviewOut


async def list_reviews(series_id: int, *, page: int = 1, page_size: int = 20) -> ReviewPage:
    """某系列评价列表（分页含昵称）。"""
    series = await repo.get_series(series_id)
    if series is None:
        raise NotFoundError("系列", str(series_id))
    rows, total = await repo.list_reviews(series_id, page=page, page_size=page_size)
    items = [ReviewOut(**r) for r in rows]
    return ReviewPage(total=total, page=page, page_size=page_size, items=items)


async def create_review(series_id: int, user_id: int, rating: int, content: str | None) -> dict:
    """提交评价（报名校验 + 防刷 + 软删复活）。"""
    series = await repo.get_series(series_id)
    if series is None:
        raise NotFoundError("系列", str(series_id))
    if not await repo.is_enrolled(series_id, user_id):
        raise PermissionDeniedError("未报名该系列，无法评价")

    # 防刷：同 user+series 已存在生效评价 → 409
    active = await repo.get_active(series_id, user_id)
    if active is not None:
        raise ConflictError("您已评价过该系列，请勿重复评价", code=STUDY_REVIEW_DUPLICATE)

    # 仅存软删行（唯一键保证至多一行）→ 复活更新；否则新增
    existed = await repo.get_any(series_id, user_id)
    if existed is not None:
        await repo.reactivate_review(int(existed["id"]), rating, content)
        review_id = int(existed["id"])
        created = False
    else:
        review_id = int(await repo.insert_review(series_id, user_id, rating, content))
        created = True

    return {"id": review_id, "series_id": series_id, "user_id": user_id,
            "rating": rating, "created": created}


async def admin_list_reviews(*, series_id: int | None = None, page: int = 1, page_size: int = 20) -> ReviewPage:
    """管理端评价列表（可分页 + series 过滤）。"""
    rows, total = await repo.admin_list(series_id=series_id, page=page, page_size=page_size)
    items = [ReviewOut(**r) for r in rows]
    return ReviewPage(total=total, page=page, page_size=page_size, items=items)


async def admin_delete_review(review_id: int) -> dict:
    """管理端软删评价（yn=0）。"""
    row = await repo.admin_get(review_id)
    if row is None:
        raise NotFoundError("评价", str(review_id))
    affected = await repo.soft_delete(review_id)
    return {"deleted": affected > 0, "id": review_id}