"""
task26 artifact 服务 + 工具输出蒸馏分流（R4 tool result clearing / GWT②）。

对齐 Anthropic《Multi-agent Research System》附录「Subagent output to filesystem」：
- 单条 MCP/工具输出 > COMPACTION_TOOL_OUTPUT_THRESHOLD(1500) token → 立即蒸馏：
  原始 JSON 进 artifact（TTL 1h），流内仅 1 行结论（tool result clearing）。
- artifact 存储：优先 Redis（TTL 1h），Redis 不可用降级内存（服务不因存储故障而 500）。

本模块不依赖 subagents.runner（避免循环导入）；runner 用其做流内精简，runner 自身 artifact 仍保留完整输出。
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from loguru import logger

from app.ai.compaction import estimate_tokens
from app.config import settings

_ARTIFACT_TTL = 3600


class ArtifactShuntStore:
    """artifact 轻量存储：Redis TTL 1h，Redis 不可用降级内存。"""

    def __init__(self) -> None:
        self._mem: dict[str, str] = {}

    async def write(self, payload: Any, ttl: int = _ARTIFACT_TTL) -> str:
        ref = f"artifact:{uuid.uuid4().hex}"
        blob = json.dumps(payload, ensure_ascii=False, default=str)
        try:
            from app.database import get_redis
            r = get_redis()
            await r.set(ref, blob, ex=ttl)
            return ref
        except Exception:
            self._mem[ref] = blob
            return ref

    async def read(self, ref: str) -> Any:
        try:
            from app.database import get_redis
            r = get_redis()
            raw = await r.get(ref)
            if raw is not None:
                return json.loads(raw)
        except Exception:
            pass
        if ref in self._mem:
            return json.loads(self._mem[ref])
        return None


_default_shunt_store = ArtifactShuntStore()


# ============================================================
# 蒸馏判定与一行结论（规则化、离线可测；无需 LLM 调用）
# ============================================================
def _serialize(result: Any) -> str:
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        return str(result)


def is_large_tool_output(result: Any, threshold: int | None = None) -> bool:
    """单条工具输出是否超阈值（> threshold token）。"""
    threshold = int(threshold if threshold is not None else settings.COMPACTION_TOOL_OUTPUT_THRESHOLD)
    blob = _serialize(result) if not isinstance(result, str) else result
    return estimate_tokens(blob) > threshold


def one_line_conclusion(tool_name: str, result: Any, line_limit: int = 120) -> str:
    """把任意工具结果精简为一行结论（含 token 量提示，原文应已入 artifact）。"""
    blob = _serialize(result)
    tokens = estimate_tokens(blob)
    one_line = blob.replace("\r", " ").replace("\n", " ").strip()
    if len(one_line) > line_limit:
        # 优先从可读字段抽一行，避免整段 JSON 涌入主上下文
        snippet = _readable_snippet(result, line_limit)
        one_line = snippet
    return f"[{tool_name}] {one_line}…（原 {tokens} token 已入 artifact）"


def _readable_snippet(result: Any, limit: int) -> str:
    if isinstance(result, str):
        return result[:limit]
    if isinstance(result, dict):
        # 常见结论字段优先
        for key in ("conclusion", "summary", "result", "answer", "text", "content", "message"):
            v = result.get(key)
            if v:
                s = _serialize(v).replace("\r", " ").replace("\n", " ").strip()
                if s:
                    return s[:limit]
        # 取首个非空值
        for v in result.values():
            if v:
                s = _serialize(v).replace("\r", " ").replace("\n", " ").strip()
                if s:
                    return s[:limit]
    return _serialize(result)[:limit]


# ============================================================
# 蒸馏主入口：写 artifact + 返回流内结论
# ============================================================
async def distill_tool_output(
    tool_name: str,
    result: Any,
    threshold: int | None = None,
    ttl: int = _ARTIFACT_TTL,
    store: ArtifactShuntStore | None = None,
) -> dict:
    """对单条工具输出分流：超阈值 → 原文进 artifact，返回 1 行结论；否则原样返回。

    Returns:
        dict {tool_name, distilled(bool), conclusion(str), artifact_ref(str|None),
              tokens(int), result(Any)}
    """
    st = store or _default_shunt_store
    blob = _serialize(result) if not isinstance(result, str) else result
    tokens = estimate_tokens(blob)
    if not is_large_tool_output(blob, threshold):
        return {"tool_name": tool_name, "distilled": False, "conclusion": blob,
                "artifact_ref": None, "tokens": tokens, "result": result}
    try:
        artifact_ref = await st.write({"tool_name": tool_name, "input_tokens": tokens, "raw": result}, ttl)
    except Exception as exc:
        logger.warning(f"[artifact] artifact 写入失败，流内返回截断: {type(exc).__name__}: {exc}")
        artifact_ref = None
    conclusion = one_line_conclusion(tool_name, result)
    return {"tool_name": tool_name, "distilled": True, "conclusion": conclusion,
            "artifact_ref": artifact_ref, "tokens": tokens, "result": result}


async def shunt_tool_outputs(
    calls: list[dict],
    threshold: int | None = None,
    ttl: int = _ARTIFACT_TTL,
    store: ArtifactShuntStore | None = None,
) -> dict:
    """对一批 [{'tool_name', 'result'}] 分流：大输出进 artifact，返回流内 1 行结论列表 + 入库数。"""
    flow: list[dict] = []
    artifacts = 0
    for call in calls:
        name = str(call.get("tool_name") or call.get("name") or "tool")
        result = call.get("result", call.get("output"))
        d = await distill_tool_output(name, result, threshold=threshold, ttl=ttl, store=store)
        if d["distilled"]:
            artifacts += 1
        flow.append({
            "tool_name": name,
            "distilled": d["distilled"],
            "conclusion": d["conclusion"],
            "artifact_ref": d.get("artifact_ref"),
        })
    return {"flow": flow, "distilled_count": artifacts}


def artifact_shunt_store() -> ArtifactShuntStore:
    """暴露存储（供验收 inspect 原文）。"""
    return _default_shunt_store