# -*- coding: utf-8 -*-
"""监控路由：
- /metrics：Prometheus 抓取端点（text/plain）。C5-K1：可选 METRICS_TOKEN Bearer 门。
- /api/metrics/cache-context-dashboard：task97 联合看板（上下文水位 task96 + 缓存命中 task97）JSON。
"""
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response

from app.monitoring.metrics import render_metrics
from app.auth import CurrentUser, UserRole, require_role
from app.config import settings

router = APIRouter(tags=["监控"])


@router.get("/metrics")
async def metrics_endpoint(request: Request):
    """Prometheus 抓取端点（text/plain 格式）。

    C5-K1 门禁：METRICS_TOKEN 未设置 → 维持公开（向后兼容，监控抓取不被破坏）；
    设置后要求 Authorization: Bearer <METRICS_TOKEN>，否则 401 壳（40101，
    与全站鉴权失败响应形状一致）。比对用 hmac.compare_digest（恒定时间）。
    """
    expected = (settings.METRICS_TOKEN or "").strip()
    if expected:
        import hmac as _hmac

        provided = request.headers.get("Authorization") or ""
        if not _hmac.compare_digest(provided, f"Bearer {expected}"):
            return JSONResponse(
                status_code=401,
                content={"code": "40101", "message": "metrics 访问凭证缺失或无效", "data": None},
                headers={"WWW-Authenticate": "Bearer"},
            )
    return Response(
        content=render_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/api/metrics/cache-context-dashboard")
async def cache_context_dashboard(
    session_id: str | None = Query(default=None, description="可选：指定会话，便于前端观测单会话水位"),
    current_user: CurrentUser = Depends(require_role([UserRole.ADMIN, UserRole.MANAGER])),
):
    """联合看板：上下文水位（task96 ContextUsageMonitor）+ 缓存命中（task97 CacheMonitor）。

    不依赖真实 LLM，直接读进程内监控器快照；供管理端观测面板（task-FE-O1）消费。
    """
    try:
        from app.ai.cache_monitor import get_cache_monitor

        board = await get_cache_monitor().joint_dashboard(session_id=session_id)
        return JSONResponse(content=board)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=200, content={"error": str(exc)[:200], "cache": {}, "context": {}})


@router.get("/api/metrics/otel")
async def otel_metrics_snapshot(
    current_user: CurrentUser = Depends(require_role([UserRole.ADMIN, UserRole.MANAGER])),
):
    """task-O1 5 维指标全局快照（AC2）。

    进程内累加器，每项含计数 + 比例 + 溯源事件列表；供观测面板（task-FE-O1）消费。
    不依赖真实 LLM，直接读进程内累加器。
    """
    try:
        from app.otel.metrics import get_otel_metrics

        return JSONResponse(content=get_otel_metrics().snapshot())
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=200, content={"error": str(exc)[:200]})


@router.get("/api/metrics/trace/{trace_id}")
async def trace_events(
    trace_id: str,
    limit: int = Query(default=500, ge=1, le=5000, description="返回事件上限"),
    current_user: CurrentUser = Depends(require_role([UserRole.ADMIN, UserRole.MANAGER])),
):
    """按 trace_id 检索一次完整问答的全部观测事件（task-O1 AC1 交付契约，供 task-FE-O1 观测面板）。

    返回该 trace 下的：记忆写/召回、LLM usage、工具结果、压缩前后 token 等全部事件，
    + 该 trace 局部的 5 维指标快照（由本 trace 事件重算，保证可溯源）。
    可据此还原「为什么没召回 3 天前目标」等问题。

    契约（handoff → task-FE-O1）：
      GET /api/metrics/trace/{trace_id}
      200 {
        trace_id, event_count,
        events: [ {ts, trace_id, span_id, event_type, event_id, payload, user_id, model, latency_ms}, ... ],
        trace_metrics: { memory_hit_rate, compaction_efficiency, tool_success_rate, cache_hit_rate, queue_timeout_rate }
      }
    """
    try:
        from app.otel.exporter import get_otel_exporter
        from app.otel.metrics import OtelMetrics

        exporter = get_otel_exporter()
        events = exporter.get_events_by_trace(trace_id)
        # 该 trace 局部 5 维指标（仅基于本 trace 事件重算，保证可溯源）
        m = OtelMetrics()
        for e in events:
            m.record(e)
        return JSONResponse(
            content={
                "trace_id": trace_id,
                "event_count": len(events),
                "events": events[-limit:],
                "trace_metrics": m.snapshot(),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=200,
            content={"trace_id": trace_id, "event_count": 0, "events": [], "trace_metrics": {}, "error": str(exc)[:200]},
        )
