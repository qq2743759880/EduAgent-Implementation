# -*- coding: utf-8 -*-
"""P4 思维导图 builder（基于 MySQL graph_node/graph_edge 替代 Neo4j）。"""
from __future__ import annotations

from typing import Any

from app.database import fetch_all
from app.mindmap.schemas import MindMap, MindMapLink, MindMapNode


CATEGORY_OF_LABEL = {
    "CourseSeries": 0,
    "CourseModule": 1,
    "KnowledgePoint": 2,
    "QuestionTag": 3,
}
LINE_STYLE_BY_REL: dict[str, dict[str, Any]] = {
    "CONTAINS":     {"color": "#5B8FF9", "type": "solid", "width": 1.2},
    "PREREQUISITE": {"color": "#F6BD16", "type": "solid", "width": 2.0, "curveness": 0.2},
    "RELATED_TO":   {"color": "#945FB9", "type": "dashed", "width": 1.0},
    "TESTS":        {"color": "#5AD8A6", "type": "solid", "width": 1.0},
}


def _mastery_status(ratio: float) -> str:
    if ratio >= 0.9:
        return "MASTERED"
    if ratio >= 0.3:
        return "IN_PROGRESS"
    if ratio <= 0.0:
        return "NOT_STARTED"
    return "BLOCKED"


def _value_of(label: str, kids_count: int, ratio: float) -> int:
    base = {
        "CourseSeries": 48,
        "CourseModule": 32,
        "KnowledgePoint": 22,
        "QuestionTag": 16,
    }.get(label, 18)
    return int(base + kids_count * 2 + int(ratio * 10))


# ============================================================
# 1. build_from_neo4j 等价实现（MySQL 图谱 → series_id 过滤）
# ============================================================

async def build_from_neo4j(series_id: int | None = None, subject_code: str | None = None) -> MindMap:
    """
    从 MySQL graph_node/graph_edge 构建课程系列思维导图（替代 Neo4j Cypher 查询）。

    - 如指定 series_id：围绕该系列 + 其下属 module + 下属 KP + 关联标签绘制。
    - 否则按 subject_code（若有）过滤，或整张图谱前 200 节点。
    """
    # step 1: 节点筛选
    where: list[str] = ["N.yn = 1"]
    params: list[Any] = []
    if series_id and series_id > 0:
        seed = await fetch_all(
            "SELECT id, label, code FROM graph_node WHERE label='CourseSeries' AND id=%s AND yn=1 LIMIT 1",
            (series_id,),
        )
        if not seed:
            # code 不可用 → 也允许用 subject_code
            series_id = 0
        else:
            root_series_id = int(seed[0]["id"])
            where.append(f"""
            (
              N.id = %s OR
              N.parent_id = %s OR
              N.id IN (SELECT E.to_node_id FROM graph_edge E WHERE E.yn=1 AND E.rel_type='CONTAINS'
                       AND (E.from_node_id = %s OR E.from_node_id IN (
                         SELECT id FROM graph_node WHERE parent_id = %s AND yn=1 AND label='CourseModule'
                       ))) OR
              N.label='QuestionTag' AND N.id IN (SELECT E.to_node_id FROM graph_edge E WHERE E.yn=1 AND E.rel_type='TESTS'
                       AND E.from_node_id IN (
                         SELECT K.id FROM graph_node K WHERE K.yn=1 AND (
                           K.parent_id = %s OR
                           K.id IN (SELECT E2.to_node_id FROM graph_edge E2 WHERE E2.yn=1 AND E2.rel_type='CONTAINS'
                                    AND E2.from_node_id IN (
                                      SELECT id FROM graph_node WHERE parent_id=%s AND yn=1 AND label='CourseModule'
                                    ))
                         )
                       ))
            )
            """)
            params.extend([root_series_id, root_series_id, root_series_id, root_series_id, root_series_id, root_series_id])
    if subject_code and (not series_id or series_id == 0):
        where.append("LOWER(N.subject_code) = %s")
        params.append(subject_code.lower())
    where_sql = " AND ".join(where)
    limit_sql = ""
    if not subject_code and (not series_id or series_id == 0):
        limit_sql = " LIMIT 200 "

    nodes = await fetch_all(
        f"SELECT N.id, N.label, N.code, N.name, N.subject_code, N.sort_no, N.properties_json "
        f"FROM graph_node N WHERE {where_sql} ORDER BY N.subject_code, N.label, N.sort_no {limit_sql}",
        tuple(params),
    )
    if not nodes:
        # 至少返回空骨架（便于前端渲染）
        return MindMap(title=f"空图谱 {subject_code or ''}", subject_code=subject_code, nodes=[], links=[], stats={"node_count": 0, "edge_count": 0})

    node_ids = [int(n["id"]) for n in nodes]
    placeholders = ",".join(["%s"] * len(node_ids))
    edges = await fetch_all(
        f"SELECT from_node_id, to_node_id, rel_type, weight FROM graph_edge "
        f"WHERE yn=1 AND from_node_id IN ({placeholders}) AND to_node_id IN ({placeholders})",
        tuple(node_ids + node_ids),
    )

    # 统计：每个 CourseSeries/MODULE 的子孩子数（用来定 node.value 大小）
    children_count: dict[int, int] = {}
    for e in edges:
        if e["rel_type"] == "CONTAINS":
            children_count[int(e["from_node_id"])] = children_count.get(int(e["from_node_id"]), 0) + 1

    def subject_of(series_id_hint: Any) -> str | None:
        if isinstance(series_id_hint, dict):
            return series_id_hint.get("subject_code")
        return None

    node_id_to_code: dict[int, str] = {int(n["id"]): n["code"] for n in nodes}
    node_objs: list[MindMapNode] = []
    stats_mastered = stats_progress = 0
    for n in nodes:
        nid = int(n["id"])
        status = "NOT_STARTED"
        ratio = 0.0
        category = CATEGORY_OF_LABEL.get(n["label"], 2)
        if status == "MASTERED":
            stats_mastered += 1
        elif status == "IN_PROGRESS":
            stats_progress += 1
        node_objs.append(MindMapNode(
            id=n["code"],
            label=n["label"],
            name=n["name"],
            subject_code=n["subject_code"] or subject_of(n),
            category=category,
            value=_value_of(n["label"], children_count.get(nid, 0), ratio),
            status=status,
            mastery_ratio=ratio,
        ))

    link_objs: list[MindMapLink] = []
    for e in edges:
        src = node_id_to_code.get(int(e["from_node_id"]))
        dst = node_id_to_code.get(int(e["to_node_id"]))
        if not src or not dst:
            continue
        link_objs.append(MindMapLink(
            source=src,
            target=dst,
            rel_type=e["rel_type"],
            line_style=dict(LINE_STYLE_BY_REL.get(e["rel_type"], {"color": "#ccc", "type": "solid", "width": 1})),
        ))

    title_parts = []
    if series_id:
        first_series = next((n for n in nodes if n["label"] == "CourseSeries"), None)
        if first_series:
            title_parts.append(first_series["name"])
    if subject_code:
        title_parts.append(f"{subject_code.upper()} 学科")
    if not title_parts:
        title_parts.append("学习图谱总览")
    title = " / ".join(title_parts)

    stats = {
        "node_count": len(node_objs),
        "edge_count": len(link_objs),
        "by_label": {
            lbl: sum(1 for n in node_objs if n.label == lbl)
            for lbl in CATEGORY_OF_LABEL
        },
        "mastered_count": stats_mastered,
        "in_progress_count": stats_progress,
    }
    return MindMap(
        title=title,
        subject_code=next(iter({n["subject_code"] for n in nodes if n["subject_code"]}), None),
        nodes=node_objs,
        links=link_objs,
        stats=stats,
    )


# ============================================================
# 2. 叠加用户学习进度（上色 MASTERED/IN_PROGRESS）
# ============================================================

async def build_from_user_progress(user_id: int, series_id: int | None = None,
                                    subject_code: str | None = None) -> MindMap:
    """在 build_from_neo4j 基础上，用 P3 数据给节点叠 mastery 颜色。"""
    from app.recommender.engine import _load_mastery_by_kp_code
    base = await build_from_neo4j(series_id=series_id, subject_code=subject_code)
    kp_ratio = await _load_mastery_by_kp_code(user_id)

    # 1) KP 级直接替换 ratio/status
    for n in base.nodes:
        if n.label == "KnowledgePoint" and n.id in kp_ratio:
            n.mastery_ratio = float(kp_ratio[n.id])
            n.status = _mastery_status(n.mastery_ratio)

    # 2) MODULE = 下属 KP 平均；SERIES = 下属 MODULE 平均
    ratio_map: dict[str, float] = {n.id: n.mastery_ratio for n in base.nodes}
    # 两次迭代（先 KP → MODULE, 再 MODULE → SERIES）
    for parent_rel, child_cat in [("CONTAINS", "CourseModule"), ("CONTAINS", "CourseSeries")]:
        for n in base.nodes:
            if child_cat == "CourseModule" and n.label != "CourseModule":
                continue
            if child_cat == "CourseSeries" and n.label != "CourseSeries":
                continue
            child_ids = [
                L.target for L in base.links if L.rel_type == parent_rel and L.source == n.id
            ]
            child_ratios = [ratio_map[c] for c in child_ids if c in ratio_map]
            if child_ratios:
                n.mastery_ratio = round(sum(child_ratios) / len(child_ratios), 4)
                n.status = _mastery_status(n.mastery_ratio)
                ratio_map[n.id] = n.mastery_ratio

    stats_mastered = sum(1 for n in base.nodes if n.status == "MASTERED")
    stats_progress = sum(1 for n in base.nodes if n.status == "IN_PROGRESS")
    base.stats = dict(base.stats or {},
                     mastered_count=stats_mastered,
                     in_progress_count=stats_progress,
                     for_user_id=user_id)
    return base


# ============================================================
# 3. 先修关系树（以某 KP 为起点的 PREREQUISITE 链 / 反向依赖链）
# ============================================================

async def build_prerequisite_tree(kp_code: str | None = None, direction: str = "forward") -> MindMap:
    """
    PREREQUISITE 先修 / 反向依赖链可视化。

    direction:
      - forward：从「最基础先修」→「当前 KP」→「依赖当前 KP 的后续」（完整先修链流向）
      - backward：仅当前 KP 所需的全部前置节点（to→from 反向 BFS）
    kp_code：起点；若为空，随机选 subject 下最长先修链起点。
    """
    # 找起点：如果 kp_code 没提供，选 english 下 第一个 KP 为起点
    if not kp_code:
        seed = await fetch_all(
            "SELECT code FROM graph_node WHERE label='KnowledgePoint' AND yn=1 "
            "ORDER BY subject_code, sort_no LIMIT 1",
        )
        if seed:
            kp_code = seed[0]["code"]
    assert kp_code, "必须提供 kp_code 或库里至少 1 个知识点"

    # id ↔ code
    code_to_id = {r["code"]: int(r["id"]) for r in await fetch_all(
        "SELECT id, code FROM graph_node WHERE label='KnowledgePoint' AND yn=1",
    )}
    id_to_code = {v: k for k, v in code_to_id.items()}
    if kp_code not in code_to_id:
        # 兜底：允许任何 label 的 code
        row = await fetch_one("SELECT id, code FROM graph_node WHERE code=%s AND yn=1 LIMIT 1", (kp_code,))
        if not row:
            return MindMap(title=f"先修链：{kp_code} 未找到", nodes=[], links=[], stats={})
        code_to_id[kp_code] = int(row["id"])
        id_to_code[int(row["id"])] = kp_code
    start = code_to_id[kp_code]

    # 关系：forward=先修→后续；backward=所需前置
    # PREREQUISITE 边：from_node_id → (先修点) 要 先于 → to_node_id
    # forward BFS：沿 edge (P→Q)；start 之后 successors；start 之前 predecessors
    # backward BFS：沿 edge 的反方向（P←Q），即从 start 找所有 P
    rows = await fetch_all(
        "SELECT from_node_id AS fid, to_node_id AS tid FROM graph_edge "
        "WHERE rel_type='PREREQUISITE' AND yn=1",
    )
    adj: dict[int, list[int]] = {}   # 正常 from → list of to (forward successor direction)
    rev: dict[int, list[int]] = {}   # reverse to → list[from]（prereq lookup）
    for r in rows:
        f, t = int(r["fid"]), int(r["tid"])
        adj.setdefault(f, []).append(t)
        rev.setdefault(t, []).append(f)

    # forward：start 的所有祖先 prereq（沿 rev 递归） + start + 所有后继（沿 adj 递归）
    # backward：只有 prereq（rev 递归） + start
    included: set[int] = {start}
    stack = [start]
    while stack:
        cur = stack.pop()
        for p in rev.get(cur, []):
            if p not in included:
                included.add(p)
                stack.append(p)
    if direction == "forward":
        stack = [start]
        while stack:
            cur = stack.pop()
            for c in adj.get(cur, []):
                if c not in included:
                    included.add(c)
                    stack.append(c)

    # 只加载包含的节点（KP 图）
    ids = list(included)
    placeholders = ",".join(["%s"] * len(ids)) if ids else "NULL"
    nodes_rows = await fetch_all(
        f"SELECT id, code, name, subject_code, sort_no FROM graph_node WHERE id IN ({placeholders})",
        tuple(ids),
    )
    id_info = {int(r["id"]): r for r in nodes_rows}

    mm_nodes: list[MindMapNode] = []
    code_to_idx: dict[str, int] = {}
    for nid in sorted(ids, key=lambda i: (id_info.get(i, {}).get("sort_no", 0), i)):
        info = id_info.get(nid) or {}
        n_obj = MindMapNode(
            id=info.get("code") or f"N{nid}",
            label="KnowledgePoint",
            name=info.get("name") or f"KP-{nid}",
            subject_code=info.get("subject_code"),
            category=CATEGORY_OF_LABEL["KnowledgePoint"],
            value=24 + (2 if nid == start else 0),
            status=("NOT_STARTED" if nid != start else "IN_PROGRESS"),
            mastery_ratio=1.0 if nid == start else 0.0,
        )
        mm_nodes.append(n_obj)
        code_to_idx[n_obj.id] = len(mm_nodes) - 1

    links: list[MindMapLink] = []
    for r in rows:
        f, t = int(r["fid"]), int(r["tid"])
        if f in included and t in included:
            a = id_info.get(f, {}).get("code") or f"N{f}"
            b = id_info.get(t, {}).get("code") or f"N{t}"
            links.append(MindMapLink(
                source=a,
                target=b,
                rel_type="PREREQUISITE",
                line_style=dict(LINE_STYLE_BY_REL["PREREQUISITE"]),
            ))

    stats = {
        "node_count": len(mm_nodes),
        "edge_count": len(links),
        "direction": direction,
        "start_kp_code": kp_code,
    }
    title = f"先修链：{kp_code}（{direction}）共 {len(mm_nodes)} 节点 / {len(links)} 边"
    return MindMap(title=title, nodes=mm_nodes, links=links, stats=stats,
                   categories=[{"name": "知识点"}],
                   legend=["PREREQUISITE (先修：源节点必须先于目标节点)"])
