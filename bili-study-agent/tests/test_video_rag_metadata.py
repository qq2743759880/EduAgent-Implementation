"""Video seed metadata survives the existing Milvus loader and retrieval seam."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.knowledge.importer import loader
from app.knowledge.models import KnowledgeChunk
from app.knowledge.video_metadata import VIDEO_METADATA_FIELDS


META = {
    "series_id": 401, "session_id": 501, "video_id": 601,
    "start_seconds": 120.25, "end_seconds": 160.5,
    "distill_artifact_id": "native-p1", "distill_artifact_sha256": "a" * 64,
    "source_bvid": "BV1xa411A76q", "source_cid": 295285948,
    "compiler_version": "1", "generation": "native-p1-generation",
}


class Client:
    def __init__(self):
        self.rows = []
        self.search = None

    def upsert(self, **kwargs):
        self.rows.extend(deepcopy(kwargs["data"]))

    def query(self, **kwargs):
        return []

    def list_partitions(self, *args):
        return ["course_public"]

    def hybrid_search(self, **kwargs):
        self.search = kwargs
        return [[{"id": row["id"], "distance": .99, "entity": row} for row in self.rows]]


def fixture_loader(monkeypatch):
    client = Client()
    monkeypatch.setattr(loader, "get_milvus_client", lambda: client)
    monkeypatch.setattr(loader, "ensure_collection_exists", lambda: None)
    monkeypatch.setattr(loader, "ensure_partition_exists", lambda tenant: tenant)
    return client


def chunk(metadata=None):
    return KnowledgeChunk(
        chunk_id="video-metadata-test", content="用哈希表查找目标值与当前数的差。",
        raw_content="用哈希表查找目标值与当前数的差。", source_file="two-sum.json",
        content_type="doc_chunk",
        visibility="public", owner_id=1, security_scope="default",
        document_id="new-video-document", parse_fingerprint="native-video-fp",
        dense_vector=[0.1] * 1024, sparse_indices=[4], sparse_values=[.5],
        series_codes=["CURATED_V1", "LC_GOLDEN"],
        extra={"security_scope": "default", "generation_state": "active",
               "seed_metadata": dict(META if metadata is None else metadata)},
    )


def test_video_metadata_roundtrip_keeps_numeric_types_and_security(monkeypatch):
    client = fixture_loader(monkeypatch)
    assert loader.load_chunks([chunk()], "course_public") == 1
    row = client.rows[0]
    assert {key: row[key] for key in META} == META
    assert all(key not in row for key in ("source_kind", "source_asset_id", "source_media_sha256"))
    assert type(row["series_id"]) is type(row["session_id"]) is type(row["video_id"]) is int
    assert type(row["start_seconds"]) is float
    assert row["series_codes"] == "CURATED_V1,LC_GOLDEN"
    assert (row["tenant_id"], row["visibility"], row["owner_id"], row["security_scope"]) == (
        "course_public", "public", 1, "default",
    )
    hits = loader.hybrid_search([.1] * 1024, {4: .5}, ["course_public"], include_internal=True)
    assert set(VIDEO_METADATA_FIELDS).issubset(client.search["output_fields"])
    assert {key: hits[0][key] for key in META} == META
    assert all(hits[0][key] is None for key in ("source_kind", "source_asset_id", "source_media_sha256"))
    assert hits[0]["series_codes"] == "CURATED_V1,LC_GOLDEN"


@pytest.mark.parametrize("override", [
    {"end_seconds": 120.25}, {"start_seconds": float("nan")},
    {"start_seconds": False},
    {"session_id": "session_legacy"}, {"video_id": True},
    {"distill_artifact_sha256": "unverified"},
])
def test_invalid_video_metadata_rejected_before_any_write(monkeypatch, override):
    client = fixture_loader(monkeypatch)
    with pytest.raises(ValidationError):
        loader.load_chunks([chunk({**META, **override})], "course_public")
    assert client.rows == []


def test_incomplete_video_metadata_rejected_before_any_write(monkeypatch):
    client = fixture_loader(monkeypatch)
    with pytest.raises(ValidationError):
        loader.load_chunks([chunk({"video_id": 601})], "course_public")
    assert client.rows == []


def test_legacy_question_metadata_retains_csv_and_session_string(monkeypatch):
    client = fixture_loader(monkeypatch)
    assert loader.load_chunks([chunk({"session_id": "session_legacy", "source_table": "question"})]) == 1
    assert client.rows[0]["session_id"] == "session_legacy"
    assert client.rows[0]["series_codes"] == "CURATED_V1,LC_GOLDEN"
    assert "video_id" not in client.rows[0]


def test_video_primary_key_collision_never_overwrites_existing_namespace(monkeypatch):
    client = fixture_loader(monkeypatch)

    def collision(**kwargs):
        key = int(kwargs["filter"].split("[")[1].split("]")[0])
        return [{"id": key, "chunk_id": "another-document", "tenant_id": "_default"}]

    monkeypatch.setattr(client, "query", collision)
    with pytest.raises(ValueError, match="existing namespace"):
        loader.load_chunks([chunk()], "course_public")
    assert client.rows == []


def test_bounded_embedding_rejects_a_cloud_batch_even_when_last_batch_is_local(monkeypatch):
    from app.knowledge.importer import embedder
    from app.knowledge.models import ImportState

    calls = []

    def mixed(texts):
        backend = "cloud" if not calls else "bge_m3"
        calls.append(backend)
        return embedder.DenseResult(vectors=[[.1] * 1024 for _ in texts], backend=backend,
            normalized=backend == "bge_m3", precision="fp16", embedding_model="bge-m3@revision", max_length=8192)

    monkeypatch.setattr(embedder.settings, "EMBED_BATCH_SIZE", 1)
    monkeypatch.setattr(embedder, "encode_dense_batch_detailed", mixed)
    state = ImportState(task_id="bounded-video", chunks=[chunk(), chunk()], tenant_id="course_public",
                        extra={"required_embedding_backend": "bge_m3"})
    patch = embedder.embed_node(state)
    assert calls == ["cloud", "bge_m3"]
    assert "Embedding backend requirement failed" in patch["error"]
    assert "chunks" not in patch
