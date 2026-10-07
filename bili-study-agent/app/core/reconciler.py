# -*- coding: utf-8 -*-
"""W3 reconciler: MySQL leases and stages govern recovery; Redis PEL is transport state."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core import job_stream as js
from app.core.worker_runtime import HEARTBEAT_KEY_FMT, WorkerLifecycle, WorkerSpec

logger = logging.getLogger(__name__)

RECONCILER_INTERVAL_S = 15.0
RECONCILER_MIN_IDLE_MS = 180_000
RECONCILER_BATCH = 100
MAX_RETRY = 3
PARSER_GROUP = "parser-worker-group"
INGEST_GROUP = "ingest_worker_group"


def build_reconciler_spec() -> WorkerSpec:
    """Declare the streams whose durable leases and pending entries are reconciled."""
    return WorkerSpec(
        name="reconciler",
        entry_script="scripts/run_reconciler.py",
        streams_subscribed=(js.PARSER_JOBS_STREAM, js.INGEST_JOBS_STREAM),
        heartbeat_key=HEARTBEAT_KEY_FMT.format(name="reconciler"),
        startup_deps=("mysql", "redis"),
    )


class ReconcilerWorker(WorkerLifecycle):
    """Standalone process for MySQL lease recovery and Redis PEL settlement."""

    def __init__(self, *, redis_port=None):
        super().__init__(build_reconciler_spec(), redis=redis_port)
        self._stop_event = asyncio.Event()
        self._liveness_task: asyncio.Task | None = None

    def request_shutdown(self) -> None:
        self._shutdown_requested = True
        self._stop_event.set()

    async def startup(self) -> None:
        errors = self.spec.validate()
        if errors:
            raise RuntimeError(f"reconciler WorkerSpec invalid: {errors}")
        self._liveness_task = asyncio.create_task(self._keep_liveness(), name="reconciler-liveness")
        logger.info(self._startup_banner())

    async def _keep_liveness(self) -> None:
        while not self._stop_event.is_set():
            await self.heartbeat()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                pass

    async def run_loop(self) -> None:
        for stream, group in (
            (js.PARSER_JOBS_STREAM, PARSER_GROUP),
            (js.INGEST_JOBS_STREAM, INGEST_GROUP),
        ):
            if self._shutdown_requested:
                break
            stats = await run_reconcile_cycle(stream, group)
            logger.info("[reconciler] stream=%s stats=%s", stream, stats)
        if not self._shutdown_requested:
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=RECONCILER_INTERVAL_S)
            except asyncio.TimeoutError:
                pass

    async def shutdown(self, deadline_s: float = 30.0) -> int:
        self.request_shutdown()
        if self._liveness_task is not None:
            try:
                await asyncio.wait_for(self._liveness_task, timeout=max(0.0, deadline_s))
            except asyncio.TimeoutError:
                self._liveness_task.cancel()
                return 1
        return 0


async def _durable_dlq(stream: str, msg: dict, reason: str, task_store) -> bool:
    """XADD to DLQ, persist its epoch marker, then allow the source PEL ACK."""
    task_id, asset_id = str(msg.get("task_id") or ""), str(msg.get("asset_id") or "")
    current = await task_store.get_authoritative_task_asset(task_id, asset_id) if task_id and asset_id else None
    if current is None:
        return await js.send_to_dlq(stream, msg, reason)
    asset = current[1]
    epoch = int(asset.get("execution_epoch") or 0)
    if asset.get("dlq_epoch") == epoch:
        return True
    if not await js.send_to_dlq(stream, msg, reason):
        return False
    await task_store.mark_asset_dlq(asset_id, execution_epoch=epoch)
    latest = await task_store.get_authoritative_task_asset(task_id, asset_id)
    return bool(latest and latest[1].get("dlq_epoch") == epoch)


async def run_reconcile_cycle(stream_name: str, group_name: str,
                              consumer_name: str = "reconciler") -> dict:
    """Recover DB-expired leases, dispatch MySQL work, then settle stale PEL entries."""
    from app.knowledge import task_store

    stats = {"expired_recovered": 0, "dispatched": 0, "reclaimed": 0,
             "requeued": 0, "acked": 0, "dlq": 0, "pending_live_lease": 0,
             "errors": 0}

    # MySQL is the retry/lease source of truth. Redis idle age alone never steals a job.
    try:
        expired = await task_store.list_expired_assets(RECONCILER_BATCH)
        for asset in expired:
            try:
                recovered = await task_store.recover_expired_asset(
                    str(asset["asset_id"]), max_retries=MAX_RETRY,
                )
                if recovered:
                    stats["expired_recovered"] += 1
            except Exception:
                stats["errors"] += 1
                logger.exception("[reconciler] MySQL lease recovery failed asset=%s", asset.get("asset_id"))
    except Exception:
        stats["errors"] += 1
        logger.exception("[reconciler] MySQL expired lease scan failed")

    try:
        dispatch = await task_store.dispatch_pending_assets(RECONCILER_BATCH)
        stats["dispatched"] += dispatch.get("queued", 0)
        stats["errors"] += dispatch.get("failed", 0)
    except Exception:
        stats["errors"] += 1
        logger.exception("[reconciler] MySQL→Redis dispatch scan failed")

    try:
        claimed = await js.reclaim(
            stream_name, group_name, consumer_name,
            min_idle_ms=RECONCILER_MIN_IDLE_MS, count=RECONCILER_BATCH,
        )
    except Exception:
        stats["errors"] += 1
        logger.exception("[reconciler] Redis reclaim failed stream=%s", stream_name)
        return stats

    for msg in claimed or []:
        stats["reclaimed"] += 1
        entry_id = str(msg.get(js.ENTRY_ID_KEY) or "")
        task_id = str(msg.get("task_id") or "")
        asset_id = str(msg.get("asset_id") or "")
        if not entry_id:
            stats["errors"] += 1
            continue
        try:
            current = await task_store.get_authoritative_task_asset(task_id, asset_id)
            if current is None:
                if await js.send_to_dlq(stream_name, msg, "task/asset authority missing during reconciliation"):
                    if await js.ack(stream_name, group_name, entry_id):
                        stats["acked"] += 1
                        stats["dlq"] += 1
                    else:
                        stats["errors"] += 1
                else:
                    stats["errors"] += 1
                continue

            task, asset = current
            stage = asset.get("stage")
            epoch = int(asset.get("execution_epoch") or 0)
            message_epoch = msg.get("execution_epoch", 0)
            lease_until = asset.get("lease_until")

            if stage == "failed":
                reason = str(asset.get("error") or "asset entered failed terminal state")
                if await _durable_dlq(stream_name, msg, reason, task_store):
                    if await js.ack(stream_name, group_name, entry_id):
                        stats["acked"] += 1
                        stats["dlq"] += 1
                    else:
                        stats["errors"] += 1
                else:
                    stats["errors"] += 1
                continue

            if stage == "ingested":
                if await js.ack(stream_name, group_name, entry_id):
                    stats["acked"] += 1
                else:
                    stats["errors"] += 1
                continue

            if stage in ("parsing", "ingesting"):
                # Redis idle is not ownership. Keep the PEL entry pending while its
                # MySQL owner lease remains valid; recovery only happens after expiry.
                stats["pending_live_lease"] += 1
                continue

            if stage in ("queued_parser", "ir_ready"):
                # A reclaimed entry has already left its original stream consumer.
                # Publish a replacement (to the stage-derived stream) before ACK.
                if await task_store.dispatch_asset(asset, force=True):
                    if await js.ack(stream_name, group_name, entry_id):
                        stats["acked"] += 1
                        stats["requeued"] += 1
                    else:
                        stats["errors"] += 1
                else:
                    stats["errors"] += 1
                continue

            # Unknown durable stage is not silently discarded. Preserve the full
            # original message in DLQ and acknowledge only after successful XADD.
            if await js.send_to_dlq(stream_name, msg, f"unknown durable asset stage: {stage!r}"):
                if await js.ack(stream_name, group_name, entry_id):
                    stats["acked"] += 1
                    stats["dlq"] += 1
                else:
                    stats["errors"] += 1
            else:
                stats["errors"] += 1
        except Exception:
            stats["errors"] += 1
            logger.exception("[reconciler] failed to settle entry=%s task=%s asset=%s",
                             entry_id, task_id, asset_id)

    return stats


async def reconciler_loop(streams: list[tuple[str, str]], *, stop_event: Any = None) -> None:
    """Run DB-driven recovery for configured consumer groups until stopped."""
    while stop_event is None or not stop_event.is_set():
        for stream_name, group_name in streams:
            await run_reconcile_cycle(stream_name, group_name)
        if stop_event is not None:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=RECONCILER_INTERVAL_S)
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(RECONCILER_INTERVAL_S)
