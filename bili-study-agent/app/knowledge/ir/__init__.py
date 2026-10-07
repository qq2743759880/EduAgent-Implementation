# -*- coding: utf-8 -*-
"""Document IR 契约层 —— W2-S3（PRD v2 §6 / v2.1 §6.2 / ADR-W2-01）。

纯内存契约层：零 Redis / MinIO / Milvus I/O；零 upload / executor / task_store / importer 依赖。
- W2-S4 消费 ParserProtocol（parse_node 的 DOC_IR_ENABLED 分支）；
- SeedKnowledgeChunk.security 缺失 = 构造失败（fail-closed，无 public 默认）。
（本文件由 gen 脚本按 models.py/protocol.py 的 AST 真名生成——名随源，勿手改导出。）
"""

from app.knowledge.ir.models import (
    BLOCK_ID_FMT,
    BlockType,
    DocumentBlock,
    IR_SCHEMA_VERSION,
    IRArtifact,
    ParsedDocument,
    SecurityMeta,
    SeedKnowledgeChunk,
    SourceAssetRef,
    build_block_id,
    join_blocks_text,
)

from app.knowledge.ir.protocol import (
    PARSER_PROTOCOL_VERSION,
    get_parser,
    register_parser,
    registered_parsers,
    unregister_parser,
)

__all__ = [
    "BLOCK_ID_FMT",
    "BlockType",
    "DocumentBlock",
    "IR_SCHEMA_VERSION",
    "IRArtifact",
    "PARSER_PROTOCOL_VERSION",
    "ParsedDocument",
    "SecurityMeta",
    "SeedKnowledgeChunk",
    "SourceAssetRef",
    "build_block_id",
    "get_parser",
    "join_blocks_text",
    "register_parser",
    "registered_parsers",
    "unregister_parser",
]
