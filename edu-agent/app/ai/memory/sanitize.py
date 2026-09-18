"""记忆落库脱敏（R04-b，承接 audit P3-23/24 落库数据最小化语义）。

审计结论（落库链路敏感面）：
- `user_memory_event.content`：规则抽取（ingest.detect_memories）+ LLM 抽取
  （extract_llm）产出的记忆候选，content 为对话窗内**原文片段**——用户在对话中
  粘贴的 API key / token / JWT / 手机号 / 身份证号会被原样抽入长期记忆并落库；
- Redis 队列 turn 载荷 `messages[].content`：整窗原文入队（LPUSH），LLM 抽取失败时
  `window_preview` 还会把前 2 条预览写入 degraded 键；
- 脱敏收口点 = 队列写入边界（enqueue_turn_window / enqueue_candidate），覆盖规则+LLM
  双来源与全部落库路径（事件溯源/快照表都经 store.write←queue）。

范式对齐（不重复造轮子）：
- 手机号/邮箱正则直接复用 `app/common/log_sanitizer`（T19-3 日志脱敏既有范式）；
- 掩码标记 `***REDACTED***` 对齐 `app/mcp/executor._redact_sensitive`（W-NEXT-MCP-001
  P0-③ 落库脱敏同款），全库单一口径；
- 新增高熵 token / 已知密钥前缀 / Bearer / key=value / 身份证号模式（记忆内容是纯文本，
  MCP 的 dict key 命中范式不适用，需文本级模式脱敏——这是唯一新增部分）。

铁律：
- **只损内容不损结构**：只对字符串值做就地掩码，消息条数/字段名/JSON 结构完整不变
  （事件行 JSON 字段、队列载荷字段、窗口 role/content 键均保持原状）；
- **检索/HEAD 逻辑零改动**：本模块不触碰 event_persistence 的查询/版本语义；
- 脱敏命中计数入日志（logger + 模块级累计统计），验收可观测。
"""
from __future__ import annotations

import re
from typing import Any

from loguru import logger

# 复用既有脱敏范式：手机号/邮箱正则与替换口径与 app/common/log_sanitizer 完全一致
from app.common.log_sanitizer import _EMAIL_PATTERN, _PHONE_PATTERN

# 掩码标记：对齐 mcp/executor._REDACTED（落库脱敏单一口径）
REDACTED = "***REDACTED***"

# ---------------------------------------------------------------------------
# 模式级脱敏正则（文本内容专用；顺序即应用顺序，先特异后泛化）
# ---------------------------------------------------------------------------
# 1) 身份证号（18 位，出生日期段结构校验，降误伤；必须先于手机号处理——长数字串内含手机号形状子串）
_RE_ID_CARD = re.compile(
    r"(?<!\d)(\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3})([\dXx])(?!\d)"
)

# 2) 已知密钥前缀（业界固定格式，零歧义）；左侧禁 word-char/-/_ 邻接，防 task-2024... 之类单词误伤
_RE_KNOWN_PREFIX = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"(sk-[A-Za-z0-9_-]{12,}"          # OpenAI/DeepSeek 等
    r"|gh[pousr]_[A-Za-z0-9]{16,}"     # GitHub token
    r"|AKIA[0-9A-Z]{16}"               # AWS access key id
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"   # Slack token
    r")"
)

# 3) JWT（三段 base64url，首段固定 eyJ）
_RE_JWT = re.compile(
    r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])"
)

# 4) Authorization: Bearer <token>
_RE_BEARER = re.compile(r"(?i)\b(bearer)\s+([A-Za-z0-9._~+/=-]{8,})")

# 5) key=value 形态（password=xxx / token: xxx / api_key：xxx；值为 ≥8 连续非空白）
_RE_KEY_VALUE = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|authorization)"
    r"(\s*[=:：]\s*)([^\s，。；、！？'\"]{8,})"
)

# 6) 泛化高熵串：≥32 位 base64/hex 形字符连续 run（边界防切断更长 token；
#    函数替换里再要求字母+数字混合，避免全字母/全数字误伤）
_RE_HIGH_ENTROPY = re.compile(
    r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/=_-]{32,}(?![A-Za-z0-9+/=_-])"
)

_TRAILING_PUNCT = "，。；、！？：：'\"”’）)，.;"


def _mask_key_value(m: re.Match) -> str:
    """key=value → key=***REDACTED***（保留 key 与分隔符，尾部标点还原文案）。"""
    value = m.group(3)
    trail = ""
    while value and value[-1] in _TRAILING_PUNCT:
        trail = value[-1] + trail
        value = value[:-1]
    if len(value) < 8:  # 剥掉尾标点后不足 8 位则不动（降误伤）
        return m.group(0)
    return f"{m.group(1)}{m.group(2)}{REDACTED}{trail}"


def _mask_high_entropy(m: re.Match) -> str:
    """高熵串 → ***REDACTED***；需字母+数字混合（防全字母长串/纯数字单号误伤）。"""
    s = m.group(0)
    if any(c.isdigit() for c in s) and any(c.isalpha() for c in s):
        return REDACTED
    return s


# 应用顺序（先特异后泛化；身份证必须先于手机号）
_TEXT_PATTERNS: tuple[tuple[re.Pattern[str], Any], ...] = (
    (_RE_ID_CARD, lambda m: f"{m.group(1)[:4]}********{m.group(2)}"),  # 前4+末1
    (_RE_KNOWN_PREFIX, lambda m: REDACTED),
    (_RE_JWT, lambda m: REDACTED),
    (_RE_BEARER, lambda m: f"{m.group(1)} {REDACTED}"),
    (_RE_KEY_VALUE, _mask_key_value),
    (_RE_HIGH_ENTROPY, _mask_high_entropy),
)

# 模块级命中累计（观测/验收；进程内计数，不保证跨实例聚合）
SANITIZE_STATS: dict[str, int] = {"text_calls": 0, "hits": 0, "window_calls": 0, "window_hits": 0}


def reset_stats_for_test() -> None:
    """测试隔离：清零累计统计。"""
    for k in SANITIZE_STATS:
        SANITIZE_STATS[k] = 0


def sanitize_memory_text(text: str) -> tuple[str, int]:
    """对记忆内容文本做模式级脱敏。

    Returns:
        (脱敏后文本, 命中数)。无命中时原串原样返回（零开销路径）。
        非字符串输入原样返回（防御，不抛错——脱敏绝不阻断落库链路）。
    """
    SANITIZE_STATS["text_calls"] += 1
    if not isinstance(text, str) or not text:
        return text, 0
    hits = 0
    out = text
    for pattern, repl in _TEXT_PATTERNS:
        # 手机号/邮箱沿用 log_sanitizer 的 partial-mask 替换串；其余模式各自函数替换
        out, n = pattern.subn(repl, out)
        hits += n
    # 手机号/邮箱（log_sanitizer 同款替换口径：138****1234 / u***@domain.com）
    out, n = _PHONE_PATTERN.subn(r"\1****\2", out)
    hits += n
    out, n = _EMAIL_PATTERN.subn(r"\1***\2", out)
    hits += n
    if hits:
        SANITIZE_STATS["hits"] += hits
        logger.info(
            f"[Memory:sanitize] 落库脱敏命中 {hits} 处（累计 {SANITIZE_STATS['hits']}）"
        )
    return out, hits


def sanitize_turn_messages(messages: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], int]:
    """对话窗消息列表脱敏：逐条 content 掩码，role/键结构/条数完整保留。

    只损内容不损结构：返回**新列表**（不原地改入参），每个元素保持
    `{"role": ..., "content": ...}` 键集不变，其余字段原样透传。
    """
    SANITIZE_STATS["window_calls"] += 1
    if not messages:
        return messages if isinstance(messages, list) else [], 0
    out: list[dict[str, Any]] = []
    total = 0
    for m in messages:
        if not isinstance(m, dict):
            out.append(m)
            continue
        clone = dict(m)  # 结构完整：所有键原样保留
        content = clone.get("content")
        if isinstance(content, str):
            masked, n = sanitize_memory_text(content)
            clone["content"] = masked
            total += n
        out.append(clone)
    if total:
        SANITIZE_STATS["window_hits"] += total
    return out, total
