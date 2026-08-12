# -*- coding: utf-8 -*-
"""P6 社区 forum schemas：发帖/回帖/反应 + 分页列表。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


BOARDS = {"english", "math", "programming", "general"}
LIKE = "LIKE"
FAVORITE = "FAVORITE"
TARGET_POST = "POST"
TARGET_COMMENT = "COMMENT"
COMMENT_SORT_HOT = "HOT"
COMMENT_SORT_NEW = "NEW"


class PostCreate(BaseModel):
    board_code: str = Field("general", pattern=r"^(english|math|programming|general)$", max_length=32)
    title: str = Field(..., min_length=2, max_length=200)
    content_md: str = Field(..., min_length=2, max_length=20000)
    tags: list[str] = Field(default_factory=list, max_length=8, description="标签列表，最多 8 个")


class PostUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    content_md: str | None = Field(default=None, max_length=20000)
    tags: list[str] | None = Field(default=None, max_length=8)
    is_pinned: bool | None = None
    is_locked: bool | None = None


class PostListItem(BaseModel):
    post_id: int
    board_code: str
    author_id: int
    author_name: str | None
    title: str
    summary: str
    tags: list[str]
    is_pinned: bool
    is_locked: bool
    view_count: int
    like_count: int
    comment_count: int
    favorite_count: int
    hot_score: float
    mine_react_like: bool = False
    mine_react_favorite: bool = False
    created_at: datetime
    updated_at: datetime


class PostDetail(PostListItem):
    content_md: str


class PostListResp(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[PostListItem]
    mine_total_posts: int = 0


class CommentCreate(BaseModel):
    content_md: str = Field(..., min_length=1, max_length=5000)
    parent_id: int | None = None
    reply_to_id: int | None = None


class CommentItem(BaseModel):
    comment_id: int
    post_id: int
    author_id: int
    author_name: str | None
    parent_id: int | None
    reply_to_id: int | None
    content_md: str
    like_count: int
    mine_liked: bool = False
    created_at: datetime


class CommentListResp(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[CommentItem]


class ReactToggleResp(BaseModel):
    target_type: str
    target_id: int
    react_type: str
    active: bool
    total_count: int
    points_awarded: int = 0


class PostCreateResp(BaseModel):
    post_id: int
    points_awarded: int = 0
    badge_unlocked: list[str] = []
