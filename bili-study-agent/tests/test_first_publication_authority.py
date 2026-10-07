"""READY authority, independent non-video compatibility and pre-ANN scope."""
from types import SimpleNamespace
import pytest
from app.auth import UserRole
from app.chat import service
from app.chat.retrieval_filter import StudyRetrievalScope, _study_scope_expression
from app.chat.schemas import RagQueryRequest, RetrievedDoc
from app.domains.video_learning import publication


def context():
    return {'series_id':2,'series_code':'course_a','session_id':12,'video':{'video_id':4}}


def video(generation='a'*64, sha='b'*64):
    return RetrievedDoc(doc_id=generation[:4],score=.9,content='Video statement',content_type='doc_chunk',
        tenant_id='course_public',series_id=2,series_code='course_a',session_id=12,video_id=4,
        generation=generation,distill_artifact_id=generation,distill_artifact_sha256=sha)


def ordinary():
    return [RetrievedDoc(doc_id='question',score=.9,content='Bound question',content_type='question',
                        tenant_id='_default',series_codes=['other_course','course_a']),
            RetrievedDoc(doc_id='course-note',score=.8,content='Normal course note',content_type='doc_chunk',
                        tenant_id='_default',series_codes=['other_course','course_a'])]


def test_first_publication_without_ready_rejects_video_and_keeps_nonvideo_course_docs():
    scope=StudyRetrievalScope(2,'course_a',12,4)
    assert not scope.matches(video()), 'Milvus active is not formal authority'
    assert all(scope.matches(doc) for doc in ordinary())
    assert not scope.matches(SimpleNamespace(content_type='doc_chunk',series_codes=['course_ab']))


def test_ready_scope_keeps_course_docs_and_only_exact_video_version():
    scope=StudyRetrievalScope(2,'course_a',12,4,generation='a'*64,artifact_sha256='b'*64)
    assert scope.matches(video())
    assert not scope.matches(video('c'*64,'d'*64))
    assert not scope.matches(video('a'*64,'d'*64))
    assert all(scope.matches(doc) for doc in ordinary())


def test_dynamic_field_existence_is_grouped_before_boolean_operators():
    # Live Milvus rejects `or not exists video_id or ...` due to EXISTS operand
    # precedence. This grouping is required for the non-video compatibility arm.
    assert '(not exists video_id)' in _study_scope_expression(StudyRetrievalScope(2,'course_a',12,4))


@pytest.mark.asyncio
@pytest.mark.parametrize('ready',[False,True])
async def test_service_never_infers_ready_from_active_and_preserves_ordinary_docs(monkeypatch,ready):
    pointer={'video_id':4,'artifact_id':'a'*64,'artifact_sha256':'b'*64} if ready else None
    async def get_pointer(_):return pointer
    async def retrieve(query,**kwargs):
        return service.RetrievalBundle(docs=ordinary()+[video(),video('c'*64,'d'*64)],
            graph_entities=[],raw_retrieved_count=4,rewrite_query=query,degraded_reason=None)
    monkeypatch.setattr(publication,'get_video_publication',get_pointer)
    monkeypatch.setattr(service,'retrieve_three_channel',retrieve)
    bundle=await service._retrieve_study_context_bundle(RagQueryRequest(query='question'),
        user_id=7,role=UserRole.STUDENT,context=context(),context_query='question')
    assert {doc.doc_id for doc in bundle.docs}==({'question','course-note','aaaa'} if ready else {'question','course-note'})


@pytest.mark.asyncio
async def test_missing_readiness_column_cannot_become_formal_publication(monkeypatch):
    from pymysql.err import OperationalError
    calls=[]
    async def fetch(sql,parameters):
        calls.append(sql)
        if "rag_status='ready'" in sql:raise OperationalError(1054,'Unknown column rag_status')
        return {'video_id':4,'artifact_id':'a'*64,'artifact_sha256':'b'*64}
    monkeypatch.setattr(publication,'fetch_one',fetch)
    assert await publication.get_video_publication(4) is None
    assert len(calls)==1


def test_unscoped_student_search_cannot_bypass_publication_authority(monkeypatch):
    from app.chat import retriever
    rows=[{'chunk_id':'video','content':'pending video','content_type':'doc_chunk','score':.9,
           'tenant_id':'course_public','visibility':'public','internal':False,'video_id':4,
           'series_id':2,'session_id':12,'generation':'a'*64},
          {'chunk_id':'note','content':'ordinary note','content_type':'doc_chunk','score':.8,
           'tenant_id':'course_public','visibility':'public','internal':False},
          {'chunk_id':'question','content':'ordinary question','content_type':'question','score':.8,
           'tenant_id':'_default','visibility':'public','internal':False}]
    seen={}
    def search(**kwargs):seen.update(kwargs);return rows
    monkeypatch.setattr(retriever,'ensure_jieba_ready',lambda:None)
    monkeypatch.setattr(retriever,'encode_dense_batch_detailed',lambda _:SimpleNamespace(
        vectors=[[.1]*1024],backend='bge_m3',normalized=True,embedding_model='fixture'))
    monkeypatch.setattr(retriever,'build_sparse_vector',lambda _:{4:.5})
    monkeypatch.setattr(retriever,'_milvus_hybrid_search',search)
    docs,degraded,_=retriever._milvus_hybrid_search_safe('query',user_id=7,role=UserRole.STUDENT,top_k=20)
    assert degraded is None
    assert {doc.doc_id for doc in docs}=={'note','question'}
    assert '(not exists video_id)' in seen['filter_expr']


def test_graph_neighbor_content_fetch_cannot_bypass_video_authority(monkeypatch):
    from app.chat import retriever
    from app.knowledge.importer import loader
    seen={}
    class Client:
        def query(self,**kwargs):
            seen.update(kwargs)
            return [{'chunk_id':'pending-video','content':'pending evidence','video_id':4,
                     'tenant_id':'course_public','visibility':'public','internal':False},
                    {'chunk_id':'ordinary','content':'course text','tenant_id':'_default',
                     'visibility':'public','internal':False}]
    monkeypatch.setattr(loader,'get_milvus_client',Client)
    result=retriever._milvus_fetch_contents(['pending-video','ordinary'],user_id=7,
        role=UserRole.STUDENT,caller='flows_agent_legacy')
    assert result=={'ordinary':'course text'}
    assert '(not exists video_id)' in seen['filter']
    assert 'video_id' in seen['output_fields']
