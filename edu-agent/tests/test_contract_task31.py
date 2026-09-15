# -*- coding: utf-8 -*-
"""task31 RAG reranker 接入 + course_public 分区 合同测试。

GWT 覆盖：
- ① reranker.py：懒加载单例、批量16、失败返回 None → _rule_rerank 兜底
- ② retriever：召回 150 → rerank top-20 → 断崖 → 5；按 rerank 分数排序
- ③ course_public 分区隔离用户上传；filter_expr 排除促销/班次/公告（防混入）
- ④ sparse 基于 contextual 文本（build_sparse_vector 与入库端一致）

单位逻辑用 fake reranker，避免测试加载 GPU 模型；分区隔离/Milvus 集成 skipif 不可达。
"""
from __future__ import annotations

import asyncio
import zlib

import pytest

from app.auth import UserRole
from app.chat.retriever import _cliff_cutoff, _normalize_rerank_scores, _rerank_docs, _search_tenant_ids
from app.chat.schemas import RetrievedDoc
from app.config import settings
from app.knowledge.importer.loader import COLLECTION_NAME, COURSE_PUBLIC, _get_partition_name, get_milvus_client
from app.knowledge.reranker import Reranker


def make_doc(i: int, text: str, score: float = 0.5) -> RetrievedDoc:
    return RetrievedDoc(doc_id=f"d{i}", score=score, content=text)


# ------------------------------------------------------------------
# GWT① reranker：懒加载单例 + 失败返回 None
# ------------------------------------------------------------------
def test_reranker_singleton() -> None:
    assert Reranker.get() is Reranker.get()


def test_reranker_unavailable_returns_none() -> None:
    """加载失败（不可用）→ rerank 恒返回 None（调用方 _rule_rerank 兜底）。"""
    rk = Reranker()
    rk.__dict__["_model"] = None
    rk.__dict__["_load_error"] = "FlagReranker 加载失败: 模型目录不存在"
    assert rk.rerank("q", ["doc1", "doc2"]) is None


# ------------------------------------------------------------------
# GWT② 重排：打分排序 + 截断 top-20 + 降级回退
# ------------------------------------------------------------------
class FakeRerankerOk:
    """模拟打分成功：分数与 doc_id 数值正相关（d 数字越大分越高）。"""
    load_error = None

    def rerank(self, query, contents, **kw):
        return [float(100 + i) for i in range(len(contents))]


class FakeRerankerFail:
    load_error = "模拟 GPU 不可用"

    def rerank(self, query, contents, **kw):
        return None


def test_rerank_sorts_by_score_and_truncates_to_20(monkeypatch) -> None:
    docs = [make_doc(i, f"内容 {i}") for i in range(30)]  # d29 分最高
    # 隔离 sidecar：禁用后直接走进程内 Reranker，保证单测确定性（GWT③ 测试隔离）
    monkeypatch.setattr(settings, "RERANK_SIDECAR_ENABLED", False)
    monkeypatch.setattr("app.chat.retriever.Reranker.get", lambda: FakeRerankerOk())
    out, degrade = asyncio.run(_rerank_docs("q", docs))
    assert degrade is None
    assert len(out) == min(20, len(docs))                      # 截断 top-20
    assert out[0].doc_id == "d29"                              # 按 rerank 分数降序前移
    assert all(out[i].score >= out[i + 1].score for i in range(len(out) - 1))


def test_rerank_fallback_on_unavailable(monkeypatch) -> None:
    docs = [make_doc(i, f"内容 {i}", score=0.3) for i in range(5)]
    # 隔离 sidecar：禁用后直接走进程内 Reranker，验证 reranker_unavailable 降级链
    monkeypatch.setattr(settings, "RERANK_SIDECAR_ENABLED", False)
    monkeypatch.setattr("app.chat.retriever.Reranker.get", lambda: FakeRerankerFail())
    out, degrade = asyncio.run(_rerank_docs("q", docs))
    assert degrade == "reranker_unavailable"                   # GWT② 明确降级标注
    assert len(out) == 5                                       # 规则兜底不丢候选


def test_normalize_rerank_scores_monotonic() -> None:
    norm = _normalize_rerank_scores([10.0, 50.0, 20.0])
    assert 0.0 <= min(norm) <= max(norm) <= 1.0
    assert norm[-1] < norm[1]                                  # 50 → 最高分
    assert _normalize_rerank_scores([3.0, 3.0]) == [1.0, 1.0]  # 全等 → 平坦


def test_cliff_cutoff_to_5() -> None:
    docs = [make_doc(i, f"c{i}", score=0.9 - i * 0.01) for i in range(20)]
    assert len(_cliff_cutoff(docs, final_max_k=5, drop_ratio=0.2)) <= 5


# ------------------------------------------------------------------
# GWT③ course_public 分区 + 搜索范围
# ------------------------------------------------------------------
def test_search_tenant_includes_course_public() -> None:
    assert _search_tenant_ids(1, UserRole.STUDENT) == ["_default", COURSE_PUBLIC, "user_1"]
    assert _search_tenant_ids(1, UserRole.ADMIN) is None


def test_get_partition_name_course_public_literal() -> None:
    assert _get_partition_name("course_public") == "course_public"  # 保留分区，不前缀 user_
    assert _get_partition_name("_default") == "_default"
    assert _get_partition_name("123") == "user_123"


def test_admin_partition_validation_allows_course_public() -> None:
    from app.admin.rag_admin.service import _validate_partition_name
    from app.common.exceptions import ValidationError
    _validate_partition_name("course_public")                    # 不抛
    _validate_partition_name("_default")
    with pytest.raises(ValidationError):
        _validate_partition_name("not_a_partition")


# ------------------------------------------------------------------
# GWT④ sparse 基于 contextual 文本
# ------------------------------------------------------------------
def test_sparse_built_from_query_text() -> None:
    from app.knowledge.importer.embedder import build_sparse_vector
    sv = build_sparse_vector("图像分类用深度学习怎么做")
    assert isinstance(sv, dict) and len(sv) > 0
    assert len(sv) <= 64
    assert all(isinstance(int(k), int) and 0 < int(k) < (1 << 32) for k in sv)


# ------------------------------------------------------------------
# Milvus 集成：course_public 分区隔离 + filter_expr（skipif 不可达）
# ------------------------------------------------------------------
def _milvus_up() -> bool:
    try:
        get_milvus_client().list_collections()
        return True
    except Exception:
        return False


def _pseudo_dense(text: str):
    import hashlib
    dim = settings.EMBEDDING_DIM
    h = hashlib.md5(text.encode("utf-8")).digest()
    vec = [0.0] * dim
    for i in range(dim):
        vec[i] = ((h[i % 16] / 255.0) - 0.5) * 2.0
    return vec


def _cleanup_ids(*ids: str) -> None:
    client = get_milvus_client()
    try:
        client.delete(COLLECTION_NAME, ids=[zlib.crc32(i.encode("utf-8")) for i in ids])
    except Exception:
        pass


@pytest.mark.skipif(not _milvus_up(), reason="Milvus 不可达，跳过")
def test_course_public_partition_and_filter_isolate(tmp_path) -> None:
    """GWT③：课程 chunk 进 course_public、促销/班次 chunk 进 _default；
    检索 course_public（带 filter_expr）只回课程，不混入促销文案。"""
    from app.knowledge.importer import embedder, loader

    from app.knowledge.models import ContentType, KnowledgeChunk, Visibility

    def _chunk(cid: str, text: str) -> KnowledgeChunk:
        c = KnowledgeChunk(chunk_id=cid, content=text, content_type=ContentType.DOC_CHUNK,
                           series_code="SR-77", visibility=Visibility.PUBLIC)
        c.dense_vector = _pseudo_dense(text)
        svec = embedder.build_sparse_vector(text)
        items = sorted(svec.items(), key=lambda kv: -kv[1])[:64]
        c.sparse_indices = [int(k) for k, _ in items]
        c.sparse_values = [float(v) for _, v in items]
        return c

    # R03: load_chunks 入库前覆写 canonical chunk_id，断言/清理均以覆写后 id 为准
    course_probe = [_chunk("t31_course", "线性代数特征值与特征向量计算")]
    assert loader.load_chunks(course_probe, tenant_id="course_public") == 1
    course_cid = course_probe[0].chunk_id
    promo = _chunk("t31_promo", "暑期大促五折抢购、班次时间安排")
    assert loader.load_chunks([promo], tenant_id="_default") == 1
    promo_cid = promo.chunk_id

    qvec = _pseudo_dense("特征值 特征向量")
    qsparse = {}
    sq = embedder.build_sparse_vector("特征值 特征向量")
    for i, v in sorted(sq.items(), key=lambda kv: -kv[1])[:64]:
        qsparse[str(i)] = float(v)

    client = get_milvus_client()
    # 直插一条 content_type=promotion 到 course_public，验证 filter_expr 层隔离
    client.upsert(
        COLLECTION_NAME, partition_name="course_public",
        data=[{
            "id": zlib.crc32(b"t31_promo_in_course"),
            "chunk_id": "t31_promo_in_course",
            "content": "暑期大促 五折优惠 立即抢购 班次安排",
            "content_type": "promotion",
            "source_file": "x.pdf",
            "dense_vec": _pseudo_dense("暑期大促 五折"),
            "sparse_vec": {str(i): float(v) for i, v in sorted(
                embedder.build_sparse_vector("暑期大促 五折").items(), key=lambda kv: -kv[1])[:64]},
            "tenant_id": "course_public",
            "visibility": "public",
        }]
    )
    client.flush(COLLECTION_NAME)

    try:
        # 只搜 course_public 分区：不带过滤 → promotion 也可见（分区内）
        all_course = loader.hybrid_search(qvec, qsparse, tenant_ids=["course_public"], top_k=10)
        all_ids = {r["chunk_id"] for r in all_course}
        assert course_cid in all_ids and "t31_promo_in_course" in all_ids

        # 带 filter_expr 排促销/班次 → promotion 被过滤，课程 chunk 保留
        filtered = loader.hybrid_search(
            qvec, qsparse, tenant_ids=["course_public"], top_k=10,
            filter_expr='content_type not in ["promotion","schedule","announcement","marketing"]',
        )
        f_ids = {r["chunk_id"] for r in filtered}
        assert course_cid in f_ids
        assert "t31_promo_in_course" not in f_ids          # 促销文案不混入（GWT③）

        # 分区隔离：搜 course_public 不返回 _default 里的促销 chunk（R03: 按 canonical id 判定）
        assert promo_cid not in {r["chunk_id"] for r in all_course}
    finally:
        _cleanup_ids(course_cid, promo_cid, "t31_promo_in_course")