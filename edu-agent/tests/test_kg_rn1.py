# -*- coding: utf-8 -*-
"""R-N1 知识图谱测试（KG-1 幂等同步核心 + KG-2 路径端点，contracts/reshape-r-kg.json draft）。

覆盖（对齐派单验收 GWT）：
- ① graph.py 纯算法离线矩阵：环检测（自环/二环/三环/无环）、BFS 最短路（直达/多跳/
  src==dst/不可达/带环输入终止）、邻域（深度截断/带环终止）、确定性（同输入同输出）
- ② sync_core 纯抽取：norm_text 归一化、build_chunk_graph 关键词打分 + MAX_MENTIONS 封顶
- ③ service 环检测 fail-closed：先修图带环 → 40910（stub driver 离线注入，真实 Neo4j
  数据无环且红线禁写——环注入只发生在测试 stub，不碰真实库）
- ④ 资源缺失精确区分：40460/40461/40462；依赖降级：driver None → 50301（detail 恒 None 脱敏）
- ⑤ 契约一致性：contracts/reshape-r-kg.json draft:true，3 端点与 router 实际注册一致，
  错误码 40460~40462/40910/50301 已注册
- ⑥ Neo4j 真集成（skipif 隔离，**只读**——红线：Neo4j 写仅限 scripts/kg_sync.py）：
  连通 + kg_sync 子图计数>0 + course_path 与 MySQL graph_edge 基线链一致
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.common.error_codes import (
    DEPENDENCY_UNAVAILABLE,
    KG_CHAPTER_NOT_FOUND,
    KG_COURSE_NOT_FOUND,
    KG_NODE_NOT_FOUND,
    KG_PREREQUISITE_CYCLE,
)
from app.common.exceptions import AppException, DependencyUnavailableError
from app.domains.kg import graph as kg_graph
from app.domains.kg import service as kg_service
from app.domains.kg import sync_core as sc

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "reshape-r-kg.json"


# ══════════════════════════════════════════════════════════════
# ① graph.py 纯算法
# ══════════════════════════════════════════════════════════════
class TestFindCycle:
    def test_no_cycle_dag(self):
        edges = [("a", "b"), ("b", "c"), ("a", "c")]
        assert kg_graph.find_cycle(edges) is None

    def test_self_loop(self):
        assert kg_graph.find_cycle([("a", "a")]) == ["a", "a"]

    def test_two_cycle(self):
        assert kg_graph.find_cycle([("a", "b"), ("b", "a")]) == ["a", "b", "a"]

    def test_three_cycle(self):
        edges = [("x", "y"), ("y", "z"), ("z", "x")]
        assert kg_graph.find_cycle(edges) == ["x", "y", "z", "x"]

    def test_cycle_in_larger_dag(self):
        edges = [("s", "a"), ("a", "b"), ("b", "c"), ("c", "a"), ("c", "t")]
        cyc = kg_graph.find_cycle(edges)
        assert cyc is not None and cyc[0] == cyc[-1] and len(cyc) >= 3

    def test_empty(self):
        assert kg_graph.find_cycle([]) is None

    def test_cycle_input_terminates_on_reachable(self):
        # 带环输入下最短路仍终止（visited 兜底，不死循环）
        edges = [("a", "b"), ("b", "a"), ("b", "c")]
        assert kg_graph.shortest_path(edges, "a", "c") == ["a", "b", "c"]


class TestShortestPath:
    def test_direct(self):
        assert kg_graph.shortest_path([("a", "b")], "a", "b") == ["a", "b"]

    def test_multi_hop_prefers_shortest(self):
        edges = [("a", "b"), ("b", "c"), ("c", "d"), ("a", "d")]
        assert kg_graph.shortest_path(edges, "a", "d") == ["a", "d"]

    def test_same_src_dst(self):
        assert kg_graph.shortest_path([("a", "b")], "a", "a") == ["a"]

    def test_unreachable(self):
        assert kg_graph.shortest_path([("a", "b")], "b", "a") is None

    def test_deterministic(self):
        edges = [("a", "b"), ("b", "c"), ("a", "c")]
        assert kg_graph.shortest_path(edges, "a", "c") == kg_graph.shortest_path(edges, "a", "c")


class TestReachableWithin:
    def test_depth_truncation(self):
        edges = [("a", "b"), ("b", "c"), ("c", "d")]
        assert kg_graph.reachable_within(edges, "a", max_depth=1) == {"b": 1}
        assert kg_graph.reachable_within(edges, "a", max_depth=2) == {"b": 1, "c": 2}

    def test_cycle_terminates(self):
        edges = [("a", "b"), ("b", "a")]
        assert kg_graph.reachable_within(edges, "a") == {"b": 1}

    def test_reverse_for_upstream(self):
        # upstream = 沿反向边走 1 跳：(p)->(q) 反向后 q 的邻接含 p
        edges = [("p", "q")]
        assert kg_graph.reachable_within([(b, a) for a, b in edges], "q", max_depth=1) == {"p": 1}


def test_build_adj_dedup_sorted():
    adj = kg_graph.build_adj([("a", "b"), ("a", "b"), ("a", "c")])
    assert adj == {"a": ["b", "c"]}


# ══════════════════════════════════════════════════════════════
# ② sync_core 纯抽取
# ══════════════════════════════════════════════════════════════
def test_norm_text():
    assert sc.norm_text("  变量与\n  类型  ") == "变量与 类型"
    assert sc.norm_text(None) == ""
    assert sc.norm_text("ABC") == "abc"


def test_build_chunk_graph_keyword_scoring_and_cap():
    kps = [
        {"key": "kp:KP-A", "props": {"source": "kg_sync", "code": "KP-A", "name": "变量"}},
        {"key": "kp:KP-B", "props": {"source": "kg_sync", "code": "KP-B", "name": "函数"}},
        {"key": "kp:KP-C", "props": {"source": "kg_sync", "code": "KP-C", "name": "类"}},
        {"key": "kp:KP-D", "props": {"source": "kg_sync", "code": "KP-D", "name": "模块"}},
        {"key": "kp:KP-E", "props": {"source": "kg_sync", "code": "KP-E", "name": "循环"}},
        {"key": "kp:KP-F", "props": {"source": "kg_sync", "code": "KP-F", "name": "字典"}},
        {"key": "kp:KP-G", "props": {"source": "kg_sync", "code": "KP-G", "name": "列表"}},
    ]
    chunks = [
        {
            "chunk_id": "c1",
            "content": "本文讲 变量 与 函数 的用法，类与对象也涉及。未命中知识点：张三李四。",
            "keywords": ["变量", "函数"],
            "tags": [],
            "series_code": "SER-1",
            "module_codes": ["m1"],
        }
    ]
    courses = [{"key": "series:1", "props": {"code": "SER-1"}}]
    chapters = [{"key": "module:m1", "props": {"code": "m1"}}]
    out = sc.build_chunk_graph(chunks, kps, chapters, courses)
    assert out["chunks"][0]["key"] == "chunk:c1"
    # keywords 命中（score=2）排前：变量、函数；正文命中（score=1）：类
    rules = [(m["b"], m["rule"]) for m in out["mentions_chunk"]]
    assert ("kp:KP-A", "keyword_match:2") in rules
    assert ("kp:KP-B", "keyword_match:2") in rules
    assert ("kp:KP-C", "keyword_match:1") in rules
    # 未命中的知识点不产生 MENTIONS
    assert all(b not in {"kp:KP-D", "kp:KP-E", "kp:KP-F", "kp:KP-G"} for b, _ in rules)
    # BELONGS_TO 双挂：series_code → Course，module_codes → Chapter
    assert {"a": "chunk:c1", "b": "series:1"} in out["belongs_chunk_course"]
    assert {"a": "chunk:c1", "b": "module:m1"} in out["belongs_chunk_chapter"]


def test_build_chunk_graph_mentions_capped():
    kps = [
        {"key": f"kp:KP-{i}", "props": {"source": "kg_sync", "code": f"KP-{i}", "name": f"知识点{i}"}}
        for i in range(10)
    ]
    content = " ".join(f"知识点{i}" for i in range(10))
    chunks = [{"chunk_id": "c1", "content": content, "keywords": [], "tags": []}]
    out = sc.build_chunk_graph(chunks, kps, [], [])
    assert len(out["mentions_chunk"]) == sc.MAX_MENTIONS_PER_CHUNK


# ══════════════════════════════════════════════════════════════
# ③④ service：stub driver 离线矩阵（环 40910 / 40460~40462 / 50301 脱敏）
# ══════════════════════════════════════════════════════════════
COURSE_ROW = {"c": {"key": "series:1", "code": "SER-1", "name": "测试课程"}}


def _kp_rows(f: str, t: str) -> list[dict]:
    return [{"code": c} for c in (f, t)]


def _edge_rows(edges: list[tuple[str, str]]) -> list[dict]:
    return [
        {"a_key": f"kp:{a}", "a_code": a, "a_name": f"名{a}", "b_key": f"kp:{b}", "b_code": b, "b_name": f"名{b}"}
        for a, b in edges
    ]


class _FakeResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def data(self) -> list[dict]:
        return self._rows


class _FakeSession:
    def __init__(self, routes: dict[str, Any]):
        self._routes = routes

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *a: Any) -> bool:
        return False

    def run(self, cypher: str, **params: Any) -> _FakeResult:
        for frag, fn in self._routes.items():
            if frag in cypher:
                return _FakeResult(fn(params))
        raise AssertionError(f"stub 未覆盖的 Cypher: {cypher}")


class _FakeDriver:
    def __init__(self, routes: dict[str, Any]):
        self._routes = routes

    def session(self, database: str | None = None) -> _FakeSession:
        return _FakeSession(self._routes)


def _install_driver(monkeypatch: pytest.MonkeyPatch, routes: dict[str, Any]) -> None:
    driver = _FakeDriver(routes)
    monkeypatch.setattr(kg_service, "_get_driver", lambda: driver)


def _base_routes(edges: list[tuple[str, str]], course_hit: bool = True, kp_hit: bool = True) -> dict[str, Any]:
    return {
        "MATCH (c:Course {series_id:$cid})": lambda p: [COURSE_ROW] if course_hit else [],
        "k.code IN [$f, $t]": lambda p: _kp_rows(p["f"], p["t"]) if kp_hit else [],
        "RETURN DISTINCT a.key AS a_key": lambda p: _edge_rows(edges),
    }


def test_service_path_happy(monkeypatch: pytest.MonkeyPatch):
    _install_driver(monkeypatch, _base_routes([("KP-A", "KP-B"), ("KP-B", "KP-C")]))
    data = kg_service.course_path(1, "KP-A", "KP-C")
    assert data.found is True and data.hops == 2 and data.cycle_checked is True
    assert [s.code for s in data.path] == ["KP-A", "KP-B", "KP-C"]
    assert [s.step for s in data.path] == [1, 2, 3]


def test_service_path_unreachable_found_false(monkeypatch: pytest.MonkeyPatch):
    _install_driver(monkeypatch, _base_routes([("KP-A", "KP-B")]))
    data = kg_service.course_path(1, "KP-A", "KP-Z")
    # KP-Z 不在边里 → 知识点存在性已过（stub 返回存在），但图上不可达
    assert data.found is False and data.hops == 0 and data.path == []


def test_service_cycle_fail_closed_40910(monkeypatch: pytest.MonkeyPatch):
    """环检测 fail-closed：真实库无环且红线禁写，环注入仅在 stub 中（离线防御性验证）。"""
    _install_driver(monkeypatch, _base_routes([("KP-A", "KP-B"), ("KP-B", "KP-C"), ("KP-C", "KP-A")]))
    with pytest.raises(AppException) as ei:
        kg_service.course_path(1, "KP-A", "KP-C")
    assert str(ei.value.code) == KG_PREREQUISITE_CYCLE == "40910"
    assert "KP-A" in ei.value.message  # message 含环节点序列（脏数据可定位）


def test_service_self_loop_40910(monkeypatch: pytest.MonkeyPatch):
    _install_driver(monkeypatch, _base_routes([("KP-A", "KP-A")]))
    with pytest.raises(AppException) as ei:
        kg_service.course_path(1, "KP-A", "KP-B")
    assert str(ei.value.code) == "40910"


def test_service_course_not_found_40460(monkeypatch: pytest.MonkeyPatch):
    _install_driver(monkeypatch, _base_routes([], course_hit=False))
    with pytest.raises(AppException) as ei:
        kg_service.course_path(999, "KP-A", "KP-B")
    assert str(ei.value.code) == KG_COURSE_NOT_FOUND == "40460"


def test_service_node_not_found_40462(monkeypatch: pytest.MonkeyPatch):
    routes = _base_routes([("KP-A", "KP-B")])
    routes["k.code IN [$f, $t]"] = lambda p: [{"code": c} for c in (p["f"], p["t"]) if c == "KP-A"]
    _install_driver(monkeypatch, routes)
    with pytest.raises(AppException) as ei:
        kg_service.course_path(1, "KP-A", "KP-MISSING")
    assert str(ei.value.code) == KG_NODE_NOT_FOUND == "40462"


def test_service_chapter_not_found_40461(monkeypatch: pytest.MonkeyPatch):
    routes = {
        "MATCH (ch:Chapter {code:$code})": lambda p: [],
        "RETURN DISTINCT a.key AS a_key": lambda p: [],
    }
    _install_driver(monkeypatch, routes)
    with pytest.raises(AppException) as ei:
        kg_service.chapter_neighbors("__nope__", "upstream")
    assert str(ei.value.code) == KG_CHAPTER_NOT_FOUND == "40461"


def test_service_chapter_neighbors_upstream(monkeypatch: pytest.MonkeyPatch):
    """upstream：本章 MENTIONS q=KP-B，PREREQUISITE p→q ⇒ p=KP-A 入邻接；KP-A 所属其他章节回填。"""
    routes = {
        "MATCH (ch:Chapter {code:$code})": lambda p: [{"ch": {"key": "module:m1", "code": "m1", "name": "章1"}}],
        "MATCH (x)-[:MENTIONS]->(k:KnowledgePoint)": lambda p: [
            {"key": "kp:KP-B", "code": "KP-B", "name": "名B"}
        ],
        "RETURN DISTINCT a.key AS a_key": lambda p: _edge_rows([("KP-A", "KP-B"), ("KP-B", "KP-C")]),
        "MATCH (ch:Chapter)-[:MENTIONS]->(k:KnowledgePoint)": lambda p: [
            {"key": "module:m0", "code": "m0", "name": "章0"},
            {"key": "module:m1", "code": "m1", "name": "章1"},  # 本章自身应被剔除
        ],
    }
    _install_driver(monkeypatch, routes)
    data = kg_service.chapter_neighbors("m1", "upstream")
    assert data.direction == "upstream"
    assert [k.code for k in data.mentioned_kps] == ["KP-B"]
    assert [k.code for k in data.neighbor_kps] == ["KP-A"]  # 上游只取前置，不含下游 KP-C
    assert [c.code for c in data.neighbor_chapters] == ["m0"]  # 本章剔除


def test_service_chapter_neighbors_downstream(monkeypatch: pytest.MonkeyPatch):
    routes = {
        "MATCH (ch:Chapter {code:$code})": lambda p: [{"ch": {"key": "module:m1", "code": "m1", "name": "章1"}}],
        "MATCH (x)-[:MENTIONS]->(k:KnowledgePoint)": lambda p: [
            {"key": "kp:KP-B", "code": "KP-B", "name": "名B"}
        ],
        "RETURN DISTINCT a.key AS a_key": lambda p: _edge_rows([("KP-A", "KP-B"), ("KP-B", "KP-C")]),
        "MATCH (ch:Chapter)-[:MENTIONS]->(k:KnowledgePoint)": lambda p: [],
    }
    _install_driver(monkeypatch, routes)
    data = kg_service.chapter_neighbors("m1", "downstream")
    assert [k.code for k in data.neighbor_kps] == ["KP-C"]  # 下游只取后续，不含前置 KP-A


def test_service_driver_none_50301(monkeypatch: pytest.MonkeyPatch):
    """降级链：driver 未初始化（init 失败/DEBUG 跳过）→ 50301，不 500 不裸抛。"""
    import app.database as db

    monkeypatch.setattr(db, "get_neo4j_driver", lambda: None)
    with pytest.raises(DependencyUnavailableError) as ei:
        kg_service.course_path(1, "KP-A", "KP-B")
    assert str(ei.value.code) == DEPENDENCY_UNAVAILABLE == "50301"
    assert ei.value.http_status == 503
    assert ei.value.detail is None  # 脱敏契约：原始异常不进响应


def test_service_neo4j_error_wrapped_50301(monkeypatch: pytest.MonkeyPatch):
    """运行期 Neo4j 异常（SessionExpired 等）→ logger.exception 全量入日志 + 50301（脱敏）。"""
    class _BoomDriver:
        def session(self, database=None):
            raise RuntimeError("neo4j-bolt-internal 192.168.x.x:7687 cred leak should NOT surface")

    monkeypatch.setattr(kg_service, "_get_driver", lambda: _BoomDriver())
    with pytest.raises(DependencyUnavailableError) as ei:
        kg_service.course_path(1, "KP-A", "KP-B")
    assert str(ei.value.code) == "50301"
    assert "192.168" not in (ei.value.message or "")
    assert ei.value.detail is None


# ══════════════════════════════════════════════════════════════
# ⑤ 契约一致性（draft）
# ══════════════════════════════════════════════════════════════
def test_contract_draft_matches_router():
    assert CONTRACT_PATH.exists(), "contracts/reshape-r-kg.json 缺失"
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["planId"] == "reshape-r-kg"
    assert contract["draft"] is True
    contract_eps = {(e["method"], e["path"]) for e in contract["endpoint_details"]}
    assert contract_eps == {
        ("GET", "/api/kg/course/{course_id}/path"),
        ("GET", "/api/kg/chapter/{chapter_code}/upstream"),
        ("GET", "/api/kg/chapter/{chapter_code}/downstream"),
    }
    from app.domains.kg.router import router

    registered = {(next(iter(r.methods)), r.path) for r in router.routes}
    assert contract_eps <= registered, f"契约端点未全部注册: {contract_eps - registered}"


def test_kg_error_codes_registered():
    assert KG_COURSE_NOT_FOUND == "40460"
    assert KG_CHAPTER_NOT_FOUND == "40461"
    assert KG_NODE_NOT_FOUND == "40462"
    assert KG_PREREQUISITE_CYCLE == "40910"


# ══════════════════════════════════════════════════════════════
# ⑥ Neo4j 真集成（只读；skipif 隔离）
# ══════════════════════════════════════════════════════════════
def _neo4j_up() -> bool:
    try:
        from app.config import settings
        from neo4j import GraphDatabase

        d = GraphDatabase.driver(
            settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            connection_timeout=3.0,
        )
        d.verify_connectivity()
        d.close()
        return True
    except Exception:
        return False


NEO4J_UP = _neo4j_up()
neo4j_needed = pytest.mark.skipif(
    not NEO4J_UP, reason=f"Neo4j {__import__('app.config', fromlist=['settings']).settings.NEO4J_URI} 不可达（skipif 隔离）"
)


@neo4j_needed
def test_live_kg_subgraph_synced():
    """真实库只读断言：kg_sync 子图已落库（两轮幂等实测后的稳态计数）。"""
    from app.config import settings

    driver = kg_service._get_driver()
    counts = sc.kg_counts(driver, settings.NEO4J_DATABASE)
    assert counts["kg"]["node:Course"] >= 1
    assert counts["kg"]["node:KnowledgePoint"] >= 1
    assert counts["kg"]["rel:PREREQUISITE"] >= 1
    assert counts["kg"]["rel:BELONGS_TO"] >= 1


@neo4j_needed
def test_live_path_matches_mysql_baseline():
    """真实库只读断言：MySQL graph_edge 基线链 KP-PY-VAR→…→KP-PY-SQL 共 5 跳。"""
    data = kg_service.course_path(1, "KP-PY-VAR", "KP-PY-SQL")
    assert data.found is True
    assert data.hops == 5
    assert data.cycle_checked is True
    assert [s.code for s in data.path] == [
        "KP-PY-VAR", "KP-PY-CTRL", "KP-PY-FUNC", "KP-PY-OOP", "KP-PY-HTTP", "KP-PY-SQL",
    ]
