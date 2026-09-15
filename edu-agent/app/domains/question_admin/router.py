"""
管理端题库域路由（task13 契约冻结④）。

前缀：/api/admin/questions
依赖：require_role([ADMIN, MANAGER])
标签逻辑删除（不再维护 tag 表）→ stem/analysis_text LIKE 检索替代。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Query

from app.auth import CurrentUser, get_current_user, require_role
from app.auth.schemas import UserRole
from app.common.exceptions import PermissionDeniedError
from app.core.resp import ok
from app.domains.question_admin import service as svc
from app.domains.question_admin.schemas import (
    BankCreateAdmin,
    BankListDataAdmin,
    BankResponseAdmin,
    BankUpdateAdmin,
    BatchImportExecuteResponse,
    BatchImportPreviewResponse,
    ExamCreateAdmin,
    ExamListDataAdmin,
    ExamPublishRequest,
    ExamPublishResponse,
    ExamResponseAdmin,
    ExamUpdateAdmin,
    QuestionAdminCreate,
    QuestionAdminUpdate,
    QuestionListDataAdmin,
    QuestionResponseAdmin,
    QuestionTypeListResponse,
    QuestionTypeResponse,
)

router = APIRouter(
    prefix="/api/admin/questions",
    tags=["question_admin · 管理端题库（task13）"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.MANAGER]))],
)


# ═══════════════════════════════════════════
# 题型维表（只读）
# ═══════════════════════════════════════════

@router.get("/types", summary="题型维表列表（只读）")
async def list_question_types():
    items = await svc.list_question_types()
    return ok(data={"items": [i.model_dump(mode="json") for i in items], "total": len(items)})


# ═══════════════════════════════════════════
# 题库（question_bank）CRUD
# ═══════════════════════════════════════════

@router.get("/banks", summary="题库列表（分页 + 关键词检索）")
async def list_banks(
    institution_id: Optional[int] = Query(None, description="机构ID"),
    keyword: Optional[str] = Query(None, max_length=128, description="关键词（检索bank_name/bank_code）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    result = await svc.list_banks(
        institution_id=institution_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return ok(data=result.model_dump(mode="json"))


@router.get("/banks/{bank_id}", summary="题库详情")
async def get_bank(bank_id: int):
    result = await svc.get_bank(bank_id)
    return ok(data=result.model_dump(mode="json"))


@router.post("/banks", summary="创建题库", status_code=201)
async def create_bank(payload: BankCreateAdmin):
    result = await svc.create_bank(payload)
    return ok(data=result.model_dump(mode="json"))


@router.patch("/banks/{bank_id}", summary="更新题库")
async def update_bank(bank_id: int, payload: BankUpdateAdmin):
    result = await svc.update_bank(bank_id, payload)
    return ok(data=result.model_dump(mode="json"))


@router.delete("/banks/{bank_id}", summary="删除题库（软删 yn=0；非空且非 force→40924，force→级联软删题目，force 仅 ADMIN）")
async def delete_bank(
    bank_id: int,
    force: bool = Query(False, description="true=库内含题目时仍级联软删题目（仅 ADMIN）"),
    me: CurrentUser = Depends(get_current_user),
):
    # T7-C1：force 级联删除角色门对齐 F9（course_admin 班次删除）——仅 ADMIN，MANAGER 只可删空库
    if force and me.role != UserRole.ADMIN:
        raise PermissionDeniedError("强制级联删除仅 ADMIN 可执行")
    result = await svc.delete_bank(bank_id, force=force)
    return ok(data={
        "deleted": True,
        "id": bank_id,
        "forced": result["forced"],
        "questions_removed": result["questions_removed"],
    })


# ═══════════════════════════════════════════
# 题目（question）CRUD
# ═══════════════════════════════════════════

@router.get("/banks/{bank_id}/questions", summary="按题库查题目列表（分页 + 题型/关键词检索，LIKE 替代标签）")
async def list_questions(
    bank_id: int,
    question_type_id: Optional[int] = Query(None, description="题型ID过滤"),
    keyword: Optional[str] = Query(None, max_length=128, description="关键词（检索 stem / analysis_text）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    result = await svc.list_questions(
        bank_id,
        question_type_id=question_type_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return ok(data=result.model_dump(mode="json"))


@router.get("/questions/{question_id}", summary="题目详情")
async def get_question(question_id: int):
    result = await svc.get_question(question_id)
    return ok(data=result.model_dump(mode="json"))


@router.post("/questions", summary="创建题目", status_code=201)
async def create_question(payload: QuestionAdminCreate):
    result = await svc.create_question(payload)
    return ok(data=result.model_dump(mode="json"))


@router.patch("/questions/{question_id}", summary="更新题目")
async def update_question(question_id: int, payload: QuestionAdminUpdate):
    result = await svc.update_question(question_id, payload)
    return ok(data=result.model_dump(mode="json"))


@router.delete("/questions/{question_id}", summary="删除题目（软删 yn=0）")
async def delete_question(question_id: int):
    await svc.delete_question(question_id)
    return ok(data={"deleted": True, "id": question_id})


# ═══════════════════════════════════════════
# 批量导入
# ═══════════════════════════════════════════

@router.post("/import-preview", summary="批量导入预览（校验 + 报告失败行，不落库）")
async def batch_import_preview(
    bank_id: int = Query(..., description="目标题库ID"),
    items: list[dict] = Body(..., embed=True, description="题目 JSON 数组"),
):
    result = await svc.batch_import_preview(items, bank_id)
    return ok(data=result.model_dump(mode="json"))


@router.post("/import-execute", summary="批量导入执行（幂等：重复 question_code 跳过但返回原记录信息）")
async def batch_import_execute(
    bank_id: int = Query(..., description="目标题库ID"),
    items: list[dict] = Body(..., embed=True, description="题目 JSON 数组"),
):
    result = await svc.batch_import_execute(items, bank_id)
    return ok(data=result.model_dump(mode="json"))


# ═══════════════════════════════════════════
# 考试（session_exam）CRUD + 组卷快照
# ═══════════════════════════════════════════

@router.get("/exams", summary="考试列表（按 session_id 过滤）")
async def list_exams(
    session_id: Optional[int] = Query(None, description="课次ID过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    result = await svc.list_exams(session_id=session_id, page=page, page_size=page_size)
    return ok(data=result.model_dump(mode="json"))


@router.get("/exams/{exam_id}", summary="考试详情（含快照题目列表）")
async def get_exam(exam_id: int):
    result = await svc.get_exam(exam_id)
    return ok(data=result.model_dump(mode="json"))


@router.post("/exams", summary="创建考试", status_code=201)
async def create_exam(payload: ExamCreateAdmin):
    result = await svc.create_exam(payload)
    return ok(data=result.model_dump(mode="json"))


@router.patch("/exams/{exam_id}", summary="更新考试信息（快照题目不受影响）")
async def update_exam(exam_id: int, payload: ExamUpdateAdmin):
    result = await svc.update_exam(exam_id, payload)
    return ok(data=result.model_dump(mode="json"))


@router.post("/exams/{exam_id}/publish", summary="发布考试 = 快照题目到 session_exam_question_rel（冻结后改原题不影响考试判分）")
async def publish_exam(exam_id: int, req: ExamPublishRequest):
    result = await svc.publish_exam(exam_id, req)
    return ok(data=result.model_dump(mode="json"))