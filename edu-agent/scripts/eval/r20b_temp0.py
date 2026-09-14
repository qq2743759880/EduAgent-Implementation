# -*- coding: utf-8 -*-
"""taskR20b · 确定性注入（commit ①，可整体 revert）。

kickoff v1.1 硬约束：「凡 LLM 参与（decide_agent_plan/图内路由）固定 temperature=0，
monkeypatch 级配置注入，不改正产代码，单独 commit 可 revert」。

现状（启动断言）：生产默认 LLM_TEMPERATURE=0.0、RULE_ROUTING_ENABLED=True
→ decide_agent_plan 与 graph.route 均走 0-LLM 规则路由（正则，零采样噪声）。
本模块做「防漂移」的兜底强制注入：
  1) 进程内把 settings.LLM_TEMPERATURE 钉死为 0.0；
  2) 包住唯一 LLM 收口 app.chat.generator._ChatClient.call_chat（call_chat_with_retry /
     call_chat_stream_with_retry 内部都委托它；HyDE 改写、route 兜底、answer、judge、子代理
     全部经此收口）——无论调用方传什么 temperature，一律覆写为 0.0。

纯内存 patch，只在本探针进程生效；不 import 本模块即完全不影响正产。revert = 不安装/删除本文件。
"""
from __future__ import annotations

from loguru import logger

_INSTALLED = False
_ORIG_CALL = None


def install() -> None:
    global _INSTALLED, _ORIG_CALL
    if _INSTALLED:
        return
    from app.config import settings
    from app.chat.generator import _ChatClient

    settings.LLM_TEMPERATURE = 0.0  # 防 .env/环境变量漂移引入采样噪声
    _ORIG_CALL = _ChatClient.call_chat

    def _forced_call_chat(self, *, messages, model, temperature, max_tokens, timeout=60.0):
        return _ORIG_CALL(self, messages=messages, model=model, temperature=0.0,
                          max_tokens=max_tokens, timeout=timeout)

    _ChatClient.call_chat = _forced_call_chat
    _INSTALLED = True
    logger.info("[r20b-temp0] 确定性注入已安装：settings.LLM_TEMPERATURE=0.0，call_chat 收口强制 temperature=0.0")


def status() -> dict:
    return {"installed": _INSTALLED}
