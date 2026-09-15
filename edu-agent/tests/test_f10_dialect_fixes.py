# -*- coding: utf-8 -*-
"""F-10 契约测试：两处口径瑕疵（①/media 404 纯文本；②RAG 幽灵集合读侧过滤）。

①/media：_MediaStaticFiles 缺失文件 → PlainTextResponse 404（静态资源不套 JSON 壳），
  已存在文件仍正常 200 返回。
②RAG collections：Milvus 可达时读侧过滤物理不存在的幽灵集合（knowledge_chunk_v1），
  Milvus 集合名拿不到（不可达/失败）→ 不过滤，保持 MySQL 快照降级，且不删 MySQL 行。
离线纯单测：不连 Milvus/MySQL/后端。
"""
from __future__ import annotations

import contextlib
from datetime import datetime

import pytest
from starlette.responses import PlainTextResponse

# 注意：rag_admin.service 与 chat.service 存在循环导入；app.main 按安全顺序导入二者，
# 故此处必须先 import app.main 解开环（与线上启动路径一致），再导入 rag_admin.service。
import app.main  # noqa: F401
from app.admin.rag_admin import service as rag_svc
from app.main import _MediaStaticFiles


# ═══════════════════════════════════════════
# F-10① /media 404 → 纯文本
# ═══════════════════════════════════════════

class TestMediaPlainText404:
    @pytest.fixture
    def media(self, tmp_path):
        root = tmp_path / "media"
        root.mkdir()
        (root / "ok.txt").write_text("hello", encoding="utf-8")
        return _MediaStaticFiles(directory=str(root))

    _SCOPE = {
        "type": "http", "method": "GET", "scheme": "http",
        "path": "/media/x", "raw_path": b"/media/x", "query_string": b"",
        "headers": [], "server": ("testserver", 80), "client": ("127.0.0.1", 1234),
    }

    async def test_missing_file_plain_text_404(self, media):
        resp = await media.get_response("__nonexistent_f10__.mp4", dict(self._SCOPE))
        assert isinstance(resp, PlainTextResponse)
        assert resp.status_code == 404
        assert "404" in resp.body.decode("utf-8")

    async def test_existing_file_served(self, media):
        resp = await media.get_response("ok.txt", dict(self._SCOPE))
        assert resp.status_code == 200


# ═══════════════════════════════════════════
# F-10② /api/admin/rag/collections 幽灵集合过滤
# ═══════════════════════════════════════════

class _FakeCursor:
    def __init__(self):
        self.executed = []

    async def execute(self, sql, args=None):
        self.executed.append((sql, args))
        return 1


@contextlib.asynccontextmanager
async def _fake_transaction():
    yield (None, _FakeCursor())


def _meta_row(mid: int, name: str) -> dict:
    return {
        "id": mid, "collection_name": name, "partition_name": "_default",
        "tenant_id": None, "display_name": name, "row_count": 0, "source_count": 0,
        "last_rebuild_at": None, "last_snapshot_at": datetime(2026, 1, 1),
        "status": "ready", "status_message": None, "visibility": "public",
        "created_at": datetime(2026, 1, 1), "updated_at": datetime(2026, 1, 1),
    }


@pytest.fixture
def _wire(monkeypatch):
    rows = [_meta_row(1, "knowledge_chunk_v1"), _meta_row(4, "edu_knowledge")]

    async def _fetch_all(sql, *a, **k):
        return rows

    async def _noop_recover(*a, **k):
        return None

    async def _parts():
        return [{"name": "_default", "row_count": 7}]

    monkeypatch.setattr(rag_svc, "_recover_stuck_collections", _noop_recover)
    monkeypatch.setattr(rag_svc, "fetch_all", _fetch_all)
    monkeypatch.setattr(rag_svc, "_list_all_partitions_limited", _parts)
    monkeypatch.setattr(rag_svc, "transaction", _fake_transaction)
    # 保证不走「loader 导入失败」的提前返回分支
    monkeypatch.setattr(rag_svc, "_milvus_list_all_partitions", lambda: [])
    return monkeypatch


class TestRagGhostCollectionFilter:
    async def test_ghost_filtered_when_milvus_reachable(self, _wire):
        async def _cols():
            return ["pf_bagu_kb", "user_memory", "edu_knowledge"]
        _wire.setattr(rag_svc, "_list_milvus_collections_limited", _cols)
        out = await rag_svc.list_collections()
        names = [m.collection_name for m in out]
        assert "knowledge_chunk_v1" not in names  # 幽灵集合被隐藏
        assert "edu_knowledge" in names           # 真实集合保留

    async def test_no_filter_when_collections_unavailable(self, _wire):
        async def _cols():
            return []  # Milvus 集合名拿不到 → 不过滤（降级）
        _wire.setattr(rag_svc, "_list_milvus_collections_limited", _cols)
        out = await rag_svc.list_collections()
        names = [m.collection_name for m in out]
        assert "knowledge_chunk_v1" in names
        assert "edu_knowledge" in names
