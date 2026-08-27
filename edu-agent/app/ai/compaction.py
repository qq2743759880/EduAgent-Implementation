"""
task26 AI 助手上下文管理：compaction + R4 context editing + tool result clearing。

task96 起，R4 的权威实现（精确删除 + 前缀签名 + 使用率监控 + 阈值策略）迁至 `app.ai.context_edit`：
- 本模块的 `context_edit()` / `tool_result_clearing()` 保留原签名与返回键，内部**委派**到 context_edit 模块
  （函数内惰性导入，双向无循环），既是向后兼容层也是 compaction 的前置轻量手段；
- 本模块继续独占 compaction（重量压缩：结构化 summary + 最近 K 轮原文）与 token/消息原语（单一真源）。

对齐 Anthropic《Effective Context Engineering》Compaction 章节 + Claude Code context-window 文档：
- context editing = "最轻量上下文管理"：精确删除历史消息（已完成工具调用+结果、冗余中间推理），
  保留前缀缓存（后续消息不变可命中缓存）。
- tool result clearing = 工具结果在 N 轮后自动精简为一行结论（原文进 artifact）。
- compaction = 重量手段（全量压缩），仅当 context_edit 后仍超阈值才触发。
  触发阈值：消息流 >6000 token → plan_node 前压缩至 ≤6000；compaction 后新增 >3000 再触发；
  压缩后 summary 保留结构化决策语义（profile_updates/pending_tasks/decisions/facts），最近 K=6 轮原文保留。

设计原则：
- 纯函数 + 无外部 LLM 硬依赖：默认用规则结构化摘要（确定性可测）；可注入 `summarizer` 走 LLM 生成。
- 消息模型：list[dict] 每项 {role, content}，role ∈ {system,user,assistant,tool}；
  runner 的「[工具 X 返回]」用户消息按 content 前缀识别为 tool 消息（向后兼容）。
- 不修改调用方原始列表（返回新的精简列表），副作用由调用方处理。
"""
from __future__ import annotations

import json
from typing import Any, Callable, Sequence

from loguru import logger

from app.config import settings


# ============================================================
# 1. Token 估算（中文/全角 ≈1 token/字，ASCII ≈1 token/4 字符，保守偏大）
# ============================================================
def estimate_tokens(text: str) -> int:
    """粗略 token 估算：CJK ≈1 token/字，ASCII ≈1 token/4 字符（偏保守大）。"""
    if not text:
        return 0
    cjk = 0
    ascii_cnt = 0
    for ch in text:
        o = ord(ch)
        if (0x2E80 <= o <= 0x9FFF) or (0x3000 <= o <= 0x303F):
            cjk += 1
        elif ch != "\n":
            ascii_cnt += 1
    return cjk + ascii_cnt // 4 + 1


def _msg_content(m) -> str:
    """兼容 str / 含 content 属性或 dict 的多种消息表示。"""
    if isinstance(m, str):
        return m
    if isinstance(m, dict):
        return str(m.get("content") or "")
    if hasattr(m, "content"):
        return str(m.content or "")
    return str(m)


def _msg_tokens(m) -> int:
    return estimate_tokens(_msg_content(m))


def _is_tool_msg(m) -> bool:
    role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "")
    content = _msg_content(m).lstrip()
    return (
        role in ("tool", "function")
        or content.startswith("[工具 ")
        or content.startswith("[tool")
        or content.startswith("[工具")
    )


def _is_system_msg(m) -> bool:
    role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "")
    return role == "system"


def _is_user_query(m) -> bool:
    role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "")
    if role not in ("user", "human"):
        return False
    return not _is_tool_msg(m)


def _group_rounds(messages: Sequence[Any]) -> list[list[Any]]:
    """把扁平消息流按「用户问题」切分成轮次：一轮从一条用户问题开始至下一用户问题前。

    系统消息作为每轮前缀保留在同一轮。纯工具(无用户问题前缀)消息并入前一轮。
    返回 list[轮= list[消息]]（正序）。
    """
    rounds: list[list[Any]] = []
    open_round: list[Any] = []
    for m in messages:
        if _is_user_query(m):
            if open_round:
                rounds.append(open_round)
            open_round = [m]
        elif _is_system_msg(m):
            # 系统消息挂在当前轮前；若尚无轮则自起一轮（前缀稳定性：system 永远保留在首）
            if not open_round and not rounds:
                open_round.append(m)
            else:
                # 追加到当前轮（无用户问题前仍是开场）
                open_round.append(m)
        else:
            if not open_round:
                open_round.append(m)
            else:
                open_round.append(m)
    if open_round:
        rounds.append(open_round)
    return rounds


def _render(messages: Sequence[Any]) -> str:
    parts = []
    for m in messages:
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "msg")
        parts.append(f"[{role}] {_msg_content(m)}")
    return "\n".join(parts)


# ============================================================
# 2. context editing（最轻量：精确删历史工具调用+结果/冗余中间，保留前缀缓存）
#    task96：实现迁至 app.ai.context_edit（权威），此处为兼容委派层。
# ============================================================
def context_edit(messages: Sequence[Any], policy: Any | None = None) -> dict:
    """R4 context editing：精确删除「已完成工具调用 + 其工具结果」对与冗余中间消息。

    删除范围：工具调用 + 结果（它们已完成使命，原文已在 artifact）；紧邻其前、可被结论替代的填充式推理。
    保留范围：用户意图（用户问题）、未完成决策（有工具调用但无结果）、system 可缓存前缀。
    前缀（system 段）永不改写 → prompt cache 前缀签名不变，缓存可命中。

    实现委派 `app.ai.context_edit.context_edit()`；默认策略取自 settings
    （CONTEXT_EDIT_KEEP_RECENT_ROUNDS 默认 0 = 删除全部已完成对，与 task26 契约等价）。

    Returns:
        dict {edited, removed, removed_tokens, kept_tokens, messages,
              prefix_signature, prefix_stable, stable_prefix_len, removed_details}
    """
    from app.ai.context_edit import context_edit as _context_edit  # 惰性导入：避免模块级循环

    return _context_edit(messages, policy)


def _is_tool_call(m) -> bool:
    """严格判定「工具调用」：role ∈ {assistant,ai} 且 content 是含 tool/tool_call 键的 JSON。

    （避免把普通 assistant 回答 + 紧随的工具结果误判为「已完成工具对」而整对误删——
    工具调用在 runner 中以 `json.dumps({"tool": name, "args": {...}})` 写入，
    结构为含 tool 键的 JSON 对象。）
    """
    role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "")
    if role not in ("assistant", "ai"):
        return False
    content = _msg_content(m).lstrip()
    if not (content.startswith("{") or content.startswith("[")):
        return False
    try:
        obj = json.loads(content)
    except Exception:
        return False
    return isinstance(obj, dict) and ("tool" in obj or "tool_call" in obj)


# ============================================================
# 2.5 公共原语别名（task96）
#     token 估算与消息判定是全局单一真源，`app.ai.context_edit` 模块级导入这些公共名，
#     避免跨模块引用私有下划线名；本模块内部继续用 `_xxx`（零改动风险）。
# ============================================================
msg_content = _msg_content
msg_tokens = _msg_tokens
is_tool_msg = _is_tool_msg
is_tool_call = _is_tool_call
is_system_msg = _is_system_msg
is_user_query = _is_user_query
group_rounds = _group_rounds
render_messages = _render


# ============================================================
# 3. tool result clearing（R4 / GWT②：N 轮后工具结果 → 一行结论，原文进 artifact 由调用方处理）
# ============================================================
def tool_result_clearing(
    messages: Sequence[Any],
    keep_rounds: int | None = None,
    line_limit: int = 120,
    on_original: Callable[[int, str, str], str | None] | None = None,
) -> dict:
    """工具结果在超出最近 keep_rounds 轮后自动精简为一行结论。

    规则：保留最近 keep_rounds 轮的工具结果原文；更早的工具结果内容截断为
    「[工具 X 返回] <一行结论>…（原 N token 已入 artifact）」，仅一行。
    原文去向：注入 `on_original(index, tool_name, content) -> ref|None` 即可落 artifact；
    不注入则只做流内精简（零副作用）。异步 artifact 版见
    `app.ai.context_edit.clear_tool_results_to_artifact()`。

    实现委派 `app.ai.context_edit.tool_result_clearing()`。

    Returns:
        dict {cleared, results:[{index, tool_name, before_tokens, after_tokens, cleared_to,
              artifact_ref}], kept_tokens, cleared_tokens, messages, prefix_stable}
    """
    from app.ai.context_edit import tool_result_clearing as _clear  # 惰性导入：避免模块级循环

    return _clear(messages, keep_rounds=keep_rounds, line_limit=line_limit, on_original=on_original)


def _clone_msg_with_content(m: dict, content: str) -> dict:
    out = dict(m)
    out["content"] = content
    return out


# ============================================================
# 4. 结构化摘要（compaction 的 summary 保留结构化决策语义）
# ============================================================
def _default_structured_summary(prefix_messages: Sequence[Any]) -> dict:
    """规则化结构化摘要：从被压缩的历史消息中抽取 profile_updates/pending_tasks/decisions/facts。

    确定性实现（离线可测）；调用方可用 LLM summarizer 覆盖以获得更高质量摘要。
    返回 dict，安全包含 4 个稳定键。
    """
    text = _render(prefix_messages)
    profile_updates: list[str] = []
    pending_tasks: list[str] = []
    decisions: list[str] = []
    facts: list[str] = []

    # 用户明确偏好/目标/纠正（对齐 task25 R7 分词信号）
    for kw in ("记住", "我偏好", "我喜欢", "我想", "我的目标", "目标是", "不要", "改为"):
        if kw in text:
            # 抽取含关键词的一句话
            for line in text.splitlines():
                if kw in line:
                    snip = line.strip()[:180]
                    if snip not in profile_updates:
                        profile_updates.append(snip)
    # 未完成的计划/待办（"帮我/下一步/待办/后续"）
    for kw in ("下一步", "待办", "后续", "帮我安排", "请你先"):
        if kw in text:
            for line in text.splitlines():
                if kw in line:
                    snip = line.strip()[:180]
                    if snip not in pending_tasks:
                        pending_tasks.append(snip)
    # 结构化决策：工具调用结论
    for m in prefix_messages:
        if _is_tool_msg(m):
            c = _msg_content(m)[:120]
            if c not in decisions:
                decisions.append("[工具结论] " + c)
    # 事实：无明显偏好的常规信息压缩
    for line in text.splitlines():
        line = line.strip()
        if line and len(line) <= 200 and line not in facts and not line.startswith("["):
            facts.append(line)
        if len(facts) >= 5:
            break

    return {
        "profile_updates": profile_updates[:4],
        "pending_tasks": pending_tasks[:4],
        "decisions": decisions[:4],
        "facts": facts[:6],
    }


def build_structured_summary(prefix_messages: Sequence[Any], summarizer: Callable | None = None) -> dict:
    """构造结构化摘要 dict（4 稳定键）。summarizer 注入时由其生成。"""
    if summarizer is not None:
        try:
            out = summarizer(prefix_messages)
            if isinstance(out, dict):
                return {
                    "profile_updates": list(out.get("profile_updates") or []),
                    "pending_tasks": list(out.get("pending_tasks") or []),
                    "decisions": list(out.get("decisions") or []),
                    "facts": list(out.get("facts") or []),
                }
        except Exception as exc:
            logger.warning(f"[compaction] summarizer 失败，回退规则摘要: {type(exc).__name__}: {exc}")
    return _default_structured_summary(prefix_messages)


# ============================================================
# 5. compaction：消息流转为 summary + 保留最近 K 轮原文
# ============================================================
def compact_messages(
    messages: Sequence[Any],
    threshold: int | None = None,
    keep_rounds: int | None = None,
    summarizer: Callable | None = None,
) -> dict:
    """compaction：消息流超阈值 → context_edit(轻量) → compaction(重量) → ≤threshold。

    GWT①：
      - before_tokens > threshold 才触发
      - 压缩后 after_tokens ≤ threshold
      - summary 保留结构化决策语义（4 键 JSON）
      - 最近 keep_rounds 轮原文保留（新消息流 = summary 消息 + 最近 keep_rounds 轮原文）

    Returns:
        dict {applied, before_tokens, edited_removed_tokens, after_tokens, summary_json,
              summary_text, summary_msg, kept_messages}
    """
    threshold = int(threshold if threshold is not None else settings.COMPACTION_TOKEN_THRESHOLD)
    keep_rounds = int(keep_rounds if keep_rounds is not None else settings.COMPACTION_KEEP_ROUNDS)
    msgs = list(messages)

    before_tokens = sum(_msg_tokens(m) for m in msgs)
    if before_tokens <= threshold:
        # 新增 >COMPACTION_REFRESH_THRESHOLD 再触发（GWT：新增 >3000 再触发）
        return {
            "applied": False,
            "trigger": "none",
            "before_tokens": before_tokens,
            "after_tokens": before_tokens,
            "edited_removed_tokens": 0,
            "summary_json": None,
            "summary_text": "",
            "summary_msg": None,
            "kept_messages": msgs,
        }

    # —— 第 1 优先：context_edit（轻量，保留前缀缓存）——
    edit = context_edit(msgs)
    edit_msgs = edit["messages"]
    after_edit_tokens = sum(_msg_tokens(m) for m in edit_msgs)
    if after_edit_tokens <= threshold:
        return {
            "applied": False,          # context_edit 已解决，无需重量 compaction
            "trigger": "context_edit",
            "before_tokens": before_tokens,
            "after_tokens": after_edit_tokens,
            "edited_removed_tokens": edit["removed_tokens"],
            "summary_json": None,
            "summary_text": "",
            "summary_msg": None,
            "kept_messages": edit_msgs,
        }

    # —— 第 2 优先：compaction（重量，仍超才用）——
    # 目标：summary(结构化决策语义) + 最近 keep_rounds 轮原文 ≤ threshold（GWT①「最近 6 轮原文保留」）。
    # 若最近 keep_rounds 轮本身 + summary 仍超阈值 → 逐轮收缩 keep（把最老保留原文并入摘要）直到
    # keep=1；仍超则收紧 summary —— 保证压缩后 ≤ threshold。
    rounds = _group_rounds(edit_msgs)
    max_keep = min(int(keep_rounds), len(rounds)) if keep_rounds else len(rounds)
    min_keep = 1
    summary_msg: dict | None = None
    keep_target = max(min_keep, max_keep)
    while True:
        prefix = [m for rnd in rounds[:-keep_target] for m in rnd]
        kept = [m for rnd in rounds[-keep_target:] for m in rnd]
        summary_dict = build_structured_summary(prefix, summarizer)
        summary_json = json.dumps(summary_dict, ensure_ascii=False)
        summary_msg = {
            "role": "system",
            "content": "[compaction 摘要（原始历史已压缩，原结构化语义保留如下）]\n" + summary_json,
        }
        summary_tokens = _msg_tokens(summary_msg)
        kept_tokens = sum(estimate_tokens(_msg_content(m)) for m in kept)
        after_tokens = summary_tokens + kept_tokens
        if after_tokens <= threshold or keep_target <= min_keep:
            break
        keep_target -= 1

    # 兜底：keep=1 单轮原文仍超（退化场景）→ 收紧 summary 至保证 ≤ threshold
    if after_tokens > threshold and summary_msg is not None:
        while _msg_tokens(summary_msg) > 0 and after_tokens > threshold:
            content = str(summary_msg["content"])
            cut = len(content) - 200
            if cut <= 30:
                summary_msg["content"] = "[compaction 摘要]（上下文过长，结构化信息已入 artifact）"
                break
            summary_msg["content"] = content[:cut]
            after_tokens = _msg_tokens(summary_msg) + kept_tokens
    summary_json = str(summary_msg.get("content", "")).split("\n", 1)[-1].lstrip() if summary_msg else ""

    return {
        "applied": True,
        "trigger": "compaction",
        "before_tokens": before_tokens,
        "after_tokens": after_tokens,
        "edited_removed_tokens": edit["removed_tokens"],
        "summary_json": summary_json,
        "summary_text": summary_json,
        "summary_msg": summary_msg,
        "kept_messages": kept,
    }


# ============================================================
# 6. 触发策略（context_edit 优先，仍超才 compaction）
# ============================================================
def compaction_policy(messages: Sequence[Any], threshold: int | None = None) -> str:
    """每轮前评估：返回执行策略 none | context_edit | compaction。"""
    threshold = int(threshold if threshold is not None else settings.COMPACTION_TOKEN_THRESHOLD)
    total = sum(estimate_tokens(_msg_content(m)) for m in messages)
    if total <= threshold:
        return "none"
    after_edit = sum(_msg_tokens(m) for m in context_edit(messages)["messages"])
    return "compaction" if after_edit > threshold else "context_edit"


def needs_recompaction(messages: Sequence[Any], after_previous: int) -> bool:
    """compaction 后新增是否超 COMPACTION_REFRESH_THRESHOLD（GWT：新增 >3000 再触发）。"""
    total = sum(estimate_tokens(_msg_content(m)) for m in messages)
    refresh = int(settings.COMPACTION_REFRESH_THRESHOLD)
    return (total - after_previous) > refresh