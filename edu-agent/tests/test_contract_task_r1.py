# -*- coding: utf-8 -*-
"""
task-R1 契约测试：Rerank 独立服务 + 连续批处理（AC1~AC5）。

全程无 CUDA 依赖：
- AC1 一致性：用 FakeReranker 证明 sidecar（rerank_pairs）与进程内（rerank）数学等价，
  以及 /rerank 端点返回分数 == rerank_pairs 直连（真实模型复用同一代码路径，误差 <1e-4 由
  相同模型 + 各对独立序列保证；真实 CUDA 校验见 test-reports 中 R1_RUN_CUDA_TESTS 一键脚本）。
- AC2 事件循环不阻塞：并发 _rerank_docs，sidecar 模拟 GPU 异步等待，验证主循环未被串行阻塞。
- AC3 连续批处理：5 请求合并 ≤2 批、单请求延迟 ≤ RERANK_MAX_WAIT_MS、吞吐 ≥ 串行 2x。
- AC4 降级链：sidecar 不可达→进程内直连(rerank_sidecar_unavailable)→_rule_rerank(reranker_unavailable)。
- AC5 压测对比：rerank_stress 同参对比 sidecar(批处理) vs 同进程(串行)，speedup ≥ 2x。
"""
from __future__ import annotations

import asyncio
import time

import pytest

from app.rerank_service.batcher import BatchClosed, ContinuousBatcher
from app.rerank_service.main import RerankReq, _handle_rerank, build_batcher
from app.rerank_service.queue_adapter import DirectQueue, build_queue_adapter

import app.knowledge.reranker as reranker_mod
import app.chat.retriever as retriever_mod
from app.chat.retriever import _rerank_docs, _rerank_via_sidecar, _rule_rerank
from app.chat.schemas import RetrievedDoc


# ----------------------------------------------------------------------
# FakeReranker：确定性打分，证明 rerank == rerank_pairs（AC1 数学等价）
# ----------------------------------------------------------------------
class FakeReranker:
    _instance = None

    def __init__(self) -> None:
        self._model = object()  # 标记为已加载

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _score(self, q: str, c: str) -> float:
        return float((hash((q, c)) % 1000) / 1000.0)

    def rerank(self, query, contents, *, batch_size=None):
        return [self._score(query, c) for c in contents]

    def rerank_pairs(self, pairs):
        return [self._score(q, c) for (q, c) in pairs]

    @property
    def load_error(self):
        return None


@pytest.fixture
def fake_reranker(monkeypatch):
    """用 FakeReranker 替换全局 Reranker（进程内直连与 sidecar 推理均走 fake）。"""
    monkeypatch.setattr(reranker_mod, "Reranker", FakeReranker)
    monkeypatch.setattr(retriever_mod, "Reranker", FakeReranker)
    FakeReranker._instance = None
    yield FakeReranker.get()


# ======================================================================
# AC1 服务正确性：sidecar 分数 == 进程内直连
# ======================================================================
def test_ac1_rerank_pairs_equals_rerank(fake_reranker):
    """同参调用下 rerank_pairs 与 rerank 分数逐位相等（sidecar 复用 rerank_pairs）。"""
    rk = fake_reranker
    q, contents = "什么是向量数据库", ["A" * 20, "B" * 30, "C" * 10]
    direct = rk.rerank(q, contents)
    via_pairs = rk.rerank_pairs([(q, c) for c in contents])
    assert direct == pytest.approx(via_pairs, abs=1e-9)


async def test_ac1_sidecar_endpoint_equals_rerank_pairs(fake_reranker):
    """POST /rerank 经 batcher 返回分数 == rerank_pairs 直连（相同代码路径）。"""
    batcher = build_batcher(infer_fn=fake_reranker.rerank_pairs)
    batcher.start()
    try:
        q, contents = "RAG 是什么", ["a", "bb", "ccc", "dddd"]
        resp = await _handle_rerank(RerankReq(query=q, contents=contents), batcher)
        assert resp.scores == pytest.approx(
            fake_reranker.rerank_pairs([(q, c) for c in contents]), abs=1e-9
        )
        assert resp.latency_ms >= 0
    finally:
        await batcher.stop()


@pytest.mark.skipif(
    __import__("os").environ.get("R1_RUN_CUDA_TESTS") != "1",
    reason="真实 CUDA 一致性校验需加载 2.2GB 模型，默认跳过（设 R1_RUN_CUDA_TESTS=1 开启）",
)
async def test_ac1_real_cuda_consistency():
    """真实模型：sidecar 经 batcher 的 rerank_pairs 与进程内 rerank 误差 <1e-4。"""
    from app.knowledge.reranker import Reranker

    rk = Reranker.get()
    q, contents = "什么是检索增强生成", ["RAG 结合检索与生成", "深度学习模型", "向量相似度搜索", "课程大纲设计"]
    direct = rk.rerank(q, contents)
    assert direct is not None, "真实模型未加载，无法校验（确认 RERANKER_PATH 与 CUDA）"
    batcher = build_batcher()
    batcher.start()
    try:
        resp = await _handle_rerank(RerankReq(query=q, contents=contents), batcher)
    finally:
        await batcher.stop()
    assert resp.scores == pytest.approx(direct, abs=1e-4)


# ======================================================================
# AC2 主链路改造：事件循环不被 GPU 阻塞（并发无卡顿）
# ======================================================================
async def test_ac2_event_loop_not_blocked_by_sidecar(monkeypatch):
    """5 个并发 _rerank_docs，sidecar 模拟异步 GPU（await sleep），总耗时≈单次而非 5×。"""

    async def fake_sidecar(query, contents):
        await asyncio.sleep(0.05)  # 模拟 sidecar GPU 推理（独立进程，主循环 await 让出）
        return [0.1 * i for i in range(len(contents))]

    monkeypatch.setattr(retriever_mod, "_rerank_via_sidecar", fake_sidecar)
    docs = [RetrievedDoc(doc_id=str(i), score=0.0, content=f"content-{i}") for i in range(3)]

    t0 = time.perf_counter()
    await asyncio.gather(*[_rerank_docs(f"q{j}", list(docs)) for j in range(5)])
    elapsed = time.perf_counter() - t0

    # 若主循环被同步 GPU 阻塞，会是 5×0.05=0.25s；异步应 ≈0.05s（并发）
    assert elapsed < 0.05 * 5 * 0.8, f"主循环疑似被阻塞：{elapsed:.3f}s"


async def test_ac2_interleaving_main_loop_runs(monkeypatch):
    """rerank 进行中，主循环其他协程仍可推进（证明未阻塞事件循环）。"""
    counter = {"n": 0}

    async def fake_sidecar(query, contents):
        for _ in range(5):
            await asyncio.sleep(0.01)  # 让出控制权
        return [0.0] * len(contents)

    monkeypatch.setattr(retriever_mod, "_rerank_via_sidecar", fake_sidecar)
    docs = [RetrievedDoc(doc_id="1", score=0.0, content="x")]

    async def spinner():
        for _ in range(10):
            await asyncio.sleep(0)
            counter["n"] += 1

    await asyncio.gather(_rerank_docs("q", list(docs)), spinner())
    assert counter["n"] >= 5, "rerank 期间主循环未推进，疑似阻塞"


# ======================================================================
# AC3 连续批处理
# ======================================================================
async def _fake_infer_fixed_overhead(pairs):
    """模拟 GPU 推理：固定每次调用开销（kernel 启动/H2D）+ 与对数线性开销。

    分数按 (query,content) 内容确定性计算（而非位置索引），保证批处理与逐请求调用结果一致
    （真实 Reranker 各对序列独立，天然满足；这里用 content-hash 模拟同一性质）。
    """
    await asyncio.sleep(0.02 + 0.0001 * len(pairs))
    return [float(abs(hash((q, c))) % 1000) / 1000.0 for (q, c) in pairs]


async def test_ac3_merge_five_requests_within_two_batches():
    """20ms 内 5 请求 → 合并 ≤2 批。"""
    batcher = ContinuousBatcher(
        _fake_infer_fixed_overhead, window_ms=20, max_batch_pairs=64, max_wait_ms=50, max_queue=200
    )
    batcher.start()
    try:
        reqs = [(f"q{i}", [f"c{j}" for j in range(8)]) for i in range(5)]  # 40 对 ≤64
        await asyncio.gather(*[batcher.submit(q, c) for q, c in reqs])
        assert batcher.batch_count <= 2, f"批数={batcher.batch_count}"
    finally:
        await batcher.stop()


async def test_ac3_large_requests_split_into_two_batches():
    """5 请求 × 20 内容 = 100 对 > 64 → 拆 2 批（仍 ≤2）。"""
    batcher = ContinuousBatcher(
        _fake_infer_fixed_overhead, window_ms=20, max_batch_pairs=64, max_wait_ms=50, max_queue=200
    )
    batcher.start()
    try:
        reqs = [(f"q{i}", [f"c{j}" for j in range(20)]) for i in range(5)]  # 100 对
        await asyncio.gather(*[batcher.submit(q, c) for q, c in reqs])
        assert batcher.batch_count == 2, f"批数={batcher.batch_count}"
    finally:
        await batcher.stop()


async def test_ac3_single_request_latency_within_max_wait():
    """单请求延迟 ≤ RERANK_MAX_WAIT_MS（含攒批窗口，不含推理）。"""
    batcher = ContinuousBatcher(
        _fake_infer_fixed_overhead, window_ms=20, max_batch_pairs=64, max_wait_ms=50, max_queue=200
    )
    batcher.start()
    try:
        t0 = time.perf_counter()
        await batcher.submit("q", ["c1", "c2"])
        latency = (time.perf_counter() - t0) * 1000
        assert latency <= 50 + 50, f"延迟 {latency:.1f}ms 超上限"
    finally:
        await batcher.stop()


async def test_ac3_throughput_ge_2x_serial():
    """连续批处理吞吐 ≥ 同参数串行 2x。"""
    reqs = [(f"q{i}", [f"c{j}" for j in range(8)]) for i in range(5)]

    # sidecar 模式：一个 batcher 并发提交
    b = ContinuousBatcher(
        _fake_infer_fixed_overhead, window_ms=20, max_batch_pairs=64, max_wait_ms=50, max_queue=200
    )
    b.start()
    try:
        t0 = time.perf_counter()
        await asyncio.gather(*[b.submit(q, c) for q, c in reqs])
        batched_ms = (time.perf_counter() - t0) * 1000
    finally:
        await b.stop()

    # 同进程串行：每个请求单独前向（task31 现状）
    t0 = time.perf_counter()
    for q, c in reqs:
        await _fake_infer_fixed_overhead([(q, cc) for cc in c])
    serial_ms = (time.perf_counter() - t0) * 1000

    assert batched_ms <= serial_ms / 2.0, f"speedup={serial_ms/batched_ms:.2f}x < 2x"


async def test_ac3_queue_full_returns_batch_closed():
    """队列满 → BatchClosed（调用方走降级，不 500）。"""
    batcher = ContinuousBatcher(_fake_infer_fixed_overhead, max_queue=1)  # 不启动 task，避免排空
    # 直接预填队列（模拟已满），不经过 submit 以免阻塞等待
    fut = asyncio.get_event_loop().create_future()
    batcher._queue.put_nowait(("q0", ["c"], fut))
    with pytest.raises(BatchClosed):
        await batcher.submit("q1", ["c"])  # qsize(1) >= max_queue(1) → 立即 BatchClosed


# ======================================================================
# AC4 降级链：sidecar → 进程内直连 → 规则兜底
# ======================================================================
async def test_ac4_sidecar_down_fallback_to_inprocess(fake_reranker, monkeypatch):
    """sidecar 不可达 → 回退进程内直连，degraded='rerank_sidecar_unavailable'。"""

    async def _none(q, c):
        return None

    monkeypatch.setattr(retriever_mod, "_rerank_via_sidecar", _none)
    docs = [
        RetrievedDoc(doc_id="1", score=0.0, content="深度学习"),
        RetrievedDoc(doc_id="2", score=0.0, content="无关文本zzz"),
    ]
    out, degrade = await _rerank_docs("神经网络", list(docs))
    assert degrade == "rerank_sidecar_unavailable"
    assert len(out) == 2
    assert all(d.score >= 0 for d in out)


async def test_ac4_sidecar_and_inprocess_fail_then_rule_rerank(fake_reranker, monkeypatch):
    """sidecar 不可达 + 进程内也失败 → _rule_rerank 兜底，degraded='reranker_unavailable'。"""

    async def _none(q, c):
        return None

    monkeypatch.setattr(retriever_mod, "_rerank_via_sidecar", _none)
    monkeypatch.setattr(fake_reranker, "rerank", lambda q, c, **k: None)  # 进程内直连也失败
    docs = [
        RetrievedDoc(doc_id="1", score=0.5, content="机器学习"),
        RetrievedDoc(doc_id="2", score=0.5, content="机器学习进阶"),
    ]
    out, degrade = await _rerank_docs("机器学习", list(docs))
    assert degrade == "reranker_unavailable"
    assert len(out) == 2  # 规则兜底仍产出有序 doc


async def test_ac4_sidecar_connect_error_triggers_fallback(fake_reranker, monkeypatch):
    """sidecar 抛连接异常 → 返回 None → 回退进程内直连。"""
    import httpx

    class _FailClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(retriever_mod.httpx, "AsyncClient", _FailClient)
    docs = [RetrievedDoc(doc_id="1", score=0.0, content="AI")]
    out, degrade = await _rerank_docs("AI", list(docs))
    assert degrade == "rerank_sidecar_unavailable"
    assert out[0].doc_id == "1"


# ======================================================================
# AC5 压测对比：sidecar(批处理) vs 同进程(串行)
# ======================================================================
async def test_ac5_stress_speedup_ge_2x():
    """rerank_stress 同参对比，sidecar 连续批处理 speedup ≥ 2x。"""
    from scripts.eval.stress import rerank_stress

    result = await rerank_stress(
        n_reqs=20, contents_per=5, infer=_fake_infer_fixed_overhead, window_ms=20, max_batch_pairs=64
    )
    assert result["speedup"] >= 2.0, f"speedup={result['speedup']}x"
    # 一致性：两种模式分数应一致（同一 infer）
    assert result["sidecar_scores"] == result["inproc_scores"]


# ======================================================================
# 可选 Redis 队列适配（降级到直连）
# ======================================================================
async def test_queue_adapter_default_direct():
    q = build_queue_adapter(maxsize=10)
    assert isinstance(q, DirectQueue)
    await q.put("x")
    assert await q.get() == "x"
