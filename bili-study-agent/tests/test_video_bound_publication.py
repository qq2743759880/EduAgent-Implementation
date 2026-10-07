"""Existing EDU media has its own honest identity and staged activation."""
import json
import pytest
from tests.test_video_learning_publication import artifact, database, storage, local
from app.domains.video_learning import publication
from app.domains.video_learning.artifacts import seal_video_artifact, load_video_artifact
from app.knowledge.video_metadata import VideoKnowledgeMetadata, _sign_published_video_row, is_trusted_public_video
from tests.test_video_knowledge_ir import native_artifact
from pymysql.err import OperationalError
from asyncmy.errors import OperationalError as AsyncOperationalError


def local_artifact(artifact):
    path, native = artifact
    payload = native.model_dump(mode="json")
    payload.update(schema_version=4, quality="asr_compiled")
    payload["source"] = {"platform":"edu", "source_kind":"existing_video", "session_id":7000,
        "video_id":4,"asset_id":5,"media_sha256":"e"*64,"url":"edu://video/4",
        "title":"本地真实视频", "duration":10.0}
    payload["compiler"].update(version="2",transcript_origin="asr",asr_run={
        "provider":"faster-whisper","model":"base","language":"zh","device":"cpu",
        "compute_type":"int8","package_version":"1.2.1","media_sha256":"e"*64,
        "audio_sha256":"f"*64,"audio_duration":10.0})
    model=seal_video_artifact(payload)
    path.write_text(json.dumps(model.model_dump(mode="json"),ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
    return path,model


def test_bound_video_artifact_has_no_fabricated_platform_identity(artifact):
    path,model=local_artifact(artifact)
    assert load_video_artifact(path)==model
    assert "bvid" not in model.source.model_dump() and "cid" not in model.source.model_dump()
    payload=model.model_dump(mode="json")
    payload["source"]["media_sha256"]="0"*64
    with pytest.raises(ValueError):seal_video_artifact(payload)


@pytest.mark.parametrize("field,value",[("video_id",999),("asset_id",999),("session_id",999)])
def test_bound_source_requires_the_same_actual_video_asset_and_lesson(artifact,field,value):
    _,model=local_artifact(artifact)
    row={"video_code":"VID-real-local","duration_seconds":10,"asset_id":5,"session_id":7000}
    row[field]=value
    with pytest.raises(ValueError):publication.validate_artifact_video_binding(model,row.get("video_id",4),row)


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type",[OperationalError,AsyncOperationalError])
async def test_missing_readiness_column_cannot_authorize_a_legacy_pointer(monkeypatch,error_type):
    calls=[]
    async def query(sql,args=()):
        calls.append(sql)
        if "rag_status" in sql:raise error_type(1054,"Unknown readiness column")
        return {"video_id":4,"id":1}
    monkeypatch.setattr(publication,"fetch_one",query)
    assert await publication.get_video_publication(4) is None
    assert len(calls)==1
    assert "rag_status" in calls[0]


def test_bound_video_identity_is_signed_and_mutation_invalidates_proof():
    row={"series_id":7,"session_id":7000,"video_id":4,"start_seconds":0.0,"end_seconds":3.0,
        "distill_artifact_id":"a"*64,"distill_artifact_sha256":"b"*64,"compiler_version":"2","generation":"a"*64,
        "source_kind":"existing_video","source_asset_id":5,"source_media_sha256":"e"*64,
        "internal":False,"tenant_id":"course_public","visibility":"public","parser_backend":"edu-video-compiler",
        "content_type":"doc_chunk","video_provenance_version":1,"video_publication_id":1,
        "document_id":"c"*32,"parse_fingerprint":"d"*16,"owner_id":9,"security_scope":"default",
        "source_file":"video_4.asr.json","content":"真实课程","raw_content":"真实课程","series_code":"LEET","module_code":"LEET1"}
    assert "source_bvid" not in VideoKnowledgeMetadata.model_validate(row).model_dump()
    row["video_provenance_signature"]=_sign_published_video_row(row)
    assert is_trusted_public_video(row)
    row["source_media_sha256"]="0"*64
    assert not is_trusted_public_video(row)


def test_existing_video_survives_ir_loader_and_current_tutor_provenance(monkeypatch,native_artifact):
    from tests.test_video_public_provenance import loaded_rows
    payload=native_artifact.model_dump(mode="json")
    payload.update(schema_version=4,quality="asr_compiled")
    payload["source"]={"platform":"edu","source_kind":"existing_video","session_id":201,
        "video_id":301,"asset_id":5,"media_sha256":"e"*64,"url":"edu://video/301",
        "title":"真实媒体","duration":210.0}
    payload["compiler"].update(version="2",transcript_origin="asr",asr_run={
        "provider":"faster-whisper","model":"base","language":"zh","device":"cpu",
        "compute_type":"int8","package_version":"1.2.1","media_sha256":"e"*64,
        "audio_sha256":"f"*64,"audio_duration":210.0})
    model=seal_video_artifact(payload)
    client,_=loaded_rows(monkeypatch,model)
    assert client.rows and all(is_trusted_public_video(row) for row in client.rows)
    assert all(row["source_media_sha256"]=="e"*64 and "source_bvid" not in row for row in client.rows)


@pytest.mark.asyncio
async def test_pending_rebuild_does_not_displace_ready_student_version(database,storage,artifact):
    path,old=artifact
    first=await publication.publish_video_artifact(4,path)
    payload=old.model_dump(mode="json");payload["summary"]["overview"]="审核后的新版本"
    newer=seal_video_artifact(payload)
    path.write_text(json.dumps(newer.model_dump(mode="json"),ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
    pending=await publication.publish_video_artifact(4,path,rag_pending=True)
    assert pending["rag_status"]=="pending" and pending["previous_publication_id"]==first["id"]
    assert (await publication.get_video_knowledge(7000,101))["generation"]==old.content_sha256
    # An error or a mismatched ingest receipt can never activate a different pack.
    receipt={"status":"PASS","generation":newer.content_sha256,"task_status":"succeeded",
        "vector_status":"succeeded","active_vector_count":2,"pending_messages":0,
        "binding":{"video_id":4},"artifact_source":{"sha256":pending["object_sha256"]}}
    with pytest.raises(ValueError):
        await publication.activate_video_publication(4,"0"*64,receipt)
    assert (await publication.get_video_publication(4))["id"]==first["id"]
    activated=await publication.activate_video_publication(4,newer.artifact_sha256,receipt)
    assert activated["rag_status"]=="ready"
    assert (await publication.get_video_knowledge(7000,101))["generation"]==newer.content_sha256
    assert (await publication.activate_video_publication(4,newer.artifact_sha256,receipt))["id"]==activated["id"]
