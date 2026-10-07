# -*- coding: utf-8 -*-
"""
知识库导入 LangGraph 管道（P1 步骤 8）

流程：
    parse → chunk → contextualize → embed → load → graph_build → END

节点职责：
  parse          ：parser.parse_node —— 读文件、解析成初版 chunks
  chunk          ：chunker.chunk_node —— 按文本特征选择切分策略
  contextualize  ：contextualize.contextualize_node（task30）—— 知识型 chunk 生成 50-100 token 上下文前缀，
                   content=前缀版、raw_content=原文（向量化提召回）；题库/代码跳过；LLM 失败降级原文入库
  embed          ：embedder.embed_node —— 批量生成 dense(1024) + sparse(BM25-jieba)（对前缀版 content）
  load           ：pipeline 内 load_node —— 调用 loader.load_chunks 写 Milvus，累加 imported_count
  graph_build    ：graph_builder.graph_build_node —— 抽取实体关系，写 Neo4j（失败不阻断）

状态载体：app.knowledge.models.ImportState
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from app.knowledge.importer.chunker import chunk_node
from app.knowledge.importer.contextualize import contextualize_node
from app.knowledge.importer.embedder import embed_node
from app.knowledge.importer.graph_builder import graph_build_node
from app.knowledge.importer.loader import load_chunks
from app.knowledge.importer.parser import parse_node
from app.knowledge.models import ImportState


# ============================================================
# load_node 放在这里（P1 步骤 7 已验证 loader Schema 字段名统一为 dense_vec/sparse_vec）
# ============================================================
def load_node(state: ImportState) -> dict:
    """LangGraph 节点：把 state.chunks 写 Milvus，更新 imported_count。"""
    if state.error:
        logger.warning("跳过 load_node（前序已出错）")
        return {}
    if not state.chunks:
        logger.info("load_node：chunks 为空，跳过")
        return {}
    try:
        count = load_chunks(state.chunks, tenant_id=state.tenant_id)
        logger.info(f"load_node：成功写入 Milvus {count}/{len(state.chunks)} 条（tenant={state.tenant_id}）")
        return {"imported_count": state.imported_count + count}
    except Exception as exc:
        msg = f"Milvus 入库失败：{exc.__class__.__name__}: {exc}"
        logger.exception(msg)
        return {"error": msg}


# ============================================================
# 路由：决定 END 或继续（任何节点写了 state.error → 立即 END）
# ============================================================
def _should_stop(state: ImportState) -> str:
    if state.error:
        return "__end__"
    return "continue"


# ============================================================
# 构建 LangGraph StateGraph
# ============================================================
def build_import_pipeline():
    """
    构造 LangGraph 管道（懒加载，避免导入时强依赖 langgraph 安装）。

    返回可执行的 CompiledGraph。
    """
    try:
        from langgraph.graph import StateGraph, END
    except Exception as exc:  # pragma: no cover - 降级到线性执行
        logger.warning(f"langgraph 未安装（{exc}）→ 管道退化为线性顺序执行器 LinearImportPipeline")
        return LinearImportPipeline()

    graph = StateGraph(ImportState)
    graph.add_node("parse", parse_node)
    graph.add_node("chunk", chunk_node)
    graph.add_node("contextualize", contextualize_node)
    graph.add_node("embed", embed_node)
    graph.add_node("load", load_node)
    graph.add_node("graph_build", graph_build_node)

    graph.set_entry_point("parse")

    # 线性串：parse → chunk → contextualize → embed → load → graph_build → END
    graph.add_edge("parse", "chunk")
    graph.add_edge("chunk", "contextualize")
    graph.add_edge("contextualize", "embed")
    graph.add_edge("embed", "load")
    graph.add_edge("load", "graph_build")
    graph.add_edge("graph_build", END)

    return graph.compile()


# ============================================================
# 降级：langgraph 没装时，一个轻量顺序执行器（接口一致）
# ============================================================
class LinearImportPipeline:
    """langgraph 缺失时的降级实现：按顺序 invoke 5 个节点。"""

    def invoke(self, initial: dict[str, Any] | ImportState) -> ImportState:
        if isinstance(initial, ImportState):
            state = initial.model_copy(deep=True)
        else:
            state = ImportState(**initial)
        nodes = [
            ("parse", parse_node),
            ("chunk", chunk_node),
            ("contextualize", contextualize_node),
            ("embed", embed_node),
            ("load", load_node),
            ("graph_build", graph_build_node),
        ]
        for name, fn in nodes:
            if state.error:
                logger.warning(f"管道在节点 [{name}] 前中止（前序已出错）")
                break
            patch = fn(state) or {}
            # 把 patch 合到 state（ImportState 支持 dict 解包赋值）
            updates = {k: v for k, v in patch.items() if hasattr(state, k)}
            if updates:
                state = state.model_copy(update=updates)
            # 特殊字段：error 单独设
            if "error" in patch and not state.error:
                state = state.model_copy(update={"error": patch["error"]})
        return state


# ============================================================
# 高层便捷函数：一次跑完整条管道
# ============================================================
def run_import_pipeline(state: ImportState | dict) -> ImportState:
    """同步执行一次完整导入（同步阻塞接口，后台任务使用 run_in_threadpool 异步化）。"""
    pipeline = build_import_pipeline()
    result = pipeline.invoke(state)
    if isinstance(result, ImportState):
        return result
    return ImportState(**result)
