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
def context_edit(messages: Sequence[Any], policy: Any | None = None, *, anchor_round: int | None = None) -> dict:
    """R4 context editing：精确删除「已完成工具调用 + 其工具结果」对与冗余中间消息。

    删除范围：工具调用 + 结果（它们已完成使命，原文已在 artifact）；紧邻其前、可被结论替代的填充式推理。
    保留范围：用户意图（用户问题）、未完成决策（有工具调用但无结果）、system 可缓存前缀。
    前缀（system 段）永不改写 → prompt cache 前缀签名不变，缓存可命中。
    anchor_round（opt-in，task-C1）：额外保护前 N 个含用户问题的轮次（AC4「闸门前字节零改动」）。

    实现委派 `app.ai.context_edit.context_edit()`；默认策略取自 settings
    （CONTEXT_EDIT_KEEP_RECENT_ROUNDS 默认 0 = 删除全部已完成对，与 task26 契约等价）。

    Returns:
        dict {edited, removed, removed_tokens, kept_tokens, messages,
              prefix_signature, prefix_stable, stable_prefix_len, removed_details}
    """
    from app.ai.context_edit import context_edit as _context_edit  # 惰性导入：避免模块级循环

    return _context_edit(messages, policy, anchor_round=anchor_round)


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
# 4.5 预算分配器 + 锚定闸门 + LLM 动态选片段（task-C1 / P4 上下文压缩固定丢轮）
# ------------------------------------------------------------
# 设计目标：把"固定保留最近 K 轮"升级为 token 预算分配器 + LLM 动态选片段，
# 并为前缀缓存引入锚定闸门（闸门前字节零改动）。
# 全部为纯函数 / 可注入 LLM，默认 compact_messages 不改行为（AC5 回归不变）。
# ============================================================
def _classify_message_type(m) -> str:
    """把单条消息归类到预算桶：system / user_query / tool_result / history。"""
    if _is_system_msg(m):
        return "system"
    if _is_tool_msg(m):
        return "tool_result"
    if _is_user_query(m):
        return "user_query"
    return "history"


class BudgetAllocator:
    """token 预算分配器（对齐 Codex：系统10% / 用户20% / 工具30% / 历史40%）。

    纯函数，确定性可测。AC1：各类型预算占比之和必须=100%，且每类型预算 ≤ 比例 × 总阈值。
    """

    RATIOS: dict = {"system": 0.10, "user_query": 0.20, "tool_result": 0.30, "history": 0.40}

    @classmethod
    def ratios(cls, ratios: dict | None = None) -> dict:
        r = cls.RATIOS.copy()
        if ratios:
            r.update({k: float(v) for k, v in ratios.items() if k in cls.RATIOS})
        total = sum(r.values()) or 1.0
        # 归一化到 Σ=1.0（防御配置手滑）
        return {k: v / total for k, v in r.items()}

    @classmethod
    def allocate(
        cls,
        messages: Sequence[Any],
        threshold: int | None = None,
        ratios: dict | None = None,
    ) -> dict:
        """计算预算分配 + 实测各桶占用。

        Returns:
            dict {threshold, ratios(归一化), budgets{type:int}, observed{type:int},
                  sum_budget_ratio(float≈1.0), valid:bool}
        """
        threshold = int(threshold if threshold is not None else settings.COMPACTION_TOKEN_THRESHOLD)
        rat = cls.ratios(ratios)
        observed = {"system": 0, "user_query": 0, "tool_result": 0, "history": 0}
        for m in messages:
            observed[_classify_message_type(m)] += _msg_tokens(m)
        budgets = {k: int(rat[k] * threshold) for k in rat}
        sum_ratio = round(sum(rat.values()), 9)
        valid = (
            abs(sum_ratio - 1.0) < 1e-9
            and all(budgets[k] <= rat[k] * threshold + 1 for k in rat)
            and all(v >= 0 for v in budgets.values())
        )
        return {
            "threshold": threshold,
            "ratios": rat,
            "budgets": budgets,
            "observed": observed,
            "sum_budget_ratio": sum_ratio,
            "valid": valid,
        }


def anchor_gate(messages: Sequence[Any], anchor_round: int = 3) -> int:
    """锚定闸门：返回受保护前缀的切片上界（exclusive）。

    保护连续 system 前缀 + 前 `anchor_round` 个含用户问题的轮次（System + 核心决策轮 + 工具前缀）。
    闸门前内容在任意压缩中不得改写 → 前缀缓存可命中（对齐 Claude 锚定策略 + Glean 静态优先）。

    Returns:
        int：messages[:retval] 为锚定不可变区（byte-stable）。
    """
    anchor_round = int(anchor_round if anchor_round is not None else settings.ANCHOR_ROUND)
    if anchor_round <= 0:
        return cache_prefix_end_compat(messages)
    rounds = _group_rounds(messages)
    end = 0
    user_rounds_seen = 0
    for rnd in rounds:
        if any(_is_user_query(m) for m in rnd):
            user_rounds_seen += 1
        end += len(rnd)
        if user_rounds_seen >= anchor_round:
            break
    # 始终额外保护连续 system 前缀（即便它构成独立轮次也无用户问题）
    return max(end, cache_prefix_end_compat(messages))


def cache_prefix_end_compat(messages: Sequence[Any]) -> int:
    """连续 system 前缀长度（与 context_edit.cache_prefix_end 同义，compaction 内联避免额外导入）。"""
    end = 0
    for m in messages:
        if _is_system_msg(m):
            end += 1
        else:
            break
    return end


def _extract_json_obj(text: str) -> dict | None:
    """从 LLM 文本稳健抽取第一个 JSON 对象（容忍 markdown/前后文）。无则 None。"""
    if not text:
        return None
    s = text.strip()
    # 去 ```json 围栏
    if "```" in s:
        import re as _re
        m = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, _re.DOTALL)
        if m:
            s = m.group(1)
        else:
            s = _re.sub(r"```.*?```", "", s, flags=_re.DOTALL).strip()
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start : i + 1])
                except Exception:
                    return None
    return None


def llm_select_fragments(
    rounds: list[list[Any]],
    plan: dict,
    llm: Callable,
    *,
    keep_rounds: int | None = None,
) -> list[int] | None:
    """LLM 动态选片段：fast 模型输出 {keep_round_ids:[...]} 决定保留哪些历史轮。

    llm: Callable[[list[dict]] -> str]，输入 messages，返回模型文本。
    失败/窗口外 → 返回 None（调用方回退规则选片段）。
    """
    keep_rounds = int(keep_rounds if keep_rounds is not None else settings.COMPACTION_KEEP_ROUNDS)
    if not rounds or llm is None:
        return None
    # 构造决策上下文：每轮给 id + 角色摘要 + token + 是否含工具/决策关键词
    budget_hint = plan.get("budgets", {})
    lines = []
    for i, rnd in enumerate(rounds):
        toks = sum(_msg_tokens(m) for m in rnd)
        roles = sorted({m.get("role") if isinstance(m, dict) else getattr(m, "role", "?") for m in rnd})
        snippet = _render(rnd)[:240].replace("\n", " ")
        lines.append(f"[{i}] roles={roles} tokens={toks} :: {snippet}")
    sys_prompt = (
        "你是上下文压缩选择器。给定多轮对话，选出最该保留的轮次 id（最多 "
        f"{keep_rounds} 个），使关键信息（用户偏好/目标/决策/未决问题/关键事实）不丢失，"
        "冗余工具结果可丢弃。只输出 JSON：{\"keep_round_ids\": [int,...]}。"
    )
    user_prompt = (
        f"预算(每类 token 上限) = {budget_hint}\n"
        f"共 {len(rounds)} 轮，请选 ≤{keep_rounds} 个保留：\n"
        + "\n".join(lines)
    )
    try:
        out = llm([{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}])
        obj = _extract_json_obj(out if isinstance(out, str) else str(out))
        if not obj or "keep_round_ids" not in obj:
            return None
        ids = [int(x) for x in obj["keep_round_ids"] if isinstance(x, (int, float))]
        ids = [i for i in ids if 0 <= i < len(rounds)]
        if not ids:
            return None
        # 不超过 keep_rounds（超出取前 keep_rounds 个，保持确定性）
        return ids[: max(1, keep_rounds)]
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[compaction] LLM 选片段失败，回退规则选片段: {type(exc).__name__}: {exc}")
        return None


def _round_value_score(rnd: list[Any]) -> float:
    """规则价值评分：用户问题/决策关键词/工具调用/偏好信号 → 高分；越新略加权。"""
    text = _render(rnd)
    score = 0.0
    if any(_is_user_query(m) for m in rnd):
        score += 2.0
    for kw in ("决策", "目标", "偏好", "记住", "计划", "待办", "下一步", "关键", "结论", "总结"):
        if kw in text:
            score += 1.0
    if any(_is_tool_call(m) for m in rnd) and any(_is_tool_msg(m) for m in rnd):
        score += 0.5  # 已完成工具对（结论型）有一定保留价值
    if _is_system_msg(rnd[0]) if rnd and _is_system_msg(rnd[0]) else False:
        score += 0.2
    return score


def _default_fragment_selection(
    rounds: list[list[Any]],
    *,
    keep_rounds: int | None = None,
    plan: dict | None = None,
) -> list[int]:
    """规则选片段（确定性回退）：按价值评分排序，取 top-keep_rounds；同分取较新。

    与旧"固定保留最近 K 轮"等价（最近轮天然高分），但优先保留含关键信号的旧轮，
    解决"用户第 7 轮问第 3 轮数据被压掉"问题。
    """
    keep_rounds = int(keep_rounds if keep_rounds is not None else settings.COMPACTION_KEEP_ROUNDS)
    if not rounds:
        return []
    scored = [(i, _round_value_score(rnd)) for i, rnd in enumerate(rounds)]
    # 降序：分数高优先；同分索引大（较新）优先
    scored.sort(key=lambda t: (t[1], t[0]), reverse=True)
    top = scored[: max(1, keep_rounds)]
    return sorted(i for i, _ in top)


def make_fast_llm() -> Callable:
    """构造真实 fast 模型调用（火山 ark plan/v3 deepseek-v4-flash），供测试窗口内注入 llm_select_fragments。

    仅窗口内（12:00-14:00 / 18:00-9:00）调用。其余时段调用方应不注入（走规则回退）。
    惰性导入 scripts.eval.llm_client，避免 app 层依赖 scripts。
    """
    from scripts.eval import llm_client

    def _call(messages: list[dict]) -> str:
        return llm_client.call(messages=messages, model="fast", temperature=0.0, max_tokens=500)["text"]

    return _call


def _compact_legacy(edit_msgs, threshold, keep_rounds, summarizer, before_tokens, edit_removed_tokens) -> dict:
    """原版 compaction（task26 行为逐字节等价）：context_edit 后仍超 → summary + 最近 keep_rounds 轮原文。

    仅用于默认 compact_messages 调用（无 anchor_round / 无 llm 注入）以保 AC5 回归。
    """
    rounds = _group_rounds(edit_msgs)
    max_keep = min(int(keep_rounds), len(rounds)) if keep_rounds else len(rounds)
    min_keep = 1
    summary_msg = None
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
        "edited_removed_tokens": edit_removed_tokens,
        "summary_json": summary_json,
        "summary_text": summary_json,
        "summary_msg": summary_msg,
        "kept_messages": kept,
    }


def _compact_with_budget(
    edit_msgs,
    threshold,
    keep_rounds,
    summarizer,
    *,
    edit,
    llm=None,
    llm_select=None,
    anchor_round=None,
) -> dict:
    """增强 compaction：预算分配器 + 锚定闸门 + LLM/规则选片段。

    保证：① after_tokens ≤ threshold；② 锚定闸门前字节零改动（frozen 原文前置）；
    ③ summary 仍 4 键 JSON（向后兼容 graph.compact_node 消费）；④ keep_round_ids 含关键旧轮。
    """
    if llm_select is None:
        llm_select = bool(getattr(settings, "COMPACTION_LLM_SELECT", True))
    keep_rounds = int(keep_rounds if keep_rounds is not None else settings.COMPACTION_KEEP_ROUNDS)

    # —— 锚定闸门：冻结闸门前（前置，保证前缀缓存）——
    gate_idx = 0
    if anchor_round is not None:
        gate_idx = anchor_gate(edit_msgs, int(anchor_round))
    frozen = list(edit_msgs[:gate_idx])
    body = list(edit_msgs[gate_idx:])

    rounds = _group_rounds(body)
    plan = BudgetAllocator.allocate(edit_msgs, threshold=threshold)

    # —— 选片段：LLM（注入时）或 规则回退 ——
    if llm is not None and llm_select:
        keep_ids = llm_select_fragments(rounds, plan, llm, keep_rounds=keep_rounds)
        if keep_ids is None:
            keep_ids = _default_fragment_selection(rounds, keep_rounds=keep_rounds, plan=plan)
    else:
        keep_ids = _default_fragment_selection(rounds, keep_rounds=keep_rounds, plan=plan)
    keep_set = set(keep_ids)

    # —— 组装：frozen 原文 + 选中轮原文 + summary(非选中且非 frozen) ——
    selected_flat = [m for i, rnd in enumerate(rounds) if i in keep_set for m in rnd]
    kept = frozen + selected_flat
    to_summarize = frozen + [m for i, rnd in enumerate(rounds) if i not in keep_set for m in rnd]
    summary_dict = build_structured_summary(to_summarize, summarizer)
    summary_json = json.dumps(summary_dict, ensure_ascii=False)
    summary_msg = {
        "role": "system",
        "content": "[compaction 摘要（原始历史已压缩，原结构化语义保留如下）]\n" + summary_json,
    }

    def _recalc():
        return _msg_tokens(summary_msg) + sum(_msg_tokens(m) for m in kept)

    after_tokens = _recalc()

    # —— 兜底：超阈值则逐轮移除价值最低选中轮（并入 summary 文本），仍超则收紧 summary ——
    if after_tokens > threshold:
        ordered = sorted(keep_set)  # 最老优先移除
        for victim in ordered:
            if after_tokens <= threshold or len(keep_set) <= 1:
                break
            keep_set.discard(victim)
            # 把被移除轮内容追加进 summary（确定性，不重跑 LLM）
            extra = _render(rounds[victim]) if 0 <= victim < len(rounds) else ""
            if extra:
                summary_msg["content"] = summary_msg["content"] + "\n" + extra
            # 重算 kept
            selected_flat = [m for i, rnd in enumerate(rounds) if i in keep_set for m in rnd]
            kept = frozen + selected_flat
            after_tokens = _recalc()
    if after_tokens > threshold:
        while _msg_tokens(summary_msg) > 0 and after_tokens > threshold:
            content = str(summary_msg["content"])
            cut = len(content) - 200
            if cut <= 30:
                summary_msg["content"] = "[compaction 摘要]（上下文过长，结构化信息已入 artifact）"
                break
            summary_msg["content"] = content[:cut]
            after_tokens = _recalc()

    summary_json = str(summary_msg.get("content", "")).split("\n", 1)[-1].lstrip() if summary_msg else ""
    # 输出顺序：frozen 前置（保前缀缓存）→ summary → 选中轮原文
    out_messages = frozen + [summary_msg] + selected_flat

    return {
        "applied": True,
        "trigger": "compaction",
        "before_tokens": edit.get("before_tokens", 0),
        "after_tokens": after_tokens,
        "edited_removed_tokens": edit.get("removed_tokens", 0),
        "summary_json": summary_json,
        "summary_text": summary_json,
        "summary_msg": summary_msg,
        "kept_messages": out_messages,
        # task-C1 扩展字段（不影响旧消费方）
        "anchor_gate_idx": gate_idx,
        "budget_plan": plan,
        "keep_round_ids": sorted(keep_set),
    }


# ============================================================
# 5. compaction：消息流转为 summary + 保留最近 K 轮原文
# ============================================================
def compact_messages(
    messages: Sequence[Any],
    threshold: int | None = None,
    keep_rounds: int | None = None,
    summarizer: Callable | None = None,
    *,
    llm: Callable | None = None,
    llm_select: bool | None = None,
    anchor_round: int | None = None,
) -> dict:
    """compaction：消息流超阈值 → context_edit(轻量) → compaction(重量) → ≤threshold。

    GWT①：
      - before_tokens > threshold 才触发
      - 压缩后 after_tokens ≤ threshold
      - summary 保留结构化决策语义（4 键 JSON）
      - 最近 keep_rounds 轮原文保留（新消息流 = summary 消息 + 最近 keep_rounds 轮原文）

    task-C1（P4 上下文压缩固定丢轮）增强（opt-in，向后兼容）：
      - anchor_round：启用锚定闸门，闸门前字节零改动（保护前缀缓存）。
      - llm：注入 fast 模型调用，由 LLM 动态选保留片段（keep_round_ids）；
             未注入时回退规则选片段（_default_fragment_selection）。

    默认（anchor_round=None 且 llm=None）行为与原版逐字节一致 → task26/96 回归不变（AC5）。

    Returns:
        dict {applied, before_tokens, edited_removed_tokens, after_tokens, summary_json,
              summary_text, summary_msg, kept_messages, [anchor_gate_idx, budget_plan, keep_round_ids]}
    """
    threshold = int(threshold if threshold is not None else settings.COMPACTION_TOKEN_THRESHOLD)
    keep_rounds = int(keep_rounds if keep_rounds is not None else settings.COMPACTION_KEEP_ROUNDS)
    if llm_select is None:
        llm_select = bool(getattr(settings, "COMPACTION_LLM_SELECT", True))
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
        try:
            from app.otel.exporter import get_otel_exporter
            get_otel_exporter().record_compaction_event(
                before_tokens=before_tokens, after_tokens=after_edit_tokens,
                dropped_rounds=edit["removed_tokens"], policy="context_edit",
            )
        except Exception:
            pass
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
    # 增强路径（锚定/LLM）与默认路径分流：默认路径与原版逐字节一致（AC5 回归）。
    use_enhanced = (anchor_round is not None) or (llm is not None)
    if use_enhanced:
        result = _compact_with_budget(
            edit_msgs, threshold, keep_rounds, summarizer,
            edit={"before_tokens": before_tokens, "removed_tokens": edit["removed_tokens"]},
            llm=llm, llm_select=llm_select, anchor_round=anchor_round,
        )
        pol = "compact_budget"
    else:
        result = _compact_legacy(
            edit_msgs, threshold, keep_rounds, summarizer,
            before_tokens=before_tokens, edit_removed_tokens=edit["removed_tokens"],
        )
        pol = "compaction"
    try:
        from app.otel.exporter import get_otel_exporter
        get_otel_exporter().record_compaction_event(
            before_tokens=result["before_tokens"], after_tokens=result["after_tokens"],
            dropped_rounds=result.get("dropped_rounds", 0), policy=pol,
        )
    except Exception:
        pass
    return result


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