"""Retained older vectors cannot consume the current publication's ANN budget."""
import json
import re
import sqlite3
from types import SimpleNamespace
import pytest
from app.auth.schemas import UserRole
from app.chat.retrieval_filter import RetrievalFilter,StudyRetrievalScope,compile_retrieval_filter


def expression(scope):
    return compile_retrieval_filter(RetrievalFilter(tenant_scope=["course_public","_default"],study_scope=scope),
        caller="flows_agent_legacy",user_id=10,role=UserRole.STUDENT).expression


def test_ready_generation_filters_old_and_pending_vectors_before_both_ann_channels(monkeypatch):
    from tests.test_video_rag_metadata import fixture_loader
    from app.knowledge.importer import loader
    scope=StudyRetrievalScope(2,"course_a",12,4,generation="a"*64,artifact_sha256="b"*64)
    expr=expression(scope)
    values=[]
    def bind(match):values.append(json.loads(match.group()));return "?"
    sql=re.sub(r'"(?:\\.|[^"\\])*"',bind,expr).replace(" in ["," in (").replace("]",")")
    sql=re.sub(r"\blike \?","like ? ESCAPE '\\'",sql)
    sql=re.sub(r"\bnot exists video_id\b","video_id IS NULL",sql)
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE chunks(id TEXT,tenant_id TEXT,internal BOOL,content_type TEXT,series_id INTEGER,series_code TEXT,series_codes TEXT,session_id INTEGER,video_id INTEGER,generation TEXT,distill_artifact_sha256 TEXT)")
        rows=[("ready","course_public",False,"doc_chunk",2,"course_a","",12,4,"a"*64,"b"*64),
              ("old","course_public",False,"doc_chunk",2,"course_a","",12,4,"c"*64,"d"*64),
              ("pending","course_public",False,"doc_chunk",2,"course_a","",12,4,"e"*64,"f"*64),
              ("other_provenance","course_public",False,"doc_chunk",2,"course_a","",12,4,"a"*64,"f"*64),
              ("question","_default",False,"question",None,"course_a","",None,None,None,None),
              ("ordinary-course-doc","course_public",False,"doc_chunk",None,"","other,course_a",None,None,None,None)]
        db.executemany("INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?,?,?)",rows)
        assert {row[0] for row in db.execute("SELECT id FROM chunks WHERE "+sql,values)}=={"ready","question","ordinary-course-doc"}
    client=fixture_loader(monkeypatch)
    loader.hybrid_search([.1]*1024,{4:.5},["course_public"],include_internal=True,filter_expr=expr)
    assert client.search["reqs"][0].expr==client.search["reqs"][1].expr==expr
    doc=SimpleNamespace(tenant_id="course_public",content_type="doc_chunk",series_id=2,session_id=12,video_id=4,generation="c"*64,distill_artifact_sha256="d"*64)
    assert not scope.matches(doc)
    doc.generation="a"*64;doc.distill_artifact_sha256="b"*64
    assert scope.matches(doc)


@pytest.mark.asyncio
async def test_tutor_scope_takes_version_only_from_server_ready_publication(monkeypatch):
    from app.chat import service
    from app.chat.schemas import RagQueryRequest
    from app.domains.video_learning import publication
    seen={}
    async def ready(_):return {"video_id":4,"artifact_id":"a"*64,"artifact_sha256":"b"*64}
    async def retrieve(query,**kwargs):
        seen.update(kwargs)
        return service.RetrievalBundle(docs=[],graph_entities=[],raw_retrieved_count=0,rewrite_query=query,degraded_reason=None)
    monkeypatch.setattr(publication,"get_video_publication",ready)
    monkeypatch.setattr(service,"retrieve_three_channel",retrieve)
    await service._retrieve_study_context_bundle(RagQueryRequest(query="question",generation="e"*64),user_id=10,
        role=UserRole.STUDENT,context={"series_id":2,"series_code":"course_a","session_id":12,"video":{"video_id":4}},context_query="question")
    assert seen["study_scope"].generation=="a"*64
    assert seen["study_scope"].artifact_sha256=="b"*64


@pytest.mark.parametrize("generation,sha",[("bad","b"*64),("a"*64,None),(None,"b"*64)])
def test_invalid_or_partial_publication_scope_is_rejected(generation,sha):
    with pytest.raises(ValueError):StudyRetrievalScope(2,"course_a",12,4,generation=generation,artifact_sha256=sha)


def test_course_scope_without_ready_preserves_ordinary_knowledge_and_excludes_video():
    course=StudyRetrievalScope(2,"course_a")
    video=StudyRetrievalScope(2,"course_a",12,4)
    assert "generation" not in expression(course) and "generation" not in expression(video)
    question=SimpleNamespace(content_type="question",series_code="course_a",series_codes=[])
    assert course.matches(question) and video.matches(question)
    ordinary=SimpleNamespace(content_type="doc_chunk",video_id=None,series_code="",series_codes="other,course_a")
    assert course.matches(ordinary) and video.matches(ordinary)
    unready_video=SimpleNamespace(tenant_id="course_public",content_type="doc_chunk",series_id=2,
        session_id=12,video_id=4,series_code="course_a",series_codes=[],generation="a"*64,
        distill_artifact_sha256="b"*64)
    assert not course.matches(unready_video) and not video.matches(unready_video)
