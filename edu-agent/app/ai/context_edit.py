"""
task96 / R4 上下文编辑（context editing）+ 工具结果清理 + 上下文使用率监控与阈值策略。

竞品对标（引用见 test-reports/task96-completion-report.md）：
- Claude Code《Manage Claude's context window》: context editing 是「最轻量的上下文管理形态」——
  在**不重写前缀**的前提下精确删除历史消息，因此已缓存的 system/tools 前缀仍可命中 prompt cache；
  compaction 属重量手段（整段重写 → 前缀失效、缓存全部重算）。
- Anthropic cookbook《tool result clearing》: 超过最近 N 轮的工具结果自动清理为一行结论，
  原文落 artifact（可回读），主上下文只留结论。

本模块是 R4 的权威实现（canonical）：
- `context_edit()`      GWT①：精确删除「已完成工具调用 + 结果」对与紧邻的填充式中间推理；
                              保留用户意图 / 未完成决策 / system 前缀；**前缀签名前后不变**。
- `tool_result_clearing()` GWT②：超出最近 keep_rounds 轮的工具结果 → 一行结论（原文进 artifact）。
- `measure_usage()` / `ContextUsageMonitor` GWT③：上下文使用率监控（占窗口比例 + 水位告警 + 快照环形缓冲）。
- `ThresholdStrategy` / `plan_context_action()` / `apply_context_strategy()` GWT③：
                              阈值策略配置 —— 先 context_edit（轻量），仍超阈值才 compaction（重量）。

分层与依赖（避免循环导入）：
- 低层 token/消息原语（estimate_tokens / 轮次切分 / 工具消息判定）单一真源仍在 `app.ai.compaction`，
  本模块**模块级**导入它们；`compaction` 侧对本模块一律**函数内惰性导入** → 双向安全。
- artifact 写入（`app.ai.artifact`）亦为函数内惰性导入（artifact → compaction 已有依赖）。

纯函数 + 零外部 IO：除 `clear_tool_results_to_artifact()`（可注入 store）外全部离线可测，不调用 LLM。
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Sequence

from loguru import logger

from app.ai.compaction import (
    estimate_tokens,
    group_rounds,
    is_system_msg,
    is_tool_call,
    is_tool_msg,
    msg_content,
    msg_tokens,
)
from app.config import settings

# 填充式中间推理前缀（仅在紧邻被删工具对时才删，保守白名单）
_FILLER_PREFIXES = (
    "让我", "好的，我", "好的,我", "我来调用", "我将调用", "我需要调用",
    "正在调用", "先调用", "接下来我调用", "稍等", "马上调用",
)
REDUNDANT_REASONING_MAX_TOKENS = 60      # 超过此长度的 assistant 消息不视为「填充」，一律保留
ARTIFACT_MARKER = "已入 artifact"         # 幂等标记：已清理过的工具结果不再二次清理
_TOOL_NAME_RE = re.compile(r"^\[\s*(?:工具|tool)\s+([^\]\s]+)")


# ============================================================
# 1. 可缓存前缀：边界 / 签名 / 公共前缀长度（GWT①「前缀不变」的度量手段）
# ============================================================
def cache_prefix_end(messages: Sequence[Any]) -> int:
    """可缓存前缀边界下标：自 0 起连续的 system 消息。

    对齐 Anthropic prompt caching 的稳定前缀定义（system prompt + tool definitions 位于流首）。
    context_edit / tool_result_clearing 永不触碰 `messages[:cache_prefix_end]`。
    """
    end = 0
    for m in messages:
        if is_system_msg(m):
            end += 1
        else:
            break
    return end


def prefix_messages(messages: Sequence[Any]) -> list[Any]:
    """返回可缓存前缀消息（不含后续对话）。"""
    return list(messages)[: cache_prefix_end(messages)]


def _render_one(m: Any) -> str:
    role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "msg")
    return f"[{role}] {msg_content(m)}"


def prefix_signature(messages: Sequence[Any]) -> str:
    """稳定前缀签名（sha256）。编辑前后一致 ⇒ prompt cache 前缀仍可命中。"""
    blob = "\n".join(_render_one(m) for m in prefix_messages(messages))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def first_divergence_index(before: Sequence[Any], after: Sequence[Any]) -> int:
    """before/after 首个不同消息的下标 = 未受影响的最长公共前缀长度（可命中缓存的消息条数）。"""
    n = min(len(before), len(after))
    for i in range(n):
        if _render_one(before[i]) != _render_one(after[i]):
            return i
    return n


# ============================================================
# 2. 编辑策略（可配置；默认与 task26 契约等价：删除全部已完成工具对）
# ============================================================
@dataclass
class EditPolicy:
    """context editing 策略。

    keep_recent_rounds: 保护最近 N 轮内的工具对不被删除（0 = 不保护，删除全部已完成对，兼容 task26）。
    drop_redundant_reasoning: 是否同时删除紧邻被删工具对之前的填充式中间推理。
    protect_prefix: 是否保护可缓存前缀（默认 True，前缀绝不删）。
    min_pair_tokens: 工具对 token 小于此值则不删（避免为省几十 token 破坏可读上下文）。
    """

    keep_recent_rounds: int = 0
    drop_redundant_reasoning: bool = True
    protect_prefix: bool = True
    min_pair_tokens: int = 0

    @classmethod
    def from_settings(cls) -> "EditPolicy":
        return cls(
            keep_recent_rounds=int(getattr(settings, "CONTEXT_EDIT_KEEP_RECENT_ROUNDS", 0)),
            drop_redundant_reasoning=bool(
                getattr(settings, "CONTEXT_EDIT_DROP_REDUNDANT_REASONING", True)
            ),
        )


def _is_redundant_reasoning(m: Any) -> bool:
    """填充式中间推理：assistant 短消息且以调用前置语开头（结论型回答不在此列）。"""
    role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "")
    if role not in ("assistant", "ai"):
        return False
    if is_tool_call(m):
        return False
    content = msg_content(m).strip()
    if not content or estimate_tokens(content) > REDUNDANT_REASONING_MAX_TOKENS:
        return False
    return content.startswith(_FILLER_PREFIXES)


def _protected_start_index(msgs: Sequence[Any], keep_recent_rounds: int) -> int:
    """最近 keep_recent_rounds 轮的起始下标（该下标及之后一律保护）。0 轮 → 返回 len（无保护）。"""
    if keep_recent_rounds <= 0:
        return len(msgs)
    rounds = group_rounds(msgs)
    if keep_recent_rounds >= len(rounds):
        return 0
    cut = len(rounds) - keep_recent_rounds
    return sum(len(r) for r in rounds[:cut])


def context_edit(messages: Sequence[Any], policy: EditPolicy | None = None, *, anchor_round: int | None = None) -> dict:
    """GWT①：精确删除历史消息，保留前缀缓存。

    删除：已完成的「工具调用 + 工具结果」对（原文已在 artifact）；紧邻其前的填充式中间推理。
    保留：可缓存 system 前缀、用户意图（user 消息）、未完成决策（有调用无结果）、结论型回答、
          最近 keep_recent_rounds 轮内的一切。
    anchor_round（opt-in，task-C1）：额外冻结前 N 个含用户问题的轮次（AC4「闸门前字节零改动」），
                                   默认 None → 不改变既有行为（task96 回归不变）。

    Returns:
        dict {edited, removed, removed_tokens, kept_tokens, messages,
              prefix_signature, prefix_stable, stable_prefix_len, removed_details,
              anchor_gate_idx}
    """
    pol = policy or EditPolicy.from_settings()
    msgs = list(messages)
    if not msgs:
        return {
            "edited": False, "removed": 0, "removed_tokens": 0, "kept_tokens": 0,
            "messages": [], "prefix_signature": prefix_signature([]),
            "prefix_stable": True, "stable_prefix_len": 0, "removed_details": [],
            "anchor_gate_idx": 0,
        }

    prefix_end = cache_prefix_end(msgs) if pol.protect_prefix else 0
    # 锚定闸门（opt-in）：冻结 System + 前 N 个含用户问题的轮次，绝不改写其字节
    gate_idx = prefix_end
    if anchor_round is not None:
        from app.ai.compaction import anchor_gate as _anchor_gate

        gate_idx = _anchor_gate(msgs, int(anchor_round))
    frozen_end = gate_idx
    protected_from = _protected_start_index(msgs, pol.keep_recent_rounds)

    kept: list[Any] = list(msgs[:frozen_end])
    removed_details: list[dict] = []
    removed_tokens = 0
    i = frozen_end
    n = len(msgs)

    while i < n:
        m = msgs[i]
        # 最近 N 轮保护窗内：原样保留
        if i >= protected_from:
            kept.append(m)
            i += 1
            continue
        # 已完成工具对 = 工具调用紧接工具结果
        if is_tool_call(m) and i + 1 < n and is_tool_msg(msgs[i + 1]):
            pair_tokens = msg_tokens(m) + msg_tokens(msgs[i + 1])
            if pair_tokens >= pol.min_pair_tokens:
                # 顺带回删紧邻的填充式中间推理（不越过前缀边界）
                if (
                    pol.drop_redundant_reasoning
                    and len(kept) > prefix_end
                    and _is_redundant_reasoning(kept[-1])
                ):
                    dropped = kept.pop()
                    removed_tokens += msg_tokens(dropped)
                    removed_details.append({
                        "index": i - 1, "reason": "redundant_reasoning",
                        "tokens": msg_tokens(dropped),
                    })
                removed_tokens += pair_tokens
                removed_details.append({
                    "index": i, "reason": "completed_tool_call", "tokens": msg_tokens(m),
                })
                removed_details.append({
                    "index": i + 1, "reason": "completed_tool_result",
                    "tokens": msg_tokens(msgs[i + 1]),
                })
                i += 2
                continue
        kept.append(m)
        i += 1

    sig_before = prefix_signature(msgs)
    sig_after = prefix_signature(kept)
    if sig_before != sig_after:  # 理论不可达（前缀受保护）；出现即为回归缺陷
        logger.error("[context_edit] 前缀签名发生变化，prompt cache 将失效（应为不可达分支）")

    return {
        "edited": len(removed_details) > 0,
        "removed": len(removed_details),
        "removed_tokens": removed_tokens,
        "kept_tokens": sum(msg_tokens(m) for m in kept),
        "messages": kept,
        "prefix_signature": sig_after,
        "prefix_stable": sig_before == sig_after,
        "stable_prefix_len": first_divergence_index(msgs, kept),
        "removed_details": removed_details,
        "anchor_gate_idx": frozen_end,
    }


# ============================================================
# 3. tool result clearing（GWT②：N 轮后工具结果 → 一行结论，原文进 artifact）
# ============================================================
def extract_tool_name(content: str) -> str:
    """从「[工具 X 返回] …」前缀提取工具名，取不到返回 'tool'。"""
    m = _TOOL_NAME_RE.match(content.lstrip())
    return m.group(1) if m else "tool"


def _already_cleared(m: Any) -> bool:
    return ARTIFACT_MARKER in msg_content(m)


def _clone_msg_with_content(m: dict, content: str) -> dict:
    out = dict(m)
    out["content"] = content
    return out


def build_one_line(content: str, before_tokens: int, line_limit: int, artifact_ref: str | None = None) -> str:
    """单行结论（保持 task26 既有文案格式，附加可选 artifact 引用）。"""
    one = content.replace("\r", "").replace("\n", " ").strip()
    ref = f" {artifact_ref}" if artifact_ref else ""
    tail = f"（原 {before_tokens} token {ARTIFACT_MARKER}{ref}）"
    if len(one) > line_limit:
        return one[:line_limit] + "…" + tail
    return one + tail


def tool_result_clearing(
    messages: Sequence[Any],
    keep_rounds: int | None = None,
    line_limit: int = 120,
    on_original: Callable[[int, str, str], str | None] | None = None,
) -> dict:
    """GWT②：超出最近 keep_rounds 轮的工具结果精简为一行结论。

    幂等：已带 artifact 标记的消息不再二次清理。
    `on_original(index, tool_name, content) -> artifact_ref | None` 可注入以落原文（同步回调）。

    Returns:
        dict {cleared, results, kept_tokens, cleared_tokens, messages,
              prefix_signature, prefix_stable}
    """
    msgs = list(messages)
    rounds = group_rounds(msgs)
    keep_rounds = int(keep_rounds if keep_rounds is not None else settings.COMPACTION_KEEP_ROUNDS)
    prefix_end = cache_prefix_end(msgs)

    flattened: list[Any] = []
    results: list[dict] = []
    cleared = 0
    cleared_tokens = 0
    idx = -1

    for ridx, rnd in enumerate(rounds):
        is_recent = ridx >= len(rounds) - keep_rounds
        for m in rnd:
            idx += 1
            if (
                not is_recent
                and idx >= prefix_end            # 前缀绝不改写（保前缀缓存）
                and is_tool_msg(m)
                and not _already_cleared(m)
            ):
                content = msg_content(m)
                before_tokens = estimate_tokens(content)
                tool_name = extract_tool_name(content)
                ref: str | None = None
                if on_original is not None:
                    try:
                        ref = on_original(idx, tool_name, content)
                    except Exception as exc:
                        logger.warning(
                            f"[context_edit] artifact 落原文失败，仅做流内精简: {type(exc).__name__}: {exc}"
                        )
                cleared_to = build_one_line(content, before_tokens, line_limit, ref)
                after_tokens = estimate_tokens(cleared_to)
                m = _clone_msg_with_content(m, cleared_to) if isinstance(m, dict) else cleared_to
                cleared += 1
                cleared_tokens += max(0, before_tokens - after_tokens)
                results.append({
                    "index": idx, "tool_name": tool_name, "before_tokens": before_tokens,
                    "after_tokens": after_tokens, "cleared_to": cleared_to, "artifact_ref": ref,
                })
            flattened.append(m)

    sig_before = prefix_signature(msgs)
    sig_after = prefix_signature(flattened)
    return {
        "cleared": cleared,
        "results": results,
        "kept_tokens": sum(msg_tokens(m) for m in flattened),
        "cleared_tokens": cleared_tokens,
        "messages": flattened,
        "prefix_signature": sig_after,
        "prefix_stable": sig_before == sig_after,
    }


async def clear_tool_results_to_artifact(
    messages: Sequence[Any],
    keep_rounds: int | None = None,
    line_limit: int = 120,
    store: Any | None = None,
    ttl: int | None = None,
) -> dict:
    """tool result clearing 的 artifact 版：原文写入 artifact（TTL 默认 ARTIFACT_TTL），流内留一行结论 + ref。

    两遍走法（确定性）：先 dry-run 收集待清理原文 → 批量写 artifact → 带 ref 正式清理。
    """
    from app.ai.artifact import ArtifactShuntStore  # 惰性导入：避免 compaction ↔ artifact 循环

    st = store or ArtifactShuntStore()
    ttl = int(ttl if ttl is not None else getattr(settings, "ARTIFACT_TTL", 3600))

    pending: list[tuple[int, str, str]] = []

    def _collect(index: int, tool_name: str, content: str) -> None:
        pending.append((index, tool_name, content))
        return None

    dry = tool_result_clearing(messages, keep_rounds, line_limit, on_original=_collect)
    if not pending:
        return dry

    refs: dict[int, str] = {}
    for index, tool_name, content in pending:
        try:
            refs[index] = await st.write(
                {"tool_name": tool_name, "input_tokens": estimate_tokens(content), "raw": content}, ttl
            )
        except Exception as exc:
            logger.warning(f"[context_edit] artifact 写入失败: {type(exc).__name__}: {exc}")

    out = tool_result_clearing(messages, keep_rounds, line_limit, on_original=lambda i, n, c: refs.get(i))
    out["artifact_refs"] = refs
    out["store"] = st
    return out


# ============================================================
# 4. 上下文使用率监控（GWT③）
# ============================================================
@dataclass
class ContextUsage:
    """一次使用率测量结果。"""

    total_tokens: int
    window_tokens: int
    edit_threshold: int
    usage_ratio: float          # total / window
    threshold_ratio: float      # total / edit_threshold
    prefix_tokens: int
    tool_result_tokens: int
    rounds: int
    messages_count: int
    over_threshold: bool
    over_warn: bool

    def to_dict(self) -> dict:
        return asdict(self)


def measure_usage(
    messages: Sequence[Any],
    window_tokens: int | None = None,
    edit_threshold: int | None = None,
    warn_ratio: float | None = None,
) -> ContextUsage:
    """测量上下文使用率：总 token / 窗口预算 / 前缀占用 / 工具结果占用 / 是否越水位。"""
    msgs = list(messages)
    window = int(window_tokens if window_tokens is not None
                 else getattr(settings, "CONTEXT_WINDOW_TOKENS", 32000))
    thr = int(edit_threshold if edit_threshold is not None else settings.COMPACTION_TOKEN_THRESHOLD)
    warn = float(warn_ratio if warn_ratio is not None
                 else getattr(settings, "CONTEXT_USAGE_WARN_RATIO", 0.6))
    window = max(1, window)

    total = sum(msg_tokens(m) for m in msgs)
    prefix_tokens = sum(msg_tokens(m) for m in prefix_messages(msgs))
    tool_tokens = sum(msg_tokens(m) for m in msgs if is_tool_msg(m))
    ratio = total / window
    return ContextUsage(
        total_tokens=total,
        window_tokens=window,
        edit_threshold=thr,
        usage_ratio=round(ratio, 4),
        threshold_ratio=round(total / max(1, thr), 4),
        prefix_tokens=prefix_tokens,
        tool_result_tokens=tool_tokens,
        rounds=len(group_rounds(msgs)) if msgs else 0,
        messages_count=len(msgs),
        over_threshold=total > thr,
        over_warn=ratio >= warn,
    )


class ContextUsageMonitor:
    """使用率快照环形缓冲（供 /admin 观测与 task97 缓存监控串联）。clock 可注入，离线可测。"""

    def __init__(self, maxlen: int | None = None, clock: Callable[[], float] | None = None) -> None:
        self._maxlen = int(maxlen if maxlen is not None
                           else getattr(settings, "CONTEXT_USAGE_MONITOR_MAX", 50))
        self._clock = clock or time.time
        self._records: list[dict] = []

    def record(self, usage: ContextUsage, action: str = "none", session_id: str | int | None = None) -> dict:
        rec = {
            "ts": self._clock(),
            "session_id": session_id,
            "action": action,
            **usage.to_dict(),
        }
        self._records.append(rec)
        if len(self._records) > self._maxlen:
            self._records = self._records[-self._maxlen:]
        if usage.over_warn:
            logger.info(
                f"[context_usage] 使用率 {usage.usage_ratio:.0%} 越水位 "
                f"({usage.total_tokens}/{usage.window_tokens} token) action={action}"
            )
        return rec

    @property
    def records(self) -> list[dict]:
        return list(self._records)

    def peak_ratio(self) -> float:
        return max((r["usage_ratio"] for r in self._records), default=0.0)

    def over_warn_count(self) -> int:
        return sum(1 for r in self._records if r.get("over_warn"))

    def action_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self._records:
            key = str(r.get("action") or "none")
            out[key] = out.get(key, 0) + 1
        return out

    def snapshot(self) -> dict:
        return {
            "samples": len(self._records),
            "peak_ratio": self.peak_ratio(),
            "over_warn": self.over_warn_count(),
            "actions": self.action_counts(),
            "last": self._records[-1] if self._records else None,
        }

    def reset(self) -> None:
        self._records.clear()


_default_monitor = ContextUsageMonitor()


def get_context_monitor() -> ContextUsageMonitor:
    """进程内默认监控器（观测端点用）。"""
    return _default_monitor


# ============================================================
# 5. 阈值策略配置 + 决策 + 执行（GWT③：context_edit 优先，仍超才 compaction）
# ============================================================
@dataclass
class ThresholdStrategy:
    """阈值策略配置（全部可由 settings 覆盖，运维零改码调参）。"""

    edit_threshold: int
    keep_rounds: int
    window_tokens: int
    warn_ratio: float
    order: tuple[str, ...]
    context_edit_enabled: bool

    @classmethod
    def from_settings(cls) -> "ThresholdStrategy":
        raw_order = str(getattr(settings, "CONTEXT_STRATEGY_ORDER", "context_edit,compaction"))
        order = tuple(s.strip() for s in raw_order.split(",") if s.strip())
        return cls(
            edit_threshold=int(settings.COMPACTION_TOKEN_THRESHOLD),
            keep_rounds=int(settings.COMPACTION_KEEP_ROUNDS),
            window_tokens=int(getattr(settings, "CONTEXT_WINDOW_TOKENS", 32000)),
            warn_ratio=float(getattr(settings, "CONTEXT_USAGE_WARN_RATIO", 0.6)),
            order=order or ("context_edit", "compaction"),
            context_edit_enabled=bool(getattr(settings, "CONTEXT_EDIT_ENABLED", True)),
        )


def plan_context_action(
    messages: Sequence[Any],
    strategy: ThresholdStrategy | None = None,
    policy: EditPolicy | None = None,
) -> dict:
    """监控 + 阈值决策：返回 {action, reason, usage, projected_tokens}。

    action ∈ none | context_edit | compaction。未超阈值 → none；
    超阈值且 context_edit 后可降至阈值内 → context_edit；否则 compaction。
    """
    st = strategy or ThresholdStrategy.from_settings()
    usage = measure_usage(messages, st.window_tokens, st.edit_threshold, st.warn_ratio)
    if not usage.over_threshold:
        return {"action": "none", "reason": "under_threshold", "usage": usage,
                "projected_tokens": usage.total_tokens}

    if st.context_edit_enabled and "context_edit" in st.order:
        edit = context_edit(messages, policy)
        projected = edit["kept_tokens"]
        if projected <= st.edit_threshold:
            return {"action": "context_edit", "reason": "context_edit_sufficient",
                    "usage": usage, "projected_tokens": projected}
        return {"action": "compaction", "reason": "context_edit_insufficient",
                "usage": usage, "projected_tokens": projected}
    return {"action": "compaction", "reason": "context_edit_disabled",
            "usage": usage, "projected_tokens": usage.total_tokens}


def apply_context_strategy(
    messages: Sequence[Any],
    strategy: ThresholdStrategy | None = None,
    policy: EditPolicy | None = None,
    summarizer: Callable | None = None,
    monitor: ContextUsageMonitor | None = None,
    session_id: str | int | None = None,
) -> dict:
    """执行阈值策略链：先 context_edit（轻量、保前缀缓存），仍超阈值才 compaction（重量）。

    Returns:
        dict {chain, action, before_tokens, after_tokens, messages, prefix_stable,
              stable_prefix_len, usage_before, usage_after, edit, compaction}
    """
    st = strategy or ThresholdStrategy.from_settings()
    msgs = list(messages)
    usage_before = measure_usage(msgs, st.window_tokens, st.edit_threshold, st.warn_ratio)
    sig_before = prefix_signature(msgs)

    chain: list[str] = []
    edit_out: dict | None = None
    comp_out: dict | None = None
    current = msgs

    if usage_before.over_threshold:
        if st.context_edit_enabled and "context_edit" in st.order:
            edit_out = context_edit(current, policy)
            if edit_out["edited"]:
                chain.append("context_edit")
                current = edit_out["messages"]
        still_over = sum(msg_tokens(m) for m in current) > st.edit_threshold
        if still_over and "compaction" in st.order:
            from app.ai.compaction import compact_messages  # 惰性导入：避免模块级循环

            comp_out = compact_messages(
                current, threshold=st.edit_threshold, keep_rounds=st.keep_rounds, summarizer=summarizer
            )
            chain.append("compaction")
            kept = list(comp_out["kept_messages"])
            summary_msg = comp_out.get("summary_msg")
            current = ([summary_msg] + kept) if summary_msg else kept

    usage_after = measure_usage(current, st.window_tokens, st.edit_threshold, st.warn_ratio)
    action = chain[-1] if chain else "none"
    mon = monitor if monitor is not None else _default_monitor
    mon.record(usage_after, action=action, session_id=session_id)

    return {
        "chain": chain,
        "action": action,
        "before_tokens": usage_before.total_tokens,
        "after_tokens": usage_after.total_tokens,
        "messages": current,
        "prefix_stable": (
            prefix_signature(current) == sig_before if "compaction" not in chain else None
        ),
        "stable_prefix_len": first_divergence_index(msgs, current),
        "usage_before": usage_before,
        "usage_after": usage_after,
        "edit": edit_out,
        "compaction": comp_out,
    }
