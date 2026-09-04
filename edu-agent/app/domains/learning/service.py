# -*- coding: utf-8 -*-
"""study/learning 域（task21）service：访问鉴权 + 学习大纲 + 课次完成 + 课次详情。

access_scope 鉴权矩阵（GWT①）：
- enrolled_only：需该用户 student_cohort_rel.active（否则 403 40330「需报名」）
- internal_only：仅管理端（本域 C 端登录用户一律不可见）
- public/trial：无需报名可访问
- 未报名用户（非公共/试听全封闭）→ 403
"""
from __future__ import annotations

import logging

from app.common.exceptions import AppException
from app.database import transaction
from app.domains.learning.repository import StudyRepo, StudyWriteRepo
from app.domains.learning.schemas import (
    StudyAccessResult, StudyAssetItem, StudyModuleOutlineItem, StudyOutline,
    StudySessionDetail, StudySessionOutlineItem, StudyVideoInfo, SessionCompleteResult,
)

logger = logging.getLogger(__name__)

_repo = StudyRepo()
_write = StudyWriteRepo()

# 无需报名的访问域
_OPEN_SCOPES = {"public", "trial"}


def _accessible_scopes_for(user_id: int, enrolled: bool) -> list[str]:
    """该用户可访问的 access_scope（enrolled_only 需已报名）。"""
    scopes = ["public", "trial"]
    if enrolled:
        scopes.append("enrolled_only")
    return scopes


# ═══════════════════════════════════════════════════════
# 1. 访问鉴权（GWT①）
# ═══════════════════════════════════════════════════════
async def get_study_access(user_id: int, series_id: int) -> StudyAccessResult:
    series = await _repo.get_series(series_id)
    if series is None:
        raise AppException("40400", "课程不存在")

    enrolled = await _repo.get_active_enrollment_for_series(user_id, series_id)
    if enrolled is not None:
        return StudyAccessResult(
            series_id=series_id, cohort_id=int(enrolled["cohort_id"]),
            accessible=True, reason=None,
        )

    # 未报名：仅当系列含 public/trial 资源才可访问（否则 403「需报名」）
    scopes = await _repo.get_series_video_scopes(series_id)
    if scopes & _OPEN_SCOPES:
        return StudyAccessResult(
            series_id=series_id, cohort_id=None, accessible=True,
            reason="当前可访问公开/试听内容（部分课次仅报名可见）",
        )
    return StudyAccessResult(
        series_id=series_id, cohort_id=None, accessible=False,
        reason="仅报名该班次的学员可访问本课次内容",
    )


# ═══════════════════════════════════════════════════════
# 2. 学习大纲（GWT② outline，含资源过滤 + 进度）
# ═══════════════════════════════════════════════════════
async def get_study_outline(user_id: int, series_id: int) -> StudyOutline:
    series = await _repo.get_series(series_id)
    if series is None:
        raise AppException("40400", "课程不存在")

    enrolled = await _repo.get_active_enrollment_for_series(user_id, series_id)
    vis_scopes = _accessible_scopes_for(user_id, enrolled is not None)

    modules, session_ids = await _repo.get_outline_sessions(series_id)
    videos = await _repo.get_session_videos(session_ids)
    watch = await _repo.get_watch_ratio(user_id, session_ids)
    hw_done = await _repo.get_homework_done(user_id, session_ids)

    mod_map: dict[int, list[dict]] = {}
    for m in modules:
        mod_map.setdefault(int(m["module_id"]), []).append(m)

    total = 0
    completed = 0
    ratio_sum = 0.0
    out_modules: list[StudyModuleOutlineItem] = []
    for mod_id in sorted(mod_map):
        sess_rows = mod_map[mod_id]
        mod_sessions: list[StudySessionOutlineItem] = []
        for s in sorted(sess_rows, key=lambda x: int(x["session_no"])):
            sid = int(s["session_id"])
            v = videos.get(sid)
            # 未报名：折叠 enrolled_only/internal_only 视频课次（避免元数据越权可见）
            if v and v["access_scope"] not in vis_scopes and v["access_scope"] in ("enrolled_only", "internal_only"):
                continue
            total += 1
            # 资源过滤：仅可见 scope 的视频参与大纲（url 仅 completed）
            url = None
            if v and v["access_scope"] in vis_scopes:
                url = v["file_url"] if v["transcode_status"] == "completed" else None
            ratio = watch.get(sid, 0.0)
            hw = sid in hw_done
            sess_item = StudySessionOutlineItem(
                session_id=sid, session_title=s["session_title"],
                session_no=int(s["session_no"]),
                duration_minutes=int(v["duration_seconds"] // 60) if v else 0,
                video_url=url, watch_ratio=round(ratio * 100, 1),
                homework_done=hw,
                transcode_status=(v["transcode_status"] if v else None),
            )
            mod_sessions.append(sess_item)
            ratio_sum += ratio
            if ratio >= 0.8 and hw:
                completed += 1
        mod_ratio = (sum(x.watch_ratio for x in mod_sessions) / len(mod_sessions)) / 100 if mod_sessions else 0.0
        out_modules.append(StudyModuleOutlineItem(
            module_id=mod_id, module_title=sess_rows[0]["module_name"],
            module_no=int(sess_rows[0]["module_no"]),
            overall_ratio=round(mod_ratio * 100, 1), sessions=mod_sessions,
        ))

    overall = (ratio_sum / total) if total else 0.0
    return StudyOutline(
        series_id=series_id, series_title=series["series_name"],
        overall_ratio=round(overall * 100, 1), total_sessions=total,
        completed_sessions=completed, modules=out_modules,
    )


# ═══════════════════════════════════════════════════════
# 3. 课次完成态
# ═══════════════════════════════════════════════════════
async def complete_session(user_id: int, session_id: int) -> SessionCompleteResult:
    sess = await _repo.get_session(session_id)
    if sess is None:
        raise AppException("40440", "课次不存在")
    # 访问守卫：enrolled_only 课次需已报名（GWT① 鉴权矩阵）
    series_id = int(sess["series_id"])
    v = await _repo.get_session_video(session_id)
    if v and v["access_scope"] in ("enrolled_only", "internal_only"):
        enrolled = await _repo.get_active_enrollment_for_series(user_id, series_id)
        if enrolled is None:
            raise AppException("40330", "该课次为报名专属内容，需先报名本班次", http_status=403)
    async with transaction() as (conn, cur):
        affected = await _write.mark_session_completed(cur=cur, user_id=user_id, session_id=session_id)
    # 未产生播放会话 → 仍返回 completed=False（未真正看）
    return SessionCompleteResult(session_id=session_id, completed=affected > 0)


# ═══════════════════════════════════════════════════════
# 4. 课次详情（GWT③ session_asset 过滤 + GWT④ transcode）
# ═══════════════════════════════════════════════════════
async def get_session_detail(user_id: int, session_id: int) -> StudySessionDetail:
    sess = await _repo.get_session(session_id)
    if sess is None:
        raise AppException("40440", "课次不存在")
    series_id = int(sess["series_id"])
    enrolled = await _repo.get_active_enrollment_for_series(user_id, series_id)
    vis_scopes = _accessible_scopes_for(user_id, enrolled is not None)

    assets = await _repo.get_session_assets(session_id, vis_scopes)
    asset_items = [StudyAssetItem(
        asset_id=int(r["asset_id"]), asset_code=r["asset_code"], asset_name=r["asset_name"],
        material_category=r["material_category"], access_scope=r["access_scope"],
        file_url=r["file_url"], file_size=r["file_size"],
    ) for r in assets]

    video_item = None
    v = await _repo.get_session_video(session_id)
    if v:
        # GWT① 鉴权：未报名用户访问 enrolled_only/internal_only 视频 → 403「需报名」
        if v["access_scope"] not in vis_scopes and v["access_scope"] in ("enrolled_only", "internal_only"):
            raise AppException(
                "40330", "该课次为报名专属内容，需先报名本班次才能观看",
                http_status=403,
            )
        chapters = await _repo.get_video_chapters(int(v["video_id"]))
        video_item = StudyVideoInfo(
            video_id=int(v["video_id"]), video_code=v["video_code"], video_title=v["video_title"],
            duration_seconds=int(v["duration_seconds"]), cover_url=v["cover_url"],
            transcode_status=v["transcode_status"], review_status=v["review_status"],
            video_url=(v["file_url"] if v["transcode_status"] == "completed" else None),
            chapters=chapters,
        )

    return StudySessionDetail(
        session_id=session_id, session_no=int(sess["session_no"]),
        session_title=sess["session_title"], teaching_status=sess["teaching_status"],
        teaching_date=sess.get("teaching_date"),
        module_id=int(sess["module_id"]) if sess.get("module_id") else None,
        module_name=sess.get("module_name"),
        series_id=series_id, assets=asset_items, video=video_item,
    )