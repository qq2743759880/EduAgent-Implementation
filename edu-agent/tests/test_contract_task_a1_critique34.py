# -*- coding: utf-8 -*-
"""task-A1 批判③④ 契约：未知 impl fallback（批判③）+ 拓扑常量化 fail-fast 自检（批判④）。

AC-A1-③-1 未知 HARNESS_IMPL 不抛进程级失败：build_harness 回退 sixnode + 告警。
AC-A1-③-2 启动校验 HARNESS_IMPL 合法性：validate_harness_config 对非法值返回错误描述。
AC-A1-④-1 拓扑锁定常量化：EXPECTED_SIXNODE_* 与默认 build_graph 拓扑完全一致。
AC-A1-④-2 启动 fail-fast 自检：_selfcheck_sixnode_topology 在拓扑正确时不抛错（错误时立即暴露）。
"""
from __future__ import annotations

import pytest

from app.ai import graph as graph_mod
from app.ai.harness import registry as registry_mod
from app.ai.harness.base import Harness
from app.ai.harness.sixnode import SixNodeHarness


class TestCritique3UnknownImplFallback:
    def test_unknown_impl_falls_back_to_sixnode(self):
        """批判③：未知 impl 回退 sixnode，不抛 ValueError。"""
        h = registry_mod.build_harness("__nonexistent_impl__")
        assert isinstance(h, SixNodeHarness), "未知 impl 必须回退默认 sixnode"

    def test_validate_config_ok_for_default(self):
        """批判③：默认 sixnode 配置合法，validate 返回 None。"""
        err = registry_mod.validate_harness_config()
        assert err is None, f"默认 sixnode 配置应合法，实得：{err}"

    def test_validate_config_reports_unknown(self, monkeypatch):
        """批判③：非法 HARNESS_IMPL 经 validate 返回错误描述（fail-fast / 告警用）。"""

        class _FakeSettings:
            HARNESS_IMPL = "ghost_impl"

        monkeypatch.setattr(registry_mod, "settings", _FakeSettings())
        err = registry_mod.validate_harness_config()
        assert err is not None
        assert "ghost_impl" in err


class TestCritique4TopologyFailFast:
    def test_expected_topology_matches_build_graph(self):
        """批判④：EXPECTED_SIXNODE_* 常量与默认 build_graph 拓扑逐字节一致。"""
        g = graph_mod.build_graph()
        nodes = tuple(sorted(g.nodes.keys()))
        edges = []
        for e in g.edges:
            if isinstance(e, tuple) and len(e) >= 2:
                edges.append((e[0], e[1]))
            else:
                edges.append((getattr(e, "source"), getattr(e, "target")))
        edges = tuple(sorted(edges))
        assert nodes == graph_mod.EXPECTED_SIXNODE_NODES
        assert edges == graph_mod.EXPECTED_SIXNODE_EDGES
        assert set(g.branches.keys()) == set(graph_mod.EXPECTED_SIXNODE_BRANCHES)

    def test_selfcheck_topology_passes(self):
        """批判④：拓扑正确时 _selfcheck_sixnode_topology 不抛错（fail-fast 自检通过）。"""
        graph_mod._selfcheck_sixnode_topology()  # 不应抛 RuntimeError

    def test_selfcheck_topology_fails_on_drift(self, monkeypatch):
        """批判④：拓扑漂移时 _selfcheck_sixnode_topology 立即 fail-fast 抛错。"""
        import app.ai.graph as _g

        bad = list(_g.EXPECTED_SIXNODE_NODES) + ["preprocess"]
        monkeypatch.setattr(_g, "EXPECTED_SIXNODE_NODES", tuple(sorted(bad)))
        with pytest.raises(RuntimeError):
            _g._selfcheck_sixnode_topology()
