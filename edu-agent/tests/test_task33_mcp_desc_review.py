# -*- coding: utf-8 -*-
"""task33 GWT 契约测试：MCP 工具描述评分/重写 + per-server 熔断 + 只读缓存。

覆盖（全文见 .opencode/plans/tasks/task33-mcp-description-review.md）：
- GWT① description_reviewer.score_description：六项规则打分 0-100，<70 触发 FAST 重写（LLM 降级语义）；
- GWT② core.breaker 连续失败模式：5 次 record_failure → OPEN，30s 后半开探针，探针成功恢复；
- GWT③ executor._is_cached_call：只读工具可缓存，写语义工具跳过缓存。

数据策略：
- score_description / _is_cached_call / _mcp_cache_key 为纯函数，零 DB 依赖；
- 熔断器用独立命名的实例（避免 Redis 旧状态污染），open_duration 回拨模拟 30s 流逝。
"""
from __future__ import annotations

import pytest

from app.core.breaker import BreakerConfig, BreakerState, CircuitBreaker, CircuitOpenError
from app.mcp.description_reviewer import (
    REWRITE_THRESHOLD,
    score_description,
)
from app.mcp.executor import _is_cached_call, _mcp_cache_key


# ============================================================
# GWT① 规则打分（纯函数）
# ============================================================
def test_gwt1_score_high_quality_description():
    """六要素齐全 → 满分 100。"""
    desc = ("根据用户阅读偏好推荐个性化课程，返回课程列表与匹配理由，"
            "需要传入 user_id 与 category 参数，示例：user_id=3；"
            "避免在无偏好历史时使用，仅当用户有浏览记录时触发。")
    s = score_description(desc, schema={"type": "object",
                                        "properties": {"user_id": {"type": "integer"}}})
    assert s.total == 100, s.to_dict()
    assert s.breaches == [], s.breaches


def test_gwt1_score_poor_description_below_threshold():
    """句式填充开头、缺边界/参数/返回/示例 → 低分并触发重写。"""
    desc = "这是一个课程查询工具"
    s = score_description(desc)
    assert s.total < REWRITE_THRESHOLD, s.to_dict()
    assert "不以动词/动作短语起句" in s.breaches
    assert "缺少『何时不该用』边界说明" in s.breaches


def test_gwt1_score_empty_description():
    """空描述 → 0 分且标记『描述为空』，不报错。"""
    s = score_description("")
    assert s.total == 0 and s.breaches == ["描述为空"]


def test_gwt1_score_param_from_required_schema():
    """描述不含『参数』字样，但 schema.required 命中参数名 → 参数域得分。"""
    desc = "根据 weather_code 判断是否下雨，返回晴/雨；避免对空值调用，示例：weather_code='100'。"
    schema = {"type": "object", "required": ["weather_code"],
              "properties": {"weather_code": {"type": "string"}}}
    s = score_description(desc, schema)
    assert s.param == 20, s.to_dict()


def test_gwt1_score_schema_example_fallback():
    """描述无示例字样，但 schema 自带 example → 示例项得分。"""
    desc = "根据 user_id 返回用户画像摘要，需要传入 user_id；仅当存在该用户时使用，返回结构化字段。"
    schema = {"type": "object",
              "properties": {"user_id": {"type": "integer", "example": 7}}}
    s = score_description(desc, schema)
    assert s.example == 10, s.to_dict()


# ============================================================
# GWT③ 只读缓存分类（纯函数）
# ============================================================
def test_gwt3_readonly_tool_cached():
    assert _is_cached_call("get_user_profile", {"uid": 1}) is True


def test_gwt3_write_tool_skips_cache():
    """写语义前缀工具（create/send/update…）不缓存，避免缓存非幂等副作用。"""
    assert _is_cached_call("create_order", {"sku": "A"}) is False
    assert _is_cached_call("send_message", {"text": "hi"}) is False
    assert _is_cached_call("update_stock", {"spu": 9}) is False


def test_gwt3_cache_key_arg_order_independent():
    """同参不同 key 顺序 → 幂等 key（保证 60s 命中）；不同参数 → 不同 key。"""
    a = _mcp_cache_key(1, "get_stat", {"b": 2, "a": 1})
    b = _mcp_cache_key(1, "get_stat", {"a": 1, "b": 2})
    c = _mcp_cache_key(1, "get_stat", {"a": 1, "b": 3})
    d = _mcp_cache_key(2, "get_stat", {"a": 1, "b": 2})
    assert a == b
    assert a != c
    assert a != d


# ============================================================
# GWT② 连续失败熔断（core.breaker 连续失败模式）
# ============================================================
@pytest.mark.asyncio
async def test_gwt2_consecutive_failures_opens_then_half_open_probe():
    """连续 5 次失败 → OPEN（check 快速失败）；30s 后半开放行探针；探针连续成功 → 恢复 closed。"""
    import time as _t
    breaker = CircuitBreaker(
        name="task33-test-consecutive",
        config=BreakerConfig(consecutive_failures=5, open_duration=30.0, half_open_probes=3),
    )

    async def _no_redis():
        return None
    breaker._get_redis = _no_redis  # 关掉 Redis 同步，保证本地状态确定性

    # 前 4 次失败：仍 closed
    for _ in range(4):
        await breaker.record_failure()
    assert breaker._state == BreakerState.CLOSED
    # 第 5 次失败 → OPEN
    await breaker.record_failure()
    assert breaker._state == BreakerState.OPEN

    # 未到 open_duration → check 抛 CircuitOpenError（毫秒级快速失败）
    with pytest.raises(CircuitOpenError):
        await breaker.check()

    # 回拨 opened_at 31s（等效 30s 流逝）→ check 进入半开放行探针
    breaker._opened_at = _t.time() - 31.0
    breaker._last_sync = 0.0
    await breaker.check()
    assert breaker._state == BreakerState.HALF_OPEN

    # 半开探针连续 3 次成功 → 恢复 closed
    await breaker.record_success()
    await breaker.record_success()
    await breaker.record_success()
    assert breaker._state == BreakerState.CLOSED