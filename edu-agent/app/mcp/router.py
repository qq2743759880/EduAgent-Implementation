# -*- coding: utf-8 -*-
"""P8 MCP：管理端 Router（注册/import-url/工具列表/工具测试/注销 5 API + 日志/health/discover 扩展）。

RBAC：整路由 require_role([ADMIN])，与全局约束第 8 条一致。
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.auth import CurrentUser, UserRole, get_current_user, require_role
from app.common.exceptions import AppException
from app.core.resp import ok

from . import description_reviewer, executor, registry
from .schemas import (
    DEFAULT_PAGE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE,
    MCPServerCreate, MCPServerDetail, MCPServerListResp,
    MCPServerUpdate, MCPImportResp, MCPImportUrlReq, MCPLogDetail, MCPLogItem, MCPLogListResp,
    MCPToolListResp, MCPToolTestReq, MCPToolTestResp,
    MCPLiveDiscoverResp, MCPRawRpcReq, MCPRawRpcResp, MCPHealthScanResp,
    MCPSessionCreateReq, MCPSessionItem, MCPSessionListResp, MCPSessionResp,
    MCPDescriptionReviewResp, MCPReviewLogItem, MCPReviewLogListResp,
)

# task04 #5：call-log status 过滤白名单。
# 必须用模块级类型别名而非函数内联 Literal 字面量 —— 本文件启用了
# `from __future__ import annotations`，内联 Literal 会被字符串化 ForwardRef，
# FastAPI/Pydantic 无法解析其成员 → PydanticUserError not fully defined（500）。
CallLogStatus = Literal["SUCCESS", "ERROR", "TIMEOUT", "SKIPPED"]


router = APIRouter(
    prefix="/api/mcp",
    tags=["MCP-管理端"],
    dependencies=[Depends(require_role([UserRole.ADMIN]))],
)


# ============================================================
# 1. Server 注册 / 列表 / 详情 / 更新 / 删除
# ============================================================
@router.post("/servers", response_model=dict,
             summary="P8-1 手动注册 MCP Server（stdio / SSE / HTTP）")
async def p8_register_server(payload: MCPServerCreate, me: CurrentUser = Depends(get_current_user)):
    try:
        return ok(await registry.register_server(created_by=int(me.user_id), payload=payload))
    except AppException as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


@router.get("/servers", response_model=dict,
            summary="P8-2 MCP Server 列表（分页+transport/enabled/关键词过滤）")
async def p8_list_servers(
    transport: Optional[str] = Query(default=None, description="stdio | sse | http"),
    enabled: Optional[int] = Query(default=None, ge=0, le=1),
    keyword: Optional[str] = Query(default=None, max_length=128, description="server_code/display_name/描述 模糊"),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    return ok(await registry.list_servers(
        transport=transport, enabled=enabled, keyword=keyword, page=page, page_size=page_size,
    ))


@router.get("/servers/{server_id}", response_model=dict,
            summary="P8-3 Server 详情（含敏感字段：run_command/args/env/http_headers）")
async def p8_server_detail(server_id: int):
    try:
        return ok(await registry.get_server_detail(server_id))
    except AppException as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


@router.patch("/servers/{server_id}", response_model=dict,
              summary="P8-4 更新 Server 部分字段（局部修改）")
async def p8_update_server(server_id: int, payload: MCPServerUpdate):
    try:
        return ok(await registry.update_server(server_id, payload))
    except AppException as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


@router.delete("/servers/{server_id}", status_code=200,
               summary="P8-5 注销 Server（软删 yn=0；关联工具同步 yn=0）")
async def p8_delete_server(server_id: int, me: CurrentUser = Depends(get_current_user)):
    try:
        await registry.delete_server(server_id, operator_id=int(me.user_id))
        return ok({"ok": True, "server_id": server_id, "deleted": True})
    except AppException as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


# ============================================================
# 2. Health & Discover 工具
# ============================================================
@router.post("/servers/{server_id}/health",
             summary="P8-6 立即健康检查（stdio：initialize+ping；SSE：GET base_url 200）")
async def p8_health_check(server_id: int):
    try:
        return ok({"server_id": server_id, **(await executor.health_check_server(server_id))})
    except AppException as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


@router.post("/servers/{server_id}/discover",
             summary="P8-7 initialize+tools/list 自动导入所有工具到 mcp_tool（INSERT IGNORE 幂等）")
async def p8_discover(server_id: int, me: CurrentUser = Depends(get_current_user)):
    try:
        result = await executor.discover_tools(server_id, operator_user_id=int(me.user_id))
        return ok({"server_id": server_id,
                   "discovered_count": int(result.get("count") or 0),
                   "warning": result.get("error") or None})
    except AppException as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


# ============================================================
# 3. Import URL（一键导入）—— 支持 http(s) URL 与 data://test-stdio 打靶占位
# ============================================================
@router.post("/servers/import-url", response_model=dict,
             summary="P8-8 一键导入 MCP Server（data://test-stdio 打靶专用或 https:// 实际 SSE URL）")
async def p8_import_url(payload: MCPImportUrlReq, me: CurrentUser = Depends(get_current_user)):
    url = (payload.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url 不能为空")
    display_name = payload.preset_name or None
    if url.startswith("data://test-stdio") or url.startswith("test-stdio://"):
        # 打靶数据协议：创建 stdio-echodemo 副本，编码唯一（加时间戳）
        import time as _t
        suffix = f"COPY-{int(_t.time()*1000)}-{uuid.uuid4().hex[:6]}"
        server_code = f"stdio-import-{suffix}"
        display_name = display_name or f"Import 副本 · stdio 演示（{suffix[-6:]}）"
        python_exe = sys.executable or os.environ.get("PYTHON_EXE") or "python"
        demo_script = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "p8_stdio_demo_server.py",
        ))
        create = MCPServerCreate(
            server_code=server_code, display_name=display_name,
            description=f"通过 import-url {url} 从 stdio-echodemo 副本导入。",
            provider="self", transport="stdio",
            run_command=python_exe,
            run_args=["-u", demo_script],
            working_dir=str(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))),
            base_url=None, http_headers=None, env=None,
            connect_timeout_ms=3000, call_timeout_ms=15000, enabled=1,
        )
        try:
            server = await registry.register_server(int(me.user_id), create)
        except AppException as exc:
            raise HTTPException(status_code=exc.http_status, detail=exc.message)
        disc_count = 0
        warning: str | None = None
        if not payload.skip_health_check:
            try:
                disc = await executor.discover_tools(int(server.id), int(me.user_id))
                disc_count = int(disc.get("count") or 0)
                warning = disc.get("error")
            except Exception as exc:  # noqa: BLE001
                warning = f"health/discover 异常：{exc}"[:512]
        return ok(MCPImportResp(
            imported=True, server_id=int(server.id), server_code=server.server_code,
            display_name=server.display_name, transport=server.transport,
            discovered_tool_count=disc_count, warning=warning,
        ))
    # http(s) / URL：默认 SSE，base_url=url
    if url.startswith("http://") or url.startswith("https://"):
        suffix = f"URL-{int(datetime.now().timestamp()*1000)}-{uuid.uuid4().hex[:6]}"
        server_code = f"sse-import-{suffix}"
        display_name = display_name or f"Import SSE · {url.split('?')[0][:40]}"
        create = MCPServerCreate(
            server_code=server_code, display_name=display_name,
            description=f"通过 import-url 导入（{url}）",
            provider="self", transport="sse",
            base_url=url, enabled=0,  # 默认 disabled，避免对话注入无鉴权 SSE
            connect_timeout_ms=5000, call_timeout_ms=30000,
        )
        try:
            server = await registry.register_server(int(me.user_id), create)
        except AppException as exc:
            raise HTTPException(status_code=exc.http_status, detail=exc.message)
        warning = None
        if not payload.skip_health_check:
            try:
                hc = await executor.health_check_server(int(server.id))
                if not hc.get("ok"):
                    warning = f"SSE 健康检查未通过（首次导入属常见，检查 URL/网络后可再启用）：{hc.get('reason')}"[:512]
            except Exception as exc:  # noqa: BLE001
                warning = f"SSE 健康检查异常：{exc}"[:512]
        return ok(MCPImportResp(
            imported=True, server_id=int(server.id), server_code=server.server_code,
            display_name=server.display_name, transport=server.transport,
            discovered_tool_count=0, warning=warning,
        ))
    raise HTTPException(status_code=400,
                        detail=f"不支持的 URL 协议（需要 http(s):// 或 data://test-stdio），实际：{url[:100]}")


# ============================================================
# 4. 工具列表（可按 server_id/server_code/category/关键词 过滤 + 分页）
# ============================================================
@router.get("/servers/{server_id}/tools", response_model=dict,
            summary="P8-9 按 server 查看工具列表（含分页+按名字/描述关键词过滤）")
async def p8_list_tools_of_server(
    server_id: int,
    category: Optional[str] = Query(default=None, max_length=32),
    keyword: Optional[str] = Query(default=None, max_length=128),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    return ok(await registry.list_tools(server_id=server_id, category=category, keyword=keyword,
                                        page=page, page_size=page_size))


@router.get("/tools", response_model=dict,
            summary="P8-10 全局工具列表（跨 server；可按 server_code/category/关键词搜索）")
async def p8_list_tools_global(
    server_code: Optional[str] = Query(default=None, max_length=64),
    category: Optional[str] = Query(default=None, max_length=32),
    keyword: Optional[str] = Query(default=None, max_length=128),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    return ok(await registry.list_tools(server_id=None, server_code=server_code, category=category,
                                        keyword=keyword, page=page, page_size=page_size))


# ============================================================
# 4B. 描述体检（task33）：『描述体检』按钮 + 审计日志
# ============================================================
@router.post("/description-review", response_model=dict,
             summary="P8-22 立即对全部（或指定 server）MCP 工具做描述体检（规则打分 + <70 分 FAST 重写），供前端『描述体检』按钮调用")
async def p8_run_description_review(
    server_id: Optional[int] = Query(default=None, description="不传=全部 yn=1 的 server"),
    me: CurrentUser = Depends(get_current_user),
):
    """管理端『描述体检』按钮 → 规则打分 0-100；<70 分 FAST 模型按五要素重写；
    结果写回 mcp_tool.description_rewritten + 审计日志。LLM 重写受测试窗口纪律约束。"""
    result = await description_reviewer.run_description_review(
        server_id=server_id,
        operator_user_id=int(me.user_id),
        trace_id=f"p8-desc-review-{uuid.uuid4().hex[:12]}",
    )
    return ok(MCPDescriptionReviewResp.model_validate(result))


@router.get("/description-review-log", response_model=dict,
            summary="P8-23 描述体检审计日志（分页，可按 server_id/tool_id 过滤，时间倒序）")
async def p8_list_description_review_log(
    server_id: Optional[int] = Query(default=None),
    tool_id: Optional[int] = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    total, rows = await registry.list_description_review_log(
        server_id=server_id, tool_id=tool_id, page=page, page_size=page_size,
    )
    items = [MCPReviewLogItem.model_validate(dict(r)) for r in rows]
    return ok(MCPReviewLogListResp(total=total, page=page, page_size=page_size, items=items))


# ============================================================
# 5. Tool 测试调用（写 mcp_tool_call_log 审计）
# ============================================================
@router.post("/tools/test", response_model=dict,
             summary="P8-11 测试调用工具（tool_id 或 server_id+tool_name，结果含 content_text & latency_ms）")
async def p8_tool_test(payload: MCPToolTestReq, me: CurrentUser = Depends(get_current_user)):
    trace_id = f"p8-test-{uuid.uuid4().hex[:12]}"
    try:
        return ok(await executor.call_tool(
            operator_user_id=int(me.user_id),
            tenant_id=str(getattr(me, "tenant_id", "") or ""),
            trace_id=trace_id,
            tool_id=payload.tool_id,
            server_id=payload.server_id,
            tool_name=payload.tool_name,
            args=payload.args or {},
        ))
    except AppException as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)


# ============================================================
# 6. 调用日志（按 server_id/tool_name/user_id/时间范围分页）
# ============================================================
@router.get("/call-log", response_model=dict,
            summary="P8-12 工具调用审计日志（分页，支持按 server_id/tool_name/status/user_id/created_from/created_to 过滤）")
async def p8_list_call_log(
    server_id: Optional[int] = Query(default=None),
    tool_name: Optional[str] = Query(default=None, max_length=128),
    status: Optional[CallLogStatus] = Query(default=None, max_length=16),
    user_id: Optional[int] = Query(default=None),
    created_from: Optional[datetime] = Query(default=None),
    created_to: Optional[datetime] = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    # task04 #5：status 用 Literal 枚举约束——非法枚举由 FastAPI 校验层直接 422，
    # 不再静默跳过过滤条件（此前 status=HACKED 返回全量日志，审计结果误导）。
    from app.database import fetch_all, fetch_one
    where = ["1=1"]
    args: list[Any] = []
    if server_id:
        where.append("server_id=%s"); args.append(server_id)
    if tool_name:
        where.append("tool_name=%s"); args.append(tool_name)
    if status:
        where.append("status=%s"); args.append(status)
    if user_id:
        where.append("user_id=%s"); args.append(user_id)
    if created_from:
        where.append("created_at>=%s"); args.append(created_from)
    if created_to:
        where.append("created_at<=%s"); args.append(created_to)
    sql_base = f" FROM mcp_tool_call_log WHERE {' AND '.join(where)}"
    t_row = await fetch_one(f"SELECT COUNT(*) AS c {sql_base}", tuple(args))
    total = int(t_row["c"] or 0) if t_row else 0
    offset = (page - 1) * page_size
    rows = await fetch_all(
        f"SELECT id,call_id,server_id,tool_name,status,latency_ms,user_id,trace_id,error_message,created_at "
        f"{sql_base} ORDER BY id DESC LIMIT %s OFFSET %s",
        tuple(args) + (page_size, offset),
    )
    items = [MCPLogItem.model_validate(dict(r)) for r in rows]
    return ok(MCPLogListResp(total=total, page=page, page_size=page_size, items=items))


@router.get("/call-log/{log_id}", response_model=dict,
            summary="P8-12a【调试】单条 MCP 调用日志详情（含完整 args / result / error_info JSON）")
async def p8_get_call_log_detail(log_id: int):
    from app.database import fetch_one
    import json as _json

    row = await fetch_one(
        "SELECT id,call_id,server_id,tool_name,status,latency_ms,user_id,tenant_id,trace_id,"
        "error_message,created_at,args_json,result_json,error_json "
        "FROM mcp_tool_call_log WHERE id=%s LIMIT 1",
        (int(log_id),),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"mcp_call_log#{log_id} not found")
    payload = dict(row)

    def _safe_load(s: str | None):
        if not s:
            return None
        try:
            return _json.loads(s)
        except Exception:
            return {"_raw": s}

    detail_obj = MCPLogDetail(
        id=int(payload["id"]),
        call_id=str(payload["call_id"]),
        server_id=int(payload["server_id"]),
        tool_name=str(payload["tool_name"]),
        status=str(payload["status"]),
        latency_ms=int(payload["latency_ms"] or 0),
        user_id=int(payload["user_id"] or 0),
        tenant_id=str(payload.get("tenant_id") or ""),
        trace_id=str(payload.get("trace_id") or ""),
        error_message=None if not payload.get("error_message") else str(payload["error_message"]),
        created_at=payload["created_at"],
        args=_safe_load(payload.get("args_json")) or {},
        result=_safe_load(payload.get("result_json")),
        error_info=_safe_load(payload.get("error_json")) or {},
    )
    return ok(detail_obj)


# ============================================================
# 7. 管理端调试面板专用 API
# ============================================================
@router.get("/servers/{server_id}/discover-live", response_model=dict,
            summary="P8-13【调试】直连 Server 取 tools/list 实时快照（不落库，不写 mcp_tool）")
async def p8_live_discover(server_id: int):
    result = await executor.live_discover_tools(server_id)
    return ok(MCPLiveDiscoverResp.model_validate(result))


@router.post("/servers/{server_id}/raw-rpc", response_model=dict,
             summary="P8-14【调试】管理员直连 Server 发任意 JSON-RPC（initialize/tools/list/ping/…）")
async def p8_raw_rpc(server_id: int, payload: MCPRawRpcReq):
    result = await executor.raw_rpc_call(
        server_id=server_id, method=payload.method, params=payload.params,
        call_timeout_ms=payload.call_timeout_ms, session_id=payload.session_id,
    )
    return ok(MCPRawRpcResp.model_validate(result))


@router.post("/health-scan", response_model=dict,
             summary="P8-15【调试】对所有 yn=1 的 MCP Server 做批量健康扫描")
async def p8_health_scan():
    result = await executor.scan_all_servers_health()
    return ok(MCPHealthScanResp.model_validate(result))


# ============================================================
# 7B. stdio 长连接会话（Checkpoint）：创建/列表/详情/保活/关闭 + GC
# ============================================================
@router.post("/sessions", response_model=dict,
             summary="P8-17【调试】创建 stdio 长连接会话（initialize 成功后入池，空闲 GC TTL 可配）")
async def p8_sessions_create(payload: MCPSessionCreateReq,
                             me: CurrentUser = Depends(get_current_user)):
    result = await executor.session_create(
        server_id=payload.server_id, ttl_seconds=payload.ttl_seconds,
        created_by_uid=int(me.user_id),
    )
    return ok(MCPSessionResp.model_validate(result))


@router.get("/sessions", response_model=dict,
            summary="P8-18【调试】列出当前进程内所有活动会话（含 pid/call_count/idle TTL）")
async def p8_sessions_list():
    await executor.session_pool_gc(force_all=False)
    items = [MCPSessionItem.model_validate(x) for x in await executor.session_list()]
    return ok(MCPSessionListResp(total=len(items), items=items))


@router.get("/sessions/{session_id}", response_model=dict,
            summary="P8-19【调试】单个会话快照（不存在 404）")
async def p8_sessions_get(session_id: str):
    item = await executor.session_get(session_id)
    if item is None:
        return ok(MCPSessionResp(ok=False, message=f"session={session_id} not found", session=None))
    return ok(MCPSessionResp(ok=True, message="ok", session=MCPSessionItem.model_validate(item)))


@router.post("/sessions/{session_id}/touch", response_model=dict,
             summary="P8-20【调试】保活：重置 last_used_ms（避免 idle GC 回收）")
async def p8_sessions_touch(session_id: str):
    result = await executor.session_ping(session_id)
    if not result.get("ok"):
        return ok(MCPSessionResp(ok=False, message=str(result.get("message") or "touch fail"), session=None))
    return ok(MCPSessionResp(ok=True, message=str(result.get("message") or "ok"),
                             session=MCPSessionItem.model_validate(result["session"])))


@router.delete("/sessions/{session_id}", response_model=dict,
               summary="P8-21【调试】关闭会话（terminate 子进程 + 移除池）")
async def p8_sessions_close(session_id: str):
    result = await executor.session_close(session_id)
    if (result.get("session") or None) is None:
        return ok(MCPSessionResp(ok=True, message=str(result.get("message") or "closed"), session=None))
    return ok(MCPSessionResp(ok=True, message=str(result.get("message") or "closed"),
                             session=MCPSessionItem.model_validate(result["session"])))


# ============================================================
# 8. 调试面板 UI HTML（单页内嵌 JS：工具列表 + 参数编辑 + 调用 + 最近日志）
# ============================================================
@router.get("/console", response_class=HTMLResponse, include_in_schema=False,
            summary="P8-16【调试 UI】管理端 MCP 工具在线调试单页")
async def p8_debug_console_page(request: Request):
    """服务端渲染：一次性吐出 Server 列表 + HTML + 内嵌 JS（直接 fetch 上面 API）。"""
    from app.database import fetch_all
    servers = await fetch_all(
        "SELECT id,server_code,display_name,transport,last_health_ok,last_health_at "
        "FROM mcp_server WHERE yn=1 ORDER BY id ASC"
    )
    default_sid = int(servers[0]["id"]) if servers else 0
    server_cards_html = "".join(
        f"""<div class="svr-card" data-sid="{s['id']}" onclick="selectServer({s['id']})">
            <div class="svr-title">#{s['id']} <b>{_h(s['server_code'])}</b></div>
            <div class="svr-sub">{_h(s['display_name'] or '')} · {_h(s['transport'] or '')}</div>
            <div class="svr-status {'ok' if s.get('last_health_ok') else 'err'}">
              {'● OK' if s.get('last_health_ok') else '● ERR'}
              <span>{_h(str(s.get('last_health_at') or '-')[:19])}</span>
            </div>
        </div>"""
        for s in servers
    ) if servers else '<div class="empty">未发现 MCP Server。请先在管理端 POST /api/admin/mcp/servers 注册。</div>'
    servers_json = json.dumps([
        {
            "id": int(s["id"]),
            "server_code": str(s.get("server_code") or ""),
            "display_name": str(s.get("display_name") or ""),
            "transport": str(s.get("transport") or ""),
        } for s in servers
    ], ensure_ascii=False)
    api_base = str(request.base_url).rstrip("/")
    # 使用 4 个显式占位符 __TOKEN__ 替换，避免 str.format 与 CSS/JS 原生 {} 冲突
    html = (_MCP_CONSOLE_TEMPLATE
            .replace("__API_BASE__", api_base)
            .replace("__SERVER_CARDS_HTML__", server_cards_html)
            .replace("__SERVERS_JSON__", servers_json)
            .replace("__DEFAULT_SID__", str(default_sid)))
    return HTMLResponse(content=html, status_code=200)


def _h(s: str) -> str:
    """HTML 转义：避免 xss（server_code / display_name 来自管理员配置，仍做最小转义）。"""
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


# ============================================================
# 9. UI 模板（调试面板单页 HTML/CSS/JS）
# ============================================================
_MCP_CONSOLE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<title>MCP Console · 管理端工具在线调试</title>
<style>
:root{
  --bg:#0f172a; --card:#111827; --line:#1f2937; --txt:#e5e7eb; --sub:#9ca3af;
  --ok:#10b981; --err:#ef4444; --accent:#6366f1; --warn:#f59e0b; --mono:#fde68a;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--txt);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif}
a{color:var(--accent)}
.wrap{max-width:1400px;margin:0 auto;padding:16px}
.hd{display:flex;align-items:center;justify-content:space-between;padding:4px 2px 14px;border-bottom:1px solid var(--line);margin-bottom:16px}
.hd h1{font-size:18px;margin:0}
.hd .tag{background:var(--accent);color:#fff;padding:3px 10px;border-radius:999px;font-size:12px}
.grid{display:grid;grid-template-columns: 280px 1fr; gap:16px}
@media (max-width: 980px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.card h2{font-size:13px;color:var(--sub);margin:0 0 10px;letter-spacing:.08em;text-transform:uppercase}
.svr-list{display:flex;flex-direction:column;gap:8px;max-height:70vh;overflow:auto}
.svr-card{border:1px solid var(--line);border-radius:8px;padding:10px;cursor:pointer;transition:.15s}
.svr-card:hover{border-color:var(--accent)}
.svr-card.active{border-color:var(--accent);box-shadow:0 0 0 2px rgba(99,102,241,.18)}
.svr-title{font-size:14px;margin-bottom:4px}
.svr-sub{font-size:12px;color:var(--sub);margin-bottom:6px}
.svr-status{font-size:12px}
.svr-status.ok{color:var(--ok)}
.svr-status.err{color:var(--err)}
.svr-status span{color:var(--sub);margin-left:6px;font-size:11px}
.empty{color:var(--sub);padding:16px;text-align:center;border:1px dashed var(--line);border-radius:8px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
@media (max-width: 760px){.row{grid-template-columns:1fr}}
.btn{display:inline-flex;align-items:center;gap:6px;border:0;background:var(--accent);color:#fff;padding:8px 14px;border-radius:8px;cursor:pointer;font-size:13px}
.btn.sec{background:#1f2937;color:var(--txt)}
.btn.dan{background:var(--ok)}
.btn.war{background:var(--warn);color:#111}
.btn:disabled{opacity:.5;cursor:not-allowed}
textarea,input,select{background:#0b1220;color:var(--txt);border:1px solid var(--line);border-radius:6px;padding:8px 10px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px;width:100%}
textarea{min-height:140px;resize:vertical}
label{display:block;color:var(--sub);font-size:12px;margin-bottom:4px}
.tbl{width:100%;border-collapse:collapse;font-size:13px}
.tbl th,.tbl td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.tbl th{color:var(--sub);font-weight:600;background:rgba(255,255,255,.02);position:sticky;top:0}
.tbl tr:hover td{background:rgba(99,102,241,.05)}
.tbl td b{color:#fff}
.tbl .mono{color:var(--mono);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px}
.badge.ok{background:rgba(16,185,129,.15);color:var(--ok)}
.badge.err{background:rgba(239,68,68,.15);color:var(--err)}
.badge.run{background:rgba(245,158,11,.15);color:var(--warn)}
.panel{background:#0b1220;border:1px solid var(--line);border-radius:8px;padding:12px;min-height:140px;white-space:pre-wrap;word-break:break-all;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;color:var(--mono);max-height:360px;overflow:auto}
.kv{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px;margin-bottom:10px}
.kv .k{color:var(--sub);font-size:12px}
.kv .v{font-size:13px}
.tabs{display:flex;gap:6px;margin:0 0 10px;border-bottom:1px solid var(--line)}
.tabs div{padding:8px 14px;cursor:pointer;color:var(--sub);border-bottom:2px solid transparent;font-size:13px}
.tabs div.a{color:#fff;border-color:var(--accent)}
.hint{color:var(--sub);font-size:12px;margin-top:6px}
.row-flex{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.ml-a{margin-left:auto}
.pill{padding:3px 10px;border-radius:999px;font-size:11px;background:#1f2937;color:var(--sub)}
.scan-bar{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
</style>
</head>
<body>
<div class="wrap">
  <div class="hd">
    <h1>🧩 MCP Console · 管理端工具在线调试面板</h1>
    <span class="tag">ADMIN ONLY</span>
  </div>

  <div class="grid">
    <!-- 左：Server 选择 -->
    <section class="card">
      <h2>MCP Servers</h2>
      <div class="scan-bar">
        <button class="btn war" onclick="scanAll()">批量扫描</button>
        <span id="scan-summary" class="pill">未扫描</span>
      </div>
      <div id="server-list" class="svr-list">__SERVER_CARDS_HTML__</div>
    </section>

    <!-- 右：工具 / 调用 / 日志 -->
    <section>
      <!-- 工具列表 -->
      <div class="card" style="margin-bottom:16px">
        <div class="row-flex">
          <h2 style="margin:0">Tools <span id="tl-count" class="pill">—</span></h2>
          <div class="ml-a">
            <button class="btn sec" onclick="liveDiscover()">🔄 实时 Discover</button>
            <button class="btn" onclick="fetchDbTools()">📚 DB 列表</button>
          </div>
        </div>
        <p class="hint">实时 Discover：直连 Server 发 initialize → notifications/initialized → tools/list，结果不落库。</p>
        <div style="max-height:300px;overflow:auto;border:1px solid var(--line);border-radius:8px">
        <table class="tbl" id="tools-tbl">
          <thead><tr><th style="width:28%"># 工具名</th><th>描述 / Schema</th><th style="width:120px">操作</th></tr></thead>
          <tbody><tr><td colspan="3" class="empty">请选择左侧 Server 并点击 “实时 Discover”</td></tr></tbody>
        </table>
        </div>
      </div>

      <!-- 调用面板 -->
      <div class="card" style="margin-bottom:16px">
        <h2>Tool Call（使用 tools/call）</h2>
        <div class="row">
          <div><label>tool_name</label><input id="c-name" placeholder="如 echo / add / list_alphabet / ping" /></div>
          <div><label>server_id</label><input id="c-sid" value="__DEFAULT_SID__" readonly /></div>
        </div>
        <label>参数 args（JSON）</label>
        <textarea id="c-args">{  }</textarea>
        <div class="row-flex" style="margin-top:8px">
          <button class="btn dan" onclick="callTool()">▶ 调用工具</button>
          <button class="btn sec" onclick="rawRpcCall()">发 JSON-RPC（原始）</button>
          <span class="hint" style="margin-left:6px">或选择下方 Raw RPC 模式：</span>
          <input id="r-method" placeholder="JSON-RPC method，如 ping / tools/list" style="max-width:260px" />
        </div>
      </div>

      <!-- 结果 -->
      <div class="card" style="margin-bottom:16px">
        <div class="tabs" id="res-tabs">
          <div class="a" data-tab="out" onclick="tab('out')">Output</div>
          <div data-tab="raw" onclick="tab('raw')">Raw JSON</div>
        </div>
        <div class="kv">
          <div><div class="k">status</div><div class="v" id="r-status">—</div></div>
          <div><div class="k">latency_ms</div><div class="v" id="r-lat">—</div></div>
          <div><div class="k">content_text</div><div class="v" id="r-text">—</div></div>
          <div><div class="k">error_message</div><div class="v" id="r-err">—</div></div>
        </div>
        <div class="panel" id="r-raw">（尚未调用）</div>
      </div>

      <!-- 最近调用日志 -->
      <div class="card">
        <div class="row-flex">
          <h2 style="margin:0">调用日志（最近 20 条）</h2>
          <button class="btn sec ml-a" onclick="refreshLog()">🔄 刷新</button>
        </div>
        <div style="max-height:340px;overflow:auto;border:1px solid var(--line);border-radius:8px;margin-top:10px">
        <table class="tbl" id="log-tbl">
          <thead><tr>
            <th>时间</th><th>server</th><th>tool</th><th>status</th><th>latency</th><th>user_id</th><th>error</th>
          </tr></thead>
          <tbody><tr><td colspan="7" class="empty">暂无</td></tr></tbody>
        </table>
        </div>
      </div>
    </section>
  </div>
</div>

<script>
const API_BASE = "__API_BASE__";
const SERVERS = __SERVERS_JSON__;
let currentSid = __DEFAULT_SID__;
let token = (document.cookie.match(/access_token=([^;]+)/)||[])[1] || localStorage.getItem("access_token") || "";
function authHdrs(){ return {"Content-Type":"application/json", "Authorization":"Bearer " + token}; }
function esc(s){return (s==null?"":String(s)).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}
function j2(o){try{return JSON.stringify(o,null,2)}catch(e){return String(o)}}

function selectServer(sid){
  currentSid = sid;
  document.getElementById("c-sid").value = sid;
  document.querySelectorAll(".svr-card").forEach(el=>{
    el.classList.toggle("active", Number(el.dataset.sid)===sid);
  });
  fetchDbTools();
  refreshLog();
}

async function doFetch(url, opts){
  const r = await fetch(url, {headers: authHdrs(), ...(opts||{})});
  if(!r.ok){
    let t=""; try{t=await r.text()}catch(_){}
    throw new Error("HTTP "+r.status+": "+(t.slice(0,300)||r.statusText));
  }
  return r;
}

async function liveDiscover(){
  if(!currentSid){alert("未选中 Server");return}
  const tr = document.querySelector("#tools-tbl tbody tr"); if(tr && tr.querySelector(".empty")) tr.parentElement.innerHTML="";
  document.getElementById("tl-count").textContent="loading…";
  try{
    const r = await (await doFetch(API_BASE+"/api/mcp/servers/"+currentSid+"/discover-live")).json();
    renderTools(r.tools||[]);
    document.getElementById("tl-count").textContent = (r.tool_count||0)+" 个 · "+(r.latency_ms||0)+"ms · "+(r.ok?"OK":"ERR");
    if(!r.ok){alert("Discover 失败："+(r.reason||"未知原因"))}
  }catch(e){alert("discover-live 失败："+e.message)}
}

async function fetchDbTools(){
  if(!currentSid){document.getElementById("tl-count").textContent="未选 Server";return}
  document.getElementById("tl-count").textContent="loading…";
  try{
    const r = await (await doFetch(API_BASE+"/api/mcp/servers/"+currentSid+"/tools?page_size=200")).json();
    renderTools((r.items||[]).map(it=>({tool_name:it.tool_name, display_name:it.display_name, description:it.description, input_schema:it.input_schema||{}})), true);
    document.getElementById("tl-count").textContent = (r.total||0)+" 个（DB）";
  }catch(e){document.getElementById("tl-count").textContent="加载失败"}
}

function renderTools(list, fromDb){
  const tb = document.querySelector("#tools-tbl tbody");
  if(!list.length){tb.innerHTML = `<tr><td colspan="3" class="empty">${fromDb?"Server 未发现 DB 工具，先点击 Discover 导入":"Server 返回空 tools/list"}</td></tr>`;return}
  tb.innerHTML = list.map(t=>{
    const schema = t.input_schema||{};
    const props = (schema&&schema.properties)?Object.keys(schema.properties):[];
    const argsJson = props.length? Object.fromEntries(props.map(p=>[p, schema.properties[p].type==="integer"?0:schema.properties[p].type==="number"?0.0:schema.properties[p].type==="boolean"?false:""])) : {};
    return `<tr>
      <td><b>${esc(t.tool_name)}</b><br><span class="mono">${esc(t.display_name||t.tool_name)}</span></td>
      <td>${esc((t.description||"").slice(0,120))||"—"}
        ${props.length?`<div class="hint">args: ${esc(props.join(", "))}</div>`:""}
      </td>
      <td>
        <button class="btn sec" style="padding:4px 8px;font-size:12px"
          onclick='fillAndGo(${JSON.stringify(t.tool_name).replace(/'/g,"&#39;")}, ${JSON.stringify(j2(argsJson)).replace(/'/g,"&#39;")})'>调用</button>
      </td>
    </tr>`;
  }).join("");
}

function fillAndGo(name, argsText){
  document.getElementById("c-name").value = name;
  try{
    document.getElementById("c-args").value = argsText;
  }catch(_){}
  callTool();
}

async function callTool(){
  const tool_name = document.getElementById("c-name").value.trim();
  if(!tool_name){alert("请填写 tool_name");return}
  let args = {};
  try{ args = JSON.parse(document.getElementById("c-args").value||"{}") }
  catch(e){alert("args JSON 解析失败："+e.message);return}
  setStatus("RUNNING","—","—","—", "(调用中…)");
  const t0 = performance.now();
  try{
    const body = {server_id: currentSid, tool_name, args};
    const r = await (await doFetch(API_BASE+"/api/mcp/tools/test", {method:"POST", body: JSON.stringify(body)})).json();
    setStatus(r.status || (r.ok?"SUCCESS":"ERROR"),
      (r.latency_ms??Math.round(performance.now()-t0))+"ms",
      r.content_text||"—",
      r.error_message||"—",
      j2(r));
    refreshLog();
  }catch(e){setStatus("ERROR","—","—",e.message,String(e))}
}

async function rawRpcCall(){
  const method = document.getElementById("r-method").value.trim();
  if(!method){alert("请填写 JSON-RPC method（如 ping / tools/list / initialize）");return}
  let params = {};
  try{ params = JSON.parse(document.getElementById("c-args").value||"{}") }
  catch(e){alert("params JSON 解析失败："+e.message);return}
  setStatus("RUNNING","—","—","—", "(raw-rpc 调用中…)");
  try{
    const body = {method, params};
    const r = await (await doFetch(API_BASE+"/api/mcp/servers/"+currentSid+"/raw-rpc", {method:"POST", body: JSON.stringify(body)})).json();
    setStatus(r.ok?"SUCCESS":"ERROR",
      r.latency_ms+"ms",
      (typeof r.result==="string"?r.result.substring(0,120):"—"),
      (r.error?JSON.stringify(r.error).substring(0,200):"—"),
      j2(r));
  }catch(e){setStatus("ERROR","—","—",e.message,String(e))}
}

function setStatus(st, lat, text, err, raw){
  const el = document.getElementById("r-status");
  const cls = st==="RUNNING"?"run":(st==="SUCCESS"||st==="ok"||st==="OK"?"ok":"err");
  el.innerHTML = `<span class="badge ${cls}">${esc(st)}</span>`;
  document.getElementById("r-lat").textContent = lat;
  document.getElementById("r-text").textContent = text;
  document.getElementById("r-err").textContent = err;
  document.getElementById("r-raw").textContent = raw;
  tab("out");
}
function tab(name){
  document.querySelectorAll("#res-tabs div").forEach(d=>d.classList.toggle("a", d.dataset.tab===name));
  document.getElementById("r-raw").style.display = (name==="raw"?"block":"none");
  // out 模式下也显示（kv 固定）；raw tab 隐藏 kv？简单起见均保留
}

async function refreshLog(){
  const sid = currentSid || "";
  const q = new URLSearchParams({page_size:"20"});
  if(sid) q.set("server_id", sid);
  try{
    const r = await (await doFetch(API_BASE+"/api/mcp/call-log?"+q.toString())).json();
    renderLog(r.items||[]);
  }catch(e){}
}
function renderLog(items){
  const tb = document.querySelector("#log-tbl tbody");
  if(!items.length){tb.innerHTML=`<tr><td colspan="7" class="empty">暂无</td></tr>`;return}
  tb.innerHTML = items.map(it=>{
    const c = it.status==="SUCCESS"?"ok":"err";
    return `<tr>
      <td class="mono">${esc(String(it.created_at||"").slice(0,19))}</td>
      <td>${it.server_id}</td>
      <td><b>${esc(it.tool_name||"")}</b><br><span class="mono">#${esc(it.call_id||"")}</span></td>
      <td><span class="badge ${c}">${esc(it.status||"")}</span></td>
      <td>${it.latency_ms}ms</td>
      <td>${it.user_id||"—"}</td>
      <td class="mono" style="color:var(--err)">${esc((it.error_message||"").slice(0,80))||"—"}</td>
    </tr>`;
  }).join("");
}

async function scanAll(){
  const s = document.getElementById("scan-summary");
  s.textContent="扫描中…";
  try{
    const r = await (await doFetch(API_BASE+"/api/mcp/health-scan", {method:"POST"})).json();
    s.textContent = `OK ${r.ok_count} / ERR ${r.error_count}（共 ${r.scanned}，${r.elapsed_ms}ms）`;
    // 重新渲染卡片状态
    const host = document.getElementById("server-list");
    const oldHtml = host.innerHTML;
    (r.items||[]).forEach(it=>{
      const el = host.querySelector(`.svr-card[data-sid="${it.server_id}"] .svr-status`);
      if(!el) return;
      const cls = it.ok?"ok":"err";
      el.className = "svr-status "+cls;
      el.innerHTML = (it.ok?"● OK":"● ERR") + `<span>${it.latency_ms}ms${it.reason?" · "+it.reason.slice(0,30):""}</span>`;
    });
  }catch(e){s.textContent = "失败："+e.message}
}

// 初始化
(function init(){
  if(currentSid) selectServer(currentSid);
  else if(SERVERS.length) selectServer(SERVERS[0].id);
  refreshLog();
})();
</script>
</body>
</html>
"""

