# -*- coding: utf-8 -*-
"""task-A1：Harness 注册表与工厂。

- HARNESS_IMPLEMENTATIONS：已注册实现映射（默认 sixnode）。
- build_harness(name=None)：按配置 HARNESS_IMPL（或显式 name）实例化。
- register_harness(name, cls)：注册自定义实现（task-E1 影子模式 / loop 变体 / 新模型 harness）。

切换 HARNESS_IMPL 只换节点实现，图拓扑（节点名 + 边）不变（keep_sixnode）。
"""
from __future__ import annotations

from typing import Type

from app.ai.harness.base import Harness
from app.ai.harness.sixnode import SixNodeHarness
from app.config import settings


HARNESS_IMPLEMENTATIONS: dict[str, Type[Harness]] = {
    "sixnode": SixNodeHarness,
}


def register_harness(name: str, cls: Type[Harness]) -> None:
    """注册自定义 harness 实现（节点级可插拔的扩展点）。"""
    if not (isinstance(cls, type) and issubclass(cls, Harness)):
        raise TypeError(f"harness {name!r} 必须实现 Harness 抽象基类：{cls!r}")
    HARNESS_IMPLEMENTATIONS[name] = cls


def build_harness(name: str | None = None) -> Harness:
    """按 HARNESS_IMPL（或显式 name）实例化 harness。"""
    name = name or getattr(settings, "HARNESS_IMPL", "sixnode")
    cls = HARNESS_IMPLEMENTATIONS.get(name)
    if cls is None:
        raise ValueError(
            f"未知 HARNESS_IMPL={name!r}；已注册实现：{sorted(HARNESS_IMPLEMENTATIONS)}"
        )
    return cls()
