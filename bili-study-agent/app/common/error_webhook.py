# -*- coding: utf-8 -*-
"""C5-K3：500 错误上报通道（可选 ERROR_WEBHOOK_URL）。

设计约束：
- 非 DEBUG 且设置 ERROR_WEBHOOK_URL 时，global_exception_handler 对 500 级异常
  fire-and-forget POST 精简载荷（trace_id / 时间 / 异常类型 / 堆栈首 2000 字符）；
- 发送失败静默（任何异常吞掉 + WARN），绝不影响错误响应本身；
- DEBUG 模式一律不发（本地开发零外呼）；
- **响应契约零变更**：50301/50000 脱敏判定（main.py）完全不动，本模块只做旁路上报。
"""
from __future__ import annotations

import traceback
from datetime import datetime, timezone

from app.common.logging import logger

# 堆栈截断上限（C5-K3 规格）
_STACK_MAX_CHARS = 2000
# 上报超时（秒，C5-K3 规格）
WEBHOOK_TIMEOUT_SECONDS = 2.0


def build_error_webhook_payload(trace_id: str, exc: BaseException) -> dict:
    """构造精简上报载荷（不含请求体/用户数据，避免二次泄漏）。"""
    stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return {
        "trace_id": trace_id or "",
        "time": datetime.now(timezone.utc).isoformat(),
        "exception_type": type(exc).__name__,
        "stack": stack[:_STACK_MAX_CHARS],
    }


async def post_error_webhook(url: str, payload: dict) -> None:
    """POST 载荷到 webhook；失败静默（WARN 日志），永不抛出。"""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                logger.warning(
                    f"[error-webhook] 上报端返回非 2xx: {resp.status_code}（静默忽略）"
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[error-webhook] 上报失败（静默忽略，不影响错误响应）: {type(exc).__name__}: {exc}")
