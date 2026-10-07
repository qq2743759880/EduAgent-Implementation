# -*- coding: utf-8 -*-
"""study/learning 域（task21 契约⑪ task21 段）路由。

端点（对齐前端 study.ts，供 /learning 播放页 / task48）：
- GET  /api/study/courses/{series_id}/access   访问鉴权（access_scope 矩阵，enrolled_only 需报名）
- GET  /api/study/courses/{series_id}/outline  学习大纲（模块/课次/进度 + 资源过滤）
- POST /api/study/sessions/{session_id}/complete 课次完成态
- GET  /api/study/sessions/{session_id}        课次详情（session_asset 过滤 + transcode）

响应壳沿用契约① ok()；失败 AppException → 全局 handler（403 用业务码 403xx）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependencies import CurrentUser, get_current_user
from app.core.resp import ok
from app.domains.learning import service as svc
from app.domains.learning.study_context import create_study_context
from app.domains.learning.schemas import (StudyContextCreateIn, StudyContextCreateOut,
    LearningLoopActivateIn, LearningLoopActivateOut)
from app.domains.learning import learning_loop
from app.domains.learning.pilot_material import get_pilot_lesson_material
from app.domains.video_learning.publication import get_video_knowledge
from uuid import UUID

router = APIRouter(prefix="/api/study", tags=["study · 学习"])  # noqa: F401


@router.get("/sessions/{session_id}/video-knowledge", summary="本课视频的章节、笔记、字幕与思维导图")
async def video_knowledge(session_id: int, user: CurrentUser = Depends(get_current_user)):
    return ok(data=await get_video_knowledge(session_id, user.user_id))


@router.post("/loops", summary="开始可复核的一门课学习轮次")
async def learning_loop_activate(
    body: LearningLoopActivateIn, user: CurrentUser = Depends(get_current_user),
):
    data = await learning_loop.activate(body.study_context_id, user.user_id)
    return ok(data=LearningLoopActivateOut(**data).model_dump(mode="json"))


@router.get("/loops/{loop_id}", summary="复核学习轮次与已提交的下一步行动")
async def learning_loop_receipt(loop_id: UUID, user: CurrentUser = Depends(get_current_user)):
    return ok(data=await learning_loop.receipt(loop_id, user.user_id))


@router.post("/contexts", summary="创建服务端校验的本课学习上下文")
async def study_context_create(
    body: StudyContextCreateIn,
    user: CurrentUser = Depends(get_current_user),
):
    data = await create_study_context(body.session_id, user.user_id)
    return ok(data=StudyContextCreateOut(**data).model_dump())


@router.get("/contexts/{context_id}", summary="当前答疑课程与正式资料状态")
async def study_context_view(context_id: str, user: CurrentUser = Depends(get_current_user)):
    from app.domains.learning.study_context import resolve_study_context
    from app.domains.video_learning.publication import get_video_publication
    context = await resolve_study_context(context_id, user.user_id)
    video = context.get("video") or {}
    publication = await get_video_publication(video["video_id"]) if video else None
    return ok(data={"series_name": context["series_name"], "session_title": context["session_title"],
                    "series_id": context["series_id"], "session_id": context["session_id"],
                    "video_title": video.get("title"), "knowledge_ready": publication is not None})


@router.get("/courses/{series_id}/access", summary="班次访问鉴权")
async def study_access(
    series_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.get_study_access(user.user_id, series_id)
    return ok(data=data.model_dump(mode="json"))


@router.get("/courses/{series_id}/outline", summary="学习大纲")
async def study_outline(
    series_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.get_study_outline(user.user_id, series_id)
    return ok(data=data.model_dump(mode="json"))


@router.post("/sessions/{session_id}/complete", summary="课次完成态")
async def session_complete(
    session_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.complete_session(user.user_id, session_id)
    return ok(data=data.model_dump(mode="json"))


@router.get("/sessions/{session_id}", summary="课次详情（资源过滤 + transcode）")
async def session_detail(
    session_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    data = await svc.get_session_detail(user.user_id, session_id)
    return ok(data=data.model_dump(mode="json"))


@router.get("/sessions/{session_id}/pilot-material", summary="隔离 Pilot 冻结课文")
async def pilot_lesson_material(
    session_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    return ok(data=await get_pilot_lesson_material(session_id, user.user_id))
