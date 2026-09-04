# -*- coding: utf-8 -*-
"""curriculum.service 单测：列表过滤/分页/详情/树形聚合（mock DB 层）。"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.curriculum import service as cur_svc


def _mk_series_row(sid: int, **overrides) -> dict:
    row = {
        "id": sid, "series_code": f"SR-{sid:04d}", "series_name": f"系列{sid}",
        "subject_code": "english", "level_code": "L1", "level_name": "入门",
        "description": "desc", "cover_url": None, "target_hours": 20,
        "sale_status": "on_sale", "sort_no": 1, "created_by": None,
        "created_at": datetime(2026, 1, 1, 10, 0, 0),
        "updated_at": datetime(2026, 1, 1, 10, 0, 0),
    }
    row.update(overrides)
    return row


def _mk_module_row(mid: int, series_id: int, **overrides) -> dict:
    row = {
        "id": mid, "series_id": series_id, "module_code": f"MD-{mid:04d}",
        "module_name": f"模块{mid}", "stage_no": 1, "lesson_count": 5,
        "total_hours": 5, "yn": 1,
        "created_at": datetime(2026, 1, 1, 10, 0, 0),
        "updated_at": datetime(2026, 1, 1, 10, 0, 0),
    }
    row.update(overrides)
    return row


def _mk_session_row(sid: int, module_id: int, **overrides) -> dict:
    row = {
        "id": sid, "module_id": module_id, "session_no": 1,
        "session_title": f"课次{sid}", "teaching_status": "scheduled",
        "duration_minutes": 30, "yn": 1,
        "created_at": datetime(2026, 1, 1, 10, 0, 0),
        "updated_at": datetime(2026, 1, 1, 10, 0, 0),
    }
    row.update(overrides)
    return row


# ============================================================
# 1. 列表：分页参数收敛 + 过滤条件构造
# ============================================================
@pytest.mark.asyncio
async def test_list_series_page_clamped(monkeypatch):
    """page=0 → 收敛为 1；page_size 超限 → 收敛为 100。"""
    async def fake_fetch_one(sql, args):
        return {"total": 0}

    async def fake_fetch_all(sql, args):
        return []

    monkeypatch.setattr(cur_svc, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(cur_svc, "fetch_all", fake_fetch_all)

    resp = await cur_svc.list_series(page=0, page_size=999)
    assert resp.page == 1
    assert resp.page_size == 100
    assert resp.total == 0
    assert resp.items == []


@pytest.mark.asyncio
async def test_list_series_with_filters(monkeypatch):
    """学科+分级+关键词过滤 → SQL 带全部条件且参数正确。"""
    captured: dict = {}

    async def fake_fetch_one(sql, args):
        captured["count"] = (sql, tuple(args))
        return {"total": 1}

    async def fake_fetch_all(sql, args):
        captured["list"] = (sql, tuple(args))
        return [_mk_series_row(1, cohort_count=3, total_session_count=12)]

    monkeypatch.setattr(cur_svc, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(cur_svc, "fetch_all", fake_fetch_all)

    from app.curriculum.schemas import LevelCode, SubjectCode

    resp = await cur_svc.list_series(
        subject_code=SubjectCode.ENGLISH, level_code=LevelCode.L1, keyword="音标",
    )
    assert resp.total == 1
    assert len(resp.items) == 1
    item = resp.items[0]
    assert item.cohort_count == 3
    assert item.total_session_count == 12

    count_sql = captured["count"][0]
    assert "s.subject_code = %s" in count_sql
    assert "s.level_code = %s" in count_sql
    assert "LIKE %s" in count_sql
    assert "s.sale_status = 'on_sale'" in count_sql
    # 参数：subject + level + 3 个 like
    assert len(captured["count"][1]) == 5


@pytest.mark.asyncio
async def test_list_series_no_filter_only_on_sale(monkeypatch):
    """无条件过滤时也只查在售系列。"""
    async def fake_fetch_one(sql, args):
        return {"total": 2}

    async def fake_fetch_all(sql, args):
        return [_mk_series_row(1), _mk_series_row(2)]

    monkeypatch.setattr(cur_svc, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(cur_svc, "fetch_all", fake_fetch_all)

    resp = await cur_svc.list_series()
    assert resp.total == 2
    assert len(resp.items) == 2


# ============================================================
# 2. 详情
# ============================================================
@pytest.mark.asyncio
async def test_get_series_found(monkeypatch):
    async def fake_fetch_one(sql, args):
        return _mk_series_row(5)

    monkeypatch.setattr(cur_svc, "fetch_one", fake_fetch_one)
    s = await cur_svc.get_series(5)
    assert s is not None
    assert s.id == 5
    assert s.series_code == "SR-0005"


@pytest.mark.asyncio
async def test_get_series_missing(monkeypatch):
    async def fake_fetch_one(sql, args):
        return None

    monkeypatch.setattr(cur_svc, "fetch_one", fake_fetch_one)
    assert await cur_svc.get_series(999) is None


# ============================================================
# 3. 树形聚合（series + cohorts + modules with sessions + 统计）
# ============================================================
@pytest.mark.asyncio
async def test_get_series_tree_aggregation(monkeypatch):
    """模块总课时/总课次统计正确。"""
    async def fake_fetch_one(sql, args):
        if "curriculum_series" in sql:
            return _mk_series_row(1)
        return None

    async def fake_fetch_all(sql, args):
        if "curriculum_cohort" in sql:
            return [{
                "id": 1, "series_id": 1, "cohort_code": "CH-0001", "cohort_name": "春季班",
                "start_date": datetime(2026, 3, 1).date(), "end_date": None,
                "max_student_count": 50, "current_student_count": 12, "sale_price": 199,
                "yn": 1,
                "created_at": datetime(2026, 1, 1), "updated_at": datetime(2026, 1, 1),
            }]
        if "curriculum_module" in sql:
            return [
                _mk_module_row(1, 1, total_hours=5),
                _mk_module_row(2, 1, total_hours=7),
            ]
        if "curriculum_session" in sql:
            return [
                _mk_session_row(1, 1),
                _mk_session_row(2, 1),
                _mk_session_row(3, 2),
            ]
        return []

    monkeypatch.setattr(cur_svc, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(cur_svc, "fetch_all", fake_fetch_all)

    tree = await cur_svc.get_series_tree(1)
    assert tree is not None
    assert tree.series.id == 1
    assert len(tree.cohorts) == 1
    assert len(tree.modules) == 2
    # 模块1 挂 2 课次，模块2 挂 1 课次
    assert len(tree.modules[0].sessions) == 2
    assert len(tree.modules[1].sessions) == 1
    assert tree.summary_total_sessions == 3
    assert tree.summary_total_hours == 12


@pytest.mark.asyncio
async def test_get_series_tree_missing(monkeypatch):
    async def fake_fetch_one(sql, args):
        return None

    monkeypatch.setattr(cur_svc, "fetch_one", fake_fetch_one)
    assert await cur_svc.get_series_tree(999) is None


# ============================================================
# 4. 课次分组
# ============================================================
@pytest.mark.asyncio
async def test_get_sessions_grouped(monkeypatch):
    async def fake_fetch_all(sql, args):
        assert "IN (%s, %s)" in sql  # 批量 IN 占位符
        assert args == [1, 2]
        return [_mk_session_row(1, 1), _mk_session_row(2, 1), _mk_session_row(3, 2)]

    monkeypatch.setattr(cur_svc, "fetch_all", fake_fetch_all)
    grouped = await cur_svc._get_sessions_grouped([1, 2])
    assert set(grouped.keys()) == {1, 2}
    assert len(grouped[1]) == 2
    assert len(grouped[2]) == 1


@pytest.mark.asyncio
async def test_get_sessions_grouped_empty(monkeypatch):
    monkeypatch.setattr(cur_svc, "fetch_all", lambda *a, **k: (_ for _ in ()).throw(AssertionError("不应调用")))
    assert await cur_svc._get_sessions_grouped([]) == {}
