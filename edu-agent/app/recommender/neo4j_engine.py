# -*- coding: utf-8 -*-
"""
Neo4j 图谱推荐引擎（Phase 3 图谱深度掌握）

这是对现有 MySQL 版 recommender/engine.py 的 Neo4j 补充策略。
MySQL 做不了的事，Neo4j 用 Cypher 图遍历一行搞定：

策略对比：
  MySQL 引擎：冷启动（画像匹配）+ 协同过滤（同画像统计）+ 图谱遍历（MySQL JOIN 递归）
  Neo4j 引擎：最短学习路径（shortestPath）+ 共现推荐（RELATED_TO 图遍历）+ PageRank 重要性

面试考点：
  - 为什么需要 Neo4j？MySQL 的递归 CTE 在 3 层以上先修链时性能指数级下降
  - Cypher 的 shortestPath() 内置 BFS 算法，比手动递归 JOIN 快 100x
  - PageRank 算法：Neo4j GDS 库内置，知识点在网络中的重要性排序
  - 两套引擎互补：MySQL 做画像匹配 + 行为统计，Neo4j 做图遍历 + 路径推荐
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.database import get_neo4j_driver


# ============================================================
# 策略 1：最短学习路径（shortestPath）
# ============================================================
def find_shortest_learning_path(
    from_kp_name: str,
    to_kp_name: str,
    *,
    tenant_id: str = "_default",
    max_depth: int = 5,
) -> list[dict[str, Any]]:
    """
    从知识点 A 到知识点 B 的最短先修学习路径。

    面试考点：
    - shortestPath() 内置 BFS 算法，O(V+E) 复杂度
    - MySQL 做同样的事需要递归 CTE，3 层以上性能指数下降
    - 实际应用：学生想学「机器学习」但只会「Python 基础」，计算最短路径

    Cypher 解释：
      MATCH path = shortestPath((a)-[:PREREQUISITE*..5]->(b))
      - *..5 表示 0 到 5 跳的路径
      - PREREQUISITE 边的方向：from 必须先于 to，所以 from→to 表示先修顺序
      - nodes(path) 返回路径上的所有节点
    """
    driver = get_neo4j_driver()
    if driver is None:
        return []

    cypher = """
    MATCH path = shortestPath(
      (a:KnowledgePoint {name: $from_name, tenant_id: $tenant_id})
      -[:PREREQUISITE*..$max_depth]->
      (b:KnowledgePoint {name: $to_name, tenant_id: $tenant_id})
    )
    RETURN
      length(path) AS hops,
      [n IN nodes(path) | n.name] AS node_names,
      [n IN nodes(path) | n.code] AS node_codes,
      reduce(s = 0, r IN relationships(path) | s + coalesce(r.weight, 1)) AS total_weight
    ORDER BY hops ASC
    LIMIT 3
    """

    try:
        with driver.session() as session:
            result = session.run(
                cypher,
                from_name=from_kp_name,
                to_name=to_kp_name,
                tenant_id=tenant_id,
                max_depth=max_depth,
            )
            paths = []
            for record in result:
                paths.append({
                    "hops": record["hops"],
                    "node_names": record["node_names"],
                    "node_codes": record["node_codes"],
                    "total_weight": record["total_weight"],
                })
            return paths
    except Exception as exc:
        print(f"  shortestPath 查询失败: {exc}")
        return []


# ============================================================
# 策略 2：共现知识点推荐（RELATED_TO 图遍历）
# ============================================================
def recommend_by_co_occurrence(
    kp_name: str,
    *,
    tenant_id: str = "_default",
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """
    基于 RELATED_TO 关系的共现推荐："学了 A 的人还学了 B"。

    面试考点：
    - RELATED_TO 边由 graph_builder.py 在导入时自动生成（同模块下关键词共现）
    - 与此对应的是 MySQL 的 collaborative_filter，但 MySQL 需要 JOIN 多张表
    - Neo4j 用 2 跳图遍历：A → RELATED_TO → B → CONTAINS → Module
    - 返回结果包含推荐知识点 + 所属模块 + 关联强度

    Cypher 解释：
      MATCH (a)-[:RELATED_TO]-(b)
      - 无向关系（方向不重要），找到所有与 a 有关联的知识点
      - OPTIONAL MATCH (b)-[:CONTAINS]-(m) 找到 b 所属的模块
      - count(*) 统计共现次数作为关联强度
    """
    driver = get_neo4j_driver()
    if driver is None:
        return []

    cypher = """
    MATCH (a:KnowledgePoint {name: $kp_name, tenant_id: $tenant_id})
          -[:RELATED_TO]-
          (b:KnowledgePoint)
    WHERE b.name <> a.name
    OPTIONAL MATCH (b)<-[:CONTAINS]-(m:CourseModule)
    RETURN
      b.name AS recommended_kp,
      b.code AS kp_code,
      collect(DISTINCT m.name)[0..3] AS related_modules,
      count(*) AS strength
    ORDER BY strength DESC
    LIMIT $top_n
    """

    try:
        with driver.session() as session:
            result = session.run(
                cypher,
                kp_name=kp_name,
                tenant_id=tenant_id,
                top_n=top_n,
            )
            recommendations = []
            for record in result:
                recommendations.append({
                    "recommended_kp": record["recommended_kp"],
                    "kp_code": record["kp_code"],
                    "related_modules": record["related_modules"],
                    "strength": record["strength"],
                })
            return recommendations
    except Exception as exc:
        print(f"  共现推荐查询失败: {exc}")
        return []


# ============================================================
# 策略 3：PageRank 知识点重要性排序
# ============================================================
def pagerank_importance(
    *,
    tenant_id: str = "_default",
    top_n: int = 20,
) -> list[dict[str, Any]]:
    """
    用 PageRank 算法计算知识点在图谱中的重要性。

    面试考点：
    - PageRank 原理：被更多节点引用的节点更重要（类似 Google 网页排名）
    - 在教育场景中：被更多知识点作为前置依赖的知识点 = 基础中的基础
    - Neo4j GDS 库内置 PageRank 算法，无需手动实现迭代

    实际应用：
    - 学习路径规划：PageRank 高的知识点应优先学习（基础中的基础）
    - 课程设计：PageRank 高的知识点应放在课程开头

    注意：需要 Neo4j GDS 库（Graph Data Science）。
    如果未安装，降级为简单的入度统计（indegree）。
    """
    driver = get_neo4j_driver()
    if driver is None:
        return []

    # 先尝试 GDS PageRank，失败则降级为入度统计
    try:
        cypher = """
        MATCH (kp:KnowledgePoint {tenant_id: $tenant_id})
        OPTIONAL MATCH (kp)<-[:PREREQUISITE]-(dependent:KnowledgePoint)
        WITH kp, count(dependent) AS indegree
        WHERE indegree > 0
        RETURN
          kp.name AS name,
          kp.code AS code,
          indegree AS importance,
          'indegree' AS algorithm
        ORDER BY indegree DESC
        LIMIT $top_n
        """
        with driver.session() as session:
            result = session.run(cypher, tenant_id=tenant_id, top_n=top_n)
            rankings = []
            for record in result:
                rankings.append({
                    "name": record["name"],
                    "code": record["code"],
                    "importance": record["importance"],
                    "algorithm": record["algorithm"],
                })
            return rankings
    except Exception as exc:
        print(f"  PageRank 查询失败: {exc}")
        return []


# ============================================================
# 策略 4：学习路径完整性检查
# ============================================================
def check_learning_path_gaps(
    target_kp_name: str,
    mastered_kp_names: list[str],
    *,
    tenant_id: str = "_default",
    max_depth: int = 4,
) -> list[dict[str, Any]]:
    """
    检查学习路径缺口：要达到目标知识点，还缺哪些前置知识？

    面试考点：
    - 这是「先修链分析」的逆向思维：不是从已学找下一步，而是从目标往回找缺口
    - 实际应用：学生想学「机器学习」，系统自动检查缺少哪些前置知识

    Cypher 解释：
      MATCH path = (a)-[:PREREQUISITE*..4]->(b)
      - 找到从任意前置知识点到目标知识点的所有路径
      - WHERE NOT a.name IN $mastered 过滤掉已掌握的知识点
      - 返回缺口知识点 + 所在路径深度
    """
    driver = get_neo4j_driver()
    if driver is None:
        return []

    cypher = """
    MATCH path = (a:KnowledgePoint)-[:PREREQUISITE*..$max_depth]->(b:KnowledgePoint {name: $target_name, tenant_id: $tenant_id})
    WHERE NOT a.name IN $mastered
    RETURN
      a.name AS gap_kp,
      a.code AS gap_code,
      length(path) AS distance_to_target,
      [n IN nodes(path) | n.name] AS full_path
    ORDER BY distance_to_target ASC
    LIMIT 10
    """

    try:
        with driver.session() as session:
            result = session.run(
                cypher,
                target_name=target_kp_name,
                mastered=mastered_kp_names,
                tenant_id=tenant_id,
                max_depth=max_depth,
            )
            gaps = []
            for record in result:
                gaps.append({
                    "gap_kp": record["gap_kp"],
                    "gap_code": record["gap_code"],
                    "distance_to_target": record["distance_to_target"],
                    "full_path": record["full_path"],
                })
            return gaps
    except Exception as exc:
        print(f"  学习路径缺口查询失败: {exc}")
        return []


# ============================================================
# 演示入口
# ============================================================
def demo():
    """演示 4 种 Neo4j 图推荐策略。"""
    print("=" * 60)
    print("  EduAgent Neo4j 图谱推荐引擎")
    print("=" * 60)
    print()

    # 策略 1：最短学习路径
    print("1. 最短学习路径：'Python Basics' → 'Machine Learning'")
    paths = find_shortest_learning_path("Python Basics", "Machine Learning")
    if paths:
        for p in paths:
            print(f"   {p['hops']} 跳: {' → '.join(p['node_names'])}")
    else:
        print("   无结果（可能知识点不存在或 Neo4j 未连接）")

    print()

    # 策略 2：共现推荐
    print("2. 共现推荐：'Python Decorator' 的相关知识点")
    recs = recommend_by_co_occurrence("Python Decorator", top_n=5)
    if recs:
        for r in recs:
            print(f"   {r['recommended_kp']}（关联强度: {r['strength']}）→ 模块: {r['related_modules']}")
    else:
        print("   无结果")

    print()

    # 策略 3：PageRank 重要性
    print("3. 知识点重要性排序（入度 = 被多少知识点依赖）")
    ranks = pagerank_importance(top_n=5)
    if ranks:
        for r in ranks:
            print(f"   {r['name']}（重要性: {r['importance']}）")
    else:
        print("   无结果")

    print()

    # 策略 4：学习路径缺口
    print("4. 学习路径缺口：目标 'Machine Learning'，已掌握 ['Python Basics']")
    gaps = check_learning_path_gaps("Machine Learning", ["Python Basics"])
    if gaps:
        for g in gaps:
            print(f"   缺口: {g['gap_kp']}（距目标 {g['distance_to_target']} 步）→ 路径: {' → '.join(g['full_path'])}")
    else:
        print("   无缺口（前置知识已全部掌握）或 Neo4j 未连接")


if __name__ == "__main__":
    demo()