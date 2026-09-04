# -*- coding: utf-8 -*-
"""market 域（task16 契约⑦）service：优惠券 + 课程收藏。

幂等三层纵深（tech-source-audit §四 + task16 GWT）：
1. 业务层幂等：receive 先查「已领则返回原记录」；POST /favorites 已收藏返回原记录
2. 唯一键幂等：receive_no 唯一键 + series_favorite(user_id, series_id) 唯一键，DB 兜底
3. 条件更新防超发：UPDATE ... WHERE receive_count<total_count，受影响行数=0 → 40920 已领完
"""
from __future__ import annotations

from datetime import datetime

from app.common.error_codes import NOT_FOUND, TRADE_COUPON_EXHAUSTED
from app.common.exceptions import AppException
from app.domains.market.repository import CouponRepo, FavoriteRepo
from app.domains.market.schemas import (
    Coupon, CouponPage, CouponTemplate, FavoriteDeletedResponse,
    FavoriteItem, FavoritePage,
)

# 收藏来源默认（前端未传时）
DEFAULT_FAVORITE_SOURCE = "series_detail"

_coupon_repo = CouponRepo()
_favorite_repo = FavoriteRepo()


# ═══════════════════════════════════════════════════════
# 工具：券行 → 响应模型
# ═══════════════════════════════════════════════════════
def _effective_status(row: dict) -> str:
    """计算券当前状态：used 优先（used_at 有值）；否则 valid_to 已过 → expired；否则 unused。"""
    if row.get("receive_status") == "used" or row.get("used_at") is not None:
        return "used"
    valid_to = row.get("valid_to")
    if valid_to is not None:
        vt = valid_to if valid_to.tzinfo else valid_to
        if vt < datetime.now():
            return "expired"
    return "unused"


def _template_from_row(row: dict) -> CouponTemplate:
    coupon_type = row["coupon_type"]
    if coupon_type == "discount":
        face_value = float(row.get("discount_rate") or 0)
    else:
        face_value = float(row.get("discount_amount") or 0)
    return CouponTemplate(
        coupon_template_id=int(row["id"]),
        coupon_name=row["coupon_name"],
        coupon_type=coupon_type,
        face_value=face_value,
        min_spend=float(row.get("threshold_amount") or 0),
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        total_count=int(row.get("total_count") or 0),
        received_count=int(row.get("receive_count") or 0),
        per_user_limit=int(row.get("per_user_limit") or 1),
    )


def _coupon_from_receive(row: dict) -> Coupon:
    """领券记录 JOIN coupon → Coupon 模型。"""
    coupon_type = row["coupon_type"]
    if coupon_type == "discount":
        face_value = float(row.get("discount_rate") or 0)
    else:
        face_value = float(row.get("discount_amount") or 0)
    return Coupon(
        coupon_id=int(row["receive_record_id"]),
        coupon_template_id=int(row["coupon_id"]),
        coupon_name=row["coupon_name"],
        coupon_type=coupon_type,
        face_value=face_value,
        min_spend=float(row.get("threshold_amount") or 0),
        status=_effective_status(row),
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        received_at=row["received_at"],
        used_at=row.get("used_at"),
        order_no=None,
    )


# ═══════════════════════════════════════════════════════
# 优惠券读
# ═══════════════════════════════════════════════════════
async def list_coupon_templates(*, series_id: int | None = None) -> list[CouponTemplate]:
    """可领券模板列表（GET /api/coupons?series_id= 可领 / /api/coupons/templates 全部）。"""
    rows = await _coupon_repo.list_templates(series_id=series_id)
    return [_template_from_row(r) for r in rows]


async def list_my_coupons(
    user_id: int, *, status: str | None = None, page: int = 1, page_size: int = 20,
) -> CouponPage:
    """我的券列表（GET /api/coupons 我的；含 receive_status 过滤）。"""
    rows, total = await _coupon_repo.list_my_coupons(
        user_id, status=status, page=page, page_size=page_size,
    )
    items = [_coupon_from_receive(r) for r in rows]
    return CouponPage(total=total, page=page, page_size=page_size, items=items)


# ═══════════════════════════════════════════════════════
# 领券（防超发）
# ═══════════════════════════════════════════════════════
async def receive_coupon(user_id: int, coupon_template_id: int) -> Coupon:
    """
    领券。幂等 + 防超发：
    1. 幂等判重：已领同一券 → 返回原记录（不重复占额度）
    2. 条件更新 receive_count（WHO receive_count<total_count）→ 0 行 = 已领完 → 40920
    3. 事务内写 coupon_receive_record（receive_no 唯一键兜底）
    """
    coupon = await _coupon_repo.get_coupon(coupon_template_id)
    if coupon is None:
        raise AppException(NOT_FOUND, "优惠券不存在或已下架")

    # 幂等判重：已领 → 返回原记录（GWT②：重复领返回原记录）
    existing = await _coupon_repo.get_my_coupon(coupon_template_id, user_id)
    if existing is not None:
        return _coupon_from_receive(existing)

    now = datetime.now()
    expired_at = coupon["valid_to"]
    result = await _coupon_repo.receive_in_transaction(
        coupon_id=coupon_template_id, user_id=user_id,
        receive_source="coupon_center", expired_at=expired_at, now=now,
    )
    if not result["created"]:
        # 条件更新 0 行 → 已领完
        raise AppException(TRADE_COUPON_EXHAUSTED, "该优惠券已被领完")

    # 返回领券成功后的记录（幂等重查，获取最新 receive_status）
    anew = await _coupon_repo.get_my_coupon(coupon_template_id, user_id)
    if anew is None:
        # 极端兜底：直接按事务结果构造（券模板行列名为 id，需映射成 coupon_id/valid_to）
        coupon_template = dict(coupon)
        coupon_row = {**coupon_template,
                      "coupon_id": coupon_template["id"],
                      "receive_record_id": result["receive_record_id"],
                      "receive_status": "unused", "received_at": now,
                      "used_at": None}
        return _coupon_from_receive(coupon_row)
    return _coupon_from_receive(anew)


# ═══════════════════════════════════════════════════════
# 课程收藏（幂等）
# ═══════════════════════════════════════════════════════
async def list_favorites(user_id: int, *, page: int = 1, page_size: int = 20) -> FavoritePage:
    """我的收藏分页（GET /api/favorites）。"""
    rows, total = await _favorite_repo.list_favorites(user_id, page=page, page_size=page_size)
    items = [
        FavoriteItem(
            favorite_id=int(r["id"]),
            user_id=int(r["user_id"]),
            target_type="series",
            series_id=int(r["series_id"]),
            series_title=r.get("series_name"),
            cover_url=r.get("cover_url"),
            created_at=r["created_at"],
        )
        for r in rows
    ]
    return FavoritePage(total=total, page=page, page_size=page_size, items=items)


async def add_favorite(user_id: int, series_id: int, favorite_source: str) -> FavoriteItem:
    """
    新增收藏（POST /api/favorites）。服务端幂等：
    已收藏（yn=1）→ 返回原记录；软删（yn=0）→ 重收藏激活；未收藏 → 新建。
    """
    # 系列校验（存在 + on_sale）
    if await _favorite_repo.get_series(series_id) is None:
        raise AppException(NOT_FOUND, "课程系列不存在或已下架")

    now = datetime.now()
    favorite_id = await _favorite_repo.create_favorite(
        series_id=series_id, user_id=user_id,
        favorite_source=favorite_source or DEFAULT_FAVORITE_SOURCE, now=now,
    )
    # 幂等返回原记录（create_favorite 内部 ON DUPLICATE，favorite_id 恒为该系列收藏行）
    row = await _favorite_repo.get_series_name_for_favorite(favorite_id)
    if row is None:
        # 兜底（极端竞争）
        row = await _favorite_repo.get_active_favorite(series_id, user_id)
    return FavoriteItem(
        favorite_id=int(row["id"]),
        user_id=int(row["user_id"]),
        target_type="series",
        series_id=int(row["series_id"]),
        series_title=row.get("series_name"),
        cover_url=row.get("cover_url"),
        created_at=row["created_at"],
    )


async def remove_favorite(user_id: int, series_id: int) -> FavoriteDeletedResponse:
    """取消收藏（DELETE /api/favorites/{series_id}）。软删幂等：重复删除返回 deleted=True。"""
    affected = await _favorite_repo.soft_delete_favorite(series_id, user_id)
    # 幂等语义：已删/不存在也返回 deleted=True（满足 GWT② 幂等）
    return FavoriteDeletedResponse(deleted=True, series_id=series_id)