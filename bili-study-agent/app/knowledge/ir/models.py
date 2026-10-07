# -*- coding: utf-8 -*-
"""Document IR 数据模型（W2-S3 契约冻结；PRD v2 §6.2 + v2.1 §6.2 F-025）。

硬规则（与 PRD 逐条对应）：
1. BlockType 独立轴：TEXT/TITLE/TABLE/IMAGE/FORMULA/CODE——禁止混入 ContentType（业务轴）。
2. DocumentBlock：text（纯文本视图）/ markdown / html（后两者可选，TABLE 必有 markdown）；
   page_start/page_end（legacy 无页码 = 1/1）；bbox 4 元组或 None；
   table_id/caption（TABLE 专用）；ocr_confidence ∈ [0,1] 可 None；metadata 扩展位。
3. ParsedDocument：blocks 非空；parse_fingerprint = sha256(sha256|backend|version|options_hash)[:16]，
   同输入同 hash / 异 options_hash 异 hash。
4. SeedKnowledgeChunk（F-025）：单 block 或同类型 block 组 → 一个 seed，禁止跨类型合并；
   text 逐 block 以 "\n\n" 连接 + block_span 无损映射（禁无映射 join）；
   security 必填（SecurityMeta 无默认）= fail-closed。
纯 pydantic v2 + stdlib；零 Redis/MinIO/Milvus I/O；import 即安全。
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

#: IR schema 版本（契约冻结；跨版本迁移走 ADR，与 job_stream v1 同纪律）。
IR_SCHEMA_VERSION = "v1"

#: block_id 命名约定："{document_id}:b{seq}"。
BLOCK_ID_FMT = "{document_id}:b{seq}"


def build_block_id(document_id: str, seq: int) -> str:
    """block_id 工厂（冻结命名，消费方按前缀反查 document_id）。"""
    return BLOCK_ID_FMT.format(document_id=document_id, seq=seq)


class BlockType(str, Enum):
    """版面块类型（结构轴；与 ContentType 业务轴正交）。"""

    TEXT = "text"          # 正文段落
    TITLE = "title"        # 标题（层级进 metadata，如 {"level": 2}）
    TABLE = "table"        # 表格（markdown 必填；table_id/caption 生效）
    IMAGE = "image"        # 图片（text 为 OCR/alt 视图；ocr_confidence 生效）
    FORMULA = "formula"    # 公式（markdown 侧 LaTeX；原子不切是 W4 的事）
    CODE = "code"          # 代码块（语言进 metadata）


class SecurityMeta(BaseModel):
    """安全元数据（first-class；fail-closed：visibility 必填、缺失即失败、无 public 默认）。"""

    visibility: str = Field(description="可见性 private/public（必填 = fail-closed）")
    owner_id: Optional[int] = Field(None, description="属主用户 ID；public 资产可为 None")
    security_scope: str = Field(default="default", description="安全域 scope（多租户扩展位）")

    @field_validator("visibility")
    @classmethod
    def _visibility_known(cls, v: str) -> str:
        if v not in ("private", "public"):
            raise ValueError(f"visibility 必须是 private/public，实际 {v!r}")
        return v


class SourceAssetRef(BaseModel):
    """源资产引用（MinIO 定位 + sha256 指纹；只读引用，不触达存储）。"""

    bucket: str = Field(description="MinIO bucket 名（如 edu-upload）")
    object_key: str = Field(description="MinIO 对象键")
    sha256: str = Field(description="源文件内容 sha256（64 位 hex）")
    document_id: str = Field(description="文档 ID（block_id/chunk 命名空间根）")
    file_name: str = Field(description="原始文件名")
    mime: str = Field(description="MIME 类型（parser 路由输入）")

    @field_validator("sha256")
    @classmethod
    def _sha256_shape(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) != 64 or any(c not in "0123456789abcdef" for c in v):
            raise ValueError(f"sha256 必须是 64 位 hex，实际 {v!r}")
        return v


class DocumentBlock(BaseModel):
    """版面块：Document IR 最小结构单元。"""

    block_id: str = Field(description=f"块 ID（命名约定 {BLOCK_ID_FMT}）")
    block_type: BlockType = Field(description="版面块类型（结构轴）")
    text: str = Field(default="", description="纯文本视图（IMAGE 可为空串）")
    markdown: Optional[str] = Field(None, description="Markdown 视图（TABLE 必有）")
    html: Optional[str] = Field(None, description="HTML 视图（可 None）")
    page_start: int = Field(default=1, ge=1, description="起始页（legacy 无页码 =1）")
    page_end: int = Field(default=1, ge=1, description="结束页（legacy 无页码 =1）")
    bbox: Optional[tuple[float, float, float, float]] = Field(None, description="(x0,y0,x1,y1) 或 None")
    table_id: Optional[str] = Field(None, description="表格 ID（TABLE 专用）")
    caption: Optional[str] = Field(None, description="题注（TABLE/IMAGE 专用）")
    ocr_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="OCR 置信度或 None")
    metadata: dict[str, Any] = Field(default_factory=dict, description="扩展位")

    @model_validator(mode="after")
    def _table_needs_markdown(self) -> "DocumentBlock":
        if self.block_type is BlockType.TABLE and not (self.markdown and self.markdown.strip()):
            raise ValueError(f"TABLE 块 {self.block_id!r} 必须携带 markdown（结构保真硬约束）")
        if self.page_end < self.page_start:
            raise ValueError(f"块 {self.block_id!r} page_end({self.page_end}) < page_start({self.page_start})")
        return self


class ParsedDocument(BaseModel):
    """parser 产出契约（blocks 非空）。"""

    source: SourceAssetRef = Field(description="源资产引用（指纹根）")
    parser_backend: str = Field(description="解析后端名（mineru / pdfplumber_fallback / legacy_str）")
    parser_version: str = Field(description="解析后端版本（fingerprint 输入）")
    ir_schema_version: str = Field(default=IR_SCHEMA_VERSION, description="IR schema 版本（恒 v1）")
    blocks: list[DocumentBlock] = Field(description="块列表（非空）")
    page_count: int = Field(ge=1, description="总页数（legacy 单文本 =1）")
    options_hash: str = Field(default="none", description="解析参数指纹（缺省 none）")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("blocks")
    @classmethod
    def _blocks_nonempty(cls, v: list[DocumentBlock]) -> list[DocumentBlock]:
        if not v:
            raise ValueError("blocks 不得为空：空文档解析必须走失败语义，不产空 IR")
        return v

    def parse_fingerprint(self, options_hash: Optional[str] = None) -> str:
        """sha256(sha256 | backend | version | options_hash)[:16]；同输入同 hash。"""
        oh = options_hash if options_hash is not None else self.options_hash
        material = "\x1f".join([self.source.sha256, self.parser_backend, self.parser_version, oh])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


class SeedKnowledgeChunk(BaseModel):
    """IR→chunk 传递单元（F-025）：单 block 或同类型 block 组 → 一个 seed。"""

    seed_id: str = Field(description="seed 唯一 ID")
    document_id: str = Field(description="所属文档 ID（= block_id 前缀）")
    block_ids: list[str] = Field(min_length=1, description="来源 block 列表（同类型，禁跨类型）")
    block_type: BlockType = Field(description="本 seed 块类型（= 组内所有 block 类型）")
    page_start: int = Field(ge=1, description="组内最小 page_start")
    page_end: int = Field(ge=1, description="组内最大 page_end")
    parser_backend: str = Field(description="来源后端透传")
    table_id: Optional[str] = Field(None, description="TABLE seed 专用")
    caption: Optional[str] = Field(None, description="题注（TABLE/IMAGE）")
    text: str = Field(description='纯文本拼接视图（逐 block 以 "\\n\\n" 连接）')
    markdown: Optional[str] = Field(None, description="markdown 拼接视图（组内均有才有）")
    block_span: list[tuple[str, int, int]] = Field(description="[(block_id, start, end)] 无损映射（禁无映射 join）")
    security: SecurityMeta = Field(description="安全元数据（必填 = fail-closed）")
    metadata: dict[str, Any] = Field(default_factory=dict, description="扩展位")

    @model_validator(mode="after")
    def _spans_cover_text(self) -> "SeedKnowledgeChunk":
        expected = "\n\n".join(self.text[s:e] for _, s, e in self.block_span)
        if expected != self.text:
            raise ValueError("block_span 与 text 不一致（禁止无映射 join）")
        return self


class IRArtifact(BaseModel):
    """Parser→Ingest 唯一 v1 wire contract（身份、IR 与带权限 seed 一起校验）。"""

    artifact_type: str = Field(default="ir_v1")
    ir_schema_version: str = Field(default=IR_SCHEMA_VERSION)
    task_id: str
    asset_id: str
    document_id: str
    parsed: ParsedDocument
    seeds: list[SeedKnowledgeChunk] = Field(default_factory=list)

    @model_validator(mode="after")
    def _identity_matches_payload(self) -> "IRArtifact":
        if self.artifact_type != "ir_v1":
            raise ValueError(f"artifact_type 必须是 ir_v1，实际 {self.artifact_type!r}")
        if self.ir_schema_version != IR_SCHEMA_VERSION:
            raise ValueError(f"ir_schema_version 必须是 {IR_SCHEMA_VERSION}，实际 {self.ir_schema_version!r}")
        if self.parsed.ir_schema_version != self.ir_schema_version:
            raise ValueError("artifact 与 ParsedDocument 的 IR schema version 不一致")
        if self.parsed.source.document_id != self.document_id:
            raise ValueError("artifact document_id 与 source.document_id 不一致")
        block_ids = {block.block_id for block in self.parsed.blocks}
        for seed in self.seeds:
            if seed.document_id != self.document_id:
                raise ValueError("seed document_id 与 artifact 不一致")
            if not set(seed.block_ids).issubset(block_ids):
                raise ValueError(f"seed 引用了不属于当前 ParsedDocument 的 block: {seed.seed_id}")
        return self


def join_blocks_text(blocks: list["DocumentBlock"]) -> tuple[str, list[tuple[str, int, int]]]:
    """同类型 block → (text, block_span) 的唯一合法工具（W2-S4 seed 工厂消费）。"""
    parts: list[str] = []
    spans: list[tuple[str, int, int]] = []
    cursor = 0
    for b in blocks:
        if parts:
            parts.append("\n\n")
            cursor += 2
        parts.append(b.text)
        spans.append((b.block_id, cursor, cursor + len(b.text)))
        cursor += len(b.text)
    return "".join(parts), spans
