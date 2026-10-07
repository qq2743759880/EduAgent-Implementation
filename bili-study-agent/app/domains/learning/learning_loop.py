"""Pilot learning loops backed by MySQL, with authorization at creation and read."""
from __future__ import annotations

import uuid

from app.common.exceptions import AppException
from app.database import fetch_one, transaction
from app.domains.learning.study_context import resolve_study_context


async def activate(study_context_id: str, user_id: int) -> dict:
    context = await resolve_study_context(study_context_id, user_id)
    loop_id = str(uuid.uuid4())
    async with transaction() as (_conn, cur):
        await cur.execute(
            "INSERT INTO learning_loop (id,user_id,course_id,session_id,status,activated_at,updated_at) "
            "VALUES (%s,%s,%s,%s,'ACTIVE',NOW(6),NOW(6))",
            (loop_id, int(user_id), int(context["module_id"]), int(context["session_id"])),
        )
    return {"learning_loop_id": loop_id, "course_id": int(context["module_id"]),
            "session_id": int(context["session_id"]), "status": "ACTIVE"}


async def receipt(loop_id: uuid.UUID, user_id: int) -> dict:
    loop = await fetch_one(
        "SELECT id,course_id,session_id,status,activated_at FROM learning_loop "
        "WHERE id=%s AND user_id=%s", (str(loop_id), int(user_id)),
    )
    if not loop:
        raise AppException("40440", "学习轮次不存在或无权访问", http_status=404)
    # The read is a receipt of committed domain facts, not a computed success flag.
    row = await fetch_one(
        "SELECT a.id AS action_id,a.kind,a.status AS action_status,a.due_at,a.executed_at,"
        "q.id AS evidence_id,q.attempt_id,q.is_correct,q.course_id "
        "FROM learning_next_action a JOIN quiz_answer_session q "
        "ON q.id=a.quiz_answer_session_id AND q.user_id=a.user_id "
        "AND q.learning_loop_id COLLATE utf8mb4_unicode_ci="
        "a.learning_loop_id COLLATE utf8mb4_unicode_ci "
        "WHERE a.learning_loop_id=%s AND a.user_id=%s ORDER BY a.id DESC LIMIT 1",
        (str(loop_id), int(user_id)),
    )
    activity = ({"type": "QUIZ_SUBMIT", "domain_table": "quiz_answer_session",
                 "domain_id": int(row["evidence_id"])} if row else None)
    evidence = ({"type": "QUIZ_SCORE", "domain_table": "quiz_answer_session",
                 "domain_id": int(row["evidence_id"]), "attempt_id": row["attempt_id"],
                 "is_correct": bool(row["is_correct"])} if row else None)
    return {"learning_loop_id": str(loop["id"]), "course_id": int(loop["course_id"]),
            "session_id": int(loop["session_id"]), "status": loop["status"],
            "activated_at": loop["activated_at"], "activity": activity,
            "evidence": evidence, "action": row}
