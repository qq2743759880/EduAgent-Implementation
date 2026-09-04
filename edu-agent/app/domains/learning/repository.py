# -*- coding: utf-8 -*-
"""study/learning 域 repository：课程结构 + 资源鉴权 + 播放/提交聚合。

列对照（edu.sql 权威核实）：
- session_asset：material_category(video/handout/exercise/reference/image)、access_scope(public/trial/enrolled_only/internal_only)
- session_video：asset_id、transcode_status(pending/in_progress/completed/failed)、review_status
- session_video_play：video_id、last_position_seconds、progress_percent、completed_flag、watched_seconds（play_session_no 唯一）
- session_homework_submission：session_id、submit_status
- 资源鉴权矩阵：enrolled_only 需 student_cohort_rel.active；internal_only 仅管理端
"""
from __future__ import annotations

from app.database import fetch_all, fetch_one


class StudyRepo:
    """只读查询。"""

    async def get_series(self, series_id: int) -> dict | None:
        return await fetch_one(
            "SELECT id, institution_id, series_name, delivery_mode, sale_status"
            " FROM series WHERE id=%s LIMIT 1", (series_id,))

    async def get_active_enrollment_for_series(self, user_id: int, series_id: int) -> dict | None:
        """该用户在指定系列下有 active 报名（含班次）。"""
        return await fetch_one(
            "SELECT scr.cohort_id, c.series_id FROM student_cohort_rel scr"
            " JOIN series_cohort c ON c.id = scr.cohort_id"
            " WHERE scr.user_id=%s AND c.series_id=%s AND scr.enroll_status='active' LIMIT 1",
            (int(user_id), series_id),
        )

    async def get_series_video_scopes(self, series_id: int) -> set[str]:
        """该系列所有视频资源的 access_scope 集合（鉴权矩阵用）。"""
        rows = await fetch_all(
            "SELECT DISTINCT sa.access_scope FROM session_asset sa"
            " JOIN series_cohort_session scs ON scs.id = sa.session_id"
            " JOIN series_cohort_course ccc ON ccc.id = scs.series_cohort_course_id"
            " JOIN series_cohort c ON c.id = ccc.cohort_id"
            " WHERE c.series_id=%s AND sa.material_category='video'",
            (series_id,),
        )
        return {r["access_scope"] for r in rows}

    async def get_outline_sessions(self, series_id: int) -> tuple[list[dict], list[int]]:
        """系列教学结构（系列→班次→模块→课次）。返回 (modules, session_ids)。"""
        modules = await fetch_all(
            "SELECT ccc.id AS module_id, ccc.module_name, ccc.stage_no AS module_no,"
            " ccc.cohort_id, c.series_id,"
            " scs.id AS session_id, scs.session_title, scs.session_no, scs.teaching_status"
            " FROM series_cohort c"
            " JOIN series_cohort_course ccc ON ccc.cohort_id = c.id"
            " JOIN series_cohort_session scs ON scs.series_cohort_course_id = ccc.id"
            " WHERE c.series_id=%s AND scs.teaching_status <> 'cancelled'"
            " ORDER BY ccc.stage_no, scs.session_no",
            (series_id,),
        )
        session_ids = sorted({int(r["session_id"]) for r in modules})
        return modules, session_ids

    async def get_session_videos(self, session_ids: list[int]) -> dict[int, dict]:
        """课次 → completed 视频（仅 completed 可播；url 用 asset.file_url，status 透出）。"""
        if not session_ids:
            return {}
        marks = ",".join(["%s"] * len(session_ids))
        rows = await fetch_all(
            "SELECT sa.session_id, sv.id AS video_id, sv.video_code, sv.video_title,"
            " sv.duration_seconds, sv.cover_url, sv.transcode_status, sv.review_status,"
            " sa.access_scope, sa.file_url"
            " FROM session_video sv JOIN session_asset sa ON sa.id = sv.asset_id"
            f" WHERE sa.session_id IN ({marks}) AND sa.material_category='video'",
            tuple(session_ids),
        )
        return {int(r["session_id"]): dict(r) for r in rows}

    async def get_watch_ratio(self, user_id: int, session_ids: list[int]) -> dict[int, float]:
        """课次 → 观看比例（session_video_play.last_position_seconds / video.duration_seconds）。"""
        if not session_ids:
            return {}
        marks = ",".join(["%s"] * len(session_ids))
        rows = await fetch_all(
            "SELECT sa.session_id,"
            " MAX(svp.last_position_seconds) AS maxpos, MAX(sv.duration_seconds) AS dur"
            " FROM session_video_play svp"
            " JOIN session_video sv ON sv.id = svp.video_id"
            " JOIN session_asset sa ON sa.id = sv.asset_id"
            f" WHERE svp.user_id=%s AND sa.session_id IN ({marks})"
            " GROUP BY sa.session_id",
            tuple([int(user_id)] + session_ids),
        )
        out: dict[int, float] = {}
        for r in rows:
            dur = int(r["dur"] or 0)
            out[int(r["session_id"])] = min(int(r["maxpos"] or 0) / dur, 1.0) if dur else 0.0
        return out

    async def get_homework_done(self, user_id: int, session_ids: list[int]) -> set[int]:
        if not session_ids:
            return set()
        marks = ",".join(["%s"] * len(session_ids))
        rows = await fetch_all(
            "SELECT DISTINCT session_id FROM session_homework_submission"
            f" WHERE user_id=%s AND session_id IN ({marks}) AND submit_status='submitted'",
            tuple([int(user_id)] + session_ids),
        )
        return {int(r["session_id"]) for r in rows}

    # ---------- 会话详情（GWT③/④） ----------
    async def get_session(self, session_id: int) -> dict | None:
        return await fetch_one(
            "SELECT scs.id AS session_id, scs.session_no, scs.session_title, scs.teaching_status,"
            " scs.teaching_date, ccc.id AS module_id, ccc.module_name, c.series_id"
            " FROM series_cohort_session scs"
            " JOIN series_cohort_course ccc ON ccc.id = scs.series_cohort_course_id"
            " JOIN series_cohort c ON c.id = ccc.cohort_id"
            " WHERE scs.id=%s LIMIT 1", (session_id,))

    async def get_session_assets(self, session_id: int, accessible_scopes: list[str]) -> list[dict]:
        marks = ",".join(["%s"] * len(accessible_scopes))
        return await fetch_all(
            f"SELECT id AS asset_id, asset_code, asset_name, material_category, access_scope,"
            f" file_url, file_size FROM session_asset"
            f" WHERE session_id=%s AND access_scope IN ({marks}) ORDER BY sort_no, id",
            tuple([session_id] + accessible_scopes),
        )

    async def get_session_video(self, session_id: int) -> dict | None:
        return await fetch_one(
            "SELECT sv.id AS video_id, sv.video_code, sv.video_title, sv.duration_seconds,"
            " sv.cover_url, sv.transcode_status, sv.review_status, sa.file_url, sa.access_scope"
            " FROM session_video sv JOIN session_asset sa ON sa.id = sv.asset_id"
            " WHERE sa.session_id=%s AND sa.material_category='video' LIMIT 1",
            (session_id,))

    async def get_video_chapters(self, video_id: int) -> list[dict]:
        return await fetch_all(
            "SELECT id, chapter_no, chapter_title, start_second, end_second"
            " FROM session_video_chapter WHERE video_id=%s ORDER BY chapter_no", (video_id,))


class StudyWriteRepo:
    """事务内写：课次完成态（completed_flag）。"""

    async def mark_session_completed(self, *, cur, user_id: int, session_id: int) -> int:
        """将该课次该生的视频播放会话置 completed_flag=1（若无播放会话则 0 行）。"""
        await cur.execute(
            "UPDATE session_video_play svp"
            " JOIN session_video sv ON sv.id = svp.video_id"
            " JOIN session_asset sa ON sa.id = sv.asset_id"
            " SET svp.completed_flag=1, svp.progress_percent=100, svp.updated_at=NOW()"
            " WHERE svp.user_id=%s AND sa.session_id=%s",
            (int(user_id), session_id),
        )
        return int(cur.rowcount) if cur.rowcount else 0