# -*- coding: utf-8 -*-
"""
task29 评估用 LLM 客户端：扩展 _ChatClient 以捕获 usage（prompt_cache_*）与流式首包 TTFT。

复用 app.chat.generator._ChatClient 的 Session（trust_env=False 防本地代理劫持），
新增：
  - call()      ：非流式，返回 {text, usage, latency_ms}
  - call_stream()：流式，返回 {text, usage, ttft_ms, latency_ms}

不伪造数据：usage 直接取自 provider 返回值；TTFT 用真实计时的首个 token。
"""
from __future__ import annotations

import time

from app.chat.generator import _ChatClient
from app.config import settings


def _model_name(model: str) -> str:
    return settings.LLM_MODEL_STRONG if model == "strong" else settings.LLM_MODEL_FAST


def _headers():
    return {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }


def call(*, messages: list[dict], model: str, temperature: float = 0.0,
         max_tokens: int = 500, timeout: float = 60.0) -> dict:
    """非流式。返回 {text, usage, latency_ms}。"""
    client = _ChatClient.get()
    body = {
        "model": _model_name(model),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    t0 = time.perf_counter()
    resp = client._session.post(
        f"{settings.LLM_BASE_URL}/chat/completions",
        headers=_headers(),
        json=body,
        timeout=timeout,
    )
    latency_ms = (time.perf_counter() - t0) * 1000
    if resp.status_code != 200:
        raise RuntimeError(f"LLM HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    return {"text": text, "usage": usage, "latency_ms": latency_ms}


def call_stream(*, messages: list[dict], model: str, temperature: float = 0.0,
                max_tokens: int = 500, timeout: float = 120.0) -> dict:
    """流式。返回 {text, usage, ttft_ms, latency_ms}。ttft=到首个内容 token 的真实耗时。"""
    client = _ChatClient.get()
    body = {
        "model": _model_name(model),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    t0 = time.perf_counter()
    ttft_ms: float | None = None
    chunks: list[str] = []
    usage: dict = {}
    with client._session.post(
        f"{settings.LLM_BASE_URL}/chat/completions",
        headers=_headers(),
        json=body,
        timeout=timeout,
        stream=True,
    ) as resp:
        if resp.status_code != 200:
            raise RuntimeError(f"LLM stream HTTP {resp.status_code}: {resp.text[:300]}")
        resp.encoding = "utf-8"
        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            if raw_line.startswith("data:"):
                raw_line = raw_line[5:].lstrip()
            if raw_line == "[DONE]":
                continue
            import json as _json
            try:
                obj = _json.loads(raw_line)
            except Exception:
                continue
            # 流结束包可能带 usage
            if obj.get("usage"):
                usage = obj.get("usage") or usage
            choices = obj.get("choices") or []
            if not choices:
                continue
            delta = (choices[0].get("delta") or {}).get("content")
            if delta:
                if ttft_ms is None:
                    ttft_ms = (time.perf_counter() - t0) * 1000  # 首包
                chunks.append(delta)
    latency_ms = (time.perf_counter() - t0) * 1000
    if ttft_ms is None:
        ttft_ms = latency_ms  # 无内容（异常/空）
    return {"text": "".join(chunks), "usage": usage, "ttft_ms": ttft_ms, "latency_ms": latency_ms}


def cache_stats_from_usage(usage: dict) -> dict:
    """从 provider usage 提取 prompt caching 计量（DeepSeek 字段）。"""
    hit = int(usage.get("prompt_cache_hit_tokens") or 0)
    miss = int(usage.get("prompt_cache_miss_tokens") or 0)
    return {"cache_hit_tokens": hit, "cache_miss_tokens": miss,
            "hit_rate": round(hit / (hit + miss), 4) if (hit + miss) > 0 else 0.0}