# -*- coding: utf-8 -*-
"""parser 协议 + 注册表（W2-S3 契约冻结；W3 MinerU 实现方消费；本单不实现任何 parser）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

#: parser 协议版本（冻结 v1；跨版本迁移走 ADR，与 IR_SCHEMA_VERSION 同纪律）。
PARSER_PROTOCOL_VERSION = "v1"
#: 支持的协议版本集合（唯一成员 v1；v2 出现须先过 ADR）。
SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = ("v1",)


@dataclass(frozen=True)
class PreparedAsset:
    """解码后的本地暂存输入（本地临时路径 + mime + encoding 声明；纯数据零 I/O）。"""

    local_path: Path
    mime: str
    encoding: str | None = None
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.local_path, Path):
            raise TypeError(f"local_path 必须是 pathlib.Path，实际 {type(self.local_path).__name__}")


@runtime_checkable
class ParserProtocol(Protocol):
    """parser 结构化协议（v1 冻结）：parse(source, prepared) -> ParsedDocument。

    实现方（W3 MinerU / pdfplumber fallback / 测试 stub）只需提供 parse 方法
    即满足协议（isinstance 结构化判定），无需继承。契约语义：
    - 成功：返回 blocks 非空的 ParsedDocument（空文档走失败语义，不产空 IR）；
    - 失败：抛异常由调用方降级（v2 §6.4），协议层不吞异常、不返回 None。
    """

    def parse(self, source, prepared: PreparedAsset):  # noqa: ANN001 — 具体类型见 ir.models
        ...


_PARSERS: dict[str, ParserProtocol] = {}


def register_parser(name: str, parser: ParserProtocol) -> None:
    """按名注册 parser（重名 = 契约冲突直接拒绝；非协议实现拒收）。"""
    if not name or not name.strip():
        raise ValueError("parser 名不得为空")
    if name in _PARSERS:
        raise ValueError(f"parser {name!r} 已注册（重名注册 = 契约冲突，禁止静默覆盖）")
    if not isinstance(parser, ParserProtocol):
        raise TypeError(f"parser 必须满足 ParserProtocol，实际 {type(parser).__name__}")
    _PARSERS[name] = parser


def get_parser(name: str) -> ParserProtocol:
    """按名取 parser；未注册 = KeyError（不掩盖路由错误）。"""
    try:
        return _PARSERS[name]
    except KeyError:
        raise KeyError(f"parser {name!r} 未注册（已注册：{sorted(_PARSERS)}）") from None


def unregister_parser(name: str) -> None:
    """注销 parser（仅供测试隔离使用；生产路径不调用）。"""
    _PARSERS.pop(name, None)


def registered_parsers() -> tuple[str, ...]:
    """已注册 parser 名（只读视图，审计/路由打印用）。"""
    return tuple(sorted(_PARSERS))
