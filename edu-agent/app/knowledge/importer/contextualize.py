# -*- coding: utf-8 -*-
"""
task30 RAG Contextual Retrieval - 写入步骤的 chunk 上下文前缀（chunker→contextualize→embedder）。

对齐 tech-source-audit 三（Anthropic Contextual Retrieval：contextual embeddings 降 35% 召回失败率）：
- CONTEXT_PROMPT `<document>+<chunk>` → 生成 50-100 token 的上下文前缀（仅知识型内容，题库/代码跳过）。
- 产物：`chunk.content` = 前缀版（用于向量化，提高召回）；`chunk.raw_content` = 原文（answer 展示用）。
- 降级（GWT③）：LLM 调用失败 → 保留无前缀原 chunk 照常入库 + `extra.contextualize_degraded_reason`，不 500。
- 并发 ≤8（GWT②）：以 CONTEXTUALIZE_MAX_CONCURRENCY 限速，不击穿 LLM 预算。

LLM 调用可注入（`llm_caller(document, chunk_text) -> prefix`），默认走 app.chat.generator 的
_ChatClient（OpenAI 兼容 / a6api / DashScope）。契约单测注入确定性 stub，不烧付费额度。
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from loguru import logger

from app.config import settings
from app.knowledge.models import ContentType, KnowledgeChunk


# ============================================================
# 1. CONTEXT_PROMPT：给定 <document> + <chunk> 生成 50-100 token 中文上下文前缀
# ============================================================
CONTEXT_PROMPT = (
    "你是一个为知识检索做准备的 context 助手。给你一段<文档上下文>和其中的<片段>，"
    "请写一个简短的中文上下文描述，把<片段>放到所属文档的主题语境里，便于后续语义检索命中。"
    f"要求：(1) 仅输出描述本身，不要重复<片段>原文；(2) 控制在{settings.CONTEXT_PREFIX_TOKEN_BUDGET_MIN}"
    f"-{settings.CONTEXT_PREFIX_TOKEN_BUDGET_MAX}个token；(3) 只描述与<片段>相关的内容。"
    "\n<document>\n{document}\n</document>"
    "\n<chunk>\n{chunk}\n</chunk>"
)

# 非知识型 content_type：题库（question）跳过（GWT①「题库跳过」）
_SKIP_CONTENT_TYPES = {ContentType.QUESTION}
# 代码类 resource_type 跳过（GWT①「代码跳过」）
_CODE_RESOURCE_MARKERS = ("代码", "code", "coding", "program", "source")


def _is_code_resource(resource_type: str | None) -> bool:
    rt = (resource_type or "").strip().lower()
    if not rt:
        return False
    return any(m in rt for m in _CODE_RESOURCE_MARKERS)


def should_contextualize(chunk: KnowledgeChunk) -> bool:
    """是否对该 chunk 生成上下文前缀：仅知识型内容，题库/代码跳过。"""
    if chunk.content_type in _SKIP_CONTENT_TYPES:
        return False
    if _is_code_resource(chunk.resource_type):
        return False
    if not (chunk.content or "").strip():
        return False
    return True


def _build_document_context(chunk: KnowledgeChunk) -> str:
    """从 chunk 元数据 + 片段自身构造 <document> 语境（pipeline 不携带整篇原文，据此足矣）。"""
    bits: list[str] = []
    if chunk.series_name:
        bits.append(f"课程/系列：{chunk.series_name}")
    if chunk.category:
        bits.append(f"分类：{chunk.category}")
    if chunk.module_codes:
        bits.append(f"模块：{'、'.join(chunk.module_codes)}")
    if chunk.goal:
        bits.append(f"目标：{chunk.goal}")
    if chunk.source_file:
        bits.append(f"来源文件：{chunk.source_file}")
    if chunk.tags:
        bits.append(f"标签：{'、'.join(chunk.tags)}")
    body = "；".join(bits) if bits else "无额外元数据。"
    head = (chunk.content or "").strip()
    head_snippet = (head[:80] + "…") if len(head) > 80 else head
    return f"{body}\n（片段自身开头：{head_snippet}）"


def _default_llm_caller(document: str, chunk_text: str) -> str:
    """默认 LLM 调用（OpenAI 兼容，走 a6api/DashScope，非流式，同步阻塞）。

    仅供本模块内部使用；契约测试注入 stub 而非调用它，避免烧 DeepSeek。单次 max_tokens=200 已覆盖前缀。
    """
    from app.chat.generator import _ChatClient  # 复用统一 LLM 客户端（直连 / 禁系统代理）

    messages = [
        {"role": "user", "content": CONTEXT_PROMPT.format(document=document, chunk=chunk_text)}
    ]
    raw = _ChatClient.get().call_chat(
        messages=messages,
        model=settings.CONTEXTUALIZE_MODEL,
        temperature=0.0,        # 确定性前缀，稳定缓存命中前缀
        max_tokens=200,         # 50-100 token 前缀，200 上限留余量
        timeout=30.0,           # 单次调用超时兜底（GWT③ 降级）
    )
    return (raw or "").strip()


# ============================================================
# 2. Contextualizer：批量 + 并发限速 + 降级标注
# ============================================================
class Contextualizer:
    """把 pipeline 中一批 chunk 做上下文前缀化。

    - `enabled=False`：跳过，不产生任何前缀（CONTEXTUALIZE_ENABLED 总开关）。
    - 仅 `should_contextualize` 通过的 chunk 参与；
    - 并发用线程池限制 ≤ max_concurrency（LangGraph 节点为同步，线程池最贴合）；
    - LLM 失败单条降级（原文保留 + degraded_reason），整批不抛。
    """

    def __init__(
        self,
        *,
        llm_caller: Callable[[str, str], str] | None = None,
        max_concurrency: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._caller = llm_caller or _default_llm_caller
        self._max_concurrency = max(
            1, int(max_concurrency if max_concurrency is not None else settings.CONTEXTUALIZE_MAX_CONCURRENCY)
        )
        self.enabled = bool(enabled if enabled is not None else settings.CONTEXTUALIZE_ENABLED)
        self.degraded_count = 0
        self.contextualized_count = 0
        self.skipped_count = 0
        self._lock = threading.Lock()

    def contextualize(self, chunks: list[KnowledgeChunk]) -> None:
        """就地处理 list[KnowledgeChunk]。破坏性：改写 content/raw_content/extra。"""
        if not self.enabled:
            return
        if not chunks:
            return

        # 找 eligible 索引（知识型 + 有内容）；跳过项记录
        todo: list[tuple[int, KnowledgeChunk]] = []
        for idx, c in enumerate(chunks):
            if should_contextualize(c):
                todo.append((idx, c))
            else:
                self.skipped_count += 1

        if not todo:
            return

        # 单条处理：成功→前缀版；失败→原文保留 + degraded_reason（GWT③）
        def _process(item: tuple[int, KnowledgeChunk]) -> None:
            idx, chunk = item
            doc = _build_document_context(chunk)
            try:
                prefix = (self._caller(doc, chunk.content) or "").strip()
            except Exception as exc:  # 降级，绝不 500
                with self._lock:
                    self.degraded_count += 1
                chunk.extra["contextualize_degraded_reason"] = (
                    f"contextualize LLM 失败: {type(exc).__name__}: {str(exc)[:200]}"
                )
                logger.warning(f"[contextualize] chunk={chunk.chunk_id} 降级（原文入库）: {exc}")
                return
            if not prefix:
                with self._lock:
                    self.degraded_count += 1
                chunk.extra["contextualize_degraded_reason"] = "contextualize LLM 返回空前缀"
                logger.warning(f"[contextualize] chunk={chunk.chunk_id} 降级（空前缀）")
                return
            # 前缀版作 content（向量化用），原文作 raw_content（展示用）
            chunk.raw_content = chunk.content
            chunk.context_prefix = prefix
            chunk.content = f"{prefix}\n{chunk.content}"
            chunk.extra["contextualized"] = True
            chunk.extra["context_prefix"] = prefix
            with self._lock:
                self.contextualized_count += 1

        workers = min(self._max_concurrency, len(todo))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_process, item) for item in todo]
            for fut in as_completed(futures):
                exc = fut.exception()
                if exc is not None:  # 理论不可达（已 try/except），兜底防单条崩溃带崩整批
                    logger.warning(f"[contextualize] 线程异常（忽略，不影响入库）: {exc}")

        logger.info(
            f"[contextualize] 完成：contextualized={self.contextualized_count} / "
            f"degraded={self.degraded_count} / skipped={self.skipped_count}（并发≤{self._max_concurrency}）"
        )
        return


def contextualize_node(state: ImportState, *, llm_caller: Callable[[str, str], str] | None = None) -> dict:
    """LangGraph 节点：parse → chunk → **contextualize** → embed → load。

    失败不置 error（降级原则：无前缀原 chunk 照常入库），仅逐条标注 degraded_reason。
    """
    if state.error:
        logger.warning("跳过 contextualize（前序已出错）")
        return {}
    if not state.chunks:
        return {}
    Contextualizer(llm_caller=llm_caller).contextualize(state.chunks)
    return {}


# 延迟导入避免循环依赖（pipeline 运行时已 import 本模块）
from app.knowledge.models import ImportState  # noqa: E402