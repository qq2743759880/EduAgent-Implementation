# -*- coding: utf-8 -*-
"""P4 推荐引擎 schemas。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ========== 1. 单条推荐项目 ==========

class RecommendedCourse(BaseModel):
    """推荐的课程系列 / 模块 / 知识点节点。"""
    item_type: str = Field(..., description="SERIES / MODULE / KNOWLEDGE_POINT / QUESTION_TAG")
    item_code: str = Field(..., description="业务 code：对齐 graph_node.code")
    item_name: str
    subject_code: str | None = None
    level_code: str | None = Field(default=None, description="L1-L5 估算难度")
    score: float = Field(..., ge=0, description="推荐得分（越高越靠前）")
    reason: str = Field(..., description="推荐原因：学科偏好命中 / 先修满足 / 同画像用户热门")
    estimated_hours: float | None = Field(default=None, ge=0, description="预计耗时（小时）")
    prerequisite_codes: list[str] = Field(default_factory=list)
    mastery_ratio: float = Field(0.0, ge=0, le=1, description="当前用户对该节点已掌握比例（0 未知 → 1 已掌握）")
    source: str = Field("mysql", description="图谱来源：neo4j=来自 Neo4j 图谱，mysql=来自 MySQL 图")
    extra: dict[str, Any] = Field(default_factory=dict)


# ========== 2. 学习路径（完整 6 周 / 8 周 计划） ==========

class PathNode(BaseModel):
    """路径中的一个步骤节点。"""
    step_no: int = Field(..., ge=1)
    node_type: str = Field(..., description="MODULE / KNOWLEDGE_POINT / EXAM / PROJECT")
    node_code: str
    node_name: str
    subject_code: str | None = None
    duration_hours: float = Field(..., ge=0)
    suggestion: str = Field(..., max_length=300, description="学习建议，如「先看对应视频，完成课后习题，再做 EX-xxx 试卷」")
    prerequisite_codes: list[str] = Field(default_factory=list)
    source: str = Field("mysql", description="图谱来源：neo4j=来自 Neo4j 图谱，mysql=来自 MySQL 图")


class LearningPath(BaseModel):
    """对单个用户的个性化学习路径完整返回。"""
    path_code: str = Field(..., description="唯一码，可持久化到 learning_path_instance & 反馈")
    title: str
    subject_code: str | None = None
    target_level: str | None = Field(default=None, description="目标级别，如 L2 / L3")
    total_sessions: int = Field(..., ge=0)
    total_hours: float = Field(..., ge=0)
    rationale: str = Field(..., max_length=500, description="路径生成理由：画像 + 先修链匹配说明")
    nodes: list[PathNode] = Field(..., min_length=1)
    saved_instance_id: int | None = Field(default=None, description="learning_path_instance.id（若已持久化）")
    created_at: datetime = Field(default_factory=datetime.now)
    graph_source: str = Field("mysql", description="路径图谱来源：neo4j=含 Neo4j 图谱节点，mysql=纯 MySQL 图")

    model_config = ConfigDict(extra="ignore")


# ========== 3. 反馈接口 ==========

class RecommendFeedbackIn(BaseModel):
    """推荐反馈：对某条推荐项目或路径点 ✅/❌/⏭。"""
    scene_code: str = Field(..., pattern=r"^(PATH|NEXT|NODE)$")
    target_id: str = Field(..., max_length=128)
    feedback_type: str = Field(..., pattern=r"^(HELPFUL|NOT_INTERESTED|ALREADY_LEARNED|TOO_HARD)$")
    note: str | None = Field(default=None, max_length=500)


class RecommendFeedbackOut(BaseModel):
    scene_code: str
    target_id: str
    feedback_type: str
    score_delta: float
    ok: bool = True


# ========== 4. 下一步推荐（轻量 API，用于前端学习卡片底部「接下来学什么」） ==========

class NextStepOut(BaseModel):
    items: list[RecommendedCourse] = Field(..., description="按得分降序 TOP N，默认 TOP 5")
    strategy_weights: dict[str, float] = Field(..., description="本次融合各策略权重：cold/cf/graph/feedback")
    graph_source: str = Field("mysql", description="图谱来源：neo4j=图谱候选含 Neo4j 来源，mysql=纯 MySQL 图")
