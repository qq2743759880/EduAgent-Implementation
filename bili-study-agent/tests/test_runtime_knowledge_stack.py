import pytest
from app.knowledge import document_graph
from app.knowledge.models import KnowledgeChunk,ContentType


def test_new_ir_text_documents_project_active_ids_without_touching_legacy_catalog():
    chunk=KnowledgeChunk(chunk_id='active-id',content='Cache consistency TTL',content_type=ContentType.DOC_CHUNK,
        parser_backend='legacy_str',block_ids=['block-1'],extra={'document_id':'doc','parse_fingerprint':'fp','generation_state':'active'})
    assert document_graph.projection_rows([chunk],'_default','task')[0]['parser_backend']=='legacy_str'
    chunk.extra['generation_state']='candidate'
    assert document_graph.projection_rows([chunk],'_default','task')==[]


def test_pdf_auto_uses_real_mineru_when_enabled_and_other_files_keep_reader(monkeypatch):
    from app.knowledge.routers import upload
    monkeypatch.setattr(upload.settings,'MINERU_ENABLED',True)
    assert upload.select_document_parser('course.pdf','auto')=='mineru'
    assert upload.select_document_parser('course.md','auto')=='auto'


@pytest.mark.asyncio
async def test_video_graph_cannot_project_first_pending_generation(monkeypatch):
    from app.domains.video_learning import graph
    async def no_ready(video_id):return None
    monkeypatch.setattr(graph,'get_video_publication',no_ready)
    with pytest.raises(Exception,match='正式|READY'):
        await graph.project_ready_video(9)


@pytest.mark.asyncio
async def test_admin_typed_markdown_uses_durable_ir_workers_in_legacy_mode(monkeypatch):
    from app.knowledge.routers import upload
    from app import database
    class Redis:
        async def ping(self):return True
        async def exists(self,key):return True
    class Minio:
        def bucket_exists(self,bucket):return True
    monkeypatch.setattr(upload.settings,'IMPORT_COMMAND_MODE','legacy')
    monkeypatch.setattr(database,'get_redis',lambda:Redis())
    monkeypatch.setattr(database,'get_minio_client',lambda:Minio())
    assert await upload._w3_worker_path_ready([{'object_key':'sample.md','sha256':'a'*64,
        'business_metadata':{'parser_backend':'legacy_str'}}])
