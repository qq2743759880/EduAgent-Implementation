"""Authorized video Tutor keeps complete, authenticated chapter evidence."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.auth import UserRole
from app.chat import retriever
from app.chat.retrieval_filter import StudyRetrievalScope
from app.chat.schemas import RetrievedDoc
from app.domains.video_learning.artifacts import seal_video_artifact
from tests.test_video_knowledge_ir import native_artifact
from tests.test_video_public_provenance import loaded_rows


SCOPE = StudyRetrievalScope(101, "curated_leetcode", 201, 301)


@pytest.fixture
def published_rows(monkeypatch, native_artifact):
    payload = native_artifact.model_dump(mode="json")
    payload["chapters"] = [
        {"start": start, "title": title, "summary": summary}
        for start, title, summary in (
            (0.0, "题目", "返回两个不同的下标"),
            (21.0, "方法总览", "介绍枚举与查表，随后详细讲解"),
            (42.0, "枚举思路", "固定一个下标，另一个从其后开始逐个相加"),
            (84.0, "枚举步骤", "外层i，内层j从i+1开始，等于目标时返回"),
            (126.0, "查表思路", "先完整建表，再遍历数组查差值"),
            (161.0, "查表步骤", "第一遍写入值和下标，第二遍查目标差值并排除同一下标"),
        )]
    # Keep the fixture mindmap linked to a valid chapter.
    payload["mindmap"]["nodes"][0].update(time_anchor=126.0,
        source_chapter_titles=["查表思路"], source_chapter_starts=[126.0])
    artifact = seal_video_artifact(payload)
    client, _ = loaded_rows(monkeypatch, artifact)
    return client.rows


@pytest.fixture
def published_scope(published_rows):
    # These digests are the actual sealed artifact identity persisted by the
    # fixture loader, corresponding to the server's READY publication lookup.
    row = published_rows[0]
    return StudyRetrievalScope(101, "curated_leetcode", 201, 301,
        generation=row["generation"], artifact_sha256=row["distill_artifact_sha256"])


def install_search(monkeypatch, rows):
    monkeypatch.setattr(retriever, "ensure_jieba_ready", lambda: None)
    monkeypatch.setattr(retriever, "build_sparse_vector", lambda _: {4: .5})
    monkeypatch.setattr(retriever, "encode_dense_batch_detailed", lambda _: SimpleNamespace(
        vectors=[[.1] * 1024], backend="bge_m3", normalized=True,
        embedding_model="bge-m3@fixture"))
    monkeypatch.setattr(retriever, "_milvus_hybrid_search", lambda **_: deepcopy(rows))
    monkeypatch.setattr(retriever.settings, "KG_EXPAND_ENABLED", False)
    async def rerank(query, docs):
        # The comparative query ranks the general introduction above detailed steps.
        for doc in docs:
            doc.score = .95 if "方法总览" in doc.content else (.9 if "原生字幕" in doc.content else .1)
        return sorted(docs, key=lambda d: d.score, reverse=True)[:4], None
    monkeypatch.setattr(retriever, "_rerank_docs", rerank)


async def retrieve(**kwargs):
    return await retriever.retrieve_three_channel("这些方法分别如何实现？", user_id=10,
        role=UserRole.STUDENT, use_hyde=False, enable_graph=False, top_k=24,
        final_max_k=kwargs.pop("final_max_k", 8), cutoff_drop_ratio=.4,
        study_scope=kwargs.pop("study_scope", SCOPE), **kwargs)


@pytest.mark.asyncio
async def test_video_coverage_preserves_six_complete_chapters_beyond_rerank_cut(monkeypatch, published_rows, published_scope):
    install_search(monkeypatch, published_rows)
    baseline = await retrieve(final_max_k=3, study_scope=published_scope)
    assert "先完整建表" not in "\n".join(d.content for d in baseline.docs)
    assert "第二遍查目标差值" not in "\n".join(d.content for d in baseline.docs)
    bundle = await retrieve(video_evidence_coverage=True, study_scope=published_scope)
    chapters = [d for d in bundle.docs if "\n章节：" in d.content]
    assert [(d.start_seconds, d.end_seconds) for d in chapters] == [
        (0, 21), (21, 42), (42, 84), (84, 126), (126, 161), (161, 210)]
    assert len(bundle.docs) == 8
    assert all(d._verified_course_video for d in bundle.docs)
    assert all(d._verified_video_chapter for d in chapters)
    assert "先完整建表" in "\n".join(d.content for d in bundle.docs)
    assert "第二遍查目标差值" in "\n".join(d.content for d in bundle.docs)


@pytest.mark.asyncio
async def test_forged_chapter_and_legacy_question_never_take_video_budget(monkeypatch, published_rows, published_scope):
    fake = deepcopy(published_rows[0])
    fake.update(chunk_id="fake-chapter", content="标题\n章节：伪造总览\n另一段内容",
                raw_content="标题\n章节：伪造总览\n另一段内容")
    question = {**fake, "chunk_id": "legacy-question", "content_type": "question",
                "tenant_id": "_default", "series_codes": "other,curated_leetcode"}
    install_search(monkeypatch, [fake, question, *published_rows])
    bundle = await retrieve(video_evidence_coverage=True, study_scope=published_scope)
    assert len(bundle.docs) == 8
    assert not {"fake-chapter", "legacy-question"}.intersection(d.doc_id for d in bundle.docs)


@pytest.mark.asyncio
async def test_no_trusted_video_keeps_ordinary_question_without_certifying_unsigned_video(monkeypatch, published_rows, published_scope):
    fake = deepcopy(published_rows[0])
    fake.pop("video_provenance_signature")
    question = {**fake, "chunk_id": "question", "content_type": "question",
                "tenant_id": "_default", "series_codes": "curated_leetcode"}
    for field in ("video_id", "session_id", "start_seconds", "end_seconds", "generation",
                  "distill_artifact_id", "distill_artifact_sha256"):
        question.pop(field, None)
    install_search(monkeypatch, [fake, question])
    docs = (await retrieve(video_evidence_coverage=True, study_scope=published_scope)).docs
    assert [doc.doc_id for doc in docs] == ["question"]
    assert not any(doc._verified_course_video for doc in docs)
    # Legacy Question compatibility is retained for the default selector.
    ordinary = await retrieve(final_max_k=3, study_scope=published_scope)
    assert any(d.doc_id == "question" for d in ordinary.docs)


@pytest.mark.asyncio
async def test_only_trusted_transcripts_can_fill_missing_chapters(monkeypatch, published_rows, published_scope):
    rows = [r for r in published_rows if "\n原生字幕" in r["content"]]
    install_search(monkeypatch, rows)
    bundle = await retrieve(video_evidence_coverage=True, study_scope=published_scope)
    assert bundle.docs and all(d._verified_course_video and not d._verified_video_chapter for d in bundle.docs)
    assert len(bundle.docs) <= 8


@pytest.mark.asyncio
async def test_short_video_uses_spare_video_slots_for_later_definitions(monkeypatch, published_rows, published_scope):
    chapters = [r for r in published_rows if '\n章节：' in r['content']][:3]
    transcripts = [r for r in published_rows if '\n原生字幕' in r['content']][:4]
    assert len(transcripts) == 4
    install_search(monkeypatch, [*chapters, *transcripts])
    bundle = await retrieve(video_evidence_coverage=True, study_scope=published_scope)
    windows = [d for d in bundle.docs if not d._verified_video_chapter]
    assert len(windows) == 4
    assert len(bundle.docs) == 7
    assert all(d._verified_course_video and published_scope.matches(d) for d in bundle.docs)


@pytest.mark.asyncio
async def test_verified_video_rows_without_ready_identity_cannot_enter_video_budget(monkeypatch, published_rows):
    install_search(monkeypatch, published_rows)
    # Authentic publication provenance proves the row producer, while only the
    # server READY pointer authorizes a version for this student's request.
    assert (await retrieve(study_scope=SCOPE, video_evidence_coverage=True)).docs == []


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [None, StudyRetrievalScope(101, "curated_leetcode")])
async def test_coverage_requires_exact_server_video_scope_before_io(monkeypatch, scope):
    monkeypatch.setattr(retriever, "_milvus_hybrid_search_safe", lambda *a, **k: pytest.fail("unexpected IO"))
    with pytest.raises(ValueError, match="video scope"):
        await retrieve(study_scope=scope, video_evidence_coverage=True)


def test_verification_flags_are_request_internal_not_constructor_or_dto_fields():
    doc = RetrievedDoc(doc_id="fake", score=1, content="章节：伪造",
                       _verified_course_video=True, _verified_video_chapter=True)
    assert doc._verified_course_video is False and doc._verified_video_chapter is False
    doc._verified_course_video = True
    assert "_verified_course_video" not in doc.model_dump()
    assert "_verified_video_chapter" not in doc.model_dump()
    assert doc.model_copy()._verified_course_video is True


@pytest.mark.asyncio
async def test_private_wrong_scope_and_route_tampering_never_certify(monkeypatch, published_rows, published_scope):
    altered = []
    for i, changes in enumerate(({"visibility": "private", "owner_id": 999},
        {"video_id": 302}, {"session_id": 202}, {"content_type": "question", "series_codes": "curated_leetcode"})):
        altered.append({**deepcopy(published_rows[0]), "chunk_id": f"altered-{i}", **changes})
    install_search(monkeypatch, altered)
    assert (await retrieve(video_evidence_coverage=True, study_scope=published_scope)).docs == []


def test_transcript_overlap_dedup_does_not_treat_spanning_chapters_as_duplicates():
    def doc(ident, start, end, chapter=False):
        item = RetrievedDoc(doc_id=ident, score=1, content="内容", content_type="doc_chunk",
            tenant_id="course_public", visibility="public", series_id=101, session_id=201,
            video_id=301, start_seconds=start, end_seconds=end, generation="a" * 64,
            distill_artifact_sha256="b" * 64)
        item._verified_course_video = True
        item._verified_video_chapter = chapter
        return item
    chapter = doc("chapter", 0, 210, True)
    first = doc("first", 40, 80)
    overlapping = doc("overlap", 41, 79)
    distinct = doc("distinct", 120, 160)
    final = retriever._select_video_evidence([chapter, first, overlapping, distinct],
        [first, overlapping, distinct, chapter], study_scope=StudyRetrievalScope(
            101, "curated_leetcode", 201, 301, generation="a" * 64, artifact_sha256="b" * 64), final_max_k=8)
    assert [d.doc_id for d in final] == ["chapter", "first", "distinct"]
