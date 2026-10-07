"""question_bank 管理端仓储（task13）。

表结构（edu.sql 权威）：
  - question_bank：id, institution_id, category_id, bank_code, bank_name, yn, created_at, updated_at
  - UNIQUE (institution_id, bank_code)
  - yn 列可用作软删（与 course 系不同，该表有 yn）。
"""
from __future__ import annotations

from typing import Optional

from app.database import execute_write, fetch_all, fetch_one


class BankAdminRepo:
    """题库主表仓储。"""

    async def get_by_id(self, bank_id: int) -> Optional[dict]:
        return await fetch_one(
            "SELECT * FROM question_bank WHERE id = %s",
            (bank_id,),
        )

    async def get_by_code(self, institution_id: int, bank_code: str) -> Optional[dict]:
        """按 institution_id + bank_code 查（唯一约束校验）。"""
        return await fetch_one(
            "SELECT * FROM question_bank WHERE institution_id = %s AND bank_code = %s",
            (institution_id, bank_code),
        )

    async def list_banks(
        self,
        *,
        institution_id: Optional[int] = None,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """管理端题库列表（分页）。"""
        where: list[str] = ["yn = 1"]
        args: list = []

        if institution_id is not None:
            where.append("institution_id = %s")
            args.append(institution_id)
        if keyword:
            where.append("(bank_name LIKE %s OR bank_code LIKE %s)")
            like = f"%{keyword}%"
            args.extend([like, like])

        where_sql = " AND ".join(where)
        offset = (page - 1) * page_size

        cnt_row = await fetch_one(
            f"SELECT COUNT(*) AS cnt FROM question_bank WHERE {where_sql}",
            tuple(args),
        )
        total = int(cnt_row["cnt"]) if cnt_row else 0

        rows = await fetch_all(
            f"SELECT * FROM question_bank WHERE {where_sql} ORDER BY id DESC LIMIT %s OFFSET %s",
            tuple(args + [page_size, offset]),
        )
        return rows, total

    async def insert(self, data: dict) -> int:
        return await execute_write(
            "INSERT INTO question_bank (institution_id, category_id, bank_code, bank_name, "
            "yn, created_at, updated_at) VALUES (%s, %s, %s, %s, 1, NOW(), NOW())",
            (data["institution_id"], data["category_id"], data["bank_code"], data["bank_name"]),
        )

    async def update(self, bank_id: int, data: dict) -> int:
        set_clauses = []
        args = []
        for key, val in data.items():
            set_clauses.append(f"`{key}` = %s")
            args.append(val)
        if not set_clauses:
            return 0
        set_clauses.append("updated_at = NOW()")
        args.append(bank_id)
        return await execute_write(
            f"UPDATE question_bank SET {', '.join(set_clauses)} WHERE id = %s",
            tuple(args),
        )

    async def soft_delete(self, bank_id: int) -> int:
        return await execute_write(
            "UPDATE question_bank SET yn = 0, updated_at = NOW() WHERE id = %s",
            (bank_id,),
        )