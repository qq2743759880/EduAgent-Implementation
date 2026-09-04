"""
系列仓储（series + dim_course_category + series_category_rel）。

设计要点：
- 列表筛选动态拼 WHERE（占位符参数化），排序走白名单映射（防注入）
- min_price：series 主表无价格，LEFT JOIN 子查询聚合 series_cohort.sale_price（yn=1）
- category：名称模糊匹配 dim_course_category，经 series_category_rel 命中 series_id 集合
- 缓存点预留：task23 在 service 层接入 get_or_load（repo 保持纯数据访问）
"""
from __future__ import annotations

from typing import Optional

from app.database import fetch_all, fetch_one

# 排序白名单：外部参数 → SQL 排序表达式（禁止直接拼接用户输入）
# S4：price_asc 用 "(min_price IS NULL)" 前置，无价系列（无在售班次）排最后（MySQL NULLS LAST 等效）
# P1-1（task16 gap）：popular=系列实付销量降序（order_item paid/completed 经 cohort 挂系列）。
#   sales_count 列在 list_series 中 sort=='popular' 时注入 base_sql 派生表；白名单仅放行的表达式。
_SORT_MAP = {
    "default": "id DESC",
    "newest": "created_at DESC, id DESC",
    "price_asc": "(min_price IS NULL), min_price ASC, id DESC",
    "price_desc": "min_price DESC, id DESC",  # DESC 时 NULL 天然排最后，无需处理
    "popular": "sales_count DESC, id DESC",
}

# 系列表无 yn 软删列（以 sale_status 表达生命周期）


class SeriesRepo:
    """series 表仓储。"""

    async def match_category_ids_by_name(self, name_keyword: str) -> list[int]:
        """按分类名称模糊匹配（如「编程」→ 编程语言/Web编程语言…）→ category_id 列表。"""
        rows = await fetch_all(
            "SELECT id FROM dim_course_category "
            "WHERE yn = 1 AND category_name LIKE %s",
            (f"%{name_keyword}%",),
        )
        return [r["id"] for r in rows]

    async def list_series(
        self,
        *,
        series_ids: Optional[list[int]] = None,
        delivery_mode: Optional[str] = None,
        keyword: Optional[str] = None,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        sort: str = "default",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """
        筛选分页列表。

        Args:
            series_ids: category 命中的分类 ID 集合；传空列表表示分类无匹配 → 空结果；
                        传 None 表示未启用分类筛选
            price_min/price_max: 按班次最低价（min_price）过滤

        Returns:
            (rows, total)
        """
        where: list[str] = []
        args: list = []

        # 分类筛选：IN 子查询（series_ids 为空列表时直接短路返回空）
        if series_ids is not None:
            if not series_ids:
                return [], 0
            placeholders = ", ".join(["%s"] * len(series_ids))
            where.append(
                f"s.id IN (SELECT series_id FROM series_category_rel "
                f"WHERE category_id IN ({placeholders}))"
            )
            args.extend(series_ids)

        if delivery_mode is not None:
            where.append("s.delivery_mode = %s")
            args.append(delivery_mode)

        if keyword is not None:
            where.append("(s.series_name LIKE %s OR s.description LIKE %s OR s.series_code LIKE %s)")
            args.extend([f"%{keyword}%"] * 3)

        # P1-1（task16 gap）：sort=popular 时把系列实付销量聚合为派生列 sales_count，
        # 供 _SORT_MAP["popular"] 排序；仅该分支注入，避免非热门需求下为每行跑销量子查询。
        # harden：销量 = order_item(paid/completed) 经 series_cohort 聚合，全部参数化，无路径注入。
        sales_sel = ""
        if sort == "popular":
            sales_sel = (
                "  , (SELECT COUNT(*) FROM order_item oi"
                "      JOIN series_cohort sc ON sc.id = oi.cohort_id"
                "      WHERE sc.series_id = s.id AND sc.yn = 1"
                "        AND oi.order_item_status IN ('paid','completed')) AS sales_count"
            )

        # 基础行集（派生表 t：系列 + 聚合最低价 + 可选销量，只保留在售）
        base_sql = (
            "SELECT * FROM ("
            "  SELECT s.*"
            + sales_sel
            + ","
            "    (SELECT MIN(sale_price) FROM series_cohort c WHERE c.series_id = s.id AND c.yn = 1) AS min_price"
            "  FROM series s"
            "  WHERE s.sale_status = 'on_sale'"
            + ("".join(f" AND {w}" for w in where))
            + ") t WHERE 1=1"
        )

        # 价格过滤作用于聚合列（在派生表外层）
        if price_min is not None:
            base_sql += " AND t.min_price >= %s"
            args.append(price_min)
        if price_max is not None:
            base_sql += " AND t.min_price <= %s"
            args.append(price_max)

        # 计数
        cnt_row = await fetch_one(f"SELECT COUNT(*) AS cnt FROM ({base_sql}) x", tuple(args))
        total = int(cnt_row["cnt"]) if cnt_row else 0

        # 排序 + 分页（白名单映射，防注入）
        order_by = _SORT_MAP.get(sort, _SORT_MAP["default"])
        page_sql = f"SELECT * FROM ({base_sql}) x ORDER BY {order_by} LIMIT %s OFFSET %s"
        rows = await fetch_all(page_sql, tuple(args + [page_size, (page - 1) * page_size]))
        return rows, total

    async def get_series(self, series_id: int) -> Optional[dict]:
        """系列主表单行（on_sale 才返回）。"""
        return await fetch_one(
            "SELECT * FROM series WHERE id = %s AND sale_status = 'on_sale' LIMIT 1",
            (series_id,),
        )

    async def get_price_range(self, series_id: int) -> Optional[dict]:
        """系列下班次价格区间（yn=1）。"""
        return await fetch_one(
            "SELECT MIN(sale_price) AS min_price, MAX(sale_price) AS max_price "
            "FROM series_cohort WHERE series_id = %s AND yn = 1",
            (series_id,),
        )

    async def count_cohorts(self, series_id: int) -> int:
        row = await fetch_one(
            "SELECT COUNT(*) AS cnt FROM series_cohort WHERE series_id = %s AND yn = 1",
            (series_id,),
        )
        return int(row["cnt"]) if row else 0

    async def list_categories(self, series_id: int) -> list[dict]:
        """系列的分类列表（经 series_category_rel）。"""
        return await fetch_all(
            "SELECT c.id, c.category_code, c.category_name, c.category_level "
            "FROM series_category_rel r "
            "JOIN dim_course_category c ON c.id = r.category_id AND c.yn = 1 "
            "WHERE r.series_id = %s "
            "ORDER BY c.category_level, c.sort_no, c.id",
            (series_id,),
        )

    async def list_category_names_bulk(self, series_ids: list[int]) -> dict[int, list[str]]:
        """批量取系列→分类名列表（列表页聚合用，避免 N+1）。"""
        if not series_ids:
            return {}
        placeholders = ", ".join(["%s"] * len(series_ids))
        rows = await fetch_all(
            "SELECT r.series_id, c.category_name "
            "FROM series_category_rel r "
            "JOIN dim_course_category c ON c.id = r.category_id AND c.yn = 1 "
            f"WHERE r.series_id IN ({placeholders}) "
            "ORDER BY c.category_level, c.sort_no",
            tuple(series_ids),
        )
        result: dict[int, list[str]] = {sid: [] for sid in series_ids}
        for r in rows:
            result.setdefault(r["series_id"], []).append(r["category_name"])
        return result


class CategoryRepo:
    """dim_course_category 分类维表仓储（task12 管理端复用）。"""

    async def list_all(self) -> list[dict]:
        """全量分类树（yn=1）。"""
        return await fetch_all(
            "SELECT id, parent_id, category_code, category_name, category_level, sort_no "
            "FROM dim_course_category WHERE yn = 1 "
            "ORDER BY category_level, sort_no, id"
        )
