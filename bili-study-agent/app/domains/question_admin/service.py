"""
管理端题库域服务层（task13）。

职责：
- question_bank CRUD（bank_code 唯一冲突 → 409xx）
- question CRUD（question_code 唯一 per bank → 409xx；LIKE 全文检索替代标签）
- 批量导入：校验 → 预览 → 分批导入 → 失败行定位 → 幂等（question_no 冲突回查）
- 组卷快照：发布考试时将题目快照到 session_exam_question_rel
- quiz 出题源：从 question 表读取（替代旧 admin_question）
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, List, Optional

from app.common.error_codes import (
    BAD_REQUEST,
    BANK_IN_USE,
    CONFLICT,
    NOT_FOUND,
)
from app.common.exceptions import AppException, ConflictError, NotFoundError
from app.common.logging import logger
from app.database import fetch_all, fetch_one, transaction
from app.domains.question_admin.repository import (
    BankAdminRepo,
    DimQuestionTypeRepo,
    ExamAdminRepo,
    QuestionAdminRepo,
)
from app.domains.question_admin.schemas import (
    BankCreateAdmin,
    BankListDataAdmin,
    BankResponseAdmin,
    BankUpdateAdmin,
    BatchImportExecuteResponse,
    BatchImportItem,
    BatchImportPreviewResponse,
    BatchImportPreviewRow,
    ExamCreateAdmin,
    ExamListDataAdmin,
    ExamPublishRequest,
    ExamPublishResponse,
    ExamResponseAdmin,
    ExamQuestionRelItem,
    ExamUpdateAdmin,
    QuestionAdminCreate,
    QuestionAdminUpdate,
    QuestionPublishAdmin,
    QuestionListDataAdmin,
    QuestionResponseAdmin,
    QuestionTypeResponse,
)

_bank_repo = BankAdminRepo()
_question_repo = QuestionAdminRepo()
_exam_repo = ExamAdminRepo()
_dim_repo = DimQuestionTypeRepo()


# ═══════════════════════════════════════════
# question_bank CRUD
# ═══════════════════════════════════════════

async def create_bank(payload: BankCreateAdmin) -> BankResponseAdmin:
    """创建题库（bank_code 唯一约束 → 409）。"""
    exists = await _bank_repo.get_by_code(payload.institution_id, payload.bank_code)
    if exists:
        raise ConflictError(
            message=f"题库编码已存在: {payload.bank_code}",
            code="40921",
        )
    d = payload.model_dump(mode="json")
    pk = await _bank_repo.insert(d)
    row = await _bank_repo.get_by_id(pk)
    if not row:
        raise AppException("50000", "创建题库后读取失败")
    return BankResponseAdmin(**row)


async def list_banks(
    *,
    institution_id: Optional[int] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> BankListDataAdmin:
    """题库列表（分页，LIKE 检索 bank_name/bank_code）。"""
    rows, total = await _bank_repo.list_banks(
        institution_id=institution_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    items = [BankResponseAdmin(**r) for r in rows]
    return BankListDataAdmin(items=items, total=total, page=page, page_size=page_size)


async def get_bank(bank_id: int) -> BankResponseAdmin:
    row = await _bank_repo.get_by_id(bank_id)
    if not row or row.get("yn") == 0:
        raise NotFoundError("题库", str(bank_id))
    return BankResponseAdmin(**row)


async def update_bank(bank_id: int, payload: BankUpdateAdmin) -> BankResponseAdmin:
    row = await _bank_repo.get_by_id(bank_id)
    if not row:
        raise NotFoundError("题库", str(bank_id))
    patch = {k: v for k, v in payload.model_dump(mode="json").items() if v is not None}
    if not patch:
        return BankResponseAdmin(**row)
    await _bank_repo.update(bank_id, patch)
    updated = await _bank_repo.get_by_id(bank_id)
    return BankResponseAdmin(**updated)


async def delete_bank(bank_id: int, *, force: bool = False) -> dict:
    """删除题库（软删 yn=0）。

    F-8 引用保护（对齐课程域 40908 风格）：
    - 库内仍有有效题目且未显式 force → 40924，绝不静默留下题目孤儿；
    - force=True → 先级联软删库内题目（yn=0，可恢复，不物理删）再软删题库。
    """
    row = await _bank_repo.get_by_id(bank_id)
    if not row or row.get("yn") == 0:
        raise NotFoundError("题库", str(bank_id))
    question_count = await _question_repo.count_active_by_bank(bank_id)
    if question_count > 0 and not force:
        raise ConflictError(
            message=f"题库内仍有 {question_count} 道有效题目，无法删除（确需连同题目一并删除请加 force=true）",
            code=BANK_IN_USE,
        )
    cascaded = 0
    if question_count > 0:  # force=True
        cascaded = await _question_repo.soft_delete_all_by_bank(bank_id)
    await _bank_repo.soft_delete(bank_id)
    return {"bank_id": bank_id, "forced": bool(force and cascaded > 0), "questions_removed": cascaded}


# ═══════════════════════════════════════════
# question CRUD
# ═══════════════════════════════════════════

def _parse_row_to_question(row: dict) -> dict:
    """解析 JSON 列（asyncmy 返回 str → 实际类型）。"""
    result = dict(row)
    if isinstance(result.get("options_json"), str):
        try:
            result["options_json"] = json.loads(result["options_json"])
        except (json.JSONDecodeError, TypeError):
            result["options_json"] = None
    return result


async def create_question(payload: QuestionAdminCreate) -> QuestionResponseAdmin:
    """创建题目（question_code 唯一 per bank → 409）。"""
    # 校验 bank 存在
    bank = await _bank_repo.get_by_id(payload.bank_id)
    if not bank or bank.get("yn") == 0:
        raise NotFoundError("题库", str(payload.bank_id))
    # 校验题型存在
    qtype = await _dim_repo.get_by_id(payload.question_type_id)
    if not qtype:
        raise AppException(BAD_REQUEST, f"题型不存在: question_type_id={payload.question_type_id}")
    # 唯一约束
    exists = await _question_repo.get_by_code(payload.bank_id, payload.question_code)
    if exists:
        raise ConflictError(
            message=f"题目编码已存在: {payload.question_code}（bank_id={payload.bank_id}）",
            code="40922",
        )
    d = payload.model_dump(mode="json")
    pk = await _question_repo.insert(d)
    row = await _question_repo.get_by_id(pk)
    if not row:
        raise AppException("50000", "创建题目后读取失败")
    return QuestionResponseAdmin(**_parse_row_to_question(row))


async def list_questions(
    bank_id: int,
    *,
    question_type_id: Optional[int] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> QuestionListDataAdmin:
    """按题库查题目列表（LIKE 检索 stem/analysis_text 替代标签逻辑删除）。"""
    rows, total = await _question_repo.list_by_bank(
        bank_id,
        question_type_id=question_type_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    items = [QuestionResponseAdmin(**_parse_row_to_question(r)) for r in rows]
    return QuestionListDataAdmin(items=items, total=total, page=page, page_size=page_size)


async def get_question(question_id: int) -> QuestionResponseAdmin:
    row = await _question_repo.get_by_id(question_id)
    if not row or row.get("yn") == 0:
        raise NotFoundError("题目", str(question_id))
    return QuestionResponseAdmin(**_parse_row_to_question(row))


async def update_question(question_id: int, payload: QuestionAdminUpdate) -> QuestionResponseAdmin:
    row = await _question_repo.get_by_id(question_id)
    if not row:
        raise NotFoundError("题目", str(question_id))
    patch = {k: v for k, v in payload.model_dump(mode="json").items() if v is not None}
    if not patch:
        return QuestionResponseAdmin(**_parse_row_to_question(row))
    async with transaction() as (_conn, cur):
        await cur.execute("SELECT id,yn FROM `question` WHERE id=%s FOR UPDATE", (question_id,))
        locked_question = await cur.fetchone()
        if not locked_question or int(locked_question[1]) != 1:
            raise NotFoundError("题目", str(question_id))
        await cur.execute(
            "SELECT review_status,question_version FROM quiz_question_publication "
            "WHERE question_id=%s FOR UPDATE",
            (question_id,),
        )
        publication = await cur.fetchone()
        if publication and publication[0] == "PUBLISHED":
            raise ConflictError(
                "已发布题目不可直接修改。请先退役题目，再编辑并使用新的 question_version 重新发布。",
                code="40923",
            )
        assignments = []
        values = []
        for key, value in patch.items():
            if key == "options_json" and value is not None:
                value = json.dumps(value, ensure_ascii=False)
            assignments.append(f"`{key}`=%s")
            values.append(value)
        assignments.append("updated_at=NOW()")
        values.append(question_id)
        await cur.execute(
            f"UPDATE `question` SET {','.join(assignments)} WHERE id=%s",
            tuple(values),
        )
    updated = await _question_repo.get_by_id(question_id)
    return QuestionResponseAdmin(**_parse_row_to_question(updated))


async def publish_bank_practice(bank_id: int, subject_code: str, *, reviewer_user_id: int) -> dict:
    """Explicit admin publication, reusing the same quiz authority and grading path."""
    import hashlib
    from app.interactive.quiz.service import _unjson
    bank = await _bank_repo.get_by_id(bank_id)
    if not bank or int(bank.get("yn", 0)) != 1:
        raise NotFoundError("题库", str(bank_id))
    rows = await fetch_all("SELECT q.*,qt.type_code FROM question q JOIN dim_question_type qt "
        "ON qt.id=q.question_type_id WHERE q.bank_id=%s AND q.yn=1 ORDER BY q.id LIMIT 101", (bank_id,))
    if not rows or len(rows) > 100:
        raise AppException(BAD_REQUEST, "请发布含 1～100 道题的题库；较大题库需分组审核")
    for row in rows:
        options = _unjson(row.get("options_json")) or []
        answer = _unjson(row["answer_text"])
        if answer is None: answer = row["answer_text"]
        keys = {str(option.get("key", option.get("label", ""))) for option in options if isinstance(option, dict)}
        valid = bool(row.get("stem") and row.get("analysis_text"))
        if row["type_code"] == "single_choice": valid = valid and isinstance(answer, str) and answer in keys and len(keys) >= 2
        elif row["type_code"] == "multi_choice": valid = valid and isinstance(answer, list) and bool(answer) and set(answer) <= keys
        elif row["type_code"] == "true_false":
            from app.interactive.quiz.service import _normalize_judge
            valid = valid and _normalize_judge(answer) is not None
        elif row["type_code"] == "fill_blank": valid = valid and bool(answer)
        else: valid = False
        if not valid:
            raise AppException(BAD_REQUEST, "请先修正题目格式、答案或解析：" + row["question_code"])
    result = {"bank_id": bank_id, "published": 0, "already_published": 0, "preserved_course_questions": 0, "failures": []}
    for row in rows:
        old = await fetch_one("SELECT course_id,review_status,question_version FROM quiz_question_publication WHERE question_id=%s", (row["id"],))
        if old and old["course_id"] is not None:
            result["preserved_course_questions"] += 1
            continue
        if old and old["review_status"] == "PUBLISHED":
            result["already_published"] += 1
            continue
        canonical = json.dumps({key:row[key] for key in ("question_code","stem","options_json","answer_text","analysis_text")}, ensure_ascii=False, sort_keys=True)
        content_hash = hashlib.sha256(canonical.encode()).hexdigest()
        version = "bank-" + hashlib.sha256((canonical + (old["question_version"] if old else "")).encode()).hexdigest()[:32]
        payload = QuestionPublishAdmin(course_id=None, question_version=version, subject_code=subject_code,
            difficulty="basic", source="owned_question_bank", knowledge_codes=[],
            content_authorization_ref="Admin publication of existing bank " + str(bank_id),
            expected_content_sha256=content_hash, preserve_course_scope=True)
        try:
            await publish_quiz_question(row["id"], payload, reviewer_user_id=reviewer_user_id)
            result["published"] += 1
        except AppException as error:
            result["failures"].append({"question_code":row["question_code"], "message":error.message})
    return result


async def publish_quiz_question(question_id: int, payload: QuestionPublishAdmin,
                                *, reviewer_user_id: int) -> dict:
    """发布正式题：课程、题面元数据、授权依据及有效 KP 必须一并存在。"""
    question = await _question_repo.get_by_id(question_id)
    if not question or int(question.get("yn", 0)) != 1:
        raise NotFoundError("题目", str(question_id))
    if payload.course_id is not None:
        course = await fetch_one("SELECT id FROM series_cohort_course WHERE id=%s", (payload.course_id,))
        if not course:
            raise NotFoundError("课程", str(payload.course_id))
    codes = sorted({str(code).strip() for code in payload.knowledge_codes if str(code).strip()})
    if payload.course_id is not None and not codes:
        raise AppException(BAD_REQUEST, "正式题必须关联至少一个有效知识点")
    placeholders = ",".join(["%s"] * len(codes))
    active = await fetch_all(
        "SELECT code FROM graph_node WHERE label='KnowledgePoint' AND yn=1 "
        f"AND code IN ({placeholders})",
        tuple(codes),
    ) if codes else []
    active_codes = {str(row["code"]) for row in active}
    missing = [code for code in codes if code not in active_codes]
    if missing:
        raise AppException(BAD_REQUEST, "知识点不存在或未启用: " + ", ".join(missing))
    auth_ref = payload.content_authorization_ref.strip()
    if not auth_ref:
        raise AppException(BAD_REQUEST, "发布正式题必须记录内容授权依据")
    async with transaction() as (_conn, cur):
        await cur.execute("SELECT id,question_code,stem,options_json,answer_text,analysis_text FROM `question` WHERE id=%s AND yn=1 FOR UPDATE", (question_id,))
        locked_question = await cur.fetchone()
        if locked_question is None:
            raise NotFoundError("题目", str(question_id))
        if payload.expected_content_sha256:
            import hashlib
            canonical = json.dumps(dict(zip(("question_code","stem","options_json","answer_text","analysis_text"), locked_question[1:])), ensure_ascii=False, sort_keys=True)
            if hashlib.sha256(canonical.encode()).hexdigest() != payload.expected_content_sha256:
                raise ConflictError("题目在校验后已修改，请重新检查并发布。", code="40924")
        if payload.course_id is not None:
            await cur.execute("SELECT id FROM series_cohort_course WHERE id=%s FOR UPDATE", (payload.course_id,))
            if await cur.fetchone() is None:
                raise NotFoundError("课程", str(payload.course_id))
        if codes:
            await cur.execute(
            "SELECT code FROM graph_node WHERE label='KnowledgePoint' AND yn=1 "
            f"AND code IN ({placeholders}) FOR UPDATE",
            tuple(codes),
            )
            active_codes_in_tx = {str(row[0]) for row in await cur.fetchall()}
            if active_codes_in_tx != set(codes):
                raise AppException(BAD_REQUEST, "发布时知识点状态已变化，请重新选择有效知识点")
        await cur.execute(
            "SELECT review_status,question_version,course_id FROM quiz_question_publication "
            "WHERE question_id=%s FOR UPDATE",
            (question_id,),
        )
        old_publication = await cur.fetchone()
        if payload.preserve_course_scope and old_publication and old_publication[2] is not None:
            raise ConflictError("题目已绑定课程，保留课程专属权限。", code="40924")
        if (old_publication and old_publication[0] in ("PUBLISHED", "RETIRED")
                and str(old_publication[1]) == payload.question_version.strip()):
            raise ConflictError(
                "重新发布必须使用新的 question_version。",
                code="40924",
            )
        await cur.execute(
            "INSERT INTO quiz_question_publication "
            "(question_id,course_id,question_version,subject_code,difficulty,source,review_status,"
            "published_at,reviewer_user_id,content_authorization_ref,created_at,updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,'PUBLISHED',NOW(),%s,%s,NOW(),NOW()) "
            "ON DUPLICATE KEY UPDATE course_id=VALUES(course_id),"
            "question_version=VALUES(question_version),subject_code=VALUES(subject_code),"
            "difficulty=VALUES(difficulty),source=VALUES(source),review_status='PUBLISHED',"
            "published_at=NOW(),reviewer_user_id=VALUES(reviewer_user_id),"
            "content_authorization_ref=VALUES(content_authorization_ref),updated_at=NOW()",
            (question_id, payload.course_id, payload.question_version.strip(),
             payload.subject_code.strip(), payload.difficulty.strip(), payload.source.strip(),
             reviewer_user_id, auth_ref),
        )
        await cur.execute("DELETE FROM quiz_question_kp WHERE question_id=%s", (question_id,))
        if codes:
            await cur.executemany(
            "INSERT INTO quiz_question_kp (question_id,knowledge_code) VALUES (%s,%s)",
            [(question_id, code) for code in codes],
            )
    return {"question_id": question_id, "course_id": payload.course_id,
            "question_version": payload.question_version.strip(), "subject_code": payload.subject_code.strip(),
            "knowledge_codes": codes, "review_status": "PUBLISHED",
            "reviewer_user_id": reviewer_user_id, "content_authorization_ref": auth_ref}


async def retire_quiz_question(question_id: int, *, reviewer_user_id: int) -> dict:
    """停止向学生发放当前版本；之后可编辑题目并以新版本重新发布。"""
    async with transaction() as (_conn, cur):
        await cur.execute(
            "SELECT review_status,question_version FROM quiz_question_publication "
            "WHERE question_id=%s FOR UPDATE",
            (question_id,),
        )
        publication = await cur.fetchone()
        if not publication:
            raise NotFoundError("已发布题目", str(question_id))
        if publication[0] != "PUBLISHED":
            raise ConflictError("只有 PUBLISHED 题目可以退役。", code="40925")
        await cur.execute(
            "UPDATE quiz_question_publication SET review_status='RETIRED',reviewer_user_id=%s,updated_at=NOW() "
            "WHERE question_id=%s AND review_status='PUBLISHED'",
            (int(reviewer_user_id), int(question_id)),
        )
    return {"question_id": question_id, "review_status": "RETIRED",
            "question_version": str(publication[1]), "reviewer_user_id": int(reviewer_user_id)}


async def delete_question(question_id: int) -> None:
    """软删题目（yn=0）。"""
    row = await _question_repo.get_by_id(question_id)
    if not row or row.get("yn") == 0:
        raise NotFoundError("题目", str(question_id))
    await _question_repo.soft_delete(question_id)


# ═══════════════════════════════════════════
# dim_question_type（只读）
# ═══════════════════════════════════════════

async def list_question_types() -> List[QuestionTypeResponse]:
    rows = await _dim_repo.list_all()
    return [QuestionTypeResponse(**r) for r in rows]


# ═══════════════════════════════════════════
# 批量导入
# ═══════════════════════════════════════════

async def batch_import_preview(
    items: List[dict],
    bank_id: int,
) -> BatchImportPreviewResponse:
    """批量导入预览：逐行校验，返回每行结果（不落库）。"""
    # 校验 bank 存在
    bank = await _bank_repo.get_by_id(bank_id)
    if not bank or bank.get("yn") == 0:
        raise NotFoundError("题库", str(bank_id))

    rows: List[BatchImportPreviewRow] = []
    valid_count = 0
    for idx, raw in enumerate(items):
        errors: List[str] = []
        # 必填检查
        if not raw.get("question_code"):
            errors.append("缺少 question_code")
        if not raw.get("stem"):
            errors.append("题干为空")
        if not raw.get("answer_text"):
            errors.append("答案为空")
        # 题型检查
        qtype_id = raw.get("question_type_id")
        if qtype_id is None:
            errors.append("缺少 question_type_id")
        else:
            qtype = await _dim_repo.get_by_id(int(qtype_id))
            if not qtype:
                errors.append(f"题型不存在: question_type_id={qtype_id}")

        valid = len(errors) == 0
        if valid:
            valid_count += 1
        rows.append(BatchImportPreviewRow(
            row_index=idx,
            question_code=raw.get("question_code", ""),
            valid=valid,
            errors=errors,
        ))

    return BatchImportPreviewResponse(
        total_rows=len(items),
        valid_rows=valid_count,
        invalid_rows=len(items) - valid_count,
        rows=rows,
        message=f"预览完成：{valid_count} 行有效，{len(items) - valid_count} 行无效",
    )


async def batch_import_execute(
    items: List[dict],
    bank_id: int,
) -> BatchImportExecuteResponse:
    """批量导入执行：分批插入，幂等（question_code 冲突时回查返回原记录）。"""
    bank = await _bank_repo.get_by_id(bank_id)
    if not bank or bank.get("yn") == 0:
        raise NotFoundError("题库", str(bank_id))

    imported = 0
    skipped = 0
    failed = 0
    messages: List[str] = []

    for idx, raw in enumerate(items):
        try:
            # 校验
            if not raw.get("question_code") or not raw.get("stem") or not raw.get("answer_text"):
                failed += 1
                messages.append(f"[{idx}] 缺少必填字段: question_code/stem/answer_text")
                continue
            qtype_id = raw.get("question_type_id")
            if qtype_id is None:
                failed += 1
                messages.append(f"[{idx}] 缺少 question_type_id")
                continue
            qtype = await _dim_repo.get_by_id(int(qtype_id))
            if not qtype:
                failed += 1
                messages.append(f"[{idx}] 题型不存在: question_type_id={qtype_id}")
                continue

            # 幂等检查
            question_code = raw["question_code"]
            existing = await _question_repo.get_by_code(bank_id, question_code)
            if existing:
                skipped += 1
                messages.append(f"[{idx}] 幂等跳过（已存在）: {question_code}")
                continue

            # 构造 payload 插入
            payload = QuestionAdminCreate(
                bank_id=bank_id,
                question_code=question_code,
                question_type_id=int(qtype_id),
                stem=raw["stem"],
                options_json=raw.get("options_json"),
                answer_text=raw["answer_text"],
                analysis_text=raw.get("analysis_text"),
            )
            await _question_repo.insert(payload.model_dump(mode="json"))
            imported += 1

        except Exception as exc:
            failed += 1
            messages.append(f"[{idx}] 异常: {str(exc)[:200]}")

    return BatchImportExecuteResponse(
        total=len(items),
        imported=imported,
        skipped=skipped,
        failed=failed,
        messages=messages[:50],
    )


# ═══════════════════════════════════════════
# session_exam CRUD + 组卷快照
# ═══════════════════════════════════════════

async def create_exam(payload: ExamCreateAdmin) -> ExamResponseAdmin:
    """创建考试（exam_code 唯一 per session → 409）。"""
    exists = await _exam_repo.get_by_code(payload.session_id, payload.exam_code)
    if exists:
        raise ConflictError(
            message=f"考试编码已存在: {payload.exam_code}（session_id={payload.session_id}）",
            code="40923",
        )
    d = payload.model_dump(mode="json")
    pk = await _exam_repo.insert(d)
    row = await _exam_repo.get_by_id(pk)
    if not row:
        raise AppException("50000", "创建考试后读取失败")
    # 附带已有快照关系
    questions = await _exam_repo.list_questions(pk)
    return ExamResponseAdmin(**row, questions=[ExamQuestionRelItem(**q) for q in questions])


async def list_exams(session_id: Optional[int] = None, page: int = 1, page_size: int = 20) -> ExamListDataAdmin:
    """考试列表。"""
    if session_id:
        rows = await _exam_repo.list_by_session(session_id)
    else:
        rows = []
    # 简单分页（全量查后截取）
    total = len(rows)
    offset = (page - 1) * page_size
    page_rows = rows[offset:offset + page_size]
    items: List[ExamResponseAdmin] = []
    for r in page_rows:
        questions = await _exam_repo.list_questions(int(r["id"]))
        items.append(ExamResponseAdmin(**r, questions=[ExamQuestionRelItem(**q) for q in questions]))
    return ExamListDataAdmin(items=items, total=total, page=page, page_size=page_size)


async def get_exam(exam_id: int) -> ExamResponseAdmin:
    row = await _exam_repo.get_by_id(exam_id)
    if not row:
        raise NotFoundError("考试", str(exam_id))
    questions = await _exam_repo.list_questions(exam_id)
    return ExamResponseAdmin(**row, questions=[ExamQuestionRelItem(**q) for q in questions])


async def update_exam(exam_id: int, payload: ExamUpdateAdmin) -> ExamResponseAdmin:
    row = await _exam_repo.get_by_id(exam_id)
    if not row:
        raise NotFoundError("考试", str(exam_id))
    patch = {k: v for k, v in payload.model_dump(mode="json").items() if v is not None}
    if patch:
        await _exam_repo.update(exam_id, patch)
    updated = await _exam_repo.get_by_id(exam_id)
    questions = await _exam_repo.list_questions(exam_id)
    return ExamResponseAdmin(**updated, questions=[ExamQuestionRelItem(**q) for q in questions])


async def publish_exam(exam_id: int, req: ExamPublishRequest) -> ExamPublishResponse:
    """发布考试 = 快照题目到 session_exam_question_rel（先清空再写入 = 原子快照）。"""
    row = await _exam_repo.get_by_id(exam_id)
    if not row:
        raise NotFoundError("考试", str(exam_id))

    # 校验所有 question_id 存在且 yn=1
    for item in req.question_ids:
        qid = int(item["question_id"])
        q = await _question_repo.get_by_id(qid)
        if not q or q.get("yn") == 0:
            raise NotFoundError("题目", str(qid))

    # 先清空旧快照
    await _exam_repo.delete_questions(exam_id)
    # 写入新快照
    for item in req.question_ids:
        await _exam_repo.insert_question(
            exam_id,
            int(item["question_id"]),
            int(item.get("sort_no", 0)),
            float(item.get("score", 0)),
        )

    # 更新 publish_status → published
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await _exam_repo.update(exam_id, {
        "publish_status": "published",
        "publish_at": now_str,
    })

    updated = await _exam_repo.get_by_id(exam_id)
    questions = await _exam_repo.list_questions(exam_id)
    return ExamPublishResponse(
        exam_id=int(updated["id"]),
        exam_code=updated["exam_code"],
        publish_status=updated["publish_status"],
        question_count=len(questions),
        message=f"考试已发布，{len(questions)} 道题目快照已冻结",
    )


# ═══════════════════════════════════════════
# quiz 出题源（从 question 表读取）
# ═══════════════════════════════════════════

async def get_quiz_question(question_id: int) -> Optional[dict]:
    """从 question 表读取题目（quiz 出题源用，替代旧 admin_question）。"""
    row = await _question_repo.get_by_id(question_id)
    if not row or row.get("yn") == 0:
        return None
    return _parse_row_to_question(row)


async def get_quiz_question_by_code(bank_id: int, question_code: str) -> Optional[dict]:
    """按 bank_id + question_code 查题目（quiz 出题源用）。"""
    row = await _question_repo.get_by_code(bank_id, question_code)
    if not row or row.get("yn") == 0:
        return None
    return _parse_row_to_question(row)


async def count_questions_by_bank(bank_id: int) -> int:
    """统计题库中有效题目数。"""
    rows, total = await _question_repo.list_by_bank(bank_id, page=1, page_size=1)
    return total
