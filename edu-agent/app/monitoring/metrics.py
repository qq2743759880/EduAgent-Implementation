# -*- coding: utf-8 -*-
"""Prometheus 指标（P1-2 监控）：
- HTTP 请求计数/耗时直方图/在途请求
- LLM 调用计数/耗时
- 业务指标（聊天会话）
通过 /metrics 端点暴露，供 Prometheus 抓取 + Grafana 面板。
"""
from __future__ import annotations

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# 独立注册表（避免与全局默认表冲突）
REGISTRY: CollectorRegistry = CollectorRegistry()

# ============================================================
# HTTP 指标
# ============================================================
http_requests_total = Counter(
    "edu_http_requests_total",
    "HTTP 请求总数",
    labelnames=("method", "path", "status"),
    registry=REGISTRY,
)
http_request_duration = Histogram(
    "edu_http_request_duration_seconds",
    "HTTP 请求耗时（秒）",
    labelnames=("method", "path"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    registry=REGISTRY,
)
http_requests_inflight = Gauge(
    "edu_http_requests_inflight",
    "当前在途请求数",
    registry=REGISTRY,
)

# ============================================================
# LLM 指标
# ============================================================
llm_requests_total = Counter(
    "edu_llm_requests_total",
    "LLM 调用总数",
    labelnames=("model", "stream", "status"),
    registry=REGISTRY,
)
llm_duration_seconds = Histogram(
    "edu_llm_duration_seconds",
    "LLM 调用耗时（秒）",
    labelnames=("model", "stream"),
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 40.0, 60.0),
    registry=REGISTRY,
)
llm_ttft_seconds = Histogram(
    "edu_llm_ttft_seconds",
    "LLM 流式首 token 延迟（秒）",
    labelnames=("model",),
    buckets=(0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0),
    registry=REGISTRY,
)

# ============================================================
# 业务指标
# ============================================================
chat_messages_total = Counter(
    "edu_chat_messages_total",
    "聊天消息总数（含降级模板）",
    labelnames=("mode",),  # agent / rag / fallback
    registry=REGISTRY,
)

# ============================================================
# task97 R5 缓存监控指标（命中率当 uptime 监控）
#   cache_read/creation/prompt token 累计 → 命中率 = cache_read/(cache_read+未缓存)
#   cache_hit_rate：整体命中率 Gauge（低 = SEV）
#   cache_invalidations_total{reason}：前缀失效原因计数（模型切换/MCP 变更/compaction/context_edit…）
# ============================================================
cache_read_tokens_total = Counter(
    "edu_cache_read_tokens_total",
    "Prompt cache 命中读回 token 累计（cache_read_input_tokens）",
    registry=REGISTRY,
)
cache_creation_tokens_total = Counter(
    "edu_cache_creation_tokens_total",
    "Prompt cache 新建写 token 累计（cache_creation_input_tokens）",
    registry=REGISTRY,
)
cache_prompt_tokens_total = Counter(
    "edu_cache_prompt_tokens_total",
    "LLM 调用 prompt token 累计（含 cache_read + creation + 未缓存）",
    registry=REGISTRY,
)
cache_hit_rate = Gauge(
    "edu_cache_hit_rate",
    "Prompt cache 整体命中率（cache_read / (cache_read + 未缓存基数)）；低 = SEV（竞品对标 Claude Code prompt-caching）",
    registry=REGISTRY,
)
cache_invalidations_total = Counter(
    "edu_cache_invalidations_total",
    "Prompt cache 前缀失效事件计数（命中率下降根因）",
    labelnames=("reason",),  # model_switch / mcp_change / compaction / context_edit / effort_change / prefix_change
    registry=REGISTRY,
)
# 联合看板：task96 上下文水位（usage ratio，最近一次快照）
context_usage_ratio = Gauge(
    "edu_context_usage_ratio",
    "上下文使用率水位（task96 ContextUsageMonitor 最近快照；total_tokens / 窗口预算）",
    registry=REGISTRY,
)
vector_search_duration_seconds = Histogram(
    "edu_vector_search_duration_seconds",
    "三通道检索耗时（秒）",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
    registry=REGISTRY,
)

# ============================================================
# task39 GWT② 降级指标（doc-architect-tech-arch §6.4 明文要求）
#   「降级指标全部进 Prometheus（edu_degraded_total{component}）」
#   此前只有响应体里的 degraded_reason 字符串，无聚合计数 → 容灾演练无法量化验证。
#   component ∈ milvus / redis / mongo / neo4j / minio / llm / reranker / mysql
# ============================================================
degraded_total = Counter(
    "edu_degraded_total",
    "外部依赖降级次数（按组件聚合；容灾演练与告警依据）",
    labelnames=("component", "reason"),
    registry=REGISTRY,
)
# 降级组件当前是否在降级态（1=降级中，0=正常）。配合 edu_degraded_total 做告警：
# 短时抖动看计数，持续故障看 Gauge 是否长时间为 1。
degraded_active = Gauge(
    "edu_degraded_active",
    "组件当前是否处于降级态（1=降级中）",
    labelnames=("component",),
    registry=REGISTRY,
)


def record_degraded(component: str, reason: str | None = None) -> None:
    """记录一次降级（供各降级点统一埋点）。

    组件名收敛到 §6.4 矩阵行：milvus / redis / mongo / neo4j / minio / llm / reranker / mysql。
    reason 为原始降级说明（高基数，仅用于排查；告警请按 component 聚合）。
    """
    try:
        comp = (component or "unknown").strip().lower()
        degraded_total.labels(component=comp, reason=(reason or "")[:120]).inc()
        degraded_active.labels(component=comp).set(1)
    except Exception:  # noqa: BLE001 — 指标埋点永远不影响业务链路
        pass


def clear_degraded(component: str) -> None:
    """组件恢复：把降级态 Gauge 置 0（熔断 half-open 探测成功后调用）。"""
    try:
        degraded_active.labels(component=(component or "unknown").strip().lower()).set(0)
    except Exception:  # noqa: BLE001
        pass


def render_metrics() -> bytes:
    """生成 Prometheus 文本格式指标（供 /metrics 端点）。"""
    return generate_latest(REGISTRY)
