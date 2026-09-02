"""
P7 管理端控制台 - 题库管理 service。
题 + 标签 + 批量导入 + 组卷。
"""
from __future__ import annotations

import json
import secrets
from typing import Optional

from app.common.exceptions import AppException as BizError
from app.database import execute_write, fetch_all, fetch_one, transaction
from app.admin.question_admin.schemas import (
    ExamPaper,
    ExamPaperAdminCreate,
    ExamPaperItem,
    PaperComposeRequest,
    PaperComposeResult,
    QuestionAdminCreate,
    QuestionAdminUpdate,
    QuestionBankDetail,
    QuestionBankItem,
    QuestionBankListResponse,
    QuestionBatchImportResponse,
    QuestionTag,
    QuestionTagCreate,
)


# --------- 工具 ---------
def _build_set(patch: dict) -> tuple[str, list]:
    sets = []
    params: list = []
    for k, v in patch.items():
        if v is None:
            continue
        sets.append(f"`{k}` = %s")
        params.append(v)
    if not sets:
        raise BizError(40001, "没有需要更新的字段")
    return " SET " + ", ".join(sets), params


# ============================================================
# 1. 标签 CRUD
# ============================================================
async def list_tags(tag_type: Optional[str] = None, subject_code: Optional[str] = None) -> list[QuestionTag]:
    sql = "SELECT * FROM admin_question_tag WHERE yn = 1"
    params: list = []
    if tag_type:
        sql += " AND tag_type = %s"
        params.append(tag_type)
    if subject_code:
        sql += " AND (subject_code = %s OR subject_code IS NULL)"
        params.append(subject_code)
    sql += " ORDER BY sort_no, id"
    rows = await fetch_all(sql, tuple(params) or None)
    return [QuestionTag(**r) for r in rows]


async def create_tag(payload: QuestionTagCreate) -> int:
    d = payload.model_dump(mode="json")
    sql = """
        INSERT INTO admin_question_tag
        (tag_type, tag_code, tag_name, subject_code, description, sort_no, yn, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,1,NOW(),NOW())
    """
    return int(await execute_write(sql, (
        d["tag_type"], d["tag_code"], d["tag_name"],
        d.get("subject_code"), d.get("description"), d["sort_no"],
    )))


async def delete_tag(tag_id: int) -> None:
    async with transaction() as (conn, cur):
        await cur.execute("DELETE FROM admin_question_to_tag WHERE tag_id = %s", (tag_id,))
        await cur.execute("UPDATE admin_question_tag SET yn = 0, updated_at = NOW() WHERE id = %s", (tag_id,))


# ============================================================
# 2. 题目 CRUD
# ============================================================
async def list_questions(
    subject_code: Optional[str] = None,
    question_type: Optional[str] = None,
    difficulty_level: Optional[str] = None,
    keyword: Optional[str] = None,
    tag_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
    yn: Optional[int] = None,
) -> QuestionBankListResponse:
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    where = ["q.yn = 1" if yn is None else "q.yn = %s"]
    params: list = []
    if yn is not None:
        params.append(yn)
    if subject_code:
        where.append("q.subject_code = %s")
        params.append(subject_code)
    if question_type:
        where.append("q.question_type = %s")
        params.append(question_type)
    if difficulty_level:
        where.append("q.difficulty_level = %s")
        params.append(difficulty_level)
    if keyword:
        where.append("(q.stem_html LIKE %s OR q.question_code LIKE %s)")
        like = f"%{keyword}%"
        params.extend([like, like])
    if tag_id is not None:
        where.append("q.id IN (SELECT question_id FROM admin_question_to_tag WHERE tag_id = %s)")
        params.append(tag_id)

    where_sql = " AND ".join(where)
    total_row = await fetch_one(f"SELECT COUNT(*) c FROM admin_question_bank q WHERE {where_sql}", tuple(params))
    total = int(total_row["c"] if total_row else 0)
    rows = await fetch_all(
        f"""
            SELECT q.*, LEFT(q.stem_html, 120) AS stem_preview
              FROM admin_question_bank q
             WHERE {where_sql}
             ORDER BY q.id DESC
             LIMIT %s OFFSET %s
        """,
        tuple(params + [page_size, offset]),
    )
    qids = [r["id"] for r in rows]
    tag_map: dict[int, list[QuestionTag]] = {}
    if qids:
        placeholders = ",".join(["%s"] * len(qids))
        tag_rows = await fetch_all(
            f"""
                SELECT qt.question_id, t.* FROM admin_question_to_tag qt
                JOIN admin_question_tag t ON t.id = qt.tag_id AND t.yn = 1
                WHERE qt.question_id IN ({placeholders})
            """,
            tuple(qids),
        )
        for tr in tag_rows:
            qid = int(tr["question_id"])
            t_payload = {k: tr[k] for k in tr if k != "question_id"}
            tag_map.setdefault(qid, []).append(QuestionTag(**t_payload))

    items: list[QuestionBankItem] = []
    for r in rows:
        payload = {
            "id": r["id"],
            "question_code": r["question_code"],
            "subject_code": r["subject_code"],
            "question_type": r["question_type"],
            "difficulty_level": r["difficulty_level"],
            "stem_preview": (r.get("stem_preview") or r["stem_html"])[:120],
            "default_score": int(r["default_score"] or 0),
            "yn": int(r["yn"]),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "tags": tag_map.get(int(r["id"]), []),
        }
        items.append(QuestionBankItem(**payload))
    return QuestionBankListResponse(total=total, page=page, page_size=page_size, items=items)


def _parse_options_json(raw) -> list:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            obj = json.loads(raw)
            if isinstance(obj, list):
                return obj
        except Exception:
            return []
    return []


def _parse_kp(raw) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            obj = json.loads(raw)
            if isinstance(obj, list):
                return [str(x) for x in obj]
        except Exception:
            return [x.strip() for x in raw.split(",") if x.strip()]
    return []


async def get_question(question_id: int) -> QuestionBankDetail:
    row = await fetch_one("SELECT * FROM admin_question_bank WHERE id = %s LIMIT 1", (question_id,))
    if not row:
        raise BizError(40401, f"题目不存在 id={question_id}")
    tag_rows = await fetch_all(
        """
        SELECT t.* FROM admin_question_to_tag qt
        JOIN admin_question_tag t ON t.id = qt.tag_id AND t.yn = 1
        WHERE qt.question_id = %s
        ORDER BY t.sort_no
        """,
        (question_id,),
    )
    payload = {
        **row,
        "options_json": _parse_options_json(row.get("options_json")),
        "knowledge_point_codes": _parse_kp(row.get("knowledge_point_codes")),
        "tags": [QuestionTag(**tr) for tr in tag_rows],
    }
    return QuestionBankDetail(**payload)


async def _sync_tags(question_id: int, tag_ids: list[int]) -> None:
    async with transaction() as (conn, cur):
        await cur.execute("DELETE FROM admin_question_to_tag WHERE question_id = %s", (question_id,))
        seen = set()
        for tid in tag_ids:
            if tid in seen:
                continue
            seen.add(tid)
            await cur.execute(
                "INSERT IGNORE INTO admin_question_to_tag (question_id, tag_id) VALUES (%s,%s)",
                (question_id, int(tid)),
            )


async def create_question(payload: QuestionAdminCreate, created_by: int) -> int:
    exists = await fetch_one("SELECT id FROM admin_question_bank WHERE question_code = %s LIMIT 1", (payload.question_code,))
    if exists:
        raise BizError(40901, f"题目编码已存在: {payload.question_code}")
    d = payload.model_dump(mode="json")
    tag_ids: list[int] = [int(x) for x in (d.pop("tag_ids") or [])]
    options_raw = json.dumps(d.get("options_json") or [], ensure_ascii=False)
    kp_raw = json.dumps(d.get("knowledge_point_codes") or [], ensure_ascii=False)
    async with transaction() as (conn, cur):
        await cur.execute(
            """
            INSERT INTO admin_question_bank
            (question_code, subject_code, question_type, difficulty_level, stem_html,
             analysis_html, options_json, correct_answer, correct_answer_detail,
             default_score, knowledge_point_codes, created_by, updated_by, yn, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,NOW(),NOW())
            """,
            (
                d["question_code"], d["subject_code"], d["question_type"], d["difficulty_level"],
                d["stem_html"], d.get("analysis_html"), options_raw, d["correct_answer"],
                d.get("correct_answer_detail"), d["default_score"], kp_raw,
                created_by, created_by,
            ),
        )
        qid = int(cur.lastrowid)
        for tid in tag_ids:
            await cur.execute(
                "INSERT IGNORE INTO admin_question_to_tag (question_id, tag_id) VALUES (%s,%s)",
                (qid, tid),
            )
    return qid


async def update_question(question_id: int, payload: QuestionAdminUpdate, updated_by: int) -> None:
    exists = await fetch_one("SELECT id FROM admin_question_bank WHERE id = %s LIMIT 1", (question_id,))
    if not exists:
        raise BizError(40401, f"题目不存在 id={question_id}")
    d = payload.model_dump(mode="json")
    tag_ids: Optional[list[int]] = d.pop("tag_ids", None)
    patch: dict = {"updated_by": updated_by}
    if d.get("options_json") is not None:
        patch["options_json"] = json.dumps(d["options_json"], ensure_ascii=False)
    if d.get("knowledge_point_codes") is not None:
        patch["knowledge_point_codes"] = json.dumps(d["knowledge_point_codes"], ensure_ascii=False)
    for k, v in d.items():
        if k in ("options_json", "knowledge_point_codes"):
            continue
        if v is not None:
            patch[k] = v
    set_sql, params = _build_set(patch)
    params.append(question_id)
    await execute_write(f"UPDATE admin_question_bank {set_sql}, updated_at = NOW() WHERE id = %s", tuple(params))
    if tag_ids is not None:
        await _sync_tags(question_id, [int(x) for x in tag_ids])


async def delete_question(question_id: int) -> None:
    n = await execute_write("UPDATE admin_question_bank SET yn = 0, updated_at = NOW() WHERE id = %s", (question_id,))
    if n == 0:
        raise BizError(40401, f"题目不存在 id={question_id}")


# ============================================================
# 3. 批量导入（JSON 数组：[{...QuestionAdminCreate}]）
# ============================================================
async def batch_import_questions(items: list[dict], operator_id: int) -> QuestionBatchImportResponse:
    messages: list[str] = []
    imported = 0
    skipped = 0
    failed = 0
    for idx, raw in enumerate(items):
        try:
            payload = QuestionAdminCreate(**raw)
            try:
                await create_question(payload, operator_id)
                imported += 1
            except BizError as be:
                if "已存在" in str(be):
                    skipped += 1
                    messages.append(f"[{idx}] skip 编码重复: {payload.question_code}")
                else:
                    failed += 1
                    messages.append(f"[{idx}] fail: {be.message}")
        except Exception as exc:
            failed += 1
            messages.append(f"[{idx}] schema invalid: {exc}")
    return QuestionBatchImportResponse(
        total=len(items),
        imported=imported,
        skipped=skipped,
        failed=failed,
        messages=messages[:20],
    )


# ============================================================
# 4. 试卷 CRUD
# ============================================================
async def _attach_items_to_paper(paper_id: int) -> list[ExamPaperItem]:
    rows = await fetch_all(
        "SELECT * FROM admin_exam_paper_item WHERE paper_id = %s ORDER BY sort_no, id",
        (paper_id,),
    )
    return [ExamPaperItem(**r) for r in rows]


async def list_exam_papers(subject_code: Optional[str] = None, yn: int = 1) -> list[ExamPaper]:
    sql = "SELECT * FROM admin_exam_paper WHERE yn = %s"
    params: list = [yn]
    if subject_code:
        sql += " AND subject_code = %s"
        params.append(subject_code)
    sql += " ORDER BY id DESC"
    rows = await fetch_all(sql, tuple(params))
    result: list[ExamPaper] = []
    for r in rows:
        items = await _attach_items_to_paper(int(r["id"]))
        result.append(ExamPaper(**{**r, "items": items}))
    return result


async def create_exam_paper(payload: ExamPaperAdminCreate, created_by: int) -> ExamPaper:
    exists = await fetch_one("SELECT id FROM admin_exam_paper WHERE paper_code = %s LIMIT 1", (payload.paper_code,))
    if exists:
        raise BizError(40901, f"试卷编码已存在: {payload.paper_code}")
    d = payload.model_dump(mode="json")
    items: list[dict] = d.pop("items") or []
    async with transaction() as (conn, cur):
        await cur.execute(
            """
            INSERT INTO admin_exam_paper
            (paper_code, paper_title, subject_code, total_score, duration_minutes,
             pass_score, description, created_by, yn, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,1,NOW(),NOW())
            """,
            (
                d["paper_code"], d["paper_title"], d["subject_code"],
                int(d["total_score"]), int(d["duration_minutes"]),
                int(d["pass_score"]), d.get("description"), created_by,
            ),
        )
        pid = int(cur.lastrowid)
        for it in items:
            await cur.execute(
                "INSERT INTO admin_exam_paper_item (paper_id, question_id, sort_no, score) VALUES (%s,%s,%s,%s)",
                (pid, int(it["question_id"]), int(it.get("sort_no", 0)), int(it.get("score", 0))),
            )
    items_out = await _attach_items_to_paper(pid)
    paper = await fetch_one("SELECT * FROM admin_exam_paper WHERE id = %s", (pid,))
    return ExamPaper(**{**paper, "items": items_out})


async def delete_exam_paper(paper_id: int) -> None:
    async with transaction() as (conn, cur):
        await cur.execute("DELETE FROM admin_exam_paper_item WHERE paper_id = %s", (paper_id,))
        await cur.execute("UPDATE admin_exam_paper SET yn = 0, updated_at = NOW() WHERE id = %s", (paper_id,))


# ============================================================
# 5. 组卷（按规格在库里挑选 → 生成 1 张草稿试卷）
# ============================================================
async def compose_paper(req: PaperComposeRequest, operator_id: int) -> PaperComposeResult:
    spec = req.spec
    expected = int(req.expected_question_count)

    where = ["q.yn = 1"]
    params: list = []
    if spec.subject_code:
        where.append("q.subject_code = %s")
        params.append(spec.subject_code)
    if spec.difficulty_level:
        where.append("q.difficulty_level = %s")
        params.append(spec.difficulty_level)
    if spec.tag_ids:
        placeholders = ",".join(["%s"] * len(spec.tag_ids))
        where.append(f"q.id IN (SELECT question_id FROM admin_question_to_tag WHERE tag_id IN ({placeholders}))")
        params.extend([int(x) for x in spec.tag_ids])

    sql = f"SELECT q.* FROM admin_question_bank q WHERE {' AND '.join(where)} ORDER BY RAND() LIMIT %s"
    rows = await fetch_all(sql, tuple(params + [expected]))
    if not rows:
        raise BizError(40402, "未挑选到满足规格的题目，请放宽标签/难度条件")

    paper_payload = {
        "paper_code": req.paper_code + "-" + secrets.token_hex(2).upper(),
        "paper_title": req.paper_title,
        "subject_code": spec.subject_code,
        "total_score": int(spec.total_score),
        "duration_minutes": int(spec.duration_minutes),
        "pass_score": int(spec.pass_score),
        "description": f"自动组卷草稿（规格 tag_ids={spec.tag_ids} diff={spec.difficulty_level}）",
        "items": [],
    }
    picked_items: list[dict] = []
    per_score = int(spec.per_question_score) or 5
    for idx, r in enumerate(rows):
        picked_items.append({
            "question_id": int(r["id"]),
            "sort_no": idx + 1,
            "score": per_score,
        })
    paper_payload["items"] = picked_items
    paper = await create_exam_paper(ExamPaperAdminCreate(**paper_payload), created_by=operator_id)
    return PaperComposeResult(
        draft_paper_id=int(paper.id),
        paper_code=paper.paper_code,
        paper_title=paper.paper_title,
        selected_count=len(rows),
        total_score=len(rows) * per_score,
        message=f"已生成试卷草稿，可手动在 items 中再调分或改排序。",
        items=picked_items,
    )
