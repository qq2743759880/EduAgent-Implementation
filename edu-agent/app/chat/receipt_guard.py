# -*- coding: utf-8 -*-
"""F-W1-GUARD（AUTO20 T7，C-W1-② 硬化）：答案层写类回执机检护栏。

根因（两次实证，见 .opencode/plans/critique-backlog-tracker.md W-NEXT-WRITE1 段）：
  chat 答案 LLM 在工具阶段**未真实执行**时仍可能捏造「已收藏/已提交/已导入」成功回执
  （工具被权限门拦截后、exact-pin 拒绝后，答案照谎报成功）。已有缓解只覆盖 prompt 层
  （tool 子代理「严禁虚构调用结果」指令）与工具层（tool_calling.py 诚实性约束注入），
  **answer 生成层无机检**——本模块补最后一道硬护栏。

语义（只拦写类完成语义，只读工具提及不算）：
  done 帧/响应体组装时检测——答案文本提及了写类完成关键词（已收藏/已提交/…）或写类
  工具名（favorite_add/…），但 mcp_tool_calls 凭据里**没有任何 status=="success" 的
  真实执行凭据** → ① 打 tool_receipt_unverified=True 标记 ② 答案文本**追加**诚实修正句
  （不改写原答案，追加提示句；禁删改用户看到的原内容语义）。
  真实凭据存在（任一工具 success）→ 不标记不追加，零行为变化。

插入点（单一事实源，防 P2-23 漂移）：
  - 流式：service.make_stream_finalize.build_finalize（旧 chat_stream 路径 + 默认
    graph_stream 路径共用本工厂，done 帧 data 由它组装）；
  - 非流式：service.chat_answer（RagAnswerResponse 组装处）。
  前端契约：done.data 与 RagAnswerResponse 均为**增量加字段**——test_sse_envelope_contract
  用 `DONE_DATA_KEYS <= keys` 子集断言、RagAnswerResponse 本就后挂 mcp_tool_calls 字段，
  加字段不破契约。
"""
from __future__ import annotations

import re

from app.chat.schemas import MCPToolCallSummary
from app.config import settings

# 诚实修正句（追加到答案尾部；不含删改原内容语义，仅补充「以工具调用记录为准」）
TOOL_RECEIPT_NOTICE = "⚠️ 上述工具操作未实际执行，请以工具调用记录为准。"

# done 帧 / RagAnswerResponse 上的标记字段名（前端渲染黄色警示条依据）
TOOL_RECEIPT_FLAG = "tool_receipt_unverified"


def _write_phrases() -> list[str]:
    """写类完成语义关键词（配置化，Settings.TOOL_RECEIPT_WRITE_PHRASES，禁硬编码散落）。"""
    return [str(p).strip() for p in getattr(settings, "TOOL_RECEIPT_WRITE_PHRASES", []) or [] if str(p).strip()]


def _write_tools() -> list[str]:
    """写类工具名清单（配置化，Settings.TOOL_RECEIPT_WRITE_TOOLS）。"""
    return [str(t).strip().lower() for t in getattr(settings, "TOOL_RECEIPT_WRITE_TOOLS", []) or [] if str(t).strip()]


def _readonly_tools() -> list[str]:
    """只读工具清单（Settings.TOOL_RECEIPT_READONLY_TOOLS）：提及只命中只读工具的答案不算捏造。"""
    return [str(t).strip().lower() for t in getattr(settings, "TOOL_RECEIPT_READONLY_TOOLS", []) or [] if str(t).strip()]


def _has_real_write_receipt(mcp_tool_calls: list[MCPToolCallSummary] | None) -> bool:
    """凭据判定：任一工具 status=="success" 即视为「有真实工具执行凭据」。

    注意：被权限门拦截（status=error）、HITL 挂起（status=error/awaiting_confirm）、
    失败/超时（error/timeout）都**不构成**凭据——它们恰是捏造回执的高发场景。
    """
    for s in (mcp_tool_calls or []):
        if str(getattr(s, "status", "")).strip().lower() == "success":
            return True
    return False


def _mentions_write_semantics(answer_text: str, *, mcp_tool_calls: list[MCPToolCallSummary] | None) -> bool:
    """答案文本是否提及「写类完成语义」。

    判定（三条件，任一命中即 True）：
      1. 命中写类完成关键词（已收藏/已提交/…，配置化列表 substring 匹配）；
      2. 命中写类工具名（favorite_add 等，词边界匹配防误伤普通英文词）；
      3. ——只读场景排除：若答案提及的工具名**全部**属于只读清单（search_knowledge 等），
         不算写类语义（任务铁律：只拦写类完成语义，只读工具提及不算）。

    只读排除的精确语义：substring 命中的关键词不参与工具名分析（「已收藏」不是工具名）；
    工具名命中的条目若全部 ∈ 只读清单 → 整体不判写类。
    """
    text = answer_text or ""
    if not text:
        return False

    phrases = _write_phrases()
    for p in phrases:
        if p and p in text:
            return True

    write_tools = _write_tools()
    readonly_tools = set(_readonly_tools())
    # 工具名按「词边界」匹配（\b），避免 favorite_add 命中 普通 add / search_knowledge 命中 knowledge 等误伤
    mentioned: list[str] = []
    for name in write_tools:
        if not name:
            continue
        if re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", text):
            mentioned.append(name)
    # 全部命中工具 ∈ 只读清单 → 只读提及，不算
    if mentioned and all(m in readonly_tools for m in mentioned):
        return False
    if mentioned:
        return True
    return False


def apply_tool_receipt_guard(
    answer_text: str,
    *,
    mcp_tool_calls: list[MCPToolCallSummary] | None,
) -> tuple[str, bool]:
    """答案层写类回执机检护栏主入口（纯函数，无副作用）。

    返回 (final_answer, tool_receipt_unverified)：
      - 答案提及写类完成语义 ∧ 无 success 凭据 → final_answer = 原文 + 追加诚实修正句，
        tool_receipt_unverified=True；
      - 否则 → final_answer = 原文（零变化），tool_receipt_unverified=False。
    修正句幂等：已含 TOOL_RECEIPT_NOTICE 的答案不重复追加（防多轮/重试叠句）。
    """
    text = answer_text or ""
    if not _mentions_write_semantics(text, mcp_tool_calls=mcp_tool_calls):
        return text, False
    if _has_real_write_receipt(mcp_tool_calls):
        return text, False
    if TOOL_RECEIPT_NOTICE in text:
        return text, True
    final = text.rstrip() + "\n\n" + TOOL_RECEIPT_NOTICE
    return final, True
