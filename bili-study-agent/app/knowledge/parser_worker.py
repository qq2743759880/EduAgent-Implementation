# -*- coding: utf-8 -*-
"""W3 parser consumer: MySQL authority → parse → durable IR artifact → ingest."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.job_stream import ack, dequeue, send_to_dlq, create_consumer_group
from app.core.worker_runtime import WorkerLifecycle, WorkerSpec, HEARTBEAT_KEY_FMT
from app.knowledge.ir import IRArtifact, ParsedDocument, SeedKnowledgeChunk

logger = logging.getLogger(__name__)

PARSER_STREAM = "parser_jobs"
INGEST_STREAM = "ingest_jobs"
PARSER_GROUP = "parser-worker-group"
CONSUMER_NAME = "parser-worker"
LEASE_SECONDS = 180
LEASE_RENEW_SECONDS = 45
MAX_RETRIES = 3


def build_ir_artifact(
    *, task_id: str, asset_id: str, parsed: ParsedDocument,
    seeds: list[SeedKnowledgeChunk],
) -> dict[str, Any]:
    """Serialize the shared Parser→Ingest wire contract."""
    return IRArtifact(
        task_id=task_id, asset_id=asset_id,
        document_id=parsed.source.document_id, parsed=parsed, seeds=seeds,
    ).model_dump(mode="json")


def build_ir_artifact_key(*, task_id: str, asset_id: str, source_sha: str, fingerprint: str) -> str:
    """Build an immutable per-asset artifact key without trusting IDs as path segments."""
    task_key = hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:24]
    asset_key = hashlib.sha256(asset_id.encode("utf-8")).hexdigest()[:24]
    return f"ir/{task_key}/{asset_key}/{source_sha}/{fingerprint}/parsed_document.json"


async def _renew_mysql_lease(
    asset_id: str, epoch: int, owner: str,
    stop: asyncio.Event, lost: asyncio.Event,
) -> None:
    from app.knowledge import task_store

    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=LEASE_RENEW_SECONDS)
            return
        except asyncio.TimeoutError:
            pass
        try:
            if not await task_store.renew_asset_lease(
                asset_id, execution_epoch=epoch, owner=owner,
                lease_seconds=LEASE_SECONDS,
            ):
                lost.set()
                return
        except Exception:
            logger.exception("[parser-worker] MySQL lease renew failed asset=%s", asset_id)
            lost.set()
            return


class ParserWorker(WorkerLifecycle):
    """Consume parser_jobs using durable task/asset metadata and owner fencing."""

    def __init__(self, *, redis_port=None):
        spec = WorkerSpec(
            name=CONSUMER_NAME,
            entry_script="scripts/run_parser_worker.py",
            streams_subscribed=(PARSER_STREAM,),
            heartbeat_key=HEARTBEAT_KEY_FMT.format(name=CONSUMER_NAME),
            startup_deps=("mysql", "redis", "minio"),
        )
        super().__init__(spec, redis=redis_port)
        self.jobs_consumed = 0
        self._shutdown_requested = False

    def request_shutdown(self) -> None:
        self._shutdown_requested = True

    async def startup(self) -> None:
        if not await create_consumer_group(PARSER_STREAM, PARSER_GROUP):
            raise RuntimeError("parser consumer group initialization failed")
        logger.info("[parser-worker] ready consumer=%s", CONSUMER_NAME)

    async def run_loop(self) -> None:
        # WorkerLifecycle owns the loop and heartbeats, including idle periods.
        if self._shutdown_requested:
            return
        messages = await dequeue(PARSER_STREAM, PARSER_GROUP, CONSUMER_NAME, count=1, block_ms=3000)
        for message in messages:
            try:
                await self._process_one(message)
            except Exception:
                # Leave the entry in PEL; the reconciler consults MySQL lease state.
                logger.exception("[parser-worker] unhandled job error; left pending")

    async def _process_one(self, msg: dict) -> None:
        from app.knowledge import task_store
        from app.knowledge.models import (
            ASSET_STAGE_IR_READY, ASSET_STAGE_PARSING, ASSET_STAGE_QUEUED_PARSER,
            ASSET_STAGE_FAILED,
            ImportState,
        )
        from app.knowledge.importer.parser import _parse_node_ir
        from app.services.source_asset_store import SourceAssetStore

        entry_id = str(msg.get("_entry_id") or "")
        task_id = str(msg.get("task_id") or "")
        asset_id = str(msg.get("asset_id") or "")
        if not (entry_id and task_id and asset_id):
            return
        context = await task_store.get_authoritative_task_asset(task_id, asset_id)
        if context is None:
            logger.error("[parser-worker] task/asset relation missing; leave PEL task=%s asset=%s", task_id, asset_id)
            return
        task, asset = context
        epoch = msg.get("execution_epoch", 0)
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
            logger.error("[parser-worker] invalid execution_epoch; leave PEL asset=%s", asset_id)
            return

        owner = f"parser:{os.getpid()}:{uuid.uuid4().hex[:20]}"
        claimed = await task_store.claim_asset(
            asset_id, task_id=task_id, source_stage=ASSET_STAGE_QUEUED_PARSER,
            target_stage=ASSET_STAGE_PARSING, execution_epoch=epoch,
            owner=owner, lease_seconds=LEASE_SECONDS,
        )
        if not claimed:
            current = await task_store.get_authoritative_task_asset(task_id, asset_id)
            if current and (
                current[1].get("stage") != ASSET_STAGE_QUEUED_PARSER
                or int(current[1].get("execution_epoch") or 0) != epoch
            ):
                await ack(PARSER_STREAM, PARSER_GROUP, entry_id)
            return

        stop = asyncio.Event()
        lease_lost = asyncio.Event()
        renew_task = asyncio.create_task(_renew_mysql_lease(asset_id, epoch, owner, stop, lease_lost))
        heartbeat_task = asyncio.create_task(self.maintain_heartbeat(stop, period_s=10.0))
        store = SourceAssetStore()
        source_path: Path | None = None
        ir_path: Path | None = None
        try:
            visibility = task.get("visibility")
            scope = task.get("security_scope")
            if visibility not in ("private", "public") or not scope:
                raise RuntimeError("authoritative task security metadata invalid")
            # A prior attempt's error is history, not a permanent source-invalid flag.
            # Required identity and fetched SHA below remain fail-closed on every retry.
            bucket, object_key, source_sha = asset.get("bucket"), asset.get("object_key"), asset.get("sha256")
            if not (bucket and object_key and source_sha and asset.get("document_id")):
                raise RuntimeError("authoritative asset is missing bucket/object_key/sha256/document_id")

            source_path = await asyncio.to_thread(
                store.fetch_to_temp, bucket, object_key, expected_sha256=source_sha,
            )
            if lease_lost.is_set():
                return
            source_meta = {
                "bucket": bucket, "object_key": object_key, "sha256": source_sha,
                "document_id": asset["document_id"], "file_name": asset.get("file_name"),
                "mime": asset.get("mime"),
            }
            # B0-FIX（recovery 契约）：task.source_files 里与该 asset 同 document_id 的
            # business_metadata 随 meta 进入 parser——structured 元数据（§28 不靠解析正文猜），
            # parser 仅透传不解释；无该键时行为与历史逐字节一致。
            for _tf in task.get("source_files") or []:
                if isinstance(_tf, dict) and _tf.get("document_id") == asset["document_id"]:
                    if isinstance(_tf.get("business_metadata"), dict):
                        source_meta["business_metadata"] = dict(_tf["business_metadata"])
                    break
            state = ImportState(
                task_id=task_id, source_files=[str(source_path)],
                tenant_id=str(task.get("tenant_id") or ""),
                task_type=str(task.get("task_type") or ""),
                visibility=visibility, owner_id=task.get("user_id"),
                security_scope=scope, extra={"source_files_meta": [source_meta]},
            )
            patch = await asyncio.to_thread(_parse_node_ir, state)
            if patch.get("error"):
                raise RuntimeError(str(patch["error"]))
            parsed_items = patch.get("parsed_documents") or []
            seed_items = patch.get("seeds") or []
            if len(parsed_items) != 1 or not seed_items:
                raise RuntimeError("Parser did not produce one ParsedDocument and nonempty seeds")
            parsed = ParsedDocument.model_validate(parsed_items[0])
            seeds = [SeedKnowledgeChunk.model_validate(item) for item in seed_items]
            artifact_model = IRArtifact(
                task_id=task_id, asset_id=asset_id,
                document_id=asset["document_id"], parsed=parsed, seeds=seeds,
            )
            if parsed.source.sha256 != source_sha or parsed.source.document_id != asset["document_id"]:
                raise RuntimeError("ParsedDocument source identity does not match MySQL asset")
            if any(
                seed.security.visibility != visibility
                or seed.security.owner_id != task.get("user_id")
                or seed.security.security_scope != scope
                for seed in seeds
            ):
                raise RuntimeError("Parser seed security does not match MySQL task authority")

            fingerprint = parsed.parse_fingerprint()
            raw = artifact_model.model_dump_json().encode("utf-8")
            artifact_sha = hashlib.sha256(raw).hexdigest()
            ir_path = source_path.with_name(source_path.name + ".ir.json")
            ir_path.write_bytes(raw)
            ir_key = build_ir_artifact_key(
                task_id=task_id, asset_id=asset_id,
                source_sha=source_sha, fingerprint=fingerprint,
            )
            artifact_bucket = settings.MINIO_BUCKET_ARTIFACTS
            await asyncio.to_thread(store.put_artifact, artifact_bucket, ir_key, ir_path, "application/json")
            stat = await asyncio.to_thread(store.get_artifact_ref, artifact_bucket, ir_key)
            artifact_ref = json.dumps({
                **stat, "sha256": artifact_sha, "content_type": "application/json",
                "parse_fingerprint": fingerprint,
            }, ensure_ascii=False, separators=(",", ":"))
            if lease_lost.is_set():
                return
            completed = await task_store.transition_claimed_asset(
                asset_id, execution_epoch=epoch, owner=owner,
                expected_stage=ASSET_STAGE_PARSING, stage=ASSET_STAGE_IR_READY,
                parse_fingerprint=fingerprint, artifact_ref=artifact_ref,
            )
            if not completed:
                logger.warning("[parser-worker] fenced stale completion asset=%s epoch=%d", asset_id, epoch)
                return

            await task_store.dispatch_pending_assets()
            current = await task_store.get_authoritative_task_asset(task_id, asset_id)
            if not current or current[1].get("stage") != ASSET_STAGE_IR_READY or current[1].get("dispatched_epoch") != epoch:
                logger.warning("[parser-worker] ingest dispatch not durable; leave parser PEL asset=%s", asset_id)
                return
            await ack(PARSER_STREAM, PARSER_GROUP, entry_id)
            self.jobs_consumed += 1
        except Exception as exc:
            logger.exception("[parser-worker] failed asset=%s; recording fenced retry", asset_id)
            result = await task_store.retry_claimed_asset(
                asset_id, execution_epoch=epoch, owner=owner,
                expected_stage=ASSET_STAGE_PARSING, retry_stage=ASSET_STAGE_QUEUED_PARSER,
                max_retries=MAX_RETRIES, reason=f"{type(exc).__name__}: {exc}",
            )
            if result is None:
                return
            stage, new_epoch, _retry_count = result
            if stage == ASSET_STAGE_FAILED:
                if await send_to_dlq(PARSER_STREAM, msg, f"parser retry limit reached: {exc}"):
                    await task_store.mark_asset_dlq(asset_id, execution_epoch=new_epoch)
                    current = await task_store.get_authoritative_task_asset(task_id, asset_id)
                    if current and current[1].get("dlq_epoch") == new_epoch:
                        await ack(PARSER_STREAM, PARSER_GROUP, entry_id)
            else:
                await task_store.dispatch_pending_assets()
                current = await task_store.get_authoritative_task_asset(task_id, asset_id)
                if current and current[1].get("dispatched_epoch") == new_epoch:
                    await ack(PARSER_STREAM, PARSER_GROUP, entry_id)
        finally:
            stop.set()
            await asyncio.gather(renew_task, heartbeat_task, return_exceptions=True)
            if source_path:
                store.cleanup_temp(source_path)
            if ir_path:
                store.cleanup_temp(ir_path)
            await self.heartbeat()

    async def shutdown(self, deadline_s: float = 30.0) -> int:
        logger.info("[parser-worker] graceful shutdown (jobs=%d)", self.jobs_consumed)
        return 0

    async def health(self) -> bool:
        return await self.heartbeat()
