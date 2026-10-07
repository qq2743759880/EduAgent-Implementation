"""Neo4j projection of authorized, active document chunks (derived, rebuildable)."""
from __future__ import annotations

import hashlib
import re
from itertools import combinations

from app.config import settings
from app.database import get_neo4j_driver
from app.observability.tracing import span, remote_parent
from app.knowledge.models import ContentType


def is_document_projection_chunk(chunk) -> bool:
    return chunk.content_type == ContentType.DOC_CHUNK and (chunk.parser_backend == 'mineru' or
        (chunk.parser_backend == 'legacy_str' and bool(chunk.extra.get('document_id')) and
         bool(chunk.block_ids or chunk.extra.get('block_ids')) and bool(chunk.parse_fingerprint or chunk.extra.get('parse_fingerprint'))))


def projection_rows(chunks, tenant_id: str, task_id: str) -> list[dict]:
    rows = []
    stop = {"the", "and", "for", "that", "with", "this", "from", "are", "not", "its", "only", "each", "can", "must", "when",
            "include", "includes", "including", "affect", "result", "requested", "occurs", "requires", "already",
            "controls", "prove", "reads", "together", "updates", "should", "often", "using", "improves", "reduces", "first", "later", "more", "than"}
    for chunk in chunks:
        if not is_document_projection_chunk(chunk) or chunk.extra.get("generation_state") != "active":
            continue
        terms = list(dict.fromkeys(word.lower() for word in re.findall(r"[A-Za-z][A-Za-z-]{2,}|[\u4e00-\u9fff]{2,8}", chunk.content)
                                   if word.lower() not in stop))[:8]
        if chunk.block_type == "title":
            terms = [chunk.content.strip().lower()[:120]]
        def key(term):
            return "kp:document:" + hashlib.sha256((tenant_id + "\x1f" + term).encode()).hexdigest()[:24]
        rows.append({"key": "chunk:" + chunk.chunk_id, "chunk_id": chunk.chunk_id,
                     "document_id": getattr(chunk, "document_id", None) or chunk.extra.get("document_id"),
                     "generation": chunk.parse_fingerprint or chunk.extra.get("parse_fingerprint"),
                     "task_id": task_id, "tenant_id": tenant_id, "parser_backend": chunk.parser_backend,
                     "visibility": chunk.visibility.value, "page_start": chunk.page_start, "page_end": chunk.page_end,
                     "terms": [{"key": key(term), "name": term} for term in terms],
                     "pairs": [{"a": key(a), "b": key(b)} for a, b in combinations(terms, 2)]})
    return rows


def project_document(chunks, tenant_id: str, task_id: str, trace_context: dict | None = None) -> dict:
    rows = projection_rows(chunks, tenant_id, task_id)
    if not rows:
        return {"chunks": 0, "mentions": 0}
    driver = get_neo4j_driver()
    if not settings.NEO4J_ENABLED or driver is None:
        raise RuntimeError("Neo4j document projection unavailable")
    with span("neo4j.project_document", parent=remote_parent(trace_context), attributes={"task.id": task_id, "document.chunks": len(rows)}):
        with driver.session(database=settings.NEO4J_DATABASE) as session:
            # Bounded additive indexes for the existing graph bridge; no graph rebuild.
            session.run("CREATE INDEX edu_docchunk_lookup IF NOT EXISTS FOR (n:DocChunk) ON (n.source,n.chunk_id)").consume()
            session.run("CREATE INDEX edu_document_term_lookup IF NOT EXISTS FOR (n:KnowledgePoint) ON (n.source,n.key)").consume()
            def write(tx):
                tx.run("""
                  UNWIND $rows AS row
                  MERGE (c:DocChunk {source:'kg_sync', key:row.key})
                  SET c += {chunk_id:row.chunk_id, document_id:row.document_id, generation:row.generation,
                            task_id:row.task_id, tenant_id:row.tenant_id, parser_backend:row.parser_backend,
                            visibility:row.visibility, page_start:row.page_start, page_end:row.page_end}
                  WITH c,row UNWIND row.terms AS term
                  MERGE (k:KnowledgePoint {source:'kg_sync', key:term.key})
                  SET k.name=term.name, k.tenant_id=row.tenant_id, k.origin='document_terms'
                  MERGE (c)-[:MENTIONS]->(k)
                """, rows=rows).consume()
                tx.run("""
                  UNWIND $rows AS row UNWIND row.pairs AS pair
                  MATCH (a:KnowledgePoint {source:'kg_sync', key:pair.a}),
                        (b:KnowledgePoint {source:'kg_sync', key:pair.b})
                  MERGE (a)-[r:RELATED {document_id:row.document_id, generation:row.generation}]->(b)
                  SET r.basis='cooccurrence'
                """, rows=rows).consume()
            session.execute_write(write)
    return {"chunks": len(rows), "mentions": sum(len(row["terms"]) for row in rows)}


def inspect_document(document_id: str, tenant_id: str, generation: str) -> dict:
    driver = get_neo4j_driver()
    if driver is None:
        return {"available": False, "nodes": [], "edges": []}
    with driver.session(database=settings.NEO4J_DATABASE) as session:
        result = session.run("""
          MATCH (c:DocChunk {source:'kg_sync',document_id:$document,tenant_id:$tenant,generation:$generation})
          OPTIONAL MATCH (c)-[:MENTIONS]->(k:KnowledgePoint)
          RETURN c.chunk_id AS chunk_id,c.page_start AS page_start,c.page_end AS page_end,
                 collect(DISTINCT {key:k.key,name:k.name}) AS terms ORDER BY c.chunk_id LIMIT 100
        """, document=document_id, tenant=tenant_id, generation=generation)
        nodes, edges = {}, []
        for row in result:
            cid = row["chunk_id"]
            nodes[cid] = {"id": cid, "label": f"第 {row['page_start']}–{row['page_end']} 页", "kind": "chunk"}
            for term in row["terms"]:
                if not term["key"]:
                    continue
                nodes[term["key"]] = {"id": term["key"], "label": term["name"], "kind": "term"}
                edges.append({"source": cid, "target": term["key"], "relation": "MENTIONS"})
        return {"available": True, "nodes": list(nodes.values()), "edges": edges,
                "meaning": "关键词来自文档原文；关联表示共同出现，不代表先修关系。"}
