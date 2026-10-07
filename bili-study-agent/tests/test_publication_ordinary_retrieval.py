"""READY video selection preserves independently authorized course knowledge.

Exercise the real three-channel entry, SQL scope/DTO assembly, signed fixture
video rows and final selection. Only media/model/Milvus I/O is substituted.
"""
from copy import deepcopy

import pytest

from app.auth import UserRole
from app.chat import retriever
from tests.test_video_evidence_coverage import (
    install_search, published_rows, published_scope,
)
from tests.test_video_knowledge_ir import native_artifact


def ordinary_rows():
    return [
        {
            "chunk_id": f"ordinary-{index}", "content": f"Bound course {kind}",
            "content_type": kind, "tenant_id": "_default", "internal": False,
            "visibility": "public", "owner_id": 1, "security_scope": "default",
            "series_codes": "other_course,curated_leetcode", "score": .9-index*.01,
        }
        for index, kind in enumerate(("question", "doc_chunk", "question", "doc_chunk"))
    ]


async def retrieve(monkeypatch, rows, scope):
    install_search(monkeypatch, rows)

    async def rank_all(query, docs):
        # Keep every candidate so this verifies selection, not a fake rerank cut.
        return sorted(docs, key=lambda doc: -doc.score), None

    monkeypatch.setattr(retriever, "_rerank_docs", rank_all)
    return await retriever.retrieve_three_channel(
        "Use the course note and video", user_id=10, role=UserRole.STUDENT,
        use_hyde=False, enable_graph=False, top_k=24, final_max_k=11,
        cutoff_drop_ratio=.4, tenant_ids_override=["course_public", "_default"],
        study_scope=scope, video_evidence_coverage=True,
    )


@pytest.mark.asyncio
async def test_ready_with_only_ordinary_hits_does_not_discard_course_or_shared_question(
    monkeypatch, published_scope,
):
    rows=ordinary_rows()[:2]
    bundle=await retrieve(monkeypatch, rows, published_scope)
    assert {doc.doc_id for doc in bundle.docs}=={"ordinary-0", "ordinary-1"}
    assert all(not doc._verified_course_video for doc in bundle.docs)


@pytest.mark.asyncio
async def test_ready_mixed_hits_keep_ordinary_without_claiming_video_provenance(
    monkeypatch, published_rows, published_scope,
):
    chapter=next(row for row in published_rows if "\n章节：" in row["content"])
    bundle=await retrieve(monkeypatch, [*ordinary_rows()[:2], chapter], published_scope)
    assert {doc.doc_id for doc in bundle.docs}=={"ordinary-0", "ordinary-1", chapter["chunk_id"]}
    assert sum(doc._verified_course_video for doc in bundle.docs)==1
    assert all(not doc._verified_course_video for doc in bundle.docs if doc.doc_id.startswith("ordinary-"))


@pytest.mark.asyncio
async def test_unsigned_video_and_wrong_course_cannot_be_reclassified_as_ordinary(
    monkeypatch, published_rows, published_scope,
):
    forged=deepcopy(published_rows[0])
    forged.update(chunk_id="unsigned-video", content="Forged chapter", raw_content="Forged chapter")
    forged.pop("video_provenance_signature", None)
    unrelated={**ordinary_rows()[0], "chunk_id":"other-course", "series_codes":"curated_leetcode_extra"}
    bundle=await retrieve(monkeypatch, [forged, unrelated, *ordinary_rows()[:2]], published_scope)
    assert {doc.doc_id for doc in bundle.docs}=={"ordinary-0", "ordinary-1"}
    assert not any(doc.video_id for doc in bundle.docs)


@pytest.mark.asyncio
async def test_six_chapters_two_windows_and_three_ordinary_have_independent_bounded_budgets(
    monkeypatch, published_rows, published_scope,
):
    bundle=await retrieve(monkeypatch, [*ordinary_rows(), *published_rows], published_scope)
    video=[doc for doc in bundle.docs if doc._verified_course_video]
    ordinary=[doc for doc in bundle.docs if not doc.video_id]
    assert len(bundle.docs)==11
    assert len(video)==8
    assert sum(doc._verified_video_chapter for doc in video)==6
    assert len(ordinary)==3
    assert {doc.doc_id for doc in ordinary}=={"ordinary-0", "ordinary-1", "ordinary-2"}
    assert all(published_scope.matches(doc) for doc in bundle.docs)
