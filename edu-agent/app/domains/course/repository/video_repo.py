"""
视频仓储（session_video + session_asset）。

关联链：series_cohort_session → session_asset(material_category='video')
       → session_video(asset_id)
每课次约 1 条视频（full 档 205776 课次 / 205776 视频）。
"""
from __future__ import annotations

from app.database import fetch_all


class VideoRepo:
    """session_video 表仓储（只读；写路径归 task12 分片上传/转码）。"""

    async def list_by_session_ids(self, session_ids: list[int]) -> dict[int, list[dict]]:
        """批量取课次→视频列表（含资产 file_url），避免 N+1。"""
        if not session_ids:
            return {}
        placeholders = ", ".join(["%s"] * len(session_ids))
        rows = await fetch_all(
            "SELECT v.id, v.asset_id, v.video_code, v.video_title, v.cover_url, "
            "       v.duration_seconds, v.resolution_label, v.bitrate_kbps, "
            "       v.transcode_status, v.review_status, a.file_url, a.session_id "
            "FROM session_asset a "
            "JOIN session_video v ON v.asset_id = a.id "
            f"WHERE a.session_id IN ({placeholders}) AND a.material_category = 'video' "
            "ORDER BY a.session_id, a.sort_no, v.id",
            tuple(session_ids),
        )
        result: dict[int, list[dict]] = {sid: [] for sid in session_ids}
        for r in rows:
            result.setdefault(r["session_id"], []).append(r)
        return result
