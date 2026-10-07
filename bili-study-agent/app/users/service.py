"""
用户画像 Service（两条：get_or_create_profile / update_profile 部分更新）。
- 水平越权保护：user_id 只从 CurrentUser 取，router 不允许传。
- UPDATE 只改非 None 字段；JSON 列序列化/反序列化 + level_assessments.assessed_at 空时自动填 NOW()。
"""
from __future__ import annotations

import json as _json
from datetime import datetime
from typing import Any

from app.auth.dependencies import CurrentUser
from app.common.exceptions import ValidationError
from app.database import fetch_one, transaction
from app.users.schemas import UserProfile, UserProfileUpdate, LevelAssessment


_COLUMNS = [
    "nickname", "avatar_url", "gender", "birthday", "grade_code", "school_name",
    "region_code", "weekly_available_hours", "study_style", "target_qualification",
    "learning_goals", "subject_preferences", "level_assessments", "interest_tags",
]


def _serialize_json(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (list, dict)):
        return _json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    return v


def _row_to_profile(row: dict) -> UserProfile:
    data = {}
    for col in _COLUMNS + ["created_at", "updated_at"]:
        if col not in row:
            continue
        v = row[col]
        if col in ("learning_goals", "subject_preferences", "level_assessments", "interest_tags"):
            if isinstance(v, (bytes, bytearray)):
                v = v.decode("utf-8")
            if isinstance(v, str):
                try:
                    v = _json.loads(v)
                except Exception:
                    v = []
            data[col] = v or []
        else:
            data[col] = v
    return UserProfile.model_validate(data)


def _patch_level_assessment_timestamps(items) -> list[dict] | None:
    if items is None:
        return None
    now = datetime.utcnow()
    out = []
    for it in items:
        d = it.model_dump() if hasattr(it, "model_dump") else dict(it)
        if d.get("assessed_at") is None:
            d["assessed_at"] = now
        if isinstance(d.get("assessed_at"), datetime):
            d["assessed_at"] = d["assessed_at"].isoformat(timespec="seconds")
        out.append(d)
    return out


async def get_or_create_profile(user: CurrentUser) -> UserProfile:
    row = await fetch_one(
        "SELECT * FROM user_profile WHERE user_id = %(user_id)s LIMIT 1",
        {"user_id": user.user_id},
    )
    if row:
        return _row_to_profile(row)

    async with transaction() as (conn, cur):
        await cur.execute(
            """
            INSERT IGNORE INTO user_profile
                (user_id, nickname, gender, weekly_available_hours, study_style,
                 learning_goals, subject_preferences, level_assessments, interest_tags)
            VALUES
                (%(user_id)s, %(nickname)s, 'secret', 5, 'mixed',
                 '[]', '[]', '[]', '[]')
            """,
            {
                "user_id": user.user_id,
                "nickname": user.nickname or f"用户{user.user_id}",
            },
        )
    row = await fetch_one(
        "SELECT * FROM user_profile WHERE user_id = %(user_id)s LIMIT 1",
        {"user_id": user.user_id},
    )
    if not row:
        raise ValidationError("用户画像初始化失败，请稍后重试")
    return _row_to_profile(row)


async def update_profile(user: CurrentUser, req: UserProfileUpdate) -> UserProfile:
    _ = await get_or_create_profile(user)

    changes = req.model_dump(exclude_none=True)
    if not changes:
        return await get_or_create_profile(user)

    if "level_assessments" in changes:
        changes["level_assessments"] = _patch_level_assessment_timestamps(
            [LevelAssessment.model_validate(x) for x in changes["level_assessments"]]
        )
    for col in ("learning_goals", "subject_preferences", "level_assessments", "interest_tags"):
        if col in changes:
            changes[col] = _serialize_json(changes[col])

    sets = ", ".join(f"{k} = %({k})s" for k in changes.keys())
    changes["user_id"] = user.user_id

    async with transaction() as (conn, cur):
        await cur.execute(f"UPDATE user_profile SET {sets} WHERE user_id = %(user_id)s LIMIT 1", changes)

    return await get_or_create_profile(user)
