# -*- coding: utf-8 -*-
"""P8 MCP：工具调用执行器（stdio / SSE 两种传输）。

关键设计（参考 experience 621000）：
  1. stdio：使用 asyncio.create_subprocess_exec（async 原生子进程，避免 Popen+thread 的 Windows 缓冲假死）；
     双向 pipe 通信，Content-Length: N 帧协议；绝不通过 HTTP/8000 假连接。
  2. SSE：优先 httpx，未装则 aiohttp；两者都缺失时降级为 TIMEOUT+清晰错误，不会崩溃。
  3. 每次调用都在 mcp_tool_call_log 写一条（含 ERROR/TIMEOUT），支持幂等 call_id。
  4. 所有网络/子进程调用都有超时控制：connect_timeout_ms + call_timeout_ms 默认 5s + 30s。
"""
from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from app.common.exceptions import AppException
from app.common.error_codes import SERIES_CODE_CONFLICT
from app.common.logging import logger
from app.database import execute_write, fetch_one, get_redis
from app.config import settings
from app.core.breaker import BreakerConfig, CircuitBreaker, CircuitOpenError
from app.core.cache import get_or_load

from . import description_reviewer, registry
from .schemas import MCPToolTestResp, ToolCallStatusEnum
from .retry_loop import (
    ToolRetryStateMachine, AttemptOutcome, RejectStore, MemRejectStore,
    build_manual_guide, ACTION_NORMAL, ACTION_REWRITE, ACTION_SWITCH,
)
# MCP-TRUTH 接线（修复 audit-rag #5 四模块死代码）：生产链路实际消费以下能力——
#   auth:           远程（sse/http）传输注入 OAuth/API-key 认证头（_remote_auth_headers）
#   reconnect:      stdio 健康检查建会话时自动指数退避重连（_stdio_health_via_pool）
#   isolation:      工具结果超限截断（_invoke_transport → _extract_mcp_content_text 后）
#   dynamic_update: discover_tools 后同步动态工具注册表并记录差异事件
# 各接线点在 init_mcp_capabilities or 各执行入口显式调用/引用，grep 均有生产调用方（非死代码）。
from . import auth as _mcp_auth
from . import reconnect as _mcp_reconnect
from . import isolation as _mcp_isolation
from . import dynamic_update as _mcp_dynamic_update


# ============================================================
# task33 per-server 熔断 + 只读缓存
# ============================================================
# 每 MCP server 一把熔断器：连续失败阈值=5，并流 30s（task33 GWT②）
_MCP_BREAKER_FAILURES = 5
_MCP_BREAKER_OPEN_S = 30.0
# 只读工具同参缓存 TTL（秒），task33 GWT③
_MCP_CACHE_TTL = 60
# 明显写语义的工具名前缀：跳过缓存（避免缓存非幂等副作用操作）
_WRITE_TOOL_PREFIXES = ("write_", "create_", "delete_", "update_", "send_", "broadcast_", "upload_")

# W-NEXT-2 步骤3：单次工具调用的执行上下文（供内置写类 handler 取权威 tenant_id/operator）。
# 由 call_tool / _default_attempt_executor 在入口 set；LLM 提供的同名字段仅作兜底，防越租户写入。
_EXEC_CONTEXT: contextvars.ContextVar[dict] = contextvars.ContextVar("mcp_exec_ctx", default={})

# ============================================================
# task-S1 全流程 HITL 护栏：高风险动作分类（对齐 Claude 解释→提议→同意→行动）
# ============================================================
# 执行命令类工具前缀（命令注入风险，强制过 Gate）
_HITL_EXEC_COMMAND_PREFIXES = ("run_", "exec_", "shell_", "bash_", "cmd_", "system_", "command_")
# 网络访问类工具（数据外泄/ SSRF 风险）；用子串匹配，但严禁匹配 web_search 等只读查询工具
_HITL_NETWORK_PREFIXES = ("fetch", "http", "download", "scrape", "crawl", "request", "webhook", "send_http", "url")
# 退款/资金类工具关键字（资金风险）
_HITL_REFUND_MARKERS = ("refund", "chargeback", "payback", "withdraw")


def _classify_hitl_action(tool_name: str) -> str | None:
    """将工具名分类为 HITL 动作类型（字符串，避免顶层依赖 hitl_gate 枚举）。

    返回：write_file | exec_command | network_access | refund | None（非高风险，免护栏）。

    W-NEXT-2 步骤1（T4-C3 根因修复）：**类别以 permission_gate 为单一事实源**——
    契约写类名是「实体_动词」（下划线前为实体、后为动词），而旧前缀表是
    「动词_实体」（create_/write_…）→ 契约写类 10 个全漏判 None、且被误判可缓存。
    现在先查 `permission_gate.is_write_class`（已注册实物 + 契约挂起类别都在类别映射中），
    **前缀判定仅作 permission_gate 未登记工具（开发机/第三方工具名）的兜底保留**。
    """
    n = (tool_name or "").strip().lower()
    # ① 单一事实源：permission_gate 类别（course_write / admin_write → 写类高风险）
    from app.ai.permission_gate import is_write_class

    if is_write_class(n):
        return "write_file"
    # ② 兜底：未登记工具名按语义前缀判定（原行为，仅对映射表外名字生效）
    if any(p in n for p in _HITL_NETWORK_PREFIXES):
        return "network_access"
    if any(p in n for p in _HITL_REFUND_MARKERS):
        return "refund"
    if any(n.startswith(p) for p in _HITL_EXEC_COMMAND_PREFIXES):
        return "exec_command"
    if any(n.startswith(p) for p in _WRITE_TOOL_PREFIXES):
        return "write_file"
    return None

_breaker_by_server: dict[int, CircuitBreaker] = {}


def _server_breaker(server_id: int) -> CircuitBreaker:
    """获取/创建 per-server 熔断器（连续 5 次失败 → 30s 快败）。"""
    b = _breaker_by_server.get(server_id)
    if b is None:
        b = CircuitBreaker(
            name=f"mcp-server-{server_id}",
            config=BreakerConfig(consecutive_failures=_MCP_BREAKER_FAILURES,
                                 open_duration=_MCP_BREAKER_OPEN_S),
        )
        _breaker_by_server[server_id] = b
    return b


def _is_cached_call(tool_name: str, args: dict[str, Any]) -> bool:
    """只读工具可走 60s 同参缓存；写类工具跳过（避免缓存非幂等副作用）。

    W-NEXT-2 步骤1（T4-C3 根因修复）：写类判定以 permission_gate 类别为准
    （`<实体>_<动词>` 契约名同样命中），前缀判定仅作未登记工具的兜底。
    """
    from app.ai.permission_gate import is_write_class

    lowered = (tool_name or "").strip().lower()
    if is_write_class(lowered):
        return False
    if any(lowered.startswith(p) for p in _WRITE_TOOL_PREFIXES):
        return False
    return True


def _permission_denied_resp(*, tool_name: str, role: str, call_id: str,
                            server_id: int = 0) -> "MCPToolTestResp":
    """写类工具越权拦截响应（ACI 信封三字段内嵌 content_text，**不落审计日志、不执行**）。

    W-NEXT-2 步骤2 纵深防御：executor 是所有工具执行路径的公共收口
    （流式 tool_calling / 六节点图子代理 call_tool_with_retry / langgraph tool_node），
    在此对**写类**工具做最后一次角色校验 —— 上层门（tool_calling / tool_node）漏掉的
    路径也不会真实执行写操作。只拦写类（course_write/admin_write）；未登记名不在此拦截
    （保持「找不到工具 → 404」既有语义，fail-closed 由上层门负责）。
    """
    from app.ai.permission_gate import build_denied_envelope

    env = build_denied_envelope(role, tool_name)
    logger.warning(f"[MCP] 权限门拒绝（executor 收口）: role={role} tool={tool_name} hint={env['action_hint']}")
    return MCPToolTestResp(
        status=ToolCallStatusEnum.ERROR,
        error_message=f"[{env['code']}] {env['message']}",
        latency_ms=0,
        call_id=call_id or f"mcp-denied-{uuid.uuid4().hex[:8]}",
        server_id=int(server_id or 0),
        tool_name=tool_name,
        content_text=json.dumps(env, ensure_ascii=False),
        rejection_limited=False,
    )


async def _deny_if_write_class(*, name: str | None, operator_user_id: int,
                              call_id: str, server_id: int = 0) -> "MCPToolTestResp | None":
    """写类工具角色校验（executor 收口）：越权 → ACI 信封响应；非写类/已放行 → None。

    W-NEXT-2 步骤2 纵深防御。⚠️ **必须在两处调用**：
      ① 调用方传入的名字（快速路径，覆盖未登记名的 deny）；
      ② registry 解析后的**真实工具名**（`call_tool(tool_id=N)` 不传 tool_name 时名字为空，
         只校验①会让校验被整体跳过 → 越权写操作直落 HITL；HITL_ENABLED=False 时真实执行）。
    独立复验（2026-09-16）实测该绕过口子真实存在，故补②。
    """
    n = str(name or "").strip().lower()
    if not n:
        return None
    from app.ai.permission_gate import gate_tool_call, is_write_class, resolve_role

    # 写类判定：注册期强属性优先（CR-WNEXT2-executor-gate-bypass 收口），名单兜底
    write_class = n in _BUILTIN_WRITE_CLASS_NAMES or is_write_class(n)
    if not write_class:
        return None
    role = await resolve_role(operator_user_id)
    if gate_tool_call(role, n).allowed:
        return None
    return _permission_denied_resp(
        tool_name=n, role=role, call_id=call_id or "", server_id=int(server_id or 0),
    )


def _mcp_cache_key(server_id: int, tool_name: str, args: dict[str, Any]) -> str:
    """同参缓存 key：server_id + tool_name + args 排序哈希。"""
    raw = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return f"mcp:tool:{server_id}:{tool_name}:{h}"


def _raise(http_status: int, message: str, code: int | None = None) -> AppException:
    """返回 AppException：业务码默认 = http_status*100。"""
    business_code = int(code if code is not None else http_status * 100)
    return AppException(code=business_code, message=message, http_status=int(http_status))


def _short(x: Any) -> str:
    if x is None:
        return "None"
    if isinstance(x, dict):
        err = x.get("error")
        return f"keys={sorted(list(x.keys()))[:8]} res={'T' if x.get('result') is not None else 'F'} err={err if err else ('T' if x.get('error') is not None else 'F')}"
    return str(x)[:200]


# ============================================================
# 可选 HTTP 客户端（httpx 优先；aiohttp 备选；都没有→报错但不阻塞）
# ============================================================
try:
    import httpx as _httpx  # type: ignore
except Exception:  # pragma: no cover
    _httpx = None  # type: ignore

try:
    import aiohttp as _aiohttp  # type: ignore
except Exception:  # pragma: no cover
    _aiohttp = None  # type: ignore


# ============================================================
# Helper 内部协议（帧读写：async 版本）
# ============================================================
def _frame_encode(payload: dict) -> bytes:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw


async def _frame_read(stream: asyncio.StreamReader, deadline: float) -> dict | None:
    """从 async StreamReader 按帧读。deadline = 绝对时间戳（time.time()），过期抛 TimeoutError。"""
    headers: dict[str, str] = {}
    # 1) Header lines
    while True:
        if time.time() > deadline:
            raise TimeoutError("stdio: 读取 header 超时")
        line_buf = bytearray()
        while True:
            if time.time() > deadline:
                raise TimeoutError("stdio: 读 header line 字节超时")
            try:
                ch = await asyncio.wait_for(stream.read(1), timeout=max(0.01, deadline - time.time()))
            except asyncio.TimeoutError as exc:
                raise TimeoutError("stdio: 读 header 字节超时(await)") from exc
            if not ch:
                await asyncio.sleep(0.005)
                continue
            if ch == b"\n":
                break
            if ch != b"\r":
                line_buf.extend(ch)
        line = bytes(line_buf).decode("utf-8", errors="replace").strip()
        if not line:
            break
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    content_length = int(headers.get("content-length", "0"))
    if content_length <= 0:
        return None
    body = bytearray()
    while len(body) < content_length:
        if time.time() > deadline:
            raise TimeoutError("stdio: 读 body 超时")
        need = content_length - len(body)
        try:
            chunk = await asyncio.wait_for(
                stream.read(need),
                timeout=max(0.01, deadline - time.time()),
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError("stdio: 读 body 字节超时(await)") from exc
        if not chunk:
            await asyncio.sleep(0.005)
            continue
        body.extend(chunk)
    try:
        return json.loads(bytes(body).decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"stdio: JSON decode fail: {exc}")


# ============================================================
# 1. stdio transport：async 原生子进程帧通信（彻底规避 Windows threading 假死）
# ============================================================
def _build_server_env(server: dict, extra_envs: dict[str, str] | None) -> dict[str, str]:
    env = os.environ.copy()
    envs_server = _safe_json(server.get("env_json") or "{}", dict)
    if isinstance(envs_server, dict):
        for k, v in envs_server.items():
            env[str(k)] = "" if v is None else str(v)
    if extra_envs:
        env.update({str(k): "" if v is None else str(v) for k, v in extra_envs.items()})
    # PYTHONUNBUFFERED：保证子进程 stdout 不缓存
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


async def _stdio_exchange_async(server: dict, requests: list[dict], timeout_sec: float,
                                ) -> list[dict | None]:
    """async 版本：用 create_subprocess_exec 拉起，返回顺序同 requests（notification 对应 None）。"""
    run_command = server.get("run_command")
    if not run_command:
        raise _raise(500, "stdio server 未配置 run_command")
    cmd: list[str] = [run_command]
    run_args = _safe_json(server.get("run_args_json") or "[]", list)
    if isinstance(run_args, list) and run_args:
        cmd.extend(str(a) for a in run_args)
    cwd = server.get("working_dir") or None
    if not cwd:
        try:
            cwd_default = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
            cwd = cwd_default
        except Exception:
            cwd = None
    env = _build_server_env(server, None)

    executable, *args_list = cmd
    start = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_exec(
            executable, *args_list,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd, env=env,
        )
    except NotImplementedError as exc:
        # SelectorEventLoop 不支持 subprocess；提示策略（实际上 main.py 顶层已设 Proactor，这里兜底）
        raise RuntimeError(
            f"create_subprocess_exec 失败：{exc}；请确保 Windows 下使用 WindowsProactorEventLoopPolicy "
            f"(cmd={cmd[:3]}... cwd={cwd})"
        ) from exc
    logger.debug(f"stdio Popen pid={proc.pid} 启动耗时 {time.perf_counter()-start:.3f}s")
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None

    results: dict[int | str, dict] = {}
    remaining = {i + 1: req for i, req in enumerate(requests) if req.get("method") not in ("notifications/initialized",)}
    deadline_ts = time.time() + timeout_sec
    exchange_error: str | None = None
    try:
        for idx, req in enumerate(requests, start=1):
            if req.get("id") is None:
                req["id"] = idx
            try:
                proc.stdin.write(_frame_encode(req))
                await proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError, OSError) as exc:
                raise RuntimeError(f"stdio 写入失败：{exc}") from exc
        while remaining and time.time() < deadline_ts:
            try:
                msg = await _frame_read(proc.stdout, deadline_ts)
            except TimeoutError:
                break
            except Exception as exc:
                raise RuntimeError(f"stdio 读帧失败：{exc}")
            if msg is None:
                continue
            rid = msg.get("id")
            if rid is None:
                continue
            results[rid] = msg
            if rid in remaining:
                del remaining[rid]
        # graceful shutdown
        try:
            proc.stdin.write(_frame_encode({"jsonrpc": "2.0", "id": 999_998, "method": "shutdown"}))
            await proc.stdin.drain()
            proc.stdin.write(_frame_encode({"jsonrpc": "2.0", "method": "notifications/initialized"}))
            await proc.stdin.drain()
        except Exception:
            pass
    except Exception as exc:
        exchange_error = f"{type(exc).__name__}: {exc}"[:512]
        raise
    finally:
        try:
            if proc.returncode is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        except Exception:
            pass
        # 如果结果为空（调试场景），尝试读取 stderr 给排查线索
        if not results:
            try:
                stderr_raw = await asyncio.wait_for(proc.stderr.read(), timeout=0.8)
                stderr_tail = stderr_raw.decode("utf-8", errors="replace")[:600]
            except Exception:
                stderr_tail = ""
            short_cmd = " ".join(cmd)[:200]
            clue = f"cmd=[{short_cmd}] cwd={cwd} returncode={proc.returncode}"
            if stderr_tail:
                clue += f" stderr={stderr_tail}"
            if exchange_error:
                clue += f" err={exchange_error}"
            raise RuntimeError(f"stdio 未收到任何响应帧：{clue}")
    resp_in_order: list[dict | None] = []
    for i, req in enumerate(requests, start=1):
        if req.get("method") in ("notifications/initialized",):
            resp_in_order.append(None)
            continue
        resp_in_order.append(results.get(i))
    return resp_in_order


# ============================================================
# 2. SSE / HTTP 传输（最小可用实现：POST JSON-RPC body）
# ============================================================
async def _http_request_jsonrpc(base_url: str, body: dict, *, headers: dict[str, str] | None,
                                timeout_connect_ms: int, timeout_total_ms: int) -> dict:
    timeout_s = max(0.2, timeout_total_ms / 1000.0)
    connect_s = max(0.1, min(5.0, timeout_connect_ms / 1000.0))
    if _httpx is not None:
        timeout_obj = _httpx.Timeout(timeout_s, connect=connect_s)
        async with _httpx.AsyncClient(timeout=timeout_obj, follow_redirects=True) as client:
            try:
                resp = await client.post(base_url, json=body, headers=headers or {})
            except Exception as exc:
                raise RuntimeError(f"httpx POST 失败：{exc}") from exc
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
            try:
                return resp.json()
            except Exception as exc:
                raise RuntimeError(f"HTTP 响应非 JSON：{exc}，body={resp.text[:500]}")
    if _aiohttp is not None:
        timeout_obj = _aiohttp.ClientTimeout(total=timeout_s, sock_connect=connect_s)
        async with _aiohttp.ClientSession(timeout=timeout_obj) as session:
            try:
                async with session.post(base_url, json=body, headers=headers or {}) as resp:
                    text = await resp.text()
                    if resp.status >= 400:
                        raise RuntimeError(f"HTTP {resp.status}: {text[:500]}")
                    try:
                        return json.loads(text)
                    except Exception as exc:
                        raise RuntimeError(f"HTTP 响应非 JSON：{exc}，body={text[:500]}")
            except AppException:
                raise
            except Exception as exc:
                raise RuntimeError(f"aiohttp 请求失败：{exc}") from exc
    raise _raise(501, "SSE/HTTP transport 需要安装 httpx 或 aiohttp（pip install httpx）")


# ============================================================
# 3. 对外统一入口：call_tool + health_check + discover
# ============================================================

# ============================================================
# task-S1 全流程 HITL 护栏接入 seam
# ============================================================
async def _run_hitl_seam(*, action_type: str, target: str, params: dict,
                         operator_user_id: int, tenant_id: str, trace_id: str,
                         server_id: int | None, call_id: str,
                         human_decision: bool | None, action_id: str,
                         server: dict | None = None,
                         store=None, reviewer_fn=None,
                         exec_override=None) -> "MCPToolTestResp | None":
    """高风险写工具执行前必过 HITL Gate（explain→propose→approve→execute）。

    调用方需先判定 settings.HITL_ENABLED。本函数假定应执行护栏。
    返回 MCPToolTestResp（pending/escalated/rejected/executed 映射）；无需护栏返回 None。
    hitl_gate 全惰性导入，避免 executor 顶层耦合 ai 子包。

    exec_override（W-NEXT-2 步骤3）：批准后的真实执行体注入点。内置工具（knowledge_import 等）
    无 mcp_server/tool 行、走 handler 而非传输层 —— 用 `_make_builtin_hitl_exec(name)` 注入，
    保证「批准 → 真执行」对内置工具同样成立（不落传输层 404）。
    """
    from app.ai.hitl_gate import (
        run_hitl_gate, HitlAction, HitlActionType, _default_hitl_store,
    )
    _AT_MAP = {
        "write_file": HitlActionType.WRITE_FILE,
        "exec_command": HitlActionType.EXEC_COMMAND,
        "network_access": HitlActionType.NETWORK_ACCESS,
        "refund": HitlActionType.REFUND,
    }
    at = _AT_MAP.get(action_type)
    if at is None:
        return None

    srv = server
    if srv is None and server_id is not None:
        srv = await fetch_one("SELECT * FROM mcp_server WHERE id=%s AND yn=1 LIMIT 1", (int(server_id),))

    def _make_exec():
        if exec_override is not None:
            return exec_override

        async def _exec(action: HitlAction):
            cid = f"mcp-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
            return await _execute_single_attempt(
                server=srv, tool_name=target, args=dict(params), call_id=cid,
                operator_user_id=operator_user_id, tenant_id=tenant_id, trace_id=trace_id,
            )
        return _exec

    store = store or _default_hitl_store()
    action = HitlAction(
        action_type=at, target=target, params=dict(params),
        operator=str(operator_user_id), action_id=action_id or "",
        server_id=int(server_id) if server_id is not None else None, trace_id=trace_id,
    )
    result = await run_hitl_gate(
        action, store=store, reviewer_fn=reviewer_fn,
        executor_fn=_make_exec(), human_decision=human_decision, trace_id=trace_id,
    )
    return _hitl_result_to_mcp(result, server_id=server_id, tool_name=target, call_id_prefix=call_id)


def _hitl_result_to_mcp(result, *, server_id, tool_name, call_id_prefix) -> "MCPToolTestResp":
    """HitlResult → MCPToolTestResp 映射（供调用方/UI 消费）。"""
    _ST = {
        "pending": ToolCallStatusEnum.SKIPPED,
        "approved": ToolCallStatusEnum.SKIPPED,
        "rejected": ToolCallStatusEnum.ERROR,
        "executed": ToolCallStatusEnum.SUCCESS,
        "escalated": ToolCallStatusEnum.ERROR,
    }
    _MSG = {
        "pending": "【HITL 待审批】高风险动作已挂起，等待人工/AI 审批。",
        "approved": "【HITL 已批准（待执行）】",
        "rejected": "【HITL 已拒绝】高风险动作未执行。",
        "escalated": "【HITL 升级】AI 审查拒绝，需管理员 force_approve 后方可执行。",
    }
    st = _ST.get(result.status, ToolCallStatusEnum.SKIPPED)
    msg = _MSG.get(result.status)
    rec = result.record or {}
    return MCPToolTestResp(
        status=st,
        error_message=msg if result.status != "executed" else None,
        latency_ms=0,
        call_id=f"{call_id_prefix or 'hitl'}-{result.action_id}",
        server_id=int(server_id) if server_id is not None else 0,
        tool_name=tool_name,
        content_text=msg,
        attempt=1,
        actions=[rec] if rec else [],
        manual_guide={
            "hitl_action_id": result.action_id,
            "status": result.status,
            "explain_text": result.explain_text,
            "propose_text": result.propose_text,
            "operator": rec.get("operator", ""),
            "trace_id": rec.get("trace_id", ""),
            "needs_admin": result.needs_admin,
            "ai_verdict": result.ai_verdict,
        },
        rejection_limited=False,
    )
async def call_tool(*,
                    operator_user_id: int,
                    tenant_id: str = "",
                    trace_id: str = "",
                    tool_id: int | None = None,
                    server_id: int | None = None,
                    tool_name: str | None = None,
                    args: dict[str, Any] | None = None,
                    call_id: str | None = None,
                    hitl_action_id: str | None = None,
                    hitl_decision: bool | None = None,
                    _hitl_store=None,
                    _hitl_reviewer=None,
                    ) -> MCPToolTestResp:
    args = args or {}
    _EXEC_CONTEXT.set({
        "operator_user_id": int(operator_user_id or 0),
        "tenant_id": str(tenant_id or ""),
        "trace_id": str(trace_id or ""),
        # AUTO20 T12 双保险注入（CR-WRITETOOLS-001 §1b P4）：hitl_confirmed 仅由服务端在
        # resume confirm 批准（hitl_decision=True）时置 True——LLM/args 无法伪造；
        # 高危 handler（course_create）首行校验此键，未确认 → 42201 拒（service 零调用）。
        "hitl_confirmed": bool(hitl_decision is True),
    })

    # W-NEXT-2 步骤3：内置工具优先解析（calculator/search_knowledge/knowledge_import 在
    # mcp_tool 表无行 → registry 解析必失败；内置 handler 才是它们的执行事实源）。
    _builtin_name = _resolve_builtin_name(tool_id, server_id, tool_name)

    # W-NEXT-2 步骤2 纵深防御（T4-C1）：executor 是流式 / 六节点图 / langgraph tool_node
    # 三条执行路径的公共收口 —— 写类工具在此再做一次角色校验。越权 → ACI 信封返回，
    # **零执行 / 不落审计 / 不进 HITL 审批队列**（未授权操作不应占用人工审批资源）。
    # ① 调用方传入名（含内置名与 tool_name 直传形态）
    _denied = await _deny_if_write_class(
        name=(_builtin_name or tool_name), operator_user_id=operator_user_id,
        call_id=call_id or "", server_id=int(server_id or 0),
    )
    if _denied is not None:
        return _denied

    # 内置工具：无 server / 无 mcp_tool 行 → 跳过 registry+server 解析，HITL 后直跑 handler
    if _builtin_name:
        if settings.HITL_ENABLED:
            _at = _classify_hitl_action(_builtin_name)
            if _at is not None:
                _gated = await _run_hitl_seam(
                    action_type=_at, target=_builtin_name, params=args,
                    operator_user_id=operator_user_id, tenant_id=tenant_id, trace_id=trace_id,
                    server_id=None, call_id=call_id,
                    human_decision=hitl_decision, action_id=hitl_action_id or "",
                    exec_override=_make_builtin_hitl_exec(
                        _builtin_name, operator_user_id=operator_user_id,
                        tenant_id=tenant_id, trace_id=trace_id,
                    ),
                )
                if _gated is not None:
                    return _gated
        return await _execute_builtin_attempt(
            tool_name=_builtin_name, args=args,
            call_id=call_id or f"mcp-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}",
            operator_user_id=operator_user_id, tenant_id=tenant_id, trace_id=trace_id,
        )

    tool_row = await registry.get_tool_by_ref(tool_id, server_id, tool_name)
    server_id_eff = int(tool_row["server_id"])
    tool_name_eff = str(tool_row["tool_name"])
    # ② registry 解析出的真实工具名再校验一次：堵 `tool_id=N`（不传 tool_name）时
    #    名字为空 → 校验被整体跳过的绕过口子（独立复验实测，见 _deny_if_write_class）。
    _denied = await _deny_if_write_class(
        name=tool_name_eff, operator_user_id=operator_user_id,
        call_id=call_id or "", server_id=server_id_eff,
    )
    if _denied is not None:
        return _denied
    server = await fetch_one("SELECT * FROM mcp_server WHERE id=%s AND yn=1 LIMIT 1", (server_id_eff,))
    if not server:
        raise _raise(404, "关联 server 已删除")
    if int(server.get("enabled") or 0) != 1:
        raise _raise(412, f"server_code={server.get('server_code')} 已禁用（enabled=0）")

    # task-S1 全流程 HITL 护栏：高风险写工具执行前必过 Gate（HITL_ENABLED 默认 False，AC5 安全）
    if settings.HITL_ENABLED:
        _at = _classify_hitl_action(tool_name_eff)
        if _at is not None:
            _gated = await _run_hitl_seam(
                action_type=_at, target=tool_name_eff, params=args,
                operator_user_id=operator_user_id, tenant_id=tenant_id, trace_id=trace_id,
                server_id=server_id_eff, call_id=call_id,
                human_decision=hitl_decision, action_id=hitl_action_id or "",
                server=server, store=_hitl_store, reviewer_fn=_hitl_reviewer,
            )
            if _gated is not None:
                return _gated

    call_id = call_id or f"mcp-{int(time.time()*1000)}-{uuid.uuid4().hex[:8]}"
    breaker = _server_breaker(server_id_eff)

    def _breaker_open_resp() -> MCPToolTestResp:
        """熔断快速失败响应（毫秒级返回，task33 GWT②）。"""
        return MCPToolTestResp(
            status=ToolCallStatusEnum.ERROR,
            error_message=f"server={server_id_eff} 熔断中（连续失败超阈值），快速失败",
            latency_ms=0, call_id=call_id,
            server_id=server_id_eff, tool_name=tool_name_eff, content_text=None,
        )

    async def _run_once() -> MCPToolTestResp:
        """真正执行一次传输调用 + 落审计日志 + 健康回写 + 熔断结果上报。

        委托给模块级 `_execute_single_attempt`（task-T1 抽取的单步核心，行为不变，AC5 安全）。
        """
        return await _execute_single_attempt(
            server=server, tool_name=tool_name_eff, args=args, call_id=call_id,
            operator_user_id=operator_user_id, tenant_id=tenant_id, trace_id=trace_id,
        )

    async def _run_once_guarded() -> MCPToolTestResp:
        """先过熔断闸门，再执行；OPEN 且未到 open_duration 时快速失败（毫秒级返回）。"""
        try:
            await breaker.check()
        except CircuitOpenError:
            logger.warning(f"[MCP] server={server_id_eff} 熔断中，快速失败 {tool_name_eff}")
            return _breaker_open_resp()
        return await _run_once()

    async def _run_once_cached() -> MCPToolTestResp:
        """缓存 loader：先过熔断闸门（熔断异常向外抛，避免把降级结果写进缓存）。"""
        await breaker.check()
        return await _run_once()

    # GWT③：同参只读工具 60s 内命中缓存
    if _is_cached_call(tool_name_eff, args):
        key = _mcp_cache_key(server_id_eff, tool_name_eff, args)
        try:
            data = await get_or_load(
                key,
                lambda: _run_once_cached().model_dump(mode="json"),
                ttl=_MCP_CACHE_TTL,
            )
            return MCPToolTestResp.model_validate(data)
        except CircuitOpenError:
            return _breaker_open_resp()
        except Exception:
            logger.warning(f"[MCP] 缓存路径异常，直通执行: {tool_name_eff}")
            return await _run_once_guarded()

    return await _run_once_guarded()


# ============================================================
# task-T1 工具调用闭环：单步核心 + 换参/换工具/熔断/人工指南编排
# ============================================================
async def _execute_single_attempt(*, server: dict, tool_name: str, args: dict,
                                  call_id: str, operator_user_id: int, tenant_id: str,
                                  trace_id: str) -> MCPToolTestResp:
    """单次工具执行核心（调用方决定工具/参数/是否重试）。

    含：per-server 熔断闸门 + 传输调用 + 审计落库 + 健康回写 + 熔断结果上报。
    task33 行为完全保留（连续 5 失败 30s 熔断 / 审计日志 / 健康回写）。
    """
    server_id_eff = int(server.get("id") or server.get("server_id") or 0)
    breaker = _server_breaker(server_id_eff)
    try:
        await breaker.check()
    except CircuitOpenError:
        logger.warning(f"[MCP] server={server_id_eff} 熔断中，快速失败 {tool_name}")
        return MCPToolTestResp(
            status=ToolCallStatusEnum.ERROR,
            error_message=f"server={server_id_eff} 熔断中（连续失败超阈值），快速失败",
            latency_ms=0, call_id=call_id,
            server_id=server_id_eff, tool_name=tool_name, content_text=None,
        )
    t0 = time.perf_counter()
    status_eff, error_message, result_parsed, content_text = await _invoke_transport(
        server, tool_name, args, call_id)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    await _write_call_log(
        call_id=call_id, server_id=server_id_eff, tool_name=tool_name,
        args=args, result=result_parsed, content_text=content_text,
        status=status_eff, latency_ms=latency_ms,
        user_id=operator_user_id, tenant_id=tenant_id, trace_id=trace_id,
        error_message=error_message,
    )
    try:
        await registry.write_server_health(
            server_id_eff,
            ok=(status_eff == ToolCallStatusEnum.SUCCESS),
            last_error=None if status_eff == ToolCallStatusEnum.SUCCESS else error_message,
        )
    except Exception:
        logger.debug("写 MCP server health 失败，忽略")
    try:
        if status_eff == ToolCallStatusEnum.SUCCESS:
            await breaker.record_success()
        else:
            await breaker.record_failure()
    except Exception:
        logger.debug("上报熔断结果失败，忽略")
    return MCPToolTestResp(
        status=status_eff, result=result_parsed, error_message=error_message,
        latency_ms=latency_ms, call_id=call_id,
        server_id=server_id_eff, tool_name=tool_name,
        content_text=content_text,
    )


# ============================================================
# task-T1-②：内置/本地工具注册表（fallback 备用工具真实落地）
# ------------------------------------------------------------
# 批判：TOOL_FALLBACK_MAP 的 calculator/search_knowledge 此前只存在于决策前缀 spec，
# 未注册为可解析工具 → 第 3 步 switch_tool 命中后 get_tool_by_ref(None,None,name) 直接 400，
# 闭环只能「自然落到人工指南」。本段把它们注册为内置本地工具，命中即真实执行，
# 不再退化为人工指南（满足验收：switch_tool 命中真实注册工具）。
#   - calculator：本地真算四则；
#   - search_knowledge：接子代理/降级检索（后端可注入，缺省回退确定性降级结果）。
_BUILTIN_TOOL_HANDLERS: dict = {}

# CR-WNEXT2-executor-gate-bypass（登记残留）收口：写类从「名单驱动」升级为「注册期强属性」。
# 未来新增写类内置工具时必须在 register_builtin_tool(..., write_class=True) 显式声明；
# 名单（permission_gate.TOOL_CLASS_MAP）仅作未登记名的兜底。
_BUILTIN_WRITE_CLASS_NAMES: set[str] = set()


def register_builtin_tool(name: str, handler, *, write_class: bool = False) -> None:
    """注册一个内置本地工具处理器（handler: async (args) -> str）。

    write_class=True 表示该工具属写类（仅 admin 放行 + HITL 分级）——
    注册期强属性，与 permission_gate.TOOL_CLASS_MAP 名单互为补充（CR-WNEXT2-executor-gate-bypass）。
    """
    _BUILTIN_TOOL_HANDLERS[name] = handler
    if write_class:
        _BUILTIN_WRITE_CLASS_NAMES.add(name)
    else:
        _BUILTIN_WRITE_CLASS_NAMES.discard(name)


def _resolve_builtin_name(tool_id: int | None, server_id: int | None, tool_name: str | None) -> str:
    """内置工具解析（W-NEXT-2 步骤3）：按名字命中内置注册表，使内置工具**可经 HTTP 触达**。

    内置工具（calculator/search_knowledge/knowledge_import）在 mcp_tool 表**无行**，
    `registry.get_tool_by_ref` 对它们必然失败；内置 handler 才是其执行事实源。

    优先级规则：
      1) 指定了 tool_id → 一律走 registry（tool_id 是 DB 行的显式主键，不得被名字覆盖）；
      2) 否则按 tool_name 命中内置注册表（允许同时带 server_id —— `POST /api/mcp/tools/test`
         的请求体契约要求 tool_id 或 (server_id, tool_name) 二选一，若要求 server_id 为空则
         内置工具在 HTTP 上永远不可达 = 未真正上线）。
    当前内置名与 DB mcp_tool 名无交集（DB: add/echo/list_alphabet/ping/sse_health），
    由 tests/test_permission_gate.py 的注册面双向对账守住。
    """
    # SURFACED-1 防御：内置工具 sentinel 为 tool_id=0（builtin 在 mcp_tool 表无行）。
    # 若调用方仅传 tool_id=0 而不传 tool_name，旧逻辑 `tool_id or not tool_name → return ""`
    # 会静默跳过内置分支、落到 registry 解析 tool_id=0 抛「必须提供 tool_id 或 server_id+tool_name」，
    # 表现为 admin confirm 后写类工具零落库（HITL-FIX 批判实锤）。此处 fail-fast：明确报错，
    # 不让上层静默吞。仅当 tool_id==0（内置哨兵）且缺 tool_name 时触发；真实 DB 工具 tool_id>0
    # 或按 tool_name 直传的非内置工具不受影响。
    if tool_id == 0 and not tool_name:
        raise AppException(
            code=42200,
            message="内置工具（tool_id=0）必须传 tool_name=<工具名>，不能仅传 tool_id",
            http_status=422,
        )
    if tool_id or not tool_name:
        return ""
    n = str(tool_name).strip().lower()
    return n if n in _BUILTIN_TOOL_HANDLERS else ""


# ============================================================
# TA7 D1（P0）：内置工具「业务失败」不得映射 SUCCESS（凭据语义真化）
# ============================================================
# 实测缺陷（TA7 D1，真实 HTTP + DB 双证）：`_favorite_add_handler` 对**业务失败**
# （课程不存在 → `{"ok": false, "code": "40400", ...}`）是**返回结构化 JSON**而非抛异常，
# 而内置执行路径此前只看「handler 有没有抛」→ 一律映射 `status=SUCCESS`：
#   · mcp_tool_call_log.status = 'SUCCESS'（result_json 里却明写 ok:false / 40400）
#   · SSE `mcp_tool_calls[].status = "success"`
#   → receipt_guard 判「有 success 凭据」→ 写类护栏**永不触发**，而「AI 说做了但实际没做」
#     恰是护栏存在的唯一理由（TA6 之前黄条能触发只是"工具执行不了"的副产品）。
#
# 语义铁律：调用日志/SSE 的 status 必须如实反映**业务结果**，而不是「handler 是否抛异常」。
# 判定口径（保守，只认两种显式形态，避免误伤其他 handler 返回体）：
#   1) JSON 对象含 `ok` 且为 False → 业务失败；
#   2) 含 `code` 且不是成功码（"0"/"ok"/"success"/"200"）→ 业务失败。
# 反例保护（不得误判为失败）：calculator 返回 `{"result":…}`、search_knowledge 返回
# `{"results":…,"degraded":…}`、knowledge_import 返回 `{"status":…}` —— 均无 `ok`/`code` 键。
_BUILTIN_SUCCESS_CODES = {"0", "ok", "success", "200"}


def _builtin_business_failure(content_text: str | None) -> tuple[bool, str | None]:
    """判定内置 handler 返回体是否为「业务失败」。返回 (is_failure, 说明文本)。

    非 JSON / 非对象 → 不是业务失败（保持既有 SUCCESS 语义，零行为变化）。
    """
    raw = str(content_text or "").strip()
    if not raw or not raw.startswith("{"):
        return False, None
    try:
        obj = json.loads(raw)
    except Exception:
        return False, None
    if not isinstance(obj, dict):
        return False, None
    code = obj.get("code")
    code_s = "" if code is None else str(code).strip().lower()
    is_fail = obj.get("ok") is False or (code is not None and code_s not in _BUILTIN_SUCCESS_CODES)
    if not is_fail:
        return False, None
    msg = str(obj.get("message") or "").strip()
    detail = f"[{code_s or 'business_error'}] {msg}" if msg else f"[{code_s or 'business_error'}] 工具业务失败"
    return True, detail[:1024]


async def _execute_builtin_attempt(*, tool_name: str, args: dict, call_id: str,
                                    operator_user_id: int = 0, tenant_id: str = "",
                                    trace_id: str = "") -> "MCPToolTestResp":
    """执行一次内置工具 handler → MCPToolTestResp。

    内置工具无 mcp_server/mcp_tool 行，故 server_id=0。
    W-NEXT-MCP-001 步骤2（P0-②）：内置工具执行结果**落 mcp_tool_call_log 审计行**
    （与远程工具路径统一，杜绝 knowledge_import 写类无痕可查、权限门形同虚设）。
    脱敏在公共落库入口 `_write_call_log` 做（P0-③），本处只一层调用、不重复。
    落库失败（DB 抖动/不可用）不阻断主链路 —— `_write_call_log` 内部已 try/except 兜底。
    """
    handler = _BUILTIN_TOOL_HANDLERS.get(tool_name)
    t0 = time.perf_counter()
    if handler is None:
        resp = MCPToolTestResp(
            status=ToolCallStatusEnum.ERROR, error_message=f"未注册的内置工具 {tool_name}",
            latency_ms=0, call_id=call_id, server_id=0, tool_name=tool_name, content_text=None,
        )
    else:
        try:
            content = await handler(dict(args))
            # TA7 D1：业务失败（ok:false / 非 0 code）**不得**映射 SUCCESS —— 否则
            # 调用日志与 SSE 会给出假的「成功凭据」，receipt_guard 零触发。此处保留
            # content_text 原样回传（结构化 need_clarify/candidates 仍给模型用），
            # 只把 status/error_message 改成如实反映业务结果。
            _biz_fail, _biz_msg = _builtin_business_failure(content)
            resp = MCPToolTestResp(
                status=(ToolCallStatusEnum.ERROR if _biz_fail else ToolCallStatusEnum.SUCCESS),
                latency_ms=int((time.perf_counter() - t0) * 1000),
                call_id=call_id, server_id=0, tool_name=tool_name, content_text=str(content),
                error_message=(_biz_msg if _biz_fail else None),
            )
        except Exception as exc:  # noqa: BLE001 — 内置执行失败按 ERROR 返回，不冒泡打崩调用方
            logger.warning(f"[MCP] 内置工具 {tool_name} 执行失败: {type(exc).__name__}: {exc}")
            resp = MCPToolTestResp(
                status=ToolCallStatusEnum.ERROR, error_message=f"内置工具 {tool_name} 执行失败：{exc}",
                latency_ms=int((time.perf_counter() - t0) * 1000), call_id=call_id, server_id=0,
                tool_name=tool_name, content_text=None,
            )
    # P0-②：内置工具执行结果落审计行（失败也不阻断主链路，详见函数注释）
    try:
        await _write_call_log(
            call_id=call_id, server_id=0, tool_name=tool_name,
            args=args, result=None, content_text=resp.content_text,
            status=resp.status, latency_ms=resp.latency_ms,
            user_id=operator_user_id, tenant_id=tenant_id, trace_id=trace_id,
            error_message=resp.error_message,
        )
    except Exception:  # noqa: BLE001 — 审计落库失败绝不影响工具返回
        logger.debug("[MCP] 内置工具审计落库失败，忽略（不阻断主链路）")
    return resp


def _make_builtin_hitl_exec(tool_name: str, *, operator_user_id: int = 0,
                            tenant_id: str = "", trace_id: str = ""):
    """HITL Gate 批准后的执行体（内置工具版）：approve → 真实跑内置 handler（非传输层）。

    W-NEXT-MCP-001 步骤2：透传 operator_user_id/tenant_id/trace_id，使 HITL 批准后的
    内置工具执行同样落 mcp_tool_call_log（含 operator_user_id，审计可溯源）。
    """
    async def _exec(action) -> "MCPToolTestResp":
        cid = f"mcp-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
        return await _execute_builtin_attempt(
            tool_name=tool_name, args=dict(getattr(action, "params", None) or {}), call_id=cid,
            operator_user_id=operator_user_id, tenant_id=tenant_id, trace_id=trace_id,
        )

    return _exec


# search_knowledge 后端可注入（子代理检索 / 向量检索），缺省降级
_SEARCH_KNOWLEDGE_BACKEND = None


def set_search_knowledge_backend(fn) -> None:
    """注入 search_knowledge 内置工具的真实检索后端（MCP-TRUTH 接线，修复 audit-rag #6 空壳）。

    fn: async (query: str) -> str（JSON 序列化结果）。缺省为确定性降级；
    生产由 `init_mcp_capabilities()` 注入 `_default_search_knowledge_backend`（真实三通道检索）。
    """
    global _SEARCH_KNOWLEDGE_BACKEND
    _SEARCH_KNOWLEDGE_BACKEND = fn


async def _default_search_knowledge_backend(query: str) -> str:
    """真实检索后端（默认）：接通 `retrieve_three_channel` 三通道 → JSON 串。

    与 ai/graph.py::_build_tool_services.search_knowledge 对齐：
      - 参数统一读 SIXNODE_*（与图内链路同一来源，防检索口径漂移）；
      - 用户上下文取 `_EXEC_CONTEXT`（调用方注入的 operator_user_id），role=None 走学员租户范围；
      - 检索产物结构与 graph 侧一致（docs[model_dump] + graph_entities[model_dump]）。

    仍遵守降级纪律：真实检索异常 → 返回 degraded=True + 真实 reason（不假报空结果）。
    """
    ctx = _EXEC_CONTEXT.get() or {}
    user_id = int(ctx.get("operator_user_id") or 0)
    from app.chat.retriever import retrieve_three_channel

    params = {
        "use_hyde": bool(getattr(settings, "SIXNODE_USE_HYDE", True)),
        "enable_graph": True,
        "top_k": int(getattr(settings, "SIXNODE_TOP_K", 12)),
        "final_max_k": int(getattr(settings, "SIXNODE_FINAL_MAX_K", 5)),
        "cutoff_drop_ratio": float(getattr(settings, "SIXNODE_CUTOFF_DROP_RATIO", 0.40)),
    }
    bundle = await retrieve_three_channel(
        query, user_id=user_id, role=None,
        use_hyde=params["use_hyde"], enable_graph=params["enable_graph"],
        top_k=params["top_k"], final_max_k=params["final_max_k"],
        cutoff_drop_ratio=params["cutoff_drop_ratio"],
    )
    docs = [d.model_dump() for d in bundle.docs]
    graph_entities = [g.model_dump() for g in bundle.graph_entities]
    return json.dumps({
        "results": docs,
        "graph_entities": graph_entities,
        "retrieved_count": int(bundle.raw_retrieved_count or 0),
        "degraded": bool(bundle.degraded_reason),
        "degraded_reason": bundle.degraded_reason,
        "query": query,
        "note": "真实三通道检索（retrieve_three_channel）",
    }, ensure_ascii=False)


# ============================================================
# MCP-TRUTH 接线（修复 audit-rag #5 四模块死代码 / #6 search_knowledge 空壳）
# ------------------------------------------------------------
# 这四段让 auth/reconnect/isolation/dynamic_update 从「grep 仅定义文件自身引用」的死代码
# 变为「生产链路有真实调用方」的接线能力，供 capability_audit 对账。所有接线均保持默认
# 零行为变化（auth 需 server 配 auth_json、reconnect 只在建会话失败重试、isolation 超限才截断、
# dynamic_update 只记录差异日志），不误伤既有调用链。
# ============================================================

# ---- auth：远程传输注入 OAuth/API-key 认证头（HTTP 透传 http_headers_json 之上叠加）----
def _remote_auth_headers(server: dict) -> dict[str, str]:
    """把 server 的认证配置（auth_json，可存放 OAuth/API-key 凭据）转成注入请求的认证头。

    在 `http_headers_json`（显式头，优先级更高）基础上，用 `auth.build_auth_headers` 叠加
    认证头。server 无 auth_json 或 auth_type=none → 原样返回 http_headers（零变化）。
    这是 `app/mcp/auth.py` 在生产链路的真实调用方（修复 #5 auth 死代码）。
    """
    headers = _safe_json(server.get("http_headers_json") or "{}", dict)
    headers = dict(headers) if isinstance(headers, dict) else {}
    auth_cfg = _safe_json(server.get("auth_json") or "{}", dict)
    if not isinstance(auth_cfg, dict):
        return headers
    if not str(auth_cfg.get("auth_type") or "none").strip() or str(auth_cfg.get("auth_type") or "") == "none":
        return headers
    known = {
        k: auth_cfg[k] for k in _mcp_auth.AuthConfig.__dataclass_fields__
        if k in auth_cfg and auth_cfg[k] is not None
    }
    cfg = _mcp_auth.AuthConfig(**known)
    merged = _mcp_auth.build_auth_headers(cfg)
    headers.update(merged if isinstance(merged, dict) else {})
    return headers


# ---- isolation：工具结果超限截断（避免单工具巨量返回撑爆上下文）----
def _truncate_result_text(content_text: str | None) -> tuple[str | None, bool]:
    """对工具返回文本应用 per-tool 结果大小限制（`isolation.truncate_tool_result`）。

    超限截断并追加截断标记；未超限原样返回。这是 `app/mcp/isolation.py` 在生产链路的
    真实调用方（修复 #5 isolation 死代码——截断能力接线；作用域隔离属超 scope，见报告裁决）。
    """
    if content_text is None:
        return content_text, False
    text, truncated = _mcp_isolation.truncate_tool_result(content_text)
    return (text, truncated)


# ---- dynamic_update：discover 后同步动态工具注册表并记录差异事件----
_DYN_REGISTRY = _mcp_dynamic_update.DynamicToolRegistry()


def _sync_dynamic_tools(server_id: int, tools: list[dict]) -> dict:
    """把 tools/list 结果灌进动态工具注册表，返回差异事件（added/removed/updated）。

    server 工具增减无需重启会话即可感知（供 admin discover 后观测）。这是
    `app/mcp/dynamic_update.py` 在生产链路的真实调用方（修复 #5 dynamic_update 死代码）。
    """
    ev = _DYN_REGISTRY.notify_tools_changed(int(server_id), tools or [])
    if ev.added or ev.removed or ev.updated:
        logger.info(
            f"[MCP] 动态工具变更 server_id={int(server_id)} "
            f"added={ev.added} removed={ev.removed} updated={ev.updated}"
        )
    return {"added": ev.added, "removed": ev.removed, "updated": ev.updated}


# ---- reconnect：stdio 健康检查建会话时自动指数退避重连----
def _make_hc_reconnect_connect(server: dict):
    """构造 reconnect.with_reconnect 的连接体：建会话失败（create_err 非空）→ 视为连接失败。

    由 `with_reconnect` 在失败时按指数退避重试（限 max_retries 次、延迟上限 2s，保持健康检查
    低扰乱）；成功后返回会话 id。这是 `app/mcp/reconnect.py` 在生产链路的真实调用方
    （修复 #5 reconnect 死代码）。
    """

    async def _connect():
        session_id, create_err = await _hc_session_acquire(server)
        if create_err:
            raise RuntimeError(f"stdio 建会话失败待重连: {create_err}")
        return session_id

    return _connect


async def init_mcp_capabilities() -> None:
    """MCP 生产能力初始化（幂等，可多次调用）。

    由应用启动（main.lifespan）调用；当前唯一动作是给 search_knowledge 内置工具注入真实
    检索后端（`_default_search_knowledge_backend`），修复 audit-rag #6 空壳——此前该注入点
    全仓零调用，MCP 工具永远返回「知识检索后端未接入」降级结果。
    """
    if _SEARCH_KNOWLEDGE_BACKEND is None:
        set_search_knowledge_backend(_default_search_knowledge_backend)
        logger.info("[MCP] search_knowledge 后端已接线：真实三通道检索（retrieve_three_channel）")


async def _calculator_handler(args: dict) -> str:
    a = float(args.get("a"))
    b = float(args.get("b"))
    op = str(args.get("op", "add")).lower()
    if op == "add":
        val = a + b
    elif op == "sub":
        val = a - b
    elif op == "mul":
        val = a * b
    elif op == "div":
        if b == 0:
            raise ZeroDivisionError("div by zero")
        val = a / b
    elif op == "mod":
        val = a % b
    else:
        raise ValueError(f"不支持的 op={op}")
    return json.dumps({"result": val, "tool": "calculator", "op": op}, ensure_ascii=False)


async def _search_knowledge_handler(args: dict) -> str:
    q = str(args.get("q") or args.get("query") or "")
    if _SEARCH_KNOWLEDGE_BACKEND is not None:
        try:
            return await _SEARCH_KNOWLEDGE_BACKEND(q)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[builtin] search_knowledge 后端失败，降级: {type(exc).__name__}: {exc}")
    return json.dumps(
        {"results": [], "degraded": True, "query": q,
         "note": "知识检索后端未接入，已降级返回；可通过 set_search_knowledge_backend 注入子代理/向量检索"},
        ensure_ascii=False,
    )


# W-NEXT-2 步骤3：knowledge_import 写类内置工具（admin_write）
_KNOWLEDGE_IMPORT_TASK_TYPE = "agent_import"
_KNOWLEDGE_IMPORT_VISIBILITIES = ("private", "public")


def _knowledge_upload_root() -> Path:
    """knowledge_import 允许读写本地文件的唯一根目录（与 `/api/knowledge/upload` 落盘
    `knowledge_uploads` 一致）。所有 local_path 必须先 resolve 后仍落在本根内才放行。"""
    return (Path(settings.DATA_DIR) / "knowledge_uploads").resolve()


def _is_safe_knowledge_local_path(lp: str, root: Path) -> bool:
    """路径穿越防护（Mimosa HIGH 硬门1，对齐 `_safe_upload_id` 先例 R03）：
    resolve()（跟随符号链接）后仍 is_relative_to(允许根) 且是常规文件才放行。
    拒绝绝对路径逃逸、`..`、符号链接逃出根、目录等——不被接受即零读取/零删除副作用。"""
    if not lp:
        return False
    try:
        resolved = Path(lp).resolve()
    except (OSError, RuntimeError):
        return False
    return resolved.is_relative_to(root) and resolved.is_file()


async def _knowledge_import_handler(args: dict) -> str:
    """知识库导入（写类，admin_write）——包装既有真写入口 `task_store.create_task`。

    单一执行事实源：不新增 SQL、不碰 Milvus/loader.py，只调用既有 `knowledge_import_task`
    写入口（MySQL 真相源 + Redis 缓存双写）。

    行为边界（G6 幻觉检测同源：回执如实反映真实发生的写，不谎报"已导入完成"）：
      1) 校验 `source_files` 非空（list[dict|str]）+ `visibility` ∈ {private, public}；
      2) tenant_id **以执行上下文为权威**（调用方注入），LLM 传入值仅作兜底 → 防越租户写入；
      3) 落任务行（status=pending）→ 回执含 task_id/status/tenant_id/visibility/files；
      4) 仅当条目全部带真实存在的本地路径时，才后台拉起既有导入管道（pipeline_started=true）；
         否则仅登记任务（文件尚未落地），回执标注 pipeline_started=false 与等待说明。
    """
    ctx = _EXEC_CONTEXT.get() or {}
    src = args.get("source_files") or args.get("files") or []
    if isinstance(src, str):
        src = [src]
    if not isinstance(src, list) or not src:
        raise ValueError("knowledge_import 缺少 source_files（需非空列表，元素为 {file_name, local_path|object_key}）")
    visibility = str(args.get("visibility") or "private").strip().lower()
    if visibility not in _KNOWLEDGE_IMPORT_VISIBILITIES:
        raise ValueError(f"visibility 非法：{visibility}（仅允许 private/public）")

    meta: list[dict] = []
    local_paths: list[str] = []
    upload_root = _knowledge_upload_root()
    for item in src:
        if isinstance(item, str):
            meta.append({"object_key": None, "file_name": item, "file_size": 0, "content_type": ""})
            if _is_safe_knowledge_local_path(item, upload_root):
                local_paths.append(item)
            continue
        if not isinstance(item, dict):
            raise ValueError("source_files 条目必须是 dict 或 str")
        key = item.get("object_key") or item.get("key")
        meta.append({
            "object_key": key,
            "file_name": str(item.get("file_name") or item.get("name") or key or "unnamed"),
            "file_size": int(item.get("file_size") or 0),
            "content_type": str(item.get("content_type") or ""),
        })
        lp = str(item.get("local_path") or item.get("path") or "")
        if lp and _is_safe_knowledge_local_path(lp, upload_root):
            local_paths.append(lp)

    tenant_id = str(ctx.get("tenant_id") or args.get("tenant_id") or "_default")
    task_id = f"task_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    from app.knowledge import task_store

    task = await task_store.create_task(
        task_id=task_id,
        task_type=_KNOWLEDGE_IMPORT_TASK_TYPE,
        tenant_id=tenant_id,
        visibility=visibility,
        source_files_meta=meta,
    )

    pipeline_started = False
    if len(local_paths) == len(meta):
        try:
            from app.knowledge.models import Visibility
            from app.knowledge.routers.upload import _process_import

            asyncio.create_task(_process_import(
                task_id=task_id,
                local_paths=local_paths,
                original_names=[m["file_name"] for m in meta],
                tenant_id=tenant_id,
                visibility=Visibility(visibility),
                task_type=_KNOWLEDGE_IMPORT_TASK_TYPE,
                source_files_meta=meta,
            ))
            pipeline_started = True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[builtin] knowledge_import 管道拉起失败（任务已登记，状态 pending）: {type(exc).__name__}: {exc}")

    return json.dumps({
        "task_id": task["task_id"],
        "status": task["status"],
        "task_type": task["task_type"],
        "tenant_id": task["tenant_id"],
        "visibility": task["visibility"],
        "files": len(meta),
        "pipeline_started": pipeline_started,
        "operator_user_id": ctx.get("operator_user_id"),
        "created_at": task["created_at"],
        "note": ("导入任务已登记，后台 parse→chunk→embed→load 管道已启动" if pipeline_started
                 else "导入任务已登记（status=pending），文件尚未落地，管道未启动"),
    }, ensure_ascii=False)


# ============================================================
# W-NEXT-WRITE1（CR-WRITETOOLS-001 第一批，用户 P1-P6 裁定 2026-09-20）
# favorite_add —— 首个 user_write（本人低危写）内置工具
# ============================================================
_FAVORITE_ADD_SOURCE = "ai_chat"


async def _favorite_add_handler(args: dict) -> str:
    """收藏课程系列（user_write：本人收藏，P1 矩阵 student/teacher/admin=allow、manager=deny）。

    单一执行事实源：直调既有 `market.service.add_favorite`（服务端幂等：已收藏返回原记录、
    软删重收藏激活、未收藏新建）。user_id 以执行上下文为权威（_EXEC_CONTEXT 服务端注入），
    **不从 args 取** —— 伪造他人收藏在结构上不可达。

    参数（exact-pin 语义，多余键一律拒）——TA6 起支持两种寻址方式，二者互斥：
      · `series_id`(int)   —— 直传路径（保留，向后兼容）；
      · `course_name`(str) —— 按课程名解析（用户零 ID 输入）：服务端精确/LIKE 解析 DB，
                              唯一命中则直接收藏；多命中返回候选列表让模型追问一次
                              （**绝不猜**）；整串零命中时 TA7 D2 会退化为"最接近候选"
                              （status=fuzzy，仅建议、一律 need_clarify）；彻底零命中如实回传。
    两者都不传（或同时传）→ 拒。
    """
    # ① 参数精确校验（先于身份校验：非法参数零副作用）
    has_id = "series_id" in args and args.get("series_id") is not None
    has_name = "course_name" in args and str(args.get("course_name") or "").strip()
    extra = set(args) - {"series_id", "course_name"}
    if extra:
        raise ValueError(
            f"favorite_add 不接受多余参数：{sorted(extra)}（仅 series_id 或 course_name）")
    if has_id and has_name:
        raise ValueError("favorite_add 的 series_id 与 course_name 互斥（二选一，不得同时传）")
    if not has_id and not has_name:
        raise ValueError("favorite_add 缺少参数：需 course_name（课程名，推荐）或 series_id（int，课程系列 ID）")

    sid: int
    if has_id:
        sid = args["series_id"]
        if isinstance(sid, bool) or not isinstance(sid, int):
            raise ValueError(f"favorite_add 的 series_id 必须是整数，收到：{type(sid).__name__}")
        resolve_note = "by_id"
    else:
        # TA6 工作项②：按课程名解析（用户零 ID）——多命中时返回候选让模型追问，不猜
        cname = str(args["course_name"]).strip()
        if len(cname) > 128:
            raise ValueError(f"course_name 过长（{len(cname)} > 128）")
        resolved = await resolve_series_by_name(cname)
        if resolved["status"] == "multiple":
            return json.dumps({
                "ok": False,
                "code": "40930",
                "message": f"课程名「{cname}」匹配到多门课程，需用户确认是哪一门",
                "need_clarify": True,
                "course_name": cname,
                "candidates": resolved["candidates"],
                "hint": "请用业务语言向用户列出候选课程名并让其选择，不要自行猜测。",
            }, ensure_ascii=False)
        if resolved["status"] == "fuzzy":
            # TA7 D2：整串零命中，但有「最接近」候选 → 只建议、不猜（need_clarify）。
            # 注意与 40930（multiple：真的匹配到多门同名课）区分：这里是"库内没有这个
            # 名字，以下是名字最接近的几门"，用户点头前**不得**调用收藏。
            return json.dumps({
                "ok": False,
                "code": "40400",
                "message": f"未找到课程「{cname}」（库内没有此课程名）",
                "need_clarify": True,
                "course_name": cname,
                "candidates": resolved["candidates"],
                "matched_by": resolved.get("matched_token"),
                "hint": ("库内没有精确匹配该名称的在售课程。请如实告知用户没找到，并把 candidates 里"
                         "最接近的课程名**原样列出**（最多 3 个），询问是否要收藏其中某一门；"
                         "严禁自行挑选/猜测，用户未确认前不得再次调用收藏。"),
            }, ensure_ascii=False)
        if resolved["status"] == "none" or not resolved.get("series_id"):
            return json.dumps({
                "ok": False,
                "code": "40400",
                "message": f"未找到课程「{cname}」（或该课程已下架）",
                "need_clarify": True,
                "course_name": cname,
                "candidates": resolved.get("candidates") or [],
                "hint": "请如实告知用户未找到该课程，可就近的关键词再确认一次课程名。",
            }, ensure_ascii=False)
        sid = int(resolved["series_id"])
        resolve_note = f"by_name({resolved['status']})"

    # ② 操作者身份：执行上下文权威（防 args 伪造 user_id）
    ctx = _EXEC_CONTEXT.get() or {}
    user_id = int(ctx.get("operator_user_id") or 0)
    if user_id <= 0:
        raise ValueError("favorite_add 缺少操作者身份（执行上下文 operator_user_id 为空）")

    from app.domains.market import service as _market_service

    try:
        item = await _market_service.add_favorite(
            user_id=user_id, series_id=sid, favorite_source=_FAVORITE_ADD_SOURCE,
        )
    except AppException as exc:
        # 业务错（系列不存在/已下架等）→ 结构化回传，严禁伪装成功
        return json.dumps({"ok": False, "code": exc.code, "message": exc.message,
                           "series_id": sid}, ensure_ascii=False)
    return json.dumps({
        "ok": True,
        "favorite_id": int(item.favorite_id),
        "series_id": int(item.series_id),
        "series_title": item.series_title,
        "favorite_source": _FAVORITE_ADD_SOURCE,
        "resolve": resolve_note,
        "idempotent_note": "服务端幂等：重复收藏返回原记录",
        "operator_user_id": user_id,
    }, ensure_ascii=False)


register_builtin_tool("calculator", _calculator_handler)
register_builtin_tool("search_knowledge", _search_knowledge_handler)
register_builtin_tool("knowledge_import", _knowledge_import_handler, write_class=True)
# W-NEXT-WRITE1：write_class=True 仅表示「executor 收口做角色校验」（注册期强属性，
# CR-WNEXT2-executor-gate-bypass 先例）；HITL 弹卡与否由 permission_gate 类别决定
# （user_write 不入 WRITE_CLASSES → 免卡）——两个属性正交，勿混读。
register_builtin_tool("favorite_add", _favorite_add_handler, write_class=True)


# ============================================================
# AUTO20 T12（CR-WRITETOOLS-001 第二批，docs/时光.md §四 B1-B5）
# course_create —— 首个 admin_write 高危写内置工具（强制 HITL）
# ============================================================
# 42201：高危写类工具未经人工确认拒绝执行（CR-WRITETOOLS-001 §1b P4 语义；
# 422xx=校验失败码段，_http_status_for_code 自动映射 HTTP 422）。
COURSE_CREATE_UNCONFIRMED_CODE = 42201

# arg_schema（exact-pin 语义，与 时光.md §B1 草图一致）——本仓库内置工具走
# handler 内手工精确校验（与 favorite_add/knowledge_import 同构），此 dict 为
# 声明性对账面（工具目录/报告可引用），不参与运行时 JSON Schema 校验。
COURSE_CREATE_ARG_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "minLength": 1},
        # TA6：series_code 由「必填」放宽为「可选」——不传时服务端按 title 自动派生合法编码
        # （见 _derive_series_code_from_title + 40901 冲突重试）。用户不该被索要任何数据库
        # 编码类内部参数；显式传入时仍走 exact-pin 校验（保留用户值，不覆盖）。
        "series_code": {"type": "string", "pattern": "^[a-z0-9_]+$"},
        "modules": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title"],
    "additionalProperties": False,
}

# TA6：series_code 自动派生的后缀重试上限（40901 编码冲突时加后缀重试）。
COURSE_CREATE_CODE_RETRY_MAX = 3

# 中文 title → 可读 ASCII 编码的字符映射（覆盖课程命名常用字；未覆盖字直接跳过）。
# 目的：派生出的 series_code 既合法（^[a-z0-9_]+$）又尽量可读，便于人工识别与排障。
_TITLE_ASCII_MAP: dict[str, str] = {
    "课": "course", "课程": "course", "班": "class", "系列": "series",
    "入门": "intro", "基础": "basic", "进阶": "advanced", "高级": "advanced",
    "实战": "practice", "项目": "project", "实战班": "practice",
    "编程": "programming", "程序": "programming", "代码": "code",
    "数据": "data", "分析": "analysis", "结构": "structure", "算法": "algorithm",
    "数学": "math", "英语": "english", "语文": "chinese", "物理": "physics",
    "化学": "chemistry", "生物": "biology", "历史": "history", "地理": "geography",
    "自动化": "automation", "脚本": "scripting", "工具": "tooling",
    "开发": "development", "设计": "design", "测试": "testing", "运维": "operations",
    "人工智能": "ai", "机器学习": "machine_learning", "深度学习": "deep_learning",
    "网络": "network", "安全": "security", "数据库": "database",
    "前端": "frontend", "后端": "backend", "全栈": "fullstack",
    "学习": "learning", "提升": "improve", "强化": "intensive", "培训": "training",
    "素养": "literacy", "竞赛": "contest", "建模": "modeling", "证明": "proof",
    "直播": "online_live", "录播": "online_recorded", "面授": "offline",
    "信息学": "informatics", "管理": "management", "通用": "general",
    "系统": "system", "语言": "language", "脚本自动化": "scripting_automation",
    "办公": "office", "与": "and", "和": "and", "的": "", "之": "",
    "一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
    "六": "6", "七": "7", "八": "8", "九": "9", "十": "10",
    "班·": "_", "·": "_", "（": "_", "）": "_", "(": "_", ")": "_",
    " ": "_", "-": "_", "—": "_", "、": "_", "/": "_",
}


def _slugify_ascii_part(text: str) -> str:
    """把 title 的一段做 ASCII slug：ASCII 字母数字保留（小写化），中文按映射表转写。

    未映射的字符（含未收录的中文/符号）直接跳过——保证输出恒满足 ^[a-z0-9_]+$。
    """
    out: list[str] = []
    i = 0
    # 长键优先匹配（"脚本自动化" 先于 "脚本"/"自动化"；"课程" 先于 "课"）
    map_keys = sorted(_TITLE_ASCII_MAP.keys(), key=len, reverse=True)
    while i < len(text):
        ch = text[i]
        if ch.isascii() and (ch.isalnum() or ch == "_"):
            out.append(ch.lower())
            i += 1
            continue
        matched = False
        for k in map_keys:
            if k and text.startswith(k, i):
                out.append(_TITLE_ASCII_MAP[k])
                i += len(k)
                matched = True
                break
        if not matched:
            i += 1
    slug = "".join(out)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug


def _derive_series_code_from_title(title: str) -> str:
    """TA6 工作项①：由课程 title 自动派生合法 series_code（用户零 ID 输入）。

    规则（自定 slug，稳定可复现）：
      1) title 转 ASCII slug（ASCII 直留；中文按 _TITLE_ASCII_MAP 可读转写）；
      2) slug 为空（纯未收录中文等）或长度不足 → 兜底 `course_` 前缀 + 定长短哈希后缀；
      3) 加 `course_` 前缀时截断至 ≤64（表列上限），保证 re.fullmatch(r"[a-z0-9_]+") 通过。

    短哈希取 sha1(title)，故同一 title 派生结果**确定性可复现**（便于排障与测试锁定）。
    """
    slug = _slugify_ascii_part(title or "")
    if not re.fullmatch(r"[a-z0-9_]+", slug or ""):
        slug = ""
    if len(slug) < 3:
        # 兜底：可读前缀 + 定长短哈希（纯中文/未收录字符场景）
        digest = hashlib.sha1((title or "").strip().encode("utf-8")).hexdigest()[:8]
        slug = f"course_{digest}" if not slug else f"{slug}_course_{digest}"
    if not slug[0].isalpha():
        slug = f"course_{slug}"
    return slug[:64]


def _next_series_code_candidate(base_code: str, attempt: int) -> str:
    """TA6：40901 冲突时生成下一个候选编码（加 `_2`/`_3`… 后缀，仍满足 ^[a-z0-9_]+$ ≤64）。

    attempt 从 1 起（第 1 次重试 → 后缀 `_2`）。截断保证加后缀后总长不超 64。
    """
    suffix = f"_{attempt + 1}"
    return (base_code[: 64 - len(suffix)] + suffix)


# ============================================================
# TA6 工作项②：按课程名解析 series_id（用户零 ID 输入）
# ============================================================
# 匹配结果状态：
#   exact    —— 唯一精确匹配（series_name = 用户给的名称）
#   unique   —— 唯一模糊匹配（LIKE 命中恰好 1 条）
#   multiple —— 多条命中考量（返回候选，让模型追问一次，**不许猜**）
#   fuzzy    —— TA7 D2：精确+整串 LIKE 都零命中，但**逐级放宽词元**后命中若干「最接近」
#               课程（**仅作建议**：一律 need_clarify 让用户点头，绝不自动收藏）
#   none     —— 零命中（连放宽词元都没有任何候选）
COURSE_RESOLVE_LIMIT = 10
# TA7 D2：模糊兜底词元长度下限 / 中文长片逐级截断的最大前缀长度。
_FUZZY_TOKEN_MIN_LEN = 2
_FUZZY_CJK_PREFIX_MAX = 6
# TA7 D2：单次解析最多发出的放宽查询数（上界，防病态输入打爆 DB）。
_FUZZY_MAX_PATTERNS = 6


def _escape_like(s: str) -> str:
    """LIKE 元字符转义（`\\`/`%`/`_`）——用户输入一律经此再参数绑定，禁拼 SQL 文本。"""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _fuzzy_like_patterns(key: str) -> list[str]:
    """TA7 D2：把课程名拆成「由具体到宽泛」的 LIKE 词元（保序去重，上界 6 个）。

    - ASCII 词/数字串整体保留（`Python`、`C++`、`B2`）；
    - 中文片：长于 6 字的按 6→2 字前缀逐级截断（「量子物理导论第七版完全不存在版」
      能退到「量子物理」这类真实存在的课程名前缀）；短片原样保留。

    设计取向：**宁少勿滥**——只发少量上界查询，命中即停（第一个非空词元为准），
    避免"放宽到单字"造成候选爆炸与慢查询。
    """
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+#.]*|[0-9]+|[\u4e00-\u9fff]+", key or "")
    tokens.sort(key=len, reverse=True)
    out: list[str] = []
    for tok in tokens:
        is_ascii = tok[0].isascii()
        if is_ascii:
            cands = [tok] if len(tok) >= _FUZZY_TOKEN_MIN_LEN else []
        else:
            top = min(len(tok), _FUZZY_CJK_PREFIX_MAX)
            cands = [tok[:n] for n in range(top, _FUZZY_TOKEN_MIN_LEN - 1, -1)]
        for c in cands:
            if c in out or c == key:
                continue
            out.append(c)
            if len(out) >= _FUZZY_MAX_PATTERNS:
                return out
    return out


_RESOLVE_SELECT = ("SELECT id AS series_id, series_name, series_code FROM series"
                   " WHERE series_name = %s AND sale_status = 'on_sale'"
                   " ORDER BY id LIMIT %s")
_RESOLVE_LIKE = ("SELECT id AS series_id, series_name, series_code FROM series"
                 " WHERE series_name LIKE %s AND sale_status = 'on_sale'"
                 " ORDER BY CHAR_LENGTH(series_name) ASC, id ASC LIMIT %s")


def _as_candidates(rows: list[dict]) -> list[dict]:
    return [
        {"series_id": int(r["series_id"]),
         "series_name": r.get("series_name"),
         "series_code": r.get("series_code")}
        for r in rows
    ]


async def resolve_series_by_name(name: str) -> dict:
    """TA6 工作项②（TA7 D2 增补模糊兜底）：按课程名解析课程系列。

    只读查询、参数绑定，仅 on_sale 可收藏。策略（确定性、可复现，**绝不猜**）：
      1) 精确匹配优先：`series_name = %s`（去首尾空白）命中恰好 1 条 → 唯一确定；
      2) 精确匹配多条（本库 title 有重复行，如「脚本自动化入门班·录播」×6）→ 返回候选让模型追问；
      3) 精确零命中 → 退化为 LIKE %整串% 模糊匹配（**参数绑定，不做字符串拼接**）：
         命中恰好 1 条 → 唯一确定；多条 → 候选；零条 → 继续第 4 步；
      4) **TA7 D2** 整串也零命中 → 逐级放宽词元（`_fuzzy_like_patterns`，长词元优先、
         中文长片按 6→2 字前缀截断）→ 命中若干 → `status="fuzzy"` 仅给候选供模型追问；
         仍零命中 → `status="none"`。

    返回结构（供 handler 组装回执，勿直出给 LLM 之外的调用方）：
      {"status": "exact"|"unique"|"multiple"|"fuzzy"|"none",
       "series_id": int|None, "series_name": str|None,
       "candidates": [{"series_id", "series_name", "series_code"}, ...],
       "matched_token": str(仅 fuzzy——命中所用的放宽词元，便于排障/报告)}

    ⚠️ `fuzzy` 与 `unique` 语义**不可混用**：`unique` 是"整串模糊命中唯一"（可收藏），
    `fuzzy` 只是"最接近的几门课"建议（**一律 need_clarify，永不自动收藏**）。
    """
    from app.database import fetch_all

    key = (name or "").strip()
    if not key:
        return {"status": "none", "series_id": None, "series_name": None, "candidates": []}

    rows = await fetch_all(_RESOLVE_SELECT, (key, COURSE_RESOLVE_LIMIT))
    status = "exact"
    if not rows:
        rows = await fetch_all(_RESOLVE_LIKE, (f"%{_escape_like(key)}%", COURSE_RESOLVE_LIMIT))
        status = "unique"

    candidates = _as_candidates(rows)
    if len(candidates) == 1:
        return {"status": ("exact" if status == "exact" else "unique"),
                "series_id": candidates[0]["series_id"],
                "series_name": candidates[0]["series_name"],
                "candidates": candidates}
    if len(candidates) > 1:
        return {"status": "multiple", "series_id": None, "series_name": None,
                "candidates": candidates}

    # ---- TA7 D2：精确 + 整串 LIKE 双零命中 → 逐级放宽词元，给「最接近」候选（不猜）----
    for tok in _fuzzy_like_patterns(key):
        fuzzy_rows = await fetch_all(
            _RESOLVE_LIKE, (f"%{_escape_like(tok)}%", COURSE_RESOLVE_LIMIT))
        if fuzzy_rows:
            return {"status": "fuzzy", "series_id": None, "series_name": None,
                    "candidates": _as_candidates(fuzzy_rows), "matched_token": tok}

    return {"status": "none", "series_id": None, "series_name": None, "candidates": []}


async def _course_create_handler(args: dict) -> str:
    """创建课程系列（admin_write 高危，强制 HITL：仅 admin=allow、manager/student/teacher=deny）。

    双保险第一道（P4 裁定）：handler 首行校验执行上下文 `hitl_confirmed`——该键由
    executor.call_tool / call_tool_with_retry 在 resume confirm 批准（hitl_decision=True）
    时服务端注入，LLM/args 伪造结构性不可达；未确认 → 42201 拒，service 零调用。

    单一执行事实源：直调既有 `course_admin.service.create_series`
    （唯一约束 institution_id + series_code，冲突抛 40901 SERIES_CODE_CONFLICT）。
    参数精确校验（exact-pin）：title(str 非空) 必填；series_code(str ^[a-z0-9_]+$) **可选**
    ——TA6 起不传时服务端按 title 自动派生（用户零 ID 输入），显式传入则原样采用；
    modules(list[str]) 可选，多余键一律拒。
    """
    # ⓪ HITL 双保险（P4）：未确认高危写 → 42201 拒（先于一切参数/身份处理，零副作用）
    ctx = _EXEC_CONTEXT.get() or {}
    if not ctx.get("hitl_confirmed"):
        raise AppException(
            code=COURSE_CREATE_UNCONFIRMED_CODE,
            message="高危工具未确认，拒绝执行（需管理员在确认卡上批准后重试）",
            http_status=422,
        )

    # ① 参数精确校验（exact-pin：非法参数零副作用）
    title = args.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("course_create 缺少 title（非空字符串，课程标题）")
    title = title.strip()
    if len(title) > 128:
        raise ValueError(f"title 过长（{len(title)} > 128，课程系列名上限）")

    # TA6 工作项①：series_code 改「可选」——不传/空 时按 title 自动派生（用户零 ID 输入）；
    # 显式传入时保留 exact-pin 校验（用户值优先，不覆盖）。派生的编码是否可用由 40901
    # 冲突重试兜底（见下方 create 循环）。
    raw_code = args.get("series_code")
    code_explicit = isinstance(raw_code, str) and bool(raw_code.strip())
    if code_explicit:
        series_code = raw_code.strip()
        if len(series_code) > 64 or not re.fullmatch(r"[a-z0-9_]+", series_code):
            raise ValueError(f"series_code 非法：{series_code!r}（仅允许小写字母/数字/下划线，≤64 字符）")
    else:
        if raw_code is not None and not isinstance(raw_code, str):
            raise ValueError(f"series_code 必须为字符串，收到：{type(raw_code).__name__}")
        series_code = _derive_series_code_from_title(title)

    modules = args.get("modules")
    if modules is not None:
        if not isinstance(modules, list) or any(not isinstance(m, str) or not m.strip() for m in modules):
            raise ValueError("modules 必须是非空字符串列表（可选参数）")
    extra = set(args) - {"title", "series_code", "modules"}
    if extra:
        raise ValueError(f"course_create 不接受多余参数：{sorted(extra)}（仅 title/series_code/modules）")

    # ② 操作者身份：执行上下文权威（防 args 伪造）
    user_id = int(ctx.get("operator_user_id") or 0)
    if user_id <= 0:
        raise ValueError("course_create 缺少操作者身份（执行上下文 operator_user_id 为空）")

    # ③ 单一执行事实源：course_admin.service.create_series（实物方法，签名为 (data: SeriesCreateAdmin)）
    #    series 表无默认院校语义，institution_id 必须落库非空——取服务端可校验的最小合法院校
    #    （org_institution yn=1 最小 id；课程/班次父引用校验同源依据）。args 传 institution_id 视为
    #    多余键拒绝（exact-pin 防线：防 LLM 臆造父引用）。
    from app.domains.course_admin.schemas import SeriesCreateAdmin
    from app.domains.course_admin import service as _course_service
    from app.database import fetch_one

    inst_row = await fetch_one("SELECT MIN(id) AS min_id FROM org_institution WHERE yn = 1")
    institution_id = int((inst_row or {}).get("min_id") or 0)
    if institution_id <= 0:
        return json.dumps({"ok": False, "code": "40400",
                           "message": "系统未初始化任何启用院校，无法创建课程系列",
                           "series_code": series_code}, ensure_ascii=False)

    # TA6 工作项①：40901 编码冲突重试。仅对**自动派生**的编码重试（用户显式给的值冲突
    # 必须如实回传 40901，不得静默改写成另一个编码 —— 那会违反用户意图）。
    code_attempts: list[str] = []
    result = None
    last_exc: AppException | None = None
    max_tries = 1 if code_explicit else COURSE_CREATE_CODE_RETRY_MAX
    candidate = series_code
    for attempt in range(max_tries):
        try:
            result = await _course_service.create_series(SeriesCreateAdmin(
                institution_id=institution_id,
                delivery_mode="online_recorded",
                series_code=candidate,
                series_name=title,
                description="由 AI 助手（course_create 工具，HITL 确认后）创建",
                created_by=user_id,
            ))
            series_code = candidate
            break
        except AppException as exc:
            # 仅编码冲突（40901）可重试；其余业务错（含 404 院校缺失）立即如实回传
            if str(exc.code) != str(SERIES_CODE_CONFLICT) or attempt >= max_tries - 1:
                last_exc = exc
                break
            code_attempts.append(candidate)
            candidate = _next_series_code_candidate(series_code, attempt + 1)
            logger.info(
                f"[TA6] course_create series_code 冲突重试："
                f"{code_attempts[-1]!r} → {candidate!r}（第 {attempt + 1} 次）"
            )
    if result is None:
        # 业务错（编码冲突 40901 重试耗尽等）→ 结构化回传，严禁伪装成功
        exc = last_exc
        series_code = code_attempts[-1] if code_attempts else series_code
        return json.dumps({"ok": False, "code": getattr(exc, "code", "50000"),
                           "message": getattr(exc, "message", "创建课程系列失败"),
                           "series_code": series_code,
                           "code_attempts": code_attempts}, ensure_ascii=False)

    # ④ 回执如实：created=true（新建成功）；modules 为可选登记项，当前 service 无
    #    「系列级模块直挂」写入面（module 需 cohort 父引用），如实标注未落库不谎报。
    return json.dumps({
        "ok": True,
        "created": True,
        "series_id": int(result.id),
        "series_code": result.series_code,
        "series_name": result.series_name,
        "institution_id": int(result.institution_id),
        "delivery_mode": result.delivery_mode,
        "sale_status": result.sale_status,
        "series_code_source": "user" if code_explicit else "auto_derived",
        "series_code_attempts": code_attempts,
        "modules_requested": list(modules or []),
        "modules_note": "modules 仅登记回执，未创建班次/模块（需先建 cohort，走管理端）",
        "hitl_note": "经人工确认（HITL confirm）后执行",
        "operator_user_id": user_id,
    }, ensure_ascii=False)


register_builtin_tool("course_create", _course_create_handler, write_class=True)


async def _default_attempt_executor(tool_name: str, args: dict, *, call_id: str, attempt: int,
                                    operator_user_id: int, tenant_id: str, trace_id: str) -> AttemptOutcome:
    """生产默认执行器：按工具名解析 server，走单步核心。

    内置本地工具（task-T1-②：calculator/search_knowledge 等）优先命中真实处理器，
    不再因 get_tool_by_ref(None,None,name) 必然 400 而退化为人工指南。
    找不到工具 / server 禁用 / 已删 → 视为失败（非拒绝，不计入拒绝熔断），
    让闭环继续走向换工具或人工指南（AC1 不在此处中断）。
    """
    # task-T1-②：内置/本地工具优先解析（命中即真实执行，非"未注册自然走指南"）
    builtin = _BUILTIN_TOOL_HANDLERS.get(tool_name)
    if builtin is not None:
        _t0 = time.perf_counter()
        try:
            content = await builtin(dict(args))
            # TA7 D1：业务失败（ok:false / 非 0 code）→ ok=False + status=ERROR +
            # is_business_failure=True。三件事同时成立才能既如实落审计、又让 SSE/护栏
            # 看到真凭据，同时由 call_tool_with_retry 识别为**终态**（不重试/不出人工指南）。
            _biz_fail, _biz_msg = _builtin_business_failure(content)
            _outcome = AttemptOutcome(
                ok=(not _biz_fail),
                status=(ToolCallStatusEnum.ERROR.value if _biz_fail
                        else ToolCallStatusEnum.SUCCESS.value),
                tool_name=tool_name,
                args=dict(args), error_message=(_biz_msg or ""), latency_ms=0,
                is_rejection=False, is_business_failure=_biz_fail,
                result={"content": content}, content_text=content,
            )
        except Exception as exc:  # noqa: BLE001
            _outcome = AttemptOutcome(
                ok=False, status="ERROR", tool_name=tool_name, args=dict(args),
                error_message=f"内置工具 {tool_name} 执行失败: {exc}", latency_ms=0,
                is_rejection=False,
            )
        # W-NEXT-WRITE1（T6 实测缺口修复）：graph/子代理路径（call_tool_with_retry →
        # _default_attempt_executor）的内置分支此前**零审计落库**——W-NEXT-MCP-001 P0-②
        # 只覆盖了 call_tool 直连路径（_execute_builtin_attempt）。favorite_add 经此路径
        # 真实写库（favorites +1）但 mcp_tool_call_log 0 行（2026-09-20 实测）。补齐：
        # 成败均落审计（与 _execute_builtin_attempt 同构），落库失败不阻断主链路。
        try:
            await _write_call_log(
                call_id=f"mcp-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}",
                server_id=0, tool_name=tool_name,
                args=dict(args), result=None, content_text=_outcome.content_text,
                status=(ToolCallStatusEnum.SUCCESS if _outcome.ok else ToolCallStatusEnum.ERROR),
                latency_ms=int((time.perf_counter() - _t0) * 1000),
                user_id=operator_user_id, tenant_id=tenant_id, trace_id=trace_id,
                error_message=_outcome.error_message or None,
            )
        except Exception:  # noqa: BLE001 — 审计落库失败绝不影响工具返回
            logger.debug(f"[MCP] 内置工具 {tool_name} 审计落库失败（graph 路径），忽略")
        return _outcome
    try:
        tool_row = await registry.get_tool_by_ref(None, None, tool_name)
    except Exception as exc:
        return AttemptOutcome(ok=False, status="ERROR", tool_name=tool_name, args=dict(args),
                             error_message=f"未找到 MCP 工具 {tool_name}: {exc}", latency_ms=0,
                             is_rejection=False)
    server_id_eff = int(tool_row["server_id"])
    server = await fetch_one("SELECT * FROM mcp_server WHERE id=%s AND yn=1 LIMIT 1", (server_id_eff,))
    if not server:
        return AttemptOutcome(ok=False, status="ERROR", tool_name=tool_name, args=dict(args),
                              error_message=f"关联 server {server_id_eff} 已删除", latency_ms=0,
                              is_rejection=False)
    if int(server.get("enabled") or 0) != 1:
        return AttemptOutcome(ok=False, status="ERROR", tool_name=tool_name, args=dict(args),
                              error_message=f"server_code={server.get('server_code')} 已禁用（enabled=0）",
                              latency_ms=0, is_rejection=False)
    resp = await _execute_single_attempt(
        server=server, tool_name=tool_name, args=args, call_id=call_id,
        operator_user_id=operator_user_id, tenant_id=tenant_id, trace_id=trace_id,
    )
    return AttemptOutcome(
        ok=(resp.status == ToolCallStatusEnum.SUCCESS),
        status=resp.status.value, tool_name=tool_name, args=dict(args),
        latency_ms=resp.latency_ms, error_message=resp.error_message,
        is_rejection=(resp.status != ToolCallStatusEnum.SUCCESS),
        result=resp.result, content_text=resp.content_text, resp=resp,
    )


# ============================================================
# 拒绝计数熔断（对齐 Codex auto-review 3 连续拒绝熔断）
# ============================================================
_REJECT_MEM: dict[str, int] = {}


class _RedisRejectCounter:
    """会话级拒绝计数器（Redis `mcp:reject:{session_id}`，TTL 兜底）。

    Redis 不可用时降级内存 dict，保证闭环逻辑不因 Redis 抖动而崩（仅失去跨请求持久）。
    """

    def __init__(self, redis, *, ttl_s: int = 300) -> None:
        self._redis = redis
        self._ttl_s = ttl_s

    async def get(self, session_id: str) -> int:
        if self._redis is not None:
            try:
                v = await self._redis.get(f"mcp:reject:{session_id}")
                return int(v) if v else 0
            except Exception:
                pass
        return int(_REJECT_MEM.get(session_id, 0))

    async def increment(self, session_id: str) -> int:
        if self._redis is not None:
            try:
                key = f"mcp:reject:{session_id}"
                n = await self._redis.incr(key)
                if n == 1:
                    try:
                        await self._redis.expire(key, self._ttl_s)
                    except Exception:
                        pass
                return int(n)
            except Exception:
                pass
        _REJECT_MEM[session_id] = int(_REJECT_MEM.get(session_id, 0)) + 1
        return _REJECT_MEM[session_id]

    async def reset(self, session_id: str) -> None:
        if self._redis is not None:
            try:
                await self._redis.delete(f"mcp:reject:{session_id}")
            except Exception:
                pass
        _REJECT_MEM[session_id] = 0


def _make_reject_store(*, ttl_s: int = 300, _override: RejectStore | None = None) -> RejectStore:
    if _override is not None:
        return _override
    try:
        r = get_redis()
    except Exception:
        r = None
    return _RedisRejectCounter(r, ttl_s=ttl_s)


def _emit_retry_event(payload: dict, *, trace_id: str, user_id: int) -> None:
    """best-effort 上报闭环事件（task-O1 tool_result/retry 埋点基座）。失败静默。"""
    try:
        from app.otel.exporter import get_otel_exporter
        exp = get_otel_exporter()
        if exp is None:
            return
        exp.record("retry", payload={**payload, "trace_id": trace_id or None},
                   trace_id=trace_id or None,
                   user_id=int(user_id) if user_id else None,
                   latency_ms=payload.get("latency_ms"))
    except Exception:
        pass


async def _final_manual_guide(*, original_tool_name: str, server_id: int, args: dict,
                              trail: list[dict], last_error: str | None, total_t0: float,
                              trace_id: str, operator_user_id: int, tenant_id: str) -> MCPToolTestResp:
    """第 4 步：所有可用工具均失败/熔断 → 结构化人工操作指南并停止（AC1/AC2/AC4）。"""
    guide = build_manual_guide(
        original_tool_name=original_tool_name, attempts_trail=trail,
        original_args=args, last_error=last_error,
    )
    latency_ms = int((time.perf_counter() - total_t0) * 1000)
    cid = f"mcp-guide-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    try:
        await _write_call_log(
            call_id=cid, server_id=server_id, tool_name=original_tool_name,
            args=args, result=guide, content_text=None,
            status=ToolCallStatusEnum.MANUAL_GUIDE, latency_ms=latency_ms,
            user_id=operator_user_id, tenant_id=tenant_id, trace_id=trace_id,
            error_message=last_error or "所有可用工具均失败，转人工操作指南",
        )
    except Exception:
        pass
    content = (f"[人工操作指南] {guide['problem_description']} "
               f"已尝试工具：{', '.join(str(t.get('tool_name')) for t in trail)}。"
               f"请联系管理员或按指南手动处理。")
    return MCPToolTestResp(
        status=ToolCallStatusEnum.MANUAL_GUIDE, error_message=last_error,
        latency_ms=latency_ms, call_id=cid, server_id=server_id,
        tool_name=original_tool_name, content_text=content,
        attempt=len(trail) + 1 if trail else 4, actions=trail,
        manual_guide=guide, rejection_limited=False,
    )


async def _final_rejection_limit(*, original_tool_name: str, server_id: int, args: dict,
                                 trail: list[dict], total_t0: float, trace_id: str,
                                 operator_user_id: int, tenant_id: str,
                                 reject_store: RejectStore, session_id: str) -> MCPToolTestResp:
    """AC3：同会话连续被拒达上限 → 中断该回合工具循环，转人工指南（status=REJECTION_LIMIT）。"""
    guide = build_manual_guide(
        original_tool_name=original_tool_name, attempts_trail=trail,
        original_args=args, last_error="同会话连续被拒达上限，已中断工具循环",
    )
    latency_ms = int((time.perf_counter() - total_t0) * 1000)
    cid = f"mcp-rej-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    try:
        await _write_call_log(
            call_id=cid, server_id=server_id, tool_name=original_tool_name,
            args=args, result=guide, content_text=None,
            status=ToolCallStatusEnum.REJECTION_LIMIT, latency_ms=latency_ms,
            user_id=operator_user_id, tenant_id=tenant_id, trace_id=trace_id,
            error_message="同会话连续被拒达上限，已中断回合工具循环",
        )
    except Exception:
        pass
    content = (f"[拒绝熔断] 同会话内工具连续被拒达上限，已中断工具循环并转人工指南。"
               f"{guide['problem_description']}")
    return MCPToolTestResp(
        status=ToolCallStatusEnum.REJECTION_LIMIT,
        error_message="同会话连续被拒达上限",
        latency_ms=latency_ms, call_id=cid, server_id=server_id,
        tool_name=original_tool_name, content_text=content,
        attempt=4, actions=trail, manual_guide=guide, rejection_limited=True,
    )


# ============================================================
# task-T1-③：工具参数改写（第 2 步 ACTION_REWRITE）
#   - TOOL_REWRITE_RULES：确定性规则改写映射表（≥5 组），LLM 改写不可用时的兜底，零外部依赖；
#   - _fast_rewrite_args：窗口内走 FAST（火山 ark deepseek-v4-flash）真实改写；
#   - _default_rewrite_fn：优先 FAST 真实改写，失败回退规则表（保证 rewrite 闭环始终有产出）。
# 验收：真实 FAST 改写成功 ≥1 例；或增强规则改写映射表 ≥5 组。
# ============================================================
TOOL_REWRITE_RULES: list[dict] = [
    # 1) 缺失必填分页/数量参数 → 仅补实际缺失的键，避免覆盖已提供的参数
    {"id": "fill_missing_limit",
     "when_missing_any": ["limit", "top_k", "count", "page_size", "size"],
     "defaults": {"limit": 10, "top_k": 10, "count": 10, "page_size": 10, "size": 10},
     "desc": "缺失分页/数量必填参数 → 补对应默认（limit/top_k/...=10）"},
    # 2) 数值类参数强制转 int（防字符串/浮点类型错误）
    {"id": "coerce_int",
     "coerce_int": ["limit", "offset", "top_k", "count", "page", "page_size", "size", "n"],
     "desc": "数值分页参数强制转 int"},
    # 3) 布尔类参数强制转 bool（防 'true'/'false' 字符串误判）
    {"id": "coerce_bool",
     "coerce_bool": ["recursive", "enable", "enabled", "force", "strict", "overwrite", "async_"],
     "desc": "布尔参数强制转 bool"},
    # 4) 日期参数归一为 YYYY-MM-DD（去空格、中文/英文斜杠统一）
    {"id": "normalize_date",
     "normalize_date": ["date", "start_date", "end_date", "from", "to", "begin", "begin_date"],
     "desc": "日期参数归一为 YYYY-MM-DD"},
    # 5) 报错含超时 → 增大 timeout（秒），缓解瞬时限流/慢响应
    {"id": "timeout_on_error",
     "when_error_contains": ["timeout", "timed out", "504", "读写超时"],
     "set": {"timeout": 60},
     "desc": "超时类报错 → timeout=60"},
    # 6) 报错含限流 → 标记退避 + 降低批量，配合控制环退避
    {"id": "ratelimit_on_error",
     "when_error_contains": ["429", "rate limit", "too many requests", "限流", "请求过于频繁"],
     "set": {"_backoff_s": 2, "batch_size": 1},
     "desc": "限流类报错 → 退避 2s + 批量降为 1"},
]


def _extract_json_obj(text: str) -> dict | None:
    """从模型输出中尽量解析出首个 JSON 对象。"""
    if not text:
        return None
    s = text.strip()
    import re
    m = re.search(r"\{.*\}", s, re.S)
    if m:
        s = m.group(0)
    try:
        obj = json.loads(s)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _apply_rewrite_rules(args: dict, error: str | None) -> dict:
    """确定性规则改写（TOOL_REWRITE_RULES）。返回新的 args dict，原 dict 不变。"""
    out = dict(args)
    err = (error or "").lower()
    for rule in TOOL_REWRITE_RULES:
        # 缺失参数补默认（仅补实际缺失的键，保留已提供参数）
        miss = rule.get("when_missing_any")
        if miss:
            defaults = rule.get("defaults", rule.get("set", {}))
            for k in miss:
                if k not in out and k in defaults:
                    out[k] = defaults[k]
        # 报错关键词触发 set
        keys = rule.get("when_error_contains")
        if keys and any(k.lower() in err for k in keys):
            out.update(rule.get("set", {}))
        # 类型强制（不论报错，防类型错误）
        for k in rule.get("coerce_int", []):
            if k in out and out[k] is not None:
                try:
                    out[k] = int(float(out[k]))
                except (TypeError, ValueError):
                    pass
        for k in rule.get("coerce_bool", []):
            if k in out and out[k] is not None:
                v = out[k]
                out[k] = v if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "yes", "y", "t")
        for k in rule.get("normalize_date", []):
            if k in out and out[k]:
                try:
                    import datetime as _dt
                    out[k] = _dt.date.fromisoformat(str(out[k]).strip().replace("/", "-").replace("：", ":")).isoformat()
                except Exception:
                    pass
    return out


async def _fast_rewrite_args(args: dict, error: str | None, tool_name: str) -> dict | None:
    """窗口内真实 FAST 改写：火山 ark plan/v3 deepseek-v4-flash 修正工具参数。失败返回 None。"""
    from app.chat.generator import _ChatClient
    messages = [
        {"role": "system", "content": (
            "你是 MCP 工具参数修正器。给定工具名、上一次调用报错、当前参数，"
            "返回修正后的参数 JSON 对象（只改有问题的字段，保持其他字段不变）。"
            "只输出 JSON，不要解释。")},
        {"role": "user", "content": json.dumps(
            {"tool": tool_name, "error": error or "", "args": args},
            ensure_ascii=False)},
    ]
    try:
        client = _ChatClient.get()
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(
            None,
            lambda: client.call_chat(
                messages=messages, model="fast", temperature=0.0, max_tokens=500, timeout=30.0,
            ),
        )
        obj = _extract_json_obj(text)
        if isinstance(obj, dict):
            # 仅保留原args中存在的键（不擅自新增未知参数）
            return {k: obj[k] for k in obj if k in args}
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[T1-③] FAST 改写失败（回退规则表）: {type(exc).__name__}: {exc}")
    return None


async def _default_rewrite_fn(args: dict, error: str | None, tool_name: str) -> dict:
    """第 2 步改写默认实现：优先 FAST 真实改写，失败回退确定性规则表。"""
    fast = await _fast_rewrite_args(args, error, tool_name)
    if isinstance(fast, dict) and fast:
        return fast
    return _apply_rewrite_rules(args, error)


async def call_tool_with_retry(*, operator_user_id: int, tenant_id: str = "", trace_id: str = "",
                               session_id: str = "", tool_id: int | None = None,
                               server_id: int | None = None, tool_name: str | None = None,
                               args: dict | None = None, call_id: str | None = None,
                               llm_rewrite_fn=None,
                               hitl_action_id: str | None = None,
                               hitl_decision: bool | None = None,
                               _attempt_executor=None, _reject_store=None,
                               _hitl_store=None, _hitl_reviewer=None) -> MCPToolTestResp:
    """task-T1 工具调用闭环：换参 → 换工具 → 熔断 → 人工指南（AC1~AC4）。

    - 第 1 步正常；第 2 步换参数（LLM 改写 args，或规则跳级兜底）；
      第 3 步换备用工具（TOOL_FALLBACK_MAP）；第 4 步输出结构化人工指南并停止（AC1/AC2）。
    - 同会话内连续被拒达 TOOL_CONSECUTIVE_REJECTIONS → 第 4 次尝试直接中断（AC3）。
    - 每步产出 {attempt,action,tool_name,args,outcome,latency_ms} 事件 + trace_id（AC4）。
    - 保留 task33 既有契约：per-server 熔断 / 只读缓存 / 审计日志（call_tool 单步路径不变）。
    """
    args = args or {}
    _EXEC_CONTEXT.set({
        "operator_user_id": int(operator_user_id or 0),
        "tenant_id": str(tenant_id or ""),
        "trace_id": str(trace_id or ""),
        # AUTO20 T12 双保险注入（CR-WRITETOOLS-001 §1b P4）：hitl_confirmed 仅由服务端在
        # resume confirm 批准（hitl_decision=True）时置 True——LLM/args 无法伪造；
        # 高危 handler（course_create）首行校验此键，未确认 → 42201 拒（service 零调用）。
        "hitl_confirmed": bool(hitl_decision is True),
    })
    fallback_map = settings.TOOL_FALLBACK_MAP
    max_attempts = settings.MAX_TOOL_ATTEMPTS
    consecutive_rej = settings.TOOL_CONSECUTIVE_REJECTIONS
    reject_ttl = settings.TOOL_REJECT_TTL_S
    use_llm_rewrite = settings.TOOL_RETRY_LLM_REWRITE
    # task-T1-③：调用方未显式传 llm_rewrite_fn 时，默认启用「FAST 真实改写 → 规则表兜底」
    if llm_rewrite_fn is None and use_llm_rewrite:
        llm_rewrite_fn = _default_rewrite_fn

    # W-NEXT-2 步骤2 纵深防御：写类工具在本路径（六节点图子代理 call_tool 事实源）先过门，
    # 越权 → ACI 信封、零执行（不进入 registry 解析 / HITL / 重试闭环）。
    # 仅对 TOOL_CLASS_MAP 命中的写类生效 → 未登记工具名（web_search 等）保持既有 404/重试语义。
    _req_name = str(tool_name or "").strip().lower()
    if _req_name:
        from app.ai.permission_gate import gate_tool_call, is_write_class, resolve_role

        if is_write_class(_req_name):
            _role = await resolve_role(operator_user_id)
            if not gate_tool_call(_role, _req_name).allowed:
                return _permission_denied_resp(
                    tool_name=_req_name, role=_role, call_id=call_id or "",
                    server_id=int(server_id or 0),
                )

    # W-NEXT-2 步骤3：内置工具优先解析（无 mcp_tool/mcp_server 行）——合成 server 元信息后
    # 直接复用下方既有 HITL 护栏与重试闭环；真实执行仍由 _default_attempt_executor 的
    # 内置 handler 分支完成（switch_tool 换到内置备用工具同样走得通）。
    _builtin_name = _resolve_builtin_name(tool_id, server_id, tool_name)
    if _builtin_name:
        original_tool_name = _builtin_name
        server_id_eff = int(server_id or 0)
        server = {"id": server_id_eff, "server_code": "builtin", "enabled": 1, "yn": 1}
    else:
        # 解析原始工具引用
        try:
            tool_row = await registry.get_tool_by_ref(tool_id, server_id, tool_name)
        except Exception as exc:
            return MCPToolTestResp(
                status=ToolCallStatusEnum.ERROR, error_message=f"工具解析失败：{exc}",
                latency_ms=0, call_id=call_id or "mcp-err", server_id=int(server_id or 0),
                tool_name=str(tool_name or ""), content_text=None,
            )
        original_tool_name = str(tool_row["tool_name"])
        server_id_eff = int(tool_row["server_id"])
        server = await fetch_one("SELECT * FROM mcp_server WHERE id=%s AND yn=1 LIMIT 1", (server_id_eff,))
        if not server:
            return MCPToolTestResp(
                status=ToolCallStatusEnum.ERROR, error_message="关联 server 已删除",
                latency_ms=0, call_id=call_id or "mcp-err", server_id=server_id_eff,
                tool_name=original_tool_name, content_text=None,
            )
        if int(server.get("enabled") or 0) != 1:
            return MCPToolTestResp(
                status=ToolCallStatusEnum.ERROR,
                error_message=f"server_code={server.get('server_code')} 已禁用（enabled=0）",
                latency_ms=0, call_id=call_id or "mcp-err", server_id=server_id_eff,
                tool_name=original_tool_name, content_text=None,
            )

    # ② 解析后的真实工具名再校验一次：堵 `tool_id=N`（不传 tool_name）时名字为空 →
    #    上方 ① 校验被整体跳过的绕过口子（独立复验实测）。
    _denied = await _deny_if_write_class(
        name=original_tool_name, operator_user_id=operator_user_id,
        call_id=call_id or "", server_id=server_id_eff,
    )
    if _denied is not None:
        return _denied

    # task-S1 全流程 HITL 护栏：原始工具为高风险写工具时，先过 Gate 再进闭环（HITL_ENABLED 默认 False）
    if settings.HITL_ENABLED:
        _at = _classify_hitl_action(original_tool_name)
        if _at is not None:
            _gated = await _run_hitl_seam(
                action_type=_at, target=original_tool_name, params=args,
                operator_user_id=operator_user_id, tenant_id=tenant_id, trace_id=trace_id,
                server_id=(None if _builtin_name else server_id_eff), call_id=call_id,
                human_decision=hitl_decision, action_id=hitl_action_id or "",
                server=server, store=_hitl_store, reviewer_fn=_hitl_reviewer,
                # 内置工具（knowledge_import）批准后的执行体是 handler，不走传输层
                exec_override=(
                    _make_builtin_hitl_exec(
                        _builtin_name, operator_user_id=operator_user_id,
                        tenant_id=tenant_id, trace_id=trace_id,
                    )
                    if _builtin_name else None
                ),
            )
            if _gated is not None:
                return _gated

    executor = _attempt_executor or _default_attempt_executor
    reject_store = _reject_store or _make_reject_store(ttl_s=reject_ttl)
    sm = ToolRetryStateMachine(original_tool_name, args, fallback_map=fallback_map, max_attempts=max_attempts)

    trail: list[dict] = []
    last_error: str | None = None
    total_t0 = time.perf_counter()

    def _mk_call_id(attempt: int) -> str:
        return call_id or f"mcp-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}-{attempt}"

    step = sm.plan_first()
    while step is not None:
        # AC3：执行前检查会话拒绝计数，达上限则中断（不执行第 4 次工具调用）
        if session_id:
            try:
                if await reject_store.get(session_id) >= consecutive_rej:
                    return await _final_rejection_limit(
                        original_tool_name=original_tool_name, server_id=server_id_eff,
                        args=args, trail=trail, total_t0=total_t0, trace_id=trace_id,
                        operator_user_id=operator_user_id, tenant_id=tenant_id,
                        reject_store=reject_store, session_id=session_id,
                    )
            except Exception:
                pass

        # 第 2 步换参数：LLM 改写或规则跳级兜底
        eff_args = step.args
        if step.action == ACTION_REWRITE and use_llm_rewrite and llm_rewrite_fn is not None:
            try:
                rewritten = await llm_rewrite_fn(dict(args), last_error, original_tool_name)
                if isinstance(rewritten, dict):
                    eff_args = rewritten
            except Exception:
                eff_args = dict(args)  # 规则跳级兜底
        elif step.action == ACTION_REWRITE:
            eff_args = dict(args)  # 规则跳级：原参透传（动作语义仍记 rewrite_args）

        cid = _mk_call_id(step.attempt)
        # W-NEXT-2 加固（复验 P1）：第 3 步换备用工具的目标名来自 settings.TOOL_FALLBACK_MAP
        # （可被环境变量 JSON 覆盖）→ 若备用名是写类工具，必须与原始名同样过写类门，
        # 否则「读工具 → 写工具」的备用映射会成为绕过 executor 收口的通道
        # （复验实测：student + {"calculator": ["knowledge_import"]} → 写类 handler 真实执行）。
        if step.tool_name != original_tool_name:
            _denied = await _deny_if_write_class(
                name=step.tool_name, operator_user_id=operator_user_id,
                call_id=cid, server_id=server_id_eff,
            )
            if _denied is not None:
                return _denied
        outcome = await executor(
            step.tool_name, eff_args, call_id=cid, attempt=step.attempt,
            operator_user_id=operator_user_id, tenant_id=tenant_id, trace_id=trace_id,
        )
        # 记录事件（AC4）
        ev = {
            "attempt": step.attempt, "action": step.action,
            "tool_name": step.tool_name, "args": eff_args,
            "outcome": outcome.status, "latency_ms": outcome.latency_ms,
            "error_message": outcome.error_message,
        }
        trail.append(ev)
        _emit_retry_event(ev, trace_id=trace_id, user_id=operator_user_id)

        if outcome.ok:
            # 成功：重置会话拒绝计数（连续语义），返回最终响应（带闭环轨迹）
            if session_id:
                try:
                    await reject_store.reset(session_id)
                except Exception:
                    pass
            resp = outcome.resp if isinstance(outcome.resp, MCPToolTestResp) else MCPToolTestResp(
                status=ToolCallStatusEnum.SUCCESS, result=outcome.result,
                error_message=None, latency_ms=outcome.latency_ms, call_id=cid,
                server_id=server_id_eff, tool_name=step.tool_name, content_text=outcome.content_text,
            )
            resp.attempt = step.attempt
            resp.actions = trail
            resp.manual_guide = None
            resp.rejection_limited = False
            return resp

        # TA7 D1：业务失败 = **确定性终态**（参数本身不成立，如课程名不存在）
        # → 不重试（换参还是同一个不存在的名字）、不出人工指南（那只是运维模板，
        #   还会把 content 里的 need_clarify/candidates 冲掉）；也不计入拒绝熔断
        #（业务失败不是权限/协议拒绝）。如实回传 ERROR + 原始结构化 content。
        if not outcome.ok and getattr(outcome, "is_business_failure", False):
            resp = outcome.resp if isinstance(outcome.resp, MCPToolTestResp) else MCPToolTestResp(
                status=ToolCallStatusEnum.ERROR, result=outcome.result,
                error_message=outcome.error_message, latency_ms=outcome.latency_ms, call_id=cid,
                server_id=server_id_eff, tool_name=step.tool_name,
                content_text=outcome.content_text,
            )
            resp.attempt = step.attempt
            resp.actions = trail
            resp.manual_guide = None
            resp.rejection_limited = False
            return resp

        # 失败：累计拒绝计数（isError/权限拒绝）
        last_error = outcome.error_message
        if session_id and outcome.is_rejection:
            try:
                await reject_store.increment(session_id)
            except Exception:
                pass
        step = sm.plan_next(step.attempt, outcome)

    # 所有步失败 / 无备用工具 → 第 4 步人工指南
    return await _final_manual_guide(
        original_tool_name=original_tool_name, server_id=server_id_eff, args=args,
        trail=trail, last_error=last_error, total_t0=total_t0, trace_id=trace_id,
        operator_user_id=operator_user_id, tenant_id=tenant_id,
    )


async def _invoke_transport(server: dict, tool_name: str, args: dict[str, Any],
                            call_id: str) -> tuple[ToolCallStatusEnum, str | None, Any, str | None]:
    """执行一次 MCP 传输调用（stdio/sse/http），映射异常到状态。返回 4 元组。"""
    status_eff = ToolCallStatusEnum.SUCCESS
    error_message: str | None = None
    result_parsed: Any = None
    content_text: str | None = None
    transport = server.get("transport")
    try:
        if transport == "stdio":
            timeout_s = max(2.0, int(server.get("call_timeout_ms") or 30000) / 1000.0)
            reqs = [
                {"jsonrpc": "2.0", "method": "initialize",
                 "params": {"protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "edu-agent-p8", "version": "1.0"}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "method": "tools/call",
                 "params": {"name": tool_name, "arguments": args}},
            ]
            try:
                resps = await asyncio.wait_for(
                    _stdio_exchange_async(dict(server), reqs, timeout_s),
                    timeout=timeout_s + 10.0,
                )
            except asyncio.TimeoutError as exc:
                raise TimeoutError(f"stdio 调用超时（>{timeout_s:.1f}s）") from exc
            init_resp, _, call_resp = resps[0], resps[1], resps[2]
            if init_resp is None:
                raise RuntimeError("stdio initialize 无响应（server stdout 为空？）")
            if init_resp.get("error"):
                raise RuntimeError(f"initialize err: {init_resp['error']}")
            if call_resp is None:
                raise RuntimeError("stdio tools/call 无响应（进程可能提前退出）")
            if call_resp.get("error"):
                raise RuntimeError(f"tools/call JSON-RPC err: {call_resp['error']}")
            call_result = call_resp.get("result") or {}
            is_error = bool(call_result.get("isError"))
            content_text = _extract_mcp_content_text(call_result)
            content_text, _trunc = _truncate_result_text(content_text)
            if _trunc:
                logger.debug(f"[MCP] 工具 {tool_name} 结果超限已截断（isolation）")
            if is_error:
                raise RuntimeError(content_text or "MCP tool isError=true")
            try:
                result_parsed = json.loads(content_text) if content_text is not None else None
            except Exception:
                result_parsed = content_text
        elif transport in ("sse", "http"):
            headers = _remote_auth_headers(server)
            body = {
                "jsonrpc": "2.0", "id": call_id,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": args},
            }
            connect_ms = int(server.get("connect_timeout_ms") or 5000)
            call_ms = int(server.get("call_timeout_ms") or 30000)
            http_resp = await _http_request_jsonrpc(
                str(server.get("base_url")), body,
                headers=headers if isinstance(headers, dict) else {},
                timeout_connect_ms=connect_ms, timeout_total_ms=call_ms,
            )
            if http_resp.get("error"):
                raise RuntimeError(f"HTTP JSON-RPC err: {http_resp['error']}")
            call_result = http_resp.get("result") or {}
            content_text = _extract_mcp_content_text(call_result)
            content_text, _trunc = _truncate_result_text(content_text)
            if _trunc:
                logger.debug(f"[MCP] 工具 {tool_name} 结果超限已截断（isolation）")
            try:
                result_parsed = json.loads(content_text) if content_text is not None else None
            except Exception:
                result_parsed = content_text
        else:
            raise _raise(400, f"不支持的 transport={transport}")
    except TimeoutError as exc:
        status_eff = ToolCallStatusEnum.TIMEOUT
        error_message = str(exc)[:1024]
    except AppException:
        raise
    except Exception as exc:
        status_eff = ToolCallStatusEnum.ERROR
        error_message = f"{type(exc).__name__}: {exc}"[:1024]
    return status_eff, error_message, result_parsed, content_text


async def health_check_server(server_id: int) -> dict:
    """用轻量 initialize+ping 进行健康检查；返回 {ok:bool, latency_ms:int, reason?:str}。"""
    server = await fetch_one("SELECT * FROM mcp_server WHERE id=%s AND yn=1 LIMIT 1", (server_id,))
    if not server:
        raise _raise(404, f"Server id={server_id} 不存在或已删除")
    t0 = time.perf_counter()
    ok = False
    reason: str | None = None
    try:
        transport = server.get("transport")
        if transport == "stdio":
            timeout_s = max(2.0, int(server.get("connect_timeout_ms") or 5000) / 1000.0)
            concluded = False
            if settings.MCP_HC_USE_POOL:
                # B1：先池后 spawn —— 池内长连会话只发一条 ping（initialize 已在入池时完成）
                ok, reason, concluded = await _stdio_health_via_pool(server, timeout_s)
            if not concluded:
                # B1 回滚开关（MCP_HC_USE_POOL=False）或池通道兜底：一次性 spawn 全握手（旧路径，行为不变）
                reqs = [
                    {"jsonrpc": "2.0", "method": "initialize",
                     "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "edu-agent-hc", "version": "1.0"}}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "method": "ping"},
                ]
                resps = await asyncio.wait_for(
                    _stdio_exchange_async(dict(server), reqs, timeout_s),
                    timeout=timeout_s + 8.0,
                )
                init_resp, _, ping_resp = resps[0], resps[1], resps[2]
                # MCP 规范 ping 的 result 是空对象 {} —— 必须判 is not None，truthy 检查会把规范兼容的 server 误判为不健康
                if (init_resp and init_resp.get("result") is not None
                        and ping_resp and ping_resp.get("result") is not None):
                    ok = True
                else:
                    def _short(x):
                        if x is None: return "None"
                        return f"keys={sorted(list(x.keys()))[:8]} res={'T' if x.get('result') is not None else 'F'} err={'T' if x.get('error') is not None else 'F'}"
                    reason = f"stdio: init={_short(init_resp)} ping={_short(ping_resp)}"
        elif transport in ("sse", "http"):
            base_url = str(server.get("base_url") or "")
            if not base_url:
                raise RuntimeError("base_url 为空")
            headers = _safe_json(server.get("http_headers_json") or "{}", dict)
            connect_ms = int(server.get("connect_timeout_ms") or 5000)
            call_ms = int(server.get("call_timeout_ms") or 15000)
            if _httpx is not None:
                timeout_obj = _httpx.Timeout(max(0.3, call_ms / 1000.0), connect=max(0.2, connect_ms / 1000.0))
                async with _httpx.AsyncClient(timeout=timeout_obj, follow_redirects=True) as c:
                    try:
                        r = await c.get(base_url, headers=headers or {})
                        ok = (200 <= r.status_code < 500)
                        if not ok:
                            reason = f"HTTP {r.status_code}"
                    except Exception as exc:
                        reason = f"httpx fail: {exc}"[:512]
            elif _aiohttp is not None:
                timeout_obj = _aiohttp.ClientTimeout(total=max(0.3, call_ms / 1000.0), sock_connect=max(0.2, connect_ms / 1000.0))
                async with _aiohttp.ClientSession(timeout=timeout_obj) as s:
                    try:
                        async with s.get(base_url, headers=headers or {}) as r:
                            ok = (200 <= r.status < 500)
                            if not ok:
                                reason = f"HTTP {r.status}"
                    except Exception as exc:
                        reason = f"aiohttp fail: {exc}"[:512]
            else:
                ok = False
                reason = "缺少 httpx/aiohttp 依赖（pip install httpx）"
        else:
            reason = f"未知 transport={transport}"
    except Exception as exc:
        ok = False
        reason = f"{type(exc).__name__}: {exc}"[:512]
    finally:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        await registry.write_server_health(server_id, ok=ok, last_error=None if ok else reason)
    return {"ok": ok, "latency_ms": latency_ms, "reason": reason}


async def discover_tools(server_id: int, operator_user_id: int) -> dict:
    """initialize + tools/list → 批量 upsert。返回 {count:int, error?:str}"""
    server = await fetch_one("SELECT * FROM mcp_server WHERE id=%s AND yn=1 LIMIT 1", (server_id,))
    if not server:
        raise _raise(404, f"Server id={server_id} 不存在或已删除")
    transport = server.get("transport")
    tools_list: list[dict] = []
    error_msg: str | None = None
    try:
        if transport == "stdio":
            timeout_s = max(5.0, int(server.get("call_timeout_ms") or 30000) / 1000.0)
            reqs = [
                {"jsonrpc": "2.0", "method": "initialize",
                 "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "edu-agent-disc", "version": "1.0"}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "method": "tools/list"},
            ]
            resps = await asyncio.wait_for(
                _stdio_exchange_async(dict(server), reqs, timeout_s),
                timeout=timeout_s + 10.0,
            )
            init_resp, _, list_resp = resps[0], resps[1], resps[2]
            if init_resp is None or init_resp.get("error"):
                raise RuntimeError(f"initialize 失败：{init_resp and init_resp.get('error')}")
            if list_resp is None or list_resp.get("error"):
                raise RuntimeError(f"tools/list 失败：{list_resp and list_resp.get('error')}")
            tools_list = (list_resp.get("result") or {}).get("tools") or []
        elif transport in ("sse", "http"):
            tools_list = []
            error_msg = "discover 未实现通用 SSE list；请手动 POST /api/admin/mcp/servers/{id}/discover 或直接配置 mcp_tool 行。"
        else:
            error_msg = f"不支持的 transport={transport} 做 discover"
    except Exception as exc:
        error_msg = f"discover 异常：{type(exc).__name__}: {exc}"[:512]
    if tools_list:
        # MCP-TRUTH 接线（修复 #5 dynamic_update 死代码）：同步动态工具注册表（无需重启会话感知
        # server 工具增减），差异事件仅记日志，不改变 discover 既有返回语义。
        try:
            _sync_dynamic_tools(server_id, tools_list)
        except Exception:  # noqa: BLE001 —— 动态注册表同步失败不阻断 discover
            pass
        try:
            n = await registry.upsert_discovered_tools(server_id, tools_list)
        except Exception as exc:
            error_msg = f"写入 mcp_tool 失败：{type(exc).__name__}: {exc}"[:512]
            n = 0
    else:
        n = 0
    # task33 GWT①：discover 后自动跑描述体检（打分 + <70 FAST 重写 + 审计日志）
    review_summary: dict | None = None
    if n > 0 and not error_msg:
        try:
            review_summary = await description_reviewer.run_description_review(
                server_id, operator_user_id=operator_user_id,
                trace_id=f"discover-{int(time.time()*1000)}",
            )
        except Exception as exc:  # noqa: BLE001 —— 体检失败不阻断 discover
            error_msg = f"描述体检异常：{type(exc).__name__}: {exc}"[:512]
    await registry.write_server_health(server_id, ok=(not error_msg), last_error=error_msg)
    out = {"count": n, "error": error_msg}
    if review_summary:
        out["review"] = review_summary
    return out


# ============================================================
# 内部工具
# ============================================================
def _extract_mcp_content_text(call_result: dict) -> str | None:
    """兼容：content 数组第一项 text；或直接返回字符串。"""
    if not isinstance(call_result, dict):
        return None
    content = call_result.get("content")
    if isinstance(content, list) and content:
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and "text" in item:
                return str(item["text"])
            if isinstance(item, str):
                return item
    if isinstance(call_result.get("text"), str):
        return call_result["text"]
    if content is None and "text" in call_result:
        return str(call_result["text"])
    return None


# ============================================================
# W-NEXT-MCP-001 步骤3（P0-③）：字段级脱敏 —— 落库前对 args/result 做 key 命中脱敏，
# 防止 admin token 泄漏 / DB 导出后含 password|token|secret|api_key|authorization 的明文裸奔。
# 仅此一层（公共落库入口），不在每处重复；args 与 result 均经同一入口，覆盖内置/远程双路径。
# ============================================================
_REDACT_KEY_RE = re.compile(r"(password|token|secret|api_key|authorization)", re.IGNORECASE)
_REDACTED = "***REDACTED***"
_TRUNCATE_LIMIT = 4096  # 单字段 JSON 超 4KB 截断，防超长载荷撑爆审计表


def _redact_sensitive(obj):
    """递归脱敏：dict 的 key 命中敏感词 → 值替 ***REDACTED***（值本身不递归，避免误伤嵌套结构）。

    非 dict/list 原样返回（字符串/数字/None 等）；list 逐元素脱敏。
    """
    if isinstance(obj, dict):
        return {
            k: (_REDACTED if _REDACT_KEY_RE.search(str(k)) else _redact_sensitive(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_sensitive(v) for v in obj]
    return obj


def _truncate_json(s: str | None) -> str | None:
    """单字段 JSON 超长截断（>4KB 加 ...truncated 后缀），防超长载荷。"""
    if s is None:
        return None
    if len(s) > _TRUNCATE_LIMIT:
        return s[:_TRUNCATE_LIMIT] + "...truncated"
    return s


async def _write_call_log(*, call_id: str, server_id: int, tool_name: str,
                          args: dict | list | None, result: Any, content_text: str | None,
                          status: ToolCallStatusEnum, latency_ms: int,
                          user_id: int, tenant_id: str, trace_id: str,
                          error_message: str | None) -> None:
    args_s: str | None
    try:
        # P0-③：落库前对 args 做字段级脱敏（key 命中敏感词 → 值替 ***REDACTED***）
        args_redacted = _redact_sensitive(args if args is not None else {})
        args_s = json.dumps(args_redacted, ensure_ascii=False)
    except Exception:
        args_s = None
    result_s: str | None
    try:
        payload: dict[str, Any] = {}
        if result is not None:
            # P0-③：result 同样脱敏（远程工具可能回显含敏感字段的请求体）
            payload["result"] = _redact_sensitive(result)
        if content_text is not None and "content_text" not in payload:
            payload["content_text"] = content_text
        result_s = json.dumps(payload, ensure_ascii=False) if payload else None
    except Exception:
        result_s = None
    # P0-③：超长截断（单字段 ≤4KB），防超长载荷撑爆审计表
    args_s = _truncate_json(args_s)
    result_s = _truncate_json(result_s)
    try:
        await execute_write(
            "INSERT INTO mcp_tool_call_log (call_id, server_id, tool_name, args_json, result_json,"
            " status, latency_ms, user_id, tenant_id, trace_id, error_message) VALUES "
            "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE "
            "  status=VALUES(status), latency_ms=VALUES(latency_ms), "
            "  error_message=VALUES(error_message), result_json=VALUES(result_json)",
            (call_id, server_id, tool_name, args_s, result_s, status.value,
             max(0, int(latency_ms)), int(user_id or 0),
             str(tenant_id or "")[:64], str(trace_id or "")[:64],
             (error_message or "")[:1024] or None),
        )
    except Exception as exc:
        logger.warning(f"写 MCP 调用日志失败：{exc}")


def _safe_json(s: Any, default_factory) -> Any:
    if s is None:
        return default_factory() if callable(default_factory) else default_factory
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except Exception:
        return default_factory() if callable(default_factory) else default_factory


# ============================================================
# 管理端调试面板专用（不落库或只读）
# ============================================================

# ---------- B. stdio checkpoint 长连接会话池（仅管理员调试用） ----------
_SESSION_LOCK = asyncio.Lock()
_SESSION_POOL: dict[str, dict] = {}  # session_id -> {server,proc,created_ms,last_used_ms,ttl_s,call_count,id_counter}
_SESSION_GC_LIMIT = 64  # 单进程实例最多保留多少会话（避免内存/句柄泄漏）


def _session_snapshot(session_id: str, s: dict) -> dict:
    proc = s.get("proc")
    try:
        pid = int(getattr(proc, "pid", 0) or 0)
    except Exception:
        pid = 0
    server: dict = s.get("server") or {}
    created_ms = int(s.get("created_ms") or 0)
    last_used_ms = int(s.get("last_used_ms") or 0)
    ttl_s = int(s.get("ttl_s") or 0)
    if time.time() * 1000 - last_used_ms > ttl_s * 1000 and last_used_ms > 0:
        state = "idle-timeout"
    elif proc is None or getattr(proc, "returncode", None) is not None:
        state = "closed"
    else:
        state = "active"
    return {
        "session_id": session_id,
        "server_id": int(server.get("id") or 0),
        "server_code": str(server.get("server_code") or ""),
        "pid": pid,
        "created_ms": created_ms,
        "last_used_ms": last_used_ms,
        "idle_gc_ttl_s": ttl_s,
        "call_count": int(s.get("call_count") or 0),
        "state": state,
        "last_error": s.get("last_error"),
        "hc": bool(s.get("hc")),          # B1：健康检查专用会话标记
        "hc_busy": bool(s.get("hc_busy")),  # B1：健康检查交换中（GC 豁免窗口）
    }


async def session_pool_gc(force_all: bool = False) -> int:
    """空闲 TTL 回收；超过全局上限按空闲最久优先收；返回关闭数量。"""
    removed = 0
    now_ms = time.time() * 1000
    async with _SESSION_LOCK:
        ordered = sorted(
            list(_SESSION_POOL.items()),
            key=lambda kv: int(kv[1].get("last_used_ms") or 0),
        )
        over = max(0, len(_SESSION_POOL) - _SESSION_GC_LIMIT)
        for sid, s in ordered:
            last = int(s.get("last_used_ms") or 0)
            ttl_s = int(s.get("ttl_s") or 0)
            idle_too_long = last > 0 and (now_ms - last) > (ttl_s * 1000)
            need_kill = force_all or idle_too_long or over > 0
            if not need_kill:
                continue
            if s.get("hc_busy") and not force_all:
                # B1：健康检查交换中的 hc 会话豁免（池化锁口径，防 GC 竞争误杀 mid-flight 会话）
                if over > 0:
                    over -= 1   # 名额让给下一个可回收会话，避免死循环式占用
                continue
            if over > 0:
                over -= 1
            proc = s.get("proc")
            try:
                if proc is not None and getattr(proc, "returncode", None) is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=1.5)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
            except Exception:
                pass
            _SESSION_POOL.pop(sid, None)
            removed += 1
    return removed


async def session_create(server_id: int, ttl_seconds: int, created_by_uid: int,
                         timeout_s_override: float | None = None) -> dict:
    """创建 stdio 长连接会话：initialize + initialized 成功后入池，返回 snapshot。

    timeout_s_override（B1）：hc 池化路径用它钳制建会话超时（默认 None=调试语义
    (connect+call)/1000+5s 宽限公式不变）；防 hung server 把健康检查拖进分钟级。
    """
    ttl_seconds = int(max(30, min(1800, int(ttl_seconds))))
    server = await fetch_one(
        "SELECT * FROM mcp_server WHERE id=%s AND yn=1 LIMIT 1",
        (int(server_id),),
    )
    if not server:
        return {"ok": False, "message": f"server_id={server_id} not found", "session": None}
    transport = str(server.get("transport") or "").lower()
    if transport != "stdio":
        return {"ok": False, "message": f"会话仅支持 stdio（transport={transport}）", "session": None}
    # 前置 GC 一次
    await session_pool_gc(force_all=False)
    connect_ms = int(server.get("connect_timeout_ms") or 5000)
    call_ms = int(server.get("call_timeout_ms") or 30_000)
    timeout_s = max(2.0, (connect_ms + call_ms) / 1000.0 + 5.0)
    if timeout_s_override is not None:
        timeout_s = max(2.0, float(timeout_s_override))

    run_command = server.get("run_command")
    if not run_command:
        return {"ok": False, "message": "server 未配置 run_command", "session": None}
    cmd: list[str] = [run_command]
    run_args = _safe_json(server.get("run_args_json") or "[]", list)
    if isinstance(run_args, list) and run_args:
        cmd.extend(str(a) for a in run_args)
    cwd = server.get("working_dir") or None
    if not cwd:
        try:
            cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        except Exception:
            cwd = None
    env = _build_server_env(dict(server), None)
    executable, *args_list = cmd
    try:
        proc = await asyncio.create_subprocess_exec(
            executable, *args_list,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd, env=env,
        )
    except NotImplementedError as exc:
        return {"ok": False, "message": f"create_subprocess_exec: {exc}", "session": None}
    except Exception as exc:
        return {"ok": False, "message": f"Popen 失败：{type(exc).__name__}: {exc}", "session": None}

    assert proc.stdin is not None and proc.stdout is not None
    # initialize + initialized
    reqs_init = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "edu-debug-session", "version": "0.2"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    ]
    results: dict[Any, dict] = {}
    deadline_ts = time.time() + timeout_s
    error_msg: str | None = None
    try:
        for idx, req in enumerate(reqs_init, start=1):
            if req.get("id") is not None:
                req["id"] = idx
            try:
                proc.stdin.write(_frame_encode(req))
                await proc.stdin.drain()
            except (BrokenPipeError, OSError) as exc:
                raise RuntimeError(f"stdin 写入失败：{exc}") from exc
        rid_expected = {1}
        while rid_expected and time.time() < deadline_ts:
            msg = await _frame_read(proc.stdout, deadline_ts)
            if msg is None:
                continue
            rid = msg.get("id")
            if rid is None:
                continue
            results[rid] = msg
            rid_expected.discard(rid)
        init_resp = results.get(1)
        if init_resp is None or init_resp.get("error"):
            raise RuntimeError(f"initialize 失败：{_short(init_resp)}")
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"[:512]

    if error_msg:
        try:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=1.2)
                except Exception:
                    proc.kill()
        except Exception:
            pass
        return {"ok": False, "message": error_msg, "session": None}

    session_id = "ms-" + uuid.uuid4().hex[:14]
    now_ms = int(time.time() * 1000)
    async with _SESSION_LOCK:
        _SESSION_POOL[session_id] = {
            "server": dict(server),
            "proc": proc,
            "created_ms": now_ms,
            "last_used_ms": now_ms,
            "ttl_s": ttl_seconds,
            "call_count": 0,
            "id_counter": 10,
            "last_error": None,
            "uid": int(created_by_uid or 0),
        }
    snapshot = _session_snapshot(session_id, _SESSION_POOL[session_id])
    return {"ok": True, "message": "session created", "session": snapshot}


async def session_get(session_id: str) -> dict | None:
    async with _SESSION_LOCK:
        s = _SESSION_POOL.get(session_id)
        if not s:
            return None
        return _session_snapshot(session_id, s)


async def session_list() -> list[dict]:
    async with _SESSION_LOCK:
        return [_session_snapshot(sid, s) for sid, s in _SESSION_POOL.items()]


async def session_ping(session_id: str) -> dict:
    async with _SESSION_LOCK:
        s = _SESSION_POOL.get(session_id)
        if not s:
            return {"ok": False, "message": f"session={session_id} not found", "session": None}
        s["last_used_ms"] = int(time.time() * 1000)
        return {"ok": True, "message": "touch ok", "session": _session_snapshot(session_id, s)}


async def session_close(session_id: str) -> dict:
    async with _SESSION_LOCK:
        s = _SESSION_POOL.pop(session_id, None)
    if not s:
        return {"ok": True, "message": f"session {session_id} already closed", "session": None}
    proc = s.get("proc")
    try:
        if proc is not None and getattr(proc, "returncode", None) is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=1.2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
    except Exception:
        pass
    return {"ok": True, "message": "closed",
            "session": _session_snapshot(session_id, {**s, "proc": None})}


async def _stdio_exchange_via_session(session_id: str, requests: list[dict], timeout_s: float,
                                      ) -> list[dict | None]:
    """通过已存在会话池的子进程发送 N 条 JSON-RPC，notification 返回 None，按顺序返回。"""
    async with _SESSION_LOCK:
        s = _SESSION_POOL.get(session_id)
        if not s:
            raise RuntimeError(f"session_id={session_id} 不存在")
        proc = s.get("proc")
        if proc is None or getattr(proc, "returncode", None) is not None:
            # 会话已死，清
            _SESSION_POOL.pop(session_id, None)
            raise RuntimeError(f"session_id={session_id} 子进程已退出")
        id_counter = int(s.get("id_counter") or 100)
        new_ids: dict[int, int] = {}  # {logical_pos+1 -> actual_id}
        reqs_final: list[dict] = []
        for pos, req in enumerate(requests):
            rid_none = req.get("id") is None
            is_notification = (req.get("method") or "").startswith("notifications/")
            cp = dict(req)
            if rid_none and not is_notification:
                id_counter += 1
                cp["id"] = id_counter
                new_ids[pos] = id_counter
            elif rid_none and is_notification:
                pass
            else:
                new_ids[pos] = int(cp["id"])
            reqs_final.append(cp)
        s["id_counter"] = id_counter
    assert proc is not None
    assert proc.stdin is not None and proc.stdout is not None
    deadline_ts = time.time() + timeout_s
    remaining: dict[int, int] = {v: k for k, v in new_ids.items()}  # actual_id -> pos
    results: dict[int, dict] = {}
    try:
        for req in reqs_final:
            try:
                proc.stdin.write(_frame_encode(req))
                await proc.stdin.drain()
            except (BrokenPipeError, OSError) as exc:
                raise RuntimeError(f"session 写入失败：{exc}") from exc
        while remaining and time.time() < deadline_ts:
            msg = await _frame_read(proc.stdout, deadline_ts)
            if msg is None:
                continue
            rid = msg.get("id")
            if rid is None:
                continue
            results[int(rid)] = msg
            remaining.pop(int(rid), None)
    except Exception:
        raise
    finally:
        async with _SESSION_LOCK:
            s2 = _SESSION_POOL.get(session_id)
            if s2:
                s2["last_used_ms"] = int(time.time() * 1000)
                s2["call_count"] = int(s2.get("call_count") or 0) + len(reqs_final)
    out: list[dict | None] = []
    for pos, req in enumerate(requests):
        if (req.get("method") or "").startswith("notifications/"):
            out.append(None)
            continue
        rid = new_ids.get(pos)
        out.append(results.get(rid))
    return out


# ============================================================
# B1（reshape-b）：健康检查专用池会话（server_id → hc_session 注册表）
# ------------------------------------------------------------
# 口径（contract-change-reshape-b-health-scan.md §2.3）：
#   · hc 会话与调试会话不混用：内部注册表 _HC_SESSION_BY_SERVER 单独登记，
#     池条目打 "hc" 标记，避免调试会话 GC/关闭波及健康检查；
#   · 池化锁：_HC_SESSION_LOCK 守卫注册表，_SESSION_LOCK 守卫池本体，
#     锁序恒为 _HC_SESSION_LOCK → _SESSION_LOCK（反向零依赖，防死锁）；
#   · GC 竞争：池条目在交换期间带 "hc_busy" 标记（_SESSION_LOCK 内读写），
#     session_pool_gc 对在检会话豁免（force_all 除外），防误杀 mid-flight 会话；
#   · 同 server 并发检查：per-server 交换锁 _HC_XCHG_LOCKS 串行化 ping 帧
#     （单条 stdio pipe 上并发读会互相偷帧，必须串行）。
# ============================================================
_HC_SESSION_BY_SERVER: dict[int, str] = {}
_HC_SESSION_LOCK = asyncio.Lock()
_HC_XCHG_LOCKS: dict[int, asyncio.Lock] = {}


async def _hc_session_alive_locked(reg_sid: str) -> tuple[bool, dict | None]:
    """在持 _HC_SESSION_LOCK 前提下查池内会话存活（内部再取 _SESSION_LOCK，锁序安全）。"""
    async with _SESSION_LOCK:
        s = _SESSION_POOL.get(reg_sid)
        alive = (s is not None and s.get("proc") is not None
                 and getattr(s["proc"], "returncode", None) is None)
        return alive, s


async def _hc_session_acquire(server: dict) -> tuple[str | None, str | None]:
    """取/建该 server 的 hc 专用池会话。

    返回 (session_id, create_error)：
      (sid, None)      → 命中/新建成功（已置 hc_busy）；
      (None, msg)      → 建池握手失败（spawn 失败/initialize 超时）——即完整握手证据，
                         调用方可直接定论不健康（变更单 §2.3：不二次 spawn 双倍付费）；
      (None, None)     → 参数非法等瞬时不可用，调用方回退一次性 spawn 兜底。
    """
    sid = int(server.get("id") or 0)
    if sid <= 0:
        return None, None
    async with _HC_SESSION_LOCK:
        reg_sid = _HC_SESSION_BY_SERVER.get(sid)
        if reg_sid:
            alive, s = await _hc_session_alive_locked(reg_sid)
            if alive:
                s["hc_busy"] = True
                s["last_used_ms"] = int(time.time() * 1000)
                return reg_sid, None
            _HC_SESSION_BY_SERVER.pop(sid, None)   # 僵死/已死 → 摘注册表，重建
    # 未命中：per-server 单飞行建会话（防同 server 并发重复 spawn；不持全局锁，不阻塞其他 server）
    xchg_lock = _HC_XCHG_LOCKS.get(sid)
    if xchg_lock is None:
        xchg_lock = asyncio.Lock()
        _HC_XCHG_LOCKS[sid] = xchg_lock
    async with xchg_lock:
        async with _HC_SESSION_LOCK:
            reg_sid = _HC_SESSION_BY_SERVER.get(sid)
            if reg_sid:
                alive, s = await _hc_session_alive_locked(reg_sid)
                if alive:
                    s["hc_busy"] = True
                    s["last_used_ms"] = int(time.time() * 1000)
                    return reg_sid, None
                _HC_SESSION_BY_SERVER.pop(sid, None)
        # B1：建会话超时按健康检查口径钳制（connect_timeout/1000 + 2s 余量），
        # 而非调试会话的 (connect+call)/1000+5s 宽限公式——防 hung server 把
        # 健康检查拖进分钟级（首轮回归实测 challenge_dup 45s 教训）。
        hc_timeout_s = max(2.0, int(server.get("connect_timeout_ms") or 5000) / 1000.0)
        res = await session_create(
            server_id=sid, ttl_seconds=settings.MCP_HC_SESSION_TTL_S, created_by_uid=0,
            timeout_s_override=hc_timeout_s + 2.0,
        )
        if not res.get("ok"):
            return None, str(res.get("message") or "session create failed")[:300]
        new_sid = str((res.get("session") or {}).get("session_id") or "")
        if not new_sid:
            return None, "session create 返回缺少 session_id"
        async with _HC_SESSION_LOCK:
            async with _SESSION_LOCK:
                s_new = _SESSION_POOL.get(new_sid)
                if s_new is not None:
                    s_new["hc"] = True
                    s_new["hc_busy"] = True
            _HC_SESSION_BY_SERVER[sid] = new_sid
        return new_sid, None


async def _hc_session_release(server_id: int, session_id: str, *, drop: bool = False) -> None:
    """清 hc_busy；drop=True 时另摘注册表并关闭坏会话（幂等：重复调用/会话已被换均安全）。"""
    if drop:
        async with _HC_SESSION_LOCK:
            if _HC_SESSION_BY_SERVER.get(server_id) == session_id:
                _HC_SESSION_BY_SERVER.pop(server_id, None)
    async with _SESSION_LOCK:
        s = _SESSION_POOL.get(session_id)
        if s is not None:
            s["hc_busy"] = False
    if drop:
        await session_close(session_id)   # 杀进程+摘池（幂等，已不存在亦无害）


async def _stdio_health_via_pool(server: dict, timeout_s: float) -> tuple[bool, str | None, bool]:
    """stdio 单台健康检查走 sessions 池长连通道（只发一条 ping，initialize 已在入池时完成）。

    返回 (ok, reason, concluded)：
      concluded=True  → 池通道已给出健康结论，调用方直接采用
                        （含建池握手失败=不健康定论，变更单 §2.3，不二次 spawn）；
      concluded=False → 池通道基础设施故障（会话僵死/帧异常），调用方退一次性 spawn 兜底，
                        保证池故障永远不会把健康 server 误报为不健康。
    """
    server_id = int(server.get("id") or 0)
    # MCP-TRUTH 接线（修复 #5 reconnect 死代码）：建会话失败 → with_reconnect 指数退避重连，
    # 重连耗尽才定论不健康（concluded=True），语义与旧「一次 spaw 握手失败=不健康」对齐但多一层容错。
    try:
        session_id = await _mcp_reconnect.with_reconnect(
            _make_hc_reconnect_connect(server),
            policy=_mcp_reconnect.ReconnectPolicy(
                max_retries=int(getattr(settings, "MCP_HC_RECONNECT_MAX", 2)),
                base_delay_s=0.2, factor=2.0, max_delay_s=2.0,
            ),
        )
        session_id = str(session_id)
    except _mcp_reconnect.ReconnectExhausted as exc:
        return False, f"stdio hc handshake: {exc}", True
    if not session_id:
        return False, None, False
    xchg_lock = _HC_XCHG_LOCKS.get(server_id)
    if xchg_lock is None:   # 防御：acquire 未命中路径也应有一把锁
        xchg_lock = asyncio.Lock()
        _HC_XCHG_LOCKS[server_id] = xchg_lock
    try:
        async with xchg_lock:   # 单条 stdio pipe 串行化：并发读会互偷帧
            resps = await asyncio.wait_for(
                _stdio_exchange_via_session(
                    session_id, [{"jsonrpc": "2.0", "method": "ping"}], timeout_s,
                ),
                timeout=timeout_s + 2.0,
            )
    except Exception as exc:
        await _hc_session_release(server_id, session_id, drop=True)
        return False, None, False   # 池通道故障 → 本次退一次性 spawn 兜底
    try:
        ping_resp = resps[0] if resps else None
        if ping_resp is not None and ping_resp.get("error"):
            # server 在线但返回 JSON-RPC error → 结论=不健康（会话仍活着，保留）
            await _hc_session_release(server_id, session_id)
            return False, f"stdio pool ping error: {_short(ping_resp)}", True
        if ping_resp is not None and ping_resp.get("result") is not None:
            await _hc_session_release(server_id, session_id)
            return True, None, True
        # 无响应帧：会话可能僵死（半开管道）→ 弃会话，本次退一次性 spawn 兜底
        await _hc_session_release(server_id, session_id, drop=True)
        return False, None, False
    except Exception:
        await _hc_session_release(server_id, session_id, drop=True)
        return False, None, False


async def live_discover_tools(server_id: int) -> dict:
    """直接连接 Server 取 tools/list（不落库 mcp_tool，调试面板用）。同时支持 stdio / sse / http。"""
    t0 = time.perf_counter()
    server = await fetch_one(
        "SELECT * FROM mcp_server WHERE id=%s AND yn=1 LIMIT 1",
        (int(server_id),),
    )
    if server is None:
        return {"server_id": server_id, "ok": False, "tool_count": 0, "tools": [],
                "reason": f"server_id={server_id} 不存在", "latency_ms": 0}
    transport = str(server.get("transport") or "").lower()
    tools_list: list[dict] = []
    error_msg: str | None = None
    try:
        connect_ms = int(server.get("connect_timeout_ms") or 5000)
        call_ms = int(server.get("call_timeout_ms") or 30_000)
        timeout_s = max(2.0, (connect_ms + call_ms) / 1000.0 + 5.0)
        if transport == "stdio":
            reqs = [
                {"jsonrpc": "2.0", "method": "initialize",
                 "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "edu-debug", "version": "0.1"}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "method": "tools/list", "params": {}},
            ]
            resps = await asyncio.wait_for(
                _stdio_exchange_async(dict(server), reqs, timeout_s),
                timeout=timeout_s + 10.0,
            )
            init_resp, _, list_resp = resps[0], resps[1], resps[2]
            if init_resp is None or init_resp.get("error"):
                raise RuntimeError(f"initialize 失败：{_short(init_resp)}")
            if list_resp is None or list_resp.get("error"):
                raise RuntimeError(f"tools/list 失败：{_short(list_resp)}")
            tools_list = (list_resp.get("result") or {}).get("tools") or []
        elif transport in ("sse", "http"):
            base_url = str(server.get("base_url") or "")
            if not base_url:
                raise RuntimeError("base_url 为空")
            # MCP HTTP 实现：走 JSON-RPC（initialize + notifications/initialized 走 headers；再 POST tools/list）
            headers = {"mcp-client-name": "edu-debug", "mcp-client-version": "0.1"}
            init_body = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                    "clientInfo": {"name": "edu-debug", "version": "0.1"}}}
            init_resp = await _http_request_jsonrpc(
                base_url, init_body, headers=headers,
                timeout_connect_ms=connect_ms, timeout_total_ms=int(timeout_s * 1000),
            )
            if init_resp.get("error"):
                raise RuntimeError(f"HTTP initialize 失败：{_short(init_resp)}")
            list_body = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            list_resp = await _http_request_jsonrpc(
                base_url, list_body, headers=headers,
                timeout_connect_ms=connect_ms, timeout_total_ms=int(timeout_s * 1000),
            )
            if list_resp.get("error"):
                raise RuntimeError(f"HTTP tools/list 失败：{_short(list_resp)}")
            tools_list = (list_resp.get("result") or {}).get("tools") or []
        else:
            error_msg = f"live_discover 不支持的 transport={transport}"
    except Exception as exc:
        error_msg = f"live_discover 异常：{type(exc).__name__}: {exc}"[:512]
    normalized = []
    for t in tools_list:
        if not isinstance(t, dict):
            continue
        tname = str(t.get("name") or "")
        if not tname:
            continue
        schema = t.get("inputSchema") if isinstance(t.get("inputSchema"), dict) else {}
        normalized.append({
            "tool_name": tname,
            "display_name": t.get("displayName") or t.get("label") or tname,
            "description": t.get("description") or "",
            "input_schema": schema,
            "category": "",
        })
    cost = int((time.perf_counter() - t0) * 1000)
    return {
        "server_id": server_id,
        "ok": error_msg is None,
        "tool_count": len(normalized),
        "tools": normalized,
        "reason": error_msg,
        "latency_ms": cost,
    }


async def raw_rpc_call(server_id: int, method: str, params: dict | None = None,
                       call_timeout_ms: int | None = None,
                       session_id: str | None = None) -> dict:
    """管理员直连 Server 发 JSON-RPC；返回含 session_id（若复用会话）。
    - stdio + session_id：走会话池（跳过 initialize）
    - stdio 无 session_id：一次性拉起（initialize + target）
    - sse/http：POST base_url（无会话概念）
    """
    t0 = time.perf_counter()
    server = await fetch_one(
        "SELECT * FROM mcp_server WHERE id=%s AND yn=1 LIMIT 1",
        (int(server_id),),
    )
    if server is None:
        return {"server_id": server_id, "ok": False, "method": method,
                "result": None, "error": {"code": 404, "message": f"server_id={server_id} 不存在"},
                "latency_ms": 0, "session_id": None}
    transport = str(server.get("transport") or "").lower()
    connect_ms = int(server.get("connect_timeout_ms") or 5000)
    call_ms = int(call_timeout_ms or server.get("call_timeout_ms") or 30_000)
    timeout_s = max(2.0, (connect_ms + call_ms) / 1000.0 + 5.0)
    resp_obj: dict | None = None
    error_msg: str | None = None
    used_session: str | None = None
    try:
        if transport == "stdio":
            if session_id:
                used_session = str(session_id)
                reqs = [{"jsonrpc": "2.0", "method": method, "params": dict(params or {})}]
                resps = await asyncio.wait_for(
                    _stdio_exchange_via_session(used_session, reqs, timeout_s),
                    timeout=timeout_s + 10.0,
                )
                resp_obj = resps[0]
                if resp_obj is None:
                    raise RuntimeError("session raw_rpc 未收到响应帧（检查方法名/参数）")
            else:
                reqs = [
                    {"jsonrpc": "2.0", "method": "initialize",
                     "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                "clientInfo": {"name": "edu-debug", "version": "0.1"}}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "method": method, "params": dict(params or {})},
                ]
                resps = await asyncio.wait_for(
                    _stdio_exchange_async(dict(server), reqs, timeout_s),
                    timeout=timeout_s + 10.0,
                )
                init_resp = resps[0]
                if init_resp is None or init_resp.get("error"):
                    raise RuntimeError(f"initialize 失败：{_short(init_resp)}")
                resp_obj = resps[2]
        elif transport in ("sse", "http"):
            base_url = str(server.get("base_url") or "")
            if not base_url:
                raise RuntimeError("base_url 为空")
            headers = {"mcp-client-name": "edu-debug", "mcp-client-version": "0.1"}
            # MCP 2024: 若服务端要求 initialize 前置，则先做一次（失败不致命：某些 server 懒初始化）
            if method not in {"initialize", "ping"}:
                try:
                    init_body = {"jsonrpc": "2.0", "id": 9000, "method": "initialize",
                                 "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                            "clientInfo": {"name": "edu-debug", "version": "0.1"}}}
                    await _http_request_jsonrpc(
                        base_url, init_body, headers=headers,
                        timeout_connect_ms=connect_ms,
                        timeout_total_ms=int(timeout_s * 1000),
                    )
                except Exception:
                    pass
            body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": dict(params or {})}
            resp_obj = await _http_request_jsonrpc(
                base_url, body, headers=headers,
                timeout_connect_ms=connect_ms,
                timeout_total_ms=int(timeout_s * 1000),
            )
        else:
            raise RuntimeError(f"raw_rpc 不支持的 transport={transport}")
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"[:512]
    cost = int((time.perf_counter() - t0) * 1000)
    if error_msg:
        return {"server_id": server_id, "ok": False, "method": method,
                "result": None, "error": {"code": -1, "message": error_msg},
                "latency_ms": cost, "session_id": used_session}
    if resp_obj is None:
        return {"server_id": server_id, "ok": False, "method": method,
                "result": None, "error": {"code": -2, "message": "stdout/HTTP 无响应（timeout/空消息）"},
                "latency_ms": cost, "session_id": used_session}
    err = resp_obj.get("error")
    if err:
        err_dict = err if isinstance(err, dict) else {"code": -3, "message": str(err)}
        return {"server_id": server_id, "ok": False, "method": method,
                "result": None, "error": err_dict,
                "latency_ms": cost, "session_id": used_session}
    return {"server_id": server_id, "ok": True, "method": method,
            "result": resp_obj.get("result"), "error": None,
            "latency_ms": cost, "session_id": used_session}


async def scan_all_servers_health(progress_cb: Any = None) -> dict:
    """对所有 yn=1 的 MCP Server 批量做健康检查。

    progress_cb(done:int, total:int) 可选：B1 异步 job 用它回写进度（同步回调，
    逐台完成后调用；旧同步端点不传，行为与 B1 前完全一致）。
    """
    from app.database import fetch_all
    t0 = time.perf_counter()
    rows = await fetch_all(
        "SELECT id,server_code,display_name,last_health_at,last_health_ok,last_error "
        "FROM mcp_server WHERE yn=1 ORDER BY id ASC",
    )
    items: list[dict] = []
    ok_c = 0
    for idx, r in enumerate(rows, start=1):
        sid = int(r["id"])
        try:
            hc = await health_check_server(sid)
        except Exception as exc:
            hc = {"ok": False, "latency_ms": 0, "reason": f"{type(exc).__name__}: {exc}"[:200]}
        ok_flag = bool(hc.get("ok"))
        if ok_flag:
            ok_c += 1
        items.append({
            "server_id": sid,
            "server_code": str(r.get("server_code") or ""),
            "display_name": str(r.get("display_name") or ""),
            "ok": ok_flag,
            "latency_ms": int(hc.get("latency_ms") or 0),
            "reason": hc.get("reason"),
            "last_health_at": r.get("last_health_at"),
        })
        if progress_cb is not None:
            try:
                progress_cb(idx, len(rows))
            except Exception:
                pass
    elapsed = int((time.perf_counter() - t0) * 1000)
    return {
        "scanned": len(items),
        "ok_count": ok_c,
        "error_count": len(items) - ok_c,
        "items": items,
        "elapsed_ms": elapsed,
    }


# ============================================================
# B1（reshape-b）：health-scan 异步 job 存储（进程内存 + TTL，single-flight 幂等）
# 契约：contracts/reshape-b.json（冻结）
#   · POST /api/mcp/health-scan-async → 202 {job_id}，同参重复 POST 幂等返回同一 job_id
#   · GET /api/mcp/health-scan/{job_id} → {status: running|done, result}；未知 job → 404/40450
# 单实例演示架构不引入 Redis（变更单 §2.2 备案：调试域 job 不值得跨实例持久化）。
# ============================================================
_HC_SCAN_JOBS: dict[str, dict] = {}          # job_id -> job dict（含 task 引用）
_HC_SCAN_JOBS_LOCK = asyncio.Lock()          # job 表池化锁：幂等判定/GC/终态写入串行化
_HC_SCAN_JOB_TTL_MS = 10 * 60 * 1000         # done job 保留 10 分钟，过期摘除（→ 40450）
_HC_SCAN_JOB_MAX = 32                        # 防内存膨胀：超上限按完成时间最旧优先摘


def _hc_scan_job_snapshot(job: dict) -> dict:
    """job 只读快照（GET 轮询响应 data；契约字段 job_id/status/result 恒在）。"""
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "created_ms": job["created_ms"],
        "finished_ms": job.get("finished_ms"),
        "progress": {"scanned": int(job.get("scanned_done") or 0),
                     "total": int(job.get("scanned_total") or 0)},
        "result": job.get("result"),
    }


def _hc_scan_jobs_gc_locked(now_ms: int) -> int:
    """摘除过期 done job + 超上限最旧优先（调用方须持 _HC_SCAN_JOBS_LOCK；纯内存操作）。"""
    expired = [
        jid for jid, j in _HC_SCAN_JOBS.items()
        if j["status"] == "done" and j.get("finished_ms")
        and (now_ms - int(j["finished_ms"])) > _HC_SCAN_JOB_TTL_MS
    ]
    for jid in expired:
        _HC_SCAN_JOBS.pop(jid, None)
    over = max(0, len(_HC_SCAN_JOBS) - _HC_SCAN_JOB_MAX)
    if over > 0:
        done_sorted = sorted(
            (j for j in _HC_SCAN_JOBS.values() if j["status"] == "done"),
            key=lambda j: int(j.get("finished_ms") or 0),
        )
        for j in done_sorted[:over]:
            _HC_SCAN_JOBS.pop(j["job_id"], None)
    return len(expired)


async def _health_scan_job_runner(job: dict) -> None:
    """后台扫描任务：串行逐台检查（与同步端点同引擎），逐台回写进度，终态写入持锁。"""
    def _progress(done: int, total: int) -> None:
        job["scanned_done"] = int(done)
        job["scanned_total"] = int(total)

    try:
        result = await scan_all_servers_health(progress_cb=_progress)
    except Exception as exc:
        # 扫描器逐台吞错，理论上到不了这里；兜底成 done（绝不留永挂 running 的 job 毒化幂等）
        logger.error(f"health-scan job={job['job_id']} runner 异常: {exc}")
        result = {"scanned": 0, "ok_count": 0, "error_count": 0, "items": [], "elapsed_ms": 0}
    job["result"] = result
    async with _HC_SCAN_JOBS_LOCK:
        job["status"] = "done"
        job["finished_ms"] = int(time.time() * 1000)


async def health_scan_async_start() -> dict:
    """POST /health-scan-async 主体：202 受理；已有 running job → 幂等复用同一 job_id（用户签字①）。"""
    async with _HC_SCAN_JOBS_LOCK:
        _hc_scan_jobs_gc_locked(int(time.time() * 1000))
        for j in _HC_SCAN_JOBS.values():
            if j["status"] == "running":
                return {"job_id": j["job_id"], "status": "running",
                        "created_ms": j["created_ms"], "scanned_total": int(j.get("scanned_total") or 0),
                        "already_running": True}
        from app.database import fetch_one
        cnt_row = await fetch_one("SELECT COUNT(*) AS c FROM mcp_server WHERE yn=1")
        job_id = "hs-" + uuid.uuid4().hex[:12]
        job = {
            "job_id": job_id, "status": "running",
            "created_ms": int(time.time() * 1000), "finished_ms": None,
            "scanned_total": int((cnt_row or {}).get("c") or 0), "scanned_done": 0,
            "result": None,
        }
        _HC_SCAN_JOBS[job_id] = job
    job["task"] = asyncio.create_task(_health_scan_job_runner(job))
    return {"job_id": job_id, "status": "running", "created_ms": job["created_ms"],
            "scanned_total": job["scanned_total"], "already_running": False}


async def health_scan_job_status(job_id: str) -> dict | None:
    """GET /health-scan/{job_id} 主体：未知/已过期 job 返回 None（router 层转 404/40450）。"""
    async with _HC_SCAN_JOBS_LOCK:
        _hc_scan_jobs_gc_locked(int(time.time() * 1000))
        job = _HC_SCAN_JOBS.get(str(job_id or ""))
        if job is None:
            return None
        return _hc_scan_job_snapshot(job)
