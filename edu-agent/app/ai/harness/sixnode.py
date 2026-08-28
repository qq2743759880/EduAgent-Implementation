# -*- coding: utf-8 -*-
"""task-A1 默认 Harness 实现：SixNodeHarness（= task24 现有 6 节点 DAG，行为零变化）。

实现方式：把 graph.py 现有的 route_node / plan_node / fan_out_node / merge_node / reflect_node /
answer_node **原样委派（delegate）**，不搬运逻辑，保证重构前/后行为逐字节一致
（nodes_executed / 降级 / effort scaling / 子代理蒸馏 / checkpointer 全等价）。

关键：通过 ``app.ai.graph`` 模块属性**调用时动态查表**（``_graph.route_node(state)``），
而非 import 时绑定函数别名。这样测试仍可 ``monkeypatch(app.ai.graph, "answer_node", ...)``
（委派在调用时解析模块属性），task24 契约测试与 durable execution 复现不受影响。

对齐 task29 R8 keep_sixnode 裁定：默认实现 = 原 6 节点 DAG，开放接口不改变默认行为。
"""
from __future__ import annotations

from app.ai.graph import AgentState
from app.ai.graph import (  # noqa: F401  (re-export for type-checkers / discoverability)
    answer_node,
    fan_out_node,
    merge_node,
    plan_node,
    reflect_node,
    route_node,
)
from app.ai.harness.base import Harness

# 调用时动态解析模块属性（兼容 monkeypatch），避免 import 时绑定别名导致打桩失效。
from app.ai import graph as _graph


class SixNodeHarness(Harness):
    """默认实现：复用 task24 全部节点逻辑，零行为变化。"""

    async def route(self, state: AgentState) -> dict:
        return await _graph.route_node(state)

    async def plan(self, state: AgentState) -> dict:
        return await _graph.plan_node(state)

    async def fan_out(self, state: AgentState) -> dict:
        return await _graph.fan_out_node(state)

    async def merge(self, state: AgentState) -> dict:
        # 原 merge_node 为同步函数；在 async 接口内直接调用并返回其更新 dict
        return _graph.merge_node(state)

    async def reflect(self, state: AgentState) -> dict:
        return await _graph.reflect_node(state)

    async def answer(self, state: AgentState) -> dict:
        return await _graph.answer_node(state)
