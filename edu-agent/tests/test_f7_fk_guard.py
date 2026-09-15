# -*- coding: utf-8 -*-
"""F-7 契约测试：管理端课程域父记录外键预校验（非法 ID → 40400，而非 FK 1452 逃逸成 50301）。

离线纯单测：monkeypatch service 层 repo 单例，不连 MySQL/Redis/后端。
覆盖盲测报告坑 1（head_teacher_id=用户表 ID → 50301 误导）+ kickoff 要求的同文件
同病核查（cohort 四 FK / module.cohort_id / session.module_id+room_id / chapter.video_id）。
"""
from __future__ import annotations

from datetime import date

import pytest

from app.common.exceptions import NotFoundError
from app.domains.course_admin import service as svc
from app.domains.course_admin.schemas import (
    ChapterCreateAdmin,
    CohortCreateAdmin,
    CohortUpdateAdmin,
    ModuleCreateAdmin,
    SessionCreateAdmin,
)


class _FakeRepo:
    """可逐方法配置返回值的 repo 桩；记录 insert/update 是否被调用。"""

    def __init__(self, **methods):
        self._methods = methods
        self.insert_called = 0
        self.update_called = 0

    def __getattr__(self, name):
        if name in self._methods:
            async def _m(*a, **k):
                return self._methods[name](*a, **k)
            return _m
        if name == "insert":
            async def _ins(*a, **k):
                self.insert_called += 1
                return 9001
            return _ins
        if name == "update":
            async def _upd(*a, **k):
                self.update_called += 1
                return 1
            return _upd
        raise AttributeError(name)


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch):
    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(svc, "invalidate", _noop)


def _cohort_payload(**over):
    base = dict(
        institution_id=1, series_id=10, campus_id=2, head_teacher_id=3,
        cohort_code="F7-T", cohort_name="f7 test",
        sale_price="9.90", max_student_count=20, start_date=date(2026, 10, 1),
    )
    base.update(over)
    return CohortCreateAdmin(**base)


class TestCohortFkGuard:
    async def test_invalid_head_teacher_40400(self, monkeypatch):
        monkeypatch.setattr(svc, "_cohort_repo", _FakeRepo(
            institution_exists=lambda i: True,
            campus_exists=lambda i: True,
            head_teacher_exists=lambda i: False,  # 999999 无教职工档案
            get_by_code=lambda *a: None,
        ))
        monkeypatch.setattr(svc, "_series_repo", _FakeRepo(get_by_id=lambda i: {"id": i}))
        with pytest.raises(NotFoundError) as ei:
            await svc.create_cohort(_cohort_payload(head_teacher_id=999999))
        assert ei.value.code == "40400"
        assert "负责人" in ei.value.message
        assert svc._cohort_repo.insert_called == 0

    async def test_invalid_institution_series_campus_40400(self, monkeypatch):
        # institution 不存在
        monkeypatch.setattr(svc, "_cohort_repo", _FakeRepo(
            institution_exists=lambda i: False,
            campus_exists=lambda i: True, head_teacher_exists=lambda i: True,
            get_by_code=lambda *a: None,
        ))
        monkeypatch.setattr(svc, "_series_repo", _FakeRepo(get_by_id=lambda i: {"id": i}))
        with pytest.raises(NotFoundError) as ei:
            await svc.create_cohort(_cohort_payload(institution_id=888))
        assert ei.value.code == "40400" and "院校" in ei.value.message

        # series 不存在
        monkeypatch.setattr(svc, "_cohort_repo", _FakeRepo(
            institution_exists=lambda i: True,
            campus_exists=lambda i: True, head_teacher_exists=lambda i: True,
            get_by_code=lambda *a: None,
        ))
        monkeypatch.setattr(svc, "_series_repo", _FakeRepo(get_by_id=lambda i: None))
        with pytest.raises(NotFoundError) as ei:
            await svc.create_cohort(_cohort_payload(series_id=777))
        assert ei.value.code == "40400" and "课程系列" in ei.value.message

        # campus 不存在
        monkeypatch.setattr(svc, "_cohort_repo", _FakeRepo(
            institution_exists=lambda i: True,
            campus_exists=lambda i: False, head_teacher_exists=lambda i: True,
            get_by_code=lambda *a: None,
        ))
        monkeypatch.setattr(svc, "_series_repo", _FakeRepo(get_by_id=lambda i: {"id": i}))
        with pytest.raises(NotFoundError) as ei:
            await svc.create_cohort(_cohort_payload(campus_id=666))
        assert ei.value.code == "40400" and "校区" in ei.value.message

    async def test_valid_refs_creates(self, monkeypatch):
        def _full_row(i):
            return {
                "id": i, "institution_id": 1, "series_id": 10, "campus_id": 2,
                "head_teacher_id": 3, "cohort_code": "F7-T", "cohort_name": "f7 test",
                "sale_price": "9.90", "max_student_count": 20, "current_student_count": 0,
                "yn": 1, "start_date": date(2026, 10, 1), "end_date": None,
                "created_at": "2026-10-01 00:00:00", "updated_at": "2026-10-01 00:00:00",
            }
        cohort_repo = _FakeRepo(
            institution_exists=lambda i: True,
            campus_exists=lambda i: True, head_teacher_exists=lambda i: True,
            get_by_code=lambda *a: None,
            get_by_id=_full_row,
        )
        monkeypatch.setattr(svc, "_cohort_repo", cohort_repo)
        monkeypatch.setattr(svc, "_series_repo", _FakeRepo(get_by_id=lambda i: {"id": i}))
        out = await svc.create_cohort(_cohort_payload())
        assert cohort_repo.insert_called == 1
        assert out.id == 9001

    async def test_update_invalid_head_teacher_40400(self, monkeypatch):
        monkeypatch.setattr(svc, "_cohort_repo", _FakeRepo(
            get_by_id=lambda i: {"id": i, "series_id": 10},
            campus_exists=lambda i: True,
            head_teacher_exists=lambda i: False,
        ))
        with pytest.raises(NotFoundError) as ei:
            await svc.update_cohort(5, CohortUpdateAdmin(head_teacher_id=999999))
        assert ei.value.code == "40400"
        assert svc._cohort_repo.update_called == 0


class TestSiblingCreateFkGuard:
    async def test_create_module_bad_cohort_40400(self, monkeypatch):
        monkeypatch.setattr(svc, "_cohort_repo", _FakeRepo(get_by_id=lambda i: None))
        payload = ModuleCreateAdmin(
            cohort_id=404, module_code="M1", module_name="m", lesson_count=2,
            total_hours="1", stage_no=1, start_date=date(2026, 10, 1), end_date=date(2026, 10, 2),
        )
        with pytest.raises(NotFoundError) as ei:
            await svc.create_module(payload)
        assert ei.value.code == "40400" and "班次" in ei.value.message

    async def test_create_session_bad_module_40400(self, monkeypatch):
        monkeypatch.setattr(svc, "_module_repo", _FakeRepo(get_by_id=lambda i: None))
        payload = SessionCreateAdmin(
            series_cohort_course_id=404, session_no=1, session_title="s",
            teaching_date=date(2026, 10, 1),
        )
        with pytest.raises(NotFoundError) as ei:
            await svc.create_session(payload)
        assert ei.value.code == "40400" and "模块" in ei.value.message

    async def test_create_session_bad_room_40400(self, monkeypatch):
        monkeypatch.setattr(svc, "_module_repo", _FakeRepo(get_by_id=lambda i: {"id": i}))
        monkeypatch.setattr(svc, "_session_repo", _FakeRepo(room_exists=lambda i: False))
        payload = SessionCreateAdmin(
            series_cohort_course_id=1, room_id=999, session_no=1, session_title="s",
            teaching_date=date(2026, 10, 1),
        )
        with pytest.raises(NotFoundError) as ei:
            await svc.create_session(payload)
        assert ei.value.code == "40400" and "教室" in ei.value.message

    async def test_create_chapter_bad_video_40400(self, monkeypatch):
        monkeypatch.setattr(svc, "_video_repo", _FakeRepo(get_by_id=lambda i: None))
        payload = ChapterCreateAdmin(
            video_id=404, chapter_no=1, chapter_title="c", start_second=0, end_second=10,
        )
        with pytest.raises(NotFoundError) as ei:
            await svc.create_chapter(payload)
        assert ei.value.code == "40400" and "视频" in ei.value.message
