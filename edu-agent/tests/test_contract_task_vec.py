# -*- coding: utf-8 -*-
"""task-VEC 契约测试：三层记忆真实 BGE-M3(CUDA 1024 维) + Milvus 语义召回 + 降级链。

- 真实嵌入测试不产生 DeepSeek LLM 费用（本地 BGE-M3 GPU）。
- Milvus 集成测试在 Milvus 不可达时自动 skip（不强依赖外部机）。
- 用 `asyncio.run` 包异步逻辑，避免对 pytest 异步插件依赖。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # edu-agent/

from app.ai.memory.vector import (  # noqa: E402
    MemoryVectorStore,
    SemanticEmbedder,
    DeterministicEmbedder,
    _dim,
)

TEST_USER = 66001  # 契约测试专用 user，避免污染生产记忆


def _milvus_up() -> bool:
    try:
        from app.knowledge.importer.loader import get_milvus_client

        get_milvus_client().list_collections()
        return True
    except Exception:
        return False


def test_dim_aligns_embedding_dim() -> None:
    """GWT 维度：MemoryVectorStore 与 Milvus(BGE-M3) 统一 1024，不再 512。"""
    from app.config import settings

    store = MemoryVectorStore(milvus_uri="")
    assert store.dim == _dim() == settings.EMBEDDING_DIM == 1024


def test_semantic_embedder_dim_1024() -> None:
    """GWT①：真实 BGE-M3 输出 1024 维 python float，degraded=None。"""
    emb = SemanticEmbedder()
    v = emb.embed("用户偏好深度学习与神经网络")
    assert len(v) == 1024
    assert all(isinstance(x, float) for x in v)
    assert emb.degraded_reason is None


def test_degrade_when_bge_unavailable() -> None:
    """GWT③：BGE 不可用 → 降级哈希 1024 维，标注 degraded_reason，不 500。"""
    def boom(texts):
        raise RuntimeError("模拟 BGE-M3 CUDA 不可用")

    emb = SemanticEmbedder(encode_fn=boom)
    v = emb.embed("用户喜欢咖啡")
    assert len(v) == 1024
    assert emb.degraded_reason and "BGE-M3 不可用" in emb.degraded_reason
    # 降级向量有限、范围归一化（哈希向量 L2 归一，元素的绝对值 ≤1）
    assert all(abs(x) <= 1.0 for x in v)


def test_deterministic_fallback_is_1024() -> None:
    """降级维度须=1024（旧 512 与 Milvus 1024 混用会 upsert 失败）。"""
    d = DeterministicEmbedder()
    assert d.dim == 1024
    assert len(d.embed("test")) == 1024


def test_inmemory_backend_when_uri_empty() -> None:
    """milvus_uri='' → 强制内存后端，upsert/search 可用。"""

    async def run() -> list[int]:
        st = MemoryVectorStore(milvus_uri="")
        assert st.backend == "memory"
        await st.upsert(memory_id=1, user_id=TEST_USER, content="用户偏向深度学习")
        await st.upsert(memory_id=2, user_id=TEST_USER, content="用户下周订高铁票")
        hits = await st.search(user_id=TEST_USER, query="图像识别神经网络", top_k=1)
        return [h["memory_id"] for h in hits]

    assert asyncio.run(run()) == [1]


@pytest.mark.skipif(not _milvus_up(), reason="Milvus 不可达，跳过集成测试")
def test_milvus_upsert_semantic_recall_integration() -> None:
    """GWT①②④（集成）：写入真实 Milvus user_memory，语义查询召回相关记忆。"""

    async def run() -> dict:
        store = MemoryVectorStore()
        assert store.backend == "milvus"
        assert store.dim == 1024
        # 独立 user，写完清理
        uid = TEST_USER
        await store.clear_user(uid)
        cases = {
            10: "用户偏好深度学习和神经网络，用 PyTorch 研究图像分类",
            11: "用户下周五要去北京出差，订高铁票并安排酒店",
            12: "用户备考雅思，每天练英语口语听力",
        }
        for mid, content in cases.items():
            await store.upsert(memory_id=mid, user_id=uid, content=content)
        hits = await store.search(user_id=uid, query="图像识别用深度学习模型怎么做", top_k=3)
        await store.clear_user(uid)  # 清理，保持集合干净
        return {
            "degraded": store.degraded_reason,
            "top": [h["memory_id"] for h in hits],
            "top1_content": hits[0]["content"] if hits else "",
        }

    r = asyncio.run(run())
    assert r["degraded"] is None                 # 走真实 BGE，未降级
    assert r["top"] and r["top"][0] == 10        # 语义查询召回深度学习记忆居首
    assert "深度" in r["top1_content"]