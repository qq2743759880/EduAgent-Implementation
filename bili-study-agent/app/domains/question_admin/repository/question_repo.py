"""question 管理端仓储（task13）。

表结构（edu.sql 权威）：
  - question：id, bank_id, question_code, question_type_id, stem, options_json,
               answer_text, analysis_text, yn, created_at, updated_at
  - UNIQUE (bank_id, question_code)
  - options_json / analysis_text 为 JSON / TEXT 列，asyncmy 返回 str 需解析。
"""
from __future__ import annotations

import json
from typing import Optional

from app.database import execute_write, fetch_all, fetch_one


class QuestionAdminRepo:
    """题目主表仓储。"""

    @staticmethod
    def _parse_json(raw) -> list | dict | None:
        if raw is None or raw == "":
            return None
        if isinstance(raw, (list, dict)):
            return raw
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    async def get_by_id(self, question_id: int) -> Optional[dict]:
        return await fetch_one(
            "SELECT * FROM `question` WHERE id = %s",
            (question_id,),
        )

    async def get_by_code(self, bank_id: int, question_code: str) -> Optional[dict]:
        """按 bank_id + question_code 查（唯一约束校验）。"""
        return await fetch_one(
            "SELECT * FROM `question` WHERE bank_id = %s AND question_code = %s",
            (bank_id, question_code),
        )

    async def list_by_bank(
        self,
        bank_id: int,
        *,
        question_type_id: Optional[int] = None,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """按题库查题目列表（分页，LIKE 检索 stem + analysis_text，标签逻辑删除后替代方案）。"""
        where: list[str] = ["bank_id = %s", "yn = 1"]
        args: list = [bank_id]

        if question_type_id is not None:
            where.append("question_type_id = %s")
            args.append(question_type_id)
        if keyword:
            where.append("(stem LIKE %s OR analysis_text LIKE %s)")
            like = f"%{keyword}%"
            args.extend([like, like])

        where_sql = " AND ".join(where)
        offset = (page - 1) * page_size

        cnt_row = await fetch_one(
            f"SELECT COUNT(*) AS cnt FROM `question` WHERE {where_sql}",
            tuple(args),
        )
        total = int(cnt_row["cnt"]) if cnt_row else 0

        rows = await fetch_all(
            f"SELECT * FROM `question` WHERE {where_sql} ORDER BY id DESC LIMIT %s OFFSET %s",
            tuple(args + [page_size, offset]),
        )
        return rows, total

    async def insert(self, data: dict) -> int:
        return await execute_write(
            "INSERT INTO `question` (bank_id, question_code, question_type_id, stem, "
            "options_json, answer_text, analysis_text, yn, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, 1, NOW(), NOW())",
            (
                data["bank_id"], data["question_code"], data["question_type_id"],
                data["stem"],
                json.dumps(data.get("options_json"), ensure_ascii=False) if data.get("options_json") else None,
                data["answer_text"],
                data.get("analysis_text"),
            ),
        )

    async def update(self, question_id: int, data: dict) -> int:
        set_clauses = []
        args = []
        for key, val in data.items():
            if key == "options_json" and val is not None:
                val = json.dumps(val, ensure_ascii=False)
            set_clauses.append(f"`{key}` = %s")
            args.append(val)
        if not set_clauses:
            return 0
        set_clauses.append("updated_at = NOW()")
        args.append(question_id)
        return await execute_write(
            f"UPDATE `question` SET {', '.join(set_clauses)} WHERE id = %s",
            tuple(args),
        )

    async def soft_delete(self, question_id: int) -> int:
        return await execute_write(
            "UPDATE `question` SET yn = 0, updated_at = NOW() WHERE id = %s",
            (question_id,),
        )

    async def count_active_by_bank(self, bank_id: int) -> int:
        """F-8：题库内有效题目数（yn=1），删库前置保护用。"""
        row = await fetch_one(
            "SELECT COUNT(*) AS cnt FROM `question` WHERE bank_id = %s AND yn = 1",
            (bank_id,),
        )
        return int(row["cnt"]) if row else 0

    async def soft_delete_all_by_bank(self, bank_id: int) -> int:
        """F-8：force 删库时级联软删库内全部有效题目（yn=0，可恢复，不物理删）。"""
        return await execute_write(
            "UPDATE `question` SET yn = 0, updated_at = NOW() "
            "WHERE bank_id = %s AND yn = 1",
            (bank_id,),
        )