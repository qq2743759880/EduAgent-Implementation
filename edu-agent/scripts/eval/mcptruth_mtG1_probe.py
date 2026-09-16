# -*- coding: utf-8 -*-
"""MCP-TRUTH MT-G1 实测：search_knowledge 真实三通道检索（非「未接入」空壳）。

独立进程运行，镜像 8010 的启动接线：调 init_mcp_capabilities()（唯一生产注入点）→
_search_knowledge_handler({"q": ...}) → 走真实 retrieve_three_channel（Milvus+Neo4j+重排）。
"""
import asyncio
import json

from app.database import init_mysql, init_milvus
from app.mcp import executor


async def main():
    await init_mysql()
    init_milvus()

    # 镜像 8010 生产接线
    await executor.init_mcp_capabilities()
    print("BACKEND_INJECTED=", executor._SEARCH_KNOWLEDGE_BACKEND is not None)

    out = await executor._search_knowledge_handler({"q": "线性代数 矩阵 特征值"})
    body = json.loads(out)
    print("DEGRADED=", body.get("degraded"))
    print("NOTE=", body.get("note"))
    print("RETRIEVED_COUNT=", body.get("retrieved_count"))
    print("RESULTS_LEN=", len(body.get("results") or []))
    print("DEGRADED_REASON=", body.get("degraded_reason"))
    assert "未接入" not in str(body.get("note", "")), "search_knowledge 仍是空壳（未接入）"
    assert body.get("degraded") is False or body.get("degraded_reason"), \
        "应走真实检索（degraded=False 或带真实 reason），而非空壳占位"
    print("MT_G1_PASS")


asyncio.run(main())