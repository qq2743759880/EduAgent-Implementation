"""dim_question_type 维表仓储（task13）。

表结构（edu.sql 权威）：
  - dim_question_type：id, type_code, type_name, objective_flag, auto_marking_flag, sort_no, yn
"""
from __future__ import annotations

from typing import Optional

from app.database import fetch_all, fetch_one


class DimQuestionTypeRepo:
    """题型维表仓储（只读）。"""

    async def get_by_id(self, type_id: int) -> Optional[dict]:
        return await fetch_one(
            "SELECT * FROM dim_question_type WHERE id = %s AND yn = 1",
            (type_id,),
        )

    async def get_by_code(self, type_code: str) -> Optional[dict]:
        return await fetch_one(
            "SELECT * FROM dim_question_type WHERE type_code = %s AND yn = 1",
            (type_code,),
        )

    async def list_all(self) -> list[dict]:
        return await fetch_all(
            "SELECT * FROM dim_question_type WHERE yn = 1 ORDER BY sort_no, id",
        )