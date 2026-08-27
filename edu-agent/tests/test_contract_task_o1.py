# -*- coding: utf-8 -*-
"""task-O1 契约测试（production-upgrade-plan P8 观测性基座）。

覆盖 AC1~AC5：
- AC1 trace 贯穿：一次完整问答（记忆召回+LLM+工具+压缩）按 trace_id 查全部事件，可还原归因
- AC2 5 维指标：记忆命中率/压缩效率/工具成功率/缓存命中率/排队超时率，计数+比例+可溯源
- AC3 OTel 导出：空端点 → JSONL 落盘（schema 正确）；配置端点 → OTLP HTTP，失败降级 JSONL
- AC4 会话级 trace：同一会话 3 次请求共用同一 trace_id，span_id 各异
- AC5 回归：既有 X-Trace-Id 响应头仍携带 trace_id（会话级下携带会话 trace_id）
"""
from __future__ import annotations

import json
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import FastAPI, Request

from app.core.trace import (
    child_span,
    current_span,
    reset_session_traces,
    set_trace_context,
)
from app.otel.exporter import OtelExporter, get_otel_exporter, set_otel_exporter
from app.otel.metrics import OtelMetrics, get_otel_metrics, set_otel_metrics


@pytest.fixture
def iso():
    """隔离的 exporter + metrics 单例，避免测试间串扰。"""
    exp = OtelExporter(jsonl_dir=tempfile.mkdtemp(prefix="otel-test-"))
    met = OtelMetrics()
    # exporter 内部引用 metrics 单例；让二者指向同一隔离实例
    exp._metrics = met
    set_otel_exporter(exp)
    set_otel_metrics(met)
    yield exp
    set_otel_exporter(OtelExporter(jsonl_dir=tempfile.mkdtemp(prefix="otel-restore-")))
    set_otel_metrics(OtelMetrics())


# ============================================================
# AC1：trace 贯穿 —— 一次完整问答按 trace_id 可查全部事件，可归因
# ============================================================
def test_ac1_trace_propagation_and_attribution(iso):
    tid = "trace-ac1-001"
    # 一次完整问答各阶段事件（记忆召回 → LLM → 工具 → 压缩）
    iso.record_memory_event("recall", user_id="userX", adopted=True, trace_id=tid,
                            goal="本周数学计划")
    # 3 天前目标被召回但未被采纳（可还原"为什么没召回 3 天前目标"）
    iso.record_memory_event("recall", user_id="userX", adopted=False, trace_id=tid,
                            goal="3天前设定的目标：每日背 20 个单词")
    iso.record_llm_call(model="fast", trace_id=tid, latency_ms=812.3)
    iso.record_tool_result("SUCCESS", tool="calculator", attempt=1, trace_id=tid, user_id="userX")
    iso.record_compaction_event(before_tokens=8200, after_tokens=5400, dropped_rounds=3,
                                policy="compaction", trace_id=tid)

    events = iso.get_events_by_trace(tid)
    types = {e["event_type"] for e in events}
    assert {"memory_event", "llm_call", "tool_result", "compaction_event"} <= types
    # 每个事件都带 trace_id 与 span_id
    assert all(e["trace_id"] == tid for e in events)
    assert all("span_id" in e and "ts" in e for e in events)

    # 归因：3 天前目标被召回但 adopted=False → 可定位"未采纳"
    goal_events = [e for e in events if e["event_type"] == "memory_event"
                   and "3天前" in (e["payload"].get("goal") or "")]
    assert goal_events, "应能检索到 3 天前目标的召回事件"
    assert goal_events[0]["payload"]["adopted"] is False


# ============================================================
# AC2：5 维指标计数 + 比例 + 可溯源
# ============================================================
def test_ac2_five_dim_metrics_snapshot(iso):
    tid = "trace-ac2-001"
    # 记忆命中率：2 召回 1 采纳 → 0.5
    iso.record_memory_event("recall", user_id="u1", adopted=True, trace_id=tid)
    iso.record_memory_event("recall", user_id="u1", adopted=False, trace_id=tid)
    # 压缩效率：before 1000 after 600 → ratio 0.6
    iso.record_compaction_event(before_tokens=1000, after_tokens=600, dropped_rounds=2, policy="compaction", trace_id=tid)
    # 工具成功率：SUCCESS/ERROR/TIMEOUT/REJECTION_LIMIT 各 1 → 0.25
    for oc in ("SUCCESS", "ERROR", "TIMEOUT", "REJECTION_LIMIT"):
        iso.record_tool_result(oc, tool="t", trace_id=tid)
    # 缓存命中率：read 800 miss 200 → 0.8
    iso.record_cache_event(cache_read=800, cache_miss=200, model="fast", layer="project", trace_id=tid)
    # 排队超时率：acquire×3 timeout×1 → 0.25
    for _ in range(3):
        iso.record_queue_event("acquire", level="L1", trace_id=tid)
    iso.record_queue_event("timeout", level="L1", trace_id=tid)

    snap = iso._metrics.snapshot()
    mh = snap["memory_hit_rate"]
    assert mh["recall_total"] == 2 and mh["recall_accepted"] == 1
    assert mh["hit_rate"] == 0.5
    assert mh["sources"], "记忆命中率应保留溯源事件"

    ce = snap["compaction_efficiency"]
    assert ce["compactions"] == 1 and ce["before_tokens_total"] == 1000
    assert ce["compression_ratio"] == 0.6
    assert ce["policy_distribution"]["compaction"] == 1

    ts = snap["tool_success_rate"]
    assert ts["total"] == 4 and ts["success_rate"] == 0.25

    ch = snap["cache_hit_rate"]
    assert ch["cache_read"] == 800 and ch["cache_miss"] == 200 and ch["hit_rate"] == 0.8
    assert ch["by_model"]["fast"]["hit_rate"] == 0.8

    qt = snap["queue_timeout_rate"]
    # 排队超时率 = timeout / acquire = 1/3 ≈ 0.3333
    assert qt["acquire_total"] == 3 and qt["timeout_total"] == 1
    assert abs(qt["timeout_rate"] - 1 / 3) < 1e-3


# ============================================================
# AC3：OTel 导出 —— JSONL 落盘 schema / OTLP HTTP / 降级
# ============================================================
def test_ac3_jsonl_export_schema():
    with tempfile.TemporaryDirectory(prefix="otel-jsonl-") as tmp:
        exp = OtelExporter(jsonl_dir=tmp)  # 空 endpoint → JSONL 落盘
        ev = exp.record("memory_event", {"action": "recall", "user_id": "u9", "adopted": True},
                        trace_id="t-jsonl", user_id="u9", model="fast", latency_ms=12.5)
        assert ev is not None
        files = list(Path(tmp).glob("*.jsonl"))
        assert files, "应生成 JSONL 文件"
        lines = [json.loads(l) for l in Path(files[0]).read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 1
        row = lines[0]
        # schema 必需字段
        for k in ("ts", "trace_id", "span_id", "event_type", "event_id", "payload", "user_id", "model", "latency_ms"):
            assert k in row, f"JSONL 缺字段 {k}"
        assert row["trace_id"] == "t-jsonl"
        assert row["event_type"] == "memory_event"
        assert row["latency_ms"] == 12.5


def test_ac3_otlp_http_export(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="otel-otlp-") as tmp:
        exp = OtelExporter(endpoint="http://localhost:4318/v1/logs", jsonl_dir=tmp)
        posted = {}

        def fake_post(url, json=None, timeout=2.0, **kw):
            posted["url"] = url
            posted["json"] = json

            class _R:
                status_code = 200
            return _R()

        import requests as _req
        monkeypatch.setattr(_req, "post", fake_post)
        exp.record("tool_result", {"outcome": "SUCCESS"}, trace_id="t-otlp", model="fast")
        # 走 HTTP，不落盘
        assert posted.get("url") == "http://localhost:4318/v1/logs"
        assert posted["json"]["event_type"] == "tool_result"
        assert not list(Path(tmp).glob("*.jsonl")), "OTLP 成功时不应落盘 JSONL"


def test_ac3_otlp_degrade_to_jsonl(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="otel-degrade-") as tmp:
        exp = OtelExporter(endpoint="http://localhost:4318/v1/logs", jsonl_dir=tmp)
        import requests as _req

        def boom(*a, **k):
            raise RuntimeError("network down")
        monkeypatch.setattr(_req, "post", boom)
        exp.record("tool_result", {"outcome": "ERROR"}, trace_id="t-deg")
        # 失败 → 降级 JSONL 落盘，不抛出
        assert list(Path(tmp).glob("*.jsonl")), "OTLP 失败应降级 JSONL 落盘"


# ============================================================
# AC4：会话级 trace —— 同一会话多次请求共用 trace_id，span_id 各异
# ============================================================
def test_ac4_session_level_trace_id():
    reset_session_traces()
    sid = "session-ac4"
    tids = []
    spans_per_req = []
    for _ in range(3):
        tid = set_trace_context(session_id=sid)
        tids.append(tid)
        # 请求内嵌套 span：span_id 各异
        with child_span("memory_recall") as s1:
            with child_span("llm_call") as s2:
                spans_per_req.append((s1, s2))
    # 3 次请求共用同一会话级 trace_id
    assert len(set(tids)) == 1, "同一会话应复用同一 trace_id"
    # span_id 各自不同（嵌套内部）
    all_spans = [s for pair in spans_per_req for s in pair]
    assert len(set(all_spans)) == len(all_spans), "每次请求的 span_id 应各异"
    # 跨请求 span_id 也不同
    assert len({p[0] for p in spans_per_req}) == 3
    reset_session_traces()


def test_ac4_session_isolation():
    reset_session_traces()
    a = set_trace_context(session_id="sess-A")
    b = set_trace_context(session_id="sess-B")
    assert a != b, "不同会话应有不同 trace_id"
    # 再次进入同一会话得到同一 trace_id
    assert set_trace_context(session_id="sess-A") == a
    reset_session_traces()


# ============================================================
# AC5：回归 —— X-Trace-Id 响应头仍携带 trace_id（会话级下携带会话 trace_id）
# ============================================================
@pytest.mark.asyncio
async def test_ac5_x_trace_id_header_present_and_session_aware():
    from app.middleware.auth_middleware import TraceMiddleware

    reset_session_traces()
    app = FastAPI()
    captured = {}

    @app.post("/api/chat")
    async def route(request: Request):
        # 会话入口设置会话级 trace_id，并写入 request.state（穿透 BaseHTTPMiddleware context 隔离）
        tid = set_trace_context(session_id="sess-ac5")
        request.state.trace_id = tid
        captured["tid"] = tid
        return {"ok": True}

    app.add_middleware(TraceMiddleware)

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post("/api/chat")
        h1 = r1.headers.get("X-Trace-Id")
        assert h1, "响应头必须携带 X-Trace-Id（回归）"
        assert h1 == captured["tid"], "会话级下 X-Trace-Id 应等于会话 trace_id"
        # 第二次同会话请求：同一会话 trace_id 也贯穿响应头
        captured.clear()
        r2 = await client.post("/api/chat")
        h2 = r2.headers.get("X-Trace-Id")
        assert h2 == h1, "同一会话多次请求的 X-Trace-Id 应保持一致"
    reset_session_traces()


@pytest.mark.asyncio
async def test_ac5_default_trace_header_present():
    """未启用会话级时（无 session_id / 无 request.state 覆盖），X-Trace-Id 仍由中间件生成并透传（既有行为不退化）。"""
    from app.middleware.auth_middleware import TraceMiddleware

    app = FastAPI()

    @app.get("/api/healthz")
    async def route():
        return {"ok": True}

    app.add_middleware(TraceMiddleware)

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/healthz")
        assert r.headers.get("X-Trace-Id"), "默认路径下 X-Trace-Id 头仍应存在"


# ============================================================
# 端点契约（handoff → task-FE-O1）：/api/metrics/trace/{trace_id}
# ============================================================
@pytest.mark.asyncio
async def test_trace_retrieval_endpoint_contract(iso):
    tid = "trace-endpoint-001"
    iso.record_memory_event("recall", user_id="u", adopted=True, trace_id=tid)
    iso.record_tool_result("SUCCESS", trace_id=tid)
    iso.record_cache_event(cache_read=500, cache_miss=100, trace_id=tid)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.monitoring.router import router as monitoring_router

    app = FastAPI()
    app.include_router(monitoring_router)

    with TestClient(app) as client:
        r = client.get(f"/api/metrics/trace/{tid}")
        assert r.status_code == 200
        body = r.json()
        assert body["trace_id"] == tid
        assert body["event_count"] == 3
        assert len(body["events"]) == 3
        # 契约字段
        assert all("event_type" in e and "payload" in e for e in body["events"])
        # 局部 5 维指标快照（可溯源）
        assert "memory_hit_rate" in body["trace_metrics"]
        assert "tool_success_rate" in body["trace_metrics"]
        assert abs(body["trace_metrics"]["cache_hit_rate"]["hit_rate"] - 500 / 600) < 1e-3
