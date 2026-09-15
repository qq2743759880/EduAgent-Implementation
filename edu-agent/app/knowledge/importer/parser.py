"""
解析器 —— 从文件提取结构化数据。

三种解析策略：
1. parse_course_intro：正则提取课程系列（确定性解析）
2. parse_questions：正则提取题目（确定性解析）
3. parse_generic：通用文档走段落切分 + 关键词提取

文件类型检测采用两级策略（readers.detect_file_type）：
1. 文件名弱信号 → 候选
2. 内容结构强校验 → 确认
只有两步都通过才走专用解析路径。

chunk_id：本模块生成的只是「中间态 ID」（内容稳定、文件内唯一，供 chunker 作切分前缀）。
全局唯一 chunk_id（{tenant}:{sha256(canonical)[:16]}:{seq}）由 loader.load_chunks
在入库前按契约 C-R-CHUNK 统一生成（loader 同时掌握 tenant 与 canonical 内容）。
"""
import hashlib
import re
from pathlib import Path

from app.common.logging import logger
from app.knowledge.importer.readers import read_file, detect_file_type
from app.knowledge.models import ContentType, ImportState, KnowledgeChunk


def _local_id(content: str, seq: int) -> str:
    """中间态 chunk_id：内容稳定 + 文件内唯一（chunker 作切分前缀 / loader 会被覆写）。"""
    h = hashlib.sha256((content or "").encode("utf-8")).hexdigest()[:12]
    return f"c{h}_{seq:04d}"


def parse_course_intro(md_text: str, source_file: str) -> list[KnowledgeChunk]:
    """解析课程介绍 → 每个系列一条 chunk。"""
    chunks = []

    blocks = re.split(r'(?m)^##\s+', md_text)[1:]

    for idx, block in enumerate(blocks, start=1):
        lines = block.split('\n')
        series_name = lines[0].strip()

        def extract_field(key: str) -> str | None:
            pattern = rf'^-\s+\*\*{re.escape(key)}\*\*:\s*(.+)$'
            match = re.search(pattern, block, re.MULTILINE)
            return match.group(1).strip() if match else None

        series_code = extract_field('系列编码')
        category = extract_field('课程分类')
        audience = extract_field('适合人群')
        goal = extract_field('学习目标')
        desc = extract_field('描述')

        module_pattern = r'编码:\s*(\S+?),\s*课时:'
        module_codes = re.findall(module_pattern, block)

        content_parts = [
            f"课程系列：{series_name}",
            f"系列编码：{series_code}" if series_code else "",
            f"描述：{desc}" if desc else "",
            f"分类：{category}" if category else "",
            f"适合人群：{audience}" if audience else "",
            f"学习目标：{goal}" if goal else "",
        ]

        if module_codes:
            content_parts.append(f"包含 {len(module_codes)} 个模块")
            content_parts.append("模块编码：" + ", ".join(module_codes[:5]))

        content = "\n".join(p for p in content_parts if p)

        chunk = KnowledgeChunk(
            chunk_id=_local_id(content, idx),
            content=content,
            content_type=ContentType.COURSE_INTRO,
            series_code=series_code,
            series_name=series_name,
            module_codes=module_codes,
            category=category,
            audience=audience,
            goal=goal,
            resource_type="课程介绍",
            tags=[series_name, category] if category else [series_name],
            source_file=source_file,
        )
        chunks.append(chunk)

    logger.info(f"课程解析完成：{len(chunks)} 个系列")
    return chunks


def parse_questions(md_text: str, source_file: str) -> list[KnowledgeChunk]:
    """解析题目资料 → 每道题一条 chunk。"""
    chunks = []

    bank_blocks = re.split(r'(?m)^##\s+', md_text)[1:]

    for bank_block in bank_blocks:
        bank_lines = bank_block.split('\n')
        bank_name = bank_lines[0].strip()

        bank_code_match = re.search(r'^-\s+题库编码:\s*(\S+)', bank_block, re.MULTILINE)
        bank_code = bank_code_match.group(1) if bank_code_match else None

        questions = re.split(r'(?m)^###\s+', bank_block)[1:]

        for q_text in questions:
            q_lines = q_text.split('\n')
            question_code = q_lines[0].strip()

            def extract_q_field(key: str, multiline: bool = False) -> str | None:
                if multiline:
                    pattern = rf'-\s+\*\*{re.escape(key)}\*\*:\s*\n(.*?)(?=\n-\s+\*\*|\Z)'
                    match = re.search(pattern, q_text, re.DOTALL)
                else:
                    pattern = rf'-\s+\*\*{re.escape(key)}\*\*:\s*(.+)'
                    match = re.search(pattern, q_text)
                return match.group(1).strip() if match else None

            qtype = extract_q_field('题型')
            stem = extract_q_field('题干')
            options = extract_q_field('选项', multiline=True)
            answer = extract_q_field('答案')
            analysis = extract_q_field('解析')

            content_parts = [
                f"【{qtype}】" if qtype else "",
                f"题目：{stem}" if stem else "",
                f"选项：\n{options}" if options else "",
                f"答案：{answer}" if answer else "",
                f"解析：{analysis}" if analysis else "",
            ]
            content = "\n".join(p for p in content_parts if p)

            chunk = KnowledgeChunk(
                chunk_id=_local_id(content, len(chunks) + 1),
                content=content,
                content_type=ContentType.QUESTION,
                question_bank_code=bank_code,
                question_bank_name=bank_name,
                question_code=question_code,
                question_type=qtype,
                resource_type="题库",
                tags=[bank_name, qtype] if qtype else [bank_name],
                source_file=source_file,
            )
            chunks.append(chunk)

    logger.info(f"题目解析完成：{len(chunks)} 道题目")
    return chunks


def parse_generic(
    text: str,
    source_file: str,
    metadata: dict | None = None,
) -> list[KnowledgeChunk]:
    """
    通用文档解析 → 按段落切分。

    策略：按空行分段，每段一个 chunk，段数过多时自动合并。
    支持外部传入元数据（tags, difficulty, resource_type 等）。
    """
    chunks = []

    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    meta = metadata or {}
    for idx, para in enumerate(paragraphs, start=1):
        chunk = KnowledgeChunk(
            chunk_id=_local_id(para, idx),
            content=para,
            content_type=ContentType.DOC_CHUNK,
            tags=meta.get("tags", []),
            difficulty=meta.get("difficulty"),
            resource_type=meta.get("resource_type"),
            author=meta.get("author"),
            prerequisites=meta.get("prerequisites", []),
            keywords=meta.get("keywords", []),
            source_file=source_file,
        )
        chunks.append(chunk)

    logger.info(f"通用文档解析完成：{len(chunks)} 个段落")
    return chunks


def parse_node(state: ImportState) -> dict:
    """LangGraph 节点：解析所有源文件。"""
    if state.error:
        logger.warning("跳过 parse（前序节点已出错）")
        return {}

    all_chunks = []

    for file_path_str in state.source_files:
        file_path = Path(file_path_str).resolve()

        if not file_path.exists():
            return {"error": f"文件不存在: {file_path}"}

        try:
            text = read_file(str(file_path))
        except Exception as e:
            return {"error": f"读取文件失败 {file_path.name}: {e}"}

        file_type = detect_file_type(str(file_path), text)
        logger.info(f"开始解析: {file_path.name}（类型: {file_type}）")

        if file_type == "course_intro":
            chunks = parse_course_intro(text, file_path.name)
        elif file_type == "questions":
            chunks = parse_questions(text, file_path.name)
        else:
            chunks = parse_generic(text, file_path.name)

        all_chunks.extend(chunks)

    logger.info(f"解析完成，共 {len(all_chunks)} 条")
    return {"chunks": all_chunks}
