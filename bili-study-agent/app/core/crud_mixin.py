"""
Repository 层基类（Phase 重构：task09 core/ 框架层）

面试考点：
- 为什么需要 Repository 层？分离数据访问与业务逻辑，SQL 归口管理
- 软删约定：yn=1 过滤（所有查询默认带），DELETE 改为 UPDATE yn=0
- keyset 分页：替代 OFFSET 深度分页（大表 OFFSET 10000 性能差）

用法：
  class SeriesRepo(CrudMixin):
      table = "series"
      pk = "id"

  repo = SeriesRepo()
  rows = await repo.list_all(page=1, page_size=20)
  row = await repo.get_by_id(1)
"""
from __future__ import annotations

from typing import Any

from app.database import execute_write, fetch_all, fetch_one


class CrudMixin:
    """Repository 层基类。

    子类只需定义：
    - table: str = "表名"
    - pk: str = "主键列名"（默认 "id"）
    - soft_delete: bool = True（是否软删）
    """

    table: str = ""
    pk: str = "id"
    soft_delete: bool = True

    # ── 查询 ──

    async def get_by_id(self, pk_value: Any) -> dict | None:
        """按主键查询单行。"""
        where = f"{self.pk} = %s"
        if self.soft_delete:
            where += " AND yn = 1"
        return await fetch_one(f"SELECT * FROM {self.table} WHERE {where} LIMIT 1", (pk_value,))

    async def list_all(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        order_by: str = "",
        where_clause: str = "",
        where_args: tuple = (),
    ) -> tuple[list[dict], int]:
        """
        分页列表。

        Returns:
            (rows, total_count)
        """
        # 软删过滤
        conditions = ["yn = 1"] if self.soft_delete else []
        if where_clause:
            conditions.append(where_clause)

        where_sql = " AND ".join(conditions) if conditions else "1=1"
        order = order_by or f"{self.pk} DESC"
        offset = (page - 1) * page_size

        total_row = await fetch_one(
            f"SELECT COUNT(*) AS c FROM {self.table} WHERE {where_sql}",
            where_args,
        )
        total = int(total_row["c"]) if total_row else 0

        rows = await fetch_all(
            f"SELECT * FROM {self.table} WHERE {where_sql} ORDER BY {order} LIMIT %s OFFSET %s",
            (*where_args, page_size, offset),
        )
        return rows, total

    async def list_by_keyset(
        self,
        *,
        last_id: int = 0,
        page_size: int = 20,
        order_by: str = "",
        where_clause: str = "",
        where_args: tuple = (),
    ) -> list[dict]:
        """
        keyset 分页（替代 OFFSET，适合大表）。

        原理：WHERE id < last_id ORDER BY id DESC LIMIT n
        """
        conditions = ["yn = 1"] if self.soft_delete else []
        if last_id > 0:
            conditions.append(f"{self.pk} < %s")
            where_args = (*where_args, last_id)
        if where_clause:
            conditions.append(where_clause)

        where_sql = " AND ".join(conditions)
        order = order_by or f"{self.pk} DESC"

        return await fetch_all(
            f"SELECT * FROM {self.table} WHERE {where_sql} ORDER BY {order} LIMIT %s",
            (*where_args, page_size),
        )

    # ── 写操作 ──

    async def insert(self, data: dict[str, Any]) -> int:
        """插入单行，返回 lastrowid。"""
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        sql = f"INSERT INTO {self.table} ({columns}) VALUES ({placeholders})"
        return int(await execute_write(sql, tuple(data.values())))

    async def update(self, pk_value: Any, data: dict[str, Any]) -> int:
        """更新单行（按主键）。返回受影响行数。"""
        sets = ", ".join(f"{k} = %s" for k in data)
        sql = f"UPDATE {self.table} SET {sets} WHERE {self.pk} = %s"
        if self.soft_delete:
            sql += " AND yn = 1"
        return int(await execute_write(sql, (*data.values(), pk_value)))

    async def delete(self, pk_value: Any) -> int:
        """删除（软删 yn=0 或物理删除）。返回受影响行数。"""
        if self.soft_delete:
            return int(await execute_write(
                f"UPDATE {self.table} SET yn = 0 WHERE {self.pk} = %s AND yn = 1",
                (pk_value,),
            ))
        return int(await execute_write(
            f"DELETE FROM {self.table} WHERE {self.pk} = %s",
            (pk_value,),
        ))