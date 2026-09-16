# -*- coding: utf-8 -*-
"""MCP-TRUTH MT-G2b 实测：registry.get_tool_by_ref 按名（仅 tool_name）唯一命中解析。"""
import asyncio

from app.common.exceptions import AppException
from app.database import init_mysql
from app.mcp import registry


async def main():
    await init_mysql()
    rows = await registry.list_tools(page_size=50)
    names = [(t.tool_name, t.server_id) for t in rows.items]
    print("DB_TOOLS=", names)
    assert names, "DB 无 mcp_tool 行，无法实测按名解析"
    # 取第一个工具，只按 tool_name 解析
    target_name = names[0][0]
    try:
        row = await registry.get_tool_by_ref(None, None, target_name)
        print(f"BY_NAME_OK tool_name={target_name} -> server_id={row['server_id']} server_code={row['server_code']}")
    except AppException as e:
        print(f"BY_NAME_ERR tool_name={target_name} message={e.message}")
        raise


asyncio.run(main())