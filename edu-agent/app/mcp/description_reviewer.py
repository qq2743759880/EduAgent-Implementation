# -*- coding: utf-8 -*-
"""task33 MCP 描述体检：规则打分 + FAST 重写 + 审计日志。

对齐 tech-source-audit §三（Anthropic「工具测试代理减少 40% 完成时间」→ 差描述浪费轮询）：
  - 用确定性规则对 mcp_tool.description 打分（0-100，六项标准逐条给分），
    分项：动词开头+20 / 何时不该用+15 / 参数说明+20 / 返回结构+15 / 示例+10 / 无歧义+20。
  - score < 70 触发 FAST 模型（火山 ark deepseek-v4-flash）按五要素规范重写，
    结果写入 mcp_tool.description_rewritten（原 description 仅展示）。
  - 每次体检写审计日志 mcp_tool_description_review_log（score/reasons/breaches/rewritten/operator）。

设计约束：
  - 规则打分是纯函数，零外部依赖，可直接单测。
  - FAST 调用是非阻塞封装（run_in_executor），LLM 失败时降级：返回原描述、rewritten_by_llm=False，
    不阻断体检流程（降级如实标注）。
  - 任意异常都能安全返回局部结果，绝不向上抛（体检是一次后台增强，不应让 discover 失败）。
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.common.logging import logger

# 重写后描述的目标长度上限（task33 GWT①：≤120 字）
REWRITE_MAX_CHARS = 120
# 触发重写的分界线
REWRITE_THRESHOLD = 70

# ---- 分项满分 ----
_SCORE_VERB_START = 20
_SCORE_WHEN_NOT = 15
_SCORE_PARAM = 20
_SCORE_RETURN = 15
_SCORE_EXAMPLE = 10
_SCORE_NO_AMBIGUITY = 20


@dataclass
class ReviewScore:
    """一次描述的规则体检结果。"""
    total: int = 0
    verb_start: int = 0
    when_not: int = 0
    param: int = 0
    return_structure: int = 0
    example: int = 0
    no_ambiguity: int = 0
    # 未得分项的缺憾说明（供审计 / 前端展示「差距在哪」）
    breaches: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "verb_start": self.verb_start,
            "when_not": self.when_not,
            "param": self.param,
            "return_structure": self.return_structure,
            "example": self.example,
            "no_ambiguity": self.no_ambiguity,
            "breaches": self.breaches,
        }


def _clean(desc: str) -> str:
    return (desc or "").strip().replace("\r", " ").replace("\n", " ")


def _has(desc: str, *keywords: str) -> bool:
    d = desc.lower()
    return any(k.lower() in d for k in keywords)


def _required_param_names(schema: dict[str, Any]) -> list[str]:
    """从 input_schema 取 required 参数名（做参数域匹配依据）。"""
    if not isinstance(schema, dict):
        return []
    required = schema.get("required")
    if isinstance(required, list):
        return [str(p) for p in required if str(p)]
    props = schema.get("properties")
    if isinstance(props, dict):
        return [str(k) for k in props.keys() if str(k)]
    return []


def score_description(desc: str, schema: dict[str, Any] | None = None) -> ReviewScore:
    """确定性规则打分。返回逐分项 + 总分的 ReviewScore + 缺憾说明。"""
    d = _clean(desc)
    schema = schema or {}
    s = ReviewScore()
    if not d:
        s.breaches.append("描述为空")
        return s

    # 1) 动词开头（+20）：以动作性表达起句。启发式：不以填充词/代词起头，且首字符为 CJK 或字母。
    fillers = ("此工具", "这个工具", "该工具", "这是一个", "用来描述", "this is", "this tool",
               "the ", "please ", "用于展示工具", "看看", "描述-")
    if d[0].isalpha() and not _has(fillers[0], d[:6]) and not any(d.startswith(f) for f in fillers):
        s.verb_start = _SCORE_VERB_START
    else:
        s.breaches.append("不以动词/动作短语起句")

    # 2) 何时不该用（+15）
    if _has(d, "不用", "不建议", "避免", "何时用", "不适用于", "仅当", "when not", "don't use", "avoid"):
        s.when_not = _SCORE_WHEN_NOT
    else:
        s.breaches.append("缺少『何时不该用』边界说明")

    # 3) 参数说明（+20）：描述了参数域 —— 命中 required 参数名 或 出现「参数」标识
    need_params = _required_param_names(schema)
    if need_params and any(p in d for p in need_params):
        s.param = _SCORE_PARAM
    elif _has(d, "参数", "参数:", "参数域", "需要传入", "输入", "arguments", "args"):
        s.param = _SCORE_PARAM
    else:
        s.breaches.append("缺少参数域说明")

    # 4) 返回结构（+15）
    if _has(d, "返回", "输出", "结果为", "结果:", "返回:", "returns", "result", "output"):
        s.return_structure = _SCORE_RETURN
    else:
        s.breaches.append("缺少返回结构说明")

    # 5) 示例（+10）：出现示例标记，或 schema 自带 example/default 兜底
    if _has(d, "示例", "例如", "例:", "例子", "example", "举例") or _schema_has_example(schema):
        s.example = _SCORE_EXAMPLE
    else:
        s.breaches.append("缺少典型调用示例")

    # 6) 无歧义（+20）：长度足够且结构化（有句读/分段）
    if len(d) >= 15 and _has(d, "。", "；", ";", "，", ",", "\n"):
        s.no_ambiguity = _SCORE_NO_AMBIGUITY
    elif len(d) >= 25:
        s.no_ambiguity = _SCORE_NO_AMBIGUITY
    else:
        s.breaches.append("描述过短 / 语义模糊，缺少句读或分段")

    s.total = (s.verb_start + s.when_not + s.param +
               s.return_structure + s.example + s.no_ambiguity)
    return s


def _schema_has_example(schema: dict[str, Any]) -> bool:
    def _scan(obj: Any) -> bool:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("example", "default", "examples") and v is not None:
                    return True
                if isinstance(v, (dict, list)) and _scan(v):
                    return True
        elif isinstance(obj, list):
            return any(_scan(x) for x in obj if isinstance(x, (dict, list)))
        return False

    return isinstance(schema, dict) and _scan(schema)


# ============================================================
# FAST 重写（五要素规范 ≤120 字）
# ============================================================
def _rewrite_prompt(desc: str, schema: dict[str, Any]) -> list[dict]:
    schema_s = json.dumps(schema, ensure_ascii=False) if schema else "{}"
    return [
        {"role": "system", "content": (
            "你是MCP工具描述重写专家。把工具描述改写为遵循五要素规范的精炼中文描述（≤120字）："
            "1 做什么（一句话，以动词开头）；"
            "2 何时用/何时不用（边界）；"
            "3 参数域（要求的键及取值）；"
            "4 返回结构（稳定字段）；"
            "5 示例（一个典型参数JSON）。"
            "只输出改写后的描述文本本身，不要任何解释、前缀或markdown符号。"
        )},
        {"role": "user", "content": f"工具名:{_name_of(schema)}\n原始描述:{desc}\n参数Schema:{schema_s}"},
    ]


def _name_of(schema: dict[str, Any]) -> str:
    return "未知工具"


def _post_process(raw: str) -> str:
    """清洗 LLM 输出：去换行/包裹符号，截断到上限。"""
    out = (raw or "").strip()
    # 去掉可能的 ``` / 引号包裹
    out = re.sub(r"^```(?:json|text)?", "", out).strip()
    out = re.sub(r"```$", "", out).strip().strip("\"'")
    out = " ".join(out.split())
    return out[:REWRITE_MAX_CHARS]


def _call_fast_sync(messages: list[dict], timeout: float = 30.0) -> str:
    """同步调用 FAST（火山 ark deepseek-v4-flash）；失败抛异常由上层降级。"""
    from app.chat.generator import _ChatClient  # 延迟导入避免模块环

    client = _ChatClient.get()
    return client.call_chat(
        messages=messages,
        model="fast",
        temperature=0.0,
        max_tokens=256,
        timeout=timeout,
    )


async def _call_fast_async(messages: list[dict], timeout: float = 30.0) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _call_fast_sync(messages, timeout))


# ============================================================
# 对单工具执行完整体检（打分 → 必要时 FAST 重写）
# ============================================================
async def review_tool_description(
    *,
    tool_id: int,
    tool_name: str,
    description: str,
    input_schema: dict[str, Any],
    server_id: int,
    operator_user_id: int | None = None,
    trace_id: str = "",
    rewrite_enabled: bool = True,
) -> dict:
    """对单个工具做描述体检。始终落审计日志 + 回写 mcp_tool。

    返回 {tool_id, score, rewritten, rewritten_by_llm, breaches, error?}。
    所有异常吞掉并写 error（体检为后台增强，绝不阻断 discover）。
    """
    from . import registry  # 延迟导入避免环

    schema = input_schema if isinstance(input_schema, dict) else {}
    scored = score_description(description, schema)
    rewritten: str = description
    rewritten_by_llm = False
    error: str | None = None

    need_rewrite = rewrite_enabled and scored.total < REWRITE_THRESHOLD
    if need_rewrite and description:
        try:
            raw = await _call_fast_async(_rewrite_prompt(description, schema))
            cleaned = _post_process(raw)
            if cleaned and cleaned != description:
                rewritten = cleaned
                rewritten_by_llm = True
        except Exception as exc:  # noqa: BLE001 —— LLM 降级，不阻断
            error = f"{type(exc).__name__}: {exc}"[:512]
            logger.warning(f"[DescReview] tool={tool_name} FAST 重写失败，保留原描述：{error}")

    try:
        await registry.write_description_review(
            tool_id=tool_id, score=scored.total,
            rewritten=(rewritten if rewritten_by_llm else None),
        )
        await registry.insert_description_review_log(
            server_id=server_id, tool_id=tool_id, tool_name=tool_name,
            score=scored.total, reasons=scored.to_dict(), rewritten=rewritten,
            rewritten_by_llm=rewritten_by_llm, original_desc=description,
            operator_user_id=operator_user_id, trace_id=trace_id,
        )
    except Exception as exc:  # noqa: BLE001 —— 审计失败不阻断
        logger.warning(f"[DescReview] tool={tool_name} 审计落库失败：{type(exc).__name__}: {exc}")
        error = (error + "；审计落库失败" if error else "审计落库失败")

    return {
        "tool_id": tool_id,
        "tool_name": tool_name,
        "score": scored.total,
        "breaches": scored.breaches,
        "rewritten": rewritten,
        "rewritten_by_llm": rewritten_by_llm,
        "error": error,
    }


async def run_description_review(
    server_id: int | None = None,
    operator_user_id: int | None = None,
    trace_id: str = "",
) -> dict:
    """批量体检（可选按 server 过滤）。discover 后与管理端『描述体检』按钮共用。"""
    from . import registry

    rows = await registry.list_tools_for_review(server_id=server_id)
    reviewed: list[dict] = []
    low_count = 0
    rewritten_count = 0
    t0 = time.perf_counter()
    for r in rows:
        res = await review_tool_description(
            tool_id=int(r["id"]), tool_name=str(r["tool_name"]),
            description=str(r.get("description") or ""),
            input_schema=r.get("input_schema") or {},
            server_id=int(r["server_id"]),
            operator_user_id=operator_user_id, trace_id=trace_id,
        )
        reviewed.append(res)
        if res["score"] < REWRITE_THRESHOLD:
            low_count += 1
        if res.get("rewritten_by_llm"):
            rewritten_count += 1
    cost_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "scanned": len(reviewed),
        "low_score": low_count,
        "rewritten_by_llm": rewritten_count,
        "items": reviewed,
        "elapsed_ms": cost_ms,
    }