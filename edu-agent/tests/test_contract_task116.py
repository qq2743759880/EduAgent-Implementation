"""task116 契约测试：系列删除语义 + 孤儿归档可导入性。

不依赖实时后端（用 monkeypatch 替换仓储），可在无服务环境下 CI 运行；
实时 HTTP 全链路实证见 test-reports/task116_gwt_verify.py + task116_gwt_evidence.json。
"""
import asyncio

import pytest

from app.common.error_codes import SERIES_IN_USE
from app.common.exceptions import ConflictError


def _run(coro):
    return asyncio.run(coro)


def _fake_invalidate(sink=None):
    """service.invalidate 是 async 函数，替身必须同为协程，否则 `await None` 报 TypeError。"""

    async def _inner(*keys):
        if sink is not None:
            sink.extend(keys)

    return _inner


class TestSeriesDeleteSemantics:
    """① 软删下架语义 + ② 真删路径与外键校验。"""

    def test_delete_series_soft_uses_off_sale_not_physical(self, monkeypatch):
        """默认删除 = 软删下架（sale_status='off_sale'），绝不物理删除，并失效详情缓存。"""
        import app.domains.course_admin.service as adm

        off_sale_called = []
        physical_called = []
        invalidated = []

        class FakeRepo:
            async def get_by_id(self, sid):
                return {"id": sid, "sale_status": "on_sale"}

            async def off_sale(self, sid):
                off_sale_called.append(sid)

            async def physical_delete(self, sid):
                physical_called.append(sid)

            async def count_references(self, sid):
                return {"cohorts": 0, "orders": 0, "total": 0}

        monkeypatch.setattr(adm, "_series_repo", FakeRepo())
        monkeypatch.setattr(adm, "invalidate", _fake_invalidate(invalidated))

        _run(adm.delete_series(101))

        assert off_sale_called == [101], "软删必须调用 off_sale"
        assert physical_called == [], "默认删除不得物理删除"
        assert "course:series:detail:101" in invalidated

    def test_delete_series_hard_no_refs_physical(self, monkeypatch):
        """?hard=true 且零引用 → 物理删除整行。"""
        import app.domains.course_admin.service as adm

        physical_called = []

        class FakeRepo:
            async def get_by_id(self, sid):
                return {"id": sid, "sale_status": "on_sale"}

            async def physical_delete(self, sid):
                physical_called.append(sid)

            async def count_references(self, sid):
                return {"cohorts": 0, "orders": 0, "total": 0}

        monkeypatch.setattr(adm, "_series_repo", FakeRepo())
        monkeypatch.setattr(adm, "invalidate", _fake_invalidate())

        _run(adm.delete_series(101, hard=True))

        assert physical_called == [101], "零引用真删必须物理删除"

    def test_delete_series_hard_with_refs_rejected(self, monkeypatch):
        """?hard=true 且存在班次/订单引用 → 抛 409 SERIES_IN_USE，绝不静默（不执行物理删除）。"""
        import app.domains.course_admin.service as adm

        class FakeRepo:
            async def get_by_id(self, sid):
                return {"id": sid, "sale_status": "on_sale"}

            async def physical_delete(self, sid):
                raise AssertionError("存在引用时不应执行物理删除")

            async def count_references(self, sid):
                return {"cohorts": 2, "orders": 1, "total": 3}

        monkeypatch.setattr(adm, "_series_repo", FakeRepo())
        monkeypatch.setattr(adm, "invalidate", _fake_invalidate())

        with pytest.raises(ConflictError) as exc:
            _run(adm.delete_series(101, hard=True))
        assert exc.value.code == SERIES_IN_USE, "引用存在时应返回 SERIES_IN_USE(40908)"
        # 即使软删状态的班次行（yn=0）也计入引用，避免 FK 冲突 500
        assert "含已下架" in (exc.value.message or "")

    def test_delete_series_not_found(self, monkeypatch):
        """删除不存在的系列 → NotFoundError，不调用任何写操作。"""
        import app.domains.course_admin.service as adm

        writes = []

        class FakeRepo:
            async def get_by_id(self, sid):
                return None

            async def off_sale(self, sid):
                writes.append(("off_sale", sid))

            async def physical_delete(self, sid):
                writes.append(("physical", sid))

        monkeypatch.setattr(adm, "_series_repo", FakeRepo())
        monkeypatch.setattr(adm, "invalidate", _fake_invalidate())

        with pytest.raises(Exception):
            _run(adm.delete_series(999))
        assert writes == [], "系列不存在时不得执行写操作"


class TestSeriesListFilter:
    """① 管理端列表默认过滤已下架系列；include_deleted 透传仓储。"""

    def test_list_default_excludes_off_sale(self, monkeypatch):
        import app.domains.course_admin.service as adm

        captured = {}

        class FakeRepo:
            async def list_series(self, **kwargs):
                captured.update(kwargs)
                return ([], 0)

        monkeypatch.setattr(adm, "_series_repo", FakeRepo())

        _run(adm.list_series_admin())
        assert captured.get("include_deleted") is False, "默认列表应排除已下架（include_deleted=False）"

    def test_list_include_deleted_passthrough(self, monkeypatch):
        import app.domains.course_admin.service as adm

        captured = {}

        class FakeRepo:
            async def list_series(self, **kwargs):
                captured.update(kwargs)
                return ([], 0)

        monkeypatch.setattr(adm, "_series_repo", FakeRepo())

        _run(adm.list_series_admin(include_deleted=True))
        assert captured.get("include_deleted") is True, "include_deleted 应透传至仓储"


class TestArchiveImportability:
    """④ 孤儿模块归档后 app.main 仍可正常导入（无残留引用）。"""

    def test_app_main_importable_after_archive(self):
        import importlib

        import app.main as m

        importlib.import_module("app.main")
        assert hasattr(m, "app"), "归档后 app.main 必须可导入且持有 FastAPI app 实例"
