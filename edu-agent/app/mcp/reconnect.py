# -*- coding: utf-8 -*-
"""task95 R3(4)：自动重连 —— stdio 进程退出 / HTTP 会话过期后指数退避重连。

修复 self-critique 维度 2 结构性缺陷：MCP 缺自动重连（仅超时 + 熔断）。

对标 Claude Code mcp.md：自动重连（server 退出后自动恢复）、动态工具更新。
  URL: https://docs.claude.com/en/docs/claude-code/mcp

退避策略：delay = min(max_delay, base * factor**attempt)，attempt 0-based；
最多重试 max_retries 次（默认 5）。sleep / clock 可注入，便于无网、瞬时单测。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional


@dataclass
class ReconnectPolicy:
    max_retries: int = 5
    base_delay_s: float = 1.0
    factor: float = 2.0
    max_delay_s: float = 30.0


def backoff_delay(attempt: int, policy: ReconnectPolicy) -> float:
    """第 attempt 次重试前的等待秒数（0-based）。"""
    d = policy.base_delay_s * (policy.factor ** attempt)
    return min(d, policy.max_delay_s)


class ReconnectExhausted(Exception):
    """重连耗尽后抛出（连续失败超过 max_retries）。"""


async def with_reconnect(
    connect: Callable[[], Awaitable[Any]],
    *,
    policy: Optional[ReconnectPolicy] = None,
    on_down: Optional[Callable[[int], Awaitable[None]]] = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.time,
) -> Any:
    """执行 connect()；若失败（连接断开/进程退出）按指数退避自动重连。

    - 成功：返回连接对象。
    - 连续失败超过 max_retries：抛 ReconnectExhausted。
    - 每次重试前调用 on_down(attempt)（用于健康标记/告警）。
    - clock 仅用于记录（保留扩展位），当前逻辑不依赖绝对时间。
    """
    policy = policy or ReconnectPolicy()
    last_exc: Optional[Exception] = None
    for attempt in range(policy.max_retries + 1):
        try:
            conn = await connect()
            return conn
        except Exception as exc:  # noqa: BLE001 —— 任何连接异常都触发重连
            last_exc = exc
            if attempt >= policy.max_retries:
                break
            if on_down is not None:
                try:
                    await on_down(attempt)
                except Exception:
                    pass
            delay = backoff_delay(attempt, policy)
            await sleep(delay)
    _ = clock  # 预留：未来如需按绝对超时截断
    raise ReconnectExhausted(
        f"重连 {policy.max_retries} 次仍失败：{type(last_exc).__name__}: {last_exc}"
    ) from last_exc
