# -*- coding: utf-8 -*-
"""P6 社区 forum router：6 条 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from app.auth.dependencies import CurrentUser, get_current_user
from app.common.error_codes import (
    COMMUNITY_BOARD_INVALID,
    COMMUNITY_COMMENT_NOT_FOUND,
    COMMUNITY_POST_NOT_FOUND,
)
from app.common.exceptions import BadRequestError, PermissionDeniedError, ResourceNotFoundError
from app.core.resp import ok

from . import service
from .schemas import (
    BOARDS, CommentCreate, CommentListResp, FAVORITE, LIKE, PostCreate,
    PostDetail, PostListResp, PostUpdate, ReactToggleResp, TARGET_COMMENT,
    TARGET_POST,
)

router = APIRouter(prefix="/api/community", tags=["社区论坛"])


@router.get("/posts", summary="社区帖子分页列表（按版块/作者/关键词/热度）")
async def community_posts_list(
    current_user: CurrentUser = Depends(get_current_user),
    board_code: str | None = Query(default=None, description="english/math/programming/general，空=全部"),
    author_id: int | None = None,
    keyword: str | None = Query(default=None, max_length=60),
    sort: str = Query(default="HOT", pattern="^(HOT|NEW|LIKE)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    if board_code and board_code not in BOARDS:
        raise BadRequestError(
            f"board_code 只允许 {sorted(BOARDS)}",
            code=COMMUNITY_BOARD_INVALID,
        )
    return ok(await service.list_posts(
        current_user.user_id, board_code=board_code, author_id=author_id,
        keyword=keyword, sort=sort, page=page, page_size=page_size,
    ))


@router.post("/posts", response_model=dict, summary="发帖")
async def community_post_create(
    payload: PostCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    return ok(await service.create_post(current_user.user_id, current_user.nickname, payload))


@router.get("/posts/{post_id}", summary="帖子详情（浏览量自动+1）")
async def community_post_detail(
    post_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    detail = await service.get_post_detail(current_user.user_id, post_id)
    if detail is None:
        raise ResourceNotFoundError("帖子不存在", code=COMMUNITY_POST_NOT_FOUND)
    return ok(detail)


@router.patch("/posts/{post_id}", summary="改帖（作者本人；置顶/锁帖管理员）")
async def community_post_update(
    payload: PostUpdate,
    post_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    try:
        updated = await service.update_post(current_user.user_id, post_id, payload)
    except PermissionDeniedError:
        raise
    if not updated:
        raise ResourceNotFoundError("帖子不存在", code=COMMUNITY_POST_NOT_FOUND)
    return ok({"ok": True})


@router.post("/posts/{post_id}/like", summary="点赞/取消点赞 帖子")
async def community_post_like(
    post_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    from app.database import fetch_one as _fetch_one
    row = await _fetch_one("SELECT author_id FROM community_post WHERE id=%s AND yn=1", (post_id,))
    if row is None:
        raise ResourceNotFoundError("帖子不存在", code=COMMUNITY_POST_NOT_FOUND)
    author_id = int(row["author_id"] or 0)
    return ok(await service.toggle_react(
        current_user.user_id, TARGET_POST, post_id, LIKE, author_id_if_known=author_id,
    ))


@router.post("/posts/{post_id}/favorite", summary="收藏/取消收藏 帖子")
async def community_post_favorite(
    post_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    from app.database import fetch_one as _fetch_one
    row = await _fetch_one("SELECT author_id FROM community_post WHERE id=%s AND yn=1", (post_id,))
    if row is None:
        raise ResourceNotFoundError("帖子不存在", code=COMMUNITY_POST_NOT_FOUND)
    return ok(await service.toggle_react(
        current_user.user_id, TARGET_POST, post_id, FAVORITE,
        author_id_if_known=int(row["author_id"] or 0),
    ))


@router.get("/posts/{post_id}/comments", summary="评论列表")
async def community_comments_list(
    post_id: int = Path(..., ge=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    return ok(await service.list_comments(current_user.user_id, post_id, page=page, page_size=page_size))


@router.post("/posts/{post_id}/comments", response_model=dict, summary="回帖（一楼或回复）")
async def community_comment_create(
    payload: CommentCreate,
    post_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    try:
        item = await service.create_comment(current_user.user_id, current_user.nickname, post_id, payload)
    except (BadRequestError, ResourceNotFoundError):
        raise
    return ok({"comment_id": item.comment_id, "created_at": item.created_at, "points": 2})


@router.post("/comments/{comment_id}/like", summary="点赞评论")
async def community_comment_like(
    comment_id: int = Path(..., ge=1),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    from app.database import fetch_one as _fetch_one
    row = await _fetch_one("SELECT author_id FROM community_comment WHERE id=%s AND yn=1", (comment_id,))
    if row is None:
        raise ResourceNotFoundError("评论不存在", code=COMMUNITY_COMMENT_NOT_FOUND)
    return ok(await service.toggle_react(
        current_user.user_id, TARGET_COMMENT, comment_id, LIKE,
        author_id_if_known=int(row["author_id"] or 0),
    ))
