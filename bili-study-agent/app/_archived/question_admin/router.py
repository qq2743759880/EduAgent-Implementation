"""
P7 管理端控制台 - 题库管理 router。
全量 require_role([ADMIN])。
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.auth import CurrentUser, UserRole, require_role
from app.admin.question_admin import service
from app.admin.question_admin.schemas import (
    ExamPaper,
    ExamPaperAdminCreate,
    PaperComposeRequest,
    PaperComposeResult,
    QuestionAdminCreate,
    QuestionAdminUpdate,
    QuestionBankDetail,
    QuestionBankListResponse,
    QuestionBatchImportResponse,
    QuestionTag,
    QuestionTagCreate,
)
from app.common.exceptions import AppException as BizError

router = APIRouter(
    prefix="/api/admin/questions",
    tags=["admin-question"],
    dependencies=[Depends(require_role([UserRole.ADMIN]))],
)


# ============================================================
# 1. 标签
# ============================================================
@router.get("/tags", response_model=list[QuestionTag])
async def admin_list_tags(tag_type: Optional[str] = None, subject_code: Optional[str] = None):
    return await service.list_tags(tag_type, subject_code)


@router.post("/tags", response_model=dict)
async def admin_create_tag(payload: QuestionTagCreate):
    pk = await service.create_tag(payload)
    return {"id": pk, "tag_code": payload.tag_code}


@router.delete("/tags/{tag_id}", response_model=dict)
async def admin_delete_tag(tag_id: int):
    await service.delete_tag(tag_id)
    return {"deleted": True, "id": tag_id}


# ============================================================
# 2. 题目
# ============================================================
@router.get("", response_model=QuestionBankListResponse)
async def admin_list_questions(
    subject_code: Optional[str] = None,
    question_type: Optional[str] = None,
    difficulty_level: Optional[str] = None,
    keyword: Optional[str] = None,
    tag_id: Optional[int] = None,
    yn: Optional[int] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return await service.list_questions(
        subject_code=subject_code,
        question_type=question_type,
        difficulty_level=difficulty_level,
        keyword=keyword,
        tag_id=tag_id,
        page=page,
        page_size=page_size,
        yn=yn,
    )


@router.get("/{question_id}", response_model=QuestionBankDetail)
async def admin_get_question(question_id: int):
    return await service.get_question(question_id)


@router.post("", response_model=dict)
async def admin_create_question(
    payload: QuestionAdminCreate,
    user: CurrentUser = Depends(require_role([UserRole.ADMIN])),
):
    pk = await service.create_question(payload, created_by=user.user_id)
    return {"id": pk, "question_code": payload.question_code}


@router.patch("/{question_id}", response_model=dict)
async def admin_update_question(
    question_id: int,
    payload: QuestionAdminUpdate,
    user: CurrentUser = Depends(require_role([UserRole.ADMIN])),
):
    await service.update_question(question_id, payload, updated_by=user.user_id)
    return {"updated": True, "id": question_id}


@router.delete("/{question_id}", response_model=dict)
async def admin_delete_question(question_id: int):
    await service.delete_question(question_id)
    return {"deleted": True, "id": question_id}


# ============================================================
# 3. 批量导入
# ============================================================
# 上限常量：条数 ≤500、原始 body ≤2MB（对抗问题 #7：无上限时超大 payload 直通 200）
BATCH_IMPORT_MAX_ITEMS = 500
BATCH_IMPORT_MAX_BYTES = 2 * 1024 * 1024


@router.post("/batch-import", response_model=QuestionBatchImportResponse)
async def admin_batch_import_questions(
    request: Request,
    user: CurrentUser = Depends(require_role([UserRole.ADMIN])),
):
    raw = await request.body()
    if len(raw) > BATCH_IMPORT_MAX_BYTES:
        raise BizError(40001, f"批量导入数据过大：请求体 {len(raw)} 字节，上限 {BATCH_IMPORT_MAX_BYTES} 字节（2MB）")
    try:
        items = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise BizError(40001, "批量导入数据必须是合法 JSON 数组")
    if not isinstance(items, list):
        raise BizError(40001, "批量导入数据必须是数组")
    if len(items) > BATCH_IMPORT_MAX_ITEMS:
        raise BizError(40001, f"批量导入条数超出上限：{len(items)} 条，单次最多 {BATCH_IMPORT_MAX_ITEMS} 条")
    return await service.batch_import_questions(items, operator_id=user.user_id)


# ============================================================
# 4. 试卷
# ============================================================
@router.get("/papers", response_model=list[ExamPaper])
async def admin_list_papers(subject_code: Optional[str] = None, yn: int = Query(default=1, ge=0, le=1)):
    return await service.list_exam_papers(subject_code, yn)


@router.post("/papers", response_model=ExamPaper)
async def admin_create_paper(
    payload: ExamPaperAdminCreate,
    user: CurrentUser = Depends(require_role([UserRole.ADMIN])),
):
    return await service.create_exam_paper(payload, created_by=user.user_id)


@router.delete("/papers/{paper_id}", response_model=dict)
async def admin_delete_paper(paper_id: int):
    await service.delete_exam_paper(paper_id)
    return {"deleted": True, "id": paper_id}


# ============================================================
# 5. 组卷
# ============================================================
@router.post("/papers/compose", response_model=PaperComposeResult)
async def admin_compose_paper(
    req: PaperComposeRequest,
    user: CurrentUser = Depends(require_role([UserRole.ADMIN])),
):
    return await service.compose_paper(req, operator_id=user.user_id)
