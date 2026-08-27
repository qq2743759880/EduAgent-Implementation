"""记忆容量治理压缩器（task-M1：对齐 VikingMem TIME_COMPRESS）。

策略（近期高保真 + 旧事件懒合成摘要）：
- 有效记忆数 ≤ 容量上限 → 不压缩（近期记忆全程高保真）。
- 超容量 → 按综合分升序取「最低价值」的记忆分批合并为 consolidate 摘要事件，
  源 HEAD 盖章废弃，`supports` 引用被合并的**原事件 id**，history 仍可回溯。
- 压缩后该用户有效事件数收敛到容量上限（无阻塞、不丢历史）。

`summarizer` 可注入（生产接 LLM 升维；契约测试用确定性规则摘要，零外部依赖）。
"""
from __future__ import annotations

import math
from typing import Any, Callable

from loguru import logger


def _rule_summarize(contents: list[str]) -> str:
    """确定性规则摘要（无 LLM）：合并为结构化一条，保留原文要点。"""
    joined = "；".join((c or "").strip() for c in contents if (c or "").strip())
    return f"[合并 {len(contents)} 条记忆] {joined}"


async def compact_user(
    store: Any,
    user_id: int,
    *,
    summarizer: Callable[[list[str]], str] | None = None,
    batch_size: int = 5,
    capacity: int | None = None,
) -> dict[str, Any]:
    """对单用户执行容量压缩，返回压缩统计。

    Returns:
        {"compacted":int, "batches":int, "remaining":int, "kept":int, "consolidated_ids":list[int]}
    """
    summarizer = summarizer or _rule_summarize
    cap = int(capacity if capacity is not None else getattr(store, "_capacity", 500))
    effective = await store._persistence.list_effective(int(user_id))
    count = len(effective)
    if count <= cap:
        return {"compacted": 0, "batches": 0, "remaining": count, "kept": count, "consolidated_ids": []}

    B = max(2, int(batch_size))
    over = count - cap
    # 需要压缩出的批次数 b，使 (保留 K 条) + b ≤ cap
    b = max(1, math.ceil(over / (B - 1)))
    K = max(0, cap - b)
    ordered = sorted(effective, key=lambda m: (float(m.score), int(m.id)))
    keep = ordered[-K:] if K > 0 else []
    to_compress = ordered[:-K] if K > 0 else ordered

    batches = [to_compress[i:i + B] for i in range(0, len(to_compress), B)]
    consolidated_ids: list[int] = []
    for batch in batches:
        contents = [m.content for m in batch]
        summary = summarizer(contents)
        src_ids = [int(m.id) for m in batch]
        new_eid = await store.consolidate(
            source_entity_ids=src_ids,
            summary_content=summary,
            memory_type="profile",
            topic="general",
            importance=4,
            operator="compactor",
        )
        consolidated_ids.append(int(new_eid))

    remaining = await store._persistence.count_effective(int(user_id))
    logger.info(
        f"[Memory:compact] user={user_id} 压缩 {len(to_compress)} 条 → {len(batches)} 摘要，"
        f"有效数 {count} → {remaining}（上限 {cap}）"
    )
    return {
        "compacted": len(to_compress),
        "batches": len(batches),
        "remaining": remaining,
        "kept": len(keep),
        "consolidated_ids": consolidated_ids,
    }
