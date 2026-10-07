"""Initialize and close each standalone worker's own infrastructure clients."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.core.worker_runtime import WorkerSpec


_RESOURCE_HOOKS = {
    "mysql": ("init_mysql", "close_mysql", True),
    "redis": ("init_redis", "close_redis", True),
    "minio": ("init_minio", "close_minio", False),
    "milvus": ("init_milvus", "close_milvus", False),
    "mongo": ("init_mongo", "close_mongo", True),
    "neo4j": ("init_neo4j", "close_neo4j", False),
}


@asynccontextmanager
async def worker_resources(spec: WorkerSpec) -> AsyncIterator[None]:
    """Bring up the resources declared by a worker spec, then close them in reverse order.

    Startup is strict even when the web app is in DEBUG mode: a standalone worker must
    not announce ready with missing process-local pools or clients.
    """
    from app import database

    errors = spec.validate()
    if errors:
        raise RuntimeError(f"worker spec invalid: {errors}")

    initialized: list[str] = []
    try:
        for name in spec.startup_deps:
            init_name, _close_name, is_async = _RESOURCE_HOOKS[name]
            hook = getattr(database, init_name)
            result = hook()
            if is_async:
                await result
            initialized.append(name)
            if name == "minio":
                # Validate the process-local client and provision the 90-day IR bucket
                # before either worker is allowed through the web_ready gate.
                from app.database import get_minio_client
                if not get_minio_client().bucket_exists("edu-upload"):
                    raise RuntimeError("required MinIO source bucket edu-upload is missing")
                from app.services.source_asset_store import SourceAssetStore
                await asyncio.to_thread(SourceAssetStore().ensure_ir_artifact_bucket)
        yield
    finally:
        for name in reversed(initialized):
            _init_name, close_name, is_async = _RESOURCE_HOOKS[name]
            try:
                result = getattr(database, close_name)()
                if is_async:
                    await result
            except Exception:
                # Preserve the original startup/worker failure while attempting all closes.
                from app.common.logging import logger
                logger.exception("worker resource close failed: %s", name)
