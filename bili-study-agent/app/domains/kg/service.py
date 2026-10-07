# -*- coding: utf-8 -*-
"""KG-2 查询服务（R-N1）：Neo4j 只读查询 + 环检测/最短路编排。

降级链（对齐 reshape-b v2 既有范式 T19-3）：
- driver 未初始化（lifespan init_neo4j 失败 / DEBUG 跳过）→ DependencyUnavailableError(50301)；
- Neo4j 运行期异常（ServiceUnavailable/AuthError/SessionExpired/…）→ logger.exception
  完整入日志（含堆栈）+ DependencyUnavailableError(50301)，message 面向用户，
  detail 恒 None（脱敏契约：原始异常不进响应）。

查询作用域：全部限定 source='kg_sync'——P1 遗留节点（无 source 属性）天然被排除。
"""
from __future__ import annotations

import logging
from typing import Any

from app.common.error_codes import (
    KG_CHAPTER_NOT_FOUND,
    KG_COURSE_NOT_FOUND,
    KG_NODE_NOT_FOUND,
    KG_PREREQUISITE_CYCLE,
)
from app.common.exceptions import AppException, DependencyUnavailableError
from app.domains.kg import graph as kg_graph
from app.domains.kg.sync_core import KG_SOURCE  # 修复（接手 R-N1）：前任遗漏导入，运行期 NameError → 50000
from app.domains.kg.schemas import (
    KgChapterNeighborsData,
    KgCoursePathData,
    KgNodeRef,
    KgPathStep,
)

logger = logging.getLogger(__name__)

_PREREQ_CYPHER = (
    "MATCH (a:KnowledgePoint)-[r:PREREQUISITE]->(b:KnowledgePoint) "
    "WHERE a.source=$src AND b.source=$src "
    "RETURN DISTINCT a.key AS a_key, a.code AS a_code, a.name AS a_name, "
    "b.key AS b_key, b.code AS b_code, b.name AS b_name"
)


def _get_driver() -> Any:
    """取全局 Neo4j driver；未初始化/失败 → 50301（依赖不可用）。"""
    from app.database import get_neo4j_driver

    driver = get_neo4j_driver()
    if driver is None:
        raise DependencyUnavailableError()
    return driver


def _read(session: Any, cypher: str, **params: Any) -> list[dict[str, Any]]:
    try:
        return session.run(cypher, **params).data()
    except Exception as exc:
        # 脱敏契约（T19-3）：原始异常完整入日志，响应只给用户话术 + 50301
        logger.exception("[kg] Neo4j 查询失败: %s", type(exc).__name__)
        raise DependencyUnavailableError() from exc


def _session_block(driver: Any) -> Any:
    """session 作用域包装（修复：接手 R-N1 实测——前任版本只包 _read，
    driver.session() 创建/with 进入期异常（SessionExpired/AuthError/连接复位）
    裸抛 RuntimeError → 全局 50000。此处统一包 50301；AppException（40460 等）
    透传不吞。DependencyUnavailableError 是 AppException 子类，二次包装无害。"""
    class _Ctx:
        def __enter__(self) -> Any:
            try:
                self._s = driver.session()
            except AppException:
                raise
            except Exception as exc:
                logger.exception("[kg] Neo4j session 创建失败: %s", type(exc).__name__)
                raise DependencyUnavailableError() from exc
            return self._s

        def __exit__(self, exc_type: Any, exc_val: Any, tb: Any) -> bool:
            try:
                return bool(self._s.__exit__(exc_type, exc_val, tb))
            except AppException:
                raise
            except Exception as exc:
                if exc_val is not None:
                    # body 已有异常在途：close 期故障只记日志，不遮蔽原异常
                    logger.warning(
                        "[kg] Neo4j session 关闭失败（body 异常在途，不遮蔽）: %s",
                        type(exc).__name__,
                    )
                    return False
                logger.exception("[kg] Neo4j session 关闭失败: %s", type(exc).__name__)
                raise DependencyUnavailableError() from exc

    return _Ctx()


# ══════════════════════════════════════════════════════════════
# 课程先修路径（含环检测）
# ══════════════════════════════════════════════════════════════
def course_path(course_id: int, from_code: str, to_code: str) -> KgCoursePathData:
    """课程内最短先修路径；先修环 → 40910（fail-closed，不做拓扑近似）。"""
    driver = _get_driver()
    with _session_block(driver) as session:
        course_rows = _read(
            session,
            "MATCH (c:Course {series_id:$cid}) WHERE c.source=$src RETURN c LIMIT 1",
            cid=course_id,
            src=KG_SOURCE,
        )
        if not course_rows:
            raise AppException(
                KG_COURSE_NOT_FOUND, f"图谱中不存在课程：{course_id}"
            )
        course_props = course_rows[0]["c"]

        kp_rows = _read(
            session,
            "MATCH (k:KnowledgePoint) WHERE k.source=$src AND k.code IN [$f, $t] "
            "RETURN k.code AS code",
            src=KG_SOURCE,
            f=from_code,
            t=to_code,
        )
        found_codes = {r["code"] for r in kp_rows}
        if from_code not in found_codes:
            raise AppException(KG_NODE_NOT_FOUND, f"知识点不存在：{from_code}")
        if to_code not in found_codes:
            raise AppException(KG_NODE_NOT_FOUND, f"知识点不存在：{to_code}")

        edge_rows = _read(session, _PREREQ_CYPHER, src=KG_SOURCE)

    edges = [(r["a_key"], r["b_key"]) for r in edge_rows]
    name_by_key: dict[str, str | None] = {}
    code_by_key: dict[str, str] = {}
    for r in edge_rows:
        name_by_key[r["a_key"]] = r["a_name"]
        code_by_key[r["a_key"]] = r["a_code"]
        name_by_key[r["b_key"]] = r["b_name"]
        code_by_key[r["b_key"]] = r["b_code"]

    # 环检测（脏数据防御）：先修图带环 → 拓扑语义失效，明确 40910 而非死循环/近似
    cycle = kg_graph.find_cycle(edges)
    if cycle:
        cycle_codes = [code_by_key.get(k, k) for k in cycle]
        raise AppException(
            KG_PREREQUISITE_CYCLE,
            "先修图存在环，无法计算学习路径：" + " → ".join(cycle_codes),
        )

    src_key = f"kp:{from_code}"
    dst_key = f"kp:{to_code}"
    path_keys = kg_graph.shortest_path(edges, src_key, dst_key)
    steps = []
    if path_keys:
        steps = [
            KgPathStep(step=i + 1, key=k, code=code_by_key.get(k), name=name_by_key.get(k))
            for i, k in enumerate(path_keys)
        ]
    return KgCoursePathData(
        course=KgNodeRef(
            key=course_props["key"],
            type="course",
            code=course_props.get("code"),
            name=course_props.get("name"),
        ),
        from_code=from_code,
        to_code=to_code,
        found=bool(path_keys),
        hops=max(len(path_keys) - 1, 0) if path_keys else 0,
        path=steps,
        cycle_checked=True,
    )


# ══════════════════════════════════════════════════════════════
# 章节前置/后续知识面
# ══════════════════════════════════════════════════════════════
def chapter_neighbors(chapter_code: str, direction: str) -> KgChapterNeighborsData:
    """章节 upstream（前置）/downstream（后续）知识面。

    定义：
      mentioned_kps   = 本章 MENTIONS 的知识点集合（rule=module_contains / keyword_match）
      neighbor_kps    = upstream：{p | (p)-[:PREREQUISITE]->(q), q∈mentioned}
                        downstream：{s | (q)-[:PREREQUISITE]->(s), q∈mentioned}
      neighbor_chapters = 邻接知识点被哪些章节 MENTIONS（剔除本章自身）
    """
    driver = _get_driver()
    with _session_block(driver) as session:
        chapter_rows = _read(
            session,
            "MATCH (ch:Chapter {code:$code}) WHERE ch.source=$src RETURN ch LIMIT 1",
            code=chapter_code,
            src=KG_SOURCE,
        )
        if not chapter_rows:
            raise AppException(KG_CHAPTER_NOT_FOUND, f"图谱中不存在章节：{chapter_code}")
        chapter_props = chapter_rows[0]["ch"]

        mention_rows = _read(
            session,
            "MATCH (x)-[:MENTIONS]->(k:KnowledgePoint) "
            "WHERE x.source=$src AND k.source=$src AND x.key=$ckey "
            "RETURN DISTINCT k.key AS key, k.code AS code, k.name AS name",
            src=KG_SOURCE,
            ckey=chapter_props["key"],
        )
        mentioned = [
            KgNodeRef(key=r["key"], type="knowledge_point", code=r["code"], name=r["name"])
            for r in mention_rows
        ]
        mentioned_keys = [r["key"] for r in mention_rows]

        edge_rows = _read(session, _PREREQ_CYPHER, src=KG_SOURCE)
        edges = [(r["a_key"], r["b_key"]) for r in edge_rows]
        meta_by_key: dict[str, dict[str, Any]] = {}
        for r in edge_rows:
            meta_by_key[r["a_key"]] = {"key": r["a_key"], "code": r["a_code"], "name": r["a_name"]}
            meta_by_key[r["b_key"]] = {"key": r["b_key"], "code": r["b_code"], "name": r["b_name"]}

        neighbor_keys: set[str] = set()
        if mentioned_keys:
            if direction == "upstream":
                # 直接前置并集：沿反向 PREREQUISITE 走 1 跳
                rev = [(b, a) for a, b in edges]
                for mk in mentioned_keys:
                    neighbor_keys |= set(kg_graph.reachable_within(rev, mk, max_depth=1))
            else:
                # 直接后续并集：沿正向 PREREQUISITE 走 1 跳
                for mk in mentioned_keys:
                    neighbor_keys |= set(kg_graph.reachable_within(edges, mk, max_depth=1))
            neighbor_keys -= set(mentioned_keys)  # 邻接不含本章已覆盖知识点自身

        chapter_rows2: list[dict[str, Any]] = []
        if neighbor_keys:
            chapter_rows2 = _read(
                session,
                "MATCH (ch:Chapter)-[:MENTIONS]->(k:KnowledgePoint) "
                "WHERE ch.source=$src AND k.source=$src AND k.key IN $keys "
                "RETURN DISTINCT ch.key AS key, ch.code AS code, ch.name AS name",
                src=KG_SOURCE,
                keys=sorted(neighbor_keys),
            )

    neighbor_kps = [
        KgNodeRef(key=k, type="knowledge_point",
                  code=meta_by_key.get(k, {}).get("code"),
                  name=meta_by_key.get(k, {}).get("name"))
        for k in sorted(neighbor_keys)
    ]
    neighbor_chapters = [
        KgNodeRef(key=r["key"], type="chapter", code=r["code"], name=r["name"])
        for r in chapter_rows2
        if r["key"] != chapter_props["key"]
    ]
    return KgChapterNeighborsData(
        chapter=KgNodeRef(
            key=chapter_props["key"], type="chapter",
            code=chapter_props.get("code"), name=chapter_props.get("name"),
        ),
        direction=direction,
        mentioned_kps=mentioned,
        neighbor_kps=neighbor_kps,
        neighbor_chapters=neighbor_chapters,
    )
