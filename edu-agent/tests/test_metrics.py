# -*- coding: utf-8 -*-
"""P1-2 Prometheus 指标单测：注册表隔离、指标递增、路径归一化。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from app.common.auth import _metric_path


# ============================================================
# 1. 路径归一化（高基数 → 低基数）
# ============================================================
def test_metric_path_numeric_id_normalized():
    assert _metric_path("/api/chat/123") == "/api/chat/{id}"
    assert _metric_path("/api/community/post/42") == "/api/community/post/{id}"
    assert _metric_path("/api/auth/me") == "/api/auth/me"


def test_metric_path_skip_set_excluded():
    assert _metric_path("/metrics") == "/metrics"
    assert _metric_path("/health") == "/health"
    assert _metric_path("/health/detail") == "/health/detail"


def test_metric_path_slug_kept():
    # 会话 id 是字符串（session-xxx）时保留原样（可接受，不归并）
    assert _metric_path("/api/chat/session-abc") == "/api/chat/session-abc"
    # 空 path → 根
    assert _metric_path("") == "/"


# ============================================================
# 2. 指标递增
# ============================================================
def test_http_metrics_increment_and_render():
    from app.monitoring.metrics import (
        http_request_duration,
        http_requests_inflight,
        http_requests_total,
        render_metrics,
    )

    http_requests_inflight.inc()
    http_requests_total.labels(method="GET", path="/api/test", status=200).inc()
    http_request_duration.labels(method="GET", path="/api/test").observe(0.12)
    http_requests_inflight.dec()

    out = render_metrics().decode("utf-8")
    assert "edu_http_requests_total" in out
    assert 'path="/api/test"' in out
    # histogram 有 +Inf bucket
    assert 'edu_http_request_duration_seconds_bucket{le="+Inf"' in out


def test_llm_metrics_render():
    from app.monitoring.metrics import llm_duration_seconds, llm_requests_total, render_metrics

    llm_requests_total.labels(model="deepseek", stream="false", status="ok").inc()
    llm_duration_seconds.labels(model="deepseek", stream="false").observe(1.5)

    out = render_metrics().decode("utf-8")
    # label 顺序由 prometheus 决定（字典序），用宽松匹配
    assert "edu_llm_requests_total" in out
    assert "model=\"deepseek\"" in out
    assert "stream=\"false\"" in out
    assert "edu_llm_duration_seconds_bucket" in out


def test_metrics_isolated_registry():
    """自定义注册表不污染 prometheus_client 默认注册表。"""
    import prometheus_client

    default_families = [f.name for f in prometheus_client.REGISTRY.collect()]
    # 我们的指标不应出现在默认注册表（独立 REGISTRY）
    assert "edu_http_requests_total" not in default_families
