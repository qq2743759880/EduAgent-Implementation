# -*- coding: utf-8 -*-
"""p8_stdio_demo_server.py — 最小 stdio MCP 演示服务器（零依赖，stdlib only）。

被 app/mcp/executor.py 以 `python -u p8_stdio_demo_server.py`（LSP 式帧：
`Content-Length: N\\r\\n\\r\\n` + 裸 JSON）拉起，提供 4 个打靶工具：
  - ping()            → {"pong": true}
  - add(a, b)         → {"sum": int, "was_negative": bool}
  - echo(text)        → 回显文本
  - list_alphabet(n)  → 1~52 个字母 A..Z 循环序列

仅用于 MCP 管理端（/admin/mcp）健康检查 / 工具发现 / 工具测试打靶，无生产用途。
"""
from __future__ import annotations

import json
import sys
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "p8-stdio-demo", "version": "1.0.0"}


def _read_frame() -> dict[str, Any] | None:
    """读一帧 LSP 式消息（Content-Length 头 + 裸 JSON body）。EOF 返回 None。"""
    length: int | None = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None  # EOF
        line = line.strip()
        if not line:
            break  # 空行 = header 结束
        if b":" in line:
            k, v = line.split(b":", 1)
            if k.strip().lower() == b"content-length":
                try:
                    length = int(v.strip())
                except ValueError:
                    length = None
    if length is None:
        return None
    body = sys.stdin.buffer.read(length)
    if len(body) < length:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _write_frame(payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def _text_result(text: str, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


def _arg_err(msg: str) -> dict[str, Any]:
    return _text_result(msg, is_error=True)


def tool_add(args: dict[str, Any]) -> dict[str, Any]:
    a, b = args.get("a"), args.get("b")
    if not isinstance(a, int) or not isinstance(b, int) or isinstance(a, bool) or isinstance(b, bool):
        return _arg_err("args.a 与 args.b 必须是整数")
    total = a + b
    return _text_result(json.dumps({"sum": total, "was_negative": total < 0}, ensure_ascii=False))


def tool_echo(args: dict[str, Any]) -> dict[str, Any]:
    text = args.get("text")
    if not isinstance(text, str):
        return _arg_err("args.text 必须是字符串")
    return _text_result(text)


def tool_list_alphabet(args: dict[str, Any]) -> dict[str, Any]:
    n = args.get("n")
    if not isinstance(n, int) or isinstance(n, bool) or not (1 <= n <= 52):
        return _arg_err("args.n 必须是 1~52 的整数")
    seq = ("ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 2)[:n]
    return _text_result(json.dumps({"n": n, "sequence": seq}, ensure_ascii=False))


def tool_ping(args: dict[str, Any]) -> dict[str, Any]:
    return _text_result(json.dumps({"pong": True}, ensure_ascii=False))


TOOLS = {
    "ping": {
        "description": "心跳测试",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "handler": tool_ping,
    },
    "add": {
        "description": "整数 a + b，返回 {sum, was_negative}。",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
        "handler": tool_add,
    },
    "echo": {
        "description": "文本回显",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "handler": tool_echo,
    },
    "list_alphabet": {
        "description": "返回 1~52 个字母序列 A..Z 循环，用于 list/dict 往返验证。",
        "inputSchema": {
            "type": "object",
            "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 52}},
            "required": ["n"],
        },
        "handler": tool_list_alphabet,
    },
}


def _dispatch(msg: dict[str, Any]) -> dict[str, Any] | None:
    method = msg.get("method")
    msg_id = msg.get("id")
    is_notification = msg_id is None

    if method == "initialize":
        params = msg.get("params") or {}
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }
    if method in ("notifications/initialized", "initialized"):
        return None  # 通知，无响应
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [
                    {"name": name, "description": meta["description"], "inputSchema": meta["inputSchema"]}
                    for name, meta in TOOLS.items()
                ]
            },
        }
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        meta = TOOLS.get(name) if isinstance(name, str) else None
        if meta is None:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": _text_result(f"未知工具：{name!r}", is_error=True),
            }
        try:
            return {"jsonrpc": "2.0", "id": msg_id, "result": meta["handler"](params.get("arguments") or {})}
        except Exception as exc:  # 工具内异常 → isError 结果，不崩进程
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": _text_result(f"{type(exc).__name__}: {exc}", is_error=True),
            }
    if is_notification:
        return None
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main() -> int:
    while True:
        msg = _read_frame()
        if msg is None:  # EOF / shutdown
            return 0
        if not msg:
            continue
        try:
            resp = _dispatch(msg)
        except Exception:
            resp = None
        if resp is not None:
            _write_frame(resp)


if __name__ == "__main__":
    sys.exit(main())
