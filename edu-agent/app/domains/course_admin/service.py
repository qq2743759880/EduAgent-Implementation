"""
课程管理端服务层（task12）。

职责：
- 四级 CRUD 业务编排（series→cohort→module→session）
- 状态机守卫：sale_status / transcode_status / review_status
- 唯一约束检测 → AppException(409xx) 而非 500
- 软删级联：系列 off_sale → 子级 yn=0 传播（可选保留）
- 分片上传状态机：init → finalize → bind → transcode_poll
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from app.common.error_codes import (
    CHAPTER_NO_CONFLICT,
    COHORT_CODE_CONFLICT,
    MODULE_STAGE_CONFLICT,
    SESSION_NO_CONFLICT,
    SERIES_CODE_CONFLICT,
    VIDEO_CODE_CONFLICT,
)
from app.common.exceptions import AppException, ConflictError, NotFoundError
from app.core.cache import invalidate
from app.common.logging import logger
from app.domains.course_admin.repository import (
    AssetAdminRepo,
    CohortAdminRepo,
    ModuleAdminRepo,
    SeriesAdminRepo,
    SessionAdminRepo,
    VideoAdminRepo,
)
from app.domains.course_admin.schemas import (
    CohortCreateAdmin,
    CohortResponseAdmin,
    CohortUpdateAdmin,
    ModuleCreateAdmin,
    ModuleResponseAdmin,
    ModuleUpdateAdmin,
    PageMeta,
    SeriesCreateAdmin,
    SeriesResponseAdmin,
    SeriesUpdateAdmin,
    SessionCreateAdmin,
    SessionResponseAdmin,
    SessionUpdateAdmin,
)

_series_repo = SeriesAdminRepo()
_cohort_repo = CohortAdminRepo()
_module_repo = ModuleAdminRepo()
_session_repo = SessionAdminRepo()
_asset_repo = AssetAdminRepo()
_video_repo = VideoAdminRepo()


def _fix_time_columns(row: dict) -> dict:
    """asyncmy 将 MySQL TIME 列返回为 timedelta → 转 datetime.time（复用 task11 同款逻辑）。"""
    for col in ("start_time", "end_time"):
        val = row.get(col)
        if isinstance(val, timedelta):
            row[col] = (datetime.min + val).time()
    return row


def _parse_json_columns(row: dict) -> dict:
    """series 表 JSON 列（asyncmy 返回 str）→ list，对齐 task11 用户端处理。"""
    for col in ("target_learner_identity_codes", "target_learning_goal_codes", "target_grade_codes"):
        val = row.get(col)
        if isinstance(val, str):
            try:
                row[col] = json.loads(val)
            except (ValueError, TypeError):
                row[col] = None
    return row


def _build_page_meta(page: int, page_size: int, total: int) -> PageMeta:
    total_pages = math.ceil(total / page_size) if page_size > 0 else 0
    return PageMeta(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        has_more=page < total_pages,
    )


# ═══════════════════════════════════════════
# Series（系列）
# ═══════════════════════════════════════════

async def create_series(data: SeriesCreateAdmin) -> SeriesResponseAdmin:
    """创建系列。唯一约束：institution_id + series_code。"""
    existing = await _series_repo.get_by_code(data.institution_id, data.series_code)
    if existing:
        raise ConflictError(
            f"系列编码 '{data.series_code}' 已存在",
            code=SERIES_CODE_CONFLICT,
        )
    new_id = await _series_repo.insert(data.model_dump(exclude_unset=True))
    row = await _series_repo.get_by_id(new_id)
    if not row:
        raise AppException("50000", "创建系列后查询失败")
    return SeriesResponseAdmin(**_parse_json_columns(dict(row)))


async def update_series(series_id: int, data: SeriesUpdateAdmin) -> SeriesResponseAdmin:
    row = await _series_repo.get_by_id(series_id)
    if not row:
        raise NotFoundError("系列", str(series_id))
    await _series_repo.update(series_id, data.model_dump(exclude_unset=True, exclude_none=True))
    updated = await _series_repo.get_by_id(series_id)
    # task23 写后精确 DEL：课程详情缓存 key 失效（GWT②，sale_status/字段变更 1s 内新值可见）
    await invalidate(f"course:series:detail:{series_id}")
    return SeriesResponseAdmin(**_parse_json_columns(dict(updated)))


async def delete_series(series_id: int) -> None:
    """软删系列：sale_status = 'off_sale'（表无 yn 列）。"""
    row = await _series_repo.get_by_id(series_id)
    if not row:
        raise NotFoundError("系列", str(series_id))
    await _series_repo.off_sale(series_id)
    await invalidate(f"course:series:detail:{series_id}")


async def list_series_admin(
    *, keyword: Optional[str] = None, institution_id: Optional[int] = None,
    delivery_mode: Optional[str] = None, sale_status: Optional[str] = None,
    sort: str = "default", page: int = 1, page_size: int = 20,
) -> dict:
    rows, total = await _series_repo.list_series(
        keyword=keyword, institution_id=institution_id,
        delivery_mode=delivery_mode, sale_status=sale_status,
        sort=sort, page=page, page_size=page_size,
    )
    items = [SeriesResponseAdmin(**_parse_json_columns(dict(r))) for r in rows]
    return {"items": items, "page_meta": _build_page_meta(page, page_size, total)}


async def get_series_admin(series_id: int) -> SeriesResponseAdmin:
    row = await _series_repo.get_by_id(series_id)
    if not row:
        raise NotFoundError("系列", str(series_id))
    return SeriesResponseAdmin(**_parse_json_columns(dict(row)))


# ═══════════════════════════════════════════
# Cohort（班次）
# ═══════════════════════════════════════════

async def create_cohort(data: CohortCreateAdmin) -> CohortResponseAdmin:
    existing = await _cohort_repo.get_by_code(data.institution_id, data.cohort_code)
    if existing:
        raise ConflictError(
            f"班次编码 '{data.cohort_code}' 已存在",
            code=COHORT_CODE_CONFLICT,
        )
    new_id = await _cohort_repo.insert(data.model_dump(exclude_unset=True))
    row = await _cohort_repo.get_by_id(new_id)
    if not row:
        raise AppException("50000", "创建班次后查询失败")
    # task23 写后 DEL：新建班次影响 series:detail 的 cohort_count/价格
    await invalidate(f"course:series:detail:{row['series_id']}")
    return CohortResponseAdmin(**row)


async def update_cohort(cohort_id: int, data: CohortUpdateAdmin) -> CohortResponseAdmin:
    row = await _cohort_repo.get_by_id(cohort_id)
    if not row:
        raise NotFoundError("班次", str(cohort_id))
    await _cohort_repo.update(cohort_id, data.model_dump(exclude_unset=True, exclude_none=True))
    updated = await _cohort_repo.get_by_id(cohort_id)
    # task23 写后精确 DEL：班次详情 + 余位 + 系列详情聚合价/班次数失效（GWT②，D1 补）
    await invalidate(f"course:cohort:detail:{cohort_id}", f"course:cohort:seats:{cohort_id}",
                     f"course:series:detail:{row['series_id']}")
    return CohortResponseAdmin(**updated)


async def delete_cohort(cohort_id: int) -> None:
    """软删班次：yn = 0。"""
    row = await _cohort_repo.get_by_id(cohort_id)
    if not row:
        raise NotFoundError("班次", str(cohort_id))
    await _cohort_repo.soft_delete(cohort_id)
    # task23 写后精确 DEL：软删班次改 cohort_count/价格 → 连带失效 series:detail 聚合（R1 补）
    await invalidate(f"course:cohort:detail:{cohort_id}", f"course:cohort:seats:{cohort_id}",
                     f"course:series:detail:{row['series_id']}")


async def list_cohorts_by_series(series_id: int) -> list[CohortResponseAdmin]:
    rows = await _cohort_repo.list_by_series(series_id)
    return [CohortResponseAdmin(**r) for r in rows]


async def get_cohort_admin(cohort_id: int) -> CohortResponseAdmin:
    row = await _cohort_repo.get_by_id(cohort_id)
    if not row:
        raise NotFoundError("班次", str(cohort_id))
    return CohortResponseAdmin(**row)


# ═══════════════════════════════════════════
# Module（模块）
# ═══════════════════════════════════════════

async def create_module(data: ModuleCreateAdmin) -> ModuleResponseAdmin:
    """创建模块。唯一约束：cohort_id + stage_no。"""
    existing = await _module_repo.get_by_stage(data.cohort_id, data.stage_no)
    if existing:
        raise ConflictError(
            f"班次 {data.cohort_id} 阶段号 {data.stage_no} 已存在",
            code=MODULE_STAGE_CONFLICT,
        )
    new_id = await _module_repo.insert(data.model_dump(exclude_unset=True))
    row = await _module_repo.get_by_id(new_id)
    if not row:
        raise AppException("50000", "创建模块后查询失败")
    return ModuleResponseAdmin(**row)


async def update_module(module_id: int, data: ModuleUpdateAdmin) -> ModuleResponseAdmin:
    row = await _module_repo.get_by_id(module_id)
    if not row:
        raise NotFoundError("模块", str(module_id))
    if data.stage_no is not None and data.stage_no != row["stage_no"]:
        existing = await _module_repo.get_by_stage(row["cohort_id"], data.stage_no)
        if existing:
            raise ConflictError(
                f"阶段号 {data.stage_no} 已存在",
                code=MODULE_STAGE_CONFLICT,
            )
    await _module_repo.update(module_id, data.model_dump(exclude_unset=True, exclude_none=True))
    updated = await _module_repo.get_by_id(module_id)
    return ModuleResponseAdmin(**updated)


async def delete_module(module_id: int) -> None:
    """物理删除模块（series_cohort_course 无 yn 列，edu.sql 权威结构）。"""
    row = await _module_repo.get_by_id(module_id)
    if not row:
        raise NotFoundError("模块", str(module_id))
    await _module_repo.hard_delete(module_id)
    # task23 写后 DEL：删除模块同样失效 cohort:detail 模块列表
    await invalidate(f"course:cohort:detail:{row['cohort_id']}")


async def list_modules_by_cohort(cohort_id: int) -> list[ModuleResponseAdmin]:
    rows = await _module_repo.list_by_cohort(cohort_id)
    return [ModuleResponseAdmin(**r) for r in rows]


async def get_module_admin(module_id: int) -> ModuleResponseAdmin:
    row = await _module_repo.get_by_id(module_id)
    if not row:
        raise NotFoundError("模块", str(module_id))
    return ModuleResponseAdmin(**row)


# ═══════════════════════════════════════════
# Session（课次）
# ═══════════════════════════════════════════

async def create_session(data: SessionCreateAdmin) -> SessionResponseAdmin:
    existing = await _session_repo.get_by_session_no(
        data.series_cohort_course_id, data.session_no,
    )
    if existing:
        raise ConflictError(
            f"模块 {data.series_cohort_course_id} 课次号 {data.session_no} 已存在",
            code=SESSION_NO_CONFLICT,
        )
    new_id = await _session_repo.insert(data.model_dump(exclude_unset=True))
    row = await _session_repo.get_by_id(new_id)
    if not row:
        raise AppException("50000", "创建课次后查询失败")
    return SessionResponseAdmin(**_fix_time_columns(dict(row)))


async def update_session(session_id: int, data: SessionUpdateAdmin) -> SessionResponseAdmin:
    row = await _session_repo.get_by_id(session_id)
    if not row:
        raise NotFoundError("课次", str(session_id))
    await _session_repo.update(session_id, data.model_dump(exclude_unset=True, exclude_none=True))
    updated = await _session_repo.get_by_id(session_id)
    return SessionResponseAdmin(**_fix_time_columns(dict(updated)))


async def delete_session(session_id: int) -> None:
    """物理删除课次（series_cohort_session 无 yn 列，teaching_status 非软删标记）。"""
    row = await _session_repo.get_by_id(session_id)
    if not row:
        raise NotFoundError("课次", str(session_id))
    await _session_repo.hard_delete(session_id)


async def list_sessions_by_module(module_id: int) -> list[SessionResponseAdmin]:
    rows = await _session_repo.list_by_module(module_id)
    return [SessionResponseAdmin(**_fix_time_columns(dict(r))) for r in rows]


async def list_sessions_by_cohort(cohort_id: int) -> list[SessionResponseAdmin]:
    """班次下全部课次（经 cohort→modules→sessions，task12-fix 批判② 补全）。"""
    rows = await _session_repo.list_by_cohort(cohort_id)
    return [SessionResponseAdmin(**_fix_time_columns(dict(r))) for r in rows]


async def get_session_admin(session_id: int) -> SessionResponseAdmin:
    row = await _session_repo.get_by_id(session_id)
    if not row:
        raise NotFoundError("课次", str(session_id))
    return SessionResponseAdmin(**_fix_time_columns(dict(row)))


# ═══════════════════════════════════════════
# 视频 + 分片上传（标准占位实现，task13 细化）
# ═══════════════════════════════════════════

async def init_chunked_upload(session_id: int, file_name: str, file_size: int, chunk_count: int) -> dict:
    """分片上传初始化占位。返回模拟 upload_id 和策略信息。"""
    upload_id = f"chunk_{uuid.uuid4().hex[:16]}"
    chunk_size = max(1, file_size // max(chunk_count, 1))
    return {
        "upload_id": upload_id,
        "chunk_size": chunk_size,
        "upload_urls": [],
        "strategy": "local_fallback",
    }


async def finalize_chunked_upload(upload_id: str) -> dict:
    """分片上传完成占位。返回模拟 asset_id 和 video_id。"""
    logger.info(f"finalize_chunked_upload called with upload_id={upload_id}")
    return {
        "upload_id": upload_id,
        "asset_id": 0,
        "video_id": 0,
        "transcode_status": "pending",
    }


async def bind_video_to_session(session_id: int, video_id: int, sort_no: int = 0) -> dict:
    """绑定视频到课次占位。返回绑定确认。"""
    logger.info(f"bind_video_to_session: session_id={session_id}, video_id={video_id}, sort_no={sort_no}")
    return {
        "session_id": session_id,
        "video_id": video_id,
        "sort_no": sort_no,
        "bound": True,
    }


async def get_transcode_status(video_id: int) -> dict:
    """转码状态查询占位。从 video_repo 读取真实记录。"""
    row = await _video_repo.get_transcode_status(video_id)
    if not row:
        raise NotFoundError("视频", str(video_id))
    return {
        "video_id": row["id"],
        "transcode_status": row["transcode_status"],
        "review_status": row["review_status"],
    }