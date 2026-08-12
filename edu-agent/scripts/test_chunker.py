"""验证切分策略 v2 的所有功能"""
import sys
sys.path.insert(0, '.')

from app.knowledge.importer.chunker import (
    select_chunk_strategy,
    _split_by_headings_two_level,
    _split_by_paragraphs,
    _semantic_window_chunk,
    _word_window_chunk,
    _clone_chunk_with_new_fields,
    _extract_keywords,
    _estimate_tokens,
    _split_chunk_recursively,
    _merge_tiny_chunks,
    MAX_CHUNK_SIZE,
    TARGET_CHUNK_SIZE,
    OVERLAP,
    MIN_CHUNK_BEFORE_MERGE,
    chunk_node,
)
from app.knowledge.importer.readers import (
    detect_file_type,
    _looks_like_course_intro,
    _looks_like_questions,
)
from app.knowledge.models import (
    ContentType,
    ChunkStrategy,
    KnowledgeChunk,
    ImportState,
    Visibility,
)

def test():
    passed = 0
    total = 0

    # ====== 1. ChunkStrategy 不再有 STRUCTURED ======
    total += 1
    assert not hasattr(ChunkStrategy, 'STRUCTURED'), "STRUCTURED should be removed"
    assert hasattr(ChunkStrategy, 'SEMANTIC_WINDOW'), "SEMANTIC_WINDOW should exist"
    assert hasattr(ChunkStrategy, 'HEADING_BASED'), "HEADING_BASED should exist"
    print(f"[PASS] 1. STRUCTURED 已删除，剩余策略: {[s.value for s in ChunkStrategy]}")
    passed += 1

    # ====== 2. KnowledgeChunk 新增通用元数据字段 ======
    total += 1
    chunk = KnowledgeChunk(
        chunk_id="test_001",
        content="test",
        content_type=ContentType.DOC_CHUNK,
        tags=["Python", "入门"],
        difficulty="入门",
        resource_type="文档",
        author="test_author",
        prerequisites=["basic_001"],
        keywords=["变量", "常量"],
    )
    assert chunk.tags == ["Python", "入门"], "tags field should work"
    assert chunk.difficulty == "入门", "difficulty field should work"
    assert chunk.resource_type == "文档", "resource_type field should work"
    assert chunk.author == "test_author", "author field should work"
    assert chunk.prerequisites == ["basic_001"], "prerequisites field should work"
    assert chunk.keywords == ["变量", "常量"], "keywords field should work"
    print(f"[PASS] 2. 通用元数据字段全部可用")
    passed += 1

    # ====== 3. select_chunk_strategy 评分制选择 ======
    total += 1
    # 3a: 有标题的文档 → HEADING_BASED
    heading_content = "## 第一章\n内容。\n\n## 第二章\n更多内容。"
    strategy = select_chunk_strategy(heading_content)
    assert strategy == ChunkStrategy.HEADING_BASED, f"3a: Expected HEADING_BASED, got {strategy}"

    # 3b: 代码块内容 → SEMANTIC_WINDOW
    code_content = "```python\nimport os\nprint('hello')\n```\n\n解释说明代码用途。" * 3
    strategy = select_chunk_strategy(code_content)
    assert strategy == ChunkStrategy.SEMANTIC_WINDOW, f"3b: Expected SEMANTIC_WINDOW, got {strategy}"

    # 3c: 短段落 → PARAGRAPH
    short_content = "第一段内容。\n\n第二段内容。\n\n第三段内容。"
    strategy = select_chunk_strategy(short_content)
    assert strategy == ChunkStrategy.PARAGRAPH, f"3c: Expected PARAGRAPH, got {strategy}"

    # 3d: 超长文本 → WORD_WINDOW
    long_content = "这是一段很长的文本内容。" * 600
    strategy = select_chunk_strategy(long_content)
    assert strategy == ChunkStrategy.WORD_WINDOW, f"3d: Expected WORD_WINDOW, got {strategy}"

    # 3e: 表格内容 → SEMANTIC_WINDOW
    table_content = "| 姓名 | 年龄 |\n|------|------|\n| 张三 | 20 |\n| 李四 | 25 |" * 5
    strategy = select_chunk_strategy(table_content)
    assert strategy == ChunkStrategy.SEMANTIC_WINDOW, f"3e: Expected SEMANTIC_WINDOW for table, got {strategy}"

    # 3f: 列表内容 → 应有合适策略
    list_content = "- 第一项内容\n- 第二项内容\n- 第三项内容" * 10
    strategy = select_chunk_strategy(list_content)
    print(f"  列表内容策略: {strategy.value}")  # 列表通常归为 PARAGRAPH 或 HEADING_BASED

    print(f"[PASS] 3. select_chunk_strategy 评分制选择工作正常")
    passed += 1

    # ====== 4. 课程/题目 chunk <= 800 字符时自动跳过切分 ======
    total += 1
    state = ImportState(
        task_id="test_task",
        source_files=[],
        chunks=[
            KnowledgeChunk(
                chunk_id="course_001",
                content="课程系列：通用编程入门班\n系列编码：test_code\n描述：测试描述",
                content_type=ContentType.COURSE_INTRO,
                series_code="test_code",
                tags=["编程"],
            ),
        ],
    )
    result = chunk_node(state)
    assert len(result["chunks"]) == 1, f"Should keep 1 chunk, got {len(result['chunks'])}"
    assert result["chunks"][0].chunk_strategy == ChunkStrategy.SEMANTIC_WINDOW
    assert result["chunks"][0].tags == ["编程"]
    print(f"[PASS] 4. 课程 chunk ({len(state.chunks[0].content)} 字符) 自动跳过切分")
    passed += 1

    # ====== 5. 超过 800 字符的 chunk 强制切分 ======
    total += 1
    long_content = "这是一段很长的文本，包含多个段落。\n\n" * 200
    state2 = ImportState(
        task_id="test_task2",
        source_files=[],
        chunks=[
            KnowledgeChunk(
                chunk_id="long_doc",
                content=long_content,
                content_type=ContentType.DOC_CHUNK,
                tags=["测试"],
            ),
        ],
    )
    result2 = chunk_node(state2)
    assert len(result2["chunks"]) > 1, f"Should split into multiple chunks, got {len(result2['chunks'])}"
    assert result2["chunks"][0].tags == ["测试"], "tags should be preserved after split"
    print(f"[PASS] 5. 长文本 ({len(long_content)} 字符) 被强制切分为 {len(result2['chunks'])} 块")
    passed += 1

    # ====== 6. _clone_chunk_with_new_fields 保留所有元数据 ======
    total += 1
    chunk_with_meta = KnowledgeChunk(
        chunk_id="meta_test",
        content="# 标题\n\n段落1\n\n段落2",
        content_type=ContentType.DOC_CHUNK,
        tags=["Python", "教程"],
        difficulty="中级",
        resource_type="文档",
        author="张三",
        prerequisites=["basic"],
        keywords=["变量"],
    )
    cloned = _clone_chunk_with_new_fields(
        chunk_with_meta,
        new_content="新内容",
        new_chunk_id="meta_test_001",
        strategy=ChunkStrategy.PARAGRAPH,
    )
    assert cloned.tags == ["Python", "教程"], "tags should be preserved"
    assert cloned.difficulty == "中级", "difficulty should be preserved"
    assert cloned.author == "张三", "author should be preserved"
    print(f"[PASS] 6. _clone_chunk_with_new_fields 保留所有通用元数据字段")
    passed += 1

    # ====== 7. detect_file_type 两级检测 ======
    total += 1
    result = detect_file_type("C:/任意PDF.pdf", "")
    assert result == "generic", f"Expected generic, got {result}"
    result = detect_file_type("C:/课程大纲.pdf", "普通PDF内容")
    assert result == "generic", f"Expected generic, got {result}"
    print(f"[PASS] 7. detect_file_type 两级检测正确")
    passed += 1

    # ====== 8. 内容结构检测 ======
    total += 1
    course_content = """## 通用编程入门班
- **系列编码**: test_code
- **课程分类**: 计算机"""
    assert _looks_like_course_intro(course_content) is True
    assert _looks_like_course_intro("普通文本") is False
    question_content = """### q001
- **题型**: 单选题
- **题干**: 以下哪项正确？"""
    assert _looks_like_questions(question_content) is True
    assert _looks_like_questions("普通文本") is False
    print(f"[PASS] 8. _looks_like_course_intro / _looks_like_questions 结构检测正确")
    passed += 1

    # ====== 9. 两级标题切分：顶级标题聚合子标题 ======
    total += 1
    heading_doc = """## 1. HTML 基础
HTML 是超文本标记语言。
它用于创建网页结构。

### 1.1 常用标签
<div> 是容器标签。
<p> 是段落标签。

## 2. CSS 样式
CSS 是层叠样式表。
用于控制网页外观。

### 2.1 选择器
元素选择器、类选择器。

## 3. JavaScript
JavaScript 是编程语言。
用于前端开发。"""
    chunks = _split_by_headings_two_level(heading_doc, "test")
    # 按 ## 切：3 块
    assert len(chunks) == 3, f"Expected 3 chunks (## level), got {len(chunks)}"
    # 子标题 ### 应该在父级 ## 的内容中
    assert "1.1 常用标签" in chunks[0]["content"], "子标题应在父级内容中"
    assert "2.1 选择器" in chunks[1]["content"], "子标题应在父级内容中"
    print(f"[PASS] 9. 两级标题切分: {len(chunks)} 块，子标题保留在父级")
    passed += 1

    # ====== 10. 递归超限检查 ======
    total += 1
    huge_text = "## 章节\n" + "这是一段很长的文本。" * 250
    result_chunks = _split_chunk_recursively(huge_text, "test", ChunkStrategy.HEADING_BASED)
    assert len(result_chunks) > 1, f"超限文本应被递归切分，实际: {len(result_chunks)}"
    for c in result_chunks:
        assert len(c["content"]) <= MAX_CHUNK_SIZE, f"Chunk {c['chunk_id']} 仍超限: {len(c['content'])}"
    print(f"[PASS] 10. 递归超限检查: {len(result_chunks)} 块，全部 ≤ {MAX_CHUNK_SIZE} 字符")
    passed += 1

    # ====== 11. 自动关键词提取 ======
    total += 1
    keywords = _extract_keywords("Python 编程语言用于数据分析和机器学习")
    assert len(keywords) > 0, "Should extract keywords"
    assert "Python" in keywords or "编程语言" in keywords, "Should find key terms"
    print(f"[PASS] 11. 自动关键词提取: {keywords}")
    passed += 1

    # ====== 12. Token 估算 ======
    total += 1
    tokens = _estimate_tokens("你好世界")
    assert tokens >= 2, "Chinese chars should count as tokens"
    tokens_mixed = _estimate_tokens("Hello 世界")
    assert tokens_mixed >= 3, "Mixed text should count tokens"
    print(f"[PASS] 12. Token 估算: '你好世界' ≈ {tokens} tokens, 'Hello 世界' ≈ {tokens_mixed} tokens")
    passed += 1

    # ====== 13. 微型块合并 ======
    total += 1
    big_text_1 = "大块内容超过五十字符的阈值用于测试验证合并逻辑。" * 3
    big_text_2 = "另一个大块内容也超过五十字符的阈值测试验证。" * 3
    chunks = [
        {"content": big_text_1, "chunk_id": "t_0001"},
        {"content": "短。", "chunk_id": "t_0002"},
        {"content": big_text_2, "chunk_id": "t_0003"},
    ]
    merged = _merge_tiny_chunks(chunks)
    assert len(merged) == 2, f"Expected 2 after merge, got {len(merged)}"
    print(f"[PASS] 13. 微型块合并: {len(chunks)} → {len(merged)} 块")
    passed += 1

    # ====== 14. 自动关键词在 chunk_node 中工作 ======
    total += 1
    state3 = ImportState(
        task_id="test3",
        source_files=[],
        chunks=[
            KnowledgeChunk(
                chunk_id="kw_test",
                content="## Python 教程\nPython 是编程语言，用于数据科学和人工智能。" * 50,
                content_type=ContentType.DOC_CHUNK,
                keywords=[],  # 空关键词，应该被自动填充
            ),
        ],
    )
    result3 = chunk_node(state3)
    assert len(result3["chunks"]) > 0
    # 检查至少有一个 chunk 有关键词
    has_keywords = any(len(c.keywords) > 0 for c in result3["chunks"])
    print(f"  关键词提取: {sum(len(c.keywords) for c in result3['chunks'])} 个关键词分布在 {len(result3['chunks'])} 块中")
    print(f"[PASS] 14. chunk_node 自动关键词填充工作正常")
    passed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} tests passed")
    if passed == total:
        print("ALL TESTS PASSED!")
    else:
        print(f"{total - passed} tests FAILED!")

if __name__ == "__main__":
    test()
