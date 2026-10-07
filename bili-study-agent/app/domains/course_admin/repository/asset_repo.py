"""Asset（课次资源 = session_asset）管理端仓储（task12-fix）。

表 `session_asset` 按 edu.sql 权威结构：**无 yn 列**（列：id, session_id,
asset_code, asset_name, file_type, material_category, sort_no, access_scope,
file_url, file_size, uploader_user_id, created_at, updated_at）。无状态字段
→ 删除用**物理 DELETE**。
material_category: video/handout/exercise/reference/image
access_scope: public/trial/enrolled_only/internal_only
"""
from __future__ import annotations
from typing import Optional

from app.database import fetch_all, fetch_one, execute_write


class AssetAdminRepo:
    """session_asset 管理端仓储。"""

    async def get_by_id(self, asset_id: int) -> Optional[dict]:
        return await fetch_one(
            "SELECT * FROM session_asset WHERE id = %s",
            (asset_id,),
        )

    async def list_by_session(self, session_id: int) -> list[dict]:
        """课次下资源列表（无 yn 过滤——该表无软删列）。"""
        return await fetch_all(
            "SELECT * FROM session_asset WHERE session_id = %s ORDER BY sort_no, id",
            (session_id,),
        )

    async def insert(self, data: dict) -> int:
        return await execute_write(
            "INSERT INTO session_asset (session_id, asset_code, asset_name, file_type, "
            "material_category, sort_no, access_scope, file_url, file_size, "
            "uploader_user_id, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())",
            (
                data["session_id"], data["asset_code"], data["asset_name"],
                data["file_type"], data["material_category"], data.get("sort_no", 0),
                data.get("access_scope", "enrolled_only"), data["file_url"],
                data.get("file_size"), data["uploader_user_id"],
            ),
        )

    async def update(self, asset_id: int, data: dict) -> int:
        set_clauses = []
        args = []
        for key, val in data.items():
            set_clauses.append(f"{key} = %s")
            args.append(val)
        if not set_clauses:
            return 0
        set_clauses.append("updated_at = NOW()")
        args.append(asset_id)
        return await execute_write(
            f"UPDATE session_asset SET {', '.join(set_clauses)} WHERE id = %s",
            tuple(args),
        )

    async def hard_delete(self, asset_id: int) -> int:
        """物理删除（表无软删列；先删子表 session_video 引用）。"""
        await execute_write(
            "DELETE FROM session_video WHERE asset_id = %s",
            (asset_id,),
        )
        return await execute_write(
            "DELETE FROM session_asset WHERE id = %s",
            (asset_id,),
        )