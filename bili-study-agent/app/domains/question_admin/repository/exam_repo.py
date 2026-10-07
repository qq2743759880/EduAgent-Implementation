"""session_exam 管理端仓储（task13 组卷快照）。

表结构（edu.sql 权威）：
  - session_exam：id, session_id, exam_code, exam_name, total_score, pass_score,
                   publish_status(draft/published/closed), created_by, duration_minutes,
                   window_start_at, deadline_at, publish_at, created_at, updated_at
  - session_exam_question_rel：id, exam_id, question_id, sort_no, score, created_at, updated_at
  - UNIQUE (session_id, exam_code)
"""
from __future__ import annotations

from typing import Optional

from app.database import execute_write, fetch_all, fetch_one


class ExamAdminRepo:
    """考试表仓储。"""

    # ── session_exam ──

    async def get_by_id(self, exam_id: int) -> Optional[dict]:
        return await fetch_one(
            "SELECT * FROM session_exam WHERE id = %s",
            (exam_id,),
        )

    async def get_by_code(self, session_id: int, exam_code: str) -> Optional[dict]:
        return await fetch_one(
            "SELECT * FROM session_exam WHERE session_id = %s AND exam_code = %s",
            (session_id, exam_code),
        )

    async def list_by_session(self, session_id: int) -> list[dict]:
        return await fetch_all(
            "SELECT * FROM session_exam WHERE session_id = %s ORDER BY id DESC",
            (session_id,),
        )

    async def insert(self, data: dict) -> int:
        return await execute_write(
            "INSERT INTO session_exam (session_id, exam_code, exam_name, total_score, pass_score, "
            "publish_status, created_by, duration_minutes, window_start_at, deadline_at, "
            "publish_at, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())",
            (
                data["session_id"], data["exam_code"], data["exam_name"],
                data["total_score"], data["pass_score"],
                data.get("publish_status", "draft"),
                data["created_by"], data["duration_minutes"],
                data["window_start_at"], data["deadline_at"],
                data.get("publish_at"),
            ),
        )

    async def update(self, exam_id: int, data: dict) -> int:
        set_clauses = []
        args = []
        for key, val in data.items():
            set_clauses.append(f"`{key}` = %s")
            args.append(val)
        if not set_clauses:
            return 0
        set_clauses.append("updated_at = NOW()")
        args.append(exam_id)
        return await execute_write(
            f"UPDATE session_exam SET {', '.join(set_clauses)} WHERE id = %s",
            tuple(args),
        )

    # ── session_exam_question_rel（快照关系表）──

    async def list_questions(self, exam_id: int) -> list[dict]:
        return await fetch_all(
            "SELECT * FROM session_exam_question_rel WHERE exam_id = %s ORDER BY sort_no, id",
            (exam_id,),
        )

    async def delete_questions(self, exam_id: int) -> None:
        await execute_write(
            "DELETE FROM session_exam_question_rel WHERE exam_id = %s",
            (exam_id,),
        )

    async def insert_question(self, exam_id: int, question_id: int, sort_no: int, score: float) -> int:
        return await execute_write(
            "INSERT INTO session_exam_question_rel (exam_id, question_id, sort_no, score, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, NOW(), NOW())",
            (exam_id, question_id, sort_no, score),
        )