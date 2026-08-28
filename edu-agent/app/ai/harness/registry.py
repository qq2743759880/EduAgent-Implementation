# -*- coding: utf-8 -*-
"""task-A1：Harness 注册表与工厂。

- HARNESS_IMPLEMENTATIONS：已注册实现映射（默认 sixnode）。
- build_harness(name=None)：按配置 HARNESS_IMPL（或显式 name）实例化。
- register_harness(name, cls)：注册自定义实现（task-E1 影子模式 / loop 变体 / 新模型 harness）。
- validate_harness_config()：启动校验 HARNESS_IMPL 合法性（task-A1 批判③）。

切换 HARNESS_IMPL 只换节点实现，图拓扑（节点名 + 边）不变（keep_sixnode）。
"""
from __future__ import annotations

import logging
from typing import Type

from app.ai.harness.base import Harness
from app.ai.harness.sixnode import SixNodeHarness
from app.config import settings

logger = logging.getLogger(__name__)


HARNESS_IMPLEMENTATIONS: dict[str, Type[Harness]] = {
    "sixnode": SixNodeHarness,
}


def register_harness(name: str, cls: Type[Harness]) -> None:
    """注册自定义 harness 实现（节点级可插拔的扩展点）。"""
    if not (isinstance(cls, type) and issubclass(cls, Harness)):
        raise TypeError(f"harness {name!r} 必须实现 Harness 抽象基类：{cls!r}")
    HARNESS_IMPLEMENTATIONS[name] = cls


def build_harness(name: str | None = None) -> Harness:
    """按 HARNESS_IMPL（或显式 name）实例化 harness。

    task-A1 批判③：未知 impl 不再抛进程级失败，回退 sixnode + 告警，
    保证配置错误不拖垮整图启动（fail-open 而非 fail-closed）。
    """
    name = name or getattr(settings, "HARNESS_IMPL", "sixnode")
    cls = HARNESS_IMPLEMENTATIONS.get(name)
    if cls is None:
        logger.warning(
            f"[harness] 未知 HARNESS_IMPL={name!r}，回退默认 sixnode；"
            f"已注册实现：{sorted(HARNESS_IMPLEMENTATIONS)}"
        )
        cls = SixNodeHarness
    return cls()


def validate_harness_config() -> "str | None":
    """启动校验 HARNESS_IMPL 合法性（task-A1 批判③）。

    返回 None 表示合法；否则返回错误描述（供启动 fail-fast / 告警使用）。
    注意：build_harness 已对未知值做 sixnode 回退，故此处仅做显式校验与告警，
    不阻断启动。
    """
    name = getattr(settings, "HARNESS_IMPL", "sixnode")
    if name not in HARNESS_IMPLEMENTATIONS:
        return f"HARNESS_IMPL={name!r} 未注册；可选：{sorted(HARNESS_IMPLEMENTATIONS)}"
    return None
