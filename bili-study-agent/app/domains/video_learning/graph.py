"""Rebuildable Neo4j projection of the current READY video and existing RAG IDs."""
import asyncio
import json
from app.common.exceptions import AppException
from app.config import settings
from app.database import get_neo4j_driver
from app.services.source_asset_store import SourceAssetStore
from app.knowledge.importer.loader import COLLECTION_NAME,get_milvus_client
from app.observability.tracing import span
from .publication import get_video_publication,_read_verified_artifact


def _key(row):return f"video:{row['video_id']}:{row['artifact_sha256']}"


def _write_projection(row):
    artifact=_read_verified_artifact(SourceAssetStore(),row)
    identity=_key(row)
    scope=f'tenant_id == {json.dumps(settings.COURSE_PUBLIC_PARTITION)} and video_id == {int(row["video_id"])} and generation == {json.dumps(row["artifact_id"])} and distill_artifact_sha256 == {json.dumps(row["artifact_sha256"])} and generation_state == "active"'
    chunks=get_milvus_client().query(collection_name=COLLECTION_NAME,filter=scope,limit=1001,
        output_fields=['chunk_id','content','tenant_id','visibility','video_id','session_id','series_id','generation','distill_artifact_sha256','start_seconds','end_seconds'],consistency_level='Strong')
    if not chunks or len(chunks)>1000:raise ValueError('Current READY video must have 1–1000 verified RAG chunks')
    chapters=[{'key':identity+f':chapter:{i}','name':c.title,'start':c.start,
        'end':artifact.chapters[i+1].start if i+1<len(artifact.chapters) else artifact.source.duration,
        'kp':identity+f':kp:{i}'} for i,c in enumerate(artifact.chapters)]
    rows=[]
    for chunk in chunks:
        chapter=next((c for c in reversed(chapters) if c['start']<=float(chunk['start_seconds'])),None)
        if not chapter:raise ValueError('RAG chunk has no canonical chapter')
        rows.append({**chunk,'key':'chunk:'+chunk['chunk_id'],'chapter':chapter['key'],'kp':chapter['kp'],'preview':chunk['content'][:120]})
    driver=get_neo4j_driver()
    if not settings.NEO4J_ENABLED or driver is None:raise RuntimeError('Neo4j video projection unavailable')
    with span('neo4j.project_video',attributes={'video.id':row['video_id'],'video.generation':row['artifact_id'],'video.artifact_sha256':row['artifact_sha256'],'video.chunks':len(rows)}) as trace:
        with driver.session(database=settings.NEO4J_DATABASE) as session:
            def write(tx):
                tx.run("""MERGE (v:Video {source:'kg_sync',key:$key})
                  SET v.video_id=$video_id,v.generation=$generation,v.artifact_sha256=$sha,v.name=$name,v.publication_id=$publication
                  WITH v UNWIND $chapters AS row
                  MERGE (c:Chapter {source:'kg_sync',key:row.key}) SET c.name=row.name,c.start_seconds=row.start,c.end_seconds=row.end
                  MERGE (k:KnowledgePoint {source:'kg_sync',key:row.kp}) SET k.name=row.name,k.origin='video_chapter'
                  MERGE (v)-[:HAS_CHAPTER]->(c) MERGE (c)-[:MENTIONS]->(k)
                """,key=identity,video_id=row['video_id'],generation=row['artifact_id'],sha=row['artifact_sha256'],
                    name=artifact.summary.title,publication=row['id'],chapters=chapters).consume()
                tx.run("""UNWIND $rows AS row
                  MATCH (chapter:Chapter {source:'kg_sync',key:row.chapter}),(kp:KnowledgePoint {source:'kg_sync',key:row.kp})
                  MERGE (c:DocChunk {source:'kg_sync',key:row.key})
                  SET c.chunk_id=row.chunk_id,c.preview=row.preview,c.tenant_id=row.tenant_id,c.visibility=row.visibility,
                      c.video_id=row.video_id,c.session_id=row.session_id,c.series_id=row.series_id,c.generation=row.generation,
                      c.artifact_sha256=row.distill_artifact_sha256,c.start_seconds=row.start_seconds,c.end_seconds=row.end_seconds
                  MERGE (c)-[:BELONGS_TO]->(chapter) MERGE (c)-[:MENTIONS]->(kp)
                """,rows=rows).consume()
                pairs=[{'a':chapters[i]['kp'],'b':chapters[i+1]['kp']} for i in range(len(chapters)-1)]
                tx.run("""UNWIND $pairs AS row MATCH (a:KnowledgePoint {source:'kg_sync',key:row.a}),(b:KnowledgePoint {source:'kg_sync',key:row.b})
                  MERGE (a)-[r:RELATED {video_version:$key}]->(b) SET r.basis='adjacent_video_chapters'
                """,pairs=pairs,key=identity).consume()
            session.execute_write(write)
        return {'status':'succeeded','video_id':row['video_id'],'generation':row['artifact_id'],
            'artifact_sha256':row['artifact_sha256'],'chapter_count':len(chapters),'chunk_count':len(rows),
            'trace_id':trace.trace_id if trace else None}


async def project_ready_video(video_id:int, *, expected_sha256:str|None=None):
    row=await get_video_publication(video_id)
    if not row:raise AppException('40900','视频尚无正式 READY 资料，不能生成正式图谱',http_status=409)
    if expected_sha256 and row['artifact_sha256']!=expected_sha256:
        raise AppException('40900','正式版本已改变，请刷新后再同步图谱',http_status=409)
    result=await asyncio.to_thread(_write_projection,row)
    current=await get_video_publication(video_id)
    if not current or current['id']!=row['id']:
        raise AppException('40900','图谱生成期间正式版本已改变；旧图谱保留，请同步当前版本',http_status=409)
    return result


def _inspect(row):
    nodes=[{'id':_key(row),'label':'视频正式版本','kind':'video'}];edges=[]
    with get_neo4j_driver().session(database=settings.NEO4J_DATABASE) as session:
        records=session.run("""MATCH (v:Video {source:'kg_sync',key:$key})-[:HAS_CHAPTER]->(ch:Chapter)
          OPTIONAL MATCH (c:DocChunk {source:'kg_sync'})-[:BELONGS_TO]->(ch)
          RETURN ch.key AS key,ch.name AS name,ch.start_seconds AS start,
            collect(DISTINCT {id:c.chunk_id,start:c.start_seconds,preview:c.preview}) AS chunks
          ORDER BY start LIMIT 100""",key=_key(row))
        for record in records:
            nodes.append({'id':record['key'],'label':record['name'],'kind':'chapter','time_anchor':record['start']})
            edges.append({'source':_key(row),'target':record['key'],'relation':'HAS_CHAPTER'})
            for chunk in record['chunks']:
                if chunk['id']:
                    nodes.append({'id':chunk['id'],'label':chunk['preview'],'kind':'chunk','time_anchor':chunk['start']})
                    edges.append({'source':record['key'],'target':chunk['id'],'relation':'RAG_CHUNK'})
    return {'video_id':row['video_id'],'generation':row['artifact_id'],'artifact_sha256':row['artifact_sha256'],
        'available':len(nodes)>1,'nodes':nodes,'edges':edges,'meaning':'章节来自正式资料，分块ID来自现有Milvus；相邻章节关联不代表先修关系。'}


async def inspect_ready_video(video_id:int, *, expected_sha256:str|None=None):
    row=await get_video_publication(video_id)
    if not row:raise AppException('40440','本视频暂无正式 READY 资料',http_status=404)
    if expected_sha256 and row['artifact_sha256']!=expected_sha256:
        raise AppException('40900','这份视频产物属于旧版本，请在课次中查看当前正式版本图谱',http_status=409)
    return await asyncio.to_thread(_inspect,row)
