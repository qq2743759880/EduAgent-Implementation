"""R01-b：mem0 式对话窗记忆抽取（LLM 事实抽取）。

输入是一段**对话窗**（用户 query + assistant 回复成对，最近 N 条），而非单条 query：
- 用户侧：显式偏好/目标/纠正（规则抽取 `ingest.detect_memories` 已覆盖，高精度但低召回）；
- 助手侧：助手在回复中陈述、且对后续个性化有用的**用户事实**（如「该用户的课程进度是…」
  「其目标考试时间为…」），纯规则无法覆盖，由本模块 LLM 抽取补齐（mem0 ADD 语义）。

铁律（对齐 PRD R01 两要点）：
- LLM **链路失败**（网络/HTTP/超时/输出完全不可解析）必须显式返回 error，由调用方落 degraded
  队列项——**禁止把失败伪装成空列表**（空列表的合法语义是「本轮确无值得记忆的信息」）；
- 合法空结果 `([], None)` 不触发 degraded；
- 输出被 max_tokens 截断时按 T9-C1 逐条 salvage 已闭合的合法元素，仅当连一条完整元素都
  取不出时才判 `llm_unparseable_output` 落 degraded（合法事实不因尾部残缺连坐丢弃）。

默认 LLM 复用子代理 `_default_llm`（fast 模型，cost 友好，与 Dream 巩固同通道）；
测试/窗口验证可注入 `llm` 假件（签名 `async llm(messages, model=...) -> str`）。
"""
from __future__ import annotations

import json
from typing import Awaitable, Callable

from loguru import logger

from app.ai.memory.schemas import MEMORY_TOPICS, MEMORY_TYPES, MemoryCandidate

# mem0 同款抽取指令：只抽「跨会话仍有用的用户事实」，闲聊/一次性问答不抽
MEMORY_EXTRACT_SYSTEM_PROMPT = """你是用户长期记忆抽取器。从给定的多轮对话窗（含用户与助手双方发言）中，\
抽取关于该用户的、跨会话仍有价值的长期事实，覆盖两类来源：
1) 用户自己陈述的偏好、目标、纠正、个人背景；
2) 助手在回复中陈述、且用户未否认的关于该用户的事实性信息（如学习进度、已选课程、考试时间安排）。

抽取规则：
- 只抽长期有用的事实；一次性问答、寒暄、情绪、与用户无关的通用知识一律不抽；
- 每条事实写成第三人称陈述句（如「用户目标是雅思 6.5」「用户偏好 Python 而非 Java」），\
不要照抄问句，不要包含对话序号；
- 事实必须由对话内容直接支持，不得推断或臆造；证据不足就不抽；
- 同一事实只输出一条，去重合并。

仅输出一个 JSON 数组（不要 markdown 围栏、不要解释），元素形如：
[{"content": "事实陈述句", "memory_type": "preference|goal|profile|correction|fact", \
"topic": "learning-goals|preferences|profile|corrections|general", "importance": 3-5}]
- memory_type：偏好=preference，目标=goal，背景画像=profile，纠正=correction，其它事实=fact；
- topic 无法归入前四类时用 general；
- importance：明确目标/纠正=5，明确偏好=4，一般事实=3。
没有值得记忆的信息时输出 []。"""


def _render_window(messages: list[dict]) -> list[dict]:
    """对话窗 → LLM messages（仅 user/assistant 双方发言，单条截断防 prompt 膨胀）。"""
    lines: list[str] = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").lower()
        content = m.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if role.startswith("user") or role in ("human",):
            speaker = "用户"
        elif role.startswith("assistant") or role in ("ai", "bot"):
            speaker = "助手"
        else:
            continue  # system/tool 等不参与事实抽取
        lines.append(f"{speaker}：{content.strip()[:2000]}")
    if not lines:
        return []
    return [
        {"role": "system", "content": MEMORY_EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": "对话窗如下：\n" + "\n".join(lines)},
    ]


def _coerce_entry(raw: object) -> MemoryCandidate | None:
    """校验/规整单条 LLM 输出；字段非法则保守丢弃该条（不影响其它合法条目）。"""
    if not isinstance(raw, dict):
        return None
    content = str(raw.get("content") or "").strip()
    if len(content) < 2:
        return None
    mtype = str(raw.get("memory_type") or "fact").strip().lower()
    if mtype not in MEMORY_TYPES:
        mtype = "fact"
    topic = str(raw.get("topic") or "general").strip().lower()
    if topic not in MEMORY_TOPICS:
        topic = "general"
    try:
        importance = int(raw.get("importance") or 4)
    except (TypeError, ValueError):
        importance = 4
    importance = max(1, min(5, importance))
    return MemoryCandidate(
        content=content[:2000], memory_type=mtype, topic=topic,
        importance=importance, source="llm_window",
    )


def _salvage_json_array(text: str) -> list[dict]:
    """截断容错（T9-C1）：从被 max_tokens 截断的输出中逐条 salvage 完整合法元素。

    仅在整段 ``json.loads`` 失败时兜底调用：从首个 ``[`` 起做括号 / 字符串状态扫描，
    逐个收集**已闭合**的顶层 ``{...}`` 元素并单独 json 解析；未闭合的尾部元素丢弃。
    返回可解析元素列表（空列表 = 连一条完整元素都 salvage 不出 = 真不可解析）。
    """
    if not isinstance(text, str):
        return []
    start = text.find("[")
    if start < 0:
        return []
    items: list[dict] = []
    depth = 0          # 数组内嵌套深度：0 = 顶层元素位置
    in_str = False
    escaped = False
    elem_start = -1
    for i in range(start + 1, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
            if depth == 1 and ch == "{":
                elem_start = i
        elif ch in "}]":
            if depth == 0:
                if ch == "]":
                    break  # 数组已闭合，其后内容与本次 salvage 无关
                continue
            depth -= 1
            if depth == 0 and elem_start >= 0:
                try:
                    obj = json.loads(text[elem_start:i + 1])
                except Exception:
                    obj = None
                if isinstance(obj, dict):
                    items.append(obj)
                elem_start = -1
    return items


async def extract_candidates_llm(
    messages: list[dict],
    *,
    model: str | None = None,
    llm: Callable[..., Awaitable[str]] | None = None,
    max_tokens: int | None = None,
) -> tuple[list[MemoryCandidate], str | None]:
    """对话窗 → (记忆候选, error)。

    - 成功（含合法空结果）：error=None；空结果语义＝本轮无值得记忆的信息；
    - 失败（空窗/LLM 调用异常/输出不可解析）：返回 ([], error_str)，调用方必须落 degraded，
      **不得当作空结果静默吞掉**。
    """
    from app.config import settings

    llm_messages = _render_window(messages)
    if not llm_messages:
        return [], "empty_window"

    use_model = model or str(getattr(settings, "MEMORY_EXTRACT_MODEL", "fast"))
    use_max_tokens = int(max_tokens if max_tokens is not None
                         else getattr(settings, "MEMORY_EXTRACT_MAX_TOKENS", 600))
    try:
        if llm is not None:
            raw_text = await llm(llm_messages, model=use_model)
        else:
            # 与 Dream 巩固同通道：子代理 LLM（fast），内部已做线程池卸载不阻塞事件循环
            from app.ai.subagents.runner import _default_llm

            raw_text = await _default_llm(llm_messages, model=use_model)
    except Exception as exc:
        return [], f"llm_call_failed: {type(exc).__name__}: {str(exc)[:200]}"

    if not isinstance(raw_text, str) or not raw_text.strip():
        return [], "llm_empty_output"

    # 复用 Dream 的 JSON 数组容错解析（容忍 ```json 围栏/前后噪声）；解析失败=链路失败而非空结果
    from app.ai.memory.dream import _extract_json_array

    arr = _extract_json_array(raw_text)
    partial = False
    if not arr:
        # 区分「合法空数组」与「不可解析」：仅当文本中确实存在可 json 解析的 [] 切片时
        # 才算合法空结果；普通散文里的方括号不会误判（json 解析失败 → degraded）。
        import json as _json

        stripped = raw_text.strip()
        a, b = stripped.find("["), stripped.rfind("]")
        is_empty_array = False
        if a >= 0 and b > a:
            try:
                is_empty_array = _json.loads(stripped[a:b + 1]) == []
            except Exception:
                is_empty_array = False
        if is_empty_array:
            return [], None
        # T9-C1 截断容错：整批解析失败时逐条 salvage 已闭合的合法元素，
        # 仅真正不可解析的部分落 degraded（前几条合法事实不再被尾部截断连坐丢弃）。
        salvaged = _salvage_json_array(raw_text)
        if not salvaged:
            logger.warning(f"[Memory:extract] LLM 输出不可解析，判 degraded：{raw_text[:200]}")
            return [], "llm_unparseable_output"
        arr = salvaged
        partial = True

    candidates: list[MemoryCandidate] = []
    seen: set[str] = set()
    for raw_entry in arr:
        cand = _coerce_entry(raw_entry)
        if cand is None or cand.content in seen:
            continue
        seen.add(cand.content)
        candidates.append(cand)
    if partial:
        logger.warning(
            f"[Memory:extract] 输出被截断，已 salvage {len(candidates)} 条完整合法元素入库(partial=true)"
        )
    return candidates, None
