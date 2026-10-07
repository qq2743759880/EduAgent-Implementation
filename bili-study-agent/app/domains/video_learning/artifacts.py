"""Immutable video knowledge and verified platform or existing EDU media identity.

Schema 1 preserves unpublishable legacy candidates; schemas 2/3 preserve verified
platform native/ASR outputs byte-for-byte. Schema 4 binds actual EDU media by
lesson/video/asset IDs and the exact ASR input checksum, without platform IDs.
This seam performs no model calls, media acquisition or database writes.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
import re
import sqlite3
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

NonEmpty = Annotated[str, Field(min_length=1, strict=True)]
Timecode = Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", strict=True)]
PositiveInt = Annotated[int, Field(gt=0, strict=True)]
INPUT_FILES = (
    "summary.json", "transcript.txt", "knowledge_note.md", "mindmap.json",
    "transcription_worker_result.json",
)
UPSTREAM_FILES = (
    "VERSION", "LICENSE", "packages/core/src/video_sum_core/pipeline/real.py",
    "packages/core/src/video_sum_core/models/tasks.py",
    "packages/core/src/video_sum_core/pipeline/base.py",
    "packages/infra/src/video_sum_infra/config.py",
    "packages/infra/src/video_sum_infra/llm.py",
    "packages/infra/src/video_sum_infra/runtime.py",
    "apps/service/src/video_sum_service/integrations.py",
)
MAX_FILE_BYTES = 32 * 1024 * 1024


class ArtifactValidationError(ValueError):
    """An input, identity, checksum, or immutable artifact is invalid."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def nonblank_strings(self):
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, str) and not value.strip():
                raise ValueError(f"{name} must not be blank")
        return self


class VideoSource(_Model):
    platform: Literal["bilibili"]
    bvid: Annotated[str, Field(pattern=r"^BV[0-9A-Za-z]{10}$", strict=True)]
    page: PositiveInt
    cid: PositiveInt
    url: NonEmpty
    title: NonEmpty
    duration: Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)]

    @model_validator(mode="after")
    def identity_url(self) -> VideoSource:
        if self.url != f"https://www.bilibili.com/video/{self.bvid}?p={self.page}":
            raise ValueError("source URL must identify the same BVID and page")
        return self


class EduVideoSource(_Model):
    """Server-verified existing media identity, independent of a platform URL."""
    platform: Literal["edu"]
    source_kind: Literal["existing_video"]
    session_id: PositiveInt
    video_id: PositiveInt
    asset_id: PositiveInt
    media_sha256: Digest
    url: NonEmpty
    title: NonEmpty
    duration: Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)]

    @model_validator(mode="after")
    def identity_url(self):
        if self.url != f"edu://video/{self.video_id}":
            raise ValueError("EDU source URL must identify its actual video")
        return self


class Segment(_Model):
    start: Timecode
    end: Timecode
    text: NonEmpty


class Transcript(_Model):
    full_text: NonEmpty
    segments: Annotated[list[Segment], Field(min_length=1)]


class Chapter(_Model):
    title: NonEmpty
    start: Timecode
    summary: NonEmpty


class StructuredSummary(_Model):
    title: NonEmpty
    overview: NonEmpty
    key_points: Annotated[list[NonEmpty], Field(min_length=1)]


class MindMapNode(_Model):
    id: NonEmpty
    label: NonEmpty
    type: NonEmpty
    summary: NonEmpty
    children: list[MindMapNode]
    time_anchor: Timecode | None
    source_chapter_titles: list[NonEmpty]
    source_chapter_starts: list[Timecode]


class MindMap(_Model):
    version: Literal[1]
    title: NonEmpty
    root: NonEmpty
    nodes: Annotated[list[MindMapNode], Field(min_length=1, max_length=1)]


class FileFingerprint(_Model):
    path: NonEmpty
    sha256: Digest
    size_bytes: Annotated[int, Field(ge=0, strict=True)]


class UpstreamSnapshot(_Model):
    repo: Literal["https://github.com/lycohana/BiliSum.git"]
    head: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$", strict=True)]
    dirty: Annotated[bool, Field(strict=True)]
    files: list[FileFingerprint]


class LegacyRun(_Model):
    task_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$", strict=True)]
    status: Literal["completed"]
    created_at: NonEmpty
    revision: None = None
    transcript_origin: Literal["asr"]
    transcription_provider: Literal["faster-whisper"]
    transcription_model: Literal["tiny"]
    task_evidence_sha256: Digest


class LLMRun(_Model):
    stage: NonEmpty
    provider: NonEmpty
    model: NonEmpty


class CompilerProvenance(_Model):
    name: Literal["BiliSum"]
    version: NonEmpty
    importer: Literal["edu-bilisum-artifact-v1"]
    upstream_snapshot: UpstreamSnapshot
    legacy_run: LegacyRun
    llm_runs: Annotated[list[LLMRun], Field(min_length=1)]
    inputs: list[FileFingerprint]
    discovery: FileFingerprint


class NativeLLMRun(_Model):
    stage: Literal["summary", "knowledge_note", "mindmap", "exercises"]
    provider: Literal["openai-compatible", "deterministic"]
    model: NonEmpty
    served_model: NonEmpty | None = None
    request_sha256: Digest
    response_sha256: Digest
    prompt_tokens: Annotated[int, Field(ge=0, strict=True)]
    completion_tokens: Annotated[int, Field(ge=0, strict=True)]
    total_tokens: Annotated[int, Field(ge=0, strict=True)]
    reasoning_tokens: Annotated[int | None, Field(ge=0, strict=True)] = None

    @model_validator(mode="after")
    def deterministic_derivation(self) -> NativeLLMRun:
        if self.provider == "deterministic" and (
            self.stage != "mindmap" or self.model != "edu-chapter-mindmap-v1"
            or any((self.prompt_tokens, self.completion_tokens, self.total_tokens))
            or self.served_model is not None or self.reasoning_tokens not in (None, 0)
        ):
            raise ValueError("deterministic provenance is reserved for zero-token chapter MindMap derivation")
        return self


class NativeCompilerProvenance(_Model):
    name: Literal["EduVideoCompiler"]
    version: Literal["1"]
    transcript_origin: Literal["platform_subtitle"]
    subtitle: FileFingerprint
    discovery: FileFingerprint
    code_files: Annotated[list[FileFingerprint], Field(min_length=1)]
    upstream_repo: Literal["https://github.com/lycohana/BiliSum.git"]
    upstream_head: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$", strict=True)]
    upstream_license: Literal["MIT"]
    upstream_source_files: Annotated[list[FileFingerprint], Field(min_length=1)]
    llm_runs: Annotated[list[NativeLLMRun], Field(min_length=3, max_length=6)]


class ASRRun(_Model):
    provider: Literal["faster-whisper"]
    model: NonEmpty
    language: str = Field(pattern=r"^[a-z]{2,3}$")
    device: Literal["cpu", "cuda"]
    compute_type: NonEmpty
    package_version: NonEmpty
    media_sha256: Digest
    audio_sha256: Digest
    audio_duration: Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)]


class ASRCompilerProvenance(NativeCompilerProvenance):
    version: Literal["2"]
    transcript_origin: Literal["asr"]
    asr_run: ASRRun


class VideoArtifact(_Model):
    schema_version: Literal[1, 2, 3, 4]
    quality: Literal["candidate_requires_native_recompile", "native_compiled", "asr_compiled"]
    source: VideoSource | EduVideoSource
    transcript: Transcript
    chapters: Annotated[list[Chapter], Field(min_length=1)]
    summary: StructuredSummary
    knowledge_note: NonEmpty
    mindmap: MindMap
    compiler: CompilerProvenance | NativeCompilerProvenance | ASRCompilerProvenance
    content_sha256: Digest
    artifact_sha256: Digest

    @model_validator(mode="after")
    def relationships(self) -> VideoArtifact:
        duration = self.source.duration
        previous_end = 0.0
        for segment in self.transcript.segments:
            if segment.start < previous_end or segment.end <= segment.start or segment.end > duration:
                raise ValueError("transcript segments must be ordered, nonoverlapping, and within duration")
            previous_end = segment.end
        starts = [chapter.start for chapter in self.chapters]
        if starts[0] != 0 or any(a >= b for a, b in zip(starts, starts[1:])) or starts[-1] >= duration:
            raise ValueError("chapters must start at zero and increase within duration")
        if self.mindmap.nodes[0].id != self.mindmap.root:
            raise ValueError("mindmap root does not identify its root node")
        chapter_refs = {(c.title, c.start) for c in self.chapters}
        stack = [(self.mindmap.nodes[0], 0)]
        seen: set[str] = set()
        while stack:
            node, depth = stack.pop()
            if depth > 32 or node.id in seen or len(seen) >= 2000:
                raise ValueError("mindmap has duplicate IDs or exceeds tree limits")
            seen.add(node.id)
            if node.time_anchor is not None and node.time_anchor >= duration:
                raise ValueError("mindmap time anchor is outside video duration")
            refs = list(zip(node.source_chapter_titles, node.source_chapter_starts))
            if len(node.source_chapter_titles) != len(node.source_chapter_starts) or any(
                ref not in chapter_refs for ref in refs
            ):
                raise ValueError("mindmap chapter references do not match canonical chapters")
            stack.extend((child, depth + 1) for child in node.children)
        if isinstance(self.compiler, CompilerProvenance):
            if self.schema_version != 1 or self.quality != "candidate_requires_native_recompile":
                raise ValueError("legacy ASR artifacts must remain schema-1 candidates")
            expected = {f"data/data/tasks/{self.compiler.legacy_run.task_id}/{name}" for name in INPUT_FILES}
            actual = [item.path for item in self.compiler.inputs]
            if len(actual) != len(expected) or set(actual) != expected:
                raise ValueError("compiler input fingerprints must identify exactly the five legacy files")
            snapshot = [item.path for item in self.compiler.upstream_snapshot.files]
            if len(snapshot) != len(UPSTREAM_FILES) or set(snapshot) != set(UPSTREAM_FILES):
                raise ValueError("upstream snapshot fingerprints are incomplete")
        else:
            expected = ((4 if isinstance(self.source, EduVideoSource) else 3), "asr_compiled") if isinstance(self.compiler, ASRCompilerProvenance) else (2, "native_compiled")
            if (self.schema_version, self.quality) != expected:
                raise ValueError("compiler origin differs from artifact schema/quality")
            if isinstance(self.compiler, ASRCompilerProvenance) and abs(self.compiler.asr_run.audio_duration - duration) > 3:
                raise ValueError("ASR audio duration differs from authoritative video")
            if isinstance(self.source, EduVideoSource) and (
                not isinstance(self.compiler, ASRCompilerProvenance)
                or self.compiler.asr_run.media_sha256 != self.source.media_sha256
            ):
                raise ValueError("EDU media identity differs from actual ASR input")
            if {run.stage for run in self.compiler.llm_runs} != {"summary", "knowledge_note", "mindmap"}:
                raise ValueError("native artifact lacks summary, note, or MindMap generation provenance")
            anchors = {0.0, *(segment.start for segment in self.transcript.segments)}
            if any(chapter.start not in anchors for chapter in self.chapters):
                raise ValueError("native chapters must anchor to actual subtitle segments")
            stack = list(self.mindmap.nodes)
            while stack:
                node = stack.pop()
                if not node.children and (not node.source_chapter_starts or node.time_anchor != min(node.source_chapter_starts)):
                    raise ValueError("native MindMap leaves require an exact source chapter anchor")
                stack.extend(node.children)
        payload = self.model_dump(mode="json")
        if _content_digest(payload) != self.content_sha256:
            raise ValueError("artifact content checksum mismatch")
        if _artifact_digest(payload) != self.artifact_sha256:
            raise ValueError("artifact provenance checksum mismatch")
        return self


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _content_digest(payload: dict[str, Any]) -> str:
    return _digest(_json_bytes({k: v for k, v in payload.items() if k not in {
        "compiler", "content_sha256", "artifact_sha256",
    }}))


def _artifact_digest(payload: dict[str, Any]) -> str:
    return _digest(_json_bytes({k: v for k, v in payload.items() if k != "artifact_sha256"}))


def _no_links(path: Path) -> Path:
    """Reject symlinks and Windows junction/reparse ancestors before resolving."""
    path = Path(os.path.abspath(path))
    for part in reversed((path, *path.parents)):
        if not part.exists() and not part.is_symlink():
            continue
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ArtifactValidationError("symlink or reparse-point paths are not permitted")
    return path


def _file(root: Path, relative: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute() or relative_path.drive or ".." in relative_path.parts:
        raise ArtifactValidationError("input file path must remain inside its declared root")
    root = _no_links(root).resolve(strict=True)
    path = _no_links(root / relative_path).resolve(strict=True)
    if not path.is_relative_to(root) or not stat.S_ISREG(path.stat().st_mode):
        raise ArtifactValidationError("input must be a regular file inside its declared root")
    return path


def _read(path: Path) -> bytes:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ArtifactValidationError("input file exceeds the 32 MiB limit")
    return path.read_bytes()


def _json(data: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for key, value in items:
            if key in obj:
                raise ArtifactValidationError("duplicate JSON object key")
            obj[key] = value
        return obj

    try:
        result = json.loads(data.decode("utf-8"), object_pairs_hook=pairs)
        if not isinstance(result, dict):
            raise ArtifactValidationError("JSON input must be an object")
        return result
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ArtifactValidationError("invalid artifact JSON") from exc


def validate_video_artifact(payload: dict[str, Any]) -> VideoArtifact:
    """Validate schema, video timecodes, chapter links, and both checksums."""
    try:
        return VideoArtifact.model_validate(payload)
    except (ValidationError, TypeError, ValueError, RecursionError) as exc:
        raise ArtifactValidationError(f"invalid video artifact: {exc}") from exc


def load_video_artifact(path: Path) -> VideoArtifact:
    """Load the canonical JSON only; no DB, provider, or legacy-file dependency."""
    path = Path(path)
    return validate_video_artifact(_json(_read(_file(path.parent, path.name))))


def seal_video_artifact(payload: dict[str, Any]) -> VideoArtifact:
    """Normalize shared data fields, compute both hashes, and validate provenance."""
    data = dict(payload)
    try:
        source_type = EduVideoSource if data["source"].get("platform") == "edu" else VideoSource
        data["source"] = source_type.model_validate(data["source"]).model_dump(mode="json")
        data["transcript"] = Transcript.model_validate(data["transcript"]).model_dump(mode="json")
        data["chapters"] = [Chapter.model_validate(c).model_dump(mode="json") for c in data["chapters"]]
        data["summary"] = StructuredSummary.model_validate(data["summary"]).model_dump(mode="json")
        data["mindmap"] = MindMap.model_validate(data["mindmap"]).model_dump(mode="json")
        compiler_type = {1: CompilerProvenance, 2: NativeCompilerProvenance, 3: ASRCompilerProvenance, 4: ASRCompilerProvenance}[data["schema_version"]]
        data["compiler"] = compiler_type.model_validate(data["compiler"]).model_dump(mode="json")
        data["content_sha256"] = _content_digest(data)
        data["artifact_sha256"] = _artifact_digest(data)
    except (KeyError, ValidationError, TypeError, ValueError, RecursionError) as exc:
        raise ArtifactValidationError("invalid artifact fields before sealing") from exc
    return validate_video_artifact(data)


def save_video_artifact(artifact: VideoArtifact, output: Path) -> Path:
    """Publish one complete immutable canonical file, reusing identical content."""
    artifact = validate_video_artifact(artifact.model_dump(mode="json"))
    destination = _no_links(output) / artifact.content_sha256 / "artifact.json"
    _no_links(destination)
    if destination.exists():
        existing = load_video_artifact(destination)
        if existing.content_sha256 != artifact.content_sha256:
            raise ArtifactValidationError("existing pack conflicts with content identity")
        if existing.artifact_sha256 != artifact.artifact_sha256:
            raise ArtifactValidationError("existing pack conflicts with immutable provenance; use a new revision directory")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, prefix=".artifact-", delete=False) as temp:
            temp_path = Path(temp.name)
            temp.write(_json_bytes(artifact.model_dump(mode="json")) + b"\n")
            temp.flush()
            os.fsync(temp.fileno())
        try:
            os.link(temp_path, destination)
        except FileExistsError:
            existing = load_video_artifact(destination)
            if existing.content_sha256 != artifact.content_sha256:
                raise ArtifactValidationError("concurrent pack conflicts with content identity")
            if existing.artifact_sha256 != artifact.artifact_sha256:
                raise ArtifactValidationError("concurrent pack conflicts with immutable provenance; use a new revision directory")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return destination


def _fingerprint(path: str, data: bytes) -> dict[str, Any]:
    return {"path": path, "sha256": _digest(data), "size_bytes": len(data)}


def _text(data: bytes) -> str:
    # Windows writes CRLF for text files; JSON strings retain their original LF.
    # Normalize only the content representation; fingerprints cover raw bytes.
    return data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def _git(root: Path, *args: str) -> str:
    _no_links(root / ".git")
    try:
        return subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args], check=True, capture_output=True,
                              text=True, timeout=15).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ArtifactValidationError("unable to read upstream Git snapshot") from exc


def _legacy_evidence(root: Path, task_id: str, source: VideoSource) -> dict[str, Any]:
    db = _file(root, "data/data/video_sum.db")
    try:
        with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as connection:
            row = connection.execute(
                "SELECT status, task_input_json, page_number, page_title, created_at FROM tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
            events = connection.execute(
                "SELECT stage, message FROM task_events WHERE task_id=? ORDER BY created_at, event_id", (task_id,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise ArtifactValidationError("unable to read legacy task evidence") from exc
    if not row or row[0] != "completed" or row[2] != source.page:
        raise ArtifactValidationError("legacy task must be completed and identify the discovery page")
    task_input = _json(str(row[1] or "").encode("utf-8"))
    url = urlsplit(str(task_input.get("source", "")))
    page = parse_qs(url.query).get("p", ["1"])
    if url.hostname not in {"www.bilibili.com", "bilibili.com"} or url.path.rstrip("/") != f"/video/{source.bvid}" or page != [str(source.page)]:
        raise ArtifactValidationError("legacy task BVID/page does not match source discovery")
    expected_title = f"P{source.page} {source.title}"
    if row[3] != expected_title or task_input.get("title") != expected_title:
        raise ArtifactValidationError("legacy task title does not match the discovered video")
    if ("transcribing", "正在加载转写模型 tiny") not in events or not any(
        stage == "mindmap_completed" for stage, _ in events
    ):
        raise ArtifactValidationError("legacy cache lacks tiny ASR / completed MindMap evidence")
    evidence = {"task_id": task_id, "status": row[0], "page": row[2], "title": row[3],
                "source_url": task_input["source"], "created_at": row[4],
                "asr_model": "tiny", "mindmap_completed": True}
    return {"task_id": task_id, "status": "completed", "created_at": row[4], "revision": None,
            "transcript_origin": "asr", "transcription_provider": "faster-whisper",
            "transcription_model": "tiny", "task_evidence_sha256": _digest(_json_bytes(evidence))}


def _source_from_discovery(data: bytes, page: int | None = None) -> VideoSource | EduVideoSource:
    discovery = _json(data)
    if isinstance(discovery.get("source"), dict) and discovery["source"].get("platform") == "edu":
        if page is not None:
            raise ArtifactValidationError("EDU media does not have a platform page")
        try:
            return EduVideoSource.model_validate(discovery["source"])
        except ValidationError as exc:
            raise ArtifactValidationError("discovery lacks a verified EDU media identity") from exc
    pages = discovery.get("pages")
    if not isinstance(pages, list):
        raise ArtifactValidationError("discovery pages must be an array")
    matches = [p for p in pages if isinstance(p, dict) and p.get("page") == page]
    if len(matches) != 1 or matches[0].get("probe_status") != "ok":
        raise ArtifactValidationError("discovery must contain one successfully probed page")
    try:
        return VideoSource.model_validate({"platform": "bilibili", "bvid": discovery["source"]["bvid"],
            "page": matches[0]["page"], "cid": matches[0]["cid"], "url": matches[0]["source_url"],
            "title": matches[0]["title"], "duration": matches[0]["duration_seconds"]})
    except (KeyError, TypeError, ValidationError) as exc:
        raise ArtifactValidationError("discovery lacks a valid source identity/duration") from exc


def import_bilisum_video_artifact(*, bilisum_root: Path, task_id: str, discovery: Path,
                                page: int, output: Path) -> Path:
    """Validate one completed legacy tiny-ASR run and atomically persist a candidate.

    Only the five named derivation files are read; media, cookies, settings and
    BiliSum's knowledge DB are never imported. Same normalized content reuses the
    first immutable pack at ``output/<content_sha256>/artifact.json``.
    """
    if not re.fullmatch(r"[0-9a-f]{32}", task_id) or type(page) is not int or page < 1:
        raise ArtifactValidationError("invalid task ID or page")
    root = _no_links(bilisum_root).resolve(strict=True)
    discovery = _file(Path(discovery).parent, Path(discovery).name)
    discovery_bytes = _read(discovery)
    source = _source_from_discovery(discovery_bytes, page)
    legacy = _legacy_evidence(root, task_id, source)
    input_data = {name: _read(_file(root, f"data/data/tasks/{task_id}/{name}")) for name in INPUT_FILES}
    compiled = _json(input_data["summary.json"])
    worker = _json(input_data["transcription_worker_result.json"])
    try:
        summary = compiled["summary"]
        transcript = _text(input_data["transcript.txt"])
        note = _text(input_data["knowledge_note.md"])
        if compiled["title"] != f"P{page} {source.title}" or summary["title"] != compiled["title"]:
            raise ArtifactValidationError("compiled titles do not match the legacy source")
        if compiled["segments"] != worker["segments"] or transcript != worker["transcript"]:
            raise ArtifactValidationError("transcript and summary have different derivation inputs")
        if note != summary["knowledgeNoteMarkdown"]:
            raise ArtifactValidationError("knowledge note differs from its compiled summary")
        llm_runs = [{k: run[k] for k in ("stage", "provider", "model")}
                    for run in summary["llm_usage_breakdown"]]
        if not {"summary_full", "knowledge_note"}.issubset({run["stage"] for run in llm_runs}):
            raise ArtifactValidationError("cache lacks corresponding summary/knowledge-note model provenance")
        upstream = {name: _read(_file(root, name)) for name in UPSTREAM_FILES}
        repo = _git(root, "remote", "get-url", "origin")
        if repo not in {"https://github.com/lycohana/BiliSum.git", "git@github.com:lycohana/BiliSum.git"}:
            raise ArtifactValidationError("upstream origin is not the audited BiliSum repository")
        payload = {"schema_version": 1, "quality": "candidate_requires_native_recompile",
            "source": source.model_dump(mode="json"),
            "transcript": {"full_text": transcript, "segments": compiled["segments"]},
            "chapters": summary["chapters"],
            "summary": {"title": summary["title"], "overview": summary["overview"], "key_points": summary["bulletPoints"]},
            "knowledge_note": note, "mindmap": _json(input_data["mindmap.json"]),
            "compiler": {"name": "BiliSum", "version": upstream["VERSION"].decode("utf-8").strip(),
                "importer": "edu-bilisum-artifact-v1",
                "upstream_snapshot": {"repo": "https://github.com/lycohana/BiliSum.git", "head": _git(root, "rev-parse", "HEAD"),
                    "dirty": bool(_git(root, "status", "--porcelain")),
                    "files": [_fingerprint(name, data) for name, data in upstream.items()]},
                "legacy_run": legacy, "llm_runs": llm_runs,
                "inputs": [_fingerprint(f"data/data/tasks/{task_id}/{name}", data) for name, data in input_data.items()],
                "discovery": _fingerprint(discovery.name, discovery_bytes)}}
    except (KeyError, TypeError, UnicodeError) as exc:
        raise ArtifactValidationError("legacy cache lacks required corresponding artifacts") from exc
    # Normalize numeric JSON values through the schema before hashing.
    try:
        payload["transcript"] = Transcript.model_validate(payload["transcript"]).model_dump(mode="json")
        payload["chapters"] = [Chapter.model_validate(c).model_dump(mode="json") for c in payload["chapters"]]
        payload["mindmap"] = MindMap.model_validate(payload["mindmap"]).model_dump(mode="json")
    except (ValidationError, TypeError, ValueError, RecursionError) as exc:
        raise ArtifactValidationError("legacy cache has invalid transcript/chapter/MindMap fields") from exc
    payload["content_sha256"] = _content_digest(payload)
    payload["artifact_sha256"] = _artifact_digest(payload)
    artifact = validate_video_artifact(payload)
    output = _no_links(output)
    if output.resolve().is_relative_to(root):
        raise ArtifactValidationError("artifact output must not modify the upstream repository")
    return save_video_artifact(artifact, output)


def verify_bilisum_input_fingerprints(artifact: VideoArtifact, *, bilisum_root: Path,
                                    discovery: Path) -> None:
    """Explicit audit against original inputs; ordinary artifact reads need none."""
    root = _no_links(bilisum_root)
    for fingerprint in (*artifact.compiler.inputs, *artifact.compiler.upstream_snapshot.files):
        data = _read(_file(root, fingerprint.path))
        if _fingerprint(fingerprint.path, data) != fingerprint.model_dump(mode="json"):
            raise ArtifactValidationError("legacy input or upstream snapshot fingerprint changed")
    path = _file(Path(discovery).parent, Path(discovery).name)
    if _fingerprint(path.name, _read(path)) != artifact.compiler.discovery.model_dump(mode="json"):
        raise ArtifactValidationError("source discovery fingerprint changed")
    if _legacy_evidence(root, artifact.compiler.legacy_run.task_id, artifact.source) != artifact.compiler.legacy_run.model_dump(mode="json"):
        raise ArtifactValidationError("legacy task evidence changed")
