# -*- coding: utf-8 -*-
"""market 域（task16 契约⑦）schemas：优惠券 + 课程收藏。

前端对齐（task40 api-client coupons.ts / favorites.ts）：
- CouponPage 分页壳 {total,page,page_size,items[]}（page_meta 不在本域使用）
- coupon_type 枚举 {cash,discount,trial,gift}（edu.sql coupon.coupon_type 权威）
- receive_status 枚举 {unused,used,expired}（edu.sql coupon_receive_record.receive_status 权威）
- favorite_source 枚举 {series_detail,search_result,recommendation,activity_page}
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ── 值域（与 edu.sql 列注释对齐） ──
CouponType = Literal["cash", "discount", "trial", "gift"]
ReceiveStatus = Literal["unused", "used", "expired"]
FavoriteSource = Literal["series_detail", "search_result", "recommendation", "activity_page"]


# ═══════════════════════════════════════════════════════
# 优惠券
# ═══════════════════════════════════════════════════════
class CouponTemplate(BaseModel):
    """可领券模板（GET /api/coupons?series_id= / GET /api/coupons/templates）。"""
    coupon_template_id: int
    coupon_name: str
    coupon_type: CouponType
    face_value: float = 0
    min_spend: float = 0
    valid_from: datetime
    valid_to: datetime
    total_count: int
    received_count: int
    per_user_limit: int


class Coupon(BaseModel):
    """我的券单条（GET /api/coupons 我的券 / POST receive 结果）。"""
    coupon_id: int = Field(..., description="领券记录 id（coupon_receive_record.id）")
    coupon_template_id: int = Field(..., description="券模板 id（coupon.id）")
    coupon_name: str
    coupon_type: CouponType
    face_value: float = 0
    min_spend: float = 0
    status: ReceiveStatus = "unused"
    valid_from: datetime
    valid_to: datetime
    received_at: datetime
    used_at: datetime | None = None
    order_no: str | None = None


class CouponPage(BaseModel):
    """我的券分页（前端 CouponPage：cmd 枚举分页，非 page_meta）。"""
    total: int
    page: int
    page_size: int
    items: list[Coupon]


class CouponReceiveInput(BaseModel):
    """领券请求体（前端 CouponReceiveInput：coupon_template_id）。"""
    coupon_template_id: int = Field(..., ge=1)


# ═══════════════════════════════════════════════════════
# 课程收藏
# ═══════════════════════════════════════════════════════
class FavoriteItem(BaseModel):
    """我的收藏单条（前端 FavoriteItem）。"""
    favorite_id: int
    user_id: int
    target_type: str = "series"
    series_id: int
    series_title: str | None = None
    cover_url: str | None = None
    created_at: datetime


class FavoriteCreateInput(BaseModel):
    """新增收藏请求体（前端 FavoriteCreateInput：{series_id}）。"""
    series_id: int = Field(..., ge=1)
    favorite_source: FavoriteSource = "series_detail"


class FavoriteDeletedResponse(BaseModel):
    """取消收藏响应（前端 FavoriteDeletedResponse）。"""
    deleted: bool
    series_id: int


class FavoritePage(BaseModel):
    """收藏分页（前端 FavoritePage：{total,page,page_size,items[]}）。"""
    total: int
    page: int
    page_size: int
    items: list[FavoriteItem]