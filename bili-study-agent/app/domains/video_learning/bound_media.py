"""Read and verify an existing authorized video without replacing its bytes."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import math
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit

from app.config import settings
from app.database import fetch_one, get_minio_client
from app.domains.video_learning import media


def _copy_original(reference: str, destination: Path) -> None:
    if reference.startswith("minio://"):
        parsed = urlsplit(reference)
        key = parsed.path.lstrip("/")
        if (parsed.netloc != settings.MINIO_BUCKET_COURSE or parsed.username or parsed.password
                or parsed.query or parsed.fragment or not key or any(part in (".", "..", "") for part in key.split("/"))):
            raise media.MediaError("视频存储引用不属于课程原视频")
        client = get_minio_client()
        info = client.stat_object(parsed.netloc, key)
        if not 0 < info.size <= 8 * 1024**3:
            raise media.MediaError("原视频大小不在处理范围内")
        response = client.get_object(parsed.netloc, key)
        try:
            written = 0
            with destination.open("wb") as handle:
                for block in response.stream(1024 * 1024):
                    written += len(block)
                    if written > info.size:
                        raise media.MediaError("原视频读取大小发生变化")
                    handle.write(block)
            if written != info.size:
                raise media.MediaError("原视频未完整读取")
        finally:
            response.close()
            response.release_conn()
        return
    prefix = "/media/videos/"
    name = reference[len(prefix):] if reference.startswith(prefix) else ""
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.(mp4|mov|avi|webm|mkv)", name, flags=re.IGNORECASE):
        raise media.MediaError("视频存储引用不是受支持的已绑定媒体")
    root = Path(settings.DATA_DIR) / "media" / "videos"
    path = root / name
    from app.domains.video_learning.artifacts import _no_links, ArtifactValidationError
    try:
        _no_links(path)
    except ArtifactValidationError as exc:
        raise media.MediaError("本地原视频不能通过链接或重解析目录读取") from exc
    if not path.is_file():
        raise media.MediaError("本地原视频不可读取")
    if not 0 < path.stat().st_size <= 8 * 1024**3:
        raise media.MediaError("原视频大小不在处理范围内")
    shutil.copyfile(path, destination)


def prepare_bound_media(workdir: Path, row: dict) -> dict:
    """Row must come from the server's locked canonical lesson/video lookup."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    temporary = workdir / "original.partial.mp4"
    _copy_original(row["file_url"], temporary)
    info = media._probe(temporary)
    duration = info["duration"]
    if not math.isfinite(duration) or duration <= 0 or not {"video", "audio"}.issubset(
            {stream["codec_type"] for stream in info["streams"]}):
        raise media.MediaError("原视频缺少有效视频或音频")
    recorded_duration = float(row["duration_seconds"])
    if recorded_duration > 0 and abs(duration - recorded_duration) > 3:
        raise media.MediaError("原视频时长与课次记录不一致，拒绝生成资料")
    checksum = media.digest(temporary)
    original = workdir / "original.mp4"
    if original.exists():
        if media.digest(original) != checksum:
            raise media.MediaError("原视频字节已改变，旧任务不能复用新的播放来源")
        temporary.unlink()
    else:
        temporary.replace(original)
    source = {"platform": "edu", "source_kind": "existing_video", "session_id": int(row["session_id"]),
              "video_id": int(row["video_id"]), "asset_id": int(row["asset_id"]), "media_sha256": checksum,
              "url": f"edu://video/{row['video_id']}", "title": row["video_title"], "duration": duration}
    discovery = workdir / "discovery.json"
    media._write(discovery, {"source": source})
    result = {"source": source, "discovery": str(discovery.resolve()), "media": str(original.resolve()),
              "discovery_path": str(discovery.resolve()), "media_path": str(original.resolve()),
              "media_sha256": checksum, "duration": duration, "size_bytes": original.stat().st_size}
    media._write(workdir / "prepared.json", result)
    return result


def transcribe_bound_media(prepared: dict, mode: str = "auto") -> Path:
    if mode not in ("auto", "asr"):
        raise media.MediaError("不支持的转写模式")
    if media.digest(Path(prepared["media_path"])) != prepared["media_sha256"]:
        raise media.MediaError("原视频字节校验失败")
    derived = media._asr(prepared)
    source = prepared["source"]
    if derived["asr_run"]["media_sha256"] != source["media_sha256"]:
        raise media.MediaError("转写媒体身份不匹配")
    previous = 0.0
    for segment in derived["segments"]:
        start, end = float(segment["start"]), float(segment["end"])
        if end > source["duration"] and end <= source["duration"] + 0.25:
            segment["end"] = end = source["duration"]
        if not (math.isfinite(start) and math.isfinite(end) and previous <= start < end <= source["duration"]
                and str(segment["text"]).strip()):
            raise media.MediaError("转写结果时间范围无效")
        previous = end
    if not derived["segments"] or not derived["transcript"].strip():
        raise media.MediaError("转写结果为空")
    path = Path(prepared["media_path"]).parent / "transcript.json"
    media._write(path, {"source": {**source, "subtitle_segments": len(derived["segments"])},
                       "transcript_source": "asr", "publication_status": "source_only_not_compiled", **derived})
    return path


async def verify_bound_source(source) -> None:
    """Publication and RAG verify current authorized bytes, not trusted client SHA."""
    from app.domains.learning.repository import StudyRepo
    row = await fetch_one("SELECT sv.id AS video_id,sv.video_title,sv.duration_seconds,sv.video_code,"
                          "sa.id AS asset_id,sa.session_id,sa.file_url,sa.file_size FROM session_video sv "
                          "JOIN session_asset sa ON sa.id=sv.asset_id WHERE sv.id=%s", (source.video_id,))
    canonical = await StudyRepo().get_session_video(source.session_id)
    if (not row or not canonical or canonical["video_id"] != source.video_id
            or row["session_id"] != source.session_id or row["asset_id"] != source.asset_id):
        raise media.MediaError("课次与原视频绑定已变化")
    root = Path(settings.DATA_DIR) / "video_knowledge_tasks" / ".verification"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v-", dir=root) as directory:
        operation = asyncio.create_task(asyncio.to_thread(prepare_bound_media, Path(directory), row))
        try:
            prepared = await asyncio.shield(operation)
        except asyncio.CancelledError:
            # The lease/global fence owner must drain reads before temporary
            # files disappear or another operator retries the same operation.
            while not operation.done():
                with suppress(asyncio.CancelledError, Exception):
                    await asyncio.shield(operation)
            with suppress(Exception):
                operation.result()
            raise
        verified = prepared["source"]
        if (verified["media_sha256"] != source.media_sha256 or abs(verified["duration"] - source.duration) > 0.01):
            raise media.MediaError("资料与原视频字节或时长不一致")
