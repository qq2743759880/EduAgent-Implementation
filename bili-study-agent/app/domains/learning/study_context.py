"""Ephemeral, server-issued StudyContext IDs with request-time authorization checks.

The ID is a random locator in Redis, never an authorization capability. Every resolve
re-reads the current course/session/enrollment/source scope from MySQL and fails closed.
"""
from __future__ import annotations

import json
import secrets
from typing import Any

from app.common.exceptions import AppException
from app.database import fetch_all, fetch_one, get_redis
from app.domains.learning.playable_video import PLAYABLE_VIDEO_ORDER, PLAYABLE_VIDEO_PREDICATE

_PREFIX = "study_context:v1:"
_OWNER_INDEX_PREFIX = "study_context:owner:"
_TTL_SECONDS = 4 * 60 * 60

# Video-derived KP names are metadata, but must follow the same READY authority.
# Ordinary course KPs retain their existing compatibility path.
VIDEO_KP_READY = (
    "AND (COALESCE(JSON_UNQUOTE(JSON_EXTRACT(kp.properties_json,'$.source')),'')<>'video_generated' "
    "OR EXISTS (SELECT 1 FROM video_learning_publication vp WHERE vp.video_id=%s "
    "AND vp.video_id=CAST(JSON_UNQUOTE(JSON_EXTRACT(kp.properties_json,'$.video_id')) AS UNSIGNED) "
    "AND vp.artifact_id=JSON_UNQUOTE(JSON_EXTRACT(kp.properties_json,'$.generation')) "
    "AND vp.artifact_sha256=JSON_UNQUOTE(JSON_EXTRACT(kp.properties_json,'$.artifact_sha256')) "
    "AND vp.rag_status='ready' AND NOT EXISTS (SELECT 1 FROM video_learning_publication newer "
    "WHERE newer.video_id=vp.video_id AND newer.rag_status='ready' AND newer.id>vp.id))) "
)


async def _load_authorized_context(session_id: int, user_id: int) -> dict[str, Any]:
    row = await fetch_one(
        "SELECT scs.id AS session_id, scs.session_title, scs.teaching_status, "
        "ccc.id AS module_id, ccc.module_code, ccc.module_name, c.id AS cohort_id, "
        "s.id AS series_id, s.series_code, s.series_name "
        "FROM series_cohort_session scs "
        "JOIN series_cohort_course ccc ON ccc.id=scs.series_cohort_course_id "
        "JOIN series_cohort c ON c.id=ccc.cohort_id "
        "JOIN series s ON s.id=c.series_id "
        "WHERE scs.id=%s AND scs.teaching_status<>'cancelled' LIMIT 1",
        (int(session_id),),
    )
    if not row:
        raise AppException("40440", "学习课次不存在")

    enrollment = await fetch_one(
        "SELECT id FROM student_cohort_rel WHERE user_id=%s AND cohort_id=%s "
        "AND enroll_status='active' LIMIT 1",
        (int(user_id), int(row["cohort_id"])),
    )
    if not enrollment:
        raise AppException("40330", "需要报名该课程后才能使用本课 Agent", http_status=403)

    assets = await fetch_all(
        "SELECT id AS asset_id, asset_name, material_category, access_scope "
        "FROM session_asset WHERE session_id=%s ORDER BY sort_no, id",
        (int(session_id),),
    )
    # StudyContext is course-scoped; internal-only material never enters the student prompt.
    allowed = [a for a in assets if a.get("access_scope") in {"public", "trial", "enrolled_only"}]
    video = await fetch_one(
        "SELECT sv.id AS video_id, sv.video_title, sv.transcode_status, sa.access_scope "
        "FROM session_video sv JOIN session_asset sa ON sa.id=sv.asset_id "
        "WHERE sa.session_id=%s AND sa.material_category='video' "
        f"AND {PLAYABLE_VIDEO_PREDICATE} ORDER BY {PLAYABLE_VIDEO_ORDER} LIMIT 1",
        (int(session_id),),
    )
    if video and video.get("access_scope") not in {"public", "trial", "enrolled_only"}:
        video = None

    # Pull only KP nodes explicitly attached to the course module, never infer them from titles.
    kp_rows = await fetch_all(
        "SELECT DISTINCT kp.code AS knowledge_code,kp.name AS knowledge_name "
        "FROM graph_node module JOIN graph_node kp ON (kp.parent_id=module.id OR EXISTS ("
        "SELECT 1 FROM graph_edge ge WHERE ge.from_node_id=module.id AND ge.to_node_id=kp.id "
        "AND ge.rel_type='CONTAINS' AND ge.yn=1)) "
        "WHERE module.label='CourseModule' AND module.code=%s AND kp.label='KnowledgePoint' "
        "AND module.yn=1 AND kp.yn=1 " + VIDEO_KP_READY + "ORDER BY kp.code LIMIT 40",
        (str(row.get("module_code") or ""), int(video['video_id']) if video else 0),
    )
    knowledge_codes = [str(k["knowledge_code"]) for k in kp_rows if k.get("knowledge_code")]
    wrong_rows = []
    if knowledge_codes:
        marks = ",".join(["%s"] * len(knowledge_codes))
        wrong_rows = await fetch_all(
            "SELECT wb.question_id,q.stem,wb.wrong_count,wb.updated_at "
            "FROM quiz_wrong_book wb JOIN `question` q ON q.id=wb.question_id "
            "JOIN quiz_question_publication qp ON qp.question_id=q.id "
            "JOIN quiz_question_kp qkp ON qkp.question_id=q.id "
            f"WHERE wb.user_id=%s AND wb.status='ACTIVE' AND qp.course_id=%s AND qkp.knowledge_code IN ({marks}) "
            "GROUP BY wb.question_id,q.stem,wb.wrong_count,wb.updated_at "
            "ORDER BY wb.updated_at DESC LIMIT 5",
            tuple([int(user_id), int(row["module_id"])] + knowledge_codes),
        )
    goal = await fetch_one(
        "SELECT g.goal_code,g.goal_name FROM student_profile sp "
        "JOIN dim_learning_goal g ON g.id=sp.learning_goal_id "
        "WHERE sp.user_id=%s AND sp.yn=1 AND g.yn=1 LIMIT 1",
        (int(user_id),),
    )

    return {
        "user_id": int(user_id),
        "session_id": int(row["session_id"]),
        "cohort_id": int(row["cohort_id"]),
        "series_id": int(row["series_id"]),
        "series_code": str(row.get("series_code") or ""),
        "series_name": str(row.get("series_name") or ""),
        "module_id": int(row["module_id"]),
        "module_name": str(row.get("module_name") or ""),
        "session_title": str(row.get("session_title") or ""),
        "assets": [
            {"asset_id": int(a["asset_id"]), "name": str(a.get("asset_name") or ""),
             "category": str(a.get("material_category") or ""), "scope": str(a.get("access_scope") or "")}
            for a in allowed
        ],
        "video": ({"video_id": int(video["video_id"]), "title": str(video.get("video_title") or ""),
                   "transcode_status": str(video.get("transcode_status") or "")}
                  if video else None),
        "knowledge_points": [
            {"knowledge_code": str(k["knowledge_code"]), "name": str(k.get("knowledge_name") or "")}
            for k in kp_rows
        ],
        "recent_wrong_questions": [
            {"question_id": int(q["question_id"]), "stem": str(q.get("stem") or "")[:240],
             "wrong_count": int(q.get("wrong_count") or 0)}
            for q in wrong_rows
        ],
        "current_goal": ({"code": str(goal["goal_code"]), "name": str(goal["goal_name"])} if goal else None),
    }


async def create_study_context(session_id: int, user_id: int) -> dict[str, Any]:
    context = await _load_authorized_context(session_id, user_id)
    context_id = "sc_" + secrets.token_urlsafe(24)
    try:
        # Store the locator and its per-user reverse index atomically. Privacy
        # deletion can then enumerate this user's IDs without scanning all
        # random context keys or trusting a client-supplied locator.
        async with get_redis().pipeline(transaction=True) as pipe:
            pipe.set(_PREFIX + context_id,
                     json.dumps(context, ensure_ascii=False, separators=(",", ":")),
                     ex=_TTL_SECONDS)
            pipe.sadd(_OWNER_INDEX_PREFIX + str(int(user_id)), context_id)
            pipe.expire(_OWNER_INDEX_PREFIX + str(int(user_id)), _TTL_SECONDS)
            await pipe.execute()
    except Exception as exc:
        raise AppException("50300", "学习上下文服务暂不可用，请稍后重试", http_status=503) from exc
    return {"study_context_id": context_id, "expires_in_seconds": _TTL_SECONDS}


async def resolve_study_context(context_id: str, user_id: int) -> dict[str, Any]:
    if not context_id or len(context_id) > 96 or not context_id.startswith("sc_"):
        raise AppException("40440", "学习上下文无效或已过期")
    try:
        raw = await get_redis().get(_PREFIX + context_id)
    except Exception as exc:
        raise AppException("50300", "学习上下文服务暂不可用，请稍后重试", http_status=503) from exc
    if not raw:
        raise AppException("40440", "学习上下文无效或已过期")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        stored = json.loads(raw)
        session_id = int(stored["session_id"])
        owner_id = int(stored["user_id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise AppException("40440", "学习上下文无效或已过期") from exc
    if owner_id != int(user_id):
        raise AppException("40330", "无权使用该学习上下文", http_status=403)
    current = await _load_authorized_context(session_id, user_id)
    # Return freshly read data, not stale Redis course/source data.
    return current
