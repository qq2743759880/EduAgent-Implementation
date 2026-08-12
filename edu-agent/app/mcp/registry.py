# -*- coding: utf-8 -*-
"""P8 MCP：Server 注册/发现/健康检查/工具自动 discover。"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Any

from app.common.exceptions import AppException
from app.common.logging import logger
from app.database import execute_write, fetch_all, fetch_one

from .schemas import (
    MCPServerCreate, MCPServerDetail, MCPServerItem, MCPServerListResp,
    MCPServerUpdate, MCPToolItem, MCPToolListResp,
)


def _raise(http_status: int, message: str, code: int | None = None) -> AppException:
    """统一业务异常工厂：http_status 作为主码，业务码 = http_status*100（或指定 code）。返回异常对象供 raise。"""
    business_code = int(code if code is not None else http_status * 100)
    return AppException(code=business_code, message=message, http_status=int(http_status))


# ============================================================
# 1. 增删改查 CRUD
# ============================================================
async def register_server(created_by: int, payload: MCPServerCreate) -> MCPServerDetail:
    """新增 MCP Server；如果 server_code 重复抛 409。"""
    run_args_json = json.dumps(payload.run_args or [], ensure_ascii=False)
    http_headers_json = json.dumps(payload.http_headers or {}, ensure_ascii=False) if payload.http_headers is not None else None
    env_json = json.dumps(payload.env or {}, ensure_ascii=False) if payload.env is not None else None

    existing = await fetch_one(
        "SELECT id, yn FROM mcp_server WHERE server_code=%s LIMIT 1", (payload.server_code,),
    )
    if existing:
        if int(existing["yn"] or 0) == 0:
            # 软删除过则恢复：用户提供新值覆盖
            await execute_write(
                "UPDATE mcp_server SET yn=1, display_name=%s, description=%s, provider=%s, transport=%s,"
                " run_command=%s, run_args_json=%s, working_dir=%s, base_url=%s, http_headers_json=%s,"
                " env_json=%s, connect_timeout_ms=%s, call_timeout_ms=%s, enabled=%s, created_by=%s, "
                "last_health_at=NULL, last_health_ok=NULL, last_error=NULL "
                "WHERE id=%s",
                (
                    payload.display_name, payload.description or "", payload.provider or "self",
                    payload.transport.value, payload.run_command, run_args_json,
                    payload.working_dir, payload.base_url, http_headers_json,
                    env_json, payload.connect_timeout_ms, payload.call_timeout_ms,
                    payload.enabled, created_by, int(existing["id"]),
                ),
            )
            sid = int(existing["id"])
        else:
            raise _raise(409, f"server_code={payload.server_code} 已存在，请更换编码")
    else:
        sid = await execute_write(
            "INSERT INTO mcp_server (server_code, display_name, description, provider, transport,"
            " run_command, run_args_json, working_dir, base_url, http_headers_json, env_json,"
            " connect_timeout_ms, call_timeout_ms, enabled, created_by)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                payload.server_code, payload.display_name, payload.description or "",
                payload.provider or "self", payload.transport.value,
                payload.run_command, run_args_json, payload.working_dir,
                payload.base_url, http_headers_json, env_json,
                payload.connect_timeout_ms, payload.call_timeout_ms, payload.enabled, created_by,
            ),
        )
    return await get_server_detail(sid)


async def list_servers(*, transport: str | None = None, enabled: int | None = None,
                        keyword: str | None = None, page: int = 1, page_size: int = 20
                        ) -> MCPServerListResp:
    page = max(1, int(page or 1))
    page_size = max(1, min(100, int(page_size or 20)))
    where = ["S.yn=1"]
    args: list[Any] = []
    if transport:
        where.append("S.transport=%s"); args.append(transport)
    if enabled is not None:
        where.append("S.enabled=%s"); args.append(int(enabled))
    if keyword:
        kw = f"%{keyword}%"
        where.append("(S.server_code LIKE %s OR S.display_name LIKE %s OR S.description LIKE %s)")
        args += [kw, kw, kw]
    sql_base = f" FROM mcp_server S WHERE {' AND '.join(where)}"
    t_row = await fetch_one(f"SELECT COUNT(*) AS c {sql_base}", tuple(args))
    total = int(t_row["c"] or 0) if t_row else 0
    offset = (page - 1) * page_size
    rows = await fetch_all(
        f"SELECT S.*, (SELECT COUNT(*) FROM mcp_tool T WHERE T.server_id=S.id AND T.yn=1) tool_count "
        f"{sql_base} ORDER BY S.enabled DESC, S.id DESC LIMIT %s OFFSET %s",
        tuple(args) + (page_size, offset),
    )
    items: list[MCPServerItem] = []
    for r in rows:
        d = dict(r)
        d.setdefault("tool_count", 0)
        items.append(MCPServerItem.model_validate(d))
    return MCPServerListResp(total=total, page=page, page_size=page_size, items=items)


async def get_server_detail(server_id: int) -> MCPServerDetail:
    row = await fetch_one(
        "SELECT S.*, (SELECT COUNT(*) FROM mcp_tool T WHERE T.server_id=S.id AND T.yn=1) tool_count "
        "FROM mcp_server S WHERE S.id=%s AND S.yn=1 LIMIT 1",
        (server_id,),
    )
    if not row:
        raise _raise(404, f"Server id={server_id} 不存在或已删除")
    d = dict(row)
    # JSON 反序列化
    d["run_args"] = _safe_json(d.pop("run_args_json", None) or "[]", list)
    d["http_headers"] = _safe_json(d.pop("http_headers_json", None) or "{}", dict)
    d["env"] = _safe_json(d.pop("env_json", None) or "{}", dict)
    return MCPServerDetail.model_validate(d)


async def update_server(server_id: int, upd: MCPServerUpdate) -> MCPServerDetail:
    existing = await fetch_one("SELECT id, yn FROM mcp_server WHERE id=%s LIMIT 1", (server_id,))
    if not existing or int(existing["yn"] or 0) == 0:
        raise _raise(404, f"Server id={server_id} 不存在或已删除")
    sets: list[str] = []
    args: list[Any] = []
    if upd.display_name is not None:
        sets.append("display_name=%s"); args.append(upd.display_name)
    if upd.description is not None:
        sets.append("description=%s"); args.append(upd.description or "")
    if upd.provider is not None:
        sets.append("provider=%s"); args.append(upd.provider)
    if upd.transport is not None:
        sets.append("transport=%s"); args.append(upd.transport.value)
    if upd.run_command is not None:
        sets.append("run_command=%s"); args.append(upd.run_command or None)
    if upd.run_args is not None:
        sets.append("run_args_json=%s"); args.append(json.dumps(upd.run_args, ensure_ascii=False))
    if upd.working_dir is not None:
        sets.append("working_dir=%s"); args.append(upd.working_dir or None)
    if upd.base_url is not None:
        sets.append("base_url=%s"); args.append(upd.base_url or None)
    if upd.http_headers is not None:
        sets.append("http_headers_json=%s"); args.append(json.dumps(upd.http_headers, ensure_ascii=False))
    if upd.env is not None:
        sets.append("env_json=%s"); args.append(json.dumps(upd.env, ensure_ascii=False))
    if upd.connect_timeout_ms is not None:
        sets.append("connect_timeout_ms=%s"); args.append(upd.connect_timeout_ms)
    if upd.call_timeout_ms is not None:
        sets.append("call_timeout_ms=%s"); args.append(upd.call_timeout_ms)
    if upd.enabled is not None:
        sets.append("enabled=%s"); args.append(int(upd.enabled))
    if not sets:
        return await get_server_detail(server_id)
    sets.append("updated_at=CURRENT_TIMESTAMP")
    args.append(server_id)
    await execute_write(f"UPDATE mcp_server SET {', '.join(sets)} WHERE id=%s", tuple(args))
    return await get_server_detail(server_id)


async def delete_server(server_id: int, operator_id: int) -> None:
    existing = await fetch_one("SELECT id, yn FROM mcp_server WHERE id=%s LIMIT 1", (server_id,))
    if not existing or int(existing["yn"] or 0) == 0:
        raise _raise(404, f"Server id={server_id} 不存在或已删除")
    # 软删：server yn=0, 关联工具 yn=0
    await execute_write("UPDATE mcp_server SET yn=0, enabled=0, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                        (server_id,))
    await execute_write("UPDATE mcp_tool SET yn=0, updated_at=CURRENT_TIMESTAMP WHERE server_id=%s",
                        (server_id,))


# ============================================================
# 2. 工具查询
# ============================================================
async def list_tools(server_id: int | None = None, *, category: str | None = None,
                     keyword: str | None = None, page: int = 1, page_size: int = 20,
                     server_code: str | None = None,
                     ) -> MCPToolListResp:
    page = max(1, int(page or 1))
    page_size = max(1, min(100, int(page_size or 20)))
    where = ["T.yn=1"]
    args: list[Any] = []
    if server_id:
        where.append("T.server_id=%s"); args.append(server_id)
    elif server_code:
        where.append("EXISTS(SELECT 1 FROM mcp_server S WHERE S.id=T.server_id AND S.server_code=%s AND S.yn=1)")
        args.append(server_code)
    if category:
        where.append("T.category=%s"); args.append(category)
    if keyword:
        kw = f"%{keyword}%"
        where.append("(T.tool_name LIKE %s OR T.display_name LIKE %s OR T.description LIKE %s)")
        args += [kw, kw, kw]
    sql_base = (f" FROM mcp_tool T LEFT JOIN mcp_server S ON S.id=T.server_id "
                f"WHERE {' AND '.join(where)}")
    t_row = await fetch_one(f"SELECT COUNT(*) AS c {sql_base}", tuple(args))
    total = int(t_row["c"] or 0) if t_row else 0
    offset = (page - 1) * page_size
    rows = await fetch_all(
        f"SELECT T.*, S.server_code AS server_code {sql_base} "
        f"ORDER BY T.category, T.server_id, T.id LIMIT %s OFFSET %s",
        tuple(args) + (page_size, offset),
    )
    items: list[MCPToolItem] = []
    for r in rows:
        d = dict(r)
        d["input_schema"] = _safe_json(d.pop("input_schema_json", None) or "{}", dict)
        items.append(MCPToolItem.model_validate(d))
    return MCPToolListResp(total=total, page=page, page_size=page_size, items=items)


async def get_tool_by_ref(tool_id: int | None, server_id: int | None, tool_name: str | None):
    if tool_id:
        row = await fetch_one(
            "SELECT T.*, S.server_code, S.transport FROM mcp_tool T "
            "JOIN mcp_server S ON S.id=T.server_id "
            "WHERE T.id=%s AND T.yn=1 AND S.yn=1 AND S.enabled=1 LIMIT 1",
            (tool_id,),
        )
        if not row:
            raise _raise(404, f"tool_id={tool_id} 不存在或 server disabled/删除")
        return row
    if server_id and tool_name:
        row = await fetch_one(
            "SELECT T.*, S.server_code, S.transport FROM mcp_tool T "
            "JOIN mcp_server S ON S.id=T.server_id "
            "WHERE T.server_id=%s AND T.tool_name=%s AND T.yn=1 AND S.yn=1 AND S.enabled=1 LIMIT 1",
            (server_id, tool_name),
        )
        if not row:
            raise _raise(404, f"server_id={server_id} tool_name={tool_name} 不存在或 server disabled/删除")
        return row
    raise _raise(400, "必须提供 tool_id 或 server_id+tool_name")


async def write_server_health(server_id: int, *, ok: bool, last_error: str | None) -> None:
    await execute_write(
        "UPDATE mcp_server SET last_health_at=CURRENT_TIMESTAMP, last_health_ok=%s, last_error=%s "
        "WHERE id=%s",
        (1 if ok else 0, (last_error or "")[:1024] or None, server_id),
    )


# ============================================================
# 3. 工具 discover（初始化完成后 tools/list → 批量 INSERT IGNORE mcp_tool）
# ============================================================
async def upsert_discovered_tools(server_id: int, tools: list[dict]) -> int:
    """把 tools/list 返回的工具写入 mcp_tool，返回新增/更新条数。"""
    affected = 0
    for t in tools:
        name = (t.get("name") or "").strip()
        if not name:
            continue
        desc = str(t.get("description") or "")[:1024]
        schema_in = t.get("inputSchema") or t.get("input_schema") or {}
        if isinstance(schema_in, dict):
            pass
        elif isinstance(schema_in, str):
            schema_in = _safe_json(schema_in, dict)
        else:
            schema_in = {}
        existing = await fetch_one(
            "SELECT id FROM mcp_tool WHERE server_id=%s AND tool_name=%s LIMIT 1",
            (server_id, name),
        )
        if existing:
            await execute_write(
                "UPDATE mcp_tool SET description=%s, input_schema_json=%s, yn=1, "
                "display_name=CASE WHEN display_name='' THEN %s ELSE display_name END "
                "WHERE id=%s",
                (desc, json.dumps(schema_in, ensure_ascii=False), name[:64], int(existing["id"])),
            )
            affected += 1
        else:
            await execute_write(
                "INSERT INTO mcp_tool (server_id, tool_name, display_name, description, input_schema_json, category) "
                "VALUES (%s,%s,%s,%s,%s,'general')",
                (server_id, name, name[:64], desc, json.dumps(schema_in, ensure_ascii=False)),
            )
            affected += 1
    return affected


# ============================================================
# Helper
# ============================================================
def _safe_json(s: Any, default_factory) -> Any:
    if s is None:
        return default_factory() if callable(default_factory) else default_factory
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except Exception:
        return default_factory() if callable(default_factory) else default_factory
