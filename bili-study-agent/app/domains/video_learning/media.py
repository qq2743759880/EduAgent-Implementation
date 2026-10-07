"""Canonical video acquisition and transcription; no BiliSum runtime dependency.

Bilibili caption selection and Whisper decoding adapt BiliSum 1.21.0 MIT
capabilities. Attribution: vendor/bilisum/LICENSE and media-provenance.json.
Original/playback bytes remain independent of every derived operation.
"""
from __future__ import annotations

import hashlib
import http.cookiejar
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

import httpx


class MediaError(ValueError):
    """A bounded, operator-safe acquisition or transcription failure."""


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _write(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _source_client() -> httpx.Client:
    from app.config import settings
    cookies = http.cookiejar.MozillaCookieJar()
    if settings.VIDEO_BILIBILI_COOKIE_FILE:
        try:
            cookies = http.cookiejar.MozillaCookieJar(settings.VIDEO_BILIBILI_COOKIE_FILE)
            cookies.load(ignore_discard=True, ignore_expires=False)
            for cookie in list(cookies):
                if cookie.domain.lstrip('.') != 'bilibili.com' and not cookie.domain.endswith('.bilibili.com'):
                    cookies.clear(cookie.domain, cookie.path, cookie.name)
        except (OSError, http.cookiejar.LoadError):
            raise MediaError("Bilibili 登录会话配置不可读取，请更新服务端登录配置") from None
    return httpx.Client(timeout=30, trust_env=False, follow_redirects=False, cookies=cookies)


def _json(url: str) -> dict:
    try:
        with _source_client() as client:
            result = client.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"})
            if result.status_code == 412:
                raise MediaError("Bilibili 拒绝来源请求（HTTP 412）；请更新服务端 Bilibili 登录会话，或改用本地视频上传")
            result.raise_for_status()
            if len(result.content) > 32 * 1024 * 1024:
                raise MediaError("来源响应过大")
            value = result.json()
        if not isinstance(value, dict):
            raise MediaError("来源返回格式异常")
        return value
    except MediaError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise MediaError("来源网络请求失败，请稍后重试") from exc


def subtitle_url(url: str) -> str:
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("http://"):
        url = "https://" + url[7:]
    parsed = urlsplit(url)
    allowed = ("bilibili.com", "hdslb.com", "bilivideo.com")
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443)
            or not any(parsed.hostname == host or (parsed.hostname or "").endswith("." + host) for host in allowed)):
        raise MediaError("字幕 URL 不属于可信来源")
    return url


def fetch_native_subtitle(source: dict) -> dict | None:
    endpoints = [
        f"https://api.bilibili.com/x/player/wbi/v2?bvid={source['bvid']}&cid={source['cid']}",
        f"https://api.bilibili.com/x/v2/dm/view?type=1&oid={source['cid']}&pid={source['aid']}",
    ]
    successful = 0
    subtitles = []
    for endpoint in endpoints:
        try:
            value = _json(endpoint)
            if value.get("code") != 0:
                continue
            data = value.get("data")
            # Missing subtitle fields are not an authoritative empty result.
            if not isinstance(data, dict) or not isinstance(data.get("subtitle"), dict):
                continue
            items = data["subtitle"].get("subtitles")
            # DM's empty repeated field is serialized as explicit null; a
            # missing field or a failed request still cannot prove absence.
            if ("/x/v2/dm/view?" in endpoint and "subtitles" in data["subtitle"]
                    and items is None):
                items = []
            if not isinstance(items, list):
                continue
            successful += 1
            if items:
                subtitles = items
                break
        except MediaError:
            continue
    if not subtitles:
        if successful == len(endpoints):
            return None
        raise MediaError("字幕探查失败，无法确认是否有原生字幕；请重试")
    def preference(item):
        lan, doc = str(item.get("lan", "")), str(item.get("lan_doc", ""))
        chinese = "zh" in lan or "中文" in doc
        return (not chinese, "ai-" in lan, "摘要" in doc)
    selected = min(subtitles, key=preference)
    raw = _json(subtitle_url(str(selected.get("subtitle_url", ""))))
    body = raw.get("body")
    for name in ("data", "result", "subtitle"):
        if not isinstance(body, list):
            body = (raw.get(name) or {}).get("body")
    if not isinstance(body, list) or not body:
        raise MediaError("原生字幕内容为空或格式错误")
    segments = [{"start": float(x["from"]), "end": float(x["to"]), "text": str(x["content"]).strip()}
                for x in body if str(x.get("content", "")).strip()]
    if not segments:
        raise MediaError("原生字幕无有效文本")
    return {"transcript": "\n".join(x["text"] for x in segments), "segments": segments}


def _source(bvid: str, page: int) -> dict:
    if not re.fullmatch(r"BV[0-9A-Za-z]{10}", bvid) or type(page) is not int or page < 1:
        raise MediaError("无效的 BVID 或分 P 编号")
    url = f"https://www.bilibili.com/video/{bvid}?p={page}"
    try:
        payload = _json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
        data = payload.get("data") if payload.get("code") == 0 else None
    except MediaError as exc:
        if "412" in str(exc) or "登录会话" in str(exc):
            raise
        data = None
    if not data:
        try:
            with _source_client() as client:
                response = client.get(f"https://www.bilibili.com/video/{bvid}/?p={page}", headers={"User-Agent": "Mozilla/5.0"})
                response.raise_for_status()
            match = re.search(r"__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;\s*\(function", response.text, re.S)
            data = json.loads(match.group(1)).get("videoData") if match else None
        except (httpx.HTTPError, ValueError) as exc:
            raise MediaError("视频来源探查失败，请重试") from exc
    if not isinstance(data, dict) or data.get("bvid") != bvid:
        raise MediaError("视频来源身份不匹配")
    pages = [x for x in data.get("pages", []) if x.get("page") == page]
    if len(pages) != 1:
        raise MediaError("指定分 P 不存在")
    item = pages[0]
    duration = float(item["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise MediaError("来源时长无效")
    return {"bvid": bvid, "aid": int(data["aid"]), "page": page, "cid": int(item["cid"]),
            "title": str(item["part"]), "source_url": url, "duration_seconds": duration}


def _executable(name: str) -> str:
    local = Path("data/runtime/ffmpeg") / (name + (".exe" if os.name == "nt" else ""))
    path = os.environ.get("EDU_VIDEO_" + name.upper()) or (str(local.resolve()) if local.is_file() else shutil.which(name))
    if not path or not Path(path).is_file():
        raise MediaError(f"缺少 {name}，请配置 EDU_VIDEO_{name.upper()}")
    return str(path)


def _probe(path: Path) -> dict:
    result = subprocess.run([_executable("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                            check=True, capture_output=True, text=True, encoding="utf-8", timeout=60)
    value = json.loads(result.stdout)
    return {"duration": float(value["format"]["duration"]), "streams": value["streams"]}


def _verify_media(path: Path, source: dict) -> dict:
    info = _probe(path)
    if not math.isfinite(info["duration"]) or abs(info["duration"] - source["duration_seconds"]) > 3:
        raise MediaError("获取的视频时长与来源分 P 不匹配")
    if not {"video", "audio"}.issubset({x["codec_type"] for x in info["streams"]}):
        raise MediaError("获取媒体缺少视频或音频")
    return info


def _download(source: dict, directory: Path) -> Path:
    import yt_dlp
    target = directory / "original.mp4"
    identity = directory / "acquired.json"
    if identity.exists() and target.exists():
        saved = json.loads(identity.read_text(encoding="utf-8"))
        if saved.get("source") != source or saved.get("sha256") != digest(target):
            raise MediaError("下载缓存的来源或校验值不匹配")
        _verify_media(target, source)
        return target
    options = {"outtmpl": str(directory / "download.%(ext)s"),
               "format": "bestvideo[vcodec^=avc1]+bestaudio/bestvideo[vcodec=h264]+bestaudio/bestvideo+bestaudio/best",
               "merge_output_format": "mp4", "noplaylist": True, "quiet": True, "no_warnings": True, "noprogress": True,
               "proxy": "", "socket_timeout": 45, "retries": 3,
               "http_chunk_size": 1024 * 1024, "ffmpeg_location": _executable("ffmpeg")}
    from app.config import settings
    if settings.VIDEO_BILIBILI_COOKIE_FILE:
        options["cookiefile"] = settings.VIDEO_BILIBILI_COOKIE_FILE
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(source["source_url"], download=True)
        if info.get("id") != f"{source['bvid']}_p{source['page']}":
            raise MediaError("下载器返回了错误的分 P")
        downloaded = directory / "download.mp4"
        _verify_media(downloaded, source)
        os.replace(downloaded, target)
        _write(identity, {"source": source, "sha256": digest(target), "extractor": "yt-dlp", "version": importlib.metadata.version("yt-dlp")})
        return target
    except MediaError:
        raise
    except Exception as exc:
        raise MediaError("视频下载失败，请稍后重试或检查来源访问权限") from exc


def _upload(path: Path, source: dict, sha256: str) -> tuple[str, str]:
    from minio import Minio
    from app.config import settings
    client = Minio(settings.MINIO_ENDPOINT, access_key=settings.MINIO_ACCESS_KEY, secret_key=settings.MINIO_SECRET_KEY,
                   secure=settings.MINIO_SECURE)
    bucket = settings.MINIO_BUCKET_COURSE
    if not client.bucket_exists(bucket):
        raise MediaError("课程对象存储尚未就绪")
    key = f"video/{source['bvid']}/p{source['page']}/{sha256}.mp4"
    try:
        stat = client.stat_object(bucket, key)
    except Exception as exc:
        if getattr(exc, "code", None) != "NoSuchKey":
            raise MediaError("课程存储检查失败") from exc
        client.fput_object(bucket, key, str(path), content_type="video/mp4", metadata={"sha256": sha256,
                           "bvid": source["bvid"], "cid": str(source["cid"]), "page": str(source["page"])})
        stat = client.stat_object(bucket, key)
    if stat.size != path.stat().st_size or stat.metadata.get("x-amz-meta-sha256") != sha256:
        raise MediaError("课程媒体存储校验不匹配")
    value = hashlib.sha256()
    response = client.get_object(bucket, key)
    try:
        for block in response.stream(1024 * 1024):
            value.update(block)
    finally:
        response.close()
        response.release_conn()
    if value.hexdigest() != sha256:
        raise MediaError("课程媒体回读校验失败")
    return bucket, key


def prepare_media(workdir: Path, bvid: str, page: int) -> dict:
    workdir = Path(workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    source = _source(bvid, page)
    discovery = workdir / "discovery.json"
    # The existing compiler accepts only explicitly successful source probes.
    # Keep this discovery status outside source/cache identity itself.
    _write(discovery, {"source": {"bvid": bvid, "aid": source["aid"]}, "pages": [{**source, "probe_status": "ok"}]})
    original = _download(source, workdir)
    playback = workdir / "playback.mp4"
    playback_evidence = workdir / "playback-evidence.json"
    if playback.exists() and playback_evidence.exists():
        prior = json.loads(playback_evidence.read_text(encoding="utf-8"))
        if prior.get("source") != source or prior.get("source_sha256") != digest(original) or prior.get("playback_sha256") != digest(playback):
            raise MediaError("播放缓存来源或校验值不匹配")
    else:
        temporary = workdir / "playback.partial.mp4"
        original_info = _verify_media(original, source)
        video_stream = next(x for x in original_info["streams"] if x["codec_type"] == "video")
        audio_stream = next(x for x in original_info["streams"] if x["codec_type"] == "audio")
        playable = (video_stream["codec_name"] == "h264" and video_stream.get("pix_fmt") == "yuv420p"
                    and audio_stream["codec_name"] == "aac")
        encoding = ["-c", "copy"] if playable else ["-c:v", "libx264", "-threads", "2", "-preset", "veryfast", "-crf", "23",
                                                   "-pix_fmt", "yuv420p", "-c:a", "aac"]
        subprocess.run([_executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-threads", "2", "-i", str(original),
                        "-map", "0:v:0", "-map", "0:a:0", *encoding, "-movflags", "+faststart", str(temporary)],
                       check=True, capture_output=True, timeout=1800)
        _verify_media(temporary, source)
        os.replace(temporary, playback)
        _write(playback_evidence, {"source": source, "source_sha256": digest(original), "playback_sha256": digest(playback)})
    info = _verify_media(playback, source)
    if {x["codec_name"] for x in info["streams"] if x["codec_type"] in ("video", "audio")} != {"h264", "aac"}:
        raise MediaError("播放副本不是 H264/AAC")
    sha256 = digest(playback)
    bucket, key = _upload(playback, source, sha256)
    prepared = {"source": source, "discovery_path": str(discovery), "media_path": str(playback),
                "discovery": str(discovery), "media": str(playback), "bucket": bucket, "object_key": key, "key": key,
                "duration": info["duration"], "size_bytes": playback.stat().st_size, "media_sha256": sha256}
    _write(workdir / "prepared.json", prepared)
    return prepared


def _asr(prepared: dict) -> dict:
    video = Path(prepared["media_path"])
    audio = video.parent / "audio.wav"
    if not audio.exists():
        temporary = video.parent / "audio.partial.wav"
        subprocess.run([_executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
                        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(temporary)],
                       check=True, capture_output=True, timeout=300)
        os.replace(temporary, audio)
    audio_duration = _probe(audio)["duration"]
    if abs(audio_duration - prepared["duration"]) > 3:
        raise MediaError("转写音频时长与播放媒体不匹配")
    model = Path(os.environ.get("EDU_VIDEO_ASR_MODEL", "data/models/faster-whisper-base")).resolve()
    if not (model / "model.bin").is_file():
        raise MediaError("缺少本地 ASR 模型，请配置 EDU_VIDEO_ASR_MODEL")
    output = video.parent / "asr-result.json"
    evidence = {"media_sha256": prepared["media_sha256"], "audio_sha256": digest(audio), "audio_duration": audio_duration}
    if output.exists():
        saved = json.loads(output.read_text(encoding="utf-8"))
        if (all(saved["asr_run"].get(key) == value for key, value in evidence.items())
                and saved.get("asr_model_sha256") == digest(model / "model.bin")
                and saved["asr_run"].get("package_version") == importlib.metadata.version("faster-whisper")):
            return saved
        raise MediaError("已有转写结果与媒体、模型或运行时不匹配")
    try:
        subprocess.run([sys.executable, "-m", "app.domains.video_learning.asr_worker", "--audio", str(audio),
                        "--model", str(model), "--output", str(output), "--media-sha256", prepared["media_sha256"]],
                       check=True, timeout=7200)
    except subprocess.SubprocessError as exc:
        raise MediaError("ASR 转写失败，可重试；原视频仍可播放") from exc
    return json.loads(output.read_text(encoding="utf-8"))


def transcribe_media(prepared: dict, mode: str = "auto") -> Path:
    video = Path(prepared["media_path"])
    if digest(video) != prepared["media_sha256"]:
        raise MediaError("媒体校验失败，拒绝转写")
    if mode not in ("auto", "asr"):
        raise MediaError("不支持的转写模式")
    source = prepared["source"]
    native = fetch_native_subtitle(source) if mode == "auto" else None
    derived = native if native is not None else _asr(prepared)
    previous = 0.0
    normalized = []
    for segment in derived["segments"]:
        start, end = float(segment["start"]), float(segment["end"])
        if end > source["duration_seconds"] and end <= source["duration_seconds"] + 2:
            normalized.append({"start": start, "original_end": end, "end": source["duration_seconds"]})
            end = float(source["duration_seconds"])
            segment["end"] = end
        if not (math.isfinite(start) and math.isfinite(end) and previous <= start < end <= source["duration_seconds"]
                and str(segment["text"]).strip()):
            raise MediaError("转写结果时间范围无效")
        previous = end
    if not derived["segments"] or not derived["transcript"].strip():
        raise MediaError("转写结果为空")
    snapshot = {"source": {**source, "subtitle_segments": len(derived["segments"])},
                "transcript_source": "bilibili_subtitle" if native is not None else "asr",
                "publication_status": "source_only_not_compiled", **derived}
    if normalized:
        snapshot["timestamp_normalization"] = {"reason": "platform duration rounding at media tail", "segments": normalized}
    path = video.parent / "transcript.json"
    _write(path, snapshot)
    return path
