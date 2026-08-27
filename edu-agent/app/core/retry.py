"""
智能重试退避（task-G1，production-upgrade-plan P5；联动 task-T1 工具闭环状态机）。

按错误类型动态退避（非固定重试）：
- 限流（429 / RateLimit / too many requests）→ 指数退避 2^n 秒（n=重试次数），封顶 30s + jitter；
- 超时（Timeout / timed out）→ 线性退避 1s/次，最多 2 次；
- 模型错误（invalid_request / model_error）→ 立即切换备用模型（FAST↔STRONG），不重试同模型（wait=0）；
- 其余（unknown）→ 1 次重试后交 task-T1 工具闭环处理。

纯函数，无外部依赖，可单测。调用方（generator.py / agent.py 重试路径）按 classify_error 归类后
调用 next_backoff 计算等待秒数，模型错误时按 should_switch_model 切源。

对齐通用云 LLM 网关「智能重试退避（按错误类型动态）」生产实证（P5 引述）。
"""
from __future__ import annotations

import random
from enum import Enum
from typing import Any


class ErrorCategory(str, Enum):
    RATE_LIMIT = "rate_limit"      # 限流：429 / RateLimitError
    TIMEOUT = "timeout"            # 超时：Timeout / timed out
    MODEL_ERROR = "model_error"    # 模型错误：invalid_request / model_error
    UNKNOWN = "unknown"            # 其余：交 task-T1 工具闭环


# 各错误类型最大重试次数（超过后交上层处理）
MAX_RETRIES: dict[ErrorCategory, int] = {
    ErrorCategory.RATE_LIMIT: 5,
    ErrorCategory.TIMEOUT: 2,
    ErrorCategory.MODEL_ERROR: 0,   # 不重试同模型，立即切源
    ErrorCategory.UNKNOWN: 1,
}

# 双源模型（FAST↔STRONG）切换表
_MODEL_SOURCES = ("fast", "strong")


def classify_error(exc: Any) -> ErrorCategory:
    """将异常（或字符串）归类为错误类型。接受 Exception / 字符串 / ErrorCategory 透传。"""
    if exc is None:
        return ErrorCategory.UNKNOWN
    if isinstance(exc, ErrorCategory):
        return exc
    if isinstance(exc, str):
        s = exc.lower()
    else:
        name = type(exc).__name__.lower()
        try:
            args0 = exc.args[0] if getattr(exc, "args", None) else ""
        except Exception:
            args0 = ""
        s = f"{name} {exc} {args0}".lower()

    if "ratelimit" in s or "429" in s or "too many requests" in s or "rate_limit" in s:
        return ErrorCategory.RATE_LIMIT
    if "timeout" in s or "timed out" in s:
        return ErrorCategory.TIMEOUT
    if "model_error" in s or "invalid_request" in s or "model" in s and "error" in s:
        return ErrorCategory.MODEL_ERROR
    return ErrorCategory.UNKNOWN


def next_backoff(
    category: Any,
    attempt: int,
    *,
    base: float = 1.0,
    cap: float = 30.0,
    jitter: float = 0.0,
) -> float:
    """计算第 ``attempt`` 次（1-based）重试前的等待秒数。

    - RATE_LIMIT：2^attempt 秒（2,4,8,…），封顶 cap，可加 jitter；
    - TIMEOUT：线性 base*attempt 秒（1,2,…），封顶 cap；
    - MODEL_ERROR：0 秒（立即切源，不等待）；
    - UNKNOWN：base*attempt 秒（1 次后交 task-T1）。
    """
    cat = classify_error(category)
    attempt = max(1, int(attempt))
    if cat == ErrorCategory.RATE_LIMIT:
        wait = min(2.0 ** attempt, cap)
    elif cat == ErrorCategory.TIMEOUT:
        wait = min(base * attempt, cap)
    elif cat == ErrorCategory.MODEL_ERROR:
        return 0.0
    else:
        wait = min(base * attempt, cap)
    if jitter:
        wait = wait + random.uniform(0, jitter)
    return round(wait, 4)


def should_switch_model(category: Any) -> bool:
    """模型错误 → 切换备用模型（FAST↔STRONG）而非重试同模型。"""
    return classify_error(category) == ErrorCategory.MODEL_ERROR


def switch_model_source(current: str) -> str:
    """在 FAST↔STRONG 间切换备用模型源。"""
    cur = (current or "fast").lower()
    return "strong" if cur == "fast" else "fast"


def should_retry(category: Any, attempt: int) -> bool:
    """是否还应重试（未超过该类型最大重试次数）。"""
    cat = classify_error(category)
    return attempt <= MAX_RETRIES.get(cat, 1)


def plan_retry(category: Any, attempt: int, *, base: float = 1.0, cap: float = 30.0, jitter: float = 0.0) -> dict:
    """一体化退避决策：返回 {category, wait, switch_model, retry, max_retries}。"""
    cat = classify_error(category)
    return {
        "category": cat.value,
        "wait": next_backoff(cat, attempt, base=base, cap=cap, jitter=jitter),
        "switch_model": should_switch_model(cat),
        "retry": should_retry(cat, attempt),
        "max_retries": MAX_RETRIES.get(cat, 1),
    }
