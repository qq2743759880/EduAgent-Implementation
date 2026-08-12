# -*- coding: utf-8 -*-
"""P6 社区 forum service：发帖/回帖/反应/分页列表/详情(浏览量+1)。
积分&徽章联动：通过 `app.gamification.service` 函数入口（import 时懒加载避免环）。
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any

from app.database import execute_write, fetch_all, fetch_one

from .schemas import (
    BOARDS, CommentCreate, CommentItem, CommentListResp,
    FAVORITE as _FAV, LIKE as _LK, PostCreate, PostDetail, PostListItem,
    PostListResp, PostUpdate, ReactToggleResp, TARGET_COMMENT, TARGET_POST,
)

REACT_LIKE = _LK
REACT_FAVORITE = _FAV
COMMENT = "COMMENT"


# ========== 1. 发帖 ==========
async def create_post(user_id: int, display_name: str | None, payload: PostCreate) -> dict:
    tags_json = json.dumps(payload.tags or [], ensure_ascii=False)
    insert_sql = (
        "INSERT INTO community_post (board_code, author_id, author_name, title, content_md, tags_json)"
        " VALUES (%s, %s, %s, %s, %s, %s)"
    )
    pid = await execute_write(insert_sql, (
        payload.board_code, user_id, display_name or f"用户{user_id}",
        payload.title, payload.content_md, tags_json,
    ))
    # 发帖积分奖励 + 徽章检查（懒加载避免环）
    points_awarded = 0
    unlocked: list[str] = []
    try:
        from app.gamification.service import award_points, check_and_unlock_badges
        points_awarded = await award_points(
            user_id, biz_key=f"community-post-{pid}",
            point_type="POST_CREATE", delta=5, note=f"发帖 {pid}",
        )
        unlocked = await check_and_unlock_badges(user_id, event_scope="POST")
    except Exception:
        pass
    return {"post_id": int(pid), "points_awarded": points_awarded, "badge_unlocked": unlocked}


# ========== 2. 分页列表（支持 版块/作者/搜索/热度 or 时间 排序） ==========
async def list_posts(user_id: int, *, board_code: str | None = None,
                     author_id: int | None = None, keyword: str | None = None,
                     sort: str = "HOT", page: int = 1, page_size: int = 20) -> PostListResp:
    where = ["P.yn=1"]
    args: list[Any] = []
    if board_code and board_code in BOARDS:
        where.append("P.board_code=%s")
        args.append(board_code)
    if author_id:
        where.append("P.author_id=%s")
        args.append(author_id)
    if keyword:
        kw = f"%{keyword}%"
        where.append("(P.title LIKE %s OR P.content_md LIKE %s)")
        args += [kw, kw]
    order_by = {
        "HOT": "P.is_pinned DESC, P.hot_score DESC, P.created_at DESC",
        "NEW": "P.is_pinned DESC, P.created_at DESC",
        "LIKE": "P.is_pinned DESC, P.like_count DESC, P.created_at DESC",
    }.get(sort, "P.is_pinned DESC, P.hot_score DESC, P.created_at DESC")

    sql_base = f" FROM community_post P WHERE {' AND '.join(where)}"
    total_row = await fetch_one(f"SELECT COUNT(*) AS c {sql_base}", tuple(args))
    total = int(total_row["c"] or 0) if total_row else 0
    offset = max(0, (page - 1) * page_size)
    sql = (
        f"SELECT P.* {sql_base} ORDER BY {order_by} LIMIT %s OFFSET %s"
    )
    rows = await fetch_all(sql, tuple(args) + (page_size, offset))

    # 个人帖子数
    mine_row = await fetch_one(
        "SELECT COUNT(*) c FROM community_post WHERE yn=1 AND author_id=%s", (user_id,),
    )
    mine_total = int(mine_row["c"] or 0) if mine_row else 0

    # 当前用户的反应（批量化 IN）
    post_ids = [int(r["id"]) for r in rows]
    my_react_like: set[int] = set()
    my_react_fav: set[int] = set()
    if post_ids:
        ph = ",".join(["%s"] * len(post_ids))
        r_rows = await fetch_all(
            f"SELECT target_id, react_type FROM community_react "
            f"WHERE user_id=%s AND target_type='POST' AND target_id IN ({ph}) AND yn=1",
            (user_id, *post_ids),
        )
        for r in r_rows:
            if r["react_type"] == REACT_LIKE:
                my_react_like.add(int(r["target_id"]))
            elif r["react_type"] == REACT_FAVORITE:
                my_react_fav.add(int(r["target_id"]))

    items = [_row_to_list_item(r, my_react_like, my_react_fav) for r in rows]
    return PostListResp(total=total, page=page, page_size=page_size,
                        items=items, mine_total_posts=mine_total)


def _row_to_list_item(r: dict, my_like: set[int], my_fav: set[int]) -> PostListItem:
    title = r.get("title") or ""
    content = r.get("content_md") or ""
    summary = content[:120].strip() + ("…" if len(content) > 120 else "")
    tags = []
    try:
        tags = json.loads(r.get("tags_json") or "[]")
    except Exception:
        tags = []
    pid = int(r["id"])
    return PostListItem(
        post_id=pid, board_code=r.get("board_code") or "general",
        author_id=int(r["author_id"] or 0), author_name=r.get("author_name"),
        title=title, summary=summary, tags=tags if isinstance(tags, list) else [],
        is_pinned=bool(r.get("is_pinned")), is_locked=bool(r.get("is_locked")),
        view_count=int(r.get("view_count") or 0),
        like_count=int(r.get("like_count") or 0),
        comment_count=int(r.get("comment_count") or 0),
        favorite_count=int(r.get("favorite_count") or 0),
        hot_score=float(r.get("hot_score") or 0.0),
        mine_react_like=pid in my_like, mine_react_favorite=pid in my_fav,
        created_at=r.get("created_at") or datetime.utcnow(),
        updated_at=r.get("updated_at") or datetime.utcnow(),
    )


# ========== 3. 详情（浏览量 +1，顺带刷新热度分） ==========
async def get_post_detail(user_id: int, post_id: int) -> PostDetail | None:
    await execute_write(
        "UPDATE community_post SET view_count = view_count + 1 WHERE id=%s AND yn=1",
        (post_id,),
    )
    row = await fetch_one(
        "SELECT * FROM community_post WHERE id=%s AND yn=1", (post_id,),
    )
    if row is None:
        return None
    await _refresh_hot_score(post_id, row)
    row = await fetch_one("SELECT * FROM community_post WHERE id=%s AND yn=1", (post_id,))
    rset = {post_id} if row else set()
    my_like, my_fav = set(), set()
    if row:
        r_rows = await fetch_all(
            "SELECT react_type FROM community_react WHERE user_id=%s AND target_type='POST' AND target_id=%s AND yn=1",
            (user_id, post_id),
        )
        for rr in r_rows:
            if rr["react_type"] == REACT_LIKE:
                my_like.add(post_id)
            if rr["react_type"] == REACT_FAVORITE:
                my_fav.add(post_id)
    base = _row_to_list_item(row, my_like, my_fav)
    detail = PostDetail(**base.model_dump(), content_md=row.get("content_md") or "")
    return detail


# ========== 4. 反应切换（点赞/收藏） ==========
async def toggle_react(user_id: int, target_type: str, target_id: int,
                       react_type: str, author_id_if_known: int | None = None) -> ReactToggleResp:
    assert target_type in {TARGET_POST, TARGET_COMMENT}, f"非法 target_type {target_type}"
    assert react_type in {REACT_LIKE, REACT_FAVORITE}, f"非法 react_type {react_type}"

    # 幂等查询当前状态
    exist = await fetch_one(
        "SELECT id, yn FROM community_react "
        "WHERE user_id=%s AND target_type=%s AND target_id=%s AND react_type=%s LIMIT 1",
        (user_id, target_type, target_id, react_type),
    )
    active: bool
    if exist is None:
        await execute_write(
            "INSERT INTO community_react (user_id, target_type, target_id, react_type, yn)"
            " VALUES (%s, %s, %s, %s, 1)",
            (user_id, target_type, target_id, react_type),
        )
        active = True
    else:
        cur_yn = 1 if int(exist.get("yn") or 0) == 1 else 0
        new_yn = 0 if cur_yn == 1 else 1
        await execute_write(
            "UPDATE community_react SET yn=%s WHERE id=%s", (new_yn, int(exist["id"])),
        )
        active = new_yn == 1

    # 更新聚合计数
    sign = 1 if active else -1
    inc_map = {
        (TARGET_POST, REACT_LIKE): "like_count",
        (TARGET_POST, REACT_FAVORITE): "favorite_count",
        (TARGET_COMMENT, REACT_LIKE): "like_count",
    }
    col = inc_map.get((target_type, react_type))
    if col:
        if target_type == TARGET_POST:
            await execute_write(
                f"UPDATE community_post SET {col} = GREATEST(CAST({col} AS SIGNED) + %s, 0) WHERE id=%s",
                (sign, target_id),
            )
        else:
            await execute_write(
                f"UPDATE community_comment SET {col} = GREATEST(CAST({col} AS SIGNED) + %s, 0) WHERE id=%s",
                (sign, target_id),
            )
    # 刷新帖子热度分
    post_id = target_id if target_type == TARGET_POST else None
    if post_id:
        prow = await fetch_one("SELECT * FROM community_post WHERE id=%s", (post_id,))
        if prow:
            await _refresh_hot_score(post_id, prow)

    total = await _count_react(target_type, target_id, react_type)

    # 作者积分（获赞 → 2/赞）与徽章：只在 LIKE 激活，且 作者!=自己
    points_awarded = 0
    if active and react_type == REACT_LIKE and author_id_if_known and author_id_if_known != user_id:
        try:
            from app.gamification.service import award_points, check_and_unlock_badges
            scope = "POST_LIKE" if target_type == TARGET_POST else "COMMENT_LIKE"
            points_awarded = await award_points(
                author_id_if_known,
                biz_key=f"like-{target_type.lower()}-{target_id}-by-{user_id}",
                point_type="LIKE_GAIN", delta=2,
                note=f"社区 {target_type} #{target_id} 获赞 uid={user_id}",
            )
            await check_and_unlock_badges(author_id_if_known, event_scope=scope)
        except Exception:
            pass

    return ReactToggleResp(target_type=target_type, target_id=target_id,
                           react_type=react_type, active=active,
                           total_count=total, points_awarded=points_awarded)


async def _count_react(target_type: str, target_id: int, react_type: str) -> int:
    r = await fetch_one(
        "SELECT COUNT(*) c FROM community_react "
        "WHERE target_type=%s AND target_id=%s AND react_type=%s AND yn=1",
        (target_type, target_id, react_type),
    )
    return int(r["c"] or 0) if r else 0


# ========== 5. 评论 / 回复 ==========
async def create_comment(user_id: int, display_name: str | None, post_id: int,
                         payload: CommentCreate) -> CommentItem:
    # 锁帖校验
    post = await fetch_one("SELECT id, is_locked FROM community_post WHERE id=%s AND yn=1", (post_id,))
    if post is None:
        raise ValueError(f"帖子不存在 {post_id}")
    if bool(post.get("is_locked")):
        raise ValueError("帖子已锁定，不可评论")

    cid = await execute_write(
        "INSERT INTO community_comment (post_id, author_id, author_name, parent_id, reply_to_id, content_md)"
        " VALUES (%s, %s, %s, %s, %s, %s)",
        (post_id, user_id, display_name or f"用户{user_id}",
         payload.parent_id, payload.reply_to_id, payload.content_md),
    )
    # 评论数 + 1
    await execute_write(
        "UPDATE community_post SET comment_count = comment_count + 1 WHERE id=%s",
        (post_id,),
    )
    prow = await fetch_one("SELECT * FROM community_post WHERE id=%s", (post_id,))
    if prow:
        await _refresh_hot_score(post_id, prow)

    points = 0
    try:
        from app.gamification.service import award_points
        points = await award_points(
            user_id, biz_key=f"community-comment-{cid}",
            point_type="COMMENT_CREATE", delta=2, note=f"回帖 #{cid} on post {post_id}",
        )
    except Exception:
        pass

    row = await fetch_one("SELECT * FROM community_comment WHERE id=%s", (cid,))
    return _row_to_comment(row or {}, user_id_liked=user_id if False else None,
                           liked_ids=set())


async def list_comments(user_id: int, post_id: int, *, page: int = 1,
                        page_size: int = 20) -> CommentListResp:
    where = ["post_id=%s", "yn=1"]
    args: list[Any] = [post_id]
    base_sql = f" FROM community_comment WHERE {' AND '.join(where)}"
    total_row = await fetch_one(f"SELECT COUNT(*) c {base_sql}", tuple(args))
    total = int(total_row["c"] or 0) if total_row else 0
    offset = max(0, (page - 1) * page_size)
    rows = await fetch_all(
        f"SELECT * {base_sql} ORDER BY parent_id IS NULL DESC, created_at ASC LIMIT %s OFFSET %s",
        tuple(args) + (page_size, offset),
    )
    cids = [int(r["id"]) for r in rows]
    liked_ids: set[int] = set()
    if cids:
        ph = ",".join(["%s"] * len(cids))
        lr = await fetch_all(
            f"SELECT target_id FROM community_react "
            f"WHERE user_id=%s AND target_type='COMMENT' AND react_type='LIKE' AND yn=1 AND target_id IN ({ph})",
            (user_id, *cids),
        )
        for x in lr:
            liked_ids.add(int(x["target_id"]))
    items = [_row_to_comment(r, user_id, liked_ids) for r in rows]
    return CommentListResp(total=total, page=page, page_size=page_size, items=items)


def _row_to_comment(r: dict, user_id_liked: int | None, liked_ids: set[int]) -> CommentItem:
    cid = int(r.get("id") or 0)
    return CommentItem(
        comment_id=cid,
        post_id=int(r.get("post_id") or 0),
        author_id=int(r.get("author_id") or 0),
        author_name=r.get("author_name"),
        parent_id=r.get("parent_id"),
        reply_to_id=r.get("reply_to_id"),
        content_md=r.get("content_md") or "",
        like_count=int(r.get("like_count") or 0),
        mine_liked=cid in liked_ids,
        created_at=r.get("created_at") or datetime.utcnow(),
    )


# ========== 热度分重算（点赞*2 + 评论*3 + 收藏*1.5）/ log2(小时+2) ==========
async def _refresh_hot_score(post_id: int, row: dict) -> None:
    likes = int(row.get("like_count") or 0)
    comments = int(row.get("comment_count") or 0)
    favs = int(row.get("favorite_count") or 0)
    created: datetime | None = row.get("created_at")
    hours = 1.0
    if created:
        delta = (datetime.utcnow() if isinstance(created, datetime) else datetime.now()) - created
        hours = max(0.0, delta.total_seconds() / 3600.0)
    score = (likes * 2 + comments * 3 + favs * 1.5) / math.log2(hours + 2)
    await execute_write(
        "UPDATE community_post SET hot_score=%s WHERE id=%s",
        (round(score, 6), post_id),
    )


# ========== 改帖（作者本人 或 管理员用） ==========
async def update_post(user_id: int, post_id: int, payload: PostUpdate) -> bool:
    row = await fetch_one("SELECT * FROM community_post WHERE id=%s AND yn=1", (post_id,))
    if row is None:
        return False
    if int(row.get("author_id") or 0) != user_id:
        # 非作者：允许 is_pinned/is_locked 变化（认为是管理员）
        if payload.is_pinned is None and payload.is_locked is None:
            raise PermissionError("不能修改他人的帖子")
    sets: list[str] = []
    args: list[Any] = []
    if payload.title is not None:
        sets.append("title=%s")
        args.append(payload.title)
    if payload.content_md is not None:
        sets.append("content_md=%s")
        args.append(payload.content_md)
    if payload.tags is not None:
        sets.append("tags_json=%s")
        args.append(json.dumps(payload.tags or [], ensure_ascii=False))
    if payload.is_pinned is not None:
        sets.append("is_pinned=%s")
        args.append(1 if payload.is_pinned else 0)
    if payload.is_locked is not None:
        sets.append("is_locked=%s")
        args.append(1 if payload.is_locked else 0)
    if not sets:
        return True
    sql = f"UPDATE community_post SET {', '.join(sets)} WHERE id=%s"
    args.append(post_id)
    await execute_write(sql, tuple(args))
    return True
