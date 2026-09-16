# -*- coding: utf-8 -*-
"""MCP 能力对账门（MCP-TRUTH 步骤4，对齐 R15-b audit_registry 思想，防「能力虚标」复发）。

对账「声称的 MCP 能力清单」vs「生产接线实况」：
  - **虚标（virtual）**：声称有能力，但生产调用方文件对宣称的入口符号零引用 → 必须为空；
  - **断裂（broken）**：生产调用方引用了宣称的入口符号，但定义它的模块文件不存在 → 必须为空。

与「R15-b 只对账名字存在性」不同，本门对账的是**声称能力 = 生产真实接线**，杜绝
「grep 仅定义文件自身引用/空壳注入点零调用」这类能力虚标（audit-rag #3/#5/#6）。

用法（独立命令，零 DB/网络依赖，只读源码）：
    cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_contract_mcptruth.py -q
    # 或直接跑：
    .venv/Scripts/python.exe -c "from app.mcp.capability_audit import audit_mcp_capability;
                                 print(audit_mcp_capability())"
"""
from __future__ import annotations

from pathlib import Path

# edu-agent/ 项目根（app/mcp/capability_audit.py → 上溯三级）
_BASE = Path(__file__).resolve().parent.parent.parent


# ============================================================
# 声称能力清单 → 生产接线实况（数据驱动）
# ------------------------------------------------------------
# 每行：(能力ID, caller_script 期望引用的入口符号, 生产调用方脚本(相对 edu-agent/), 定义该符号的文件)
#   virtual = caller_script 未引用入口符号（声称有能力但零接线）
#   broken  = caller_script 引用了入口符号但定义文件不存在（引用断裂）
# ============================================================
_CAPABILITY_ROWS: list[tuple[str, str, str, str]] = [
    # #5 auth：executor 远程（sse/http）传输经 _remote_auth_headers → build_auth_headers 注入认证头
    ("auth_remote_auth_injection", "build_auth_headers", "app/mcp/executor.py", "app/mcp/auth.py"),
    # #5 reconnect：executor stdio 健康检查经 with_reconnect 自动指数退避重连
    ("reconnect_stdio_autoreconnect", "with_reconnect", "app/mcp/executor.py", "app/mcp/reconnect.py"),
    # #5 isolation：executor 工具结果超限经 truncate_tool_result 截断
    ("isolation_result_truncation", "truncate_tool_result", "app/mcp/executor.py", "app/mcp/isolation.py"),
    # #5 dynamic_update：executor discover 经 notify_tools_changed 同步动态工具注册表
    ("dynamic_update_discover_sync", "notify_tools_changed", "app/mcp/executor.py", "app/mcp/dynamic_update.py"),
    # #6 search_knowledge 空壳：应用启动（main.lifespan）调用 init_mcp_capabilities 注入真实后端
    ("search_knowledge_real_backend", "init_mcp_capabilities", "app/main.py", "app/mcp/executor.py"),
    # #6 注入点本身要有生产调用方：executor.init_mcp_capabilities 内 set_search_knowledge_backend(...)
    ("search_knowledge_backend_injection", "set_search_knowledge_backend", "app/mcp/executor.py", "app/mcp/executor.py"),
    # #3 按名解析：executor 默认执行器经 get_tool_by_ref(None,None,tool_name) 按名直达 DB 工具
    ("registry_name_resolution", "get_tool_by_ref", "app/mcp/executor.py", "app/mcp/registry.py"),
]


def _read(rel_path: str) -> str:
    """读取相对 edu-agent/ 的源码文本；不存在返回空串（供断裂判别）。"""
    p = (_BASE / rel_path).resolve()
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def audit_mcp_capability(*, rows=None) -> dict:
    """对账声称能力 vs 生产接线实况。

    返回 {"virtual": [...], "broken": [], "checked": n, "ok": bool}：
      - virtual  非空 = 能力虚标（声称了但生产零接线）→ 必须为空才算通过；
      - broken   非空 = 引用断裂（生产调用了不存在的模块/符号）→ 必须为空才算通过。
    """
    rows = rows if rows is not None else _CAPABILITY_ROWS
    virtual: list[str] = []
    broken: list[str] = []
    for cap_id, symbol, caller, def_file in rows:
        caller_src = _read(caller)
        def_src = _read(def_file)
        caller_refs = caller_src.count(symbol) > 0
        def_exists = bool(def_src)
        if caller_refs and not def_exists:
            broken.append(f"{cap_id}: caller={caller} 引用 {symbol} 但定义文件 {def_file} 不存在")
        elif not caller_refs:
            virtual.append(f"{cap_id}: 声称有能力但生产调用方 {caller} 零引用 {symbol}（虚标）")
    return {
        "virtual": virtual,
        "broken": broken,
        "checked": len(rows),
        "ok": (not virtual) and (not broken),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(audit_mcp_capability(), ensure_ascii=False, indent=2))