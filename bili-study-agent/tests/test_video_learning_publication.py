"""Publication public behavior with local SQL and the real object-store adapter.

Run with --noconftest: these tests never connect to shared Redis/SQL/MinIO.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import uuid

import pytest

from app.common.exceptions import AppException
from app.domains.learning import study_context
from app.domains.video_learning import playback, publication
from app.domains.video_learning.artifacts import seal_video_artifact
from app.services.source_asset_store import SourceAssetError, SourceAssetStore


@pytest.fixture
def local():
    # Normal workspace ACLs avoid pytest's inaccessible Windows mode=0700 path.
    root = Path(__file__).resolve().parents[1] / "data/video_distill/.tests"
    path = root / uuid.uuid4().hex
    path.mkdir(parents=True)
    yield path
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_relative_to(root.resolve(strict=True)):
        raise RuntimeError("test cleanup escaped its bounded fixture root")
    shutil.rmtree(resolved)


@pytest.fixture
def artifact(local):
    fingerprint = {"path": "fixture.json", "sha256": "a" * 64, "size_bytes": 10}
    payload = {
        "schema_version": 2, "quality": "native_compiled",
        "source": {"platform": "bilibili", "bvid": "BV1xa411A76q", "page": 1,
                   "cid": 295285948, "url": "https://www.bilibili.com/video/BV1xa411A76q?p=1",
                   "title": "两数之和", "duration": 10.0},
        "transcript": {"full_text": "返回不同下标", "segments": [
            {"start": 0.0, "end": 3.0, "text": "返回不同下标"}]},
        "chapters": [{"title": "题目", "start": 0.0, "summary": "返回两个下标"}],
        "summary": {"title": "两数之和", "overview": "返回两个下标", "key_points": ["不同下标"]},
        "knowledge_note": "# 两数之和\n\n返回两个不同下标。",
        "mindmap": {"version": 1, "title": "两数之和", "root": "root", "nodes": [
            {"id": "root", "label": "题目", "type": "leaf", "summary": "不同下标", "children": [],
             "time_anchor": 0.0, "source_chapter_titles": ["题目"], "source_chapter_starts": [0.0]}]},
        "compiler": {"name": "EduVideoCompiler", "version": "1", "transcript_origin": "platform_subtitle",
            "subtitle": fingerprint, "discovery": fingerprint, "code_files": [fingerprint],
            "upstream_repo": "https://github.com/lycohana/BiliSum.git", "upstream_head": "b" * 40,
            "upstream_license": "MIT", "upstream_source_files": [fingerprint],
            "llm_runs": [{"stage": stage, "provider": "openai-compatible", "model": "fixture-model",
                "request_sha256": "c" * 64, "response_sha256": "d" * 64,
                "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
                for stage in ("summary", "knowledge_note", "mindmap")]},
    }
    model = seal_video_artifact(payload)
    path = local / "artifact.json"
    path.write_text(json.dumps(model.model_dump(mode="json"), ensure_ascii=False,
                               sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return path, model


class MemoryMinio:
    def __init__(self):
        self.objects = {}
        self.puts = 0

    def put_object(self, *, bucket_name, object_name, data, length, content_type):
        raw = data.read()
        assert len(raw) == length and content_type == "application/json"
        self.objects[(bucket_name, object_name)] = raw
        self.puts += 1

    def get_object(self, bucket, key):
        if (bucket, key) not in self.objects:
            error = RuntimeError("missing fixture object")
            error.code = "NoSuchKey"
            raise error
        stream = io.BytesIO(self.objects[(bucket, key)])
        stream.release_conn = lambda: None
        return stream


@pytest.fixture
def storage(monkeypatch):
    client = MemoryMinio()
    monkeypatch.setattr(publication, "SourceAssetStore", lambda: SourceAssetStore(client=client))
    return client


@pytest.fixture
def database(monkeypatch):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.create_function("JSON_UNQUOTE", 1, lambda value: value)
    connection.executescript("""
        CREATE TABLE series(id INTEGER,series_code TEXT,series_name TEXT);
        CREATE TABLE series_cohort(id INTEGER,series_id INTEGER);
        CREATE TABLE series_cohort_course(id INTEGER,cohort_id INTEGER,module_code TEXT,module_name TEXT);
        CREATE TABLE series_cohort_session(id INTEGER,series_cohort_course_id INTEGER,
            session_title TEXT,teaching_status TEXT);
        CREATE TABLE student_cohort_rel(id INTEGER,user_id INTEGER,cohort_id INTEGER,enroll_status TEXT);
        CREATE TABLE session_asset(id INTEGER,session_id INTEGER,asset_name TEXT,
            material_category TEXT,access_scope TEXT,sort_no INTEGER);
        CREATE TABLE session_video(id INTEGER,asset_id INTEGER,video_code TEXT,
            video_title TEXT,duration_seconds INTEGER,transcode_status TEXT);
        CREATE TABLE graph_node(id INTEGER,parent_id INTEGER,label TEXT,code TEXT,name TEXT,yn INTEGER,properties_json TEXT);
        CREATE TABLE graph_edge(from_node_id INTEGER,to_node_id INTEGER,rel_type TEXT,yn INTEGER);
        CREATE TABLE student_profile(user_id INTEGER,learning_goal_id INTEGER,yn INTEGER);
        CREATE TABLE dim_learning_goal(id INTEGER,goal_code TEXT,goal_name TEXT,yn INTEGER);
        CREATE TABLE video_learning_publication(id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER,artifact_id TEXT,artifact_sha256 TEXT,object_sha256 TEXT,
            bucket TEXT,object_key TEXT,size_bytes INTEGER,rag_status TEXT DEFAULT 'ready',
            previous_publication_id INTEGER,activated_at TEXT,UNIQUE(video_id,artifact_sha256));
        CREATE TABLE video_learning_exercise(video_id INTEGER,generation TEXT,artifact_sha256 TEXT,
            bank_id INTEGER,question_count INTEGER,package_sha256 TEXT);
        INSERT INTO series VALUES(7,'LEET','LeetCode 算法题精讲');
        INSERT INTO series_cohort VALUES(70,7);
        INSERT INTO series_cohort_course VALUES(700,70,'LEET1','两数之和');
        INSERT INTO series_cohort_session VALUES(7000,700,'两数之和','completed');
        INSERT INTO student_cohort_rel VALUES(1,101,70,'active');
        INSERT INTO session_asset VALUES(5,7000,'视频','video','enrolled_only',1);
        INSERT INTO session_video VALUES(4,5,'BV1xa411A76q_P1_295285948','两数之和',10,'completed');
    """)

    async def fetch_one(sql, params=()):
        row = connection.execute(sql.replace("%s", "?"), params).fetchone()
        return dict(row) if row else None

    async def fetch_all(sql, params=()):
        return [dict(row) for row in connection.execute(sql.replace("%s", "?"), params).fetchall()]

    class Cursor:
        async def execute(self, sql, params=()):
            connection.execute(sql.replace("INSERT IGNORE", "INSERT OR IGNORE").replace("%s", "?"), params)

    @asynccontextmanager
    async def transaction():
        try:
            yield connection, Cursor()
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    monkeypatch.setattr(publication, "fetch_one", fetch_one)
    monkeypatch.setattr(publication, "transaction", transaction)
    from app.domains.video_learning import exercises
    monkeypatch.setattr(exercises, "fetch_one", fetch_one)
    monkeypatch.setattr(study_context, "fetch_one", fetch_one)
    monkeypatch.setattr(study_context, "fetch_all", fetch_all)
    yield connection
    connection.close()


@pytest.mark.asyncio
async def test_publish_roundtrip_has_real_content_without_operator_provenance(database, storage, artifact):
    path, model = artifact
    row = await publication.publish_video_artifact(4, path)
    result = await publication.get_video_knowledge(7000, 101)
    assert storage.puts == 1
    assert result["series_id"] == 7 and result["video_id"] == 4
    assert result["artifact_id"] == model.content_sha256
    assert result["transcript"]["segments"][0]["start"] == 0
    assert result["knowledge_note"] == model.knowledge_note and "compiler" not in result
    assert row["object_sha256"] == hashlib.sha256(next(iter(storage.objects.values()))).hexdigest()


@pytest.mark.asyncio
async def test_reformatted_identical_artifact_reuses_verified_object_without_overwrite(database, storage, artifact):
    path, model = artifact
    first = await publication.publish_video_artifact(4, path)
    original = dict(storage.objects)
    path.write_text(json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8")
    assert await publication.publish_video_artifact(4, path) == first
    assert storage.puts == 1 and storage.objects == original
    assert (await publication.get_video_knowledge(7000, 101))["artifact_id"] == model.content_sha256


@pytest.mark.asyncio
async def test_existing_pointer_conflict_is_rejected_before_object_write(database, storage, artifact):
    path, _ = artifact
    await publication.publish_video_artifact(4, path)
    original = dict(storage.objects)
    database.execute("UPDATE video_learning_publication SET object_sha256=?", ("0" * 64,))
    with pytest.raises(ValueError, match="reference conflicts"):
        await publication.publish_video_artifact(4, path)
    assert storage.puts == 1 and storage.objects == original


@pytest.mark.asyncio
async def test_unpublished_object_conflict_is_never_overwritten(database, storage, artifact):
    path, model = artifact
    key = f"video/{model.content_sha256}/{model.artifact_sha256}.json"
    identity = (publication.settings.MINIO_BUCKET_ARTIFACTS, key)
    storage.objects[identity] = b"conflicting existing object"
    with pytest.raises(SourceAssetError, match="sha256 mismatch"):
        await publication.publish_video_artifact(4, path)
    assert storage.puts == 0 and storage.objects[identity] == b"conflicting existing object"
    assert database.execute("SELECT COUNT(*) FROM video_learning_publication").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_verified_orphan_object_is_reused_after_db_handoff_failure(database, storage, artifact):
    path, _ = artifact
    first = await publication.publish_video_artifact(4, path)
    database.execute("DELETE FROM video_learning_publication")
    restored = await publication.publish_video_artifact(4, path)
    assert restored["object_sha256"] == first["object_sha256"] and storage.puts == 1


@pytest.mark.asyncio
async def test_student_authorization_precedes_object_read(database, storage, artifact):
    path, _ = artifact
    await publication.publish_video_artifact(4, path)
    with pytest.raises(AppException) as error:
        await publication.get_video_knowledge(7000, 102)
    assert error.value.http_status == 403
    # Even a user enrolled in another cohort of this series may not access this one.
    database.execute("INSERT INTO series_cohort VALUES(71,7)")
    database.execute("INSERT INTO student_cohort_rel VALUES(2,102,71,'active')")
    with pytest.raises(AppException) as error:
        await publication.get_video_knowledge(7000, 102)
    assert error.value.http_status == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("video_code", "BV1xa411A76q_P2_295285949"),
    ("duration_seconds", 20), ("transcode_status", "pending")])
async def test_publication_rejects_wrong_source_or_unverified_video_before_write(database, storage, artifact, field, value):
    path, _ = artifact
    database.execute(f"UPDATE session_video SET {field}=?", (value,))
    with pytest.raises(ValueError):
        await publication.publish_video_artifact(4, path)
    assert storage.puts == 0 and not storage.objects
    assert database.execute("SELECT COUNT(*) FROM video_learning_publication").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_knowledge_object_failure_is_independent_of_playback(database, storage, artifact, monkeypatch):
    path, _ = artifact
    row = await publication.publish_video_artifact(4, path)
    del storage.objects[(row["bucket"], row["object_key"])]
    with pytest.raises(AppException) as error:
        await publication.get_video_knowledge(7000, 101)
    assert error.value.http_status == 503 and "继续观看视频" in error.value.message
    calls = []

    class Signer:
        def presigned_get_object(self, bucket, key, *, expires):
            calls.append((bucket, key, expires.total_seconds()))
            return "https://media.invalid/verified-video?signature=opaque"

    monkeypatch.setattr(playback, "get_minio_signing_client", lambda: Signer())
    assert playback.playback_url(f"minio://{playback.settings.MINIO_BUCKET_COURSE}/video/golden.mp4").endswith("signature=opaque")
    assert calls[0][1:] == ("video/golden.mp4", 3600)


@pytest.mark.parametrize("reference", ["minio://other/video/golden.mp4", "minio://edu-course/../video/golden.mp4",
    "minio://edu-course/video//golden.mp4", "minio://edu-course/video/golden.mp4?secret=x"])
def test_playback_rejects_storage_reference_outside_course_boundary(reference):
    with pytest.raises(ValueError):
        playback.playback_url(reference)


def test_prompt_video_evidence_preserves_document_number_and_source_time_range():
    from app.chat.generator import format_docs_for_prompt
    from app.chat.schemas import RetrievedDoc

    docs = [RetrievedDoc(doc_id="question", score=.8, content="本课相关题目", content_type="question"),
        RetrievedDoc(doc_id="video", score=.9, content="查询差值后返回两个不同下标", content_type="course",
                     series_id=7, session_id=7000, video_id=4, start_seconds=64.5, end_seconds=128.25)]
    result = format_docs_for_prompt(docs)
    assert "doc[1]" in result and "doc[2] [视频依据=01:04–02:08]" in result
    assert "用 doc[N] 标明" in result and "只依据材料描述视频讲解" in result
    assert "series_id" not in result and "session_id" not in result and "video_id" not in result
