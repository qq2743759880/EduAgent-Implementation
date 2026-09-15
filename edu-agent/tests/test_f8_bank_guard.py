# -*- coding: utf-8 -*-
"""F-8 契约测试：管理端题库删除引用保护（非空题库 → 40924，force → 级联软删题目）。

离线纯单测：monkeypatch question_admin/service.py 的 _bank_repo / _question_repo 单例，
不连 MySQL/后端。对齐 F-7 的 _FakeRepo 套路，覆盖 kickoff GWT：
  - 非空题库删除 → 40924（BANK_IN_USE），绝不静默留下题目孤儿，soft_delete 零调用；
  - force=True → 先级联软删库内题目再软删题库（两 repo 软删都调用）；
  - 空库删除 → 200 路径（仅软删题库）；
  - 题库不存在 → 40400。
"""
from __future__ import annotations

import pytest

from app.common.error_codes import BANK_IN_USE, NOT_FOUND
from app.common.exceptions import ConflictError, NotFoundError
from app.domains.question_admin import service as svc


class _FakeBankRepo:
    def __init__(self, row=None):
        self._row = row
        self.soft_delete_calls = []

    async def get_by_id(self, bank_id: int):
        return self._row

    async def soft_delete(self, bank_id: int):
        self.soft_delete_calls.append(bank_id)
        return 1


class _FakeQuestionRepo:
    def __init__(self, count: int = 0):
        self._count = count
        self.count_calls = []
        self.soft_delete_calls = []

    async def count_active_by_bank(self, bank_id: int) -> int:
        self.count_calls.append(bank_id)
        return self._count

    async def soft_delete_all_by_bank(self, bank_id: int) -> int:
        self.soft_delete_calls.append(bank_id)
        return self._count


def _bank_row(bank_id: int) -> dict:
    return {"id": bank_id, "bank_name": f"bank-{bank_id}", "yn": 1}


class TestBankDeleteGuard:
    async def test_non_empty_delete_40924(self, monkeypatch):
        bank_repo = _FakeBankRepo(row=_bank_row(1))
        q_repo = _FakeQuestionRepo(count=4)
        monkeypatch.setattr(svc, "_bank_repo", bank_repo)
        monkeypatch.setattr(svc, "_question_repo", q_repo)
        with pytest.raises(ConflictError) as ei:
            await svc.delete_bank(1)
        assert ei.value.code == BANK_IN_USE
        assert "4" in ei.value.message
        # 保护生效：任何软删都不应执行（题目孤儿 + 题库都保留）
        assert q_repo.soft_delete_calls == []
        assert bank_repo.soft_delete_calls == []

    async def test_force_cascades_soft_delete(self, monkeypatch):
        bank_repo = _FakeBankRepo(row=_bank_row(1))
        q_repo = _FakeQuestionRepo(count=4)
        monkeypatch.setattr(svc, "_bank_repo", bank_repo)
        monkeypatch.setattr(svc, "_question_repo", q_repo)
        result = await svc.delete_bank(1, force=True)
        assert result["forced"] is True
        assert result["questions_removed"] == 4
        assert q_repo.soft_delete_calls == [1]   # 先级联软删题目
        assert bank_repo.soft_delete_calls == [1]  # 再软删题库

    async def test_empty_bank_delete_ok(self, monkeypatch):
        bank_repo = _FakeBankRepo(row=_bank_row(1))
        q_repo = _FakeQuestionRepo(count=0)
        monkeypatch.setattr(svc, "_bank_repo", bank_repo)
        monkeypatch.setattr(svc, "_question_repo", q_repo)
        result = await svc.delete_bank(1)
        assert result["forced"] is False
        assert result["questions_removed"] == 0
        assert q_repo.soft_delete_calls == []       # 无题目可删
        assert bank_repo.soft_delete_calls == [1]   # 软删题库本身

    async def test_not_found_40400(self, monkeypatch):
        bank_repo = _FakeBankRepo(row=None)
        q_repo = _FakeQuestionRepo(count=0)
        monkeypatch.setattr(svc, "_bank_repo", bank_repo)
        monkeypatch.setattr(svc, "_question_repo", q_repo)
        with pytest.raises(NotFoundError) as ei:
            await svc.delete_bank(999)
        assert ei.value.code == NOT_FOUND
        assert q_repo.soft_delete_calls == []
        assert bank_repo.soft_delete_calls == []
