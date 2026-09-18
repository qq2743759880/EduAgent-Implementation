# -*- coding: utf-8 -*-
"""R-N2 KG-3 GraphRAG 第四通道 graph_expand 测试（对齐派单验收 5 项）：
- ① 通道融合单元：mock kg 返回邻居 → RRF 并入候选、排序正确、去重不改原分
- ② 降级：kg 超时/熔断/断连/异常 → 通道静默跳过，主链结果与开关关闭逐位一致
- ③ 开关 off → 零开销路径（kg_bridge 零触达断言）
- ④ kg_bridge 查询封装：stub driver 确定性排序/跳数字面量/空实体短路；800ms 预算；RRF 范式
- ⑤ 配置：KG_EXPAND_* 默认值（灰度位默认 False）
- ⑥ 真集成（skipif 隔离，只读红线）：真实 Neo4j MENTIONS/RELATED=0 → 通道产出 0 邻居
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.ai import kg_bridge as kg
from app.auth import UserRole
from app.chat import retriever as R
from app.config import settings as st

RETRIEVE_KW = dict(user_id=1, role=UserRole.STUDENT, use_hyde=False,
                   enable_graph=False, top_k=5, final_max_k=5, cutoff_drop_ratio=1.0)


def _install_milvus_stub(monkeypatch, docs: list[R.RetrievedDoc]):
    monkeypatch.setattr(R, "_milvus_hybrid_search_safe", lambda *a, **k: (docs, None))

    async def _noop_graph(*a, **k):
        return [], None

    async def _passthrough_rerank(q, docs):
        return docs, None

    monkeypatch.setattr(R, "_graph_expand", _noop_graph)
    monkeypatch.setattr(R, "_rerank_docs", _passthrough_rerank)


# ══════════════════════════════════════════════════════════════
# ① 通道融合单元（mock kg 返回邻居 → 融合排序正确）
# ══════════════════════════════════════════════════════════════
class TestGraphExpandFusion:
    async def test_neighbors_fused_with_rrf_order_and_dedup(self, monkeypatch):
        docs_ab = [
            R.RetrievedDoc(doc_id="A", score=0.9, content="a"),
            R.RetrievedDoc(doc_id="B", score=0.8, content="b"),
        ]
        _install_milvus_stub(monkeypatch, docs_ab)
        monkeypatch.setattr(R, "_milvus_fetch_contents", lambda ids: {i: f"content-{i}" for i in ids})

        async def _fake_fetch(chunk_ids, *, hops, timeout_s, max_neighbors):
            assert chunk_ids == ["A", "B"], "种子应为融合候选前 KG_EXPAND_SEED_TOPK 个"
            # n1/n2 新邻居 + "A" 重复（已在候选）→ 不得重复并入
            return kg.KGBridgeResult([("n1", 1), ("n2", 2), ("A", 1)], {"n1": "pv1"}, None)

        monkeypatch.setattr(kg, "fetch_neighbor_chunks", _fake_fetch)
        monkeypatch.setattr(R.settings, "KG_EXPAND_ENABLED", True, raising=False)

        b = await R.retrieve_three_channel("query", **RETRIEVE_KW)
        assert [d.doc_id for d in b.docs] == ["A", "B", "n1", "n2"]
        assert b.raw_retrieved_count == 4
        n1, n2 = b.docs[2], b.docs[3]
        assert n1.source_channel == "graph"
        assert n1.content == "content-n1", "Milvus 回填正文优先于 preview 兜底"
        # RRF 范式：raw=weight/(k+rank) → 归一 (raw+1)/2；rank1 分数必须高于 rank2
        exp_n1 = (0.5 / (60 + 1) + 1.0) / 2.0
        exp_n2 = (0.5 / (60 + 2) + 1.0) / 2.0
        assert abs(n1.score - exp_n1) < 1e-9
        assert abs(n2.score - exp_n2) < 1e-9
        assert n1.score > n2.score
        assert b.degraded_reason is None

    async def test_duplicate_first_does_not_consume_rank(self, monkeypatch):
        """邻居列表首位的重复项不得消耗 RRF rank（新邻居从 rank=1 起算）。"""
        _install_milvus_stub(monkeypatch, [R.RetrievedDoc(doc_id="A", score=0.9, content="a")])
        monkeypatch.setattr(R, "_milvus_fetch_contents", lambda ids: {})

        async def _fake_fetch(chunk_ids, **k):
            return kg.KGBridgeResult([("A", 1), ("n1", 1)], {}, None)

        monkeypatch.setattr(kg, "fetch_neighbor_chunks", _fake_fetch)
        monkeypatch.setattr(R.settings, "KG_EXPAND_ENABLED", True, raising=False)

        b = await R.retrieve_three_channel("query", **RETRIEVE_KW)
        n1 = b.docs[1]
        exp = (0.5 / (60 + 1) + 1.0) / 2.0
        assert [d.doc_id for d in b.docs] == ["A", "n1"]
        assert abs(n1.score - exp) < 1e-9, "重复项跳过不计 rank"
        assert n1.content == "", "回填与 preview 均缺 → 空正文（降级留痕由 preview 字典为空体现）"

    async def test_preview_fallback_when_hydration_empty(self, monkeypatch):
        _install_milvus_stub(monkeypatch, [R.RetrievedDoc(doc_id="A", score=0.9, content="a")])
        monkeypatch.setattr(R, "_milvus_fetch_contents", lambda ids: {})

        async def _fake_fetch(chunk_ids, **k):
            return kg.KGBridgeResult([("n1", 2)], {"n1": "preview-120"}, None)

        monkeypatch.setattr(kg, "fetch_neighbor_chunks", _fake_fetch)
        monkeypatch.setattr(R.settings, "KG_EXPAND_ENABLED", True, raising=False)

        b = await R.retrieve_three_channel("query", **RETRIEVE_KW)
        assert b.docs[1].content == "preview-120"


# ══════════════════════════════════════════════════════════════
# ② 降级：kg 超时 → 通道跳过，主链与开关关闭逐位一致
# ══════════════════════════════════════════════════════════════
class TestGraphExpandDegrade:
    async def test_kg_timeout_skips_channel_result_identical_to_off(self, monkeypatch):
        docs_ab = [
            R.RetrievedDoc(doc_id="A", score=0.9, content="a"),
            R.RetrievedDoc(doc_id="B", score=0.8, content="b"),
        ]
        _install_milvus_stub(monkeypatch, docs_ab)
        monkeypatch.setattr(R.settings, "KG_EXPAND_ENABLED", False, raising=False)
        b_off = await R.retrieve_three_channel("query", **RETRIEVE_KW)

        monkeypatch.setattr(R.settings, "KG_EXPAND_ENABLED", True, raising=False)

        async def _timeout_fetch(chunk_ids, **k):
            return kg.KGBridgeResult([], {}, "kg_expand:timeout(0.8s)")

        monkeypatch.setattr(kg, "fetch_neighbor_chunks", _timeout_fetch)
        b_on = await R.retrieve_three_channel("query", **RETRIEVE_KW)

        assert [d.doc_id for d in b_on.docs] == [d.doc_id for d in b_off.docs] == ["A", "B"]
        assert b_off.degraded_reason is None
        assert "kg_expand:timeout" in (b_on.degraded_reason or ""), "降级原因必须留痕"

    async def test_kg_empty_neighbors_zero_divergence(self, monkeypatch):
        """通道开启但图上无邻居（当前 MENTIONS/RELATED=0 的真实形态）→ 结果与 off 逐位一致。"""
        docs_ab = [R.RetrievedDoc(doc_id="A", score=0.9, content="a")]
        _install_milvus_stub(monkeypatch, docs_ab)

        async def _empty_fetch(chunk_ids, **k):
            return kg.KGBridgeResult([], {}, None)

        monkeypatch.setattr(kg, "fetch_neighbor_chunks", _empty_fetch)
        monkeypatch.setattr(R.settings, "KG_EXPAND_ENABLED", True, raising=False)
        b_on = await R.retrieve_three_channel("query", **RETRIEVE_KW)
        monkeypatch.setattr(R.settings, "KG_EXPAND_ENABLED", False, raising=False)
        b_off = await R.retrieve_three_channel("query", **RETRIEVE_KW)

        assert [d.doc_id for d in b_on.docs] == [d.doc_id for d in b_off.docs] == ["A"]
        assert [d.score for d in b_on.docs] == [d.score for d in b_off.docs]
        assert b_on.raw_retrieved_count == b_off.raw_retrieved_count
        assert b_on.degraded_reason is None


# ══════════════════════════════════════════════════════════════
# ③ 开关 off → 零开销路径
# ══════════════════════════════════════════════════════════════
class TestSwitchOffZeroOverhead:
    async def test_off_never_touches_kg_bridge(self, monkeypatch):
        assert st.KG_EXPAND_ENABLED is False, "灰度位默认必须关闭"

        def _boom(*a, **k):
            raise AssertionError("开关关闭时不得触达 kg_bridge / Milvus 回填")

        _install_milvus_stub(monkeypatch, [R.RetrievedDoc(doc_id="A", score=0.9, content="a")])
        monkeypatch.setattr(kg, "fetch_neighbor_chunks", _boom)
        monkeypatch.setattr(R, "_milvus_fetch_contents", _boom)
        # 显式关闭（不依赖默认值，防 .env 灰度翻转污染单测）
        monkeypatch.setattr(R.settings, "KG_EXPAND_ENABLED", False, raising=False)

        b = await R.retrieve_three_channel("query", **RETRIEVE_KW)
        assert [d.doc_id for d in b.docs] == ["A"]
        assert b.degraded_reason is None

    async def test_empty_candidates_zero_overhead_even_when_on(self, monkeypatch):
        """开启但候选为空 → 不触达 kg_bridge（empty_seeds 结构性零开销）。"""
        _install_milvus_stub(monkeypatch, [])
        monkeypatch.setattr(R.settings, "KG_EXPAND_ENABLED", True, raising=False)

        def _boom(*a, **k):
            raise AssertionError("候选为空时不得触达 kg_bridge")

        monkeypatch.setattr(kg, "fetch_neighbor_chunks", _boom)
        b = await R.retrieve_three_channel("query", **RETRIEVE_KW)
        assert b.docs == []


# ══════════════════════════════════════════════════════════════
# ④ kg_bridge 查询封装
# ══════════════════════════════════════════════════════════════
class _FakeResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def single(self):
        return self._rows[0] if self._rows else None

    def data(self):
        return self._rows


class _FakeSession:
    def __init__(self, seed_rows: list[dict], expand_rows: list[dict], log: list):
        self._seed_rows, self._expand_rows, self._log = seed_rows, expand_rows, log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def run(self, cypher: str, **kw):
        self._log.append((cypher, kw))
        if "ents" in cypher:
            return _FakeResult(self._seed_rows)
        return _FakeResult(self._expand_rows)


class TestRunQueries:
    def _driver(self, seed_rows, expand_rows, log):
        sess = _FakeSession(seed_rows, expand_rows, log)

        class _D:
            def session(self, database=None):
                return sess

        return _D()

    def test_deterministic_order_and_preview(self):
        log: list = []
        seed = [{"ents": [{"key": "kp:B"}, None, {"key": "kp:A"}, {"key": "kp:A"}]}]
        expand = [
            {"chunk_id": "n2", "hops": 2, "preview": "p2"},
            {"chunk_id": "n1", "hops": 1, "preview": "p1"},
            {"chunk_id": "", "hops": 1, "preview": "x"},  # 空 id 过滤
            {"chunk_id": "n3", "hops": 1, "preview": None},
        ]
        out = kg._run_queries(self._driver(seed, expand, log), "neo4j", ["c1"], hops=2, max_neighbors=30)
        assert out == [("n1", 1, "p1"), ("n3", 1, None), ("n2", 2, "p2")]
        assert len(log) == 2, "两段 Cypher：种子实体 + 邻居扩展"
        seed_kw, expand_kw = log[0][1], log[1][1]
        assert seed_kw["ids"] == ["c1"] and seed_kw["src"] == "kg_sync"
        assert expand_kw["keys"] == ["kp:A", "kp:B"], "实体 key 去重 + 排序（确定性）"
        assert "*1..2" in log[1][0], "跳数字面量插入"
        assert " LIMIT 30" in log[1][0]

    def test_hops_literal_configurable(self):
        log: list = []
        kg._run_queries(self._driver([{"ents": [{"key": "kp:A"}]}], [], log), None, ["c"], hops=3, max_neighbors=5)
        assert "*1..3" in log[1][0] and " LIMIT 5" in log[1][0]

    def test_empty_seed_entities_short_circuits_expand(self):
        log: list = []
        out = kg._run_queries(self._driver([{"ents": []}], [], log), None, ["c1"])
        assert out == []
        assert len(log) == 1, "无种子实体 → 不执行扩展查询"

    def test_limit_truncation(self):
        log: list = []
        expand = [{"chunk_id": f"n{i}", "hops": 1, "preview": None} for i in range(5)]
        out = kg._run_queries(self._driver([{"ents": [{"key": "kp:A"}]}], expand, log), None, ["c"], max_neighbors=2)
        assert [x[0] for x in out] == ["n0", "n1"]


class TestFetchNeighborChunks:
    async def test_empty_seeds(self):
        r = await kg.fetch_neighbor_chunks([])
        assert r.neighbors == [] and r.previews == {}
        assert r.degraded_reason == "kg_expand:empty_seeds"

    async def test_driver_not_connected(self, monkeypatch):
        import app.database as db

        monkeypatch.setattr(db, "get_neo4j_driver", lambda: None)
        r = await kg.fetch_neighbor_chunks(["c1"])
        assert r.degraded_reason == "kg_expand:neo4j_not_connected"
        assert r.neighbors == []

    async def test_breaker_open_fast_fail(self, monkeypatch):
        import app.core.db_resilience as res
        import app.database as db

        monkeypatch.setattr(db, "get_neo4j_driver", lambda: object())

        async def _open(op_name, fn):
            raise res.DependencyUnavailableError("breaker open")

        monkeypatch.setattr(res, "neo4j_run", _open)
        r = await kg.fetch_neighbor_chunks(["c1"])
        assert r.degraded_reason == "kg_expand:neo4j_breaker_open"

    async def test_timeout_budget_enforced(self, monkeypatch):
        import app.core.db_resilience as res
        import app.database as db

        monkeypatch.setattr(db, "get_neo4j_driver", lambda: object())

        async def _slow(op_name, fn):
            await asyncio.sleep(1.0)

        monkeypatch.setattr(res, "neo4j_run", _slow)
        t0 = time.perf_counter()
        r = await kg.fetch_neighbor_chunks(["c1"], timeout_s=0.1)
        elapsed = time.perf_counter() - t0
        assert r.degraded_reason == "kg_expand:timeout(0.1s)"
        assert r.neighbors == []
        assert elapsed < 0.9, "800ms 预算内必须放弃（不拖垮检索主链）"

    async def test_driver_init_hang_respects_budget(self, monkeypatch):
        """driver 懒初始化（同步阻塞）挂在预算内被放弃：线程执行 + wait_for 硬顶，
        不得阻塞事件循环超预算（P1-4 同类教训的回归防线）。"""
        import time as _time

        import app.database as db

        def _hanging_init():
            _time.sleep(2.0)
            return object()

        monkeypatch.setattr(db, "get_neo4j_driver", _hanging_init)
        t0 = time.perf_counter()
        r = await kg.fetch_neighbor_chunks(["c1"], timeout_s=0.1)
        elapsed = time.perf_counter() - t0
        assert r.degraded_reason == "kg_expand:timeout(0.1s)"
        assert r.neighbors == []
        assert elapsed < 0.9, "同步 driver 初始化挂起必须在预算内放弃"

    async def test_generic_exception_swallowed(self, monkeypatch):
        import app.core.db_resilience as res
        import app.database as db

        monkeypatch.setattr(db, "get_neo4j_driver", lambda: object())

        async def _boom(op_name, fn):
            raise RuntimeError("boom")

        monkeypatch.setattr(res, "neo4j_run", _boom)
        r = await kg.fetch_neighbor_chunks(["c1"])
        assert r.degraded_reason == "kg_expand:RuntimeError"

    async def test_success_maps_previews(self, monkeypatch):
        import app.core.db_resilience as res
        import app.database as db

        sess = _FakeSession(
            [{"ents": [{"key": "kp:A"}]}],
            [{"chunk_id": "n1", "hops": 1, "preview": "pv1"},
             {"chunk_id": "n2", "hops": 2, "preview": None}],
            [],
        )

        class _D:
            def session(self, database=None):
                return sess

        monkeypatch.setattr(db, "get_neo4j_driver", lambda: _D())

        async def _ok(op_name, fn):
            return fn()  # 真实 neo4j_run = to_thread(fn)：stub 直接执行注入的 _do_all

        monkeypatch.setattr(res, "neo4j_run", _ok)
        r = await kg.fetch_neighbor_chunks(["c1"])
        assert r.neighbors == [("n1", 1), ("n2", 2)]
        assert r.previews == {"n1": "pv1"}
        assert r.degraded_reason is None


def test_rrf_channel_score_paradigm():
    s1 = kg.rrf_channel_score(1, weight=0.5, k=60)
    s2 = kg.rrf_channel_score(2, weight=0.5, k=60)
    assert s1 == pytest.approx(0.5 / 61)
    assert s2 == pytest.approx(0.5 / 62)
    assert s1 > s2, "通道内 rank 越小 RRF 分越高"
    assert kg.rrf_channel_score(0, weight=0.5, k=60) == s1, "rank<1 钳位到 1"
    assert kg.rrf_channel_score(1, weight=1.0, k=60) == pytest.approx(2 * s1), "通道权重为线性乘子（配置化）"


# ══════════════════════════════════════════════════════════════
# ⑤ 配置默认值（灰度位）
# ══════════════════════════════════════════════════════════════
def test_config_defaults_gray_off():
    assert st.KG_EXPAND_ENABLED is False, "默认灰度关闭（双跑对账后由编排者裁定）"
    assert st.KG_EXPAND_SEED_TOPK == 10
    assert st.KG_EXPAND_HOPS == 2
    assert st.KG_EXPAND_TIMEOUT_MS == 800
    assert st.KG_EXPAND_MAX_NEIGHBORS == 30
    assert st.KG_EXPAND_RRF_K == 60, "与 Milvus RRFRanker(k=60) 同范式"
    assert st.KG_EXPAND_RRF_WEIGHT == 0.5


# ══════════════════════════════════════════════════════════════
# ⑥ 真集成（只读红线）：真实 Neo4j 当前 MENTIONS=0 → 通道产出 0 邻居
# ══════════════════════════════════════════════════════════════
def _neo4j_probe_driver() -> Any | None:
    try:
        from neo4j import GraphDatabase

        d = GraphDatabase.driver(st.NEO4J_URI, auth=(st.NEO4J_USER, st.NEO4J_PASSWORD))
        d.verify_connectivity()
        return d
    except Exception:
        return None


_NEO4J_DRIVER = _neo4j_probe_driver()


@pytest.mark.skipif(_NEO4J_DRIVER is None, reason="Neo4j 不可达（离线环境跳过）")
class TestRealNeo4jReadOnly:
    async def test_zero_mentions_yields_zero_neighbors(self):
        """真实 kg_sync 子图（4292 节点，MENTIONS=0）→ 通道产出 0 邻居 = 预期零增益。"""
        with _NEO4J_DRIVER.session(database=st.NEO4J_DATABASE) as s:
            seed_ids = [
                str(r["chunk_id"])
                for r in s.run(
                    "MATCH (n:DocChunk {source:'kg_sync'}) WHERE n.chunk_id IS NOT NULL "
                    "RETURN n.chunk_id AS chunk_id LIMIT 5"
                )
            ]
        assert seed_ids, "真实子图应有 DocChunk 种子"
        r = await kg.fetch_neighbor_chunks(seed_ids, hops=2, timeout_s=5.0, max_neighbors=30)
        assert r.degraded_reason is None, f"真实 Neo4j 可达时不得降级：{r.degraded_reason}"
        assert r.neighbors == [], "MENTIONS/RELATED=0 → 图扩展邻居必须为 0（零增益预期）"

    async def test_bridge_never_writes(self):
        """只读红线自证：桥接两段 Cypher 均无写子句。"""
        for cypher in (kg._SEED_ENTITY_CYPHER, kg._EXPAND_CYPHER):
            assert "MERGE" not in cypher and "CREATE" not in cypher and "DELETE" not in cypher
            assert "SET " not in cypher
