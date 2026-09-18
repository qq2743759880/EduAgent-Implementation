# -*- coding: utf-8 -*-
"""KG 纯图算法（R-N1，KG-2 环检测/最短路/邻域）。

设计约束：
- 纯函数、零 I/O、零框架依赖——可离线单测（tests/test_kg_rn1.py 离线矩阵）。
- 节点统一用 key（kg_sync 写入 Neo4j 的唯一键，如 `kp:KP-xxx`）。
- 全部遍历显式 visited/color 集合——即使上游脏数据带环也不会死循环（防御性兜底，
  契约层环检测见 service.check_prereq_cycle → 40910 KG_PREREQUISITE_CYCLE）。
- 确定性：邻接表构建后排序，同输入同输出（幂等同步/对账可复现）。
"""
from __future__ import annotations

from collections import defaultdict, deque

Edges = list[tuple[str, str]]  # (from_key, to_key) 有向边


def build_adj(edges: Edges) -> dict[str, list[str]]:
    """有向邻接表（from → [to,...]，去重 + 排序，确定性）。"""
    adj: dict[str, list[str]] = defaultdict(list)
    for a, b in edges:
        if b not in adj[a]:
            adj[a].append(b)
    for k in adj:
        adj[k] = sorted(adj[k])
    return dict(adj)


def find_cycle(edges: Edges) -> list[str] | None:
    """有向图环检测（迭代式 DFS 三色标记），返回环路径（如 [A,B,C,A]）或 None。

    - 自环 (A,A) → [A, A]。
    - 节点遍历顺序按 key 排序，结果确定性；显式 (节点, 迭代器) 栈避免递归爆栈。
    """
    adj = build_adj(edges)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in adj}
    parent: dict[str, str | None] = {}

    for root in sorted(adj):
        if color[root] != WHITE:
            continue
        color[root] = GRAY
        parent[root] = None
        stack: list[tuple[str, object]] = [(root, iter(adj[root]))]
        while stack:
            node, it = stack[-1]
            descended = False
            for nxt in it:  # 从上次消费位置继续（迭代器挂在栈帧上）
                st = color.get(nxt, WHITE)
                if st == GRAY:
                    if nxt == node:
                        return [node, node]  # 自环
                    # 回溯 DFS 树 parent 链：node → ... → nxt（GRAY=当前路径上的祖先）
                    cycle = [node]
                    cur = parent.get(node)
                    while cur is not None and cur != nxt:
                        cycle.append(cur)
                        cur = parent.get(cur)
                    if cur == nxt:
                        cycle.append(nxt)
                        cycle.reverse()
                        return cycle
                    # parent 链兜底（理论不可达）：给最小环表达
                    return [nxt, node, nxt]
                if st == WHITE:
                    color[nxt] = GRAY
                    parent[nxt] = node
                    stack.append((nxt, iter(adj.get(nxt, []))))
                    descended = True
                    break
                # st == BLACK：已完成，继续消费迭代器
            if not descended:
                stack.pop()
                color[node] = BLACK
    return None


def shortest_path(edges: Edges, src: str, dst: str) -> list[str] | None:
    """BFS 最短路（边数最少），返回节点 key 序列（含首尾）或 None（不可达）。

    src == dst 时返回 [src]。visited 集合保证带环输入也终止。
    """
    if src == dst:
        return [src]
    adj = build_adj(edges)
    prev: dict[str, str] = {}
    visited = {src}
    q: deque[str] = deque([src])
    while q:
        cur = q.popleft()
        for nxt in adj.get(cur, []):
            if nxt in visited:
                continue
            visited.add(nxt)
            prev[nxt] = cur
            if nxt == dst:
                path = [dst]
                while path[-1] != src:
                    path.append(prev[path[-1]])
                path.reverse()
                return path
            q.append(nxt)
    return None


def reachable_within(edges: Edges, start: str, max_depth: int = 10) -> dict[str, int]:
    """BFS 邻域：start 沿有向边可达的节点 → 最小跳数（不含 start 自身）。

    max_depth 截断防止大图扩散；visited 保证带环输入终止。
    """
    adj = build_adj(edges)
    depth: dict[str, int] = {}
    visited = {start}
    q: deque[tuple[str, int]] = deque([(start, 0)])
    while q:
        cur, d = q.popleft()
        if d >= max_depth:
            continue
        for nxt in adj.get(cur, []):
            if nxt in visited:
                continue
            visited.add(nxt)
            depth[nxt] = d + 1
            q.append((nxt, d + 1))
    return depth
