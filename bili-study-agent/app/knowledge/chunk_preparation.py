"""Pure W4 preparation of IR seeds into provenance-preserving knowledge chunks.

This module deliberately has no model, database, vector-store, or network calls.
The authoritative tenant is passed by the caller; it is never inferred from a
parser payload or silently defaulted here.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Callable

from app.knowledge.ir import BlockType, DocumentBlock, ParsedDocument, SeedKnowledgeChunk
from app.knowledge.models import (
    ChunkStrategy,
    ContentType,
    KnowledgeChunk,
    Visibility,
)


@dataclass(frozen=True)
class ChunkPreparationPolicy:
    """Token-first budget with a bounded character fallback."""

    token_budget: int = 512
    fallback_target_chars: int = 800
    fallback_char_budget: int = 1200

    def __post_init__(self) -> None:
        if self.token_budget < 1:
            raise ValueError("token_budget must be positive")
        if self.fallback_target_chars < 1:
            raise ValueError("fallback_target_chars must be positive")
        if self.fallback_char_budget < self.fallback_target_chars:
            raise ValueError("fallback_char_budget must be >= fallback_target_chars")


_PARAGRAPH_END = re.compile(r"\n\s*\n+")
_SENTENCE_END = re.compile(r"(?<=[。！？.!?；;])(?:[”’\"'）)\]]?)(?=\s|$)")
_LINE_END = re.compile(r"\n+")
_TABLE_SEPARATOR_CELL = re.compile(r":?-{3,}:?")

TokenEstimator = Callable[[str], int]


def _load_token_estimator() -> TokenEstimator | None:
    """Lazily reuse the existing pure chunker estimator when its import works."""
    try:
        from app.knowledge.importer.chunker import _estimate_tokens
    except ImportError:
        return None
    return _estimate_tokens


def _token_count(text: str, estimator: TokenEstimator | None) -> int:
    # Character count is the explicit fallback, not a claim of true tokenization.
    count = len(text) if estimator is None else int(estimator(text))
    if count < 0:
        raise ValueError("token estimator returned a negative count")
    return count


def _largest_end_within_budget(
    text: str,
    start: int,
    *,
    budget: int,
    char_limit: int,
    estimator: TokenEstimator | None,
) -> int:
    """Find the longest end offset under budget using monotone binary search."""
    high = min(len(text), start + char_limit)
    low = start
    while low < high:
        mid = (low + high + 1) // 2
        if _token_count(text[start:mid], estimator) <= budget:
            low = mid
        else:
            high = mid - 1
    if low == start and start < len(text):
        # A single code point may itself exceed a custom estimator's budget.
        return start + 1
    return low


def _stable_chunk_id(seed_id: str, ordinal: int, content: str) -> str:
    material = f"{seed_id}\x1f{ordinal}\x1f{content}".encode("utf-8")
    return "w4_" + hashlib.sha256(material).hexdigest()[:24]


def _candidate_boundaries(text: str, seed: SeedKnowledgeChunk) -> list[tuple[int, int]]:
    """Return (position, priority), with block boundaries preferred."""
    found: dict[int, int] = {}
    for block_id, _start, end in seed.block_span:
        found[end] = max(found.get(end, 0), 3)
    for match in _PARAGRAPH_END.finditer(text):
        found[match.end()] = max(found.get(match.end(), 0), 2)
    pattern = _SENTENCE_END if seed.block_type is not BlockType.CODE else _LINE_END
    for match in pattern.finditer(text):
        found[match.end()] = max(found.get(match.end(), 0), 1)
    return sorted(found.items())


def _next_cut(
    text: str,
    start: int,
    seed: SeedKnowledgeChunk,
    policy: ChunkPreparationPolicy,
    boundaries: list[tuple[int, int]],
    estimator: TokenEstimator | None,
) -> int:
    if estimator is None:
        hard_limit = min(start + policy.fallback_char_budget, len(text))
        target = min(start + policy.fallback_target_chars, hard_limit)
        lower = start + min(200, max(1, policy.fallback_target_chars // 2))
    else:
        hard_limit = _largest_end_within_budget(
            text,
            start,
            budget=policy.token_budget,
            char_limit=len(text) - start,
            estimator=estimator,
        )
        target = hard_limit
        # Avoid tiny chunks where possible while keeping the configured token
        # budget as the hard limit.
        lower = _largest_end_within_budget(
            text,
            start,
            budget=max(1, int(policy.token_budget * 0.55)),
            char_limit=len(text) - start,
            estimator=estimator,
        )
    if hard_limit <= start:
        return min(start + 1, len(text))

    eligible = [(pos, priority) for pos, priority in boundaries if lower <= pos <= target]
    if eligible:
        return max(eligible, key=lambda item: (item[0], item[1]))[0]

    # If no natural boundary is in the preferred range, use the furthest one
    # that still respects the active size budget.
    within_budget = [(pos, priority) for pos, priority in boundaries if start < pos <= hard_limit]
    if within_budget:
        return max(within_budget, key=lambda item: (item[0], item[1]))[0]

    # Last resort: whitespace within the active size budget, then a Unicode
    # code-point boundary to guarantee progress on unbroken text.
    whitespace = [m.end() for m in re.finditer(r"\s+", text[start:hard_limit])]
    if whitespace:
        return start + whitespace[-1]
    return hard_limit


def _ranges(
    seed: SeedKnowledgeChunk,
    policy: ChunkPreparationPolicy,
    estimator: TokenEstimator | None,
) -> list[tuple[int, int]]:
    text = seed.text
    if not text.strip():
        raise ValueError(f"seed {seed.seed_id!r} has no chunkable text")

    # Formula blocks are structural atoms. Markdown tables are handled by a
    # row-aware policy below, never by splitting this flattened seed text.
    if seed.block_type is BlockType.FORMULA:
        return [(0, len(text))]

    within_initial_budget = (
        _token_count(text, estimator) <= policy.token_budget
        if estimator is not None
        else len(text) <= policy.fallback_target_chars
    )
    if within_initial_budget:
        left = len(text) - len(text.lstrip())
        right = len(text.rstrip())
        return [(left, right)]

    boundaries = _candidate_boundaries(text, seed)
    result: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(text):
        start = cursor
        while start < len(text) and text[start].isspace():
            start += 1
        if start >= len(text):
            break
        cut = _next_cut(text, start, seed, policy, boundaries, estimator)
        if cut <= start:
            cut = min(start + (policy.fallback_char_budget if estimator is None else 1), len(text))
        end = cut
        while end > start and text[end - 1].isspace():
            end -= 1
        if end <= start:
            # Whitespace-only region: move forward without producing a chunk.
            cursor = max(cut, start + 1)
            continue
        result.append((start, end))
        cursor = max(cut, end)

    if not result:
        raise ValueError(f"seed {seed.seed_id!r} produced no chunks")
    return result


def _validate_seed(parsed: ParsedDocument, seed: SeedKnowledgeChunk) -> dict[str, DocumentBlock]:
    if seed.document_id != parsed.source.document_id:
        raise ValueError(f"seed {seed.seed_id!r} belongs to another document")
    blocks: dict[str, DocumentBlock] = {block.block_id: block for block in parsed.blocks}
    unknown = set(seed.block_ids) - blocks.keys()
    if unknown:
        raise ValueError(f"seed {seed.seed_id!r} references unknown blocks: {sorted(unknown)}")
    if len(seed.block_span) != len(seed.block_ids):
        raise ValueError(f"seed {seed.seed_id!r} block_span does not cover each source block")

    span_ids = [block_id for block_id, _, _ in seed.block_span]
    if span_ids != seed.block_ids:
        raise ValueError(f"seed {seed.seed_id!r} block_span order differs from block_ids")
    for block_id, start, end in seed.block_span:
        block = blocks[block_id]
        if end > len(seed.text) or start < 0 or end < start:
            raise ValueError(f"seed {seed.seed_id!r} has an invalid span for {block_id!r}")
        if block.block_type is not seed.block_type:
            raise ValueError(f"seed {seed.seed_id!r} combines different block types")
        if seed.text[start:end] != block.text:
            raise ValueError(f"seed {seed.seed_id!r} span does not match block {block_id!r}")
    return blocks


def _make_chunk(
    parsed: ParsedDocument,
    seed: SeedKnowledgeChunk,
    blocks: dict[str, DocumentBlock],
    *,
    tenant_id: str,
    ordinal: int,
    start: int,
    end: int,
    estimator: TokenEstimator | None,
    content_override: str | None = None,
    mapped_override: list[tuple[str, int, int]] | None = None,
    source_range: tuple[int, int] | None = None,
    extra_override: dict[str, object] | None = None,
) -> KnowledgeChunk:
    content = content_override if content_override is not None else seed.text[start:end]
    mapped: list[tuple[str, int, int]] = list(mapped_override or [])
    if mapped_override is None:
        for block_id, span_start, span_end in seed.block_span:
            overlap_start = max(start, span_start)
            overlap_end = min(end, span_end)
            if overlap_start < overlap_end:
                mapped.append((block_id, overlap_start - start, overlap_end - start))
    if not mapped:
        raise ValueError(f"chunk from seed {seed.seed_id!r} has no source block mapping")

    source_blocks = [blocks[block_id] for block_id, _, _ in mapped]
    page_start = min(block.page_start for block in source_blocks)
    page_end = max(block.page_end for block in source_blocks)
    fingerprint = parsed.parse_fingerprint()
    extra: dict[str, object] = {
        "document_id": seed.document_id,
        "seed_id": seed.seed_id,
        "source_sha256": parsed.source.sha256,
        "source_bucket": parsed.source.bucket,
        "source_object_key": parsed.source.object_key,
        "security_scope": seed.security.security_scope,
        "block_span": [[block_id, local_start, local_end] for block_id, local_start, local_end in mapped],
        "chunk_size_unit": "token" if estimator is not None else "character_fallback",
    }
    if estimator is None:
        extra["estimated_chars"] = len(content)
    else:
        extra["estimated_tokens"] = _token_count(content, estimator)
    if source_range is not None:
        extra["source_range"] = list(source_range)
    if seed.security.owner_id is not None:
        extra["owner_id"] = seed.security.owner_id
    if seed.table_id is not None:
        extra["table_id"] = seed.table_id
    if seed.caption is not None:
        extra["caption"] = seed.caption
    if seed.metadata:
        extra["seed_metadata"] = dict(seed.metadata)
        # A signed published native video already contains its lesson/time context.
        # Preserve exact signed teaching text through the existing contextualizer.
        from app.knowledge.video_metadata import is_trusted_public_video
        proof_row = {**seed.metadata, "tenant_id": tenant_id,
            "visibility": seed.security.visibility, "owner_id": seed.security.owner_id,
            "security_scope": seed.security.security_scope, "source_file": parsed.source.file_name,
            "document_id": seed.document_id, "parse_fingerprint": fingerprint,
            "parser_backend": seed.parser_backend, "content_type": "doc_chunk",
            "series_codes": ",".join(seed.metadata.get("series_codes") or []),
            "module_codes": ",".join(seed.metadata.get("module_codes") or []), "context_prefix": "",
            "content": content, "raw_content": content}
        if is_trusted_public_video(proof_row):
            extra["contextualization_skipped"] = True
            extra["internal"] = False
    if extra_override:
        extra.update(extra_override)

    # B0-FIX（recovery 契约）：seed.metadata 白名单业务键 → KnowledgeChunk 一等字段
    # （loader 既有映射写 Milvus；retriever post-filter 读 chunk.series_code）。
    # 未命中白名单的键仍整体留在 extra["seed_metadata"]（上方既有行为，零丢失）。
    bm = seed.metadata if isinstance(seed.metadata, dict) else {}
    bm_module_codes = bm.get("module_codes")
    if isinstance(bm_module_codes, str):
        bm_module_codes = [s.strip() for s in bm_module_codes.split(",") if s.strip()]
    bm_series_codes = bm.get("series_codes")
    if isinstance(bm_series_codes, str):
        bm_series_codes = [s.strip() for s in bm_series_codes.split(",") if s.strip()]

    return KnowledgeChunk(
        chunk_id=_stable_chunk_id(seed.seed_id, ordinal, content),
        content=content,
        raw_content=content,
        content_type=ContentType.DOC_CHUNK,
        tenant_id=tenant_id,
        visibility=Visibility(seed.security.visibility),
        owner_id=seed.security.owner_id,
        source_file=parsed.source.file_name,
        chunk_strategy=ChunkStrategy.SEMANTIC_WINDOW,
        block_ids=[block_id for block_id, _, _ in mapped],
        block_type=seed.block_type.value,
        page_start=page_start,
        page_end=page_end,
        parser_backend=seed.parser_backend,
        parse_fingerprint=fingerprint,
        series_code=bm.get("series_code"),
        series_name=bm.get("series_name"),
        series_codes=bm_series_codes or [],
        module_codes=bm_module_codes or [],
        category=bm.get("category"),
        audience=bm.get("audience"),
        goal=bm.get("goal"),
        question_bank_code=bm.get("question_bank_code"),
        question_bank_name=bm.get("question_bank_name"),
        question_code=bm.get("question_code"),
        question_type=bm.get("question_type"),
        extra=extra,
    )


def _markdown_cells(line: str) -> list[str]:
    """Split a pipe row while treating backslash-escaped pipes as cell text."""
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    text = line.strip()
    for index, char in enumerate(text):
        if char == "|" and not escaped:
            # Markdown permits optional leading/trailing pipes.
            if index == 0 or index == len(text) - 1:
                continue
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        if char == "\\" and not escaped:
            escaped = True
        else:
            escaped = False
    cells.append("".join(current).strip())
    return cells


def _has_unescaped_pipe(line: str) -> bool:
    escaped = False
    for char in line:
        if char == "|" and not escaped:
            return True
        if char == "\\" and not escaped:
            escaped = True
        else:
            escaped = False
    return False


def _parse_markdown_table(markdown: str) -> tuple[str, str, list[str]] | None:
    """Return original header, separator, and rows for a strict pipe table."""
    lines = markdown.splitlines()
    nonempty = [index for index, line in enumerate(lines) if line.strip()]
    if len(nonempty) < 2:
        return None
    first = nonempty[0]
    second = nonempty[1]
    # Do not silently drop leading text: it may be meaningful content rather
    # than a table caption, which is carried separately in IR metadata.
    if second != first + 1:
        return None
    header = lines[first]
    separator = lines[second]
    if not _has_unescaped_pipe(header) or not _has_unescaped_pipe(separator):
        return None
    header_cells = _markdown_cells(header)
    separator_cells = _markdown_cells(separator)
    if not header_cells or len(header_cells) != len(separator_cells):
        return None
    if not all(_TABLE_SEPARATOR_CELL.fullmatch(cell.replace(" ", "")) for cell in separator_cells):
        return None

    rows: list[str] = []
    started = False
    for line in lines[second + 1 :]:
        if not line.strip():
            if started:
                # A blank line ends the table; only trailing blanks are valid.
                continue
            continue
        cells = _markdown_cells(line)
        if len(cells) != len(header_cells):
            return None
        rows.append(line)
        started = True
    return header, separator, rows


def _render_table_chunk(caption: str | None, header: str, separator: str, rows: list[str]) -> str:
    lines: list[str] = []
    if caption:
        lines.append(caption.strip())
    lines.extend((header, separator, *rows))
    return "\n".join(lines)


def _prepare_table_seed(
    parsed: ParsedDocument,
    seed: SeedKnowledgeChunk,
    blocks: dict[str, DocumentBlock],
    *,
    tenant_id: str,
    policy: ChunkPreparationPolicy,
    estimator: TokenEstimator | None,
    first_ordinal: int,
) -> list[KnowledgeChunk]:
    output: list[KnowledgeChunk] = []
    ordinal = first_ordinal
    for block_id, span_start, span_end in seed.block_span:
        block = blocks[block_id]
        markdown = block.markdown or block.text
        caption = seed.caption or block.caption
        table = _parse_markdown_table(markdown)
        block_mapping = [(block_id, 0, 0)]  # replaced after rendered content is known

        if table is None:
            content = f"{caption.strip()}\n\n{markdown}" if caption else markdown
            block_mapping = [(block_id, 0, len(content))]
            output.append(
                _make_chunk(
                    parsed,
                    seed,
                    blocks,
                    tenant_id=tenant_id,
                    ordinal=ordinal,
                    start=span_start,
                    end=span_end,
                    estimator=estimator,
                    content_override=content,
                    mapped_override=block_mapping,
                    extra_override={
                        "table_id": seed.table_id or block.table_id,
                        "caption": caption,
                        "table_split": False,
                        "contextualization_skipped": True,
                    },
                )
            )
            ordinal += 1
            continue

        header, separator, rows = table
        if not rows:
            rows = []
        row_groups: list[tuple[int, int, list[str]]] = []
        current: list[str] = []
        row_base = 1
        for index, row in enumerate(rows, start=1):
            candidate = current + [row]
            rendered = _render_table_chunk(caption, header, separator, candidate)
            within_budget = (
                _token_count(rendered, estimator) <= policy.token_budget
                if estimator is not None
                else len(rendered) <= policy.fallback_char_budget
            )
            if current and not within_budget:
                row_groups.append((row_base, index - 1, current))
                current = [row]
                row_base = index
            else:
                current = candidate
        if current:
            row_groups.append((row_base, len(rows), current))
        if not row_groups:
            # A structurally valid header-only table still produces one chunk.
            row_groups.append((0, 0, []))

        for group_index, (row_start, row_end, group_rows) in enumerate(row_groups, start=1):
            content = _render_table_chunk(caption, header, separator, group_rows)
            oversized = (
                _token_count(content, estimator) > policy.token_budget
                if estimator is not None
                else len(content) > policy.fallback_char_budget
            )
            block_mapping = [(block_id, 0, len(content))]
            output.append(
                _make_chunk(
                    parsed,
                    seed,
                    blocks,
                    tenant_id=tenant_id,
                    ordinal=ordinal,
                    start=span_start,
                    end=span_end,
                    estimator=estimator,
                    content_override=content,
                    mapped_override=block_mapping,
                    extra_override={
                        "table_id": seed.table_id or block.table_id,
                        "caption": caption,
                        "table_split": True,
                        "table_row_range": [row_start, row_end],
                        "table_header_repeated": group_index > 1,
                        "contextualization_skipped": True,
                        "chunk_size_exceeded": oversized,
                    },
                )
            )
            ordinal += 1
    return output


def prepare_chunks(
    parsed: ParsedDocument,
    seeds: list[SeedKnowledgeChunk],
    *,
    tenant_id: str,
    policy: ChunkPreparationPolicy | None = None,
    token_estimator: TokenEstimator | None = None,
) -> list[KnowledgeChunk]:
    """Convert authoritative IR seeds to token-budgeted, provenance-rich chunks.

    The default estimator lazily reuses ``importer.chunker._estimate_tokens``.
    If that estimator cannot be imported, the explicit character fallback is
    used and marked on each output. A deterministic estimator can be injected
    by callers/tests. Formula seeds remain atomic; tables split only at valid
    Markdown row boundaries with caption/header/separator repeated per chunk.
    """
    tenant = tenant_id.strip()
    if not tenant:
        raise ValueError("tenant_id is required from the authoritative task")
    if not seeds:
        raise ValueError("IR v1 preparation requires at least one seed")
    sizing = policy or ChunkPreparationPolicy()
    estimator = token_estimator if token_estimator is not None else _load_token_estimator()

    result: list[KnowledgeChunk] = []
    for seed in seeds:
        block_map = _validate_seed(parsed, seed)
        if seed.block_type is BlockType.TABLE:
            result.extend(
                _prepare_table_seed(
                    parsed,
                    seed,
                    block_map,
                    tenant_id=tenant,
                    policy=sizing,
                    estimator=estimator,
                    first_ordinal=1,
                )
            )
            continue
        for ordinal, (start, end) in enumerate(_ranges(seed, sizing, estimator), start=1):
            result.append(
                _make_chunk(
                    parsed,
                    seed,
                    block_map,
                    tenant_id=tenant,
                    ordinal=ordinal,
                    start=start,
                    end=end,
                    estimator=estimator,
                    source_range=(start, end),
                )
            )
    return result


def should_contextualize_chunk(chunk: KnowledgeChunk) -> bool:
    """Skip TABLE by the independent block_type axis, never ContentType."""
    if chunk.block_type == BlockType.TABLE.value:
        return False
    return bool((chunk.content or "").strip())


def contextualization_document_context(
    parsed: ParsedDocument,
    chunk: KnowledgeChunk,
    *,
    max_chars: int = 1200,
) -> str:
    """Pure, bounded context source for a later contextualizer/LLM caller."""
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    if chunk.extra.get("document_id") != parsed.source.document_id:
        raise ValueError("chunk and parsed document identities differ")

    block_index = {block.block_id: index for index, block in enumerate(parsed.blocks)}
    chunk_ids = chunk.block_ids
    if not chunk_ids or any(block_id not in block_index for block_id in chunk_ids):
        raise ValueError("chunk has missing or foreign source block provenance")
    first = min(block_index[block_id] for block_id in chunk_ids)
    last = max(block_index[block_id] for block_id in chunk_ids)

    # Prefer the nearest preceding title, then nearby source blocks. The output
    # is bounded and contains no generated or inferred facts.
    title = next(
        (b.text.strip() for b in reversed(parsed.blocks[: first + 1]) if b.block_type is BlockType.TITLE and b.text.strip()),
        "",
    )
    nearby = [b.text.strip() for b in parsed.blocks[max(0, first - 1) : min(len(parsed.blocks), last + 2)] if b.text.strip()]
    pieces = ([f"文档标题：{title}"] if title else []) + nearby
    context = "\n\n".join(pieces)
    return context[:max_chars]


__all__ = [
    "ChunkPreparationPolicy",
    "prepare_chunks",
    "contextualization_document_context",
    "should_contextualize_chunk",
]
