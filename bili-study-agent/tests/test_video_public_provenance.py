"""Published video proof keeps teaching visible without weakening legacy ACLs."""
from copy import deepcopy

import pytest

from tests.test_video_knowledge_ir import native_artifact
from tests.test_video_rag_metadata import fixture_loader
from app.domains.video_learning.knowledge_ir import (
    VideoKnowledgeBinding, build_video_ir, certify_published_video_ir,
)
from app.knowledge.chunk_preparation import prepare_chunks
from app.knowledge.importer import loader
from app.knowledge.ir import SourceAssetRef, SecurityMeta
from app.knowledge.video_metadata import is_trusted_public_video


def published_ir(artifact, visibility="public"):
    binding = VideoKnowledgeBinding(series_id=101, session_id=201, video_id=301,
        series_code="curated_leetcode", series_name="LeetCode 精讲", module_code="two_sum",
        security=SecurityMeta(visibility=visibility, owner_id=9, security_scope="default"))
    source = SourceAssetRef(bucket="edu-artifacts", object_key="video/real/artifact.json", sha256="f" * 64,
        document_id="d" * 32, file_name="p1.native.json", mime="application/json")
    publication = {"id": 71, "video_id": 301, "bucket": source.bucket, "object_key": source.object_key,
        "object_sha256": source.sha256, "artifact_id": artifact.content_sha256,
        "artifact_sha256": artifact.artifact_sha256}
    ir = build_video_ir(artifact, source=source, binding=binding, task_id="one-video", asset_id="one-asset")
    return ir, binding, publication


def loaded_rows(monkeypatch, artifact):
    ir, binding, publication = published_ir(artifact)
    assert all("video_provenance_signature" not in seed.metadata for seed in ir.seeds)
    certified = certify_published_video_ir(ir, publication=publication, binding=binding, tenant_id="course_public")
    chunks = prepare_chunks(certified.parsed, certified.seeds, tenant_id="course_public")
    assert all(chunk.extra.get("contextualization_skipped") is True for chunk in chunks)
    for chunk in chunks:
        chunk.dense_vector = [.1] * 1024
        chunk.sparse_indices = [4]
        chunk.sparse_values = [.5]
    client = fixture_loader(monkeypatch)
    monkeypatch.setattr(loader, "classify_internal", lambda *a, **k: True)
    assert loader.load_chunks(chunks, "course_public") == len(chunks)
    return client, chunks


def test_verified_producer_loader_and_student_search_override_only_false_positive(monkeypatch, native_artifact):
    client, chunks = loaded_rows(monkeypatch, native_artifact)
    assert all(row["internal"] is False and is_trusted_public_video(row) for row in client.rows)
    hits = loader.hybrid_search([.1] * 1024, {4: .5}, ["course_public"], include_internal=False)
    assert len(hits) == len(chunks)
    assert all(is_trusted_public_video(row) for row in hits)


@pytest.mark.parametrize("field,value", [
    ("content", "另一段保密内容"), ("raw_content", "另一段原文"), ("context_prefix", "伪造前缀"),
    ("owner_id", 10), ("video_id", 302), ("session_id", 202), ("series_id", 102),
    ("tenant_id", "institution_9"), ("security_scope", "institution_9"), ("visibility", "private"),
    ("document_id", "e" * 32), ("parse_fingerprint", "e" * 16), ("source_cid", 295285949),
    ("generation", "another-generation"), ("distill_artifact_sha256", "e" * 64),
    ("source_file", "another.json"), ("compiler_version", "2"), ("parser_backend", "client-upload"),
    ("series_code", "another_course"), ("series_codes", "another_course"), ("module_code", "other"),
    ("module_codes", "other"), ("content_type", "question"), ("video_publication_id", 72),
    ("video_provenance_signature", "0" * 64), ("video_provenance_version", True),
    ("internal", True), ("internal", "false"), ("internal", 0),
])
def test_forged_or_copied_proof_preserves_legacy_classifier(monkeypatch, native_artifact, field, value):
    client, _ = loaded_rows(monkeypatch, native_artifact)
    row = deepcopy(client.rows[0])
    row[field] = value
    assert not is_trusted_public_video(row)
    client.rows = [row]
    assert loader.hybrid_search([.1] * 1024, {4: .5}, ["course_public"], include_internal=False) == []


def test_candidate_to_active_changes_derived_id_only_preserve_document_bound_proof(monkeypatch, native_artifact):
    client, _ = loaded_rows(monkeypatch, native_artifact)
    row = {**client.rows[0], "id": 999, "chunk_id": "derived-active-id", "generation_state": "active"}
    assert is_trusted_public_video(row)


def test_private_native_ir_and_legacy_false_never_get_exception(monkeypatch, native_artifact):
    ir, binding, publication = published_ir(native_artifact, "private")
    result = certify_published_video_ir(ir, publication=publication, binding=binding, tenant_id="course_public")
    assert all("video_provenance_signature" not in seed.metadata for seed in result.seeds)
    monkeypatch.setattr(loader, "classify_internal", lambda *a, **k: True)
    assert loader._row_is_internal({"internal": False, "content_type": "question", "content": "内部资料"})


def test_unsigned_uploaded_metadata_cannot_mint_proof(monkeypatch, native_artifact):
    ir, _, _ = published_ir(native_artifact)
    chunks = prepare_chunks(ir.parsed, ir.seeds, tenant_id="course_public")
    client = fixture_loader(monkeypatch)
    monkeypatch.setattr(loader, "classify_internal", lambda *a, **k: True)
    for chunk in chunks:
        chunk.extra["internal"] = False
        chunk.extra["seed_metadata"].update(internal=False, video_publication_id=71, video_provenance_version=1)
        chunk.dense_vector = [.1] * 1024
    loader.load_chunks(chunks, "course_public")
    assert all(row["internal"] is True and "video_provenance_signature" not in row for row in client.rows)


@pytest.mark.parametrize("field,value", [("object_sha256", "e" * 64), ("video_id", 999),
    ("object_key", "video/other.json"), ("artifact_id", "e" * 64), ("artifact_sha256", "e" * 64)])
def test_publication_pointer_and_binding_mismatch_cannot_certify(native_artifact, field, value):
    ir, binding, publication = published_ir(native_artifact)
    with pytest.raises(ValueError, match="mismatch"):
        certify_published_video_ir(ir, publication={**publication, field: value}, binding=binding, tenant_id="course_public")
