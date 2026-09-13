# -*- coding: utf-8 -*-
"""C5-K1：/metrics METRICS_TOKEN 可选门禁契约测试（离线 TestClient，不触 DB/Redis）。

用例矩阵：
  ① 未设置 METRICS_TOKEN（默认）→ /metrics 公开放行 200（向后兼容，监控抓取不被破坏）
  ② 设置 METRICS_TOKEN 后：无 Authorization 头 → 401 壳 {code:"40101"}；
     错误 token → 401；正确 Bearer → 200 text/plain
  ③ 401 响应形状与全站鉴权失败一致（{code,message,data:null} + WWW-Authenticate）

守则对齐：禁 DB 直写；禁 Playwright；token 状态全部 monkeypatch 注入，不改 .env。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.monitoring.router import router as monitoring_router


@pytest.fixture()
def metrics_app() -> TestClient:
    """最小应用：只挂 monitoring 路由（不含全量中间件栈，聚焦 /metrics 端点行为）。"""
    app = FastAPI()
    app.include_router(monitoring_router)
    return TestClient(app)


def test_metrics_public_when_token_unset(metrics_app: TestClient, monkeypatch):
    """① METRICS_TOKEN 默认空 → 公开放行（向后兼容口径）。"""
    monkeypatch.setattr(settings, "METRICS_TOKEN", "")
    resp = metrics_app.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "edu_http_requests_total" in resp.text


def test_metrics_401_without_header_when_token_set(metrics_app: TestClient, monkeypatch):
    """②-a 设置 token 后：无头 → 401 壳，形状与全站鉴权失败一致。"""
    monkeypatch.setattr(settings, "METRICS_TOKEN", "tok-metrics-123")
    resp = metrics_app.get("/metrics")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "40101"
    assert body["data"] is None
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


def test_metrics_401_with_wrong_token(metrics_app: TestClient, monkeypatch):
    """②-b 错误 token → 401（Bearer 前缀缺失/值错误都算不匹配）。"""
    monkeypatch.setattr(settings, "METRICS_TOKEN", "tok-metrics-123")
    for header in ("Bearer wrong-token", "tok-metrics-123", "Bearer "):
        resp = metrics_app.get("/metrics", headers={"Authorization": header})
        assert resp.status_code == 401, header
        assert resp.json()["code"] == "40101"


def test_metrics_200_with_correct_bearer(metrics_app: TestClient, monkeypatch):
    """②-c 正确 Bearer → 200 text/plain Prometheus 载荷。"""
    monkeypatch.setattr(settings, "METRICS_TOKEN", "tok-metrics-123")
    resp = metrics_app.get("/metrics", headers={"Authorization": "Bearer tok-metrics-123"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "edu_http_requests_total" in resp.text
