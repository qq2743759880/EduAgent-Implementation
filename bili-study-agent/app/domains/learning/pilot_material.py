"""Read the frozen, owner-approved text lesson for the isolated one-course Pilot."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.common.exceptions import AppException
from app.config import settings
from app.database import fetch_one


_PACK_ROOT = Path(__file__).resolve().parents[3] / "content_packs" / "one-course-pilot"
_MANIFEST = _PACK_ROOT / "manifest.json"


async def get_pilot_lesson_material(session_id: int, user_id: int) -> dict:
    """The session ID is a locator, never authority to read a pack file."""
    try:
        manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise AppException("50340", "本课文字材料暂不可用", http_status=503) from None
    if (
        manifest.get("status") != "PILOT_FROZEN"
        or settings.MYSQL_DATABASE != manifest.get("publication", {}).get("target_schema")
    ):
        raise AppException("40440", "本课文字材料未发布")

    binding = next(
        (item for item in manifest.get("module_bindings", []) if item.get("session_id") == session_id),
        None,
    )
    if binding is None:
        raise AppException("40440", "本课文字材料不存在")

    # Exact cohort enrollment and module/session match; no file path comes from the client.
    access = await fetch_one(
        "SELECT scs.session_title, ccc.id AS module_id, c.id AS cohort_id, c.series_id "
        "FROM series_cohort_session scs "
        "JOIN series_cohort_course ccc ON ccc.id=scs.series_cohort_course_id "
        "JOIN series_cohort c ON c.id=ccc.cohort_id "
        "JOIN student_cohort_rel scr ON scr.cohort_id=c.id AND scr.user_id=%s "
        "AND scr.enroll_status='active' "
        "WHERE scs.id=%s AND scs.teaching_status<>'cancelled' LIMIT 1",
        (int(user_id), int(session_id)),
    )
    if access is None:
        raise AppException("40330", "需要报名本班次后才能阅读课文", http_status=403)
    if (
        int(access["module_id"]) != binding.get("course_id")
        or int(access["series_id"]) != manifest.get("series_id")
        or int(access["cohort_id"]) != manifest.get("cohort_id")
    ):
        raise AppException("40440", "本课文字材料未发布")

    material_path = binding.get("material")
    material = next(
        (item for item in manifest.get("materials", []) if item.get("path") == material_path),
        None,
    )
    if not material or not isinstance(material_path, str):
        raise AppException("50340", "本课文字材料暂不可用", http_status=503)
    resolved = (_PACK_ROOT / material_path).resolve()
    if not resolved.is_relative_to(_PACK_ROOT.resolve()) or not resolved.is_file():
        raise AppException("50340", "本课文字材料暂不可用", http_status=503)
    try:
        raw = resolved.read_bytes()
    except OSError:
        raise AppException("50340", "本课文字材料暂不可用", http_status=503) from None
    digest = hashlib.sha256(raw).hexdigest()
    if digest != material.get("hash"):
        raise AppException("50340", "本课文字材料校验失败", http_status=503)

    # The frozen source starts with editorial DRAFT front matter from before Owner
    # approval. Present the lesson body as-is and keep provenance in the response.
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise AppException("50340", "本课文字材料格式不可用", http_status=503) from None
    first_section = text.find("## 学习目标")
    if first_section < 0:
        raise AppException("50340", "本课文字材料格式不可用", http_status=503)
    return {
        "session_id": session_id,
        "title": str(access["session_title"]),
        "text": text[first_section:].strip(),
        "sha256": digest,
        "pack_version": manifest["pack_version"],
        "source": "Owner-approved original Pilot course material",
    }
