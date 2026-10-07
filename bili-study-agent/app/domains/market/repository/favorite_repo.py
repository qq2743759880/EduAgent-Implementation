# -*- coding: utf-8 -*-
"""课程收藏仓储：series_favorite JOIN series。

幂等（GWT②）：
- POST：先查已有收藏（user_id, series_id 唯一键），已收藏 → 返回原记录（不重复插入）
- DELETE：软删 yn=0；重复删除返回原删除结果
"""
from __future__ import annotations

from datetime import datetime

from app.database import execute_write, fetch_all, fetch_one


class FavoriteRepo:
    """series_favorite 仓储。"""

    async def get_favorite(self, series_id: int, user_id: int) -> dict | None:
        """查某用户对某系列的收藏（含 yn=0 的软删记录）。"""
        return await fetch_one(
            "SELECT id, user_id, series_id, favorite_source, yn, created_at"
            " FROM series_favorite WHERE user_id = %s AND series_id = %s LIMIT 1",
            (user_id, series_id),
        )

    async def get_active_favorite(self, series_id: int, user_id: int) -> dict | None:
        """查有效（yn=1）收藏。"""
        return await fetch_one(
            "SELECT f.id, f.user_id, f.series_id, f.favorite_source, f.created_at,"
            " s.series_name, s.cover_url"
            " FROM series_favorite f JOIN series s ON s.id = f.series_id"
            " WHERE f.user_id = %s AND f.series_id = %s AND f.yn = 1 LIMIT 1",
            (user_id, series_id),
        )

    async def list_favorites(
        self, user_id: int, *, page: int = 1, page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """我的收藏分页（JOIN series 取标题/封面）。"""
        cnt = await fetch_one(
            "SELECT COUNT(*) AS c FROM series_favorite WHERE user_id = %s AND yn = 1",
            (user_id,),
        )
        total = int(cnt["c"]) if cnt else 0
        rows = await fetch_all(
            "SELECT f.id, f.user_id, f.series_id, f.favorite_source, f.created_at,"
            " s.series_name, s.cover_url"
            " FROM series_favorite f JOIN series s ON s.id = f.series_id"
            " WHERE f.user_id = %s AND f.yn = 1"
            " ORDER BY f.id DESC LIMIT %s OFFSET %s",
            (user_id, page_size, (page - 1) * page_size),
        )
        return rows, total

    async def get_series(self, series_id: int) -> dict | None:
        """校验系列存在且 on_sale。"""
        return await fetch_one(
            "SELECT id, series_name, cover_url FROM series"
            " WHERE id = %s AND sale_status = 'on_sale' LIMIT 1",
            (series_id,),
        )

    async def create_favorite(
        self, *, series_id: int, user_id: int, favorite_source: str, now: datetime,
    ) -> int:
        """新增收藏，返回 favorite_id（幂等：更新软删记录为 yn=1 而非报错）。"""
        await execute_write(
            "INSERT INTO series_favorite (user_id, series_id, favorite_source, yn, created_at, updated_at)"
            " VALUES (%s, %s, %s, 1, %s, %s)"
            " ON DUPLICATE KEY UPDATE yn = 1, favorite_source = VALUES(favorite_source), updated_at = VALUES(updated_at)",
            (user_id, series_id, favorite_source, now, now),
        )
        row = await fetch_one(
            "SELECT id FROM series_favorite WHERE user_id = %s AND series_id = %s LIMIT 1",
            (user_id, series_id),
        )
        return int(row["id"]) if row else 0

    async def soft_delete_favorite(self, series_id: int, user_id: int) -> int:
        """软删收藏（yn=0），返回受影响行数（0=不存在/已删）。"""
        return await execute_write(
            "UPDATE series_favorite SET yn = 0, updated_at = NOW()"
            " WHERE user_id = %s AND series_id = %s AND yn = 1",
            (user_id, series_id),
        )

    async def get_series_name_for_favorite(self, favorite_id: int) -> dict | None:
        """按收藏 id 取（series 标题/封面 + 收藏时间）—— POST 幂等返回原记录用。"""
        return await fetch_one(
            "SELECT f.id, f.user_id, f.series_id, f.favorite_source, f.created_at,"
            " s.series_name, s.cover_url"
            " FROM series_favorite f JOIN series s ON s.id = f.series_id"
            " WHERE f.id = %s AND f.yn = 1 LIMIT 1",
            (favorite_id,),
        )