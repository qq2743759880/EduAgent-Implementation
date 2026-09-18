# -*- coding: utf-8 -*-
"""R-M1 学习事件流 DTO（契约权威；契约草案 contracts/reshape-r-analytics.json 同步登记）。

响应壳 {code:0, message:"ok", data} 由 app.core.resp.ok 统一包裹；
本文件只声明 data 部分（对齐 progress/schemas.py 等既有域的裸 DTO 分页/明细口径）。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LearningEventSummaryItem(BaseModel):
    """按事件类型的聚合项。"""
    type: str = Field(..., description="事件类型：video_heartbeat|quiz_submit|session_complete")
    count: int = Field(..., ge=0, description="时间窗内事件数")
    last_active_at: str | None = Field(None, description="该类型最近活跃时间（ISO8601，服务器本地时区）")


class LearningEventSummary(BaseModel):
    """GET /api/analytics/learning-events/summary 的 data。"""
    user_id: int = Field(..., ge=1, description="目标用户（student 恒为本人）")
    range: str = Field(..., description="时间窗键：1d|7d|30d|90d")
    range_days: int = Field(..., ge=1, le=90, description="时间窗天数")
    total: int = Field(..., ge=0, description="时间窗内事件总数")
    by_type: list[LearningEventSummaryItem] = Field(default_factory=list, description="按 type 聚合（count 降序）")
    first_ts: str | None = Field(None, description="时间窗内最早事件时间（无事件为 null）")
    last_ts: str | None = Field(None, description="时间窗内最近事件时间（无事件为 null）")
    generated_at: str = Field(..., description="聚合生成时间（ISO8601）")


class LearningEventStreamStats(BaseModel):
    """GET /api/analytics/learning-events/stream-stats 的 data（事件流运行态观测）。"""
    enabled: bool = Field(..., description="MONGO_EVENT_ENABLED 开关状态")
    worker_running: bool = Field(..., description="后台消费 task 是否在跑")
    queue_size: int = Field(..., ge=0, description="当前队列积压")
    queue_maxsize: int = Field(..., ge=1, description="队列上限")
    breaker_state: str = Field(..., description="mongo 写熔断器状态：closed|open|half_open")
    collection: str = Field(..., description="mongo 集合名（learning_event）")
    counters: dict = Field(default_factory=dict, description="enqueue/写成功/重试/丢弃计数器")
