# -*- coding: utf-8 -*-
"""P6 社区 forum router：6 条 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.auth.dependencies import CurrentUser, get_current_user

from . import service
from .schemas import (
    BOARDS, CommentCreate, CommentListResp, FAVORITE, LIKE, PostCreate,
    PostDetail, PostListResp, PostUpdate, ReactToggleResp, TARGET_COMMENT,
    TARGET_POST,
)

router = APIRouter(prefix="/api/community", tags=["社区论坛"])


@router.get("/posts", response_model=PostListResp, summary="社区帖子分页列表（按版块/作者/关键词/热度）")
async def community_posts_list(
    current_user: CurrentUser = Depends(get_current_user),
    board_code: str | None = Query(default=None, description="english/math/programming/general，空=全部"),
    author_id: int | None = None,
    keyword: str | None = Query(default=None, max_length=60),
    sort: str = Query(default="HOT", pattern="^(HOT|NEW|LIKE)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PostListResp:
    if board_code and board_code not in BOARDS:
        raise HTTPException(status_code=422, detail=f"board_code 只允许 {sorted(BOARDS)}")
    return await service.list_posts(
        current_user.user_id, board_code=board_code, author_id=author_id,
        keyword=keyword, sort=sort, page=page, page_size=page_size,
    )


@router.post("/posts", response_model=dict, summary="发帖")
async def community_post_create(
    payload: PostCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await service.create_post(current_user.user_id, current_user.nickname, payload)


@router.get("/posts/{post_id}", response_model=PostDetail, summary="帖子详情（浏览量自动+1）")
async def community_post_detail(
    post_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
) -> PostDetail:
    detail = await service.get_post_detail(current_user.user_id, post_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="帖子不存在")
    return detail


@router.patch("/posts/{post_id}", summary="改帖（作者本人；置顶/锁帖管理员）")
async def community_post_update(
    payload: PostUpdate,
    post_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        ok = await service.update_post(current_user.user_id, post_id, payload)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="帖子不存在")
    return {"ok": True}


@router.post("/posts/{post_id}/like", response_model=ReactToggleResp, summary="点赞/取消点赞 帖子")
async def community_post_like(
    post_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReactToggleResp:
    from app.database import fetch_one as _fetch_one
    row = await _fetch_one("SELECT author_id FROM community_post WHERE id=%s AND yn=1", (post_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="帖子不存在")
    author_id = int(row["author_id"] or 0)
    return await service.toggle_react(
        current_user.user_id, TARGET_POST, post_id, LIKE, author_id_if_known=author_id,
    )


@router.post("/posts/{post_id}/favorite", response_model=ReactToggleResp, summary="收藏/取消收藏 帖子")
async def community_post_favorite(
    post_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReactToggleResp:
    from app.database import fetch_one as _fetch_one
    row = await _fetch_one("SELECT author_id FROM community_post WHERE id=%s AND yn=1", (post_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="帖子不存在")
    return await service.toggle_react(
        current_user.user_id, TARGET_POST, post_id, FAVORITE,
        author_id_if_known=int(row["author_id"] or 0),
    )


@router.get("/posts/{post_id}/comments", response_model=CommentListResp, summary="评论列表")
async def community_comments_list(
    post_id: int = Path(..., ge=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
) -> CommentListResp:
    return await service.list_comments(current_user.user_id, post_id, page=page, page_size=page_size)


@router.post("/posts/{post_id}/comments", response_model=CommentListResp | dict, summary="回帖（一楼或回复）")
async def community_comment_create(
    payload: CommentCreate,
    post_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        item = await service.create_comment(current_user.user_id, current_user.nickname, post_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"comment_id": item.comment_id, "created_at": item.created_at, "points": 2}


@router.post("/comments/{comment_id}/like", response_model=ReactToggleResp, summary="点赞评论")
async def community_comment_like(
    comment_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReactToggleResp:
    from app.database import fetch_one as _fetch_one
    row = await _fetch_one("SELECT author_id FROM community_comment WHERE id=%s AND yn=1", (comment_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="评论不存在")
    return await service.toggle_react(
        current_user.user_id, TARGET_COMMENT, comment_id, LIKE,
        author_id_if_known=int(row["author_id"] or 0),
    )
