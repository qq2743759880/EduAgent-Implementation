# -*- coding: utf-8 -*-
"""O1-②③ 环境依赖项离线单测：OTel exporter 双通道（JSONL 落盘 / OTLP HTTP 降级）。

无需真实 OTLP 后端 / Prometheus 即可验证：
  1) record → 内存事件 + JSONL 落盘文件；
  2) count / trace 检索 / ring buffer 上限；
  3) 采样（sample_rate<1 稳定丢弃）；
  4) endpoint 配置但网络失败 → 降级 JSONL，不抛错、主流程不阻塞。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import time
import json

import pytest

from app.otel.exporter import OtelExporter, MAX_MEMORY_EVENTS


def _mk_exporter(tmp_path, **kw) -> OtelExporter:
    # 注入隔离实例（端到端 = jsonl 落盘到 tmp_path）
    cfg = {"clock": time.time, "jsonl_dir": str(tmp_path)}
    cfg.update(kw)
    return OtelExporter(**cfg)


# 1. record → 事件结构完整 + count 递增 + JSONL 落盘
def test_record_counts_and_writes_jsonl(tmp_path):
    ex = _mk_exporter(tmp_path)
    ev = ex.record("llm_call", {"q": "hi"}, trace_id="t1", latency_ms=123)
    assert ev is not None
    assert ev["event_type"] == "llm_call"
    assert ev["trace_id"] == "t1"
    assert ev["latency_ms"] == 123
    assert ex.count() == 1
    # JSONL 落盘存在（无 endpoint → 走落盘）
    files = list(Path(tmp_path).glob("otel-*.jsonl"))
    assert files, "应有日文件"
    line = json.loads(files[0].read_text(encoding="utf-8").strip().splitlines()[0])
    assert line["event_type"] == "llm_call"


# 2. trace 检索
def test_get_events_by_trace(tmp_path):
    ex = _mk_exporter(tmp_path)
    ex.record("cache_event", trace_id="tA")
    ex.record("cache_event", trace_id="tB")
    got = ex.get_events_by_trace("tA")
    assert len(got) == 1 and got[0]["trace_id"] == "tA"
    assert ex.get_events_by_trace("tX") == []


# 3. ring buffer 上限：超限最早事件被淘汰
def test_ring_buffer_caps_at_max(tmp_path):
    ex = _mk_exporter(tmp_path)
    # 注入超过上限的事件（用极低上限模拟更省时——直接覆盖模块常量在实例层不易；用真实上限造 MAX+1 条轻量事件
    n = MAX_MEMORY_EVENTS + 5
    for i in range(n):
        ex.record("ev", {"i": i}, trace_id=f"t{i}")
    assert ex.count() == MAX_MEMORY_EVENTS, "环形缓冲应稳定在上限"
    first_remaining = sorted(int(e["payload"].get("i", -1)) for e in ex.get_all_events())[0]
    assert first_remaining >= 5, f"最早 5 条应对淘汰，剩最小 i={first_remaining}"


# 4. 采样：sample_rate<1 稳定丢弃超出部分
def test_sampling_drops_when_rate_lt_1(tmp_path):
    ex = _mk_exporter(tmp_path, sample_rate=0.0)  # 0% 保留 → 全部丢弃
    n_keep = 0
    for i in range(200):
        if ex.record("ev", {"i": i}, trace_id=f"t{i}", event_id=f"{i:032x}") is not None:
            n_keep += 1
    assert n_keep == 0, "sample_rate=0 应全部丢弃"


# 5. OTLP endpoint 网络失败 → 降级 JSONL，不抛错
def test_otlp_failure_degrades_to_jsonl(tmp_path, monkeypatch):
    import requests as _requests

    # 配置 endpoint 使 record 走 _export_otlp；mock requests.post 抛网络异常
    ex = _mk_exporter(tmp_path, endpoint="http://127.0.0.1:1/none")
    calls = {"n": 0}

    def _boom(*a, **kw):
        calls["n"] += 1
        raise ConnectionError("backend down")

    monkeypatch.setattr(_requests, "post", _boom)
    ev = ex.record("queue_event", {"q": 1}, trace_id="tZ")
    assert ev is not None, "网络失败不应阻断 record（降级不抛错）"
    assert calls["n"] == 1, "应尝试一次 OTLP 投递"
    # 降级落盘
    files = list(Path(tmp_path).glob("otel-*.jsonl"))
    assert files, "网络失败应降级 JSONL 落盘"