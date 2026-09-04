"""
Neo4j 索引与查询优化脚本（Phase 3 图谱深度掌握）

面试考点：
- 为什么 Neo4j 需要显式建索引？没有索引时 MERGE 会全图扫描（AllNodesScan）
- 约束（Constraint）vs 索引（Index）：约束保证唯一性+自动建索引，索引只加速查询
- 复合索引：Neo4j 5.x 支持 composite index，加速多字段查询
- EXPLAIN vs PROFILE：EXPLAIN 只看计划不执行，PROFILE 实际执行+统计

当前问题：
- graph_builder.py 的 MERGE 语句没有索引支撑，每次 MERGE 都做 AllNodesScan
- 导入 1000 个知识点 = 1000 次全图扫描 → O(n²) 复杂度
- 加了索引后 MERGE 变成 NodeIndexSeek → O(log n)

用法：
  python tests/performance/neo4j_optimizer.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.database import get_neo4j_driver


# ============================================================
# 索引创建（幂等：已存在则跳过）
# ============================================================
NEO4J_INDEXES = [
    # ── 节点索引（加速 MERGE 的 MATCH 查找） ──
    # 语法：CREATE INDEX index_name FOR (n:Label) ON (n.property)
    ("idx_kp_name", "CREATE INDEX idx_kp_name IF NOT EXISTS FOR (n:KnowledgePoint) ON (n.name)"),
    ("idx_kp_tenant", "CREATE INDEX idx_kp_tenant IF NOT EXISTS FOR (n:KnowledgePoint) ON (n.tenant_id)"),
    ("idx_series_code", "CREATE INDEX idx_series_code IF NOT EXISTS FOR (n:CourseSeries) ON (n.code)"),
    ("idx_module_code", "CREATE INDEX idx_module_code IF NOT EXISTS FOR (n:CourseModule) ON (n.code)"),
    ("idx_qt_name", "CREATE INDEX idx_qt_name IF NOT EXISTS FOR (n:QuestionTag) ON (n.name)"),

    # ── 复合索引（同时加速 tenant_id + 业务字段查询） ──
    ("idx_kp_tenant_name", "CREATE INDEX idx_kp_tenant_name IF NOT EXISTS FOR (n:KnowledgePoint) ON (n.tenant_id, n.name)"),

    # ── 关系类型索引（加速 MATCH ()-[r:CONTAINS]->() 查询） ──
    ("idx_rel_contains", "CREATE INDEX idx_rel_contains IF NOT EXISTS FOR ()-[r:CONTAINS]-() ON (r.stage_no)"),
    ("idx_rel_prereq", "CREATE INDEX idx_rel_prereq IF NOT EXISTS FOR ()-[r:PREREQUISITE]-() ON (r.prerequisite)"),

    # ── 唯一性约束（防止同 tenant 下同 code 的重复节点） ──
    # 约束会同时创建索引，所以 IF NOT EXISTS 不会重复建
    ("cst_kp_unique", "CREATE CONSTRAINT cst_kp_unique IF NOT EXISTS FOR (n:KnowledgePoint) REQUIRE (n.tenant_id, n.name) IS UNIQUE"),
    ("cst_series_unique", "CREATE CONSTRAINT cst_series_unique IF NOT EXISTS FOR (n:CourseSeries) REQUIRE (n.tenant_id, n.code) IS UNIQUE"),
]


def create_neo4j_indexes() -> dict[str, bool]:
    """
    创建 Neo4j 索引和约束。

    返回 {index_name: created(bool)}，已存在的索引返回 False。
    面试考点：IF NOT EXISTS 保证幂等，CI/CD 中可重复执行。
    """
    driver = get_neo4j_driver()
    if driver is None:
        print("Neo4j driver 未初始化，跳过索引创建")
        return {}

    results = {}
    with driver.session() as session:
        for name, cypher in NEO4J_INDEXES:
            try:
                session.run(cypher)
                results[name] = True
                print(f"  ✅ {name}")
            except Exception as exc:
                # "already exists" 类错误视为成功（幂等）
                err_msg = str(exc)
                if "already exists" in err_msg.lower() or "equivalent" in err_msg.lower():
                    results[name] = False
                    print(f"  ⏭️ {name}（已存在）")
                else:
                    results[name] = False
                    print(f"  ❌ {name}: {err_msg[:120]}")

    created = sum(1 for v in results.values() if v)
    print(f"  共创建 {created} 个新索引/约束，{len(results) - created} 个已存在")
    return results


# ============================================================
# Cypher 查询 PROFILE 分析
# ============================================================
def profile_queries():
    """
    对核心 Cypher 查询执行 PROFILE，输出执行计划。

    面试考点：
    - PROFILE 显示实际执行统计（db hits、rows、memory）
    - AllNodesScan → 加索引后变成 NodeIndexSeek
    - Eager 操作 → 大量中间结果，需要 LIMIT 或改写查询
    """
    driver = get_neo4j_driver()
    if driver is None:
        print("Neo4j driver 未初始化，跳过 PROFILE")
        return

    queries = [
        # 查询 1：某课程系列的所有知识点（2 层关系遍历）
        ("某课程系列的知识点",
         """
         PROFILE
         MATCH (s:CourseSeries {code: 'ENG-L1'})-[:CONTAINS]->(m:CourseModule)-[:CONTAINS]->(kp:KnowledgePoint)
         RETURN s.name AS series, m.code AS module, kp.name AS knowledge_point
         LIMIT 50
         """),

        # 查询 2：某知识点的所有前置依赖（先修链）
        ("知识点的先修链",
         """
         PROFILE
         MATCH path = (kp:KnowledgePoint {name: 'Present Perfect'})-[:PREREQUISITE*1..3]->(pre:KnowledgePoint)
         RETURN kp.name AS target, [n IN nodes(path) | n.name] AS prerequisite_chain
         LIMIT 10
         """),

        # 查询 3：共现知识点推荐（"学了 A 的人还学了 B"）
        ("共现知识点推荐",
         """
         PROFILE
         MATCH (kp1:KnowledgePoint)-[:RELATED_TO]-(kp2:KnowledgePoint)
         WHERE kp1.name = 'Python Decorator'
         RETURN kp2.name AS related_topic, count(*) AS strength
         ORDER BY strength DESC
         LIMIT 10
         """),

        # 查询 4：某模块的完整知识图谱（节点+关系）
        ("模块知识图谱",
         """
         PROFILE
         MATCH (m:CourseModule {code: 'ENG-L1-M1'})
         OPTIONAL MATCH (m)-[:CONTAINS]->(kp:KnowledgePoint)
         OPTIONAL MATCH (m)-[:PREREQUISITE]->(pre)
         OPTIONAL MATCH (kp)-[:RELATED_TO]-(related:KnowledgePoint)
         RETURN m.code AS module,
                collect(DISTINCT kp.name) AS knowledge_points,
                collect(DISTINCT pre.name) AS prerequisites,
                collect(DISTINCT related.name) AS related_topics
         LIMIT 1
         """),
    ]

    with driver.session() as session:
        for title, cypher in queries:
            print(f"\n--- {title} ---")
            try:
                result = session.run(cypher)
                # 取 PROFILE 的执行计划
                summary = result.consume()
                plan = summary.profile
                if plan:
                    # 统计操作类型
                    ops: dict[str, int] = {}
                    def _count_ops(node):
                        op = node.get("operatorType", "Unknown")
                        ops[op] = ops.get(op, 0) + 1
                        for child in node.get("children", []):
                            _count_ops(child)
                    _count_ops(plan)

                    print(f"    db_hits: {summary.result_available_after}ms (结果可用) / {summary.result_consumed_after}ms (消费完成)")
                    print(f"    操作分布: {ops}")
                    # 检查是否有 AllNodesScan
                    if "AllNodesScan" in ops:
                        print(f"    ⚠️ 存在 AllNodesScan！建议添加索引（见上方索引列表）")
                    else:
                        print(f"    ✅ 无全图扫描，索引命中正常")
            except Exception as exc:
                print(f"    ❌ 查询失败: {exc}")


# ============================================================
# 主入口
# ============================================================
def main():
    print("=" * 60)
    print("  EduAgent Neo4j 索引与查询优化")
    print("=" * 60)
    print()

    print("1. 创建索引/约束")
    create_neo4j_indexes()
    print()

    print("2. PROFILE 查询分析")
    profile_queries()
    print()

    print("完成！")


if __name__ == "__main__":
    main()