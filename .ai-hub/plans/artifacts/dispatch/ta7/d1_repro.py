# -*- coding: utf-8 -*-
"""TA7 D1 复现：内置工具业务失败被记成 SUCCESS → 护栏零触发。

真实 HTTP 调 POST /api/chat/stream，问"把《…完全不存在版》加入收藏"，
对照：① SSE done.data.mcp_tool_calls[].status ② mcp_tool_call_log.status + result_json
     ③ tool_receipt_unverified 是否 true。
"""
from __future__ import annotations

import sys
import time

import _ta7_lib as L

STUDENT = sys.argv[1] if len(sys.argv) > 1 else "user000002"
QUERY = sys.argv[2] if len(sys.argv) > 2 else "帮我把《量子物理导论第七版完全不存在版》加入收藏"


def main() -> None:
    print("=" * 70)
    print(f"[D1] account={STUDENT}  query={QUERY}")
    print("=" * 70)
    token = L.login(STUDENT)
    t0 = time.time()
    events, answer, done, _raw = L.chat_stream(QUERY, token)
    print(f"[HTTP] {time.time()-t0:.1f}s  events={len(events)}")
    with open("_d1_done_raw.json", "w", encoding="utf-8") as f:
        L.json.dump(done, f, ensure_ascii=False, indent=2)
    print("\n--- 答案文本 ---")
    print(answer or "(空)")
    inner = done.get("data") if isinstance(done.get("data"), dict) else done
    print("\n--- SSE mcp_tool_calls ---")
    for c in (inner.get("mcp_tool_calls") or []):
        print("  ", {k: c.get(k) for k in ("tool_name", "status", "latency_ms")})
        print("      result_summary:", str(c.get("result_summary"))[:300])
    print("\n--- done.data 关键字段 ---")
    print("  tool_receipt_unverified =", inner.get("tool_receipt_unverified"))
    print("  memorized =", inner.get("memorized"))
    print("  keys(outer) =", sorted(done.keys()), " keys(inner) =", sorted(inner.keys()))

    rows = L.q(
        "SELECT id, call_id, tool_name, status, LEFT(result_json,400) AS result_json,"
        " LEFT(error_message,200) AS error_message, created_at"
        " FROM mcp_tool_call_log WHERE tool_name='favorite_add'"
        " ORDER BY id DESC LIMIT 6"
    )
    print("\n--- mcp_tool_call_log 最近 favorite_add 行 ---")
    for r in rows:
        print("  ", L.jj(r))


if __name__ == "__main__":
    main()
