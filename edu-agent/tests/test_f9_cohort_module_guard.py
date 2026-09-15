# -*- coding: utf-8 -*-
"""F-9 契约测试：管理端班次删除模块引用保护（含模块→40908；force 仅 ADMIN 级联删零课次模块）。

离线纯单测：monkeypatch course_admin/service.py 的 _cohort_repo / _module_repo 单例，
不连 MySQL/后端。覆盖 kickoff GWT：
  - 含模块班次删除 → 40908（SERIES_IN_USE），绝不静默；
  - force=True（ADMIN）→ 逐模块查课次，全零课次才物理删模块 + 软删班次；
  - force=True 但某模块仍有课次 → 仍 40908（绝不级联删课次）；
  - 空班次删除 → 200 路径（仅软删）；
  - 路由层：force 且非 ADMIN → PermissionDeniedError。
"""
from __future__ import annotations

import pytest

from app.auth import CurrentUser
from app.auth.schemas import UserRole
from app.common.error_codes import NOT_FOUND, SERIES_IN_USE
from app.common.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.domains.course_admin import router as cohort_router
from app.domains.course_admin import service as svc


class _CohortRepo:
    def __init__(self, row=None):
        self._row = row
        self.soft_delete_calls = []

    async def get_by_id(self, cid):
        return self._row

    async def soft_delete(self, cid):
        self.soft_delete_calls.append(cid)
        return 1


class _ModuleRepo:
    def __init__(self, modules=None, refs=None):
        self._modules = modules or []
        self._refs = refs or {}
        self.hard_delete_calls = []

    async def list_by_cohort(self, cid):
        return self._modules

    async def count_references(self, mid):
        return self._refs.get(int(mid), {"sessions": 0, "total": 0})

    async def hard_delete(self, mid):
        self.hard_delete_calls.append(mid)
        return 1


@pytest.fixture(autouse=True)
def _noop_invalidate(monkeypatch):
    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(svc, "invalidate", _noop)


class TestCohortModuleGuard:
    async def test_module_guard_40908(self, monkeypatch):
        cohort = _CohortRepo(row={"id": 1, "series_id": 10})
        mod = _ModuleRepo(modules=[{"id": 1}, {"id": 2}])
        monkeypatch.setattr(svc, "_cohort_repo", cohort)
        monkeypatch.setattr(svc, "_module_repo", mod)
        with pytest.raises(ConflictError) as ei:
            await svc.delete_cohort(1)
        assert ei.value.code == SERIES_IN_USE
        assert "模块" in ei.value.message
        assert cohort.soft_delete_calls == []
        assert mod.hard_delete_calls == []

    async def test_force_cascade_empty_modules(self, monkeypatch):
        cohort = _CohortRepo(row={"id": 1, "series_id": 10})
        mod = _ModuleRepo(
            modules=[{"id": 1}, {"id": 2}],
            refs={1: {"sessions": 0, "total": 0}, 2: {"sessions": 0, "total": 0}},
        )
        monkeypatch.setattr(svc, "_cohort_repo", cohort)
        monkeypatch.setattr(svc, "_module_repo", mod)
        await svc.delete_cohort(1, force=True)
        assert mod.hard_delete_calls == [1, 2]
        assert cohort.soft_delete_calls == [1]

    async def test_force_blocked_by_session(self, monkeypatch):
        cohort = _CohortRepo(row={"id": 1, "series_id": 10})
        mod = _ModuleRepo(modules=[{"id": 1}], refs={1: {"sessions": 3, "total": 3}})
        monkeypatch.setattr(svc, "_cohort_repo", cohort)
        monkeypatch.setattr(svc, "_module_repo", mod)
        with pytest.raises(ConflictError) as ei:
            await svc.delete_cohort(1, force=True)
        assert ei.value.code == SERIES_IN_USE
        assert "课次" in ei.value.message
        assert mod.hard_delete_calls == []

    async def test_empty_cohort_soft_delete(self, monkeypatch):
        cohort = _CohortRepo(row={"id": 1, "series_id": 10})
        mod = _ModuleRepo(modules=[])
        monkeypatch.setattr(svc, "_cohort_repo", cohort)
        monkeypatch.setattr(svc, "_module_repo", mod)
        await svc.delete_cohort(1)
        assert mod.hard_delete_calls == []
        assert cohort.soft_delete_calls == [1]

    async def test_not_found_40400(self, monkeypatch):
        cohort = _CohortRepo(row=None)
        mod = _ModuleRepo(modules=[])
        monkeypatch.setattr(svc, "_cohort_repo", cohort)
        monkeypatch.setattr(svc, "_module_repo", mod)
        with pytest.raises(NotFoundError) as ei:
            await svc.delete_cohort(999)
        assert ei.value.code == NOT_FOUND


class TestCohortDeleteRoleGuard:
    """路由层 force 参数 + ADMIN 角色门（不连 DB，monkeypatch service.delete_cohort）。"""

    class _RecordingSvc:
        def __init__(self):
            self.calls = []

        async def delete_cohort(self, cohort_id, *, force=False):
            self.calls.append((cohort_id, force))

    @staticmethod
    def _user(role: UserRole) -> CurrentUser:
        return CurrentUser(
            user_id=1, account="u", username="u", nickname="u",
            real_name="u", mobile="13800000000", email="u@e.com",
            gender="m", avatar_url="", role=role,
        )

    async def test_non_admin_force_denied(self, monkeypatch):
        rec = self._RecordingSvc()
        monkeypatch.setattr(svc, "delete_cohort", rec.delete_cohort)
        me = self._user(UserRole.MANAGER)
        with pytest.raises(PermissionDeniedError):
            await cohort_router.admin_delete_cohort(5, force=True, me=me)
        assert rec.calls == []

    async def test_admin_force_calls_svc(self, monkeypatch):
        rec = self._RecordingSvc()
        monkeypatch.setattr(svc, "delete_cohort", rec.delete_cohort)
        me = self._user(UserRole.ADMIN)
        await cohort_router.admin_delete_cohort(5, force=True, me=me)
        assert rec.calls == [(5, True)]

    async def test_admin_no_force_calls_svc_false(self, monkeypatch):
        rec = self._RecordingSvc()
        monkeypatch.setattr(svc, "delete_cohort", rec.delete_cohort)
        me = self._user(UserRole.ADMIN)
        # FastAPI 解析 Query(False) 默认值为 False 后传入；此处显式模拟
        await cohort_router.admin_delete_cohort(5, force=False, me=me)
        assert rec.calls == [(5, False)]
