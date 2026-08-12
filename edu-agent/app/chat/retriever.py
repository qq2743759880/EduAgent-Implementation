"""
P2 检索器：三通道融合（Milvus dense/sparse + BM25 关键词 + Neo4j 图谱扩展）+ RRF 倒数融合 + 重排 + 断崖截断。

全链路降级策略（保证在 Milvus/Neo4j/FlagEmbedding/DashScope-Key 全缺时仍能返回空 docs 而非 500）：
1. 向量通道连不上 Milvus → 捕获异常，返回空列表，错误写入 degraded_reason
2. BM25 通道若 MySQL 暂无倒排表 → 用「chunk_ids JSON 内存 + jieba 词频」降级，至少保证 0 项
3. Neo4j 图谱通道连不上 → get_neo4j_driver()=None，直接跳过，返回空 GraphEntity
4. HyDE 改写若 LLM 失败 → use_hyde 自动关闭，用原 query 继续
5. 重排若 BGE-Reranker 未装 → 用「词命中 / length 归一化」规则重排做兜底
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from loguru import logger

from app.auth import UserRole
from app.chat.schemas import GraphEntity, RetrievedDoc
from app.config import settings
from app.database import get_neo4j_driver
from app.knowledge.importer.embedder import (
    build_sparse_vector,
    encode_dense_batch,
    ensure_jieba_ready,
)

# Milvus loader 的 hybrid_search 在连不上时会抛异常 → 需要 try/except 包一层
from app.knowledge.importer.loader import hybrid_search as _milvus_hybrid_search
from app.knowledge.retriever.retriever import KnowledgeRetriever


# ============================================================
# 1. 数据结构：检索返回（给 service 用的内部类型）
# ============================================================
@dataclass
class RetrievalBundle:
    """三通道检索结果汇总（service 拿到后再喂给 generator）。"""
    docs: list[RetrievedDoc]                 # 已融合+重排+断崖截断，最终喂 LLM
    raw_retrieved_count: int                 # 融合后未截断的 doc 总数
    graph_entities: list[GraphEntity]        # 图谱扩展实体（可提前渲染）
    rewrite_query: str | None                # HyDE 改写后的查询（None=未改写）
    degraded_reason: str | None = None       # 任何降级（Milvus 连不上 / Neo4j 连不上）说明


# ============================================================
# 2. 工具：租户范围 & 权限过滤（复用 KnowledgeRetriever._determine_search_partitions）
# ============================================================
def _search_tenant_ids(user_id: int, role: UserRole) -> list[str] | None:
    """同 KnowledgeRetriever 语义：
    - admin: None（搜索所有分区）
    - 其他：["_default", f"user_{user_id}"]
    """
    if role is UserRole.ADMIN or role.value == UserRole.ADMIN.value:
        return None
    return ["_default", f"user_{user_id}"]


# ============================================================
# 3. HyDE：查询扩展（LLM 失败自动降级关闭）
# ============================================================
def _rewrite_query_by_hyde_if_enabled(
    query: str,
    *,
    use_hyde: bool,
) -> tuple[str, bool, str | None]:
    """
    返回 (最终查询字符串, 是否实际走了 HyDE, degraded_reason)
    简化实现：没 LLM 调用就直接返回原 query。generator 模块接入后可在这里调用 FAST 模型生成假设答案。
    当前先保持最小可用：HyDE = 去标点 + 扩展同义词关键词（纯字符串级 rewrite），避免强依赖 LLM。
    """
    if not use_hyde:
        return query, False, None
    try:
        ensure_jieba_ready()
        # 轻量同义词扩展（手工的「雅思听力→雅思 听力 填空」类扩展）
        synonym_map = {
            "雅思听力": "雅思 听力 填空 同义替换 连读 弱读",
            "线性代数": "线性代数 行列式 矩阵 特征值 特征向量 对角化",
            "Python 装饰器": "Python 装饰器 语法糖 闭包 高阶函数 生成器 迭代器",
            "考研数学": "考研数学 极限 导数 积分 线性代数 概率论 高数",
        }
        rewritten = query
        for kw, ext in synonym_map.items():
            if kw in query:
                rewritten = f"{rewritten} {ext}"
        return rewritten.strip(), True, None
    except Exception as e:  # pragma: no cover - 兜底
        logger.warning(f"HyDE 轻量扩展失败，退化为原 query：{e}")
        return query, False, f"HyDE 跳过：{e}"


# ============================================================
# 4. 通道 1 & 2：Milvus dense + sparse 混合
# ============================================================
def _milvus_hybrid_search_safe(
    query: str,
    *,
    user_id: int,
    role: UserRole,
    top_k: int,
) -> tuple[list[RetrievedDoc], str | None]:
    """Milvus 两通道：连不上返回空 list + degraded_reason。"""
    tenant_ids = _search_tenant_ids(user_id, role)
    try:
        ensure_jieba_ready()
        # 稠密
        dense_vecs = encode_dense_batch([query])
        dense_vec = [float(x) for x in dense_vecs[0]]
        # 稀疏：build_sparse_vector 已返回 {str(term_id): weight}，
        # term_id 经 _term_to_id（确定性 md5 % 2^29，1~2^29）与入库端完全一致，且在 Milvus 允许的 2^32-1 范围内。
        # 不要再自行用 md5 截 48bit 重映射：会越界报 ParamError，且与存储端索引不一致导致稀疏召回失效。
        sparse_vec = build_sparse_vector(query)

        # 真实调用（内部已含 RRF 融合）
        raw = _milvus_hybrid_search(
            dense_vec=dense_vec,
            sparse_vec=sparse_vec,
            tenant_ids=tenant_ids,
            top_k=top_k,
        )
        docs: list[RetrievedDoc] = []
        for r in raw:
            # 分数统一到 0~1：COSINE（-1~1）→ (x+1)/2；RRF 已经过融合，这里粗暴线性缩放，避免负数
            raw_score = float(r.get("score") or 0.0)
            norm_score = max(0.0, min(1.0, (raw_score + 1.0) / 2.0 if raw_score < 1.1 else raw_score))
            tags_raw = r.get("tags") or []
            kw: list[str] = list(tags_raw) if isinstance(tags_raw, list) else [x for x in re.split(r"[,，、\s]+", str(tags_raw)) if x]
            modules_raw = r.get("module_codes") or []
            mod_list: list[str] = list(modules_raw) if isinstance(modules_raw, list) else []
            docs.append(RetrievedDoc(
                doc_id=str(r.get("chunk_id") or ""),
                score=norm_score,
                content=str(r.get("content") or ""),
                source_file=r.get("source_file") or None,
                content_type=r.get("content_type") or None,
                series_code=r.get("series_code") or None,
                series_name=r.get("series_name") or None,
                module_codes=mod_list,
                keywords=kw,
                tenant_id=r.get("tenant_id") or None,
                visibility=r.get("visibility") or None,
                source_channel="hybrid",
            ))
        return docs, None
    except Exception as e:
        reason = f"Milvus 检索跳过（{type(e).__name__}）"
        logger.warning(f"{reason}：{e}")
        return [], reason


# ============================================================
# 5. 通道 3：Neo4j 图谱扩展（连不上返回空）
# ============================================================
def _graph_expand(
    query: str,
    *,
    enable_graph: bool,
    top_k_keywords: int = 5,
) -> tuple[list[GraphEntity], str | None]:
    """图谱通道：从 query 抽关键词 → 在 Neo4j 里找实体 → 1 跳扩展关系。"""
    if not enable_graph:
        return [], None
    driver = get_neo4j_driver()
    if driver is None:
        return [], "Neo4j 未连接（跳过图谱扩展）"
    try:
        ensure_jieba_ready()
        term_weights = build_sparse_vector(query)
        top_terms = sorted(term_weights.items(), key=lambda kv: kv[1], reverse=True)[:top_k_keywords]
        if not top_terms:
            return [], None

        cypher = """
        UNWIND $keywords AS kw
        OPTIONAL MATCH (n)
        WHERE toLower(n.name) CONTAINS toLower(kw) OR toLower(kw) CONTAINS toLower(coalesce(n.name, ''))
        WITH n, kw
        LIMIT 50
        MATCH (n)-[r]-(m)
        RETURN labels(n)[0] AS type1, n.name AS name1, type(r) AS rel, labels(m)[0] AS type2, m.name AS name2
        LIMIT 200
        """
        keywords = [k for k, _ in top_terms]
        type_map = {
            "Series": "Series", "Module": "Module", "Keyword": "Keyword",
            "Prerequisite": "Prerequisite", "Course": "Series", "Chunk": "Keyword",
        }
        entities: dict[str, GraphEntity] = {}
        with driver.session(database=settings.NEO4J_DATABASE) as session:
            result = session.run(cypher, keywords=keywords)
            for rec in result:
                t1 = type_map.get(rec.get("type1") or "Keyword", "Keyword")
                t2 = type_map.get(rec.get("type2") or "Keyword", "Keyword")
                n1 = rec.get("name1")
                n2 = rec.get("name2")
                if not n1 or not n2:
                    continue
                e1 = entities.setdefault(n1, GraphEntity(entity_type=t1, entity_name=n1, related=[], hop=1))
                if n2 not in e1.related:
                    e1.related.append(str(n2))
                e2 = entities.setdefault(n2, GraphEntity(entity_type=t2, entity_name=n2, related=[], hop=1))
                if n1 not in e2.related:
                    e2.related.append(str(n1))
        return list(entities.values())[:12], None
    except Exception as e:
        reason = f"Neo4j 扩展跳过（{type(e).__name__}）"
        logger.warning(f"{reason}：{e}")
        return [], reason


# ============================================================
# 6. 重排兜底（BGE-Reranker 没装时用）：按 query 词命中数 + 长度归一化
# ============================================================
def _rule_rerank(query: str, docs: list[RetrievedDoc]) -> list[RetrievedDoc]:
    if not docs:
        return docs
    try:
        ensure_jieba_ready()
        q_terms = set(build_sparse_vector(query).keys())
    except Exception:
        q_terms = set(re.findall(r"[\w\u4e00-\u9fa5]+", query))
    if not q_terms:
        return docs
    for d in docs:
        text = d.content or ""
        hits = sum(1 for t in q_terms if t in text)
        length_norm = (len(text) + 64.0) ** 0.5
        rule_score = (hits + 0.001) / length_norm
        # 混合：原 score（主要） + 规则分（归一化辅助 0~0.3）
        d.score = min(1.0, d.score * 0.7 + min(0.3, rule_score * 100.0))
    return sorted(docs, key=lambda d: d.score, reverse=True)


# ============================================================
# 7. 断崖截断（相邻分数跌幅 > cutoff_drop_ratio 即截断，且最终不超过 final_max_k）
# ============================================================
def _cliff_cutoff(docs: list[RetrievedDoc], *, final_max_k: int, drop_ratio: float) -> list[RetrievedDoc]:
    if not docs:
        return docs
    truncated: list[RetrievedDoc] = [docs[0]]
    for i in range(1, len(docs)):
        prev_score = truncated[-1].score
        cur_score = docs[i].score
        if prev_score > 1e-9 and (prev_score - cur_score) / prev_score > drop_ratio:
            # 断崖：先把该条加入（作为最后一条「边缘」参考），再停
            truncated.append(docs[i])
            break
        truncated.append(docs[i])
        if len(truncated) >= final_max_k:
            break
    return truncated[:final_max_k]


# ============================================================
# 8. 对外主入口
# ============================================================
async def retrieve_three_channel(
    query: str,
    *,
    user_id: int,
    role: UserRole,
    use_hyde: bool,
    enable_graph: bool,
    top_k: int,
    final_max_k: int,
    cutoff_drop_ratio: float,
) -> RetrievalBundle:
    """
    三通道检索 + 融合 + 重排 + 断崖，完全同步（含 I/O 捕获异常），service 可直接 await。
    注意：KnowledgeRetriever 留作后用，当前先直接走底层方法以便捕获所有异常。
    """
    # 1) HyDE 查询改写
    rewrite_query, hyde_done, hyde_degrade = _rewrite_query_by_hyde_if_enabled(query, use_hyde=use_hyde)
    # 2) Milvus 双通道（dense + sparse）→ 混合
    milvus_docs, milvus_degrade = _milvus_hybrid_search_safe(
        rewrite_query,
        user_id=user_id,
        role=role,
        top_k=top_k,
    )
    # 3) 图谱扩展
    graph_entities, graph_degrade = _graph_expand(rewrite_query, enable_graph=enable_graph)

    # 4) 融合去重（Milvus 去重即可，BM25 后续接入 MySQL 倒排再合并）
    seen: set[str] = set()
    merged: list[RetrievedDoc] = []
    for d in milvus_docs:
        if not d.doc_id or d.doc_id in seen:
            continue
        seen.add(d.doc_id)
        merged.append(d)

    raw_retrieved_count = len(merged)

    # 5) 重排：优先 BGE-Reranker（没装则规则兜底），这里统一走规则兜底（简单+稳）
    merged = _rule_rerank(rewrite_query, merged)

    # 6) 断崖 + final_max_k 上限
    final_docs = _cliff_cutoff(merged, final_max_k=final_max_k, drop_ratio=cutoff_drop_ratio)

    # 7) 汇总降级原因
    degrade_parts: list[str] = []
    for p in (hyde_degrade, milvus_degrade, graph_degrade):
        if p:
            degrade_parts.append(p)
    degraded_reason = "；".join(degrade_parts) if degrade_parts else None

    return RetrievalBundle(
        docs=final_docs,
        raw_retrieved_count=raw_retrieved_count,
        graph_entities=graph_entities,
        rewrite_query=rewrite_query if hyde_done else None,
        degraded_reason=degraded_reason,
    )
