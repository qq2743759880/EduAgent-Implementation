# -*- coding: utf-8 -*-
"""R-N2 KG-3 GraphRAG 第四通道 graph_expand —— Neo4j 查询桥（只读，app/ai 侧唯一 Neo4j 触点）。

职责（派单 R-N2 文件域：本文件 = Neo4j 查询封装，禁改 app/domains/kg/**）：
  融合候选 top-k chunk（Milvus doc_id）→ 在 Neo4j kg_sync 子图找其 MENTIONS 的
  KnowledgePoint 实体 + 所属章节（BELONGS_TO→Chapter）MENTIONS 的实体 → 实体图上
  RELATED/PREREQUISITE 1..H 跳（默认 2）邻居实体 → 反向 MENTIONS 回 DocChunk 邻居 chunk。

红线对齐：
- 只读：全部纯 MATCH，禁写（Neo4j 写仅限 scripts/kg_sync.py，对齐 R-N1 红线）。
- 作用域：全部按 source='kg_sync' 过滤（R-N1 建模范式）——天然免疫 P1 遗留数据污染。
- 降级（对齐 50301 范式但检索路径用降级跳过而非报错）：driver 未连接 / 熔断 OPEN /
  超时（默认 800ms 预算）/ 任何异常 → 恒返回 KGBridgeResult([], degraded_reason)，
  通道静默跳过 WARN，绝不拖垮检索主链（复用 task-P1C neo4j_run 熔断）。
- 契约零变更：不新增端点，仅经 settings.KG_EXPAND_* 灰度开关生效（默认 False）。

RRF 范式（对齐既有通道）：与 app/knowledge/importer/loader.py hybrid_search 的
RRFRanker(k=60) 同式——raw = weight / (k + rank)；再按 retriever Milvus 通道同款
(raw+1)/2 归一到 0~1。通道权重 weight 经 KG_EXPAND_RRF_WEIGHT 配置化。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from loguru import logger

from app.config import settings

KG_SOURCE = "kg_sync"  # 与 app/domains/kg/sync_core.KG_SOURCE 同值（import 会拖 MySQL 依赖，此处按值对齐）


@dataclass
class KGBridgeResult:
    """图谱扩展结果：neighbors=(chunk_id, hops) 按 (hops, chunk_id) 确定性升序。

    degraded_reason 非 None 表示通道降级（邻居列表恒为空）——主链路应 WARN 跳过。
    previews：DocChunk.preview（kg_sync 同步入库的 content[:120]）→ Milvus 内容
    回填失败时的兜底正文（120 字符，重排可给出弱信号；留痕为降级事实）。
    """

    neighbors: list[tuple[str, int]] = field(default_factory=list)
    previews: dict[str, str] = field(default_factory=dict)
    degraded_reason: str | None = None


def rrf_channel_score(rank: int, *, weight: float = 0.5, k: int = 60) -> float:
    """通道内 RRF 分（未归一）：与 RRFRanker(k=60) 同式 1/(k+rank)，通道权重为乘子。

    rank 从 1 起（RRF 惯例：rank=1 是通道内第一名）。调用方负责 (x+1)/2 归一。
    """
    if rank < 1:
        rank = 1
    return weight / (float(k) + float(rank))


# ══════════════════════════════════════════════════════════════
# Cypher（纯 MATCH 只读；跳数/上限为 int 字面量插值——来源 settings int 配置）
# ══════════════════════════════════════════════════════════════
# ① 种子实体面：chunk 直接 MENTIONS 的 KP ∪ chunk 所属 Chapter MENTIONS 的 KP
_SEED_ENTITY_CYPHER = (
    "MATCH (c:DocChunk {source: $src}) WHERE c.chunk_id IN $ids "
    "OPTIONAL MATCH (c)-[:MENTIONS]->(k1:KnowledgePoint) "
    "OPTIONAL MATCH (c)-[:BELONGS_TO]->(:Chapter)-[:MENTIONS]->(k2:KnowledgePoint) "
    "RETURN collect(DISTINCT k1) + collect(DISTINCT k2) AS ents"
)
# ② 实体图 1..H 跳（RELATED|PREREQUISITE 无向）→ 邻居实体被 MENTIONS 的 DocChunk；
#    排除种子 chunk；min(length(p)) = 最小跳数；(hops, chunk_id) 排序保证确定性。
#    注意：Cypher map 字面量 {} 须转义为 {{}}（.format 仅插值 {hops}/{max_n}）。
_EXPAND_CYPHER = (
    "UNWIND $keys AS ekey "
    "MATCH (e:KnowledgePoint {{source: $src, key: ekey}}) "
    "MATCH p = (e)-[:RELATED|PREREQUISITE*1..{hops}]-(e2:KnowledgePoint) "
    "WHERE e2.source = $src "
    "MATCH (e2)<-[:MENTIONS]-(nb:DocChunk {{source: $src}}) "
    "WHERE NOT nb.chunk_id IN $ids "
    "RETURN nb.chunk_id AS chunk_id, min(length(p)) AS hops, max(nb.preview) AS preview "
    "ORDER BY hops, chunk_id LIMIT {max_n}"
)


def _run_queries(
    driver: object,
    database: str | None,
    chunk_ids: list[str],
    *,
    hops: int = 2,
    max_neighbors: int = 30,
) -> list[tuple[str, int, str | None]]:
    """同步执行两段 Cypher（neo4j_run 内部 to_thread）。返回 (chunk_id, hops, preview) 列表。

    确定性：(hops, chunk_id) 升序 + LIMIT 截断。stub driver 注入可离线单测
    （对齐 tests/test_kg_rn1.py stub 范式）。
    """
    hops_i = max(1, int(hops))
    max_n = max(1, int(max_neighbors))
    expand_cypher = _EXPAND_CYPHER.format(hops=hops_i, max_n=max_n)
    with driver.session(database=database) as session:
        seed_row = session.run(_SEED_ENTITY_CYPHER, src=KG_SOURCE, ids=list(chunk_ids)).single()
        ents = list((seed_row or {}).get("ents") or [])
        # collect(DISTINCT null)=[]；chunk 面 + 章节面后按 key 去重（同 KP 可两面到达）
        keys = sorted({str(n["key"]) for n in ents if n and n.get("key")})
        if not keys:
            return []
        rows = session.run(expand_cypher, src=KG_SOURCE, keys=keys).data()
    out: list[tuple[str, int, str | None]] = []
    for r in rows:
        cid = str(r.get("chunk_id") or "")
        if cid:
            out.append((cid, int(r.get("hops") or hops_i), r.get("preview")))
    # 双保险排序（Cypher 已 ORDER BY；stub/驱动行为差异下仍确定性）
    out.sort(key=lambda t: (t[1], t[0]))
    return out[:max_n]


async def fetch_neighbor_chunks(
    chunk_ids: list[str],
    *,
    hops: int = 2,
    timeout_s: float = 0.8,
    max_neighbors: int = 30,
) -> KGBridgeResult:
    """第四通道主入口：种子 chunk_ids → Neo4j 邻居 chunk。恒不抛异常。

    降级语义（degraded_reason 取值，均不影响主链路）：
    - kg_expand:empty_seeds          种子列表为空（上游候选空，直接零开销返回）
    - kg_expand:neo4j_not_connected  driver 未初始化（lifespan 连接失败/未启用）
    - kg_expand:timeout({t}s)        超出预算（asyncio.wait_for 硬顶，默认 800ms）
    - kg_expand:neo4j_breaker_open   连续失败熔断中（毫秒级快速失败，不触达 Neo4j）
    - kg_expand:{ExcName}            其他异常（全吞，WARN 留痕）
    """
    if not chunk_ids:
        return KGBridgeResult([], {}, "kg_expand:empty_seeds")
    database = getattr(settings, "NEO4J_DATABASE", None)
    try:
        from app.core.db_resilience import DependencyUnavailableError, neo4j_run
        from app.database import get_neo4j_driver

        def _do_all() -> KGBridgeResult:
            # 整段（含 driver 懒初始化）跑线程：get_neo4j_driver 首次连接是同步阻塞调用，
            # 若留在协程内会阻塞事件循环、令 wait_for 预算失效（P1-4 同类教训）；
            # 放线程内 → 预算由外层 wait_for 硬顶，死 Neo4j 最坏首查 ~预算即放弃。
            driver = get_neo4j_driver()
            if driver is None:
                return KGBridgeResult([], {}, "kg_expand:neo4j_not_connected")
            rows = _run_queries(
                driver, database, chunk_ids, hops=hops, max_neighbors=max_neighbors
            )
            return KGBridgeResult(
                [(cid, h) for cid, h, _p in rows],
                {cid: str(p or "") for cid, _h, p in rows if p},
                None,
            )

        return await asyncio.wait_for(
            neo4j_run("kg_expand", _do_all), timeout=max(0.05, float(timeout_s))
        )
    except asyncio.TimeoutError:
        reason = f"kg_expand:timeout({timeout_s}s)"
        logger.warning(f"[kg_bridge] 图谱扩展超预算降级：{reason}（种子 {len(chunk_ids)} 个）")
        return KGBridgeResult([], {}, reason)
    except DependencyUnavailableError:
        reason = "kg_expand:neo4j_breaker_open"
        logger.warning("[kg_bridge] Neo4j 熔断中 → 图谱扩展通道毫秒级快速失败降级")
        return KGBridgeResult([], {}, reason)
    except Exception as exc:  # noqa: BLE001 - 通道降级兜底：任何异常不拖垮检索主链
        reason = f"kg_expand:{type(exc).__name__}"
        logger.warning(f"[kg_bridge] 图谱扩展异常降级：{reason}：{exc}")
        return KGBridgeResult([], {}, reason)
