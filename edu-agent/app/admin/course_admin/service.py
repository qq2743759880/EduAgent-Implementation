"""
P7 管理端控制台 - 课程管理 service。
写入 curriculum_series/cohort/module/session + admin_course_video_asset。
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from app.common.exceptions import AppException as BizError
from app.config import settings
from app.database import execute_write, fetch_all, fetch_one, transaction
from app.curriculum.schemas import (
    Cohort,
    Module,
    Series,
    SeriesDetailResponse,
    SeriesListItem,
    SeriesListResponse,
    SeriesTreeResponse,
    Session,
)
from app.admin.course_admin.schemas import (
    BindVideoToSessionRequest,
    CohortAdminCreate,
    CohortAdminUpdate,
    MaterialRedirectResponse,
    ModuleAdminCreate,
    ModuleAdminUpdate,
    SeriesAdminCreate,
    SeriesAdminUpdate,
    SessionAdminCreate,
    SessionAdminUpdate,
    VideoAsset,
    VideoUploadFinalizeRequest,
    VideoUploadInitRequest,
    VideoUploadInitResponse,
)


# ============================================================
# 内部工具：课程树 / 详情组装
# ============================================================
def _assemble_detail(series_row: dict, cohorts_rows: list[dict], modules_rows: list[dict], sessions_rows: list[dict]) -> SeriesDetailResponse:
    cohorts = [Cohort(**r) for r in cohorts_rows]
    s_map: dict[int, list[Session]] = {}
    for sr in sessions_rows:
        s_map.setdefault(int(sr["module_id"]), []).append(Session(**sr))
    modules = []
    for m in modules_rows:
        m_payload = {**m, "sessions": s_map.get(int(m["id"]), [])}
        modules.append(Module(**m_payload))
    series = Series(**series_row)
    return SeriesDetailResponse(series=series, cohorts=cohorts, modules=modules)


def _assemble_tree(series_row: dict, cohorts_rows: list[dict], modules_rows: list[dict], sessions_rows: list[dict]) -> SeriesTreeResponse:
    detail = _assemble_detail(series_row, cohorts_rows, modules_rows, sessions_rows)
    total_hours = sum((float(m.total_hours or 0) for m in detail.modules), 0.0)
    total_sessions = sum((len(m.sessions) for m in detail.modules), 0)
    from decimal import Decimal
    return SeriesTreeResponse(
        series=detail.series,
        cohorts=detail.cohorts,
        modules=detail.modules,
        summary_total_sessions=total_sessions,
        summary_total_hours=Decimal(str(total_hours)),
    )


# ============================================================
# 内部工具：字段 diff → 生成 SET 子句
# ============================================================
def _build_set_clause(patch: dict) -> tuple[str, list]:
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


def _model_dump(model) -> dict:
    # Pydantic v2 统一：用 model_dump，Enum 取 value
    return model.model_dump(mode="json", exclude_none=False)


# ============================================================
# 1. 系列 CRUD
# ============================================================
async def list_series_admin(
    subject_code: Optional[str] = None,
    level_code: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> SeriesListResponse:
    """管理员版本：不限 sale_status（下架语义用 sale_status 表达；series 表无 yn 列，不做 yn 过滤）。"""
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    where = ["1=1"]
    params: list = []
    if subject_code:
        where.append("s.subject_code = %s")
        params.append(subject_code)
    if level_code:
        where.append("s.level_code = %s")
        params.append(level_code)
    if keyword:
        where.append("(s.series_name LIKE %s OR s.series_code LIKE %s OR s.description LIKE %s)")
        like = f"%{keyword}%"
        params.extend([like, like, like])

    where_sql = " AND ".join(where)

    count_sql = f"SELECT COUNT(*) AS total FROM curriculum_series s WHERE {where_sql}"
    total = int((await fetch_one(count_sql, params) or {"total": 0})["total"])

    list_sql = f"""
        SELECT
            s.*,
            (SELECT COUNT(*) FROM curriculum_cohort c WHERE c.series_id = s.id AND c.yn = 1) AS cohort_count,
            IFNULL((SELECT COUNT(*) FROM curriculum_module m
                     JOIN curriculum_session ss ON ss.module_id = m.id AND ss.yn = 1
                    WHERE m.series_id = s.id AND m.yn = 1), 0) AS total_session_count
        FROM curriculum_series s
        WHERE {where_sql}
        ORDER BY s.sort_no ASC, s.id DESC
        LIMIT {page_size} OFFSET {offset}
    """
    rows = await fetch_all(list_sql, params)
    items: list[SeriesListItem] = []
    for row in rows:
        series_patch = {k: row[k] for k in row if k not in ("cohort_count", "total_session_count")}
        series = Series(**series_patch)
        items.append(SeriesListItem(
            **series.model_dump(),
            cohort_count=int(row["cohort_count"] or 0),
            total_session_count=int(row["total_session_count"] or 0),
        ))
    return SeriesListResponse(total=total, page=page, page_size=page_size, items=items)


async def get_series_admin(series_id: int) -> SeriesDetailResponse:
    series_sql = "SELECT * FROM curriculum_series WHERE id = %s LIMIT 1"
    series = await fetch_one(series_sql, (series_id,))
    if not series:
        raise BizError(40401, f"系列不存在 id={series_id}")
    cohorts = await fetch_all("SELECT * FROM curriculum_cohort WHERE series_id = %s ORDER BY id", (series_id,))
    modules_rows = await fetch_all(
        "SELECT * FROM curriculum_module WHERE series_id = %s AND yn = 1 ORDER BY stage_no, id",
        (series_id,),
    )
    module_ids = [m["id"] for m in modules_rows]
    if module_ids:
        sessions_rows = await fetch_all(
            f"SELECT * FROM curriculum_session WHERE module_id IN ({','.join(['%s']*len(module_ids))}) AND yn = 1 ORDER BY module_id, session_no",
            tuple(module_ids),
        )
    else:
        sessions_rows = []
    return _assemble_detail(series, cohorts, modules_rows, sessions_rows)


async def get_series_tree_admin(series_id: int) -> SeriesTreeResponse:
    detail = await get_series_admin(series_id)
    cohorts_rows = [c.model_dump(mode="json") for c in detail.cohorts]
    modules_rows: list[dict] = []
    sessions_rows: list[dict] = []
    for m in detail.modules:
        md = m.model_dump(mode="json")
        sessions = md.pop("sessions", [])
        modules_rows.append(md)
        for s in sessions:
            s["module_id"] = m.id
            sessions_rows.append(s)
    return _assemble_tree(
        detail.series.model_dump(mode="json"),
        cohorts_rows,
        modules_rows,
        sessions_rows,
    )


async def create_series(payload: SeriesAdminCreate, created_by: int) -> int:
    exists = await fetch_one("SELECT id FROM curriculum_series WHERE series_code = %s LIMIT 1", (payload.series_code,))
    if exists:
        raise BizError(40901, f"系列编码已存在: {payload.series_code}")
    sql = """
        INSERT INTO curriculum_series
        (series_code, series_name, subject_code, level_code, level_name, description,
         cover_url, target_hours, sale_status, sort_no, created_by, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
    """
    d = _model_dump(payload)
    return int(await execute_write(sql, (
        d["series_code"], d["series_name"], d["subject_code"], d["level_code"], d["level_name"],
        d.get("description"), d.get("cover_url"), d["target_hours"], d["sale_status"],
        d["sort_no"], created_by,
    )))


async def update_series(series_id: int, payload: SeriesAdminUpdate) -> None:
    exists = await fetch_one("SELECT id FROM curriculum_series WHERE id = %s LIMIT 1", (series_id,))
    if not exists:
        raise BizError(40401, f"系列不存在 id={series_id}")
    d = _model_dump(payload)
    set_sql, params = _build_set_clause(d)
    params.append(series_id)
    await execute_write(f"UPDATE curriculum_series {set_sql}, updated_at = NOW() WHERE id = %s", tuple(params))


# ============================================================
# 2. 班次 CRUD
# ============================================================
async def create_cohort(payload: CohortAdminCreate) -> int:
    exists = await fetch_one("SELECT id FROM curriculum_series WHERE id = %s LIMIT 1", (payload.series_id,))
    if not exists:
        raise BizError(40401, f"系列不存在 id={payload.series_id}")
    code_hit = await fetch_one("SELECT id FROM curriculum_cohort WHERE cohort_code = %s LIMIT 1", (payload.cohort_code,))
    if code_hit:
        raise BizError(40901, f"班次编码已存在: {payload.cohort_code}")
    d = _model_dump(payload)
    sql = """
        INSERT INTO curriculum_cohort
        (series_id, cohort_code, cohort_name, start_date, end_date, max_student_count,
         current_student_count, sale_price, yn, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,0,%s,%s,NOW(),NOW())
    """
    return int(await execute_write(sql, (
        d["series_id"], d["cohort_code"], d["cohort_name"], d.get("start_date"), d.get("end_date"),
        d["max_student_count"], d["sale_price"], d["yn"],
    )))


async def update_cohort(cohort_id: int, payload: CohortAdminUpdate) -> None:
    exists = await fetch_one("SELECT id FROM curriculum_cohort WHERE id = %s LIMIT 1", (cohort_id,))
    if not exists:
        raise BizError(40401, f"班次不存在 id={cohort_id}")
    d = _model_dump(payload)
    set_sql, params = _build_set_clause(d)
    params.append(cohort_id)
    await execute_write(f"UPDATE curriculum_cohort {set_sql}, updated_at = NOW() WHERE id = %s", tuple(params))


async def delete_cohort(cohort_id: int) -> None:
    n = await execute_write("UPDATE curriculum_cohort SET yn = 0, updated_at = NOW() WHERE id = %s", (cohort_id,))
    if n == 0:
        raise BizError(40401, f"班次不存在 id={cohort_id}")


async def list_cohorts_admin(series_id: Optional[int] = None) -> list[Cohort]:
    sql = "SELECT * FROM curriculum_cohort WHERE 1=1"
    params: tuple = ()
    if series_id is not None:
        sql += " AND series_id = %s"
        params = (series_id,)
    sql += " ORDER BY id DESC"
    rows = await fetch_all(sql, params)
    return [Cohort(**r) for r in rows]


# ============================================================
# 3. 模块 CRUD
# ============================================================
async def create_module(payload: ModuleAdminCreate) -> int:
    exists = await fetch_one("SELECT id FROM curriculum_series WHERE id = %s LIMIT 1", (payload.series_id,))
    if not exists:
        raise BizError(40401, f"系列不存在 id={payload.series_id}")
    d = _model_dump(payload)
    sql = """
        INSERT INTO curriculum_module
        (series_id, module_code, module_name, stage_no, description, lesson_count, total_hours, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
    """
    return int(await execute_write(sql, (
        d["series_id"], d["module_code"], d["module_name"], d["stage_no"],
        d.get("description"), d["lesson_count"], d["total_hours"],
    )))


async def update_module(module_id: int, payload: ModuleAdminUpdate) -> None:
    exists = await fetch_one("SELECT id FROM curriculum_module WHERE id = %s LIMIT 1", (module_id,))
    if not exists:
        raise BizError(40401, f"模块不存在 id={module_id}")
    d = _model_dump(payload)
    set_sql, params = _build_set_clause(d)
    params.append(module_id)
    await execute_write(f"UPDATE curriculum_module {set_sql}, updated_at = NOW() WHERE id = %s", tuple(params))


async def delete_module(module_id: int) -> None:
    """软删模块：级联软删其下全部课次（yn=0），并解除这些课次绑定的视频资产，避免孤儿资产（红线 2 / 对抗 #3）。"""
    async with transaction() as (conn, cur):
        # 1) 解除该模块下所有课次绑定的视频资产（session_id → NULL），消除「指向不存在课次」的幽灵数据
        await cur.execute(
            "UPDATE admin_course_video_asset SET session_id = NULL "
            "WHERE session_id IN (SELECT id FROM curriculum_session WHERE module_id = %s)",
            (module_id,),
        )
        # 2) 级联软删课次（禁止物理 DELETE）
        await cur.execute(
            "UPDATE curriculum_session SET yn = 0, updated_at = NOW() WHERE module_id = %s",
            (module_id,),
        )
        # 3) 软删模块本身
        n = await cur.execute(
            "UPDATE curriculum_module SET yn = 0, updated_at = NOW() WHERE id = %s",
            (module_id,),
        )
    if n == 0:
        raise BizError(40401, f"模块不存在 id={module_id}")


async def list_modules_admin(series_id: Optional[int] = None) -> list[Module]:
    sql = "SELECT * FROM curriculum_module WHERE yn = 1"
    params: tuple = ()
    if series_id is not None:
        sql += " AND series_id = %s"
        params = (series_id,)
    sql += " ORDER BY stage_no, id"
    rows = await fetch_all(sql, params)
    # 不附带 sessions（模块列表接口不带子树）
    return [Module(**{**r, "sessions": []}) for r in rows]


# ============================================================
# 4. 课次 CRUD
# ============================================================
async def create_session(payload: SessionAdminCreate) -> int:
    exists = await fetch_one("SELECT id FROM curriculum_module WHERE id = %s LIMIT 1", (payload.module_id,))
    if not exists:
        raise BizError(40401, f"模块不存在 id={payload.module_id}")
    d = _model_dump(payload)
    sql = """
        INSERT INTO curriculum_session
        (module_id, session_no, session_title, description, teaching_status,
         teaching_date, duration_minutes, video_url, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
    """
    return int(await execute_write(sql, (
        d["module_id"], d["session_no"], d["session_title"], d.get("description"),
        d["teaching_status"], d.get("teaching_date"), d["duration_minutes"], d.get("video_url"),
    )))


async def update_session(session_id: int, payload: SessionAdminUpdate) -> None:
    exists = await fetch_one("SELECT id FROM curriculum_session WHERE id = %s LIMIT 1", (session_id,))
    if not exists:
        raise BizError(40401, f"课次不存在 id={session_id}")
    d = _model_dump(payload)
    set_sql, params = _build_set_clause(d)
    params.append(session_id)
    await execute_write(f"UPDATE curriculum_session {set_sql}, updated_at = NOW() WHERE id = %s", tuple(params))


async def delete_session(session_id: int) -> None:
    """软删课次（yn=0）：先解除其绑定的视频资产（session_id → NULL），避免孤儿资产（红线 2 / 对抗 #3）。"""
    async with transaction() as (conn, cur):
        await cur.execute(
            "UPDATE admin_course_video_asset SET session_id = NULL WHERE session_id = %s",
            (session_id,),
        )
        n = await cur.execute(
            "UPDATE curriculum_session SET yn = 0, updated_at = NOW() WHERE id = %s",
            (session_id,),
        )
    if n == 0:
        raise BizError(40401, f"课次不存在 id={session_id}")


async def list_sessions_admin(module_id: Optional[int] = None) -> list[Session]:
    sql = "SELECT * FROM curriculum_session WHERE yn = 1"
    params: tuple = ()
    if module_id is not None:
        sql += " AND module_id = %s"
        params = (module_id,)
    sql += " ORDER BY module_id, session_no"
    return [Session(**r) for r in (await fetch_all(sql, params))]


# ============================================================
# 5. 视频资产（占位上传）
# ============================================================
_VIDEO_BUCKET = None


def _ensure_bucket_name() -> str:
    return settings.MINIO_BUCKET_COURSE


async def init_video_upload(req: VideoUploadInitRequest, created_by: int) -> VideoUploadInitResponse:
    asset_id = f"V{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
    suffix = (req.origin_file_name or "mp4").split(".")[-1] or "mp4"
    object_key = f"course/videos/{datetime.now().strftime('%Y/%m/%d')}/{uuid.uuid4().hex}.{suffix}"
    bucket = _ensure_bucket_name()

    async with transaction() as (conn, cur):
        await cur.execute(
            """
            INSERT INTO admin_course_video_asset
            (asset_id, session_id, asset_title, origin_file_name, object_key, bucket_name,
             file_size, duration_seconds, transcode_status, transcode_message, content_hash,
             created_by, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s,NOW(),NOW())
            """,
            (
                asset_id, req.bind_session_id,
                req.asset_title or req.origin_file_name,
                req.origin_file_name, object_key, bucket,
                req.file_size, req.duration_seconds,
                None, req.content_hash, created_by,
            ),
        )

    expires_at = datetime.now() + timedelta(minutes=30)
    return VideoUploadInitResponse(
        asset_id=asset_id,
        upload_type="direct_form_post",
        upload_url="/api/admin/courses/videos/_dev_direct_put",
        form_fields={
            "key": object_key,
            "bucket": bucket,
            "Content-Type": "video/mp4",
            "x-amz-meta-asset-id": asset_id,
            "policy_placeholder": "占位模式：直接调用 finalize 接口即可置 ready",
        },
        transcode_status_tip="当前占位：无需 ffmpeg，执行 Finalize 即置 ready",
        expires_at=expires_at,
        bind_session_id=req.bind_session_id,
    )


async def finalize_video_upload(req: VideoUploadFinalizeRequest) -> VideoAsset:
    row = await fetch_one("SELECT * FROM admin_course_video_asset WHERE asset_id = %s FOR UPDATE", (req.asset_id,))
    if not row:
        raise BizError(40401, f"视频资产不存在 asset_id={req.asset_id}")
    if req.transcode_error:
        new_status = "failed"
        new_msg = req.transcode_error
        play_720 = None
        play_1080 = None
        final_dur = int(row["duration_seconds"] or 0)
    else:
        new_status = "ready"
        new_msg = "占位转码完成"
        play_720 = req.play_720_url or f"https://cdn.placeholder.local/720/{row['asset_id']}.mp4"
        play_1080 = req.play_1080_url or f"https://cdn.placeholder.local/1080/{row['asset_id']}.mp4"
        final_dur = req.final_duration_seconds or int(row["duration_seconds"] or 0)
    updates = {
        "transcode_status": new_status,
        "transcode_message": new_msg,
        "play_720_url": play_720,
        "play_1080_url": play_1080,
        "duration_seconds": final_dur,
    }
    if req.object_key:
        updates["object_key"] = req.object_key
    set_sql, params = _build_set_clause(updates)
    params.append(row["id"])
    await execute_write(f"UPDATE admin_course_video_asset {set_sql}, updated_at = NOW() WHERE id = %s", tuple(params))
    # 如果之前就绑了 session，同步写 curriculum_session.video_url
    updated = await fetch_one("SELECT * FROM admin_course_video_asset WHERE id = %s", (row["id"],))
    if new_status == "ready" and updated and updated.get("session_id"):
        await execute_write(
            "UPDATE curriculum_session SET video_url = %s, updated_at = NOW() WHERE id = %s",
            (play_720, int(updated["session_id"])),
        )
    return VideoAsset(**updated)


async def bind_video_to_session(req: BindVideoToSessionRequest) -> VideoAsset:
    row = await fetch_one("SELECT * FROM admin_course_video_asset WHERE asset_id = %s", (req.asset_id,))
    if not row:
        raise BizError(40401, f"视频资产不存在 asset_id={req.asset_id}")
    session = await fetch_one("SELECT id FROM curriculum_session WHERE id = %s AND yn = 1 LIMIT 1", (req.session_id,))
    if not session:
        raise BizError(40401, f"课次不存在 session_id={req.session_id}")
    await execute_write(
        "UPDATE admin_course_video_asset SET session_id = %s, updated_at = NOW() WHERE asset_id = %s",
        (req.session_id, req.asset_id),
    )
    # 如果视频已 ready 就同步更新 session.video_url
    if row["transcode_status"] == "ready" and row.get("play_720_url"):
        await execute_write(
            "UPDATE curriculum_session SET video_url = %s, updated_at = NOW() WHERE id = %s",
            (row["play_720_url"], req.session_id),
        )
    updated = await fetch_one("SELECT * FROM admin_course_video_asset WHERE asset_id = %s", (req.asset_id,))
    return VideoAsset(**updated)


async def list_video_assets(session_id: Optional[int] = None, status: Optional[str] = None, page: int = 1, page_size: int = 20) -> tuple[int, list[VideoAsset]]:
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size
    where = ["1=1"]
    params: list = []
    if session_id is not None:
        where.append("session_id = %s")
        params.append(session_id)
    if status:
        where.append("transcode_status = %s")
        params.append(status)
    where_sql = " AND ".join(where)
    total_row = await fetch_one(f"SELECT COUNT(*) c FROM admin_course_video_asset WHERE {where_sql}", tuple(params))
    total = int(total_row["c"] if total_row else 0)
    rows = await fetch_all(
        f"SELECT * FROM admin_course_video_asset WHERE {where_sql} ORDER BY id DESC LIMIT %s OFFSET %s",
        tuple(params + [page_size, offset]),
    )
    return total, [VideoAsset(**r) for r in rows]


# ============================================================
# 6. 课件：重定向到 P1 知识库上传
# ============================================================
async def redirect_material_to_p1_upload() -> MaterialRedirectResponse:
    return MaterialRedirectResponse(
        redirect_endpoint="/api/knowledge/upload",
        method="POST",
        auth_header_required=True,
        supported_content_types=["application/pdf", "application/vnd.ms-powerpoint",
                                 "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                 "application/msword",
                                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
        tip="走 P1 知识库导入管道：上传后 knowledge_chunk 已入库，管理端仅做 307 跳转指引。",
    )
