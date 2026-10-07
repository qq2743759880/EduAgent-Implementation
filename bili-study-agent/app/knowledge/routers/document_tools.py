"""Authenticated inspection of real document IR, graph projection and tracing."""
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_role, UserRole
from app.config import settings
from app.core.resp import ok
from app.knowledge import task_store
from app.knowledge.document_graph import inspect_document
from app.knowledge.ingest_worker import _parse_artifact_ref, parse_artifact_json
from app.services.source_asset_store import SourceAssetStore

router = APIRouter()
admin = require_role([UserRole.ADMIN, UserRole.MANAGER])


@router.get("/admin/document-capabilities")
async def capabilities(_admin=Depends(admin)):
    from app.database import get_neo4j_driver, get_redis
    from app.observability.tracing import tracing_status
    workers = {}
    for name in ("parser-worker", "ingest-worker", "reconciler"):
        try:
            workers[name] = bool(await get_redis().exists(f"worker:alive:{name}"))
        except Exception:
            workers[name] = False
    neo4j_ready = False
    try:
        await asyncio.to_thread(get_neo4j_driver().verify_connectivity)
        neo4j_ready = settings.NEO4J_ENABLED
    except Exception:
        pass
    jaeger_ready = False
    query_url = settings.JAEGER_QUERY_URL or settings.JAEGER_UI_URL
    if urlsplit(query_url).hostname in {"127.0.0.1", "localhost", "::1"} or settings.JAEGER_QUERY_URL:
        try:
            async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
                response = await client.get(query_url.rstrip("/") + "/api/services")
                jaeger_ready = response.status_code == 200
        except Exception:
            pass
    return ok(data={"mineru": {"configured": settings.MINERU_ENABLED and Path(settings.MINERU_EXECUTABLE).is_file(),
                               "backend": "local", "tier": "flash", "formats": ["pdf"], "workers": workers},
                    "neo4j": {"connected": neo4j_ready, "retrieval_enabled": settings.KG_EXPAND_ENABLED,
                              "browser_url": _neo4j_browser_url()},
                    "telemetry": {**tracing_status(), "jaeger_ready": jaeger_ready,
                                  "jaeger_url": settings.JAEGER_UI_URL}})


def _neo4j_browser_url():
    if settings.NEO4J_BROWSER_URL:
        return settings.NEO4J_BROWSER_URL
    host = urlsplit(settings.NEO4J_URI).hostname
    if not host or urlsplit(settings.NEO4J_URI).scheme not in {"bolt", "neo4j"}:
        return None
    host = "[" + host + "]" if ":" in host else host
    return f"http://{host}:7474/browser/"


def _read_ir(ref: dict, task_id: str, asset: dict):
    store = SourceAssetStore()
    temporary = store.fetch_to_temp(ref["bucket"], ref["key"], expected_sha256=ref["sha256"])
    try:
        raw = Path(temporary).read_bytes()
        if len(raw) != ref["size"]:
            raise ValueError("Stored artifact size differs from authority")
        parsed, _ = parse_artifact_json(json.loads(raw), expected_task_id=task_id, expected_asset_id=asset["asset_id"])
        if (parsed.source.document_id != asset["document_id"] or parsed.source.sha256 != asset["sha256"]
                or parsed.parse_fingerprint() != asset["parse_fingerprint"]):
            raise ValueError("IR identity differs from SourceAsset authority")
        return parsed
    finally:
        store.cleanup_temp(temporary)


@router.get("/admin/document-inspection/{task_id}")
async def document_inspection(task_id: str, _admin=Depends(admin)):
    task = await task_store.get_task(task_id)
    if task is None:
        raise HTTPException(404, "导入任务不存在")
    assets = await task_store.get_source_assets(task_id)
    documents = []
    for asset in assets:
        ref = _parse_artifact_ref(asset.get("artifact_ref"))
        if not ref:
            documents.append({"file_name": asset.get("file_name"), "stage": asset.get("stage"), "available": False})
            continue
        parsed = await asyncio.to_thread(_read_ir, ref, task_id, asset)
        try:
            if parsed.parser_backend=='edu-video-compiler':
                from app.domains.video_learning.graph import inspect_ready_video
                metadata=parsed.blocks[0].metadata
                graph=await inspect_ready_video(int(metadata['video_id']),expected_sha256=metadata['distill_artifact_sha256'])
                graph['nodes']=[{**n,'kind':'term' if n['kind']=='chapter' else n['kind']} for n in graph['nodes'] if n['kind']!='video']
                graph['edges']=[{'source':e['target'],'target':e['source'],'relation':'BELONGS_TO'} for e in graph['edges'] if e['relation']=='RAG_CHUNK']
            else:
                graph = await asyncio.to_thread(inspect_document, asset["document_id"], task["tenant_id"], asset["parse_fingerprint"])
        except Exception:
            graph = {"available": False, "nodes": [], "edges": [], "error": "Neo4j 查询暂不可用；文档入库独立运行"}
        documents.append({"available": True, "file_name": asset.get("file_name"), "document_id": asset["document_id"],
                          "stage": asset.get("stage"), "vector_status": asset.get("vector_status"),
                          "graph_status": ('video_ready_projection' if parsed.parser_backend=='edu-video-compiler' and graph.get('available') else asset.get("graph_status")), "parser_backend": parsed.parser_backend,
                          "parser_version": parsed.parser_version, "page_count": parsed.page_count,
                          "parse_fingerprint": parsed.parse_fingerprint(),
                          "blocks": [block.model_dump(mode="json") for block in parsed.blocks[:200]], "graph": graph})
    return ok(data={"task_id": task_id, "documents": documents, "jaeger_url": settings.JAEGER_UI_URL})
