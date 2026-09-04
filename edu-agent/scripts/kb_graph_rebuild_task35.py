# -*- coding: utf-8 -*-
"""
task35 · Neo4j 课程/题目知识图谱重建 + retriever 图谱通道连通实证

背景：Neo4j 已接入（VM bolt://192.168.85.101:7687 可达），但图谱为空（task34 rebuild 仅清空）。
本脚本从 task34 冻结的课程/题目切片（data/kb_slices/*.json）用 build_graph_relations 抽取实体关系，
再用**原生 Cypher MERGE**（不依赖 APOC，APOC 未装）写入 Neo4j，保留 4 类标签
（CourseSeries/CourseModule/KnowledgePoint/QuestionTag）与 5 类关系
（CONTAINS/TESTS/PREREQUISITE/RELATED_TO/GRAPH_LINK 兜底），与 P4 推荐/P9 思维导图语义对齐。

验收（critique-backlog-tracker §task35）：
  1) 图谱实体入库                 → 打印 Neo4j 节点/关系计数（MATCH 实测）
  2) retriever.graph_entities 非空 → 用 app.chat.retriever._graph_expand(enable_graph=True) 跑真实查询
  3) Neo4j 连通无降级             → degraded_reason 为 None（不再走 task-P1C 熔断快败）

用法：
  .venv\\Scripts\\python.exe scripts\\kb_graph_rebuild_task35.py
输出：
  脚本内打印 + 可复写 test-reports/task35_graph_rebuild_result.json
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

EDU_AGENT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EDU_AGENT))
os.chdir(EDU_AGENT)

from app.config import settings  # noqa: E402
from app.knowledge.importer.graph_builder import _parse_entity, build_graph_relations  # noqa: E402
from app.knowledge.models import KnowledgeChunk  # noqa: E402

SLICE_DIR = EDU_AGENT / "data" / "kb_slices"
OUT_PATH = EDU_AGENT.parent / "test-reports" / "task35_graph_rebuild_result.json"

# 关系类型白名单（与 graph_builder 契约一致）
_REL_TYPES = {"CONTAINS", "TESTS", "PREREQUISITE", "RELATED_TO"}


def load_chunks() -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    for name in ("courses.json", "questions.json"):
        data = json.loads((SLICE_DIR / name).read_text(encoding="utf-8"))
        for d in data:
            chunks.append(KnowledgeChunk(**d))
    return chunks


def save_relations_native(relations, tenant_id: str, batch_size: int = 200) -> tuple[int, int]:
    """原生 Cypher 写 Neo4j（无 APOC）：按 (src_label, tgt_label, rel_type) 分组，每组一条 UNWIND MERGE。

    标签取值来自 _parse_entity（我们自己的实体约定，封闭集合，无注入风险）。
    返回 (nodes_merged, rels_merged)。
    """
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        connection_timeout=4,
    )
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in relations:
        src_label, src_key, src_props = _parse_entity(r.source_entity, tenant_id)
        tgt_label, tgt_key, tgt_props = _parse_entity(r.target_entity, tenant_id)
        groups[(src_label, tgt_label, r.relation_type)].append(
            {"src_key": src_key, "tgt_key": tgt_key, "props": r.properties or {}}
        )

    _KEY_FIELD = {"CourseSeries": "code", "CourseModule": "code",
                  "KnowledgePoint": "name", "QuestionTag": "name"}
    total_nodes = total_rels = 0
    try:
        with driver.session(database=settings.NEO4J_DATABASE) as session:
            for (src_label, tgt_label, rel_type), rows in groups.items():
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    src_f = _KEY_FIELD[src_label]
                    tgt_f = _KEY_FIELD[tgt_label]
                    cypher = f"""
                    UNWIND $rows AS r
                    MERGE (s:{src_label} {{{src_f}: r.src_key}})
                      SET s.name = r.src_key, s.tenant_id = $tid
                    MERGE (t:{tgt_label} {{{tgt_f}: r.tgt_key}})
                      SET t.name = r.tgt_key, t.tenant_id = $tid
                    MERGE (s)-[rel:{rel_type}]->(t)
                      SET rel += r.props
                    RETURN count(DISTINCT s) + count(DISTINCT t) AS n
                    """
                    res = session.run(cypher, rows=batch, tid=tenant_id)
                    for rec in res:
                        total_rels += len(batch)
                        total_nodes += int(rec["n"])
    finally:
        driver.close()
    return total_nodes, total_rels


def neo4j_counts() -> dict:
    from neo4j import GraphDatabase

    d = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                             connection_timeout=4)
    try:
        with d.session(database=settings.NEO4J_DATABASE) as s:
            return {
                "nodes": s.run("MATCH (n) RETURN count(n) AS c").single()["c"],
                "rels": s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"],
                "by_label": s.run(
                    "MATCH (n) RETURN labels(n)[0] AS l, count(n) AS c ORDER BY c DESC"
                ).data(),
                "by_rel": s.run(
                    "MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS c ORDER BY c DESC"
                ).data(),
            }
    finally:
        d.close()


async def graph_expand_probe() -> dict:
    """用 retriever._graph_expand 真实跑图谱通道：验证 graph_entities 非空 & 无降级。"""
    from app.chat.retriever import _graph_expand

    entities, degrade = await _graph_expand("通用编程 Python 程序设计", enable_graph=True, top_k_keywords=5)
    return {
        "n_entities": len(entities),
        "entities": [
            {"entity_type": e.entity_type, "entity_name": e.entity_name, "n_related": len(e.related)}
            for e in entities[:10]
        ],
        "degraded_reason": degrade,
    }


def main() -> None:
    chunks = load_chunks()
    print(f"[task35] 切片载入 {len(chunks)} 条（course+question）")

    relations = build_graph_relations(chunks, tenant_id="_default")
    print(f"[task35] 抽取关系 {len(relations)} 条")

    nn, nr = save_relations_native(relations, "_default")
    print(f"[task35] 原生写入汇总：nodes_merged={nn} rels_merged={nr}")

    counts = neo4j_counts()
    print("[task35] Neo4j 计数:", json.dumps(counts, ensure_ascii=False))

    probe = asyncio.run(graph_expand_probe())
    print("[task35] retriever._graph_expand:", json.dumps(probe, ensure_ascii=False))

    result = {
        "task": "task35",
        "slices_loaded": len(chunks),
        "relations_extracted": len(relations),
        "native_merged": {"nodes": nn, "rels": nr},
        "neo4j_counts": counts,
        "retriever_graph_expand": probe,
        "acceptance": {
            "entities_ingested": counts["nodes"] > 0,
            "graph_entities_non_empty": probe["n_entities"] > 0,
            "neo4j_no_degradation": probe["degraded_reason"] is None,
        },
        "notes": "Neo4j 无 APOC，故用原生 MERGE 写全标签图谱（CourseSeries/CourseModule/KnowledgePoint/QuestionTag）。",
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[task35] result →", OUT_PATH)
    print("[task35] acceptance:", result["acceptance"])


if __name__ == "__main__":
    main()