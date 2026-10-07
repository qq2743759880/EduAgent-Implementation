"""Deterministic, evidence-backed Mastery V0 calculation.

This module is deliberately a pure projection: callers load authoritative
MySQL domain evidence and pass the rows here. Analytics/event-stream copies
must not be used as the only source of mastery truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal


MasteryStatus = Literal["UNASSESSED", "LEARNING", "NEEDS_REVIEW", "STABLE"]

_OBJECTIVE_TYPES = {"homework_objective", "exam_objective"}
_ACTIVITY_TYPES = {"lesson_complete", "video_complete"}


def _normalize_correct(value: object) -> bool | None:
    """Accept MySQL TINYINT 0/1 and bool; reject ambiguous string values."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None


@dataclass(frozen=True)
class MasteryEvidence:
    evidence_id: str
    attempt_id: str
    knowledge_code: str
    occurred_at: datetime
    evidence_type: str
    correct: bool | None = None
    question_id: str | int | None = None
    is_new_question: bool | None = None
    independent: bool | None = None
    hint_used: bool | None = None


@dataclass(frozen=True)
class MasteryState:
    knowledge_code: str
    status: MasteryStatus
    confidence: float
    weighted_accuracy: float | None
    scored_evidence_count: int
    unique_question_count: int
    evidence_ids: tuple[str, ...]
    reason: tuple[str, ...]
    next_review_at: datetime | None


def _evidence_weight(row: MasteryEvidence) -> float | None:
    """Return the V0 score weight, or None for evidence outside scoring."""
    if row.evidence_type in _ACTIVITY_TYPES:
        return None
    if _normalize_correct(row.correct) is None:
        return None
    if row.evidence_type in _OBJECTIVE_TYPES:
        return 1.0
    if row.evidence_type != "quiz_answer":
        return None
    if row.is_new_question is False:
        return 0.6
    if row.is_new_question is not True:
        return None
    if row.hint_used is True:
        return 0.6
    if row.hint_used is False and row.independent is True:
        return 1.0
    # The PRD only assigns full weight to a proven independent attempt.
    # Unknown independence/hint state is not silently promoted to full weight.
    return None


def _same_timezone(left: datetime, right: datetime) -> bool:
    return (left.tzinfo is None) == (right.tzinfo is None)


def calculate_mastery(
    knowledge_code: str,
    evidence: Iterable[MasteryEvidence],
    *,
    now: datetime,
) -> MasteryState:
    """Calculate one KP state from at most 8 unique attempts in the last 30d.

    Naive datetimes are accepted only when `now` and all evidence timestamps
    are also naive; timezone conversion belongs at the MySQL adapter boundary.
    Duplicate attempts are ignored once, using the earliest stable row as the
    canonical projection. Conflicting duplicate payloads should be rejected by
    the database uniqueness/payload-hash gate before reaching this function.
    """
    if not knowledge_code:
        raise ValueError("knowledge_code is required")

    cutoff_30d = now - timedelta(days=30)
    cutoff_14d = now - timedelta(days=14)
    candidates: list[MasteryEvidence] = []
    for row in evidence:
        if row.knowledge_code != knowledge_code:
            continue
        if not _same_timezone(now, row.occurred_at):
            raise ValueError("now and evidence timestamps must use the same timezone awareness")
        if cutoff_30d <= row.occurred_at <= now:
            candidates.append(row)

    candidates.sort(key=lambda item: (item.occurred_at, item.evidence_id, item.attempt_id))
    seen_attempts: set[str] = set()
    scored: list[tuple[MasteryEvidence, float]] = []
    for row in candidates:
        if not row.attempt_id or row.attempt_id in seen_attempts:
            continue
        seen_attempts.add(row.attempt_id)
        weight = _evidence_weight(row)
        if weight is not None:
            scored.append((row, weight))

    # Activities do not consume the scored-evidence window.
    scored = scored[-8:]
    if not scored:
        return MasteryState(
            knowledge_code=knowledge_code,
            status="UNASSESSED",
            confidence=0.0,
            weighted_accuracy=None,
            scored_evidence_count=0,
            unique_question_count=0,
            evidence_ids=(),
            reason=("no_scored_evidence_in_last_30_days",),
            next_review_at=None,
        )

    weight_sum = sum(weight for _, weight in scored)
    weighted_accuracy = sum(
        weight * int(_normalize_correct(row.correct) is True) for row, weight in scored
    ) / weight_sum
    confidence = min(1.0, weight_sum / 3.0)
    latest_row = scored[-1][0]
    last_two = [row for row, _ in scored[-2:]]
    unique_questions = {str(row.question_id) for row, _ in scored if row.question_id is not None}
    new_question_correct_14d = any(
        row.is_new_question is True
        and _normalize_correct(row.correct) is True
        and row.occurred_at >= cutoff_14d
        for row, _ in scored
    )

    latest_correct = _normalize_correct(latest_row.correct)
    if latest_correct is False or (len(scored) >= 2 and weighted_accuracy < 0.60):
        status: MasteryStatus = "NEEDS_REVIEW"
        reasons = [
            "latest_scored_evidence_incorrect"
            if latest_correct is False
            else "weighted_accuracy_below_0.60_with_at_least_two_evidence"
        ]
    elif (
        len(unique_questions) >= 3
        and weighted_accuracy >= 0.80
        and len(last_two) == 2
        and all(_normalize_correct(row.correct) is True for row in last_two)
        and new_question_correct_14d
    ):
        status = "STABLE"
        reasons = ["three_unique_questions_weighted_accuracy_at_least_0.80_last_two_correct"]
        if new_question_correct_14d:
            reasons.append("new_question_correct_within_14_days")
    else:
        status = "LEARNING"
        reasons = ["evidence_does_not_yet_meet_stable_or_needs_review_threshold"]

    if latest_correct is False:
        next_review_at = latest_row.occurred_at + timedelta(hours=6)
    elif status == "STABLE":
        next_review_at = latest_row.occurred_at + timedelta(days=7)
    else:
        # Includes NEEDS_REVIEW reached by the low-accuracy rule without a
        # latest incorrect attempt; V0 defines +6h for a recent wrong answer.
        next_review_at = latest_row.occurred_at + timedelta(days=3)

    return MasteryState(
        knowledge_code=knowledge_code,
        status=status,
        confidence=confidence,
        weighted_accuracy=weighted_accuracy,
        scored_evidence_count=len(scored),
        unique_question_count=len(unique_questions),
        evidence_ids=tuple(row.evidence_id for row, _ in scored),
        reason=tuple(reasons),
        next_review_at=next_review_at,
    )


def utc_now() -> datetime:
    """Convenience for adapters; the calculator itself accepts an explicit clock."""
    return datetime.now(timezone.utc)
