# -*- coding: utf-8 -*-
"""community.service 核心单测：发帖/列表/反应切换/锁帖/权限（mock DB 层）。"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.community import service as com_svc
from app.community.schemas import CommentCreate, PostCreate, PostUpdate
from app.common.exceptions import BadRequestError, PermissionDeniedError, ResourceNotFoundError
from app.common.error_codes import COMMUNITY_FORBIDDEN_UPDATE, COMMUNITY_POST_LOCKED, COMMUNITY_POST_NOT_FOUND


# ============================================================
# 1. 发帖
# ============================================================
@pytest.mark.asyncio
async def test_create_post(monkeypatch):
    """正常发帖：INSERT 返回 id，调用积分奖励，返回结构正确。"""
    writes: list[tuple] = []

    async def fake_execute(sql, args):
        writes.append((sql, args))
        return 99  # lastrowid

    monkeypatch.setattr(com_svc, "execute_write", fake_execute)

    # service 内是函数内 `from app.gamification.service import ...`（懒加载）。
    # patch app.gamification.service 模块属性即可生效。
    import app.gamification.service as gam_mod

    async def fake_award(*a, **kw):
        return 5

    async def fake_badges(*a, **kw):
        return ["first_post"]

    monkeypatch.setattr(gam_mod, "award_points", fake_award)
    monkeypatch.setattr(gam_mod, "check_and_unlock_badges", fake_badges)

    payload = PostCreate(board_code="general", title="测试帖", content_md="正文内容")
    res = await com_svc.create_post(1, "Alice", payload)
    assert res["post_id"] == 99
    assert res["points_awarded"] == 5
    assert res["badge_unlocked"] == ["first_post"]
    # 验证 INSERT 带 tags_json
    insert_sql = writes[0][0]
    assert "INSERT INTO community_post" in insert_sql
    assert "tags_json" in insert_sql


@pytest.mark.asyncio
async def test_create_post_gamification_failure_silent(monkeypatch):
    """积分服务异常不应导致发帖失败（try/except pass 保护主流程）。"""
    async def fake_execute(sql, args):
        return 1

    monkeypatch.setattr(com_svc, "execute_write", fake_execute)

    import app.gamification.service as gam_mod

    async def boom(*a, **kw):
        raise RuntimeError("gamification down")

    monkeypatch.setattr(gam_mod, "award_points", boom)
    monkeypatch.setattr(gam_mod, "check_and_unlock_badges", boom)

    payload = PostCreate(board_code="general", title="测试", content_md="正文")
    res = await com_svc.create_post(1, "Alice", payload)
    assert res["post_id"] == 1
    assert res["points_awarded"] == 0


# ============================================================
# 2. 列表（分页 / 版块过滤 / 当前用户反应）
# ============================================================
def _mk_post_row(pid, **overrides) -> dict:
    row = {
        "id": pid, "board_code": "general", "author_id": 1, "author_name": "Alice",
        "title": f"帖{pid}", "content_md": "内容", "tags_json": '["python"]',
        "is_pinned": 0, "is_locked": 0, "view_count": 10, "like_count": 2,
        "comment_count": 1, "favorite_count": 0, "hot_score": 3.5,
        "created_at": datetime(2026, 1, 1, 12, 0, 0),
        "updated_at": datetime(2026, 1, 1, 12, 0, 0),
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_list_posts_happy_path(monkeypatch):
    """正常列表：count 查询 + 分页 SQL + 反应批量 IN 查询。"""
    seen_sql: list[str] = []

    async def fake_fetch_one(sql, args):
        seen_sql.append(sql)
        if "COUNT(*)" in sql and "community_react" not in sql and "author_id=" not in sql:
            return {"c": 25}
        if "author_id=" in sql:
            return {"c": 3}
        if "community_post WHERE id=" in sql:
            return _mk_post_row(7)
        return {"c": 0}

    async def fake_fetch_all(sql, args):
        seen_sql.append(sql)
        if "community_react" in sql:
            return [{"target_id": 7, "react_type": "LIKE"}]
        return [_mk_post_row(7)]

    monkeypatch.setattr(com_svc, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(com_svc, "fetch_all", fake_fetch_all)

    resp = await com_svc.list_posts(1, board_code="general", page=1, page_size=20)
    assert resp.total == 25
    assert len(resp.items) == 1
    item = resp.items[0]
    assert item.post_id == 7
    assert item.mine_react_like is True
    assert item.tags == ["python"]
    # 分页 SQL 应带 ORDER BY + LIMIT + OFFSET
    assert any("ORDER BY" in s and "LIMIT" in s for s in seen_sql)


@pytest.mark.asyncio
async def test_list_posts_react_batched(monkeypatch):
    """有帖子时对反应做 IN 批量查询（而不是 N+1）。"""
    async def fake_fetch_one(sql, args):
        if "COUNT(*)" in sql and "author_id=" not in sql:
            return {"c": 2}
        if "author_id=" in sql:
            return {"c": 0}
        return {"c": 0}

    monkeypatch.setattr(com_svc, "fetch_one", fake_fetch_one)
    captured: list[str] = []

    async def fake_fetch_all(sql, args):
        captured.append(sql)
        if "community_react" in sql:
            return []
        return [_mk_post_row(1), _mk_post_row(2)]

    monkeypatch.setattr(com_svc, "fetch_all", fake_fetch_all)
    await com_svc.list_posts(1, page=1)
    assert any("target_id IN (%s,%s)" in s for s in captured)


# ============================================================
# 3. 反应切换（点赞/取消）
# ============================================================
@pytest.mark.asyncio
async def test_toggle_react_like_then_unlike(monkeypatch):
    """首次点赞 active=True；再次点赞（同 react）→ 取消 active=False。"""
    reacts: dict[str, dict | None] = {"like": None}
    writes: list[tuple] = []

    async def fake_fetch_one(sql, args):
        if "COUNT(*)" in sql:
            # _count_react / 列表 count：reacts 存在且 yn=1 → 1，否则 0
            return {"c": 1 if reacts["like"] and reacts["like"].get("yn") == 1 else 0}
        if "community_react" in sql:
            return reacts["like"]
        if "community_post WHERE id=" in sql:
            return _mk_post_row(7, like_count=2)
        return None

    async def fake_execute(sql, args):
        writes.append((sql, args))
        if "INSERT INTO community_react" in sql:
            reacts["like"] = {"id": 5, "yn": 1}
        if "UPDATE community_react" in sql:
            reacts["like"] = {"id": 5, "yn": 0}

    async def fake_fetch_all(sql, args):
        return []

    monkeypatch.setattr(com_svc, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(com_svc, "execute_write", fake_execute)
    monkeypatch.setattr(com_svc, "fetch_all", fake_fetch_all)

    async def fake_refresh(post_id, row):
        return None

    monkeypatch.setattr(com_svc, "_refresh_hot_score", fake_refresh)

    # 第一次：插入
    r1 = await com_svc.toggle_react(1, "POST", 7, "LIKE", author_id_if_known=2)
    assert r1.active is True
    assert r1.total_count == 1
    assert any("INSERT INTO community_react" in s[0] for s in writes)
    writes.clear()
    # 模拟已存在且 yn=1
    reacts["like"] = {"id": 5, "yn": 1}
    r2 = await com_svc.toggle_react(1, "POST", 7, "LIKE", author_id_if_known=2)
    assert r2.active is False
    assert r2.total_count == 0
    assert any("UPDATE community_react SET yn=%s WHERE id=%s" == s[0] for s in writes)


@pytest.mark.asyncio
async def test_toggle_react_invalid_type_rejected():
    with pytest.raises(AssertionError):
        await com_svc.toggle_react(1, "EVIL", 7, "LIKE")
    with pytest.raises(AssertionError):
        await com_svc.toggle_react(1, "POST", 7, "HATE")


# ============================================================
# 4. 评论：锁帖校验
# ============================================================
@pytest.mark.asyncio
async def test_create_comment_on_locked_post(monkeypatch):
    """锁帖 → 拒绝评论。"""
    async def fake_fetch_one(sql, args):
        if "community_post" in sql:
            return {"id": 7, "is_locked": 1}
        return None

    monkeypatch.setattr(com_svc, "fetch_one", fake_fetch_one)
    payload = CommentCreate(content_md="回复内容")
    with pytest.raises(BadRequestError) as ei:
        await com_svc.create_comment(1, "Alice", 7, payload)
    assert ei.value.code == COMMUNITY_POST_LOCKED


@pytest.mark.asyncio
async def test_create_comment_post_missing(monkeypatch):
    """帖子不存在 → 拒绝。"""
    async def fake_fetch_one(sql, args):
        return None

    monkeypatch.setattr(com_svc, "fetch_one", fake_fetch_one)
    payload = CommentCreate(content_md="回复")
    with pytest.raises(ResourceNotFoundError) as ei:
        await com_svc.create_comment(1, "Alice", 404, payload)
    assert ei.value.code == COMMUNITY_POST_NOT_FOUND


# ============================================================
# 5. 改帖权限
# ============================================================
@pytest.mark.asyncio
async def test_update_post_own_post(monkeypatch):
    """作者本人改自己的帖 → 放行并 UPDATE。"""
    writes: list[tuple] = []

    async def fake_fetch_one(sql, args):
        return _mk_post_row(7, author_id=1)

    async def fake_execute(sql, args):
        writes.append((sql, args))

    monkeypatch.setattr(com_svc, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(com_svc, "execute_write", fake_execute)

    ok = await com_svc.update_post(1, 7, PostUpdate(title="新标题"))
    assert ok is True
    assert writes and "UPDATE community_post SET title=%s" in writes[0][0]
    assert writes[0][1][-1] == 7


@pytest.mark.asyncio
async def test_update_post_other_user_forbidden(monkeypatch):
    """非作者且不改 pin/lock → PermissionError。"""
    async def fake_fetch_one(sql, args):
        return _mk_post_row(7, author_id=1)

    monkeypatch.setattr(com_svc, "fetch_one", fake_fetch_one)
    with pytest.raises(PermissionDeniedError) as ei:
        await com_svc.update_post(2, 7, PostUpdate(title="别人改我"))
    assert ei.value.code == COMMUNITY_FORBIDDEN_UPDATE


@pytest.mark.asyncio
async def test_update_post_admin_can_lock(monkeypatch):
    """管理员（改 is_locked）→ 允许，即使不是作者。"""
    writes: list[tuple] = []

    async def fake_fetch_one(sql, args):
        return _mk_post_row(7, author_id=1)

    async def fake_execute(sql, args):
        writes.append((sql, args))

    monkeypatch.setattr(com_svc, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(com_svc, "execute_write", fake_execute)

    ok = await com_svc.update_post(99, 7, PostUpdate(is_locked=True))
    assert ok is True
    assert any("is_locked=%s" in s[0] for s in writes)


@pytest.mark.asyncio
async def test_update_post_missing(monkeypatch):
    async def fake_fetch_one(sql, args):
        return None

    monkeypatch.setattr(com_svc, "fetch_one", fake_fetch_one)
    assert await com_svc.update_post(1, 999, PostUpdate(title="x")) is False


# ============================================================
# 11. GHOST-pin-rootfix：分页排序必须全序（置顶仅首页一次 / 不跨页重复）
# ============================================================
@pytest.mark.asyncio
@pytest.mark.parametrize("sort_key", ["HOT", "NEW", "LIKE"])
async def test_list_posts_order_by_is_total_order(monkeypatch, sort_key):
    """列表分页 ORDER BY 必须以「置顶优先」开头、以唯一 tiebreaker `P.id DESC` 收尾。

    背景（GHOST-pin-rootfix）：原排序 (is_pinned, hot_score, created_at) 不是全序——
    hot_score=0 / created_at 相同的成批行在 LIMIT/OFFSET 下顺序不确定，同一帖子会跨页重复
    或被漏出（total 与 items 对不上）。补主键 tiebreaker 后排序唯一，分页严格不重不漏；
    `is_pinned DESC` 前置则保证置顶帖只在第一页首屏出现一次。
    """
    captured: list[str] = []

    async def fake_fetch_one(sql, args):
        if "COUNT(*)" in sql and "author_id=" not in sql:
            return {"c": 1}
        if "author_id=" in sql:
            return {"c": 1}
        return {"c": 0}

    async def fake_fetch_all(sql, args):
        captured.append(sql)
        if "community_react" in sql:
            return []
        return [_mk_post_row(7, is_pinned=1)]

    monkeypatch.setattr(com_svc, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(com_svc, "fetch_all", fake_fetch_all)

    await com_svc.list_posts(1, page=1, page_size=10, sort=sort_key)

    page_sql = [s for s in captured if "ORDER BY" in s and "community_react" not in s]
    assert page_sql, "未捕获分页 SQL"
    sql = page_sql[0]
    assert "LIMIT" in sql and "OFFSET" in sql, f"分页 SQL 缺少 LIMIT/OFFSET: {sql}"
    # 置顶优先（= 置顶帖只会落在第一页首屏），且以唯一 tiebreaker 收尾
    assert sql.index("P.is_pinned DESC") < sql.index("ORDER BY") + len("ORDER BY ") + 1, \
        f"ORDER BY 首要键必须为 P.is_pinned DESC: {sql}"
    assert "P.id DESC" in sql, f"ORDER BY 缺少唯一 tiebreaker P.id DESC（分页不重不漏失效）: {sql}"
    # tiebreaker 必须落在 ORDER BY 子句内、LIMIT 之前
    assert sql.index("ORDER BY") < sql.index("P.id DESC") < sql.index("LIMIT"), \
        f"tiebreaker 必须位于 ORDER BY 子句末位（LIMIT 前）: {sql}"
