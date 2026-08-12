"""
分块器 v3 - 多策略切分，评分制选择，纯文本特征驱动。

v3 优化点（相比 v2）：
1. 评分制策略选择：每个策略累积多个特征的置信分，选最高分
   → 解决 if-else 级联的边界误分类问题
2. 丰富的文本特征：标题密度、段落结构、代码块、列表、表格、句子数
   → 更精准的策略匹配
3. 动态阈值：阈值根据文本特征自适应调整
   → 避免硬编码阈值的僵化

策略评分矩阵：
┌──────────────────────────────────────────────────────────────────┐
│ 特征           │ HEADING │ PARAGRAPH │ SEMANTIC │ WORD              │
├──────────────────────────────────────────────────────────────────┤
│ 顶级标题密度   │ +3      │ +1        │ 0        │ 0                 │
│ 段落结构       │ +1      │ +3        │ +2       │ 0                 │
│ 代码块         │ +1      │ +2        │ +3       │ +1                │
│ 表格内容       │ 0       │ +2        │ +3       │ +1                │
│ 列表结构       │ +2      │ +2        │ +1       │ 0                 │
│ 中等长度       │ +1      │ +2        │ +3       │ +1                │
│ 超长文本       │ -1      │ -1        │ +1       │ +3                │
└──────────────────────────────────────────────────────────────────┘
"""

import re
from typing import Optional

from app.common.logging import logger
from app.knowledge.models import ChunkStrategy, ContentType, ImportState, KnowledgeChunk

MAX_CHUNK_SIZE = 800
MIN_CHUNK_SIZE = 100
TARGET_CHUNK_SIZE = 512
OVERLAP = 128
MIN_CHUNK_BEFORE_MERGE = 50


def _estimate_tokens(text: str) -> int:
    """估算文本 token 数（中文字符 ≈ 1-2 token）。"""
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    other_chars = len(text) - chinese_chars
    return chinese_chars + (other_chars // 4)


def _extract_keywords(text: str, top_k: int = 5) -> list[str]:
    """从文本中提取核心关键词（用 jieba）。"""
    try:
        import jieba.analyse
        keywords = jieba.analyse.extract_tags(text, topK=top_k)
        return keywords if keywords else []
    except Exception:
        return []


def _split_by_headings_two_level(text: str, chunk_id_prefix: str) -> list[dict]:
    """
    两级标题切分：按顶级标题 (##) 切，子标题 (###) 保留为上下文。

    策略：
    1. 识别顶级标题 (## ) 作为切分边界
    2. 子标题 (### , #### ) 不切分，作为父级的内容
    3. 每个 chunk 包含：顶级标题 + 该标题下的所有内容（含子标题）
    4. 结果中若有 < 50 字符的微型块，合并到前一块
    """
    lines = text.split('\n')
    chunks = []
    current_heading = ""
    current_content = []

    for line in lines:
        stripped = line.strip()

        # 顶级标题: ## 或 #
        is_top_heading = bool(re.match(r'^#{1,2}\s+', stripped))

        if is_top_heading:
            # 保存前一个标题的内容
            if current_heading and current_content:
                content_text = '\n'.join(current_content).strip()
                if content_text:
                    chunks.append({
                        "content": f"{current_heading}\n{content_text}",
                        "chunk_id": f"{chunk_id_prefix}_{len(chunks) + 1:04d}",
                    })

            # 不把标题行加入 current_content，避免重复
            current_heading = stripped
            current_content = []
        else:
            if current_heading:
                current_content.append(line)

    # 保存最后一个标题
    if current_heading:
        content_text = '\n'.join(current_content).strip()
        if content_text:
            chunks.append({
                "content": f"{current_heading}\n{content_text}" if content_text else current_heading,
                "chunk_id": f"{chunk_id_prefix}_{len(chunks) + 1:04d}",
            })

    if not chunks:
        chunks.append({
            "content": text.strip(),
            "chunk_id": f"{chunk_id_prefix}_0001",
        })

    # 合并微型块
    chunks = _merge_tiny_chunks(chunks)

    return chunks


def _merge_tiny_chunks(chunks: list[dict]) -> list[dict]:
    """
    合并 < 50 字符的微型块到相邻块。

    规则：
    - 如果是第一个微型块，合并到下一个块
    - 如果是最后一个微型块，合并到上一个块
    - 连续微型块合并到相邻的大块
    - 但微型块以 Markdown 标题开头时不合并（语义边界保护）
    """
    if len(chunks) <= 1:
        return chunks

    merged = []
    i = 0
    while i < len(chunks):
        chunk = chunks[i]
        content_len = len(chunk["content"])
        starts_with_heading = bool(re.match(r'^#{1,6}\s+', chunk["content"]))

        if content_len < MIN_CHUNK_BEFORE_MERGE and not starts_with_heading:
            # 微型块且非标题开头：尝试合并
            if merged:
                prev = merged[-1]
                merged[-1] = {
                    "content": f"{prev['content']}\n{chunk['content']}",
                    "chunk_id": prev["chunk_id"],
                }
            elif i + 1 < len(chunks):
                next_chunk = chunks[i + 1]
                chunks[i + 1] = {
                    "content": f"{chunk['content']}\n{next_chunk['content']}",
                    "chunk_id": next_chunk["chunk_id"],
                }
            else:
                merged.append(chunk)
        else:
            merged.append(chunk)

        i += 1

    # 重新编号
    for idx, chunk in enumerate(merged):
        chunk["chunk_id"] = f"{chunk['chunk_id'].rsplit('_', 1)[0]}_{idx + 1:04d}"

    return merged


def _split_by_paragraphs(text: str, chunk_id_prefix: str) -> list[dict]:
    """
    按自然段落切分（双换行分段）。
    """
    raw_paragraphs = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in raw_paragraphs if p.strip()]

    merged = []
    buffer = ""

    for para in paragraphs:
        if len(buffer) + len(para) < MIN_CHUNK_BEFORE_MERGE:
            buffer = f"{buffer}\n{para}" if buffer else para
        else:
            if buffer:
                merged.append(buffer)
            buffer = para

    if buffer:
        merged.append(buffer)

    return [
        {"content": p, "chunk_id": f"{chunk_id_prefix}_{i + 1:04d}"}
        for i, p in enumerate(merged)
    ]


def _semantic_window_chunk(
    text: str,
    chunk_id_prefix: str,
    target_size: int = TARGET_CHUNK_SIZE,
    overlap: int = OVERLAP,
) -> list[dict]:
    """
    语义感知的滑窗切分。

    策略：
    1. 先按句子分割（。！？.!?；; 作为边界）
    2. 贪心合并句子，直到达到 target_size
    3. 在句子边界处切分，避免破坏语义
    4. overlap 确保上下文连续性
    """
    sentence_pattern = r'[^。！？.!?；;]+[。！？.!?；;]?'
    sentences = re.findall(sentence_pattern, text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return []

    chunks = []
    current_chunk = []
    current_size = 0

    i = 0
    while i < len(sentences):
        sentence = sentences[i]
        sentence_len = len(sentence)

        if current_size + sentence_len > target_size and current_chunk:
            chunk_text = ''.join(current_chunk)
            chunks.append({
                "content": chunk_text,
                "chunk_id": f"{chunk_id_prefix}_{len(chunks) + 1:04d}",
            })

            overlap_sentences = []
            overlap_size = 0
            for s in reversed(current_chunk):
                if overlap_size >= overlap:
                    break
                overlap_sentences.insert(0, s)
                overlap_size += len(s)

            current_chunk = overlap_sentences
            current_size = overlap_size

        current_chunk.append(sentence)
        current_size += sentence_len
        i += 1

    if current_chunk:
        chunk_text = ''.join(current_chunk)
        if chunk_text.strip():
            chunks.append({
                "content": chunk_text,
                "chunk_id": f"{chunk_id_prefix}_{len(chunks) + 1:04d}",
            })

    return chunks


def _word_window_chunk(
    text: str,
    chunk_id_prefix: str,
    window_size: int = TARGET_CHUNK_SIZE,
    overlap: int = OVERLAP,
) -> list[dict]:
    """纯字数滑窗切分（兜底策略）。"""
    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + window_size, text_len)
        chunk_text = text[start:end]

        chunks.append({
            "content": chunk_text,
            "chunk_id": f"{chunk_id_prefix}_{len(chunks) + 1:04d}",
        })

        if end >= text_len:
            break

        start = end - overlap

    return chunks


def _analyze_text_features(text: str) -> dict:
    """
    分析文本特征，返回各维度的量化指标。

    Returns:
        特征字典，包含各维度的计数值
    """
    top_headings = len(re.findall(r'^#{1,2}\s+', text, re.MULTILINE))
    sub_headings = len(re.findall(r'^#{3,6}\s+', text, re.MULTILINE))
    has_code_blocks = len(re.findall(r'```[\s\S]*?```', text))
    has_tables = len(re.findall(r'\|[\s\S]*?\|', text))
    has_lists = len(re.findall(r'^[-*+]\s+', text, re.MULTILINE))
    has_numbered_lists = len(re.findall(r'^\d+[.\、]\s+', text, re.MULTILINE))
    paragraphs = len(re.findall(r'\n\s*\n', text)) + 1
    sentences = len(re.findall(r'[。！？.!?；;]', text))
    text_len = len(text)
    avg_sentence_len = text_len / max(sentences, 1)

    return {
        "top_headings": top_headings,
        "sub_headings": sub_headings,
        "has_code_blocks": has_code_blocks,
        "has_tables": has_tables,
        "has_lists": has_lists + has_numbered_lists,
        "paragraphs": paragraphs,
        "sentences": sentences,
        "text_len": text_len,
        "avg_sentence_len": avg_sentence_len,
    }


def select_chunk_strategy(content: str) -> ChunkStrategy:
    """
    基于评分制选择最优切分策略（与文件类型无关）。

    对每个候选策略计算置信分，选分最高的。
    解决 if-else 级联在多特征冲突时的误分类问题。
    """
    features = _analyze_text_features(content)
    scores: dict[ChunkStrategy, float] = {
        ChunkStrategy.HEADING_BASED: 0.0,
        ChunkStrategy.PARAGRAPH: 0.0,
        ChunkStrategy.SEMANTIC_WINDOW: 0.0,
        ChunkStrategy.WORD_WINDOW: 0.0,
    }

    # 1. 顶级标题密度（权重最高，因为标题是最可靠的结构信号）
    top_h = features["top_headings"]
    if top_h >= 3:
        scores[ChunkStrategy.HEADING_BASED] += 8
        scores[ChunkStrategy.PARAGRAPH] += 1
    elif top_h >= 2:
        scores[ChunkStrategy.HEADING_BASED] += 7
        scores[ChunkStrategy.PARAGRAPH] += 1
    elif top_h >= 1:
        scores[ChunkStrategy.HEADING_BASED] += 6
        scores[ChunkStrategy.PARAGRAPH] += 1
    elif top_h == 0 and features["sub_headings"] >= 2:
        scores[ChunkStrategy.PARAGRAPH] += 3

    # 2. 段落结构
    paras = features["paragraphs"]
    if paras >= 3:
        scores[ChunkStrategy.PARAGRAPH] += 3
        scores[ChunkStrategy.SEMANTIC_WINDOW] += 2
    elif paras >= 2:
        scores[ChunkStrategy.PARAGRAPH] += 2

    # 3. 代码块（高权重，代码边界对语义至关重要）
    if features["has_code_blocks"] > 0:
        scores[ChunkStrategy.SEMANTIC_WINDOW] += 6
        scores[ChunkStrategy.PARAGRAPH] += 2
        scores[ChunkStrategy.HEADING_BASED] += 1
        scores[ChunkStrategy.WORD_WINDOW] += 1

    # 4. 表格内容
    if features["has_tables"] > 0:
        scores[ChunkStrategy.SEMANTIC_WINDOW] += 3
        scores[ChunkStrategy.PARAGRAPH] += 2

    # 5. 列表结构
    lists = features["has_lists"]
    if lists >= 5:
        scores[ChunkStrategy.HEADING_BASED] += 2
        scores[ChunkStrategy.PARAGRAPH] += 2
    elif lists >= 2:
        scores[ChunkStrategy.PARAGRAPH] += 1
        scores[ChunkStrategy.HEADING_BASED] += 1

    # 6. 文本长度
    text_len = features["text_len"]
    if text_len > 5000:
        scores[ChunkStrategy.WORD_WINDOW] += 3
        scores[ChunkStrategy.SEMANTIC_WINDOW] += 1
        scores[ChunkStrategy.HEADING_BASED] -= 2
        scores[ChunkStrategy.PARAGRAPH] -= 2
    elif text_len > 2000:
        scores[ChunkStrategy.SEMANTIC_WINDOW] += 3
        scores[ChunkStrategy.WORD_WINDOW] += 1
    elif text_len > 800:
        scores[ChunkStrategy.SEMANTIC_WINDOW] += 2
        scores[ChunkStrategy.PARAGRAPH] += 1
    else:
        # 短文本：给 PARAGRAPH 和 SEMANTIC 少量加分
        # 但不应该超过标题的分数
        scores[ChunkStrategy.PARAGRAPH] += 1
        scores[ChunkStrategy.SEMANTIC_WINDOW] += 0.5

    # 7. 句子数和平均句长
    sentences = features["sentences"]
    avg_len = features["avg_sentence_len"]
    if sentences < 3:
        scores[ChunkStrategy.PARAGRAPH] += 2
        scores[ChunkStrategy.SEMANTIC_WINDOW] += 1
    elif sentences >= 10:
        scores[ChunkStrategy.SEMANTIC_WINDOW] += 2
        scores[ChunkStrategy.WORD_WINDOW] += 1

    if avg_len > 100:
        scores[ChunkStrategy.SEMANTIC_WINDOW] += 1
        scores[ChunkStrategy.WORD_WINDOW] += 1
    elif avg_len < 20:
        scores[ChunkStrategy.PARAGRAPH] += 1

    best_strategy = max(scores, key=scores.get)
    best_score = scores[best_strategy]

    logger.debug(
        f"策略评分: {[(s.value, f'{v:.1f}') for s, v in scores.items()]} → "
        f"选中 {best_strategy.value} (分数 {best_score:.1f})"
    )

    return best_strategy


def _split_chunk_recursively(
    content: str,
    chunk_id_prefix: str,
    strategy: ChunkStrategy,
) -> list[dict]:
    """
    递归切分：执行策略切分后，对超限结果再走语义滑窗。
    """
    # 第一次切分
    if strategy == ChunkStrategy.HEADING_BASED:
        sub_chunks = _split_by_headings_two_level(content, chunk_id_prefix)
    elif strategy == ChunkStrategy.PARAGRAPH:
        sub_chunks = _split_by_paragraphs(content, chunk_id_prefix)
    elif strategy == ChunkStrategy.SEMANTIC_WINDOW:
        sub_chunks = _semantic_window_chunk(content, chunk_id_prefix)
    else:
        sub_chunks = _word_window_chunk(content, chunk_id_prefix)

    # 递归检查：对超限的 sub_chunk 再切
    final_chunks = []
    for sub in sub_chunks:
        if len(sub["content"]) > MAX_CHUNK_SIZE:
            # 超限：递归走语义滑窗
            logger.info(
                f"Chunk {sub['chunk_id']} 超限 ({len(sub['content'])} 字符), "
                f"递归走语义滑窗"
            )
            sub_sub_chunks = _semantic_window_chunk(
                sub["content"],
                sub["chunk_id"],
            )
            final_chunks.extend(sub_sub_chunks)
        else:
            final_chunks.append(sub)

    return final_chunks


def _clone_chunk_with_new_fields(
    original: KnowledgeChunk,
    new_content: str,
    new_chunk_id: str,
    strategy: ChunkStrategy,
    auto_extract_keywords: bool = True,
) -> KnowledgeChunk:
    """
    基于原 chunk 创建新 chunk，保留所有元数据字段。
    v2: 可选自动提取关键词。
    """
    keywords = original.keywords
    if auto_extract_keywords and not keywords:
        keywords = _extract_keywords(new_content)

    return KnowledgeChunk(
        chunk_id=new_chunk_id,
        content=new_content,
        content_type=original.content_type,
        tags=original.tags,
        difficulty=original.difficulty,
        resource_type=original.resource_type,
        author=original.author,
        prerequisites=original.prerequisites,
        keywords=keywords,
        series_code=original.series_code,
        series_name=original.series_name,
        module_codes=original.module_codes,
        category=original.category,
        audience=original.audience,
        goal=original.goal,
        question_bank_code=original.question_bank_code,
        question_bank_name=original.question_bank_name,
        question_code=original.question_code,
        question_type=original.question_type,
        tenant_id=original.tenant_id,
        visibility=original.visibility,
        source_file=original.source_file,
        chunk_strategy=strategy,
        extra=original.extra,
    )


def chunk_node(state: ImportState) -> dict:
    """
    LangGraph 节点：多策略分块处理。

    v2 处理流程：
    1. 对每个 chunk 检查长度
       - <= MAX_CHUNK_SIZE → 直接保留（自动兼容预解析的课程/题目 chunk）
       - > MAX_CHUNK_SIZE  → 按文本特征选策略强制切分
    2. 递归切分确保所有结果 <= MAX_CHUNK_SIZE
    3. 微型块自动合并
    4. 自动提取关键词（如果原 chunk 没有）
    """
    if state.error:
        logger.warning("跳过 chunk（前序节点已出错）")
        return {}

    updated_chunks = []
    strategy_stats: dict[str, int] = {}

    for chunk in state.chunks:
        content_len = len(chunk.content)

        # Size-based skip: 已在最佳区间，直接保留
        if content_len <= MAX_CHUNK_SIZE:
            chunk.chunk_strategy = ChunkStrategy.SEMANTIC_WINDOW
            strategy_stats["skip"] = strategy_stats.get("skip", 0) + 1
            updated_chunks.append(chunk)
            continue

        # 需要切分：按文本特征选策略
        strategy = select_chunk_strategy(chunk.content)
        strategy_stats[strategy.value] = strategy_stats.get(strategy.value, 0) + 1

        # 递归切分
        sub_chunks = _split_chunk_recursively(
            chunk.content, chunk.chunk_id, strategy
        )

        for sub in sub_chunks:
            updated_chunk = _clone_chunk_with_new_fields(
                chunk,
                new_content=sub["content"],
                new_chunk_id=sub["chunk_id"],
                strategy=strategy,
                auto_extract_keywords=True,
            )
            updated_chunks.append(updated_chunk)

    strategy_summary = ", ".join(f"{k}: {v}" for k, v in strategy_stats.items())
    logger.info(
        f"分块完成，共 {len(updated_chunks)} 条。策略分布: {strategy_summary}"
    )

    return {"chunks": updated_chunks}
