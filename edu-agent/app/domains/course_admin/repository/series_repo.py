"""Series（课程系列）管理端仓储（task12）。

表 `series`（无 yn 列，可见性由 sale_status 状态机控制：draft/on_sale/off_sale）。
软删语义：DELETE → sale_status='off_sale'（用户端不再可见）。
"""
from __future__ import annotations

from typing import Optional

from app.database import fetch_all, fetch_one, execute_write


_SORT_MAP = {
    "default": "id DESC",
    "newest": "created_at DESC, id DESC",
    "name_asc": "series_name ASC, id DESC",
    "name_desc": "series_name DESC, id DESC",
}


class SeriesAdminRepo:
    """series 表管理端仓储。"""

    async def get_by_id(self, series_id: int) -> Optional[dict]:
        """按 ID 查系列（不限制 sale_status，管理端可见全部状态）。"""
        return await fetch_one(
            "SELECT * FROM series WHERE id = %s",
            (series_id,),
        )

    async def get_by_code(self, institution_id: int, series_code: str) -> Optional[dict]:
        """按 institution_id + series_code 查系列（唯一约束校验）。"""
        return await fetch_one(
            "SELECT * FROM series WHERE institution_id = %s AND series_code = %s",
            (institution_id, series_code),
        )

    async def list_series(
        self,
        *,
        keyword: Optional[str] = None,
        institution_id: Optional[int] = None,
        delivery_mode: Optional[str] = None,
        sale_status: Optional[str] = None,
        include_deleted: bool = False,
        sort: str = "default",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """管理端系列列表。

        - 默认（include_deleted=False）排除已下架（软删）系列（sale_status='off_sale'）；
          series 表无 yn 列，下架由 sale_status 状态机表达。
        - include_deleted=True 时不过滤 off_sale，用于回收站视图。
        - 显式传入 sale_status 时以显式值为准（覆盖默认排除逻辑）。
        """
        where: list[str] = []
        args: list = []

        if keyword:
            where.append("(series_name LIKE %s OR description LIKE %s OR series_code LIKE %s)")
            args.extend([f"%{keyword}%"] * 3)
        if institution_id is not None:
            where.append("institution_id = %s")
            args.append(institution_id)
        if delivery_mode is not None:
            where.append("delivery_mode = %s")
            args.append(delivery_mode)
        if sale_status is not None:
            where.append("sale_status = %s")
            args.append(sale_status)
        elif not include_deleted:
            # 默认列表过滤掉已下架（软删）系列
            where.append("sale_status != 'off_sale'")

        where_sql = " AND ".join(where) if where else "1=1"
        order_by = _SORT_MAP.get(sort, _SORT_MAP["default"])
        offset = (page - 1) * page_size

        cnt_row = await fetch_one(
            f"SELECT COUNT(*) AS cnt FROM series WHERE {where_sql}",
            tuple(args),
        )
        total = int(cnt_row["cnt"]) if cnt_row else 0

        rows = await fetch_all(
            f"SELECT * FROM series WHERE {where_sql} ORDER BY {order_by} LIMIT %s OFFSET %s",
            tuple(args + [page_size, offset]),
        )
        return rows, total

    async def insert(self, data: dict) -> int:
        """创建系列，返回自增 ID。"""
        return await execute_write(
            "INSERT INTO series (institution_id, delivery_mode, series_code, series_name, "
            "description, cover_url, target_learner_identity_codes, target_learning_goal_codes, "
            "target_grade_codes, sale_status, created_by, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())",
            (
                data["institution_id"], data["delivery_mode"], data["series_code"],
                data["series_name"], data.get("description"), data.get("cover_url"),
                data.get("target_learner_identity_codes"), data.get("target_learning_goal_codes"),
                data.get("target_grade_codes"), data.get("sale_status", "draft"),
                data["created_by"],
            ),
        )

    async def update(self, series_id: int, data: dict) -> int:
        """更新系列字段。"""
        set_clauses = []
        args = []
        for key, val in data.items():
            set_clauses.append(f"{key} = %s")
            args.append(val)
        if not set_clauses:
            return 0
        set_clauses.append("updated_at = NOW()")
        args.append(series_id)
        return await execute_write(
            f"UPDATE series SET {', '.join(set_clauses)} WHERE id = %s",
            tuple(args),
        )

    async def off_sale(self, series_id: int) -> int:
        """软删系列：sale_status = 'off_sale'。"""
        return await execute_write(
            "UPDATE series SET sale_status = 'off_sale', updated_at = NOW() WHERE id = %s",
            (series_id,),
        )

    async def count_references(self, series_id: int) -> dict:
        """外键引用计数：全部班次行（含软删 yn=0，FK 仍绑定）+ 经班次的订单明细。

        用于 hard delete 前置校验——任一 > 0 即禁止真删：
        series_cohort 即使 yn=0 仍持有指向 series 的外键，物理删除 series 会触发
        外键冲突，故与活动班次同等对待，绝不静默放行。
        """
        cohorts_row = await fetch_one(
            "SELECT COUNT(*) AS cnt FROM series_cohort WHERE series_id = %s",
            (series_id,),
        )
        orders_row = await fetch_one(
            "SELECT COUNT(*) AS cnt FROM order_item oi "
            "JOIN series_cohort sc ON oi.cohort_id = sc.id "
            "WHERE sc.series_id = %s",
            (series_id,),
        )
        cohorts = int(cohorts_row["cnt"]) if cohorts_row else 0
        orders = int(orders_row["cnt"]) if orders_row else 0
        return {"cohorts": cohorts, "orders": orders, "total": cohorts + orders}

    async def physical_delete(self, series_id: int) -> int:
        """物理真删系列（仅 ADMIN 且 count_references 为零时调用）。"""
        return await execute_write(
            "DELETE FROM series WHERE id = %s",
            (series_id,),
        )