# -*- coding: utf-8 -*-
"""task-A1：可插拔 Harness 抽象包。

暴露：
- Harness：编排「大脑」抽象基类（route/plan/fan_out/merge/reflect/answer 六节点级实现可替换）
- SixNodeHarness：默认实现（= task24 现有 6 节点 DAG，行为零变化）
- build_harness / register_harness / HARNESS_IMPLEMENTATIONS：工厂与注册表
"""
from app.ai.harness.base import Harness
from app.ai.harness.registry import (
    HARNESS_IMPLEMENTATIONS,
    build_harness,
    register_harness,
)
from app.ai.harness.sixnode import SixNodeHarness

__all__ = [
    "Harness",
    "SixNodeHarness",
    "HARNESS_IMPLEMENTATIONS",
    "build_harness",
    "register_harness",
]
