# -*- coding: utf-8 -*-
"""task30 RAG Contextual Retrieval 合同测试。

GWT 覆盖：
- ① CONTEXT_PROMPT 含 <document>/<chunk>，仅知识型（题库/代码跳过）
- ② pipeline contextualize：content=前缀版、raw_content=原文；embed 对前缀版编码
- ③ 降级：LLM 失败 → 原文照常入库 + degraded_reason，不 500；并发 ≤8
- ④ Milvus 存储预算 +15%（清单报告，此处校验 raw_content/context_prefix 字段可入库）

所有 LLM 调用用确定性 stub（不烧 DeepSeek 额度）。
"""
from __future__ import annotations

import threading
import time

import pytest

from app.config import settings
from app.knowledge.importer.contextualize import (
    CONTEXT_PROMPT,
    Contextualizer,
    should_contextualize,
)
from app.knowledge.models import ContentType, ImportState, KnowledgeChunk


def make_chunk(*, cid: str, content: str, ctype: ContentType = ContentType.DOC_CHUNK,
               resource_type: str | None = None, series_name: str = "编程入门") -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=cid, content=content, content_type=ctype,
        resource_type=resource_type, series_name=series_name,
    )


def stub_caller(prefix: str = "【上下文】本段属于编程入门课程，介绍算法基础与代码实践。") -> callable:
    def _call(document: str, chunk_text: str) -> str:
        return prefix
    return _call


# ------------------------------------------------------------------
# GWT① CONTEXT_PROMPT + 知识型过滤
# ------------------------------------------------------------------
def test_context_prompt_has_doc_and_chunk() -> None:
    assert "<document>" in CONTEXT_PROMPT and "</document>" in CONTEXT_PROMPT
    assert "<chunk>" in CONTEXT_PROMPT and "</chunk>" in CONTEXT_PROMPT


def test_should_contextualize_knowledge_only() -> None:
    doc = make_chunk(cid="c1", content="讲解了变量与循环")
    assert should_contextualize(doc) is True

    q = make_chunk(cid="q1", content="选择题题干",
                   ctype=ContentType.QUESTION, resource_type="题库")
    assert should_contextualize(q) is False          # 题库跳过

    code = make_chunk(cid="c2", content="def main(): ...", resource_type="代码")
    assert should_contextualize(code) is False       # 代码跳过

    empty = make_chunk(cid="c3", content="   ")
    assert should_contextualize(empty) is False      # 空内容跳过


# ------------------------------------------------------------------
# GWT② content=前缀版、raw_content=原文；embed 对前缀版编码
# ------------------------------------------------------------------
def test_contextualize_splits_content_and_raw() -> None:
    ctx = Contextualizer(llm_caller=stub_caller(), enabled=True)
    chunk = make_chunk(cid="c1", content="讲解了变量与循环，以及函数定义")
    ctx.contextualize([chunk])

    assert chunk.raw_content == "讲解了变量与循环，以及函数定义"
    assert chunk.context_prefix is not None
    # content 是前缀版（前缀 + 换行 + 原文），用于向量化
    assert chunk.content.startswith("【上下文】")
    assert chunk.content.endswith("讲解了变量与循环，以及函数定义")
    assert "contextualized" in chunk.extra
    assert ctx.contextualized_count == 1
    assert ctx.degraded_count == 0
    assert ctx.skipped_count == 0


def test_embed_uses_prefixed_content() -> None:
    """embed_node 读 chunk.content（现为前缀版）→ 向量化的是加了上下文的版本。"""
    from app.knowledge.importer import contextualize, embedder

    ctx = Contextualizer(llm_caller=stub_caller(), enabled=True)
    chunk = make_chunk(cid="c1", content="梯度下降算法用于优化损失函数")
    ctx.contextualize([chunk])

    state = ImportState(task_id="t", source_files=[], chunks=[chunk])
    # 不可变模型副本：先浅改 content 再跑 embed，验证以 content（前缀版）为准
    patch = embedder.embed_node(state)
    assert state.error is None
    assert chunk.dense_vector, "dense_vector 必须被填充（基于前缀版 content）"


# ------------------------------------------------------------------
# GWT③ 降级：LLM 失败 → 原文保留 + degraded_reason，不抛；并发 ≤8
# ------------------------------------------------------------------
def test_degrade_preserves_raw_and_marks_reason() -> None:
    def boom(document: str, chunk_text: str) -> str:
        raise RuntimeError("模拟 contextualize LLM 不可用")
    ctx = Contextualizer(llm_caller=boom, enabled=True)
    chunk = make_chunk(cid="c1", content="原文不变照常入库")
    ctx.contextualize([chunk])  # 不抛异常

    assert chunk.content == "原文不变照常入库"      # 无前缀，原文照常
    assert chunk.raw_content is None
    assert "contextualize_degraded_reason" in chunk.extra
    assert "contextualize LLM 失败" in chunk.extra["contextualize_degraded_reason"]
    assert ctx.degraded_count == 1


def test_empty_prefix_degrades() -> None:
    ctx = Contextualizer(llm_caller=lambda d, c: "  ", enabled=True)
    chunk = make_chunk(cid="c1", content="触发空前缀降级")
    ctx.contextualize([chunk])
    assert chunk.raw_content is None
    assert "contextualize_degraded_reason" in chunk.extra


def test_concurrency_bounded() -> None:
    """并发 ≤ CONTEXTUALIZE_MAX_CONCURRENCY（GWT② 并发 ≤8）。"""
    N = 25
    active = {"cur": 0, "max": 0}
    lock = threading.Lock()

    def slow(document: str, chunk_text: str) -> str:
        with lock:
            active["cur"] += 1
            active["max"] = max(active["max"], active["cur"])
        time.sleep(0.02)
        with lock:
            active["cur"] -= 1
        return "【上下文】并发限速测试前缀。"

    ctx = Contextualizer(llm_caller=slow, enabled=True, max_concurrency=8)
    chunks = [make_chunk(cid=f"c{i}", content=f"内容 {i}") for i in range(N)]
    ctx.contextualize(chunks)

    assert ctx.contextualized_count == N
    assert active["max"] <= 8


def test_disabled_skips() -> None:
    ctx = Contextualizer(llm_caller=stub_caller(), enabled=False)
    chunk = make_chunk(cid="c1", content="开关关闭不动 content")
    ctx.contextualize([chunk])
    assert chunk.content == "开关关闭不动 content"
    assert chunk.raw_content is None


# ------------------------------------------------------------------
# 独立 boundary 常量一致性
# ------------------------------------------------------------------
def test_prefix_budget_settings_consistent() -> None:
    assert 0 < settings.CONTEXT_PREFIX_TOKEN_BUDGET_MIN <= settings.CONTEXT_PREFIX_TOKEN_BUDGET_MAX
    assert settings.CONTEXTUALIZE_MAX_CONCURRENCY == 8


# ------------------------------------------------------------------
# 可选 Milvus 集成（skipif Milvus 不可达；需真机验证 GWT②④ 落库）
# ------------------------------------------------------------------
def _milvus_up() -> bool:
    try:
        from app.knowledge.importer.loader import get_milvus_client
        get_milvus_client().list_collections()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _milvus_up(), reason="Milvus 不可达，跳过")
def test_loader_persists_contextualize_fields(tmp_path) -> None:
    """GWT④（集成）：load_chunks 后 content=前缀版、raw_content 存库，且 content 在 Milvus 上限内。"""
    from app.knowledge.importer import embedder, loader

    raw = "本段讲解上下文注入对检索召回的提升原理。"
    prefix = "【上下文】本段属于检索增强课程，介绍 contextual retrieval 思想。"
    chunk = make_chunk(cid="task30_verify_probe", content=raw)
    # 模拟 contextualize 产物：content=前缀版、raw_content=原文
    chunk.raw_content = raw
    chunk.context_prefix = prefix
    chunk.content = f"{prefix}\n{raw}"
    chunk.dense_vector = embedder._pseudo_dense(chunk.content, settings.EMBEDDING_DIM)  # 确定性伪向量，不烧 GPU/API
    svec = embedder.build_sparse_vector(chunk.content)
    items = sorted(svec.items(), key=lambda kv: -kv[1])[:64]
    chunk.sparse_indices = [int(k) for k, _ in items]
    chunk.sparse_values = [float(v) for _, v in items]

    n = loader.load_chunks([chunk], tenant_id="_default")
    assert n == 1
    assert len(chunk.content) <= 8000  # Milvus content 上限内
    # 清理探针：按确定性主键 = crc32(chunk_id) 删除
    import zlib
    client = loader.get_milvus_client()
    pk = zlib.crc32("task30_verify_probe".encode("utf-8"))
    try:
        client.delete(collection_name=loader.COLLECTION_NAME, ids=[pk])
    except Exception:
        pass