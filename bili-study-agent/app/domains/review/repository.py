"""课程系列评价域 repository（Season-2 需求 B）。

数据访问与约定的 carrier（real DB，无 MOCK）：
- 唯一键 (series_id, user_id) 防同用户重复评价（DB 级）。
- 软删（yn=0）遵循 C-C 语义；软删后同用户重新评价走"复活"更新（yn=1）。
- 报名校验：已报名该系列（student_cohort_rel 任一 active 班次命中）才可评价。
"""
from __future__ import annotations

from app.database import execute_write, fetch_all, fetch_one


class ReviewRepo:
    """评价读写仓储。"""

    async def get_series(self, series_id: int) -> dict | None:
        """系列存在性（评价对象）。"""
        return await fetch_one(
            "SELECT id, series_name, sale_status FROM series WHERE id=%s LIMIT 1",
            (series_id,),
        )

    async def is_enrolled(self, series_id: int, user_id: int) -> bool:
        """该用户是否已报名该系列（任一 active 生效班次命中）。"""
        row = await fetch_one(
            "SELECT scr.id FROM student_cohort_rel scr"
            " JOIN series_cohort c ON c.id = scr.cohort_id"
            " WHERE scr.user_id=%s AND c.series_id=%s AND scr.enroll_status='active' LIMIT 1",
            (user_id, series_id),
        )
        return row is not None

    async def get_active(self, series_id: int, user_id: int) -> dict | None:
        """取同用户同系列的生效评价（yn=1）。"""
        return await fetch_one(
            "SELECT id, rating, content, yn FROM course_review"
            " WHERE series_id=%s AND user_id=%s AND yn=1 LIMIT 1",
            (series_id, user_id),
        )

    async def get_any(self, series_id: int, user_id: int) -> dict | None:
        """取同用户同系列的任意评价行（含软删，用于复活；唯一键保证至多一行）。"""
        return await fetch_one(
            "SELECT id, yn FROM course_review WHERE series_id=%s AND user_id=%s LIMIT 1",
            (series_id, user_id),
        )

    async def insert_review(self, series_id: int, user_id: int, rating: int, content: str | None) -> int:
        """新增评价。"""
        return await execute_write(
            "INSERT INTO course_review (series_id, user_id, rating, content, yn, created_at, updated_at)"
            " VALUES (%s, %s, %s, %s, 1, NOW(), NOW())",
            (series_id, user_id, rating, content),
        )

    async def reactivate_review(self, review_id: int, rating: int, content: str | None) -> None:
        """软删评价复活并更新（yn=1）。"""
        await execute_write(
            "UPDATE course_review SET rating=%s, content=%s, yn=1, updated_at=NOW() WHERE id=%s",
            (rating, content, review_id),
        )

    async def list_reviews(
        self, series_id: int, *, page: int = 1, page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """某系列评价列表（分页，含用户昵称联表）。"""
        cnt = await fetch_one(
            "SELECT COUNT(*) AS c FROM course_review WHERE series_id=%s AND yn=1",
            (series_id,),
        )
        total = int(cnt["c"]) if cnt else 0
        rows = await fetch_all(
            "SELECT r.id, r.series_id, r.user_id, r.rating, r.content, r.created_at, r.updated_at, "
            " u.nickname AS nickname"
            " FROM course_review r LEFT JOIN sys_user u ON u.id = r.user_id"
            " WHERE r.series_id=%s AND r.yn=1"
            " ORDER BY r.id DESC LIMIT %s OFFSET %s",
            (series_id, page_size, (page - 1) * page_size),
        )
        return rows, total

    async def admin_get(self, review_id: int) -> dict | None:
        """管理端按 id 取评价（供软删前校验）。"""
        return await fetch_one(
            "SELECT id, series_id, user_id, rating, content, yn FROM course_review WHERE id=%s LIMIT 1",
            (review_id,),
        )

    async def soft_delete(self, review_id: int) -> int:
        """软删（yn=0）。返回受影响行数。"""
        return await execute_write(
            "UPDATE course_review SET yn=0, updated_at=NOW() WHERE id=%s AND yn=1",
            (review_id,),
        )

    async def admin_list(
        self, *, series_id: int | None = None, page: int = 1, page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """管理端评价列表（分页 + 可按 series 过滤，仅生效 yn=1）。"""
        where = ["r.yn=1"]
        args: list = []
        if series_id is not None:
            where.append("r.series_id=%s")
            args.append(series_id)
        base = (
            " FROM course_review r LEFT JOIN sys_user u ON u.id = r.user_id"
            f" WHERE {' AND '.join(where)}"
        )
        cnt = await fetch_one(f"SELECT COUNT(*) AS c{base}", tuple(args))
        total = int(cnt["c"]) if cnt else 0
        rows = await fetch_all(
            "SELECT r.id, r.series_id, r.user_id, r.rating, r.content, r.created_at, r.updated_at, "
            " u.nickname AS nickname"
            f"{base} ORDER BY r.id DESC LIMIT %s OFFSET %s",
            tuple(args + [page_size, (page - 1) * page_size]),
        )
        return rows, total


repo = ReviewRepo()