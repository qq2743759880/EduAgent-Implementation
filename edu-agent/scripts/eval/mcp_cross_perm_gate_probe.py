# -*- coding: utf-8 -*-
"""W-NEXT-MCP-003 ⑰「MCP 跨权限门对账」健康门探针（check-demo.mjs 调用）。

五段验收（对齐 kickoff ⑰）：
  ① audit_mcp_capability() → ok=true 且 checked>=17（MCP1/2 12 行 + W-NEXT-MCP-003 新增 5 行）
  ② 5 个新对账行均存在（permission_gate_admin_only_tools_exist /
     permission_gate_classify_tool_intent /
     tool_calling_can_use_tool_indirect_called /
     tool_calling_uses_build_denied_envelope /
     permission_gate_in_tool_calling_module）
  ③ tool_calling 路径真接 permission_gate 4 个 API（is_write_class / gate_tool_call /
     build_denied_envelope / resolve_role 任一调用到位）
  ④ audit 返回 JSON serializable（dict[str, list[str] | int | bool]，与 check-demo 探针契约兼容）
  ⑤ 全 AST 真接模式（call / indirect / chain）— 至少 4 个新行用真接模式（非纯 grep）

跑法（在 edu-agent/ 下，纯离线、零 IO）：
    .venv/Scripts/python.exe scripts/eval/mcp_cross_perm_gate_probe.py

输出：末尾打印一行 `[CROSSPERM] <json>`，供 check-demo.mjs 解析。
  json: {audit_ok, audit_checked, five_rows_present, chat_path_connected,
         json_serializable, ast_modes_count, detail}
退出码：0=全绿；1=真实失败（代码缺陷）。无 env_blocked：本门纯离线不依赖后端/DB。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]          # edu-agent/
sys.path.insert(0, str(_REPO))


def _emit(audit_ok, audit_checked, five_rows_present, chat_path_connected,
          json_serializable, ast_modes_count, detail):
    payload = {
        "audit_ok": audit_ok,
        "audit_checked": audit_checked,
        "five_rows_present": five_rows_present,
        "chat_path_connected": chat_path_connected,
        "json_serializable": json_serializable,
        "ast_modes_count": ast_modes_count,
        "detail": detail,
    }
    print(f"[CROSSPERM] {json.dumps(payload, ensure_ascii=False)}")


async def main() -> int:
    result = {
        "audit_ok": False, "audit_checked": 0,
        "five_rows_present": False, "chat_path_connected": False,
        "json_serializable": False, "ast_modes_count": 0,
        "detail": "",
    }

    # ① audit_mcp_capability() 离线对账 → ok=true 且 checked>=17
    try:
        from app.mcp.capability_audit import (
            _CAPABILITY_ROWS, _ast_build_denied_envelope_in_tool_calling_run,
            _ast_can_use_tool_in_tool_calling_run,
            _ast_classify_tool_intent_in_is_write_class,
            _ast_permission_gate_in_tool_calling_run, _read,
            audit_mcp_capability,
        )

        r = audit_mcp_capability()
        result["audit_checked"] = r["checked"]
        result["audit_ok"] = bool(r["ok"]) and r["checked"] >= 17
        if not result["audit_ok"]:
            result["detail"] = (
                f"审计未通过: checked={r['checked']} ok={r['ok']} "
                f"virtual={r['virtual']} broken={r['broken']} "
                f"cross_module_virtual={r['cross_module_virtual']}"
            )
    except Exception as e:  # noqa: BLE001
        result["detail"] = f"审计异常: {type(e).__name__}: {e}"
        _emit(**result)
        return 1

    # ② 5 个新对账行均存在
    try:
        ids = {r[0] for r in _CAPABILITY_ROWS}
        five_required = {
            "permission_gate_admin_only_tools_exist",
            "permission_gate_classify_tool_intent",
            "tool_calling_can_use_tool_indirect_called",
            "tool_calling_uses_build_denied_envelope",
            "permission_gate_in_tool_calling_module",
        }
        missing = five_required - ids
        result["five_rows_present"] = (not missing)
        if missing:
            result["detail"] = (
                (result["detail"] + " | " if result["detail"] else "")
                + f"5 个新对账行缺失: {sorted(missing)}"
            )
    except Exception as e:  # noqa: BLE001
        result["detail"] = (
            (result["detail"] + " | " if result["detail"] else "")
            + f"行存在性校验异常: {type(e).__name__}: {e}"
        )

    # ③ tool_calling 路径真接 permission_gate 4 个 API（is_write_class / gate_tool_call /
    #    build_denied_envelope / resolve_role 中任一调用到位） + AST 链全通
    try:
        caller_src = _read("app/chat/tool_calling.py")
        def_src = _read("app/ai/permission_gate.py")
        # 三段 AST 链：(a) is_write_class 调用 + is_write_class → classify_tool_intent
        #               (b) gate_tool_call 调用 + gate_tool_call → can_use_tool
        #               (c) build_denied_envelope 调用 + 返回 dict 含 code
        chain_a = _ast_classify_tool_intent_in_is_write_class(def_src)
        chain_b = _ast_can_use_tool_in_tool_calling_run(caller_src, def_src)
        chain_c = _ast_build_denied_envelope_in_tool_calling_run(caller_src, def_src)
        in_run = _ast_permission_gate_in_tool_calling_run(caller_src)
        result["chat_path_connected"] = chain_a and chain_b and chain_c and in_run
        if not result["chat_path_connected"]:
            result["detail"] = (
                (result["detail"] + " | " if result["detail"] else "")
                + f"chat 路径 AST 链不全：chain_a(is_write_class→classify_tool_intent)={chain_a}"
                f" chain_b(gate_tool_call→can_use_tool)={chain_b}"
                f" chain_c(build_denied_envelope ACI)={chain_c}"
                f" in_run(any pg symbol)={in_run}"
            )
    except Exception as e:  # noqa: BLE001
        result["detail"] = (
            (result["detail"] + " | " if result["detail"] else "")
            + f"chat 路径链校验异常: {type(e).__name__}: {e}"
        )

    # ④ audit 返回值 JSON serializable（与 check-demo 探针契约兼容）
    try:
        json.dumps(r, ensure_ascii=False)
        result["json_serializable"] = True
    except TypeError as e:
        result["detail"] = (
            (result["detail"] + " | " if result["detail"] else "")
            + f"audit 返回非 JSON serializable: {e}"
        )
        result["json_serializable"] = False

    # ⑤ 全 AST 真接模式：5 个新行至少 4 个用真接模式（非纯 grep）
    try:
        rows_by_id = {r[0]: r for r in _CAPABILITY_ROWS}
        new_ids = (
            "permission_gate_admin_only_tools_exist",
            "permission_gate_classify_tool_intent",
            "tool_calling_can_use_tool_indirect_called",
            "tool_calling_uses_build_denied_envelope",
            "permission_gate_in_tool_calling_module",
        )
        ast_modes = {"call", "can_use_tool_indirect",
                     "is_write_class_chain", "gate_tool_call_chain",
                     "build_denied_envelope_chain", "permission_gate_in_run"}
        non_grep_count = sum(
            1 for rid in new_ids
            if len(rows_by_id.get(rid, ())) >= 5
            and rows_by_id[rid][4] in ast_modes
        )
        result["ast_modes_count"] = non_grep_count
        if non_grep_count < 4:
            result["detail"] = (
                (result["detail"] + " | " if result["detail"] else "")
                + f"AST 真接模式不足: {non_grep_count}/5（要求 ≥4）"
            )
    except Exception as e:  # noqa: BLE001
        result["detail"] = (
            (result["detail"] + " | " if result["detail"] else "")
            + f"AST 模式统计异常: {type(e).__name__}: {e}"
        )

    _emit(**result)
    if result["detail"]:
        # 任何 detail 非空 → 失败
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))