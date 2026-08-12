# -*- coding: utf-8 -*-
"""P4 思维导图 schemas（ECharts graph JSON 可直接消费）。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MindMapNode(BaseModel):
    """图节点。"""
    id: str = Field(..., description="node_code，前端 key 用")
    label: str = Field(..., description="节点类型标签：CourseSeries / CourseModule / KnowledgePoint / QuestionTag")
    name: str = Field(..., description="显示名")
    subject_code: str | None = None
    category: int = Field(0, description="ECharts 类目 index：0=系列 1=模块 2=知识点 3=题目标签；颜色区分")
    value: int = Field(1, ge=1, description="节点大小权重（下级数量或难度）")
    status: str = Field(
        "UNKNOWN", description="掌握状态：MASTERED 绿色 / IN_PROGRESS 蓝色 / NOT_STARTED 灰色 / BLOCKED 红色",
    )
    mastery_ratio: float = Field(0.0, ge=0, le=1, description="用户对该节点掌握度（进度表算）")
    x: float | None = Field(default=None, description="预留布局坐标，前端可覆盖")
    y: float | None = None


class MindMapLink(BaseModel):
    """图边。"""
    source: str = Field(..., description="源 node id")
    target: str = Field(..., description="目标 node id")
    rel_type: str = Field(..., description="CONTAINS / PREREQUISITE / RELATED_TO / TESTS")
    line_style: dict = Field(default_factory=dict, description="ECharts lineStyle 预置：{color, type, width}")


class MindMap(BaseModel):
    """完整思维导图返回（ECharts graph option 可直接渲染）。"""
    title: str
    subject_code: str | None = None
    categories: list[dict] = Field(
        default_factory=lambda: [
            {"name": "系列课程"},
            {"name": "模块"},
            {"name": "知识点"},
            {"name": "题目标签"},
        ],
    )
    nodes: list[MindMapNode]
    links: list[MindMapLink]
    stats: dict = Field(default_factory=dict, description="统计：节点总数/边数/已掌握数/进行中数 等")
    legend: list[str] = Field(
        default_factory=lambda: ["CONTAINS (包含)", "PREREQUISITE (先修)", "RELATED_TO (相关)", "TESTS (考核)"],
    )
    level: str | None = Field(default=None, description="L1-L5 概览难度")

    model_config = ConfigDict(extra="ignore")
