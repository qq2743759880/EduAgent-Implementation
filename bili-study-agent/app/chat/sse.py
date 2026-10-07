# -*- coding: utf-8 -*-
"""SSE 共享原语（R02 抽取）：事件序列化 + 建连后异常→可区分错误码映射。

R02 流式主路径进 LangGraph 后，SSE 帧的产生方有两个：
  - 旧路径：app/chat/router.py（chat_stream_sse._gen）
  - 新路径：app/chat/flows/graph_stream.py（graph.astream 适配层）
两者必须逐字段同构（SSE 契约冻结 contracts/reshape-a.json：start/retrieval/token/done/error，
token 帧 data={"delta": ...}，done 帧 data 内嵌 {code:0,message:"ok",data} 壳）。
为避免两处实现漂移（audit P2-23 同类风险），序列化与错误映射收敛到本模块单一实现：
  - _sse_line：SSE 帧字节序列化（event: X\\ndata: {...}\\n\\n）
  - _map_stream_exception：建连后异常 → (可区分错误码, 可读 message)
router.py 保留同名 re-export（历史测试 chat_router._map_stream_exception 契约不变）。
"""
from __future__ import annotations

import json
import re

from app.common.error_codes import (
    LLM_AUTH,
    LLM_RATE_LIMIT,
    LLM_TIMEOUT,
    LLM_UNAVAILABLE,
    SERVICE_DOWNSTREAM,
)


def sse_line(event: str, data: dict) -> bytes:
    """SSE 帧序列化（契约冻结：event 行 + data 行 + 空行；ensure_ascii=False 保中文原样）。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


def map_stream_exception(e: Exception) -> tuple[str, str]:
    """把 SSE 连接建立后的生成/落库期异常映射为「可区分错误码 + 可读 message」。

    两段式错误模型契约（批判 C3.1 承认的取舍）：
      - 连接前：service 层抛错 → 同步 HTTP 4xx/5xx（router 顶部 try/except）。
      - 建连后：token 迭代 / finalize 落库失败 → 流内 `event: error`，code 用本函数映射。
    本函数只据「异常类型 + 消息特征」映射，不回传 traceback；
    目标是让前端 error 分支从固定 50000 单调 → 可区分（LLM_AUTH / LLM_TIMEOUT /
    LLM_RATE_LIMIT / LLM_UNAVAILABLE / SERVICE_DOWNSTREAM）。
    （原 router._map_stream_exception 逻辑原样迁移，行为逐字节一致。）
    """
    lowered = f"{type(e).__name__} {e}".lower()

    def _has(*words: str) -> bool:
        return any(w in lowered for w in words)

    # 1) 超时：内置 TimeoutError（py3.11 与 asyncio.TimeoutError 同对象）+ 特征词
    if isinstance(e, TimeoutError) or _has("timeout", "timed out", "60s 无增量"):
        return LLM_TIMEOUT, f"答案生成超时：{type(e).__name__}"

    # 2) LLM HTTP 状态码特征（LLM 客户端抛的 RuntimeError "LLM stream HTTP <code>: ..."）
    _st = re.search(r"http\D{0,4}(\d{3})", lowered)
    status_code = int(_st.group(1)) if _st else None
    if status_code is not None:
        if status_code in (401, 403):
            return LLM_AUTH, f"LLM 下游鉴权/密钥失效(HTTP {status_code})：{type(e).__name__}"
        if status_code == 429:
            return LLM_RATE_LIMIT, f"LLM 下游限流(HTTP 429)：{type(e).__name__}"
        if status_code >= 500:
            return LLM_UNAVAILABLE, f"LLM 下游服务不可用(HTTP {status_code})：{type(e).__name__}"

    # 3) 语义/类型特征（openai 风格异常 / 连接失败）
    if _has("authenticationerror", "unauthorized", "invalid api key", "invalidapikey", "api key invalid"):
        return LLM_AUTH, f"LLM 下游鉴权/密钥失效：{type(e).__name__}"
    if _has("ratelimiterror", "rate limit", "too many requests", "not enough quota", "quota"):
        return LLM_RATE_LIMIT, f"LLM 下游限流/额度不足：{type(e).__name__}"
    if _has("connectionerror", "connection error", "connectionrefused", "failed to connect",
            "apiconnectionerror", "connection aborted", "connect timed out"):
        return LLM_UNAVAILABLE, f"LLM 下游连接失败：{type(e).__name__}"

    # 4) 其它未归类 → 通用下游兜底（保持区别于 50000，便于前端识别"生成期下游失败"）
    return SERVICE_DOWNSTREAM, f"答案生成失败（下游依赖）：{type(e).__name__}"
