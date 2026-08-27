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
import hashlib
import json
import os
import time
import uuid
from typing import Any

from app.common.exceptions import AppException
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
    """只读工具可走 60s 同参缓存；明显写语义工具跳过（避免缓存非幂等副作用）。"""
    lowered = (tool_name or "").lower()
    if any(lowered.startswith(p) for p in _WRITE_TOOL_PREFIXES):
        return False
    return True


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
async def call_tool(*,
                    operator_user_id: int,
                    tenant_id: str = "",
                    trace_id: str = "",
                    tool_id: int | None = None,
                    server_id: int | None = None,
                    tool_name: str | None = None,
                    args: dict[str, Any] | None = None,
                    call_id: str | None = None,
                    ) -> MCPToolTestResp:
    args = args or {}
    tool_row = await registry.get_tool_by_ref(tool_id, server_id, tool_name)
    server_id_eff = int(tool_row["server_id"])
    tool_name_eff = str(tool_row["tool_name"])
    server = await fetch_one("SELECT * FROM mcp_server WHERE id=%s AND yn=1 LIMIT 1", (server_id_eff,))
    if not server:
        raise _raise(404, "关联 server 已删除")
    if int(server.get("enabled") or 0) != 1:
        raise _raise(412, f"server_code={server.get('server_code')} 已禁用（enabled=0）")

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


async def _default_attempt_executor(tool_name: str, args: dict, *, call_id: str, attempt: int,
                                    operator_user_id: int, tenant_id: str, trace_id: str) -> AttemptOutcome:
    """生产默认执行器：按工具名解析 server，走单步核心。

    找不到工具 / server 禁用 / 已删 → 视为失败（非拒绝，不计入拒绝熔断），
    让闭环继续走向换工具或人工指南（AC1 不在此处中断）。
    """
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


async def call_tool_with_retry(*, operator_user_id: int, tenant_id: str = "", trace_id: str = "",
                               session_id: str = "", tool_id: int | None = None,
                               server_id: int | None = None, tool_name: str | None = None,
                               args: dict | None = None, call_id: str | None = None,
                               llm_rewrite_fn=None,
                               _attempt_executor=None, _reject_store=None) -> MCPToolTestResp:
    """task-T1 工具调用闭环：换参 → 换工具 → 熔断 → 人工指南（AC1~AC4）。

    - 第 1 步正常；第 2 步换参数（LLM 改写 args，或规则跳级兜底）；
      第 3 步换备用工具（TOOL_FALLBACK_MAP）；第 4 步输出结构化人工指南并停止（AC1/AC2）。
    - 同会话内连续被拒达 TOOL_CONSECUTIVE_REJECTIONS → 第 4 次尝试直接中断（AC3）。
    - 每步产出 {attempt,action,tool_name,args,outcome,latency_ms} 事件 + trace_id（AC4）。
    - 保留 task33 既有契约：per-server 熔断 / 只读缓存 / 审计日志（call_tool 单步路径不变）。
    """
    args = args or {}
    fallback_map = settings.TOOL_FALLBACK_MAP
    max_attempts = settings.MAX_TOOL_ATTEMPTS
    consecutive_rej = settings.TOOL_CONSECUTIVE_REJECTIONS
    reject_ttl = settings.TOOL_REJECT_TTL_S
    use_llm_rewrite = settings.TOOL_RETRY_LLM_REWRITE

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
            if is_error:
                raise RuntimeError(content_text or "MCP tool isError=true")
            try:
                result_parsed = json.loads(content_text) if content_text is not None else None
            except Exception:
                result_parsed = content_text
        elif transport in ("sse", "http"):
            headers = _safe_json(server.get("http_headers_json") or "{}", dict)
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
            if init_resp and init_resp.get("result") and ping_resp and ping_resp.get("result"):
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


async def _write_call_log(*, call_id: str, server_id: int, tool_name: str,
                          args: dict | list | None, result: Any, content_text: str | None,
                          status: ToolCallStatusEnum, latency_ms: int,
                          user_id: int, tenant_id: str, trace_id: str,
                          error_message: str | None) -> None:
    args_s: str | None
    try:
        args_s = json.dumps(args if args is not None else {}, ensure_ascii=False)
    except Exception:
        args_s = None
    result_s: str | None
    try:
        payload: dict[str, Any] = {}
        if result is not None:
            payload["result"] = result
        if content_text is not None and "content_text" not in payload:
            payload["content_text"] = content_text
        result_s = json.dumps(payload, ensure_ascii=False) if payload else None
    except Exception:
        result_s = None
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


async def session_create(server_id: int, ttl_seconds: int, created_by_uid: int) -> dict:
    """创建 stdio 长连接会话：initialize + initialized 成功后入池，返回 snapshot。"""
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


async def scan_all_servers_health() -> dict:
    """对所有 yn=1 的 MCP Server 批量做健康检查。"""
    from app.database import fetch_all
    t0 = time.perf_counter()
    rows = await fetch_all(
        "SELECT id,server_code,display_name,last_health_at,last_health_ok,last_error "
        "FROM mcp_server WHERE yn=1 ORDER BY id ASC",
    )
    items: list[dict] = []
    ok_c = 0
    for r in rows:
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
    elapsed = int((time.perf_counter() - t0) * 1000)
    return {
        "scanned": len(items),
        "ok_count": ok_c,
        "error_count": len(items) - ok_c,
        "items": items,
        "elapsed_ms": elapsed,
    }
