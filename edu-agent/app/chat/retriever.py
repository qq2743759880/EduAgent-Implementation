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

import asyncio
import re
import time
import httpx
from dataclasses import dataclass

from loguru import logger

from app.auth import UserRole
from app.chat.schemas import GraphEntity, RetrievedDoc
from app.config import settings
from app.database import get_neo4j_driver
from app.core.db_resilience import DependencyUnavailableError, neo4j_run  # task-P1C Neo4j 断连熔断
from app.knowledge.importer.embedder import (
    build_sparse_vector,
    encode_dense_batch_detailed,  # VEC-LOCK：查询侧与入库侧同一编码器同参数（单一事实源）
    ensure_jieba_ready,
)
from app.knowledge.reranker import Reranker
from app.monitoring import metrics as _metrics

# Milvus loader 的 hybrid_search 在连不上时会抛异常 → 需要 try/except 包一层
from app.knowledge.importer.loader import hybrid_search as _milvus_hybrid_search


# ============================================================
# task-E1 影子模式（AC1）
#   主链路返回完全不变；影子对比仅 fire-and-forget，绝不阻塞/改结果。
#   落库出口可注入（set_shadow_sink）；影子变体可注入（set_shadow_variant，
#   默认用规则重排对主结果重排序，零额外 IO，对比 sidecar 重排 vs 规则重排顺序差异）。
# ============================================================
_SHADOW_SINK = None            # callable(diff:dict) | None
_SHADOW_VARIANT_FN = None      # async fn(query, primary) -> RetrievalBundle | None


def set_shadow_sink(fn) -> None:
    global _SHADOW_SINK
    _SHADOW_SINK = fn


def set_shadow_variant(fn) -> None:
    global _SHADOW_VARIANT_FN
    _SHADOW_VARIANT_FN = fn


def _shadow_sampled(query: str, *, ratio: float) -> bool:
    """按流量比例确定性采样：ratio>=1 全采样；ratio<=0 不采样。"""
    if ratio >= 1.0:
        return True
    if ratio <= 0.0:
        return False
    return (hash(query) % 100) < int(ratio * 100 + 1e-9)


async def _default_shadow_variant(query: str, primary: "RetrievalBundle") -> "RetrievalBundle":
    """默认变体：用规则重排对主链路结果重新排序（零额外 IO），暴露两套重排策略的顺序差异。"""
    variant_docs = _rule_rerank(query, list(primary.docs))
    return RetrievalBundle(
        docs=variant_docs,
        raw_retrieved_count=primary.raw_retrieved_count,
        graph_entities=primary.graph_entities,
        rewrite_query=primary.rewrite_query,
        degraded_reason="shadow_variant_rule_rerank",
    )


async def _run_shadow(query: str, user_id: int, role, primary: "RetrievalBundle") -> None:
    """影子对比执行体：算主/变体 doc 集合差异 + 延迟，落 _SHADOW_SINK。任何异常全吞，不影响主链路。"""
    try:
        fn = _SHADOW_VARIANT_FN or _default_shadow_variant
        t0 = time.perf_counter()
        variant = await fn(query, primary)
        lat_ms = round((time.perf_counter() - t0) * 1000, 2)
        if variant is None:
            return
        p_ids = [d.doc_id for d in primary.docs]
        v_ids = [d.doc_id for d in variant.docs]
        union = len(set(p_ids) | set(v_ids)) or 1
        jac = len(set(p_ids) & set(v_ids)) / union
        top1_same = (p_ids[:1] == v_ids[:1]) if (p_ids or v_ids) else True
        diff = {
            "query": query,
            "user_id": int(user_id),
            "primary_topk": len(p_ids),
            "variant_topk": len(v_ids),
            "jaccard": round(jac, 4),
            "top1_consistent": top1_same,
            "variant_latency_ms": lat_ms,
            "variant": "rule_rerank",
        }
        if _SHADOW_SINK is not None:
            _SHADOW_SINK(diff)
    except Exception as exc:  # noqa: BLE001 - 影子失败绝不影响主链路
        logger.warning(f"[shadow] 影子对比失败（已吞，不影响主链路）：{exc}")


def _maybe_shadow(query, user_id, role, primary) -> None:
    """在主链路 return 前调用：开启且命中采样比例时，fire-and-forget 影子对比。"""
    if not getattr(settings, "SHADOW_MODE_ENABLED", False):
        return
    ratio = float(getattr(settings, "SHADOW_MODE_RATIO", 1.0))
    if not _shadow_sampled(query, ratio=ratio):
        return
    try:
        asyncio.create_task(_run_shadow(query, user_id, role, primary))
    except RuntimeError:
        # 无运行中的事件循环（极端情况）→ 同步跳过，绝不阻塞
        pass



# ============================================================
# W-NEXT-FUSIONBLIND-001（R20-min Crit-2 承接：融合层对 dense 故障失明）
#   Crit-2 实证：本地 BGE 缺失 + DashScope 429 → encode 静默退化 sha256 伪向量，
#   dense 通道空转、稀疏通道补偿 → hit_rate 照常 0.9688，指标不报警（可观测性盲区）。
#   本段只增不改：① channel_health 随 RetrievalBundle 显式外带（新增字段，不改既有字段语义）
#   ② 通道失败 WARN 带通道名+原因 ③ 连续 N 次失败升级 ERROR（RETRIEVER_CHANNEL_FAIL_ERROR_N，默认 3）。
#   不改变任何通道的输入/输出/降级路径（kg_expand 语义禁动，仅只读其 degraded_reason 做标记）。
# ============================================================
_CHANNEL_FAIL_STREAK: dict[str, int] = {}   # 通道名 → 连续失败次数（成功清零；仅 dense 接线）
_CHANNEL_FAIL_ERROR_N_DEFAULT = 3           # 连续失败升级 ERROR 的默认阈值（settings.RETRIEVER_CHANNEL_FAIL_ERROR_N 优先；模块常量供测试注入）


def _channel_fail_threshold() -> int:
    return max(1, int(getattr(settings, "RETRIEVER_CHANNEL_FAIL_ERROR_N", _CHANNEL_FAIL_ERROR_N_DEFAULT)
                      or _CHANNEL_FAIL_ERROR_N_DEFAULT))


def _log_channel_failure(channel: str, reason: str) -> None:
    """通道失败留痕：WARN（通道名+原因）；连续失败达阈值升级 ERROR（Crit-2③）。"""
    _CHANNEL_FAIL_STREAK[channel] = _CHANNEL_FAIL_STREAK.get(channel, 0) + 1
    n = _CHANNEL_FAIL_STREAK[channel]
    thr = _channel_fail_threshold()
    msg = f"[retriever] channel={channel} FAILED（连续 {n} 次/阈值 {thr}）：{reason}"
    if n >= thr:
        logger.error(msg)
    else:
        logger.warning(msg)


def _log_channel_recovery(channel: str) -> None:
    """通道恢复：连续失败计数清零（仅在确有失败残留时打一条 INFO，避免每查一刷）。"""
    if _CHANNEL_FAIL_STREAK.pop(channel, None) is not None:
        logger.info(f"[retriever] channel={channel} 恢复（连续失败计数清零）")


def _dense_health_from_backend(backend: str, query_embed_degrade: str | None) -> tuple[str, str | None]:
    """按编码后端定 dense 通道健康级：ok / idle（空转=异空间伪向量，检索无有效贡献）/ degraded。

    - bge_m3                       → ok（与库内向量空间一致，VEC-LOCK 单一事实源）
    - sha256（两级兜底均失败的伪向量）/ cuda 环境下异空间降级 → idle（Crit-2「空转」形态）
    - 其余（cloud 等）             → degraded（非 BGE-M3 空间，仅 cuda 环境下已有既有 WARN）
    """
    if backend == "bge_m3":
        return "ok", None
    if backend == "sha256" or query_embed_degrade:
        return "idle", (query_embed_degrade or f"backend={backend}（异空间伪向量，dense 无有效贡献）")
    return "degraded", f"backend={backend}（非 BGE-M3 空间）"


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
    # FUSIONBLIND-001：三通道健康度（只增不改）。形如
    # {"dense": {"status": ok|idle|degraded|failed, "reason", "backend"},
    #  "sparse": {"status": ok|failed|skipped, "reason"},
    #  "milvus_hybrid": {"status": ok|empty|failed, "reason"},
    #  "graph"/"kg_expand"/"rerank": {"status": ok|empty|failed|degraded|disabled, "reason"}}
    channel_health: dict | None = None


# ============================================================
# 2. 工具：租户范围 & 权限过滤（复用 KnowledgeRetriever._determine_search_partitions）
# ============================================================
def _search_tenant_ids(user_id: int, role: UserRole) -> list[str] | None:
    """搜索分区语义：
    - admin: None（搜索所有分区）
    - 其他：["_default", course_public, f"user_{user_id}"]
      —— course_public 为 task31 课程公共知识分区（隔离用户上传，GWT③）
    - None（子代理链路 role=None，task-P1L 优化H2 直连检索同路径）：按默认学员角色
      限定租户 —— 不扩大搜索范围（R4 安全红线），修复既有 search_knowledge 工具
      role=None 直达 _milvus_hybrid_search_safe 后 `.value` AttributeError 静默空结果的隐患。
    """
    if role is None:
        role = UserRole.STUDENT
    if role is UserRole.ADMIN or role.value == UserRole.ADMIN.value:
        return None
    from app.knowledge.importer.loader import COURSE_PUBLIC

    return ["_default", COURSE_PUBLIC, f"user_{user_id}"]


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
) -> tuple[list[RetrievedDoc], str | None, dict]:
    """Milvus 两通道：连不上返回空 list + degraded_reason。

    task31：召回 top_k 统一抬到 RETRIEVER_RECALL_TOPK(150)，给后续 rerank 足够候选（GWT② 12→150）；
    filter_expr 排除促销/班次/公告类 content_type，避免课程问答混入推广文案（GWT③）。

    FUSIONBLIND-001：返回第 3 元 channel_health（dense/sparse/milvus_hybrid 通道级状态），
    phase 归因——dense_embed/sparse_embed/milvus_search 各自失败落到对应通道，不再整段失明。
    """
    tenant_ids = _search_tenant_ids(user_id, role)
    # R02-tail profile：Milvus 通道内部分段计时（嵌入 dense/稀疏/远端搜索/装配）
    _t_total = time.perf_counter()
    _t_embed = _t_sparse = _t_search = _t_asm = 0.0
    health: dict = {
        "milvus_hybrid": {"status": "unknown", "reason": None},
        "dense": {"status": "unknown", "reason": None, "backend": None},
        "sparse": {"status": "unknown", "reason": None},
    }
    _phase = "init"
    try:
        ensure_jieba_ready()
        # 稠密（VEC-LOCK：与入库侧同编码器同参数——单一事实源 encode_dense_batch_detailed）
        _phase = "dense_embed"
        _t0 = time.perf_counter()
        embed_res = encode_dense_batch_detailed([query])
        _t_embed = time.perf_counter() - _t0
        dense_vec = [float(x) for x in embed_res.vectors[0]]
        health["dense"]["backend"] = embed_res.backend
        # VEC-LOCK：EMBED_BACKEND=cuda 时查询侧必须落在 BGE-M3 空间；若本次编码降级
        # 到异向量空间（cloud/sha256），显式告警并在 degraded_reason 标注（禁静默混写）
        if (
            embed_res.backend != "bge_m3"
            and str(getattr(settings, "EMBED_BACKEND", "")).lower() == "cuda"
        ):
            logger.warning(
                f"[retriever] 查询编码降级 backend={embed_res.backend}"
                f"（EMBED_BACKEND=cuda 期望 BGE-M3），与库内向量空间可能不一致 → 检索结果降级"
            )
            _query_embed_degrade = f"query_embed_fallback:{embed_res.backend}"
        else:
            _query_embed_degrade = None
        # FUSIONBLIND-001：dense 健康定级（ok/idle/degraded）+ 失败留痕（Crit-2：空转必须显式化）
        _d_status, _d_reason = _dense_health_from_backend(embed_res.backend, _query_embed_degrade)
        health["dense"]["status"] = _d_status
        health["dense"]["reason"] = _d_reason
        if _d_status == "ok":
            _log_channel_recovery("dense")
        else:
            _log_channel_failure("dense", _d_reason or f"backend={embed_res.backend}")
        # 稀疏：build_sparse_vector 返回 {str(term_id): weight}，基于（HyDE 后的）contextual 文本生成
        # —— BM25 双路增益（GWT④：sparse 与入库端同样基于带上下文文本，双路互补召回）
        _phase = "sparse_embed"
        _t0 = time.perf_counter()
        sparse_vec = build_sparse_vector(query)
        _t_sparse = time.perf_counter() - _t0
        health["sparse"]["status"] = "ok" if sparse_vec else "empty"
        if not sparse_vec:
            health["sparse"]["reason"] = "稀疏向量为空（分词无产出）"

        # 召回候选数：优先 150（GWT②）；外部传的 top_k 只是最终展示期望，不应压召回
        recall_k = max(int(top_k), int(getattr(settings, "RETRIEVER_RECALL_TOPK", 150)))
        exclude = getattr(settings, "RETRIEVER_EXCLUDE_CONTENT_TYPES", ()) or ()
        filter_expr = None
        if exclude:
            quoted = ", ".join(f'"{ct}"' for ct in exclude)
            filter_expr = f"content_type not in [{quoted}]"

        # 真实调用（内部已含 RRF 融合 + 可选分区过滤）；timeout 防 Milvus 慢拖死链路（P1-4）
        _phase = "milvus_search"
        _t0 = time.perf_counter()
        raw = _milvus_hybrid_search(
            dense_vec=dense_vec,
            sparse_vec=sparse_vec,
            tenant_ids=tenant_ids,
            top_k=recall_k,
            timeout=getattr(settings, "MILVUS_SEARCH_TIMEOUT", 8.0),
            filter_expr=filter_expr,
        )
        _t_search = time.perf_counter() - _t0
        _t0 = time.perf_counter()
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
        _t_asm = time.perf_counter() - _t0
        # R02-tail profile：Milvus 通道分段（embed=稠密嵌入 sparse=稀疏向量 search=远端混合检索 asm=DTO 装配）
        logger.info(
            "[retrieval-profile] milvus total={:.0f}ms embed(dense)={:.0f}ms sparse={:.0f}ms "
            "search={:.0f}ms asm={:.0f}ms docs={}".format(
                (time.perf_counter() - _t_total) * 1000, _t_embed * 1000, _t_sparse * 1000,
                _t_search * 1000, _t_asm * 1000, len(docs))
        )
        # FUSIONBLIND-001：hybrid 通道整体结果态（0 行=empty；融合后无逐子通道归因，dense 定级以嵌入阶段为准）
        health["milvus_hybrid"]["status"] = "ok" if docs else "empty"
        if not docs:
            health["milvus_hybrid"]["reason"] = "hybrid_search 返回 0 行（索引空/分区过滤/双通道均无召回）"
        # VEC-LOCK：查询编码降级（异向量空间）时在 degraded_reason 显式标注
        return docs, (_query_embed_degrade if _query_embed_degrade else None), health
    except Exception as e:
        reason = f"Milvus 检索跳过（{type(e).__name__}）"
        logger.warning(f"{reason}：{e}")
        # FUSIONBLIND-001：按 phase 归因到通道（dense 嵌入失败 → dense failed + sparse skipped）
        health["milvus_hybrid"]["status"] = "failed"
        health["milvus_hybrid"]["reason"] = f"{_phase}:{type(e).__name__}: {e}"
        if _phase in ("dense_embed", "init"):
            health["dense"]["status"] = "failed"
            health["dense"]["reason"] = f"{_phase}:{type(e).__name__}: {e}"
            health["sparse"]["status"] = "skipped"
            health["sparse"]["reason"] = "dense 嵌入失败，hybrid 通道整体不可用（loader 契约 dense+sparse 成对）"
            _log_channel_failure("dense", health["dense"]["reason"])
        elif _phase == "sparse_embed":
            health["sparse"]["status"] = "failed"
            health["sparse"]["reason"] = f"{type(e).__name__}: {e}"
        # milvus_search/assemble 阶段失败：dense 已按嵌入阶段定级，失败归 milvus_hybrid 通道
        return [], reason, health


def _milvus_fetch_contents(chunk_ids: list[str]) -> dict[str, str]:
    """R-N2 KG-3 graph_expand 通道内容回填：按 chunk_id 批量取 Milvus 正文。

    仅通道开启且图扩展产出新邻居时触发；失败 → 返回空 dict（调用方回退
    kg_bridge previews 兜底正文），绝不抛异常、不拖垮主链。
    """
    if not chunk_ids:
        return {}
    try:
        import json as _json

        from app.knowledge.importer.loader import COLLECTION_NAME, get_milvus_client

        client = get_milvus_client()
        id_list = ", ".join(_json.dumps(str(i)) for i in chunk_ids)
        rows = client.query(
            collection_name=COLLECTION_NAME,
            filter=f"chunk_id in [{id_list}]",
            output_fields=["chunk_id", "content"],
            limit=len(chunk_ids),
        )
        return {str(r.get("chunk_id")): str(r.get("content") or "") for r in rows or []}
    except Exception as exc:  # noqa: BLE001 - 回填失败走 preview 兜底，不影响主链
        logger.warning(f"[kg_expand] Milvus 内容回填失败（回退 preview 兜底）：{type(exc).__name__}: {exc}")
        return {}


# ============================================================
# 5. 通道 3：Neo4j 图谱扩展（连不上返回空）
# ============================================================
async def _graph_expand(
    query: str,
    *,
    enable_graph: bool,
    top_k_keywords: int = 5,
) -> tuple[list[GraphEntity], str | None]:
    """图谱通道：从 query 抽关键词 → 在 Neo4j 里找实体 → 1 跳扩展关系。

    task-P1C：Neo4j 断连经 neo4j_run 熔断保护——连续失败→OPEN→毫秒级快速失败降级，
    不再傻等连接超时（task39 实测 RAG 检索 2.8s→29.4s）。
    """
    if not enable_graph:
        return [], None
    driver = get_neo4j_driver()
    if driver is None:
        return [], "Neo4j 未连接（跳过图谱扩展）"
    try:
        ensure_jieba_ready()
        # task35 修复：build_sparse_vector 返回的 key 是稀疏 term_id（md5 hash 整数串），
        # 不是真实中文词，直接用其作为 Neo4j 关键词永远匹配不到节点名。
        # 这里改为取「jieba 真实分词 + 词频排序」作为关键词。
        from app.knowledge.importer.embedder import (_RE_CHINESE_WORD,
                                                     load_jieba_resources)
        stop_words, _ji = load_jieba_resources()
        kws_counter: dict[str, int] = {}
        if _ji:
            import jieba as _jieba
            for tok in _jieba.cut(query):
                tok = tok.strip().lower()
                if not tok or tok in stop_words:
                    continue
                if not _RE_CHINESE_WORD.match(tok):
                    continue
                kws_counter[tok] = kws_counter.get(tok, 0) + 1
        else:
            for tok in re.split(r"[^\u4e00-\u9fa5A-Za-z0-9_+\-#.]+", query.lower()):
                if tok and tok not in stop_words:
                    kws_counter[tok] = kws_counter.get(tok, 0) + 1
        if not kws_counter:
            return [], None
        keywords = [k for k, _ in sorted(kws_counter.items(), key=lambda kv: kv[1], reverse=True)][:top_k_keywords]
        if not keywords:
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
        type_map = {
            "CourseSeries": "Series", "CourseModule": "Module", "KnowledgePoint": "Keyword",
            "QuestionTag": "QuestionTag", "Series": "Series", "Module": "Module",
            "Prerequisite": "Prerequisite", "Course": "Series", "Chunk": "Keyword",
        }

        def _do() -> list[GraphEntity]:
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
            return list(entities.values())[:12]

        try:
            entities = await neo4j_run("graph_expand", _do)
        except DependencyUnavailableError:
            # 熔断中：毫秒级返回降级（不触达 Neo4j），避免 task39 的 29.4s 阻塞
            return [], "Neo4j 熔断（快速失败降级）"
        return entities, None
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
# task31 6b. BGE-reranker 重排（top-150→rerank top-20→断崖→5）
#   - Reranker 懒加载单例（防多 worker OOM 叠载，薄弱点 W3）；
#   - 打分失败返回 None → 退 _rule_rerank，degraded_reason="reranker_unavailable"（GWT② 质量不劣于现状）。
# ============================================================
def _normalize_rerank_scores(scores: list[float]) -> list[float]:
    """把 reranker 原始分数线性缩放到 0~1（单调保序，供断崖截断用）。"""
    if not scores:
        return scores
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-9:
        return [1.0] * len(scores)
    return [(s - lo) / (hi - lo) for s in scores]


# ============================================================
# 6b-0. R02-tail：sidecar 连接失败熔断（TTFT 检索段优化）
#   profile 实测（8010，2026-09-15）：sidecar 不可达时每次请求的连接尝试固定烧 ~2.05s
#   （4 轮 2051~2092ms），占 start→retrieval ~55%。连接级失败（ConnectError/超时）后
#   在冷却窗内跳过 sidecar 直接进程内直连：分数与 sidecar 同模型同批式等价
#   （rerank_pairs AC1「单对分数逐位相等」），检索语义零变化；冷却到期自动重试自愈。
#   仅 transport 级失败触发熔断——HTTP 非 200 / 分数长度不符说明 sidecar 进程活着，
#   可能瞬时可恢复，保持逐请求重试不熔断。
# ============================================================
_SIDECAR_FAIL_UNTIL: float = 0.0    # epoch 秒：此前跳过 sidecar 尝试（0=未熔断）


def _sidecar_breaker_open() -> bool:
    """熔断是否生效中（冷却窗内）。"""
    if float(getattr(settings, "RERANK_SIDECAR_COOLDOWN_S", 60.0) or 0) <= 0:
        return False
    return time.time() < _SIDECAR_FAIL_UNTIL


def _sidecar_breaker_trip() -> None:
    """连接级失败 → 开启冷却窗。"""
    global _SIDECAR_FAIL_UNTIL
    cooldown = float(getattr(settings, "RERANK_SIDECAR_COOLDOWN_S", 60.0) or 0)
    if cooldown > 0:
        _SIDECAR_FAIL_UNTIL = time.time() + cooldown
        logger.warning(f"[retriever] rerank sidecar 连接失败 → 熔断 {cooldown:.0f}s（冷却窗内直接进程内直连，到期自动重试）")


async def _rerank_via_sidecar(query: str, contents: list[str]) -> list[float] | None:
    """主链路默认走 sidecar（GPU 计算在独立进程，不阻塞主事件循环，AC2）。

    任何异常/超时/非 200/分数长度不符 → 返回 None，由 _rerank_docs 回退进程内直连（AC4）。
    全程不抛异常 → 主链路安全降级。
    R02-tail：连接相位用独立短超时（RERANK_CONNECT_TIMEOUT，默认 1s）——实测对已关闭端口
    的连接尝试固定烧 ~2.05s（Windows 连接耗尽路径），短超时把最坏情况封顶。
    """
    url = getattr(settings, "RERANK_SERVICE_URL", "http://127.0.0.1:8601").rstrip("/") + "/rerank"
    timeout = float(getattr(settings, "RERANK_HTTP_TIMEOUT", 10.0))
    connect_to = float(getattr(settings, "RERANK_CONNECT_TIMEOUT", 1.0) or 0) or timeout
    connect_to = max(0.05, min(connect_to, timeout))
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=connect_to)) as client:
            resp = await client.post(url, json={"query": query, "contents": contents})
    except Exception as exc:  # noqa: BLE001 - 连接/超时等 → 降级
        _sidecar_breaker_trip()
        logger.warning(f"[retriever] rerank sidecar 调用失败（{type(exc).__name__}: {exc}）→ 回退进程内直连")
        return None
    if resp.status_code != 200:
        logger.warning(f"[retriever] rerank sidecar 返回 {resp.status_code} → 回退进程内直连")
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    scores = data.get("scores") if isinstance(data, dict) else None
    if not isinstance(scores, list) or len(scores) != len(contents):
        logger.warning(
            f"[retriever] rerank sidecar 分数长度不符"
            f"（{len(scores) if isinstance(scores, list) else scores} != {len(contents)}）→ 回退进程内直连"
        )
        return None
    return [float(s) for s in scores]


async def _rerank_docs(query: str, docs: list[RetrievedDoc]) -> tuple[list[RetrievedDoc], str | None]:
    """对候选 docs 用 BGE-reranker 打分重排，保留 RETRIEVER_RERANK_TOPK(20)。

    降级链（AC4，全程不 500）：
      sidecar（默认，GPU 在独立进程不阻塞事件循环）→ 进程内直连（degraded="rerank_sidecar_unavailable"）
      → _rule_rerank（degraded="reranker_unavailable"）。
    RERANK_SIDECAR_ENABLED=False 时直接进程内直连（平滑切换/降级调试）。
    R02-tail：sidecar 连接失败冷却窗内跳过 HTTP 尝试直接进程内直连（分数等价，AC1）；
    进程内 rerank 是同步 GPU 前向（实测 ~0.9-1.0s/150 对），移入线程池避免阻塞事件循环。
    """
    rerank_k = int(getattr(settings, "RETRIEVER_RERANK_TOPK", 20))
    if not docs:
        return docs, None
    _t0 = time.perf_counter()
    contents = [d.content or "" for d in docs]
    scores: list[float] | None = None
    degrade: str | None = None
    if getattr(settings, "RERANK_SIDECAR_ENABLED", True):
        if _sidecar_breaker_open():
            # R02-tail：熔断冷却窗内跳过 sidecar（连接尝试实测固定 ~2s 纯烧）→ 直接进程内直连。
            # 与「sidecar 尝试失败后回退」同一降级语义：本地成功仍标 rerank_sidecar_unavailable。
            logger.info("[retriever] rerank sidecar 熔断冷却中 → 直接进程内直连")
            _t1 = time.perf_counter()
            rk = Reranker.get()
            scores = await asyncio.to_thread(rk.rerank, query, contents)
            logger.info("[retrieval-profile] rerank local (breaker-skip)={:.0f}ms pairs={}".format(
                (time.perf_counter() - _t1) * 1000, len(contents)))
            if scores is not None:
                degrade = "rerank_sidecar_unavailable"
        else:
            _tsc = time.perf_counter()
            scores = await _rerank_via_sidecar(query, contents)
            logger.info("[retrieval-profile] rerank sidecar attempt={:.0f}ms ok={}".format(
                (time.perf_counter() - _tsc) * 1000, scores is not None))
            if scores is None:  # sidecar 不可达/失败 → 回退进程内直连（task31 现状路径）
                logger.warning("[retriever] rerank sidecar 不可达 → 回退进程内直连")
                _t1 = time.perf_counter()
                rk = Reranker.get()
                scores = await asyncio.to_thread(rk.rerank, query, contents)
                _local_ms = (time.perf_counter() - _t1) * 1000
                # R02-tail profile：sidecar 失败回退时的进程内 rerank 耗时
                logger.info("[retrieval-profile] rerank local fallback={:.0f}ms pairs={} sidecar_fail=yes".format(
                    _local_ms, len(contents)))
                if scores is not None:
                    degrade = "rerank_sidecar_unavailable"
    else:
        _t1 = time.perf_counter()
        rk = Reranker.get()
        scores = await asyncio.to_thread(rk.rerank, query, contents)
        logger.info("[retrieval-profile] rerank local={:.0f}ms pairs={} sidecar=disabled".format(
            (time.perf_counter() - _t1) * 1000, len(contents)))

    if scores is None:  # 直连也失败 → 规则兜底，明确标注降级
        logger.warning(f"[retriever] reranker 不可用 → 规则重排兜底")
        return _rule_rerank(query, docs), "reranker_unavailable"
    if len(scores) != len(docs):
        scores = scores[: len(docs)] or [0.0] * len(docs)
    norm = _normalize_rerank_scores(scores)
    for d, s in zip(docs, norm):
        d.score = round(max(0.0, min(1.0, s)), 6)
    docs.sort(key=lambda d: d.score, reverse=True)  # 按 rerank 分数排序
    return docs[:rerank_k], degrade


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
    # R02-tail profile：主链路分段计时（hyde / milvus / graph / merge / rerank / cliff）
    _prof_t0 = time.perf_counter()
    # 1) HyDE 查询改写
    rewrite_query, hyde_done, hyde_degrade = _rewrite_query_by_hyde_if_enabled(query, use_hyde=use_hyde)
    _prof_hyde = time.perf_counter() - _prof_t0
    # 2) Milvus 双通道（dense + sparse）→ 混合
    #    P1-4 修复：同步 Milvus 调用跑线程 + 硬超时，避免阻塞 asyncio 事件循环
    #    （否则 Milvus 慢时所有并发请求全部排队；超时则降级返回空 docs）
    #    R02-tail：图谱通道与 Milvus 通道并行化——两者都只依赖 rewrite_query、产物独立
    #    （docs / graph_entities 分开装配），串行纯叠延迟（profile 实测 graph 212ms+ 全额在
    #    关键路径上）。并行不改任何通道的输入/输出 → 检索语义零变化；降级原因仍按
    #    milvus→graph 固定顺序汇总（下方 degrade_parts 组装顺序不变）。
    _milvus_timeout = float(getattr(settings, "MILVUS_SEARCH_TIMEOUT", 8.0))
    _prof_t1 = time.perf_counter()
    milvus_task = asyncio.ensure_future(asyncio.to_thread(
        _milvus_hybrid_search_safe,
        rewrite_query,
        user_id=user_id,
        role=role,
        top_k=top_k,
    ))
    graph_task = asyncio.ensure_future(_graph_expand(rewrite_query, enable_graph=enable_graph))
    try:
        _milvus_res = await asyncio.wait_for(milvus_task, timeout=_milvus_timeout)
    except asyncio.TimeoutError:
        logger.warning(f"Milvus 检索超时（>{_milvus_timeout}s），降级返回空 docs")
        milvus_docs, milvus_degrade = [], f"Milvus 检索超时({_milvus_timeout}s)"
        # FUSIONBLIND-001：超时=通道级失败（dense 硬失败计入连续失败升级；sparse 阶段未知不妄断）
        milvus_health = {
            "milvus_hybrid": {"status": "failed", "reason": f"timeout(>{_milvus_timeout}s)"},
            "dense": {"status": "failed", "reason": f"milvus_hybrid 超时(>{_milvus_timeout}s)", "backend": None},
            "sparse": {"status": "unknown", "reason": f"milvus_hybrid 超时(>{_milvus_timeout}s)，失败阶段未知"},
        }
        _log_channel_failure("dense", f"milvus_hybrid timeout(>{_milvus_timeout}s)")
    else:
        # FUSIONBLIND-001：兼容旧 2 元组桩（既有测试/外部注入方）——健康度按降级字段保守推导
        if isinstance(_milvus_res, tuple) and len(_milvus_res) == 3:
            milvus_docs, milvus_degrade, milvus_health = _milvus_res
        else:
            milvus_docs, milvus_degrade = _milvus_res
            milvus_health = {
                "milvus_hybrid": {"status": "failed" if milvus_degrade else ("empty" if not milvus_docs else "ok"),
                                  "reason": milvus_degrade},
                "dense": {"status": "failed" if milvus_degrade else "ok", "reason": milvus_degrade, "backend": None},
                "sparse": {"status": "failed" if milvus_degrade else "ok", "reason": None},
            }
    _prof_milvus = time.perf_counter() - _prof_t1
    # 3) 图谱扩展（已与 Milvus 并行启动，此处仅收口；_graph_expand 内部全吞异常，恒返回元组）
    graph_entities, graph_degrade = await graph_task
    _prof_graph = time.perf_counter() - _prof_t1 - _prof_milvus

    # 4) 融合去重（Milvus 去重即可，BM25 后续接入 MySQL 倒排再合并）
    _prof_t3 = time.perf_counter()
    seen: set[str] = set()
    merged: list[RetrievedDoc] = []
    for d in milvus_docs:
        if not d.doc_id or d.doc_id in seen:
            continue
        seen.add(d.doc_id)
        merged.append(d)

    # 4b) R-N2 KG-3 第四通道 graph_expand（灰度开关 KG_EXPAND_ENABLED，默认 False → 结构性零开销）
    #     种子=融合候选前 KG_EXPAND_SEED_TOPK → kg_bridge 查 Neo4j 邻居 chunk（只读，
    #     MENTIONS/章节实体 → RELATED|PREREQUISITE 2-hop → 反向 MENTIONS DocChunk）→
    #     RRF（与 RRFRanker k=60 同范式，通道权重配置化）并入候选池，与既有候选一起
    #     rerank 公平竞争。任何断连/熔断/超时 → 通道静默跳过（WARN 留痕），
    #     主链结果与开关关闭时逐位一致（对账零分歧的结构保证）。
    kg_degrade: str | None = None
    _prof_kg = 0.0
    kg_merged = 0  # FUSIONBLIND-001：只读产出计数（channel_health 标记用，不参与检索语义）
    if getattr(settings, "KG_EXPAND_ENABLED", False) and merged:
        from app.ai import kg_bridge

        _prof_t2 = time.perf_counter()
        seed_ids = [d.doc_id for d in merged[: int(getattr(settings, "KG_EXPAND_SEED_TOPK", 10))]]
        kg_res = await kg_bridge.fetch_neighbor_chunks(
            seed_ids,
            hops=int(getattr(settings, "KG_EXPAND_HOPS", 2)),
            timeout_s=float(getattr(settings, "KG_EXPAND_TIMEOUT_MS", 800)) / 1000.0,
            max_neighbors=int(getattr(settings, "KG_EXPAND_MAX_NEIGHBORS", 30)),
        )
        _prof_kg = time.perf_counter() - _prof_t2
        if kg_res.degraded_reason:
            kg_degrade = kg_res.degraded_reason
            logger.warning(f"[kg_expand] 图谱扩展通道降级跳过：{kg_degrade}")
        if kg_res.neighbors:
            fresh_ids = [cid for cid, _h in kg_res.neighbors if cid and cid not in seen]
            _contents = _milvus_fetch_contents(fresh_ids) if fresh_ids else {}
            weight = float(getattr(settings, "KG_EXPAND_RRF_WEIGHT", 0.5))
            rrf_k = int(getattr(settings, "KG_EXPAND_RRF_K", 60))
            rank = 0
            for cid, _hops in kg_res.neighbors:
                if not cid or cid in seen:
                    continue  # 已在候选中的邻居不重复并入、不改动原分（off==on 语义保真）
                seen.add(cid)
                rank += 1
                raw_rrf = kg_bridge.rrf_channel_score(rank, weight=weight, k=rrf_k)
                merged.append(RetrievedDoc(
                    doc_id=cid,
                    # 与 Milvus 通道同款 0~1 归一（(x+1)/2）：RRF 量纲对齐，rerank 前分数可比
                    score=max(0.0, min(1.0, (raw_rrf + 1.0) / 2.0)),
                    content=_contents.get(cid) or kg_res.previews.get(cid, ""),
                    source_channel="graph",  # 契约 Literal 冻结：通道3=实体渲染、通道4=chunk 扩展共用 graph 溯源
                ))
            if rank:
                kg_merged = rank  # FUSIONBLIND-001：只读计数
                logger.info(
                    f"[kg_expand] 图谱扩展并入 {rank} 个邻居 chunk（种子 {len(seed_ids)}，"
                    f"耗时 {_prof_kg * 1000:.0f}ms）"
                )

    raw_retrieved_count = len(merged)
    _prof_merge = time.perf_counter() - _prof_t3

    # 5) 重排（task31 + task-R1）：默认经 sidecar HTTP 重排（GPU 在独立进程不阻塞事件循环），
    #    sidecar 不可达→进程内直连→规则兜底（degraded_reason 标注）
    _prof_t4 = time.perf_counter()
    merged, rerank_degrade = await _rerank_docs(rewrite_query, merged)
    _prof_rerank = time.perf_counter() - _prof_t4

    # 6) 断崖 + final_max_k 上限
    final_docs = _cliff_cutoff(merged, final_max_k=final_max_k, drop_ratio=cutoff_drop_ratio)
    _prof_cliff = time.perf_counter() - _prof_t4 - _prof_rerank

    # FUSIONBLIND-001：三通道健康度汇总（只增不改——degraded_reason 组装逻辑与内容原样保留）。
    # 先于 pipeline profile 日志组装，使每次检索的通道健康态随 profile 行留痕（可观测）。
    _rerank_status = (
        "empty" if raw_retrieved_count == 0
        else "ok" if rerank_degrade is None
        else "failed" if rerank_degrade == "reranker_unavailable"
        else "degraded"
    )
    channel_health: dict = dict(milvus_health or {})
    channel_health.setdefault("dense", {"status": "unknown", "reason": None, "backend": None})
    channel_health.setdefault("sparse", {"status": "unknown", "reason": None})
    channel_health.setdefault("milvus_hybrid", {"status": "unknown", "reason": milvus_degrade})
    channel_health["graph"] = {
        "status": (
            "disabled" if not enable_graph
            else "failed" if graph_degrade
            else "ok" if graph_entities else "empty"
        ),
        "reason": graph_degrade,
    }
    channel_health["kg_expand"] = {
        "status": (
            "disabled" if not getattr(settings, "KG_EXPAND_ENABLED", False)
            else "failed" if kg_degrade
            else "ok" if kg_merged else "empty"
        ),
        "reason": kg_degrade,
    }
    channel_health["rerank"] = {"status": _rerank_status, "reason": rerank_degrade}

    # R02-tail profile：三通道主链路分段汇总（一次检索一行；kg_expand=R-N2 第四通道段；
    # FUSIONBLIND-001 追加 health 段——通道健康态随 profile 行留痕，dense 空转/失败不再静默）
    logger.info(
        "[retrieval-profile] pipeline total={:.0f}ms | hyde={:.0f} milvus={:.0f} graph={:.0f} "
        "kg_expand={:.0f} merge={:.0f} rerank={:.0f} cliff={:.0f} | raw={} final={} | "
        "health dense={} sparse={} graph={} kg={} rerank={}".format(
            (time.perf_counter() - _prof_t0) * 1000,
            _prof_hyde * 1000, _prof_milvus * 1000, _prof_graph * 1000,
            _prof_kg * 1000, _prof_merge * 1000, _prof_rerank * 1000, max(0.0, _prof_cliff) * 1000,
            raw_retrieved_count, len(final_docs),
            channel_health["dense"]["status"], channel_health["sparse"]["status"],
            channel_health["graph"]["status"], channel_health["kg_expand"]["status"],
            channel_health["rerank"]["status"])
    )

    # 7) 汇总降级原因 + task39 GWT② 逐组件指标埋点
    #    组件归属按「变量出处」判定（非字符串匹配）：
    #      hyde  → llm（HyDE 改写走 LLM）  milvus → milvus
    #      graph → neo4j                  rerank → reranker
    #      kg_expand → neo4j 图扩展第四通道（R-N2，仅开关开启且降级时非空）
    degrade_parts: list[str] = []
    for _comp, _p in (
        ("llm", hyde_degrade),
        ("milvus", milvus_degrade),
        ("neo4j", graph_degrade),
        ("kg_expand", kg_degrade),
        ("reranker", rerank_degrade),
    ):
        if _p:
            degrade_parts.append(_p)
            _metrics.record_degraded(_comp, _p)
        else:
            _metrics.clear_degraded(_comp)
    degraded_reason = "；".join(degrade_parts) if degrade_parts else None

    _bundle = RetrievalBundle(
        docs=final_docs,
        raw_retrieved_count=raw_retrieved_count,
        graph_entities=graph_entities,
        rewrite_query=rewrite_query if hyde_done else None,
        degraded_reason=degraded_reason,
        channel_health=channel_health,
    )
    # task-E1 影子模式（AC1）：主路径返回完全不变；影子对比仅 fire-and-forget，绝不阻塞/改结果
    _maybe_shadow(query, user_id, role, _bundle)
    return _bundle
