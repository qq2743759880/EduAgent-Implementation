"""Native transcript and chapter ranges survive existing IR chunk preparation."""
import pytest

from app.domains.video_learning.artifacts import seal_video_artifact
from app.domains.video_learning.knowledge_ir import VideoKnowledgeBinding, build_video_ir
from app.knowledge.chunk_preparation import prepare_chunks
from app.knowledge.ir import SourceAssetRef, SecurityMeta
from app.knowledge.video_metadata import VideoKnowledgeMetadata


@pytest.fixture
def native_artifact():
    fingerprint = {"path": "test-input", "sha256": "a" * 64, "size_bytes": 12}
    stages = [{"stage": stage, "provider": "openai-compatible", "model": "fixture-model",
               "request_sha256": "b" * 64, "response_sha256": "c" * 64,
               "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
              for stage in ("summary", "knowledge_note", "mindmap")]
    return seal_video_artifact({
        "schema_version": 2, "quality": "native_compiled",
        "source": {"platform": "bilibili", "bvid": "BV1xa411A76q", "page": 1, "cid": 295285948,
                   "url": "https://www.bilibili.com/video/BV1xa411A76q?p=1", "title": "两数之和", "duration": 210.0},
        "transcript": {"full_text": "真实字幕原文", "segments": [
            {"start": float(i * 7), "end": float(i * 7 + 6), "text": f"字幕片段{i:02d}：检查哈希表的差值"}
            for i in range(30)]},
        "chapters": [{"title": "题目与暴力", "start": 0.0, "summary": "暴力算法枚举所有两个下标组合"},
                     {"title": "哈希表", "start": 70.0, "summary": "用哈希表查询目标差值"}],
        "summary": {"title": "两数之和", "overview": "whole-overview-do-not-embed", "key_points": ["返回下标"]},
        "knowledge_note": "whole-note-do-not-embed",
        "mindmap": {"version": 1, "title": "两数之和", "root": "root", "nodes": [
            {"id": "root", "label": "哈希表", "type": "root", "summary": "目标差值", "children": [],
             "time_anchor": 70.0, "source_chapter_titles": ["哈希表"], "source_chapter_starts": [70.0]}]},
        "compiler": {"name": "EduVideoCompiler", "version": "1", "transcript_origin": "platform_subtitle",
                     "subtitle": fingerprint, "discovery": fingerprint, "code_files": [fingerprint],
                     "upstream_repo": "https://github.com/lycohana/BiliSum.git", "upstream_head": "d" * 40,
                     "upstream_license": "MIT", "upstream_source_files": [fingerprint], "llm_runs": stages},
    })


def build(artifact, owner=9):
    return build_video_ir(artifact,
        source=SourceAssetRef(bucket="edu-artifacts", object_key="video/real/artifact.json", sha256="f" * 64,
                              document_id="new-native-document", file_name="p1.native.json", mime="application/json"),
        binding=VideoKnowledgeBinding(series_id=101, session_id=201, video_id=301,
            series_code="curated_leetcode", series_name="LeetCode 精讲", module_code="two_sum",
            security=SecurityMeta(visibility="public", owner_id=owner, security_scope="default")),
        task_id="one-new-video-task", asset_id="one-new-source-asset")


def test_native_windows_and_chapters_enter_existing_chunks_with_complete_lineage(native_artifact):
    ir = build(native_artifact)
    windows = [seed for seed in ir.seeds if seed.metadata["video_knowledge_kind"] == "transcript"]
    assert len(windows) == 6
    assert all(30 <= seed.metadata["end_seconds"] - seed.metadata["start_seconds"] <= 45 for seed in windows)
    for i in range(30):
        assert sum(seed.text.count(f"字幕片段{i:02d}") for seed in windows) == 1
    chapters = [seed for seed in ir.seeds if seed.metadata["video_knowledge_kind"] == "chapter"]
    assert [(seed.metadata["start_seconds"], seed.metadata["end_seconds"]) for seed in chapters] == [(0, 70), (70, 210)]
    assert all("whole-overview" not in seed.text and "whole-note" not in seed.text for seed in ir.seeds)
    chunks = prepare_chunks(ir.parsed, ir.seeds, tenant_id="course_public")
    assert len(chunks) == 8
    for chunk in chunks:
        metadata = VideoKnowledgeMetadata.model_validate(chunk.extra["seed_metadata"])
        assert (metadata.series_id, metadata.session_id, metadata.video_id) == (101, 201, 301)
        assert metadata.generation == native_artifact.content_sha256
        assert metadata.distill_artifact_sha256 == native_artifact.artifact_sha256
        assert (chunk.tenant_id, chunk.visibility.value, chunk.owner_id, chunk.extra["security_scope"]) == (
            "course_public", "public", 9, "default")
        assert chunk.extra["document_id"] == "new-native-document"
        assert chunk.series_code == "curated_leetcode"


def test_binding_changes_parse_fingerprint_even_with_identical_artifact(native_artifact):
    assert build(native_artifact).parsed.parse_fingerprint() != build(native_artifact, owner=10).parsed.parse_fingerprint()


def test_candidate_cannot_enter_video_ir(native_artifact):
    candidate = native_artifact.model_copy(update={"quality": "candidate_requires_native_recompile"})
    with pytest.raises(ValueError, match="fresh native"):
        build(candidate)
