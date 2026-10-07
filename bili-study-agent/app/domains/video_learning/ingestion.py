"""Import one published video artifact through ImportCommand → Document IR → existing ingest.

No global worker/backlog is started. Only this new task's isolated Redis stream
is consumed; old generations are retained and graph/repair dispatch is disabled.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import nullcontext
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid


from loguru import logger
from app.config import settings
from app.core import job_stream as js
from app.core.worker_bootstrap import worker_resources
from app.core.worker_runtime import WorkerSpec
from app.database import fetch_one, get_redis
from app.domains.learning.repository import StudyRepo
from app.domains.video_learning.artifacts import EduVideoSource, load_video_artifact
from app.domains.video_learning.publication import validate_artifact_video_binding
from app.domains.video_learning.knowledge_ir import VideoKnowledgeBinding, build_video_ir, certify_published_video_ir
from app.knowledge import task_store
from app.knowledge.chunk_preparation import prepare_chunks, ChunkPreparationPolicy
from app.knowledge.import_command import ImportCommand
from app.knowledge.importer.embedder import encode_dense_batch_detailed
from app.knowledge.importer.loader import COLLECTION_NAME, get_milvus_client
from app.knowledge.ingest_worker import IngestWorker
from app.knowledge.ir import SourceAssetRef, SecurityMeta
from app.knowledge.parser_worker import build_ir_artifact_key
from app.knowledge.video_metadata import VIDEO_METADATA_FIELDS
from app.services.source_asset_store import SourceAssetStore


def event(stage: str, **values) -> None:
    print(json.dumps({"stage": stage, **values}, ensure_ascii=False), flush=True)


def validate_binding(*, artifact, video_id, row, canonical, operator, publication) -> None:
    """Authorize actual course binding before registering any import or embedding."""
    if artifact.quality not in ("native_compiled", "asr_compiled"):
        raise ValueError("A verified transcript compilation is required")
    if not row or not operator or operator.get("role") not in ("admin", "manager") or not publication:
        raise ValueError("Published video, course binding and active authorized operator are required")
    if not canonical or int(canonical["video_id"]) != video_id or int(publication["video_id"]) != video_id:
        raise ValueError("The publication must identify the canonical playable lesson video")
    validate_artifact_video_binding(artifact, video_id, row)


def resolve_import_owner(task: dict | None, assets: list[dict], *, publication: dict,
                         operator_id: int, tenant: str) -> int:
    """Retain a completed identical import's accountable owner across admins.

    The current admin was authorized against the actual course/media earlier.
    This is reuse of immutable completed output, never permission to reopen a
    different owner's running/failed task or alter its security and proof.
    """
    if task is None or task.get("user_id") == operator_id:
        return operator_id
    owner = task.get("user_id")
    expected = {"bucket": publication["bucket"], "object_key": publication["object_key"],
                "sha256": publication["object_sha256"], "size_bytes": publication["size_bytes"]}
    if (type(owner) is not int or owner <= 0 or task.get("status") != "succeeded"
            or task.get("tenant_id") != tenant or task.get("visibility") != "public"
            or task.get("security_scope") != "default" or len(assets) != 1
            or assets[0].get("task_id") != task.get("task_id") or assets[0].get("stage") != "ingested"
            or any(assets[0].get(key) != value for key, value in expected.items())):
        raise ValueError("Another operator's import may only reuse its fully completed identical publication")
    return owner


async def ingest(args: argparse.Namespace, *, borrowed_resources: bool = False) -> dict:
    from app.observability.tracing import span,remote_parent
    try:context=getattr(args,'trace_context',None) or json.loads(os.environ.get('EDU_VIDEO_TRACE_CONTEXT','{}'))
    except ValueError:context=None
    with span('video.rag_ingest',parent=remote_parent(context),attributes={'video.id':args.video_id}):
        return await _ingest(args,borrowed_resources=borrowed_resources)


async def _ingest(args: argparse.Namespace, *, borrowed_resources: bool = False) -> dict:
    artifact = load_video_artifact(args.artifact)
    if artifact.quality not in ("native_compiled", "asr_compiled"):
        raise ValueError("Only freshly compiled, auditable transcripts may enter video ingestion")
    task_id = f"video_{args.video_id}_{artifact.artifact_sha256[:24]}"
    stream = f"video_ingest:{task_id}"
    name = f"video-ingest-{args.video_id}"
    group = "bounded-video-ingest"
    spec = WorkerSpec(name=name, entry_script="app/domains/video_learning/ingestion.py",
                      streams_subscribed=(stream,), heartbeat_key=f"worker:alive:{name}",
                      startup_deps=("mysql", "redis", "minio", "milvus"))
    # Web-owned jobs reuse its BGE-M3 singleton and infrastructure. Only a
    # standalone CLI owns initialization/closure; borrowed jobs must never close
    # the pools serving students. All import scopes and fences below are shared.
    resources = nullcontext() if borrowed_resources else worker_resources(spec)
    async with resources:
        binding_row = await fetch_one(
            "SELECT sa.session_id,sv.asset_id,sv.video_code,sv.duration_seconds,s.id AS series_id,"
            "s.series_code,s.series_name,ccc.module_code FROM session_video sv "
            "JOIN session_asset sa ON sa.id=sv.asset_id "
            "JOIN series_cohort_session scs ON scs.id=sa.session_id "
            "JOIN series_cohort_course ccc ON ccc.id=scs.series_cohort_course_id "
            "JOIN series_cohort co ON co.id=ccc.cohort_id JOIN series s ON s.id=co.series_id "
            "WHERE sv.id=%s", (args.video_id,),
        )
        operator = await fetch_one(
            "SELECT u.id,a.role_code AS role FROM sys_user u JOIN sys_user_auth a ON a.user_id=u.id "
            "WHERE u.id=%s AND u.yn=1 AND u.status=1", (args.operator_id,))
        publication = await fetch_one(
            "SELECT * FROM video_learning_publication WHERE video_id=%s AND artifact_sha256=%s",
            (args.video_id, artifact.artifact_sha256),
        )
        canonical_video = await StudyRepo().get_session_video(binding_row["session_id"]) if binding_row else None
        validate_binding(artifact=artifact, video_id=args.video_id, row=binding_row,
                         canonical=canonical_video, operator=operator, publication=publication)
        if isinstance(artifact.source, EduVideoSource):
            from app.domains.video_learning.bound_media import verify_bound_source
            await verify_bound_source(artifact.source)
        raw = args.artifact.read_bytes()
        object_sha = hashlib.sha256(raw).hexdigest()
        if (publication["object_sha256"] != object_sha or publication["artifact_id"] != artifact.content_sha256
                or int(publication["size_bytes"]) != len(raw)):
            raise ValueError("Local artifact differs from the immutable publication")
        store = SourceAssetStore()
        checked = await asyncio.to_thread(store.fetch_to_temp, publication["bucket"], publication["object_key"],
                                          expected_sha256=object_sha)
        try:
            if Path(checked).read_bytes() != raw:
                raise ValueError("Published artifact bytes differ from local compilation")
        finally:
            store.cleanup_temp(checked)
        tenant = settings.COURSE_PUBLIC_PARTITION
        task = await task_store.get_task(task_id)
        prior_assets = await task_store.get_source_assets(task_id) if task is not None else []
        import_owner = resolve_import_owner(task, prior_assets, publication=publication,
                                           operator_id=args.operator_id, tenant=tenant)
        security = SecurityMeta(visibility="public", owner_id=import_owner, security_scope="default")
        binding = VideoKnowledgeBinding(
            series_id=int(binding_row["series_id"]), session_id=int(binding_row["session_id"]),
            video_id=args.video_id, series_code=binding_row["series_code"], series_name=binding_row["series_name"],
            module_code=binding_row["module_code"], security=security,
        )
        client = get_milvus_client()
        if not await asyncio.to_thread(client.has_collection, COLLECTION_NAME):
            raise ValueError("Existing EDU knowledge collection is required; this command does not bootstrap a second RAG")
        event("preflight", task_id=task_id, series_id=binding.series_id,
              session_id=binding.session_id, video_id=binding.video_id, tenant=tenant)
        dense = await asyncio.to_thread(encode_dense_batch_detailed, [artifact.source.title])
        if dense.backend != "bge_m3" or not dense.normalized:
            raise ValueError("Local normalized BGE-M3 is required before registering an import")
        event("bge_ready", embedding_model=dense.embedding_model, precision=dense.precision)
        before = await asyncio.to_thread(client.get_collection_stats, COLLECTION_NAME)
        count_before = (await asyncio.to_thread(client.query, collection_name=COLLECTION_NAME, filter="",
            output_fields=["count(*)"], consistency_level="Strong"))[0]["count(*)"]
        if task is None:
            task = await ImportCommand(mode="primary").create_import_task(
                task_id=task_id, task_type="system_init", tenant_id=tenant, visibility="public",
                user_id=args.operator_id, security_scope=security.security_scope,
                source_files_meta=[{"bucket": publication["bucket"], "object_key": publication["object_key"],
                    "file_name": (f"video_{artifact.source.video_id}.{artifact.compiler.transcript_origin}.json"
                                  if isinstance(artifact.source, EduVideoSource) else
                                  f"{artifact.source.bvid}_P{artifact.source.page}.{artifact.compiler.transcript_origin}.json"), "file_size": len(raw),
                    "content_type": "application/json", "sha256": object_sha}],
            )
        assets = await task_store.get_source_assets(task_id)
        if len(assets) != 1 or any(task.get(k) != v for k, v in {
            "tenant_id": tenant, "visibility": "public", "user_id": import_owner,
            "security_scope": security.security_scope,
        }.items()):
            raise ValueError("Existing task differs from the bounded authority")
        asset = assets[0]
        namespace_filter = f'tenant_id == "{tenant}" and document_id == "{asset["document_id"]}"'
        namespace_before = (await asyncio.to_thread(client.query, collection_name=COLLECTION_NAME,
            filter=namespace_filter, output_fields=["count(*)"], consistency_level="Strong"))[0]["count(*)"]
        reused_ingested_task = asset["stage"] == "ingested"
        if any(asset.get(k) != v for k, v in {"bucket": publication["bucket"], "object_key": publication["object_key"],
                                             "sha256": object_sha, "size_bytes": len(raw)}.items()):
            raise ValueError("Existing SourceAsset differs from the canonical publication")
        asset = await resume_asset(asset, task_id=task_id)
        source = SourceAssetRef(bucket=asset["bucket"], object_key=asset["object_key"], sha256=asset["sha256"],
                                document_id=asset["document_id"], file_name=asset["file_name"], mime=asset["mime"])
        ir = build_video_ir(artifact, source=source, binding=binding, task_id=task_id, asset_id=asset["asset_id"])
        ir = certify_published_video_ir(ir, publication=publication, binding=binding, tenant_id=tenant)
        prepared = prepare_chunks(ir.parsed, ir.seeds, tenant_id=tenant,
                                  policy=ChunkPreparationPolicy(token_budget=settings.IR_CHUNK_TOKEN_BUDGET))
        fingerprint = ir.parsed.parse_fingerprint()
        epoch = int(asset["execution_epoch"])
        if asset["stage"] == "queued_parser":
            owner = f"video-ir:{uuid.uuid4().hex[:20]}"
            if not await task_store.claim_asset(asset["asset_id"], task_id=task_id, source_stage="queued_parser",
                target_stage="parsing", execution_epoch=epoch, owner=owner, lease_seconds=180):
                raise ValueError("Video IR claim was fenced out")
            ir_path = args.receipt.parent / f"{task_id}.ir.json"
            ir_path.parent.mkdir(parents=True, exist_ok=True)
            ir_path.write_text(ir.model_dump_json(), encoding="utf-8")
            ir_sha = hashlib.sha256(ir_path.read_bytes()).hexdigest()
            ir_key = build_ir_artifact_key(task_id=task_id, asset_id=asset["asset_id"],
                                           source_sha=object_sha, fingerprint=fingerprint)
            await asyncio.to_thread(store.put_artifact, settings.MINIO_BUCKET_ARTIFACTS, ir_key, ir_path, "application/json")
            stat = await asyncio.to_thread(store.get_artifact_ref, settings.MINIO_BUCKET_ARTIFACTS, ir_key)
            ref = {**stat, "sha256": ir_sha, "content_type": "application/json", "parse_fingerprint": fingerprint}
            if not await task_store.transition_claimed_asset(asset["asset_id"], execution_epoch=epoch, owner=owner,
                expected_stage="parsing", stage="ir_ready", parse_fingerprint=fingerprint,
                artifact_ref=json.dumps(ref, ensure_ascii=False, separators=(",", ":"))):
                raise ValueError("Video IR publication was fenced out")
            asset = (await task_store.get_source_assets(task_id))[0]
        if asset["stage"] == "ir_ready":
            if asset["parse_fingerprint"] != fingerprint:
                raise ValueError("Existing IR fingerprint differs from authoritative course binding")
            await task_store.update_task(task_id=task_id, status="running", error="", total_chunks=len(prepared), started_at=datetime.now())
            if not await js.create_consumer_group(stream, group):
                raise RuntimeError("Isolated ingest group unavailable")
            await reconcile_scoped_pending(get_redis(), task_id=task_id, asset=asset)
            message = js.make_message(job_id=uuid.uuid4().hex, task_id=task_id, asset_id=asset["asset_id"],
                attempt_snapshot=int(asset["retry_count"]) + 1, execution_epoch=int(asset["execution_epoch"]),
                payload_ref=f"mysql://import_source_asset/{asset['asset_id']}")
            if not await js.enqueue(stream, message):
                raise RuntimeError("Isolated ingest message unavailable")
            messages = await js.dequeue(stream, group, name, count=1, block_ms=1)
            if len(messages) != 1:
                raise RuntimeError("Single bounded ingest message was not delivered")
            worker = IngestWorker(spec=spec, store=store, stream=stream, group=group,
                retire_old_generations=False, requeue_on_failure=False, enable_graph=False,
                allowed_task_id=task_id, require_bge_m3=True)
            event("ingest_started", transcript_windows=sum(s.metadata["video_knowledge_kind"] == "transcript" for s in ir.seeds),
                  chapters=len(artifact.chapters), prepared_chunks=len(prepared), document_id=asset["document_id"])
            outcome = await worker.process_one(messages[0])
            if outcome != "done":
                raise RuntimeError(f"Bounded ingest outcome: {outcome}")
        elif asset["stage"] != "ingested":
            raise ValueError("Existing bounded task requires operator inspection before retry")
        scope = f'tenant_id == "{tenant}" and document_id == "{asset["document_id"]}" and generation_state == "active"'
        rows = await asyncio.to_thread(client.query, collection_name=COLLECTION_NAME, filter=scope, limit=1000,
            consistency_level="Strong",
            output_fields=["chunk_id", "document_id", "parse_fingerprint", "tenant_id", "visibility", "owner_id",
                           "security_scope", "generation_state", "embedding_model", "embed_normalized", "embed_fallback",
                           *VIDEO_METADATA_FIELDS])
        if len(rows) != len(prepared) or any(
            row.get("video_id") != args.video_id or row.get("series_id") != binding.series_id
            or row.get("generation") != artifact.content_sha256 or row.get("parse_fingerprint") != fingerprint
            or row.get("embedding_model") != dense.embedding_model or row.get("embed_fallback")
            or row.get("tenant_id") != tenant or row.get("visibility") != "public"
            or row.get("owner_id") != import_owner or row.get("security_scope") != security.security_scope
            or row.get("embed_normalized") != 1 for row in rows
        ):
            raise ValueError("Published vector count, metadata or BGE provenance differs from the bounded import")
        asset = (await task_store.get_source_assets(task_id))[0]
        if asset["stage"] != "ingested":
            raise ValueError("Durable asset is not ingested after vector verification")
        if import_owner != args.operator_id:
            # Cross-admin reuse is read-only for the original producer history.
            # Incomplete ACK/recovery windows belong to that producer's operator.
            if (await get_redis().xpending(stream, group))["pending"] != 0:
                raise ValueError("Completed foreign-owner import still requires its operator to settle pending delivery")
        else:
            if not await js.create_consumer_group(stream, group):
                raise RuntimeError("Isolated ingest group unavailable")
            await reconcile_scoped_pending(get_redis(), task_id=task_id, asset=asset)
        # Recover the crash window after asset commit but before task finalization.
        # Verified active vectors and this sole durable asset are the authority.
        if not reused_ingested_task or task.get("status") != "succeeded":
            await task_store.update_task(task_id=task_id, status="succeeded", error="",
                imported_chunks=len(rows), total_chunks=len(rows), finished_at=datetime.now())
        task = await task_store.get_task(task_id)
        pending = await get_redis().xpending(stream, group)
        if task["status"] != "succeeded" or asset["stage"] != "ingested" or pending["pending"] != 0:
            raise ValueError("Durable import or isolated stream acknowledgement is incomplete")
        namespace_rows = await asyncio.to_thread(client.query, collection_name=COLLECTION_NAME,
            filter=namespace_filter, output_fields=["generation_state"], limit=1000, consistency_level="Strong")
        count_after = (await asyncio.to_thread(client.query, collection_name=COLLECTION_NAME, filter="",
            output_fields=["count(*)"], consistency_level="Strong"))[0]["count(*)"]
        return {"status": "PASS", "task_id": task_id, "asset_id": asset["asset_id"], "document_id": asset["document_id"],
            "binding": binding.model_dump(mode="json"), "tenant_id": tenant, "generation": artifact.content_sha256,
            "artifact_source": {"bucket": publication["bucket"], "key": publication["object_key"], "sha256": object_sha},
            "ir_ref": json.loads(asset["artifact_ref"]), "parse_fingerprint": fingerprint,
            "transcript_windows": sum(s.metadata["video_knowledge_kind"] == "transcript" for s in ir.seeds),
            "chapters": len(artifact.chapters), "active_vector_count": len(rows), "metadata_rows": rows,
            "task_status": task["status"], "vector_status": asset["vector_status"], "graph_status": asset["graph_status"],
            "embedding": {"backend": dense.backend, "model": dense.embedding_model, "normalized": dense.normalized},
            "isolated_stream": stream, "pending_messages": pending["pending"], "collection_stats_before": before,
            "strong_global_row_count_before": count_before, "strong_global_row_count_after": count_after,
            "namespace_row_count_before": namespace_before,
            "namespace_row_counts": {stage: sum(row.get("generation_state") == stage for row in namespace_rows)
                                     for stage in ("candidate", "active")},
            "rows_outside_new_namespace_before": count_before - namespace_before,
            "rows_outside_new_namespace_after": count_after - len(namespace_rows),
            "outside_namespace_count_unchanged": count_before - namespace_before == count_after - len(namespace_rows),
            "reused_ingested_task_without_pipeline": reused_ingested_task,
            "import_owner_id": import_owner,
            "old_generation_retirement": False, "global_worker_started": False, "shared_dispatch_called": False}


async def resume_asset(asset: dict, *, task_id: str) -> dict:
    """Resume only this verified publication's asset; never dispatch shared backlog.

    An explicit operator retry can reopen a failed asset. Active claims remain
    fenced; recovery is permitted only after the existing durable lease expires.
    """
    if asset.get("task_id") != task_id:
        raise ValueError("Refusing to retry an asset from a different task")
    stage = asset["stage"]
    if stage in ("parsing", "ingesting"):
        if not await task_store.recover_expired_asset(asset["asset_id"], max_retries=2_147_483_647):
            raise ValueError("Import asset still has an active claim; retry after its lease expires")
    elif stage == "failed":
        target = "ir_ready" if asset.get("artifact_ref") else "queued_parser"
        if await task_store.update_asset_stage(asset["asset_id"], target, expected_stage="failed") != 1:
            raise ValueError("Scoped import retry was fenced out")
    else:
        return asset
    refreshed = await task_store.get_source_assets(task_id)
    if len(refreshed) != 1 or refreshed[0]["asset_id"] != asset["asset_id"]:
        raise ValueError("Scoped import changed while retrying")
    return refreshed[0]


async def reconcile_scoped_pending(redis, *, task_id: str, asset: dict) -> int:
    """Settle stale deliveries in this producer's exclusive stream only.

    No shared PEL reclaim or vector writes occur. The durable unclaimed IR is
    replayed by the next new message, or the verified asset is already ingested.
    A crash between ACK and replay leaves that durable IR available for retry.
    """
    if not task_id.startswith("video_") or asset.get("task_id") != task_id:
        raise ValueError("Pending reconciliation scope is not a video task")
    if asset.get("stage") not in ("ir_ready", "ingested") or asset.get("lease_owner"):
        raise ValueError("Cannot settle deliveries while an asset claim is active")
    stream, group = f"video_ingest:{task_id}", "bounded-video-ingest"
    pending = await redis.xpending_range(stream, group, min="-", max="+", count=1000)
    if len(pending) >= 1000:
        raise ValueError("Scoped pending budget exceeded; operator inspection required")
    ids = []
    for item in pending:
        entry_id = item["message_id"]
        entries = await redis.xrange(stream, min=entry_id, max=entry_id, count=1)
        if len(entries) != 1:
            raise ValueError("Pending entry lacks auditable scope")
        message = js._fields_to_message(*entries[0])
        if (message.get("task_id") != task_id or message.get("asset_id") != asset["asset_id"]
                or type(message.get("execution_epoch")) is not int
                or message["execution_epoch"] > int(asset["execution_epoch"])):
            raise ValueError("Pending delivery differs from authorized task/asset/epoch scope")
        ids.append(entry_id)
    if ids and await redis.xack(stream, group, *ids) != len(ids):
        raise RuntimeError("Scoped pending acknowledgements incomplete")
    return len(ids)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--video-id", type=int, required=True)
    parser.add_argument("--operator-id", type=int, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    # database.init_redis historically logs a URL credential prefix; keep it out of operator output.
    logger.disable("app.database")
    result = asyncio.run(ingest(args))
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    event("complete", status=result["status"], task_id=result["task_id"], active_vector_count=result["active_vector_count"])


if __name__ == "__main__":
    main()
