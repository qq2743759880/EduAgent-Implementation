# -*- coding: utf-8 -*-
"""P4 思维导图 router。"""
from __future__ import annotations

from app.auth.dependencies import CurrentUser, get_current_user
from fastapi import APIRouter, Depends, Query

from app.mindmap import builder
from app.mindmap.schemas import MindMap

router = APIRouter()


@router.get("/course/{series_id}", response_model=MindMap, summary="课程系列思维导图（按 series.id 出图）")
async def mindmap_course(
    series_id: int,
) -> MindMap:
    return await builder.build_from_neo4j(series_id=series_id)


@router.get("/subject/{subject_code}", response_model=MindMap, summary="学科全量思维导图（english/programming/math）")
async def mindmap_subject(
    subject_code: str,
) -> MindMap:
    return await builder.build_from_neo4j(subject_code=subject_code)


@router.get("/me/{series_id}", response_model=MindMap, summary="「我的」学习图谱：在 /course/{series_id} 基础上叠加个人掌握度颜色")
async def mindmap_mine(
    series_id: int,
    current_user: CurrentUser = Depends(get_current_user),
) -> MindMap:
    return await builder.build_from_user_progress(current_user.user_id, series_id=series_id)


@router.get("/prerequisite", response_model=MindMap, summary="某知识点的先修链 forward（全链）/backward（仅前置）")
async def mindmap_prerequisite_tree(
    kp_code: str | None = Query(default=None, max_length=64, description="知识点 KP code，空=挑库中第一个 KP 作为起点示例"),
    direction: str = Query(default="forward", pattern=r"^(forward|backward)$", description="forward=完整先修→后续；backward=仅所需前置"),
) -> MindMap:
    return await builder.build_prerequisite_tree(kp_code=kp_code, direction=direction)
