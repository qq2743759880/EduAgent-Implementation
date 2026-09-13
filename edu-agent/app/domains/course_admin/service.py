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

import asyncio
import json
import re
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from app.common.error_codes import (
    CHAPTER_NO_CONFLICT,
    COHORT_CODE_CONFLICT,
    MODULE_STAGE_CONFLICT,
    NOT_FOUND,
    SESSION_NO_CONFLICT,
    SERIES_CODE_CONFLICT,
    SERIES_IN_USE,
    VALIDATION,
    VIDEO_CODE_CONFLICT,
)
from app.config import settings
from app.common.exceptions import AppException, ConflictError, NotFoundError
from app.core.cache import invalidate
from app.common.logging import logger
from app.domains.course_admin.repository import (
    AssetAdminRepo,
    ChapterAdminRepo,
    CohortAdminRepo,
    ModuleAdminRepo,
    SeriesAdminRepo,
    SessionAdminRepo,
    VideoAdminRepo,
)
from app.domains.course_admin.schemas import (
    ChapterCreateAdmin,
    ChapterResponseAdmin,
    ChapterUpdateAdmin,
    CohortCreateAdmin,
    CohortResponseAdmin,
    CohortUpdateAdmin,
    ModuleCreateAdmin,
    ModuleResponseAdmin,
    ModuleUpdateAdmin,
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
_chapter_repo = ChapterAdminRepo()


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


async def delete_series(series_id: int, hard: bool = False) -> None:
    """删除系列。

    - hard=False（默认）：软删下架 → sale_status='off_sale'。series 表无 yn 列，
      下架语义由 sale_status 状态机表达（与前端「下架」文案一致，消除假删除缺陷）。
    - hard=True：仅由路由层在 ADMIN 角色下放行；先做外键引用校验，
      若存在活动班次或订单引用则抛 409（SERIES_IN_USE），绝不静默；
      仅当零引用时物理删除整行。
    """
    row = await _series_repo.get_by_id(series_id)
    if not row:
        raise NotFoundError("系列", str(series_id))
    if hard:
        refs = await _series_repo.count_references(series_id)
        if refs["total"] > 0:
            raise ConflictError(
                f"系列仍被 {refs['cohorts']} 个班次（含已下架）、{refs['orders']} 笔订单引用，无法彻底删除",
                code=SERIES_IN_USE,
            )
        try:
            await _series_repo.physical_delete(series_id)
        except Exception as e:  # 兜底：分类关联/收藏等其它残留外键导致删除失败，绝不静默为 500
            raise ConflictError(
                f"系列仍存在其它关联记录，无法彻底删除：{e}",
                code=SERIES_IN_USE,
            )
    else:
        await _series_repo.off_sale(series_id)
    await invalidate(f"course:series:detail:{series_id}")


async def restore_series(series_id: int) -> dict:
    """从回收站恢复已下架系列（C5：软删三态闭环中的"回收站恢复"最小闭环）。

    - 仅恢复 sale_status='off_sale'（软删下架）的系列 → sale_status='draft'（草稿，管理员可再次上架）。
      series 表无 yn 列（下架由 sale_status 状态机表达），故无 yn 字段可置回。
    - 系列不存在 / 未处于软删态 → 404（NotFoundError 保持业务 message）。
    - 恢复时 series_code 已被其它系列占用（institution_id + series_code 唯一性）→ 409（SERIES_CODE_CONFLICT）。
    - 仅针对软删态系列；不影响原 DELETE 的 ?hard=true 真删语义（真删无法恢复，本就不可达本端点）。
    """
    row = await _series_repo.get_by_id(series_id)
    if not row:
        raise NotFoundError("系列", str(series_id))
    if row["sale_status"] != "off_sale":
        raise AppException(
            NOT_FOUND,
            f"系列 {series_id} 未处于回收站（已下架）状态，无法恢复",
        )
    existing = await _series_repo.get_by_code(row["institution_id"], row["series_code"])
    if existing and existing["id"] != series_id:
        raise ConflictError(
            f"系列编码 '{row['series_code']}' 已被其它系列占用，无法恢复",
            code=SERIES_CODE_CONFLICT,
        )
    await _series_repo.restore(series_id)
    await invalidate(f"course:series:detail:{series_id}")
    return {"series_id": series_id, "status": "restored"}


async def list_series_admin(
    *, keyword: Optional[str] = None, institution_id: Optional[int] = None,
    delivery_mode: Optional[str] = None, sale_status: Optional[str] = None,
    sort: str = "default", page: int = 1, page_size: int = 20,
    include_deleted: bool = False,
) -> dict:
    rows, total = await _series_repo.list_series(
        keyword=keyword, institution_id=institution_id,
        delivery_mode=delivery_mode, sale_status=sale_status,
        sort=sort, page=page, page_size=page_size,
        include_deleted=include_deleted,
    )
    items = [SeriesResponseAdmin(**_parse_json_columns(dict(r))) for r in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


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
    """物理删除模块（series_cohort_course 无 yn 列，edu.sql 权威结构）。

    - 前置引用校验（C-C 删除语义，对齐 series hard delete 40908）：模块仍存在
      课次（series_cohort_session）→ 抛 40908，绝不级联删子数据、绝不静默 500。
    """
    row = await _module_repo.get_by_id(module_id)
    if not row:
        raise NotFoundError("模块", str(module_id))
    refs = await _module_repo.count_references(module_id)
    if refs["total"] > 0:
        raise ConflictError(
            f"模块仍被 {refs['sessions']} 个课次引用，无法删除",
            code=SERIES_IN_USE,
        )
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
    """物理删除课次（series_cohort_session 无 yn 列，teaching_status 非软删标记）。

    - 前置引用校验（C-C 删除语义，对齐 series hard delete 40908）：课次仍被任一
      子表引用（课件/考勤/考试/作业/授课老师/告警等）→ 抛 40908，绝不级联删、绝不静默 500。
    """
    row = await _session_repo.get_by_id(session_id)
    if not row:
        raise NotFoundError("课次", str(session_id))
    refs = await _session_repo.count_references(session_id)
    if refs["total"] > 0:
        raise ConflictError(
            f"课次仍被 {refs['total']} 条子记录引用，无法删除",
            code=SERIES_IN_USE,
        )
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
# Video Chapter（视频章节，P1-2 task57 gap 接线）
# ═══════════════════════════════════════════

async def create_chapter(data: ChapterCreateAdmin) -> ChapterResponseAdmin:
    """创建章节。唯一约束：video_id + chapter_no。"""
    existing = await _chapter_repo.get_by_chapter_no(data.video_id, data.chapter_no)
    if existing:
        raise ConflictError(
            f"视频 {data.video_id} 章节号 {data.chapter_no} 已存在",
            code=CHAPTER_NO_CONFLICT,
        )
    new_id = await _chapter_repo.insert(data.model_dump(exclude_unset=True))
    row = await _chapter_repo.get_by_chapter_no(data.video_id, data.chapter_no)
    if not row:
        raise AppException("50000", "创建章节后查询失败")
    return ChapterResponseAdmin(**row)


async def update_chapter(chapter_id: int, data: ChapterUpdateAdmin) -> ChapterResponseAdmin:
    row = await _chapter_repo.get_by_id(chapter_id)
    if not row:
        raise NotFoundError("章节", str(chapter_id))
    await _chapter_repo.update(chapter_id, data.model_dump(exclude_unset=True, exclude_none=True))
    updated = await _chapter_repo.get_by_id(chapter_id)
    return ChapterResponseAdmin(**updated)


async def delete_chapter(chapter_id: int) -> None:
    """物理删除章节（session_video_chapter 无 yn 列）。"""
    row = await _chapter_repo.get_by_id(chapter_id)
    if not row:
        raise NotFoundError("章节", str(chapter_id))
    await _chapter_repo.hard_delete(chapter_id)


async def list_chapters_by_video(video_id: int) -> list[ChapterResponseAdmin]:
    rows = await _chapter_repo.list_by_video(video_id)
    return [ChapterResponseAdmin(**r) for r in rows]


async def get_chapter_admin(chapter_id: int) -> ChapterResponseAdmin:
    row = await _chapter_repo.get_by_id(chapter_id)
    if not row:
        raise NotFoundError("章节", str(chapter_id))
    return ChapterResponseAdmin(**row)


# ═══════════════════════════════════════════
# 视频 + 分片上传（本地磁盘真实现）
# ponytail: 无转码管线（无 ffmpeg），transcode_status 直接落 completed；
#           文件按原样存储为可播 mp4/webm。接入 ffmpeg 后在 finalize 处替换。
# ═══════════════════════════════════════════

async def list_session_assets(session_id: int) -> list[dict]:
    """课次资源列表；material_category=video 的资源附带其 session_video 记录。"""
    session = await _session_repo.get_by_id(int(session_id))
    if not session:
        raise NotFoundError("课次", str(session_id))
    assets = await _asset_repo.list_by_session(int(session_id))
    out: list[dict] = []
    for a in assets:
        row = dict(a)
        if row.get("material_category") == "video":
            row["videos"] = await _video_repo.list_by_asset(int(row["id"]))
        out.append(row)
    return out


_VIDEO_EXT_WHITELIST = {".mp4": "video/mp4", ".mov": "video/quicktime", ".m4v": "video/x-m4v",
                        ".webm": "video/webm", ".mkv": "video/x-matroska"}
_MAX_CHUNK_COUNT = 10000


def _video_media_root() -> Path:
    """媒体根目录：settings.DATA_DIR/media（挂载于 /media）。"""
    root = Path(settings.DATA_DIR) / "media"
    root.mkdir(parents=True, exist_ok=True)
    return root


_UPLOAD_ID_RE = re.compile(r"^[A-Za-z0-9_]{6,64}$")


def _safe_upload_id(upload_id: str) -> str:
    """路径穿越防护（Mimosa HIGH）：upload_id 仅允许字母数字下划线，拒绝 ../ 等任意路径段。"""
    if not _UPLOAD_ID_RE.match(upload_id or ""):
        raise AppException(VALIDATION, "非法的 upload_id（仅允许字母/数字/下划线，6~64 位）")
    return upload_id


def _upload_tmp_dir(upload_id: str) -> Path:
    d = Path(settings.DATA_DIR) / "uploads" / "tmp" / _safe_upload_id(upload_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


async def init_chunked_upload(session_id: int, file_name: str, file_size: int, chunk_count: int) -> dict:
    """分片上传初始化：建临时目录 + 落 manifest（finalize 依赖它建库，重启安全）。"""
    ext = Path(file_name or "").suffix.lower()
    if ext not in _VIDEO_EXT_WHITELIST:
        raise AppException(VALIDATION, f"不支持的文件类型 {ext or '(无扩展名)'}（仅 {'/'.join(sorted(_VIDEO_EXT_WHITELIST))}）")
    if file_size <= 0:
        raise AppException(VALIDATION, "file_size 必须大于 0")
    if not (1 <= int(chunk_count) <= _MAX_CHUNK_COUNT):
        raise AppException(VALIDATION, f"chunk_count 必须在 1~{_MAX_CHUNK_COUNT}")
    session = await _session_repo.get_by_id(int(session_id))
    if not session:
        raise NotFoundError("课次", str(session_id))

    upload_id = f"chunk_{uuid.uuid4().hex[:16]}"
    chunk_size = max(1, file_size // max(chunk_count, 1))
    manifest = {
        "upload_id": upload_id, "session_id": int(session_id),
        "file_name": file_name, "file_size": int(file_size), "chunk_count": int(chunk_count),
    }
    tmp = _upload_tmp_dir(upload_id)
    await asyncio.to_thread(lambda: (tmp / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8"))
    return {
        "upload_id": upload_id,
        "chunk_size": chunk_size,
        "upload_urls": [f"/api/admin/courses/videos/upload-chunk/{upload_id}/{i}" for i in range(int(chunk_count))],
        "strategy": "local_disk",
    }


async def upload_chunk(upload_id: str, chunk_index: int, data: bytes) -> dict:
    """接收单个分片并落盘（原始字节，octet-stream）。"""
    manifest_path = _upload_tmp_dir(upload_id) / "manifest.json"
    if not manifest_path.exists():
        raise NotFoundError("上传会话", upload_id)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not (0 <= int(chunk_index) < int(manifest["chunk_count"])):
        raise AppException(VALIDATION, f"chunk_index 越界（0~{manifest['chunk_count'] - 1}）")
    out = _upload_tmp_dir(upload_id) / f"chunk_{int(chunk_index):06d}"
    await asyncio.to_thread(out.write_bytes, data)
    return {"upload_id": upload_id, "chunk_index": int(chunk_index), "received_bytes": len(data)}


async def finalize_chunked_upload(upload_id: str, uploader_user_id: int = 0) -> dict:
    """按序合并分片 → 存盘 → 建 session_asset + session_video（真实 video_id）。"""
    tmp = _upload_tmp_dir(upload_id)
    manifest_path = tmp / "manifest.json"
    if not manifest_path.exists():
        raise NotFoundError("上传会话", upload_id)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ext = Path(manifest["file_name"]).suffix.lower()
    count = int(manifest["chunk_count"])

    parts = [tmp / f"chunk_{i:06d}" for i in range(count)]
    missing = [str(p) for p in parts if not p.exists()]
    if missing:
        raise AppException(VALIDATION, f"缺少 {len(missing)} 个分片，无法 finalize（如 chunk_000000）")

    video_code = f"VID-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    media_dir = _video_media_root() / "videos"
    media_dir.mkdir(parents=True, exist_ok=True)
    final_path = media_dir / f"{video_code}{ext}"

    def _assemble() -> int:
        total = 0
        with open(final_path, "wb") as w:
            for p in parts:
                w.write(p.read_bytes())
                total += p.stat().st_size
        return total

    written = await asyncio.to_thread(_assemble)

    asset_id = await _asset_repo.insert({
        "session_id": int(manifest["session_id"]),
        "asset_code": f"ASSET-{uuid.uuid4().hex[:10].upper()}",
        "asset_name": manifest["file_name"],
        "file_type": _VIDEO_EXT_WHITELIST[ext],
        "material_category": "video",
        "sort_no": 0,
        "access_scope": "enrolled_only",
        "file_url": f"/media/videos/{final_path.name}",
        "file_size": written,
        "uploader_user_id": int(uploader_user_id),  # FK → sys_user.id，由 router 传入
    })
    video_id = await _video_repo.insert({
        "asset_id": asset_id,
        "video_code": video_code,
        "video_title": Path(manifest["file_name"]).stem,
        "duration_seconds": 0,
        "bitrate_kbps": 0,
        "transcode_status": "completed",  # ponytail: 无转码管线，原样可播即 completed
        "review_status": "pending",
    })

    await asyncio.to_thread(lambda: shutil.rmtree(tmp, ignore_errors=True))

    return {
        "upload_id": upload_id,
        "asset_id": asset_id,
        "video_id": video_id,
        "transcode_status": "completed",
        "file_url": f"/media/videos/{final_path.name}",
        "file_size": written,
        "session_id": int(manifest["session_id"]),
    }


async def bind_video_to_session(session_id: int, video_id: int, sort_no: int = 0) -> dict:
    """绑定视频到课次：更新其 asset 的归属课次与排序（finalize 已建 asset，此处修正归属/排序）。"""
    video = await _video_repo.get_by_id(int(video_id))
    if not video:
        raise NotFoundError("视频", str(video_id))
    session = await _session_repo.get_by_id(int(session_id))
    if not session:
        raise NotFoundError("课次", str(session_id))
    await _asset_repo.update(int(video["asset_id"]), {"session_id": int(session_id), "sort_no": int(sort_no)})
    return {
        "session_id": int(session_id),
        "video_id": int(video_id),
        "sort_no": int(sort_no),
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