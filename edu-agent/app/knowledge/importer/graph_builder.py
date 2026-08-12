# -*- coding: utf-8 -*-
"""
知识图谱构建器（P1 步骤 6）

职责：
  1. build_graph_relations(state) —— 从 chunks 元数据（series_code / module_codes / prerequisites / keywords）
     提取实体 + 关系 → 写入 state.relations
  2. save_relations_to_neo4j(relations, tenant_id) —— 通过 get_neo4j_driver() 写入 Neo4j
  3. graph_build_node(state) —— LangGraph 节点（失败不阻断主流程，记录 warning 即可）

节点/关系约定：
  标签：
    - CourseSeries       (code, name, tenant_id)
    - CourseModule       (code, tenant_id)
    - KnowledgePoint     (name, tenant_id)      来自 keywords / 题目 tags
    - QuestionTag        (name, tenant_id)      来自 question_type / question_bank_code
  关系类型（方向、语义都与后续 P4 推荐 / P9 思维导图保持一致）：
    - (CourseSeries)-[:CONTAINS {stage_no}]->(CourseModule)
    - (CourseModule)-[:CONTAINS]->(KnowledgePoint)
    - (CourseModule)-[:TESTS]->(QuestionTag)
    - (CourseModule)-[:PREREQUISITE]->(CourseModule|KnowledgePoint)  前置关系
    - (KnowledgePoint)-[:RELATED_TO]->(KnowledgePoint)                关键词共现

关键约束（implementation-plan.mdc #660）：
  图谱构建失败不阻塞向量入库主流程 —— try/except 全包裹 + 告警日志 + state.error 不写死。
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from itertools import combinations
from typing import Iterable

from loguru import logger

from app.knowledge.models import GraphRelation, ImportState, KnowledgeChunk


# ============================================================
# 1. 实体 ID 规范化（幂等，避免 Neo4j 同实体重复节点）
# ============================================================
_ID_SAFE = re.compile(r"[^0-9A-Za-z_\-\u4e00-\u9fa5]")


def _eid(prefix: str, raw: str, tenant_id: str) -> str:
    """稳定实体 ID：{tenant_id}:{prefix}:{safe_raw}。"""
    safe = _ID_SAFE.sub("_", (raw or "").strip())[:128] or "null"
    return f"{tenant_id}:{prefix}:{safe}"


# ============================================================
# 2. 从 chunks 抽取 relations（纯 CPU、不连 Neo4j，方便单测）
# ============================================================
def build_graph_relations(chunks: Iterable[KnowledgeChunk], tenant_id: str = "_default") -> list[GraphRelation]:
    """
    从 chunk 元数据抽取关系列表（不做去重，save_relations_to_neo4j 使用 MERGE 天然去重）。
    """
    relations: list[GraphRelation] = []
    # 用于 RELATED_TO 共现统计：(模块/系列) scope -> keywords 集合合并计数
    scope_keywords: dict[str, set[str]] = defaultdict(set)

    for chunk in chunks:
        series_code = chunk.series_code or None
        series_name = chunk.series_name or series_code
        module_codes = list(chunk.module_codes or [])
        prereq = list(chunk.prerequisites or [])
        keywords = list(dict.fromkeys([*(chunk.keywords or []), *(chunk.tags or [])]))  # 去重保序

        # ---- 2.1 CourseSeries -> CourseModule (CONTAINS) ----
        if series_code and module_codes:
            series_eid = _eid("CourseSeries", series_code, tenant_id)
            for idx, m in enumerate(module_codes):
                mod_eid = _eid("CourseModule", m, tenant_id)
                relations.append(GraphRelation(
                    source_entity=series_eid,
                    target_entity=mod_eid,
                    relation_type="CONTAINS",
                    properties={
                        "stage_no": idx + 1,
                        "series_code": series_code,
                        "module_code": m,
                        "series_name": series_name or "",
                    },
                ))

        # ---- 2.2 CourseModule -> KnowledgePoint (CONTAINS) ----
        for mod in module_codes or [series_code or "__global__"]:
            mod_eid = _eid("CourseModule", mod, tenant_id)
            scope = f"{tenant_id}:{mod}"
            for kw in keywords:
                kp_eid = _eid("KnowledgePoint", kw, tenant_id)
                relations.append(GraphRelation(
                    source_entity=mod_eid,
                    target_entity=kp_eid,
                    relation_type="CONTAINS",
                    properties={"keyword": kw, "source_chunk_id": chunk.chunk_id},
                ))
                scope_keywords[scope].add(kw)

        # ---- 2.3 CourseModule -> QuestionTag (TESTS)：题型 / 题库编码 ----
        q_tags = []
        if chunk.question_type:
            q_tags.append(chunk.question_type)
        if chunk.question_bank_code:
            q_tags.append(chunk.question_bank_code)
        if q_tags:
            scope_mod = module_codes[0] if module_codes else (series_code or "__global__")
            mod_eid = _eid("CourseModule", scope_mod, tenant_id)
            for qt in q_tags:
                qt_eid = _eid("QuestionTag", qt, tenant_id)
                relations.append(GraphRelation(
                    source_entity=mod_eid,
                    target_entity=qt_eid,
                    relation_type="TESTS",
                    properties={"tag": qt, "source_chunk_id": chunk.chunk_id},
                ))

        # ---- 2.4 PREREQUISITE：显式 prerequisites 字段 ----
        if prereq:
            scope_mod = module_codes[0] if module_codes else (series_code or "__global__")
            src_eid = _eid("CourseModule", scope_mod, tenant_id)
            for p in prereq:
                # 模糊判定：以 M 开头 / 含 MODULE 关键词 → 模块，否则知识点
                p_norm = p.strip()
                if re.match(r"^[A-Z]{2,4}-L\d-M\d", p_norm, re.I) or "模块" in p_norm:
                    tgt_eid = _eid("CourseModule", p_norm, tenant_id)
                else:
                    tgt_eid = _eid("KnowledgePoint", p_norm, tenant_id)
                relations.append(GraphRelation(
                    source_entity=src_eid,
                    target_entity=tgt_eid,
                    relation_type="PREREQUISITE",
                    properties={"prerequisite": p_norm},
                ))

    # ---- 2.5 KnowledgePoint RELATED_TO：同 scope 下 keywords 两两组合 ----
    for scope, kws in scope_keywords.items():
        if len(kws) < 2:
            continue
        kw_list = sorted(kws)
        for a, b in combinations(kw_list, 2):
            a_eid = _eid("KnowledgePoint", a, tenant_id)
            b_eid = _eid("KnowledgePoint", b, tenant_id)
            relations.append(GraphRelation(
                source_entity=a_eid,
                target_entity=b_eid,
                relation_type="RELATED_TO",
                properties={"scope": scope},
            ))

    return relations


# ============================================================
# 3. 写 Neo4j（MERGE 保证幂等，批量提交）
# ============================================================
_NODE_TYPES = {
    "CourseSeries": ("code", "name"),
    "CourseModule": ("code",),
    "KnowledgePoint": ("name",),
    "QuestionTag": ("name",),
}


def _eid_key(eid: str, tenant_id: str) -> str:
    """从 eid {tenant}:{prefix}:{raw} 提取 raw（实体 key），供 Cypher 使用。

    与 _parse_entity 共用同样的解析逻辑；无法解析时兜底返回整个 eid。
    """
    parts = eid.split(":", 2)
    if len(parts) < 3 or parts[0] != tenant_id:
        return eid
    return parts[2]


def _parse_entity(eid: str, tenant_id: str) -> tuple[str, str, dict]:
    """从 eid {tenant}:{prefix}:{raw} 解析 (label, key_value, extra_props)。"""
    parts = eid.split(":", 2)
    if len(parts) < 3 or parts[0] != tenant_id:
        # 不认识的格式 → 兜底 KnowledgePoint + name=eid
        return "KnowledgePoint", eid, {}
    prefix, raw = parts[1], parts[2]
    label_map = {
        "CourseSeries": "CourseSeries",
        "CourseModule": "CourseModule",
        "KnowledgePoint": "KnowledgePoint",
        "QuestionTag": "QuestionTag",
    }
    label = label_map.get(prefix, "KnowledgePoint")
    key_field = _NODE_TYPES.get(label, ("name",))[0]
    return label, raw, {key_field: raw}


def save_relations_to_neo4j(
    relations: list[GraphRelation],
    tenant_id: str = "_default",
    batch_size: int = 200,
) -> tuple[int, int]:
    """
    MERGE 节点 + MERGE 关系写入 Neo4j。

    返回 (nodes_merged, relations_merged)。
    失败抛异常（调用方捕获，保证不阻断向量入库）。
    """
    if not relations:
        return 0, 0
    try:
        from app.database import get_neo4j_driver  # 延迟 import，避免循环
    except Exception as exc:
        raise RuntimeError(f"Neo4j driver 不可用：{exc}") from exc

    driver = get_neo4j_driver()
    if driver is None:
        raise RuntimeError("Neo4j driver 未初始化（get_neo4j_driver() 返回 None）")

    total_nodes = 0
    total_rels = 0

    # 用 Session 手工事务（官方推荐写法），按 batch_size 切分
    for i in range(0, len(relations), batch_size):
        batch = relations[i : i + batch_size]
        rows = [
            {
                "src": r.source_entity,
                "tgt": r.target_entity,
                "type": r.relation_type,
                "props": r.properties or {},
                # Cypher 的 split() 只接受 2 个参数（不支持 maxsplit），
                # 这里用 Python 的 split(':', 2) 预解析出实体 key，避免语法错误
                "src_key": _eid_key(r.source_entity, tenant_id),
                "tgt_key": _eid_key(r.target_entity, tenant_id),
            }
            for r in batch
        ]
        cypher = """
        UNWIND $rows AS r
        WITH r.src AS src_eid, r.tgt AS tgt_eid, r.type AS rel_type, r.props AS props, r.src_key AS src_key, r.tgt_key AS tgt_key
        // 解析源节点 label + key
        WITH src_eid, tgt_eid, rel_type, props, src_key, tgt_key,
             CASE
               WHEN src_eid STARTS WITH $tenant_prefix + 'CourseSeries:' THEN 'CourseSeries'
               WHEN src_eid STARTS WITH $tenant_prefix + 'CourseModule:' THEN 'CourseModule'
               WHEN src_eid STARTS WITH $tenant_prefix + 'QuestionTag:' THEN 'QuestionTag'
               ELSE 'KnowledgePoint'
             END AS src_label,
             CASE
               WHEN tgt_eid STARTS WITH $tenant_prefix + 'CourseSeries:' THEN 'CourseSeries'
               WHEN tgt_eid STARTS WITH $tenant_prefix + 'CourseModule:' THEN 'CourseModule'
               WHEN tgt_eid STARTS WITH $tenant_prefix + 'QuestionTag:' THEN 'QuestionTag'
               ELSE 'KnowledgePoint'
             END AS tgt_label
        // 用 apoc 做动态 MERGE；若 Neo4j 未装 apoc 则退化到 4 条显式 MERGE
        CALL apoc.merge.node([src_label], coalesce(
          CASE WHEN src_label = 'CourseSeries' THEN {code: src_key}
               WHEN src_label = 'CourseModule' THEN {code: src_key}
               WHEN src_label = 'QuestionTag'  THEN {name: src_key}
               ELSE {name: src_key} END,
          {name: src_key}), {tenant_id: $tenant_id}) YIELD node AS s
        CALL apoc.merge.node([tgt_label], coalesce(
          CASE WHEN tgt_label = 'CourseSeries' THEN {code: tgt_key}
               WHEN tgt_label = 'CourseModule' THEN {code: tgt_key}
               WHEN tgt_label = 'QuestionTag'  THEN {name: tgt_key}
               ELSE {name: tgt_key} END,
          {name: tgt_key}), {tenant_id: $tenant_id}) YIELD node AS t
        CALL apoc.merge.relationship(s, rel_type, {}, props, t, {}) YIELD rel
        RETURN count(DISTINCT s) + count(DISTINCT t) AS n_merged, count(rel) AS r_merged
        """
        # 注意：若 Neo4j 未安装 APOC，上面会报错；为保证失败不中断，这里用 driver.execute_query 包一层
        tenant_prefix = f"{tenant_id}:"

        def _merge_tx(tx):
            """在事务内消费结果，避免 ResultConsumedError。"""
            res = tx.run(cypher, rows=rows, tenant_id=tenant_id, tenant_prefix=tenant_prefix)
            n_nodes, n_rels = 0, 0
            for record in res:
                n_nodes += int(record.get("n_merged", 0))
                n_rels += int(record.get("r_merged", 0))
            return n_nodes, n_rels

        try:
            with driver.session() as session:
                tn, tr = session.execute_write(_merge_tx)
                total_nodes += tn
                total_rels += tr
        except Exception as apoc_exc:
            if "apoc" in str(apoc_exc).lower() or "Procedure" in str(apoc_exc):
                logger.warning(f"Neo4j 未安装 APOC（{apoc_exc}），降级为静态 MERGE（只写 KnowledgePoint/CONTAINS 核心关系）")
                total_nodes += _save_relations_sans_apoc(driver, batch, tenant_id, tenant_prefix)
                total_rels += len(batch)
            else:
                raise

    logger.info(f"Neo4j 图谱写入完成：{total_nodes} 节点 / {total_rels} 关系（tenant={tenant_id}）")
    return total_nodes, total_rels


def _save_relations_sans_apoc(driver, batch: list[GraphRelation], tenant_id: str, tenant_prefix: str) -> int:
    """APOC 不存在时的降级路径：简化版 MERGE（KnowledgePoint + CONTAINS 粗粒度）。"""
    rows = [{"src": r.source_entity, "tgt": r.target_entity, "type": r.relation_type, "props": r.properties or {},
             "src_key": _eid_key(r.source_entity, tenant_id), "tgt_key": _eid_key(r.target_entity, tenant_id)} for r in batch]
    cypher = """
    UNWIND $rows AS r
    WITH r,
         CASE WHEN r.src STARTS WITH $tenant_prefix THEN r.src_key ELSE r.src END AS sk,
         CASE WHEN r.tgt STARTS WITH $tenant_prefix THEN r.tgt_key ELSE r.tgt END AS tk
    MERGE (s:KnowledgePoint {name: sk}) SET s.tenant_id = $tenant_id
    MERGE (t:KnowledgePoint {name: tk}) SET t.tenant_id = $tenant_id
    MERGE (s)-[rel:GRAPH_LINK {type: r.type}]->(t) SET rel += r.props
    RETURN count(DISTINCT s) + count(DISTINCT t) AS n
    """
    with driver.session() as session:
        def _link_tx(tx):
            res = tx.run(cypher, rows=rows, tenant_id=tenant_id, tenant_prefix=tenant_prefix)
            return sum(int(r.get("n", 0)) for r in res)
        return session.execute_write(_link_tx)


# ============================================================
# 4. LangGraph 节点 graph_build_node（失败只告警，永远不写 state.error）
# ============================================================
def graph_build_node(state: ImportState) -> dict:
    """
    LangGraph 节点：
      1) 从 state.chunks 抽取 relations
      2) 追加 state.relations
      3) 尝试写入 Neo4j（失败仅 warning）—— 遵守 #660 约束
    """
    if state.error:
        logger.warning("跳过 graph_build_node（导入已失败）")
        return {}
    if not state.chunks:
        logger.info("graph_build_node：chunks 为空，跳过")
        return {}
    try:
        rels = build_graph_relations(state.chunks, tenant_id=state.tenant_id)
    except Exception as exc:
        logger.warning(f"图谱关系抽取失败（跳过，不影响入库）：{exc.__class__.__name__}: {exc}")
        return {}

    # 追加到 state（供下游调试）
    merged = list(state.relations) + rels
    # 写入 Neo4j（可能失败）
    try:
        save_relations_to_neo4j(rels, tenant_id=state.tenant_id)
    except Exception as exc:
        logger.warning(
            f"Neo4j 图谱写入失败（不影响 Milvus 向量入库）：{exc.__class__.__name__}: {exc}"
        )
    return {"relations": merged}
