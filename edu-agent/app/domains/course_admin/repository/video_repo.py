"""Video + Chapter（session_video + session_video_chapter）管理端仓储（task12-fix）。

表 `session_video`、`session_video_chapter` 按 edu.sql 权威结构：**无 yn 列**。
transcode_status 状态机：pending → in_progress → completed | failed。
review_status 状态机：pending → approved | rejected。
"""
from __future__ import annotations
from typing import Optional

from app.database import fetch_all, fetch_one, execute_write


class VideoAdminRepo:
    """session_video 管理端仓储。"""

    async def get_by_id(self, video_id: int) -> Optional[dict]:
        return await fetch_one(
            "SELECT * FROM session_video WHERE id = %s",
            (video_id,),
        )

    async def list_by_asset(self, asset_id: int) -> list[dict]:
        """资产下视频列表（无 yn 过滤——该表无软删列）。"""
        return await fetch_all(
            "SELECT * FROM session_video WHERE asset_id = %s ORDER BY id",
            (asset_id,),
        )

    async def insert(self, data: dict) -> int:
        return await execute_write(
            "INSERT INTO session_video (asset_id, video_code, video_title, cover_url, "
            "duration_seconds, resolution_label, bitrate_kbps, transcode_status, review_status, "
            "created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())",
            (
                data["asset_id"], data["video_code"], data["video_title"],
                data.get("cover_url"), data["duration_seconds"],
                data.get("resolution_label"), data["bitrate_kbps"],
                data.get("transcode_status", "pending"),
                data.get("review_status", "pending"),
            ),
        )

    async def update(self, video_id: int, data: dict) -> int:
        set_clauses = []
        args = []
        for key, val in data.items():
            set_clauses.append(f"{key} = %s")
            args.append(val)
        if not set_clauses:
            return 0
        set_clauses.append("updated_at = NOW()")
        args.append(video_id)
        return await execute_write(
            f"UPDATE session_video SET {', '.join(set_clauses)} WHERE id = %s",
            tuple(args),
        )

    async def hard_delete(self, video_id: int) -> int:
        """物理删除（表无软删列；先删子表 session_video_chapter 引用）。"""
        await execute_write(
            "DELETE FROM session_video_chapter WHERE video_id = %s",
            (video_id,),
        )
        return await execute_write(
            "DELETE FROM session_video WHERE id = %s",
            (video_id,),
        )

    async def get_transcode_status(self, video_id: int) -> Optional[dict]:
        return await fetch_one(
            "SELECT id, transcode_status, review_status, updated_at FROM session_video WHERE id = %s",
            (video_id,),
        )


class ChapterAdminRepo:
    """session_video_chapter 管理端仓储。"""

    async def list_by_video(self, video_id: int) -> list[dict]:
        """视频下章节列表（无 yn 过滤——该表无软删列）。"""
        return await fetch_all(
            "SELECT * FROM session_video_chapter WHERE video_id = %s ORDER BY chapter_no, id",
            (video_id,),
        )

    async def get_by_chapter_no(self, video_id: int, chapter_no: int) -> Optional[dict]:
        return await fetch_one(
            "SELECT * FROM session_video_chapter WHERE video_id = %s AND chapter_no = %s LIMIT 1",
            (video_id, chapter_no),
        )

    async def insert(self, data: dict) -> int:
        return await execute_write(
            "INSERT INTO session_video_chapter (video_id, chapter_no, chapter_title, "
            "start_second, end_second, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, NOW(), NOW())",
            (
                data["video_id"], data["chapter_no"], data["chapter_title"],
                data["start_second"], data["end_second"],
            ),
        )

    async def update(self, chapter_id: int, data: dict) -> int:
        set_clauses = []
        args = []
        for key, val in data.items():
            set_clauses.append(f"{key} = %s")
            args.append(val)
        if not set_clauses:
            return 0
        set_clauses.append("updated_at = NOW()")
        args.append(chapter_id)
        return await execute_write(
            f"UPDATE session_video_chapter SET {', '.join(set_clauses)} WHERE id = %s",
            tuple(args),
        )

    async def hard_delete(self, chapter_id: int) -> int:
        """物理删除（表无软删列）。"""
        return await execute_write(
            "DELETE FROM session_video_chapter WHERE id = %s",
            (chapter_id,),
        )