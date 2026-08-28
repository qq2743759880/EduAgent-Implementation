# -*- coding: utf-8 -*-
"""C2-③ 契约测试：schema_registry Redis 共享 → 跨实例一致（task-M2 协同）。

验收点：
1. 实例 A register_spec 的自定义 schema，实例 B（独立本地缓存、共享同一 Redis）expand_schema 可读回且字段一致。
2. 内置规范跨实例一致：A seed_builtins 后 B 也能 expand 到同一内置 schema。
3. 更新传播：A 重新 register_spec（overwrite）后，另一全新实例可读到更新值。
4. 未知工具两侧均返回 None，且不污染 Redis。
5. Redis 不可用时整体跳过（不阻塞 CI / 单测）。

直接运行：
    pytest tests/test_contract_task_c2_schema_registry.py -q
"""
from __future__ import annotations

import os
import uuid

import pytest

from app.ai.tool_specs import BUILTIN_TOOL_SPECS, SchemaRegistry, ToolSpec

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")


def _redis_available() -> bool:
    try:
        import redis

        r = redis.Redis.from_url(REDIS_URL, socket_timeout=1, socket_connect_timeout=1)
        return bool(r.ping())
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_available(), reason="Redis 不可用，跳过 C2-③ 跨实例一致性契约"
)


def _ns() -> str:
    return "c2test_" + uuid.uuid4().hex


def _make(ns: str, ttl: float = 2.0) -> SchemaRegistry:
    return SchemaRegistry(REDIS_URL, namespace=ns, cache_ttl=ttl, redis_enabled=True)


def test_cross_instance_custom_spec_consistent():
    """实例 A 注册的自定义 schema，实例 B（独立缓存）应能跨 Redis 读到且字段一致。"""
    ns = _ns()
    a = _make(ns)
    b = _make(ns)
    try:
        spec = ToolSpec(
            name="image_gen",
            description="生成图片。何时用:需要配图;不用:纯文本。参数:prompt,size。返回:{url}。副作用:写对象存储,幂等。",
            input_schema={
                "type": "object",
                "properties": {"prompt": {"type": "string"}, "size": {"type": "string"}},
                "required": ["prompt"],
            },
            risk="write",
            parallel_safe=False,
            timeout_s=45.0,
            admin_only=False,
        )
        a.register_spec(spec)
        got = b.expand_schema("image_gen")
        assert got is not None, "实例 B 应能从共享 Redis 读到实例 A 注册的 schema"
        assert got.name == spec.name
        assert got.description == spec.description
        assert got.input_schema == spec.input_schema
        assert got.risk == spec.risk
        assert got.parallel_safe == spec.parallel_safe
        assert got.timeout_s == spec.timeout_s
        assert got.admin_only == spec.admin_only
    finally:
        a.clear_namespace()


def test_cross_instance_builtin_consistent():
    """内置规范跨实例一致：A 写入后 B 也能 expand 到同一内置 schema。"""
    ns = _ns()
    a = _make(ns)
    b = _make(ns)
    try:
        a.seed_builtins(BUILTIN_TOOL_SPECS)
        for s in BUILTIN_TOOL_SPECS:
            got = b.expand_schema(s.name)
            assert got is not None, f"实例 B 应读到内置 schema {s.name}"
            assert got.name == s.name
            assert got.input_schema == s.input_schema
            assert got.risk == s.risk
            assert got.admin_only == s.admin_only
    finally:
        a.clear_namespace()


def test_update_propagation():
    """实例 A 更新 schema 后，另一全新实例应读到更新值（跨实例传播）。"""
    ns = _ns()
    a = _make(ns)
    try:
        base = ToolSpec(name="doc_qa", description="v1", input_schema={"type": "object"})
        a.register_spec(base)
        # 全新实例 b2（冷缓存）读应得 v1
        b2 = _make(ns)
        assert b2.expand_schema("doc_qa").description == "v1"
        # A 更新为 v2（overwrite）
        updated = ToolSpec(
            name="doc_qa",
            description="v2",
            input_schema={
                "type": "object",
                "properties": {"q": {"type": "string"}},
            },
        )
        a.register_spec(updated)
        # 再一个全新实例 b3 读应得 v2（跨实例读到最新）
        b3 = _make(ns)
        got = b3.expand_schema("doc_qa")
        assert got is not None
        assert got.description == "v2", "实例应读到实例 A 更新后的 schema"
        assert got.input_schema == updated.input_schema
    finally:
        a.clear_namespace()


def test_unknown_returns_none_both_instances():
    """未知工具两侧均返回 None，且不向 Redis 写入脏 key。"""
    ns = _ns()
    a = _make(ns)
    b = _make(ns)
    try:
        name = "zzz_no_such_tool_" + uuid.uuid4().hex
        assert a.expand_schema(name) is None
        assert b.expand_schema(name) is None
        # 确认没有残留 key
        import redis

        r = redis.Redis.from_url(REDIS_URL, socket_timeout=1, decode_responses=True)
        assert r.keys(f"edu:schema:{ns}:{name}") == []
    finally:
        a.clear_namespace()
