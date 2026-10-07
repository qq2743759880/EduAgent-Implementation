"""Compile one verified platform or existing EDU video into the existing IR."""
from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from app.domains.video_learning.artifacts import EduVideoSource, NativeCompilerProvenance, VideoArtifact
from app.knowledge.ir import (
    BlockType, DocumentBlock, IRArtifact, ParsedDocument, SecurityMeta,
    SeedKnowledgeChunk, SourceAssetRef, join_blocks_text,
)
from app.knowledge.video_metadata import VideoKnowledgeMetadata, _sign_published_video_row


class VideoKnowledgeBinding(BaseModel):
    """Authoritative course/video/security values resolved by the operator path."""

    model_config = ConfigDict(extra="forbid")
    series_id: int = Field(gt=0, strict=True)
    session_id: int = Field(gt=0, strict=True)
    video_id: int = Field(gt=0, strict=True)
    series_code: str = Field(min_length=1)
    series_name: str = Field(min_length=1)
    module_code: str = Field(min_length=1)
    security: SecurityMeta


def _time(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60:02d}:{whole % 60:02d}"


def build_video_ir(
    artifact: VideoArtifact, *, source: SourceAssetRef, binding: VideoKnowledgeBinding,
    task_id: str, asset_id: str,
) -> IRArtifact:
    """Use 30–45s transcript windows and real chapter ranges, without embedding a whole-video overview.

    The source references the exact immutable published artifact bytes; every seed
    carries the course/video IDs, generation, citation times and task security.
    Existing prepare_chunks, embedding, and Milvus ingestion consume this IR.
    """
    if artifact.quality not in ("native_compiled", "asr_compiled") or not isinstance(artifact.compiler, NativeCompilerProvenance):
        raise ValueError("Video IR requires a fresh native compilation")
    backend = "edu-video-compiler"
    blocks: list[DocumentBlock] = []
    seeds: list[SeedKnowledgeChunk] = []

    def append(text: str, start: float, end: float, kind: str) -> None:
        metadata = VideoKnowledgeMetadata(
            series_id=binding.series_id, session_id=binding.session_id,
            video_id=binding.video_id, start_seconds=start, end_seconds=end,
            distill_artifact_id=artifact.content_sha256,
            distill_artifact_sha256=artifact.artifact_sha256,
            **({"source_kind": "existing_video", "source_asset_id": artifact.source.asset_id,
                "source_media_sha256": artifact.source.media_sha256}
               if isinstance(artifact.source, EduVideoSource)
               else {"source_bvid": artifact.source.bvid, "source_cid": artifact.source.cid}),
            compiler_version=artifact.compiler.version, generation=artifact.content_sha256,
        ).model_dump()
        metadata.update(series_code=binding.series_code, series_name=binding.series_name,
                        module_code=binding.module_code, module_codes=[binding.module_code],
                        video_knowledge_kind=kind)
        block = DocumentBlock(block_id=f"{source.document_id}:b{len(blocks) + 1}",
                              block_type=BlockType.TEXT, text=text, metadata=metadata)
        blocks.append(block)
        seed_text, span = join_blocks_text([block])
        seeds.append(SeedKnowledgeChunk(
            seed_id=f"{source.document_id}:video{len(seeds) + 1:04d}",
            document_id=source.document_id, block_ids=[block.block_id], block_type=block.block_type,
            page_start=1, page_end=1, parser_backend=backend,
            text=seed_text, block_span=span, security=binding.security, metadata=metadata,
        ))

    window = []

    def flush() -> None:
        if not window:
            return
        start, end = window[0].start, window[-1].end
        body = "\n".join(f"[{_time(segment.start)}] {segment.text}" for segment in window)
        origin_label = "ASR 转写" if artifact.compiler.transcript_origin == "asr" else "原生字幕"
        append(f"{artifact.source.title}\n{origin_label} [{_time(start)}–{_time(end)}]\n{body}",
               start, end, "transcript")
        window.clear()

    for segment in artifact.transcript.segments:
        if segment.end - segment.start > 45:
            raise ValueError("A native subtitle segment exceeds the citation window budget")
        if window and (
            segment.end - window[0].start > 45
            or (window[-1].end - window[0].start >= 30 and segment.end - window[0].start > 40)
        ):
            flush()
        window.append(segment)
    flush()
    for index, chapter in enumerate(artifact.chapters):
        end = artifact.chapters[index + 1].start if index + 1 < len(artifact.chapters) else artifact.source.duration
        append(f"{artifact.source.title}\n章节：{chapter.title} [{_time(chapter.start)}–{_time(end)}]\n{chapter.summary}",
               chapter.start, end, "chapter")

    options = {**binding.model_dump(mode="json"), "window_min_seconds": 30,
               "window_target_seconds": 40, "window_max_seconds": 45}
    parsed = ParsedDocument(
        source=source, parser_backend=backend, parser_version=artifact.compiler.version,
        blocks=blocks, page_count=1,
        options_hash=hashlib.sha256(json.dumps(options, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
    )
    return IRArtifact(task_id=task_id, asset_id=asset_id, document_id=source.document_id,
                      parsed=parsed, seeds=seeds)


def certify_published_video_ir(
    ir: IRArtifact, *, publication: dict, binding: VideoKnowledgeBinding, tenant_id: str,
) -> IRArtifact:
    """Operator-only stage after formal publication and canonical DB binding checks.

    build_video_ir and loader never mint a proof based on supplied metadata.
    The caller resolves this pointer and binding from MySQL, checks the exact
    canonical video, and reads/hash-checks its immutable native artifact first.
    """
    source = ir.parsed.source
    if (source.sha256 != publication.get("object_sha256") or source.bucket != publication.get("bucket")
            or source.object_key != publication.get("object_key")
            or binding.video_id != publication.get("video_id") or type(publication.get("id")) is not int
            or ir.parsed.parser_backend != "edu-video-compiler"):
        raise ValueError("Published video IR pointer or binding mismatch")
    if binding.security.visibility != "public":
        return ir
    result = ir.model_copy(deep=True)
    for seed in result.seeds:
        metadata = seed.metadata
        if (metadata.get("series_id") != binding.series_id or metadata.get("session_id") != binding.session_id
                or metadata.get("video_id") != binding.video_id
                or metadata.get("distill_artifact_id") != publication.get("artifact_id")
                or metadata.get("distill_artifact_sha256") != publication.get("artifact_sha256")
                or seed.security != binding.security):
            raise ValueError("Published video IR security or lineage mismatch")
        text = seed.text.strip()
        row = {**metadata, "video_publication_id": publication["id"], "video_provenance_version": 1,
            "internal": False, "tenant_id": tenant_id, "visibility": binding.security.visibility,
            "owner_id": binding.security.owner_id, "security_scope": binding.security.security_scope,
            "source_file": source.file_name, "document_id": source.document_id,
            "parse_fingerprint": ir.parsed.parse_fingerprint(), "parser_backend": ir.parsed.parser_backend,
            "content_type": "doc_chunk", "series_codes": ",".join(metadata.get("series_codes") or []),
            "module_codes": ",".join(metadata.get("module_codes") or []),
            "context_prefix": "", "content": text, "raw_content": text}
        seed.metadata.update(internal=False, video_publication_id=publication["id"],
            video_provenance_version=1, video_provenance_signature=_sign_published_video_row(row))
    return result
