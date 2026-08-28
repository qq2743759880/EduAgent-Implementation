# -*- coding: utf-8 -*-
"""A1-① 契约测试：预处理节点纳入 Harness 可选钩子。

验收点（对应 P1 批判「预处理节点纳入 Harness 可选钩子」）：
1. Harness 基类提供可选 preprocess 钩子（默认空实现，返回 {}）。
2. 默认 SixNodeHarness 未覆盖 preprocess → has_preprocess=False → build_graph 不插入 preprocess
   节点（拓扑零变化，task24 回归安全）。
3. 子类覆盖 preprocess → has_preprocess=True → build_graph 自动在 START→route 之间插入
   preprocess 节点并接线（('__start__','preprocess') 与 ('preprocess','route')）。

直接运行：
    pytest tests/test_contract_task_a1_preprocess.py -q
"""
from __future__ import annotations

import asyncio

from app.ai.graph import build_graph
from app.ai.harness.base import Harness
from app.ai.harness.sixnode import SixNodeHarness


def test_base_preprocess_is_optional_and_default_noop():
    h = SixNodeHarness()
    assert callable(getattr(h, "preprocess", None))
    assert h.has_preprocess is False
    # 默认空实现返回 {}，不修改 state
    out = asyncio.run(h.preprocess({"messages": []}))
    assert out == {}


def test_default_sixnode_has_no_preprocess_node():
    """默认 harness 不应插入 preprocess 节点（保证 6 节点拓扑不变）。"""
    g = build_graph(SixNodeHarness())
    nodes = list(g.nodes.keys())
    assert "preprocess" not in nodes
    assert SixNodeHarness().has_preprocess is False


def test_overridden_preprocess_wires_node_and_edges():
    """子类覆盖 preprocess → 自动插入节点并接线到 route 之前。"""

    class PreHarness(SixNodeHarness):
        async def preprocess(self, state):
            return {"preprocessed": True}

    h = PreHarness()
    assert h.has_preprocess is True

    g = build_graph(h)
    nodes = list(g.nodes.keys())
    assert "preprocess" in nodes
    # START -> preprocess -> route 接线
    assert ("__start__", "preprocess") in g.edges
    assert ("preprocess", "route") in g.edges
    # 其余 6 核心节点仍在
    for n in ("route", "skill", "compact", "context_edit", "plan", "fan_out", "merge", "reflect", "answer"):
        assert n in nodes

    # 对照：默认 harness 仍无 preprocess 节点
    assert "preprocess" not in build_graph(SixNodeHarness()).nodes
