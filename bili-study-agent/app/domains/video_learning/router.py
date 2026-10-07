"""Operator API: source input, durable status, preview, retry and reviewed release."""
from __future__ import annotations

import asyncio
import json
import re

from fastapi import APIRouter, Depends, Query

from app.auth import CurrentUser, get_current_user, require_role
from app.auth.schemas import UserRole
from app.common.exceptions import AppException
from app.core.resp import ok
from app.domains.video_learning import tasks
from app.domains.video_learning.artifacts import load_video_artifact
from app.domains.video_learning.task_worker import TASK_ROOT

router = APIRouter(prefix="/api/admin/video-knowledge", tags=["Video Knowledge production"],
                   dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.MANAGER]))])


@router.post('/videos/{video_id}/graph')
async def synchronize_graph(video_id:int):
    from .graph import project_ready_video,inspect_ready_video
    from app.config import settings
    from app.knowledge.routers.document_tools import _neo4j_browser_url
    receipt=await project_ready_video(video_id)
    return ok({'receipt':receipt,'graph':await inspect_ready_video(video_id),
        'neo4j_url':_neo4j_browser_url(),'jaeger_url':settings.JAEGER_UI_URL})


@router.post("/tasks", summary="从已有原视频或真实 Bilibili 分 P 创建课次视频知识任务")
async def create(payload: tasks.CreateVideoTask, me: CurrentUser = Depends(get_current_user)):
    from app.observability.tracing import span
    with span('video.submit',attributes={'session.id':payload.session_id}) as trace:
        context={'trace_id':trace.trace_id,'span_id':trace.span_id} if trace else None
        return ok(await tasks.create_task(payload, me.user_id,trace_context=context))


@router.get("/tasks", summary="查看视频知识生产队列")
async def listing(limit: int = Query(30, ge=1, le=100), session_id: int | None = Query(None, gt=0)):
    return ok({"items": await tasks.list_tasks(limit, session_id), "worker": await tasks.worker_status()})


@router.get("/tasks/{task_id}", summary="查看当前阶段、失败原因、重试或审核状态")
async def get(task_id: str):
    return ok({**tasks.task_dto(await tasks.get_task(task_id)), "worker": await tasks.worker_status()})


def _preview(task_id: str, data: dict) -> dict:
    # Never resolve an operator supplied path. Even corrupt DB pointers cannot
    # expose another file through this endpoint.
    if len(task_id) != 32 or any(char not in "0123456789abcdef" for char in task_id):
        raise AppException("40400", "视频知识任务不存在", http_status=404)
    generation = data.get("artifact_generation", "")
    if len(generation) != 64 or any(char not in "0123456789abcdef" for char in generation):
        raise AppException("40900", "待审核资料缺少完整标识", http_status=409)
    directory = data.get("artifact_directory", "compiled")
    revision = re.fullmatch(r"compiled-r([1-9][0-9]?)", directory) if isinstance(directory, str) else None
    if directory != "compiled" and not (revision and int(revision[1]) <= 20):
        raise AppException("40900", "待审核资料目录不合法", http_status=409)
    path = TASK_ROOT / task_id / directory / generation / "artifact.json"
    artifact = load_video_artifact(path)
    if artifact.artifact_sha256 != data["artifact_sha256"] or artifact.content_sha256 != generation:
        raise AppException("40900", "待审核资料校验失败，请检查该任务", http_status=409)
    return {"artifact_sha256": artifact.artifact_sha256, "generation": artifact.content_sha256,
            "review_revision": data.get("review_revision", 0),
            "source": artifact.source.model_dump(mode="json"),
            "transcript_origin": artifact.compiler.transcript_origin,
            "transcript": artifact.transcript.model_dump(mode="json"),
            "summary": artifact.summary.model_dump(mode="json"), "knowledge_note": artifact.knowledge_note,
            "chapters": [chapter.model_dump(mode="json") for chapter in artifact.chapters],
            "mindmap": artifact.mindmap.model_dump(mode="json"),
            "exercise_questions": (data.get("exercise_package") or {}).get("questions", [])}


@router.get("/tasks/{task_id}/preview", summary="审核课程笔记、章节、字幕和思维导图")
async def preview(task_id: str):
    row = await tasks.get_task(task_id)
    data = json.loads(row["data_json"])
    if not data.get("artifact_sha256"):
        raise AppException("40900", "学习资料尚未编译完成", http_status=409)
    return ok(await asyncio.to_thread(_preview, task_id, data))


@router.post("/tasks/{task_id}/retry", summary="复用已完成阶段并重试失败任务")
async def retry(task_id: str):
    return ok(await tasks.retry_task(task_id))


@router.post("/tasks/{task_id}/reject", summary="拒绝待审核资料，保留原视频并按反馈重新编译")
async def reject(task_id: str, payload: tasks.RejectVideoTask, me: CurrentUser = Depends(get_current_user)):
    return ok(await tasks.reject_task(task_id, me.user_id, payload.reason,
        expected_artifact_sha256=payload.artifact_sha256, expected_review_revision=payload.review_revision))


@router.post("/tasks/{task_id}/approve", summary="审核通过并发布，系统自动进入现有 EDU RAG")
async def approve(task_id: str, payload: tasks.ApproveVideoTask, me: CurrentUser = Depends(get_current_user)):
    row = await tasks.get_task(task_id)
    data = json.loads(row["data_json"])
    if row["status"] != "awaiting_review":
        raise AppException("40900", "仅待审核任务可以发布", http_status=409)
    revision = data.get("review_revision", 0)
    if payload.artifact_sha256 != data.get("artifact_sha256") or payload.review_revision != revision:
        raise AppException("40900", "待审核资料已更新，请重新预览当前版本", http_status=409)
    # Approval is bound to a valid immutable artifact before the durable queue
    # becomes eligible for publication.
    await asyncio.to_thread(_preview, task_id, data)
    return ok(await tasks.approve_task(task_id, me.user_id,
        expected_artifact_sha256=payload.artifact_sha256, expected_generation=data["artifact_generation"],
        expected_review_revision=payload.review_revision))
