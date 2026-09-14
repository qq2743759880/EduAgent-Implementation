# -*- coding: utf-8 -*-
"""taskR20b 打点 hook：进程内 monkeypatch 捕获六节点图的真实检索行为。

背景（audit P1-5）：run_agent 返回体 docs/graph_entities/tool_results 硬编码为空
（graph.py:825-828）→ 新路径的检索结果在 API 层不可见。本 hook 在探针进程内把
app.chat.retriever.retrieve_three_channel 替换为「原函数 + 捕获寄存器」的 spy，
直接观测新路径检索（docs chunk_ids / 计数 / 完成时刻 / 降级）。

零正产文件改动：只改本进程内存中的模块属性；revert = 不 import 本模块。

import 顺序契约（由调用方保证）：
  1) 先 import app.chat.flows.agent / app.chat.service（其模块级
     `from app.chat.retriever import retrieve_three_channel` 绑定【原函数】
     → 旧路径 run_agent_turn 行为不变、不被捕获）；
  2) 再 install()（只替换 retriever 模块对象属性）；
  3) graph 域（sixnode.fan_out / graph._build_tool_services）对
     retrieve_three_channel 均为函数体内延迟 import，每次调用重新解析模块属性
     → 自动命中 spy。
"""
from __future__ import annotations

import time
from typing import Any

CAPTURE: dict[str, Any] = {
    "calls": 0,                 # 本轮 retrieve_three_channel 触发次数
    "docs": [],                 # [{chunk_id, score, content_head}] 最终截断后 docs
    "raw_retrieved_count": 0,   # 融合后未截断计数
    "t_last": None,             # 最近一次检索完成时刻（perf_counter，TTFT 代理用）
    "degraded": None,           # 检索层降级说明
    "queries": [],              # 每次检索实际用的 query（含 HyDE 改写差异观测）
}

_ORIG: Any = None
_PATCHED = False


def install() -> None:
    """替换 app.chat.retriever.retrieve_three_channel 为捕获版。可重入。"""
    global _ORIG, _PATCHED
    if _PATCHED:
        return
    import app.chat.retriever as _ret

    _ORIG = _ret.retrieve_three_channel

    async def _spy(query, **kwargs):
        bundle = await _ORIG(query, **kwargs)
        CAPTURE["calls"] += 1
        CAPTURE["t_last"] = time.perf_counter()
        CAPTURE["queries"].append(str(query))
        CAPTURE["raw_retrieved_count"] = int(getattr(bundle, "raw_retrieved_count", 0) or 0)
        CAPTURE["degraded"] = getattr(bundle, "degraded_reason", None)
        docs = []
        for d in (getattr(bundle, "docs", None) or [])[:12]:
            docs.append({
                "chunk_id": getattr(d, "doc_id", None),
                "score": round(float(getattr(d, "score", 0.0) or 0.0), 6),
                "content_head": str(getattr(d, "content", "") or "")[:120],
            })
        CAPTURE["docs"] = docs
        return bundle

    _ret.retrieve_three_channel = _spy
    _PATCHED = True


def reset() -> None:
    """每样本双跑前清空捕获寄存器。"""
    CAPTURE["calls"] = 0
    CAPTURE["docs"] = []
    CAPTURE["raw_retrieved_count"] = 0
    CAPTURE["t_last"] = None
    CAPTURE["degraded"] = None
    CAPTURE["queries"] = []


def uninstall() -> None:
    """探针结束还原（进程退出即回收，防御性提供）。"""
    global _PATCHED
    if _PATCHED and _ORIG is not None:
        import app.chat.retriever as _ret

        _ret.retrieve_three_channel = _ORIG
        _PATCHED = False


def assert_isolation() -> dict:
    """断言 import 顺序契约成立：旧路径绑定原函数、模块属性为 spy。"""
    import app.chat.retriever as _ret
    import app.chat.flows.agent as _flows

    return {
        "module_attr_is_spy": _ret.retrieve_three_channel is not _ORIG,
        "flows_binding_is_orig": _flows.retrieve_three_channel is _ORIG,
    }
