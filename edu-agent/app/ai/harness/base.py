# -*- coding: utf-8 -*-
"""task-A1：Harness 抽象基类（可插拔编排接口）。

定义编排「大脑」的六个节点级实现：route / plan / fan_out / merge / reflect / answer。
图结构（节点名 + 边）由 app.ai.graph.build_graph 固定编译，不因实现切换而改变；
模型升级 / 变体对比（task-E1 影子模式 / loop 候选）只需替换 Harness 实现（HARNESS_IMPL），不改图拓扑。

竞品对标（production-upgrade-plan.md P11）：
- Claude Managed Agents：Harness(大脑) / Sandbox(双手) / Session(记忆) 三可独立替换抽象层。
- Codex：codex-core Session→Turn→Step 三级模型，层级抽象可替换。

默认实现 SixNodeHarness 即 task24 现有 6 节点 DAG，行为零变化（task29 R8 keep_sixnode 裁定）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.ai.graph import AgentState


class Harness(ABC):
    """可插拔编排抽象：节点级实现可替换，图结构不变。

    所有方法均为异步、接收完整 AgentState、返回 LangGraph 节点更新 dict（含 nodes_executed trace）。
    签名与 app/ai/graph.py 现有节点函数（route_node / plan_node / fan_out_node / merge_node /
    reflect_node / answer_node）保持一致：``(state) -> dict``。
    """

    @abstractmethod
    async def route(self, state: AgentState) -> dict:
        """四类意图路由：写入 intent / effort（chitchat→L0 直答，其余→L1/L2）。"""

    @abstractmethod
    async def plan(self, state: AgentState) -> dict:
        """按意图 + effort 产出子代理任务清单 tasks[{subagent, objective, input}]。"""

    @abstractmethod
    async def fan_out(self, state: AgentState) -> dict:
        """并行子代理（task92 runner），主 state 收蒸馏摘要 subagent_results。"""

    @abstractmethod
    async def merge(self, state: AgentState) -> dict:
        """汇总 / 去重 / 冲突标注 merged_context。"""

    @abstractmethod
    async def reflect(self, state: AgentState) -> dict:
        """LLM-as-judge：写入 reflect_count / sufficient（达 MAX_REFLECT 强制放行）。"""

    @abstractmethod
    async def answer(self, state: AgentState) -> dict:
        """最终回答（strong 模型），写入 final_answer。"""
