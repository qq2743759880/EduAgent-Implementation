# -*- coding: utf-8 -*-
"""KG-1 图谱同步核心（R-N1）：MySQL(+Milvus 只读) → Neo4j 抽取与幂等写入。

红线对齐（派单 R-N1）：
- Neo4j 写操作**仅**发生在本模块（经 scripts/kg_sync.py CLI 调用）——有备份、幂等；
- Milvus **只读**（doc_chunk 内容抽取，失败降级跳过不阻断）；
- MySQL 只读（series / series_cohort_course / series_cohort / graph_node / graph_edge）；
- 不碰 app/ai/**、analytics 等其他 agent 域。

建模（planId=reshape-r-kg，contracts/reshape-r-kg.json draft）：
  节点  Course(key=series:<id>) / Chapter(key=module:<module_code>)
        / KnowledgePoint(key=kp:<code>) / DocChunk(key=chunk:<chunk_id>)
  关系  PREREQUISITE(KP→KP，MySQL graph_edge) / BELONGS_TO(Chapter→Course、DocChunk→Course|Chapter)
        / MENTIONS(Chapter→KP 规则=module_contains；DocChunk→KP 规则=keyword_match)
        / RELATED(KP→KP，MySQL graph_edge RELATED_TO/RELATED)
  隔离  本模块写入的所有节点带 source='kg_sync'——全量重建只删自己的子图，
        P1 遗留数据（CourseSeries/CourseModule/QuestionTag/旧 KnowledgePoint）不动；
        KG-2 查询一律按 source='kg_sync' 作用域，天然免疫遗留数据污染。

幂等：MERGE 按 key 幂等；节点/关系属性全部确定性（无时间戳）；重跑计数不变。
备份：写入前导出 kg_sync 子图清单 + 全图标签快照 → data/kg_backup/*.json。

注意：Neo4j 服务器未装 APOC（2026-09-18 实测 ProcedureNotFound），全部纯 Cypher。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

KG_SOURCE = "kg_sync"

NODE_LABELS = ("Course", "Chapter", "KnowledgePoint", "DocChunk")
REL_TYPES = ("PREREQUISITE", "BELONGS_TO", "MENTIONS", "RELATED")

MAX_MENTIONS_PER_CHUNK = 6  # 单 chunk MENTIONS 上限（关键词命中封顶，防 clique 爆炸）

_WS_RE = re.compile(r"\s+")


def norm_text(s: str | None) -> str:
    """规则抽取的归一化：去首尾空白 + 压缩内部空白 + lower。"""
    return _WS_RE.sub(" ", (s or "").strip()).lower()


# ══════════════════════════════════════════════════════════════
# 数据抽取（MySQL 只读）
# ══════════════════════════════════════════════════════════════
async def extract_mysql_sources() -> dict[str, Any]:
    """抽取 MySQL 课程/章/知识点/先修边（全部只读 SELECT）。

    真实库实测（2026-09-18）：series 2815 行；series_cohort_course distinct
    module_code=659；(module_code,series_id) 对=7886；graph_node KP=18；
    graph_edge PREREQUISITE=14、CONTAINS=19。session_video_chapter 61 万行
    属视频切片，不作为 Chapter 节点源（Chapter=课程模块，与 C 端模块列表对齐）。
    """
    from app.database import fetch_all

    courses = await fetch_all(
        "SELECT id, series_code, series_name, delivery_mode, sale_status FROM series"
    )
    chapters = await fetch_all(
        "SELECT module_code, MIN(module_name) AS module_name, MIN(stage_no) AS stage_no "
        "FROM series_cohort_course GROUP BY module_code"
    )
    belongs_rows = await fetch_all(
        "SELECT DISTINCT sc.series_id AS series_id, scc.module_code AS module_code "
        "FROM series_cohort_course scc "
        "JOIN series_cohort sc ON sc.id = scc.cohort_id"
    )
    kps = await fetch_all(
        "SELECT code, name, subject_code FROM graph_node "
        "WHERE label='KnowledgePoint' AND yn=1"
    )
    # CONTAINS(CourseModule→KP) → Chapter MENTIONS KP（规则抽取 rule=module_contains）
    contains_rows = await fetch_all(
        "SELECT DISTINCT fm.code AS module_code, tn.code AS kp_code FROM graph_edge e "
        "JOIN graph_node fm ON fm.id = e.from_node_id "
        "JOIN graph_node tn ON tn.id = e.to_node_id "
        "WHERE e.rel_type='CONTAINS' AND e.yn=1 "
        "AND fm.label='CourseModule' AND tn.label='KnowledgePoint' AND fm.yn=1 AND tn.yn=1"
    )
    prereq_rows = await fetch_all(
        "SELECT DISTINCT fm.code AS src, tn.code AS dst FROM graph_edge e "
        "JOIN graph_node fm ON fm.id = e.from_node_id "
        "JOIN graph_node tn ON tn.id = e.to_node_id "
        "WHERE e.rel_type='PREREQUISITE' AND e.yn=1 "
        "AND fm.label='KnowledgePoint' AND tn.label='KnowledgePoint' AND fm.yn=1 AND tn.yn=1"
    )
    related_rows = await fetch_all(
        "SELECT DISTINCT fm.code AS src, tn.code AS dst FROM graph_edge e "
        "JOIN graph_node fm ON fm.id = e.from_node_id "
        "JOIN graph_node tn ON tn.id = e.to_node_id "
        "WHERE e.rel_type IN ('RELATED_TO','RELATED') AND e.yn=1 "
        "AND fm.label='KnowledgePoint' AND tn.label='KnowledgePoint' AND fm.yn=1 AND tn.yn=1"
    )

    course_nodes = [
        {
            "key": f"series:{r['id']}",
            "props": {
                "source": KG_SOURCE,
                "series_id": int(r["id"]),
                "code": r["series_code"],
                "name": r["series_name"],
                "delivery_mode": r["delivery_mode"],
                "sale_status": r["sale_status"],
            },
        }
        for r in courses
    ]
    chapter_nodes = [
        {
            "key": f"module:{r['module_code']}",
            "props": {
                "source": KG_SOURCE,
                "code": r["module_code"],
                "name": r["module_name"],
                "stage_no": int(r["stage_no"] or 0),
            },
        }
        for r in chapters
    ]
    kp_nodes = [
        {
            "key": f"kp:{r['code']}",
            "props": {
                "source": KG_SOURCE,
                "code": r["code"],
                "name": r["name"],
                "subject_code": r["subject_code"],
            },
        }
        for r in kps
    ]
    kp_codes = {r["code"] for r in kps}
    chapter_keys = {c["key"] for c in chapter_nodes}

    belongs = [
        {"a": f"module:{r['module_code']}", "b": f"series:{int(r['series_id'])}"}
        for r in belongs_rows
        if f"module:{r['module_code']}" in chapter_keys
    ]
    # 章节覆盖知识点（rule=module_contains）
    mentions_chapter = [
        {"a": f"module:{r['module_code']}", "b": f"kp:{r['kp_code']}", "rule": "module_contains"}
        for r in contains_rows
        if r["kp_code"] in kp_codes and f"module:{r['module_code']}" in chapter_keys
    ]
    prereq = [
        {"a": f"kp:{r['src']}", "b": f"kp:{r['dst']}", "rule": "mysql_graph_edge"}
        for r in prereq_rows
        if r["src"] in kp_codes and r["dst"] in kp_codes
    ]
    related = [
        {"a": f"kp:{r['src']}", "b": f"kp:{r['dst']}", "rule": "mysql_graph_edge"}
        for r in related_rows
        if r["src"] in kp_codes and r["dst"] in kp_codes
    ]
    return {
        "courses": course_nodes,
        "chapters": chapter_nodes,
        "kps": kp_nodes,
        "belongs": belongs,
        "mentions_chapter": mentions_chapter,
        "prereq": prereq,
        "related": related,
    }


# ══════════════════════════════════════════════════════════════
# 数据抽取（Milvus 只读，可降级）
# ══════════════════════════════════════════════════════════════
def extract_doc_chunks(limit: int = 5000) -> list[dict[str, Any]]:
    """只读抽取 Milvus doc_chunk（content_type=='doc_chunk'）。

    Milvus 不可达/查询失败 → 返回 []（WARN 降级，同步主体 Course/Chapter/KP 不受影响）。
    output_fields 先按全字段尝试，老 schema 缺列时回退最小字段集。
    """
    try:
        from app.knowledge.importer.loader import COLLECTION_NAME, get_milvus_client

        client = get_milvus_client()
        if not client.has_collection(COLLECTION_NAME):
            return []
        fields_full = ["chunk_id", "content", "keywords", "tags", "series_code", "module_codes"]
        try:
            rows = client.query(
                collection_name=COLLECTION_NAME,
                filter="content_type == 'doc_chunk'",
                output_fields=fields_full,
                limit=limit,
            )
        except Exception:
            rows = client.query(
                collection_name=COLLECTION_NAME,
                filter="content_type == 'doc_chunk'",
                output_fields=["chunk_id", "content"],
                limit=limit,
            )
        return list(rows)
    except Exception as exc:  # 降级：doc_chunk 是增强项，不阻断主体同步
        import logging

        logging.getLogger(__name__).warning(
            "[kg_sync] Milvus doc_chunk 抽取失败（降级跳过，不阻断主体同步）: %s", exc
        )
        return []


def build_chunk_graph(
    chunks: list[dict[str, Any]],
    kp_nodes: list[dict[str, Any]],
    chapter_nodes: list[dict[str, Any]],
    course_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """规则抽取：DocChunk 节点 + MENTIONS(chunk→KP) + BELONGS_TO(chunk→Course/Chapter)。

    MENTIONS 规则（rule=keyword_match）：KP 名与 chunk keywords/tags 归一化精确命中
    （score=2）或 KP 名出现在 content 正文（score=1），按分降序取前 MAX_MENTIONS_PER_CHUNK。
    """
    kp_names: dict[str, dict[str, str]] = {}  # norm_name -> {key, code, name}
    for n in kp_nodes:
        nm = norm_text(n["props"].get("name"))
        if nm:
            kp_names[nm] = n["props"]

    chunk_nodes: list[dict[str, Any]] = []
    mentions: list[dict[str, Any]] = []
    belongs_course: list[dict[str, Any]] = []
    belongs_chapter: list[dict[str, Any]] = []

    course_by_code: dict[str, str] = {}
    for c in course_nodes:
        code = c["props"].get("code")
        if code and code not in course_by_code:  # 跨机构同码取最小 series_id（抽取序稳定）
            course_by_code[code] = c["key"]
    chapter_keys = {c["key"] for c in chapter_nodes}

    for r in chunks:
        chunk_id = str(r.get("chunk_id") or "")
        if not chunk_id:
            continue
        content = str(r.get("content") or "")
        chunk_key = f"chunk:{chunk_id}"
        chunk_nodes.append(
            {
                "key": chunk_key,
                "props": {"source": KG_SOURCE, "chunk_id": chunk_id, "preview": content[:120]},
            }
        )
        # MENTIONS（规则抽取）
        kws = [norm_text(k) for k in (r.get("keywords") or []) if k]
        kws += [norm_text(t) for t in (r.get("tags") or []) if t]
        scored: list[tuple[int, str, dict[str, str]]] = []
        content_norm = norm_text(content)
        for nm, props in kp_names.items():
            score = 0
            if nm in kws:
                score += 2
            if nm in content_norm:
                score += 1
            if score > 0:
                scored.append((score, props["code"], props))
        scored.sort(key=lambda t: (-t[0], t[1]))
        for score, _code, props in scored[:MAX_MENTIONS_PER_CHUNK]:
            mentions.append(
                {"a": chunk_key, "b": f"kp:{props['code']}", "rule": f"keyword_match:{score}"}
            )
        # BELONGS_TO Course（series_code 元数据）
        sc = r.get("series_code")
        if sc and str(sc) in course_by_code:
            belongs_course.append({"a": chunk_key, "b": course_by_code[str(sc)]})
        # BELONGS_TO Chapter（module_codes 元数据）
        for mc in r.get("module_codes") or []:
            k = f"module:{mc}"
            if k in chapter_keys:
                belongs_chapter.append({"a": chunk_key, "b": k})

    return {
        "chunks": chunk_nodes,
        "mentions_chunk": mentions,
        "belongs_chunk_course": belongs_course,
        "belongs_chunk_chapter": belongs_chapter,
    }


# ══════════════════════════════════════════════════════════════
# Neo4j 写入（幂等 MERGE，纯 Cypher 无 APOC）
# ══════════════════════════════════════════════════════════════
_LABEL_REL_ENDPOINT = {
    "PREREQUISITE": ("KnowledgePoint", "KnowledgePoint"),
    "RELATED": ("KnowledgePoint", "KnowledgePoint"),
    "MENTIONS": (None, "KnowledgePoint"),  # 源端可为 Chapter 或 DocChunk
    "BELONGS_TO": (None, None),            # Chapter→Course / DocChunk→Course|Chapter
}


def _run_batches(session: Any, statements: list[tuple[str, list[dict]]], batch: int = 500) -> int:
    """UNWIND 分批执行，返回受影响行数合计。"""
    total = 0
    for cypher, rows in statements:
        for i in range(0, len(rows), batch):
            session.run(cypher, rows=rows[i : i + batch]).consume()
            total += min(batch, len(rows) - i)
    return total


_UPSERT_NODE = (
    "UNWIND $rows AS row MERGE (n:{label} {{key: row.key}}) SET n += row.props"
)
_UPSERT_REL = (
    "UNWIND $rows AS row "
    "MATCH (a {{key: row.a}}) MATCH (b {{key: row.b}}) "
    "MERGE (a)-[r:{rel}]->(b) "
    "SET r.rule = coalesce(row.rule, r.rule)"
)


def write_graph(driver: Any, sources: dict[str, Any], database: str | None = None) -> dict[str, int]:
    """幂等写入全部节点与关系（MERGE by key；属性确定性 → 重跑不翻倍不改值）。"""
    node_statements: list[tuple[str, list[dict]]] = []
    for label, rows_key in (
        ("Course", "courses"),
        ("Chapter", "chapters"),
        ("KnowledgePoint", "kps"),
        ("DocChunk", "chunks"),
    ):
        rows = [{"key": n["key"], "props": n["props"]} for n in sources.get(rows_key, [])]
        if rows:
            node_statements.append((_UPSERT_NODE.format(label=label), rows))

    rel_statements: list[tuple[str, list[dict]]] = []
    for rel, rows_key in (
        ("PREREQUISITE", "prereq"),
        ("RELATED", "related"),
        ("BELONGS_TO", "belongs"),
        ("BELONGS_TO", "belongs_chunk_course"),
        ("BELONGS_TO", "belongs_chunk_chapter"),
        ("MENTIONS", "mentions_chapter"),
        ("MENTIONS", "mentions_chunk"),
    ):
        rows = list(sources.get(rows_key, []))
        if rows:
            rel_statements.append((_UPSERT_REL.format(rel=rel), rows))

    counts: dict[str, int] = {}
    with driver.session(database=database) as session:
        counts["nodes"] = _run_batches(session, node_statements)
        counts["rels"] = _run_batches(session, rel_statements)
    return counts


def delete_kg_subgraph(driver: Any, database: str | None = None) -> int:
    """全量重建前置：仅删除 source='kg_sync' 子图（P1 遗留数据不动）。"""
    with driver.session(database=database) as session:
        summary = session.run(
            "MATCH (n) WHERE n.source=$src DETACH DELETE n", src=KG_SOURCE
        ).consume()
        counters = summary.counters
        return int(getattr(counters, "nodes_deleted", 0) or 0)


# ══════════════════════════════════════════════════════════════
# 备份（写前导出，对齐数据软删三核闸纪律）
# ══════════════════════════════════════════════════════════════
def backup_kg_subgraph(driver: Any, backup_dir: Path, database: str | None = None) -> Path:
    """导出 kg_sync 子图（节点全属性 + 关系清单）与全图标签/关系类型快照 → JSON。"""
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    out = backup_dir / f"kg_backup_{now}.json"
    payload: dict[str, Any] = {
        "created_at": now,
        "uri_host": settings.NEO4J_URI.split("//")[-1].split("/")[0],
        "database": database or settings.NEO4J_DATABASE,
        "scope": "source='kg_sync' 子图 + 全图标签/关系类型计数快照（遗留数据审计用）",
        "nodes": [],
        "rels": [],
        "global_snapshot": {},
    }
    with driver.session(database=database) as session:
        nodes = session.run(
            "MATCH (n) WHERE n.source=$src RETURN labels(n) AS labels, properties(n) AS props",
            src=KG_SOURCE,
        ).data()
        payload["nodes"] = nodes
        rels = session.run(
            "MATCH (a)-[r]->(b) WHERE a.source=$src AND b.source=$src "
            "RETURN type(r) AS type, a.key AS a, b.key AS b, properties(r) AS props",
            src=KG_SOURCE,
        ).data()
        payload["rels"] = rels
        labels = session.run(
            "MATCH (n) UNWIND labels(n) AS l RETURN l AS label, count(*) AS c ORDER BY l"
        ).data()
        rel_types = session.run(
            "MATCH ()-[r]->() UNWIND type(r) AS t RETURN t AS rel, count(*) AS c ORDER BY t"
        ).data()
        payload["global_snapshot"] = {
            "labels": {r["label"]: r["c"] for r in labels},
            "rel_types": {r["rel"]: r["c"] for r in rel_types},
        }
    out.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    return out


# ══════════════════════════════════════════════════════════════
# 计数自证（幂等验收用：同步两轮计数对比）
# ══════════════════════════════════════════════════════════════
def kg_counts(driver: Any, database: str | None = None) -> dict[str, Any]:
    """kg_sync 子图 + 全图计数快照。"""
    counts: dict[str, Any] = {"kg": {}, "global_labels": {}, "global_rels": {}}
    with driver.session(database=database) as session:
        for label in NODE_LABELS:
            counts["kg"][f"node:{label}"] = session.run(
                f"MATCH (n:{label}) WHERE n.source=$src RETURN count(n) AS c", src=KG_SOURCE
            ).single()["c"]
        for rel in REL_TYPES:
            counts["kg"][f"rel:{rel}"] = session.run(
                f"MATCH ()-[r:{rel}]->() "
                "WHERE (startNode(r).source=$src OR endNode(r).source=$src) RETURN count(r) AS c",
                src=KG_SOURCE,
            ).single()["c"]
        for r in session.run(
            "MATCH (n) UNWIND labels(n) AS l RETURN l AS label, count(*) AS c ORDER BY l"
        ).data():
            counts["global_labels"][r["label"]] = r["c"]
        for r in session.run(
            "MATCH ()-[r]->() UNWIND type(r) AS t RETURN t AS rel, count(*) AS c ORDER BY t"
        ).data():
            counts["global_rels"][r["rel"]] = r["c"]
    return counts
