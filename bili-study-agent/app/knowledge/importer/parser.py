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
import asyncio
import hashlib
import re
import threading
from pathlib import Path

from app.common.logging import logger
from app.config import settings
from app.knowledge.importer.readers import read_file, detect_file_type
from app.knowledge.ir import (
    BlockType,
    DocumentBlock,
    IR_SCHEMA_VERSION,
    ParsedDocument,
    SecurityMeta,
    SeedKnowledgeChunk,
    SourceAssetRef,
    build_block_id,
    join_blocks_text,
)
from app.knowledge.models import (
    ASSET_STAGE_IR_READY,
    ASSET_STAGE_QUEUED_PARSER,
    ChunkStrategy,
    ContentType,
    ImportState,
    KnowledgeChunk,
    Visibility,
)


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


# ============================================================
# W2-S4：DOC_IR_ENABLED 分支（legacy_str 合成 IR → Seed → KnowledgeChunk）
# ============================================================

def _resolve_visibility(state: ImportState) -> str | None:
    """安全元数据双读（W2-S4 过渡纪律）：state.visibility（正式字段）→ state.extra["visibility"]。

    S5 收敛 upload.py 走正式字段后，extra 回落分支删除。
    ImportState 是 pydantic 模型且未开 extra="allow"——extra 由 upload.py 经
    ``state.__dict__.setdefault("extra", {})`` hack 注入，故一律 getattr 兜底。
    """
    if state.visibility:
        return state.visibility
    extra = getattr(state, "extra", None) or {}
    v = extra.get("visibility")
    return str(v) if v else None


def _run_async(coro):
    """同步 LangGraph 节点内执行协程（task_store.update_asset_stage 是 async）。

    - 常规路径（upload.py 经 anyio.to_thread 跑管道 / pytest 直调）：当前线程无事件循环
      → asyncio.run 直接跑；
    - 若已处于事件循环线程（防嵌套 run 崩溃）：丢独立线程执行后 join 取结果。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict = {}

    def _runner() -> None:
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 - 原样回传主线程
            box["error"] = exc

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _legacy_parse_fingerprint(content_sha256: str) -> str:
    """legacy_str 后端的解析指纹（与 ir.ParsedDocument.parse_fingerprint 同公式）：

    sha256(sha256 | backend | version | options_hash)[:16]——同输入稳定、异输入必异。
    单独抽函数：过渡期 SourceAssetRef 可能缺省（upload meta 缺 object_key），
    无法构造 ParsedDocument 时仍能按同一契约出指纹。
    """
    material = "\x1f".join([content_sha256, "legacy_str", "v1", "none"])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _segment_markdown_to_blocks(text: str, document_id: str) -> list[DocumentBlock]:
    """legacy str → 合成 Document IR block（W2-04 过渡；真版面解析器 mineru/pdfplumber 属后续批）。

    行扫描规则：
    - ``#`` / ``##`` / ``###`` 开头 → TITLE（层级进 metadata.level）
    - ``` 代码围栏 → CODE（markdown=含围栏原文；语言进 metadata.lang）
    - ``|`` 表格行连续 >=2 → TABLE（markdown=原文，text=去管道符拼单元格）；单行 → TEXT
    - 其余非空行 → TEXT（连续非特殊行归一个段落块，空行即段落边界）
    page 恒 1/1（legacy_str 无页码，IR 契约默认值）。
    """
    blocks: list[DocumentBlock] = []
    seq = 0

    def _mk(block_type: BlockType, t: str, markdown: str | None = None, metadata: dict | None = None) -> None:
        nonlocal seq
        seq += 1
        blocks.append(
            DocumentBlock(
                block_id=build_block_id(document_id, seq),
                block_type=block_type,
                text=t,
                markdown=markdown,
                metadata=metadata or {},
            )
        )

    lines = text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        stripped = lines[i].strip()
        if not stripped:  # 空行 = 段落边界
            i += 1
            continue
        # 代码围栏（含收尾围栏；未闭合则吃到 EOF）
        if stripped.startswith("```"):
            code_lines = [lines[i]]
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                code_lines.append(lines[i])
                i += 1
            code_src = "\n".join(code_lines)
            _mk(BlockType.CODE, code_src, markdown=code_src, metadata={"lang": stripped[3:].strip() or None})
            continue
        # Markdown 标题
        m = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if m:
            _mk(BlockType.TITLE, m.group(2).strip(), metadata={"level": len(m.group(1))})
            i += 1
            continue
        # 表格：| 开头连续 >=2 行归 TABLE；孤立单行降级 TEXT
        if stripped.startswith("|"):
            tbl: list[str] = []
            while i < n and lines[i].strip().startswith("|"):
                tbl.append(lines[i].strip())
                i += 1
            if len(tbl) >= 2:
                cells: list[str] = []
                for row in tbl:
                    for c in row.strip("|").split("|"):
                        c = c.strip()
                        if c and not re.fullmatch(r":?-{2,}:?", c):  # 剥管道符 + 剥分隔行（---）
                            cells.append(c)
                plain = " ".join(cells)
                _mk(BlockType.TABLE, plain or "\n".join(tbl), markdown="\n".join(tbl))
            else:
                _mk(BlockType.TEXT, tbl[0])
            continue
        # TEXT：连续非空、非标题/围栏/表格行归一个段落块
        para: list[str] = []
        while i < n:
            s = lines[i].strip()
            if not s or s.startswith("```") or s.startswith("|") or re.match(r"^#{1,3}\s", s):
                break
            para.append(lines[i])
            i += 1
        if para:
            _mk(BlockType.TEXT, "\n".join(para).strip())
    return blocks


def _blocks_to_seeds(
    blocks: list[DocumentBlock],
    document_id: str,
    visibility: str,
    owner_id: int | None,
    security_scope: str,
    business_metadata: dict | None = None,
    parser_backend: str = "legacy_str",
) -> list[SeedKnowledgeChunk]:
    """seed 组装（F-025）：连续同类型 block 归一个 SeedKnowledgeChunk，跨类型必断。

    text 用 join_blocks_text（逐 block "\\n\\n" 连接 + block_span 无损映射），
    SeedKnowledgeChunk 校验器保证 span 与 text 一致（禁无映射 join）。

    B0-FIX（recovery 契约）：business_metadata 非空时随 seed.metadata 透传
    （来源 ImportState.extra["source_files_meta"][i]["business_metadata"]，结构化
    业务元数据；parser 不解释业务语义，仅透传给 chunk 层做一等字段映射）。
    """
    seeds: list[SeedKnowledgeChunk] = []
    group: list[DocumentBlock] = []

    def _flush() -> None:
        if not group:
            return
        text, span = join_blocks_text(group)
        markdown = None
        if all(b.markdown for b in group):  # 组内均有 markdown 才拼（TABLE seed 用）
            markdown = "\n\n".join(b.markdown for b in group)
        seeds.append(
            SeedKnowledgeChunk(
                seed_id=f"{document_id}:s{len(seeds) + 1:04d}",
                document_id=document_id,
                block_ids=[b.block_id for b in group],
                block_type=group[0].block_type,
                page_start=min(b.page_start for b in group),
                page_end=max(b.page_end for b in group),
                parser_backend=parser_backend,
                text=text,
                markdown=markdown,
                block_span=span,
                security=SecurityMeta(
                    visibility=visibility, owner_id=owner_id, security_scope=security_scope
                ),
                metadata=dict(business_metadata) if business_metadata else {},
            )
        )
        group.clear()

    for b in blocks:
        if group and b.block_type is not group[0].block_type:
            _flush()  # 跨类型必断
        group.append(b)
    _flush()
    return seeds


def _parse_node_ir(state: ImportState) -> dict:
    """DOC_IR_ENABLED=True 分支：read_file（legacy reader 复用）→ 合成 IR → seed → KnowledgeChunk。

    provenance 双写：KnowledgeChunk first-class 字段 + extra（loader 白名单按值透传
    Milvus dynamic field）。安全元数据 fail-closed；asset stage 推进失败仅 WARN 不阻断。
    """
    # ---- 安全元数据（fail-closed）----
    vis = _resolve_visibility(state)
    if state.task_type == "system_init" and not vis:
        # 历史兼容裁定（W2-04）：system_init 是管理员初始化通道，存量初始化数据没有显式
        # visibility 声明；放行为 public。user_upload 无声明仍 fail-closed 直接失败。
        vis = "public"
    if vis not in ("private", "public"):
        return {"error": "security metadata missing (fail-closed)"}

    extra = getattr(state, "extra", None) or {}
    # owner_id / security_scope 与 visibility 同纪律：正式字段优先，extra 兜底双读
    owner_id_raw = state.owner_id if state.owner_id is not None else extra.get("owner_id")
    try:  # extra 兜底值可能是 str/脏数据——坏值降级 None（public 资产合法），不让解析炸掉
        owner_id = int(owner_id_raw) if owner_id_raw is not None else None
    except (TypeError, ValueError):
        owner_id = None
    scope = state.security_scope
    if not scope or scope == "default":
        scope = extra.get("security_scope") or "default"

    metas = extra.get("source_files_meta") or []
    all_chunks: list[KnowledgeChunk] = []
    parsed_documents: list[dict] = []
    artifact_seeds: list[dict] = []

    for fi, file_path_str in enumerate(state.source_files):
        file_path = Path(file_path_str).resolve()
        if not file_path.exists():
            return {"error": f"文件不存在: {file_path}"}
        content_sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
        meta = metas[fi] if fi < len(metas) and isinstance(metas[fi], dict) else None
        # document_id：asset 传入（S5 起 meta 携带）优先；否则从内容 sha 派生稳定短 id
        # （同文件重导 document_id/block_ids/fingerprint 全稳定 = 幂等）
        document_id = (meta or {}).get("document_id") or f"doc{content_sha[:12]}"

        # SourceAssetRef：upload meta 有 object_key 才构造（缺则 None，不阻塞解析）
        asset_ref = None
        if (meta or {}).get("object_key"):
            try:
                asset_ref = SourceAssetRef(
                    bucket=(meta or {}).get("bucket") or "edu-upload",
                    object_key=meta["object_key"],
                    sha256=(meta or {}).get("sha256") or content_sha,
                    document_id=document_id,
                    file_name=(meta or {}).get("file_name") or file_path.name,
                    mime=(meta or {}).get("mime") or (meta or {}).get("content_type") or "text/plain",
                )
            except Exception as exc:  # noqa: BLE001 - 引用构造失败降级，不阻断解析
                logger.warning(f"[parse_node-ir] SourceAssetRef 构造失败（降级）: {exc!r}")
                asset_ref = None

        business_metadata = (meta or {}).get("business_metadata") or {}
        backend = business_metadata.get("parser_backend", "legacy_str")
        parsed_document = None
        try:
            if backend == "mineru":
                if asset_ref is None:
                    raise ValueError("MinerU requires a durable authorized SourceAsset")
                from app.knowledge.ir.mineru import parse_pdf
                parsed_document = parse_pdf(file_path, asset_ref, ocr_mode=business_metadata.get("mineru_ocr_mode", "auto"))
                fingerprint = parsed_document.parse_fingerprint()
                blocks = parsed_document.blocks
            else:
                text = read_file(str(file_path))
                fingerprint = _legacy_parse_fingerprint(content_sha)
                blocks = _segment_markdown_to_blocks(text, document_id)
        except Exception as exc:
            return {"error": f"{backend} 解析失败 {file_path.name}: {type(exc).__name__}: {exc}"}
        if not blocks:
            return {"error": f"空文档解析失败: {file_path.name}"}
        seeds = _blocks_to_seeds(blocks, document_id, vis, owner_id, scope, business_metadata, backend)

        if asset_ref is not None:
            parsed_document = parsed_document or ParsedDocument(
                source=asset_ref,
                parser_backend="legacy_str",
                parser_version="v1",
                ir_schema_version=IR_SCHEMA_VERSION,
                blocks=blocks,
                page_count=max((block.page_end for block in blocks), default=1),
                options_hash="none",
            )
            # 双重实现必须产生同一指纹；若以后版本策略漂移则解析失败，不写错误指纹。
            if parsed_document.parse_fingerprint() != fingerprint:
                return {"error": "legacy IR fingerprint 与冻结指纹算法不一致"}
            parsed_documents.append(parsed_document.model_dump(mode="json"))
            artifact_seeds.extend(seed.model_dump(mode="json") for seed in seeds)

        provenance_common: dict = {
            "parser_backend": backend,
            "parse_fingerprint": fingerprint,
            "document_id": document_id,
            "security_scope": scope,
        }
        if owner_id is not None:
            provenance_common["owner_id"] = owner_id
        if asset_ref is not None:
            provenance_common["asset_ref"] = asset_ref.model_dump()

        for seq_i, seed in enumerate(seeds, start=1):
            chunk = KnowledgeChunk(
                chunk_id=_local_id(seed.text, seq_i),  # 过渡值；loader canonical_id 在 load 时仍为准
                content=seed.text,
                content_type=ContentType.DOC_CHUNK,
                visibility=Visibility(vis),
                tags=list(extra.get("tags") or []),
                difficulty=extra.get("difficulty"),
                resource_type=extra.get("resource_type"),
                author=extra.get("author"),
                keywords=list(extra.get("keywords") or []),
                source_file=file_path.name,
                chunk_strategy=ChunkStrategy.SEMANTIC_WINDOW,
                # ---- provenance first-class 字段 ----
                block_ids=list(seed.block_ids),
                block_type=seed.block_type.value,
                page_start=seed.page_start,
                page_end=seed.page_end,
                parser_backend=seed.parser_backend,
                parse_fingerprint=fingerprint,
                extra={
                    # ---- provenance extra（loader 白名单读取源之一）----
                    "block_ids": ",".join(seed.block_ids),
                    "block_type": seed.block_type.value,
                    "page_start": seed.page_start,
                    "page_end": seed.page_end,
                    **provenance_common,
                    # seed 级无损映射（answer/审计侧可复原 per-block 视图）
                    "block_span": [[b, s, e] for (b, s, e) in seed.block_span],
                },
            )
            all_chunks.append(chunk)

        logger.info(
            f"[parse_node-ir] {file_path.name}: {len(blocks)} blocks → {len(seeds)} seeds"
            f"（doc={document_id}, backend={backend}）"
        )

    # ---- asset stage 推进（queued_parser → ir_ready，CAS；失败 WARN 不阻断）----
    for aid in extra.get("source_asset_ids") or []:
        try:
            # 惰性导入：parser 模块不强依赖 DB 双写层（无 source_asset_ids 的纯解析场景零触发）
            from app.knowledge import task_store as _ts

            n = _run_async(
                _ts.update_asset_stage(
                    str(aid), ASSET_STAGE_IR_READY, expected_stage=ASSET_STAGE_QUEUED_PARSER
                )
            )
            if not n:
                logger.warning(f"[parse_node-ir] asset stage CAS 落败（expected≠queued_parser）: {aid}")
            else:
                logger.info(f"[parse_node-ir] asset stage queued_parser → ir_ready: {aid}")
        except Exception as exc:  # noqa: BLE001 - 不阻断解析主流程
            logger.warning(f"[parse_node-ir] asset stage 推进失败（不阻断）: {aid} -> {exc!r}")

    logger.info(f"[parse_node-ir] 解析完成，共 {len(all_chunks)} 条 seed chunk")
    return {"chunks": all_chunks, "parsed_documents": parsed_documents, "seeds": artifact_seeds}


def parse_node(state: ImportState) -> dict:
    """LangGraph 节点：解析所有源文件。"""
    if state.error:
        logger.warning("跳过 parse（前序节点已出错）")
        return {}

    # W2-S4：DOC_IR_ENABLED 总开关——ON 走合成 IR 路径（seed 级 provenance 全链路传播）；
    # OFF（默认）走下方既有 str 路径逐位不变（回滚 = 单关本 flag，无 DDL、无数据回填）。
    if getattr(settings, "DOC_IR_ENABLED", False):
        return _parse_node_ir(state)

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
