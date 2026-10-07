"""MySQL adapter that projects quiz truth into persisted Mastery V0 state."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.domains.learning.mastery import MasteryEvidence, MasteryState, calculate_mastery


def _decode_kps(value: Any) -> list[str]:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    if not isinstance(value, list):
        return []
    return [str(code) for code in value if isinstance(code, str) and code.strip()]


async def recompute_quiz_mastery_in_transaction(
    cur: Any,
    user_id: int,
    course_id: int,
    *,
    now: datetime | None = None,
) -> dict[str, MasteryState]:
    """Recompute all touched KPs from MySQL quiz rows inside the caller's tx.

    The caller must have inserted the current answer using this same cursor. The
    versioned KP snapshot stored with each answer is the attribution authority;
    Mongo/event-stream data and the current editable question mapping are not.
    """
    if not user_id or not course_id:
        return {}

    await cur.execute("SELECT NOW() AS db_now")
    clock_row = await cur.fetchone()
    if now is None:
        now = clock_row[0]
    await cur.execute(
        "SELECT id, attempt_id, question_id, course_id, question_version, "
        "knowledge_codes_snapshot, is_correct, hint_used, redo_of_attempt_id, created_at "
        "FROM quiz_answer_session "
        "WHERE user_id=%s AND course_id=%s "
        "AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) "
        "ORDER BY created_at ASC, id ASC",
        (int(user_id), int(course_id)),
    )
    columns = [item[0] for item in cur.description]
    records = [dict(zip(columns, row)) for row in await cur.fetchall()]

    evidence_by_kp: dict[str, list[MasteryEvidence]] = {}
    seen_question_ids: set[str] = set()
    for row in records:
        question_id = row.get("question_id")
        version = row.get("question_version")
        if question_id is None:
            continue
        question_key = str(question_id)
        knowledge_codes = _decode_kps(row.get("knowledge_codes_snapshot"))
        if not knowledge_codes:
            continue

        attempt_id = str(row.get("attempt_id") or "")
        if not attempt_id:
            # Pre-migration/invalid evidence cannot be made idempotent in memory.
            continue
        was_seen = question_key in seen_question_ids
        seen_question_ids.add(question_key)
        redo_of = row.get("redo_of_attempt_id")
        is_new_question = not was_seen and not redo_of
        occurred_at = row.get("created_at")
        if not isinstance(occurred_at, datetime):
            continue
        for knowledge_code in knowledge_codes:
            evidence_by_kp.setdefault(knowledge_code, []).append(
                MasteryEvidence(
                    evidence_id=str(row["id"]),
                    attempt_id=attempt_id,
                    knowledge_code=knowledge_code,
                    occurred_at=occurred_at,
                    evidence_type="quiz_answer",
                    correct=row.get("is_correct"),
                    question_id=question_id,
                    is_new_question=is_new_question,
                    independent=not bool(row.get("hint_used")),
                    hint_used=bool(row.get("hint_used")),
                )
            )

    # MySQL DATETIME values are naive; use the DB's own clock so timezone
    # interpretation remains consistent with created_at and DATE_SUB(NOW()).
    states = {
        code: calculate_mastery(code, rows, now=now)
        for code, rows in evidence_by_kp.items()
    }
    for state in states.values():
        await cur.execute(
            "INSERT INTO user_kp_mastery "
            "(user_id, course_id, knowledge_code, status, confidence, weighted_accuracy, "
            "scored_evidence_count, unique_question_count, reason_json, evidence_ids_json, "
            "next_review_at, updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()) "
            "ON DUPLICATE KEY UPDATE status=VALUES(status), confidence=VALUES(confidence), "
            "weighted_accuracy=VALUES(weighted_accuracy), "
            "scored_evidence_count=VALUES(scored_evidence_count), "
            "unique_question_count=VALUES(unique_question_count), reason_json=VALUES(reason_json), "
            "evidence_ids_json=VALUES(evidence_ids_json), next_review_at=VALUES(next_review_at), "
            "updated_at=VALUES(updated_at)",
            (
                int(user_id),
                int(course_id),
                state.knowledge_code,
                state.status,
                state.confidence,
                state.weighted_accuracy,
                state.scored_evidence_count,
                state.unique_question_count,
                json.dumps(state.reason, ensure_ascii=False),
                json.dumps(state.evidence_ids, ensure_ascii=False),
                state.next_review_at.replace(tzinfo=None) if state.next_review_at else None,
            ),
        )
    return states
