"""Local MinerU → existing Document IR. No remote service or separate index."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from app.config import settings
from app.observability.tracing import span
from .models import BlockType, DocumentBlock, ParsedDocument, SourceAssetRef, build_block_id


def _text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_text(item) for item in value)
    if isinstance(value, dict):
        return _text(value.get("content", value.get("text", "")))
    return ""


def document_from_middle_json(data: dict, source: SourceAssetRef, *, ocr_mode: str) -> ParsedDocument:
    producer = data.get("metadata", {}).get("producer", {})
    if producer.get("name") != "mineru" or not producer.get("version"):
        raise ValueError("MinerU output has no valid producer identity")
    blocks = []
    kinds = {"paragraph_title": BlockType.TITLE, "title": BlockType.TITLE,
             "code": BlockType.CODE, "formula": BlockType.FORMULA}
    for page in data.get("pages", []):
        page_number = int(page["page_idx"]) + 1
        for raw in page.get("blocks", []):
            text = _text(raw.get("content", raw.get("text", ""))).strip()
            if not text:
                continue
            # Unknown layout types remain honest text blocks; never claim table fidelity.
            kind = kinds.get(raw.get("type"), BlockType.TEXT)
            bbox = raw.get("bbox")
            blocks.append(DocumentBlock(
                block_id=build_block_id(source.document_id, len(blocks) + 1),
                block_type=kind, text=text, page_start=page_number, page_end=page_number,
                bbox=tuple(bbox) if isinstance(bbox, list) and len(bbox) == 4 else None,
                metadata={"mineru_type": raw.get("type", "text"), "level": raw.get("level"),
                          "bbox_units": "normalized", "ocr_mode": ocr_mode},
            ))
    options = json.dumps({"tier": "flash", "ocr_mode": ocr_mode, "image_analysis": False}, sort_keys=True)
    return ParsedDocument(source=source, parser_backend="mineru", parser_version=producer["version"],
                          blocks=blocks, page_count=int(data["metadata"]["document"]["page_count"]),
                          options_hash=hashlib.sha256(options.encode()).hexdigest()[:16])


def parse_pdf(path: Path, source: SourceAssetRef, *, ocr_mode: str = "auto") -> ParsedDocument:
    executable = Path(settings.MINERU_EXECUTABLE)
    if not settings.MINERU_ENABLED or not executable.is_file():
        raise ValueError("MinerU local runtime is unavailable")
    if path.suffix.lower() != ".pdf" or ocr_mode not in {"auto", "txt", "ocr"}:
        raise ValueError("MinerU accepts PDF and auto/txt/ocr modes only")
    if hashlib.sha256(path.read_bytes()).hexdigest() != source.sha256:
        raise ValueError("MinerU source SHA does not match the authorized SourceAsset")
    with span("mineru.parse", attributes={"document.id": source.document_id, "parser.backend": "mineru",
                                         "parser.ocr_mode": ocr_mode}) as trace:
        with tempfile.TemporaryDirectory(prefix="edu-mineru-") as directory:
            output = Path(directory) / "middle.json"
            process = subprocess.run(
                [str(executable), "parse", str(path), "-o", str(output), "--format", "middle_json",
                 "--tier", "flash", "--ocr-mode", ocr_mode, "--disable-image-analysis"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=settings.MINERU_TIMEOUT_S,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
            )
            if process.returncode != 0 or not output.is_file():
                raise ValueError(f"MinerU local parse failed (exit={process.returncode}); check runtime/models")
            if output.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("MinerU output exceeds 32 MiB")
            parsed = document_from_middle_json(json.loads(output.read_text(encoding="utf-8")), source, ocr_mode=ocr_mode)
            if trace is not None:
                trace.set_attributes({"document.pages": parsed.page_count, "document.blocks": len(parsed.blocks)})
                for block in parsed.blocks:
                    block.metadata["trace_id"] = trace.trace_id
                    block.metadata["span_id"] = trace.span_id
            return parsed
