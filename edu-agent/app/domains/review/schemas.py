"""课程系列评价域 schemas（Season-2 需求 B）。

契约：
- 评价列表分页外层 {total, page, page_size, items}（C-B 统一分页壳）；
- POST body：rating 1~5 必填，content 可选；
- 管理端删除返回已删语义（C-C 软删）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    """提交评价请求体。"""
    rating: int = Field(..., ge=1, le=5, description="评分 1~5（必填）")
    content: Optional[str] = Field(None, max_length=2000, description="评价内容（可选）")


class ReviewOut(BaseModel):
    """评价条目（含用户昵称联表）。"""
    id: int
    series_id: int
    user_id: int
    rating: int
    content: Optional[str] = None
    nickname: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ReviewPage(BaseModel):
    """评价列表分页（C-B {total,page,page_size,items} 权威）。"""
    total: int
    page: int
    page_size: int
    items: list[ReviewOut]