"""
日志脱敏工具（Phase 3 可观测性）。

防止敏感信息泄露到日志中：
- 密码字段（password/pwd/secret）
- Token（access_token/refresh_token/Authorization）
- API Key
- 手机号（脱敏为 138****1234）
- 邮箱（脱敏为 u***@domain.com）
"""
from __future__ import annotations

import re
from typing import Any

# 敏感字段名匹配模式（不区分大小写）
_SENSITIVE_KEY_PATTERNS = re.compile(
    r"(password|pwd|secret|token|api[_-]?key|authorization|credential)",
    re.IGNORECASE,
)

# 手机号匹配（中国大陆 11 位）
_PHONE_PATTERN = re.compile(r"(1[3-9]\d)\d{4}(\d{4})")

# 邮箱匹配
_EMAIL_PATTERN = re.compile(r"([a-zA-Z0-9._%+-]{1,3})[a-zA-Z0-9._%+-]*(@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})")


def sanitize_for_log(value: Any, max_length: int = 200) -> str:
    """
    对任意值做日志脱敏处理。

    策略：
    - 敏感字段名 → 值替换为 ***
    - 手机号 → 138****1234
    - 邮箱 → u***@domain.com
    - 过长字符串 → 截断

    面试考点：为什么不在日志写入时脱敏而是在输入时脱敏？
    因为日志可能被多个 handler 处理（文件/控制台/远程），在源头脱敏最安全。
    """
    if value is None:
        return "None"
    if isinstance(value, (int, float, bool)):
        return str(value)

    s = str(value)

    # 手机号脱敏
    s = _PHONE_PATTERN.sub(r"\1****\2", s)

    # 邮箱脱敏
    s = _EMAIL_PATTERN.sub(r"\1***\2", s)

    # 截断长字符串（后缀长度计入 max_length，保证总长不超合同）
    if len(s) > max_length:
        suffix = f"...(truncated {len(value) - max_length} chars)"
        s = s[: max(0, max_length - len(suffix))] + suffix

    return s


def sanitize_dict_for_log(data: dict[str, Any]) -> dict[str, Any]:
    """
    对字典做日志脱敏，敏感字段的值替换为 "***"。

    递归处理嵌套字典，但不进入列表/元组（避免性能问题）。
    """
    if not isinstance(data, dict):
        return data

    result: dict[str, Any] = {}
    for key, val in data.items():
        if _SENSITIVE_KEY_PATTERNS.search(str(key)):
            result[key] = "***"
        elif isinstance(val, dict):
            result[key] = sanitize_dict_for_log(val)
        elif isinstance(val, str):
            result[key] = sanitize_for_log(val)
        else:
            result[key] = val
    return result


def is_sensitive_key(key: str) -> bool:
    """判断一个键名是否属于敏感字段。"""
    return bool(_SENSITIVE_KEY_PATTERNS.search(key))