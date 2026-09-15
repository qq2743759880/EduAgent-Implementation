# -*- coding: utf-8 -*-
"""R12 验收探针：8011 临时实例（TOOL_DECISION_MODE=llm）真实 HTTP + SSE 实测。

步骤：登录 student → 流式 chat 两条（工具意图/非工具）→ 解析 retrieval 帧
mcp_tool_calls → 打印 call_id 供 call_log 核对。只读，无 DB 直写。
"""
import json
import sys

import requests

BASE = "http://127.0.0.1:8011"
S = requests.Session()
S.trust_env = False


def login() -> str:
    r = S.post(f"{BASE}/api/auth/login", json={"account": "user000001", "password": "Test@123456"}, timeout=15)
    r.raise_for_status()
    body = r.json()
    data = body.get("data") or {}
    token = data.get("access_token") or data.get("token")
    assert token, f"登录无 token: {body}"
    return token


def stream_chat(token: str, query: str) -> dict:
    """跑一条流式问答，解析 SSE 帧返回摘要。"""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    events: list[tuple[str, dict]] = []
    with S.post(f"{BASE}/api/chat/stream", json={"query": query, "stream": True},
                headers=headers, timeout=120, stream=True) as resp:
        assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:200]}"
        cur_event, data_buf = None, []
        for raw in resp.iter_lines(decode_unicode=True):
            if raw is None:
                continue
            line = raw.strip()
            if line.startswith("event:"):
                cur_event = line.split(":", 1)[1].strip()
                data_buf = []
            elif line.startswith("data:"):
                data_buf.append(line.split(":", 1)[1].strip())
                if cur_event:
                    try:
                        events.append((cur_event, json.loads(data_buf[-1])))
                    except Exception:
                        events.append((cur_event, {"_raw": data_buf[-1]}))
                    cur_event = None

    out: dict = {"query": query, "mcp_calls": [], "tokens": 0, "done": None, "retrieval_degraded": None}
    answer_chars = 0
    for ev, data in events:
        if ev == "retrieval":
            out["mcp_calls"] = data.get("mcp_tool_calls") or []
            out["retrieval_degraded"] = data.get("degraded_reason")
        elif ev == "token":
            out["tokens"] += 1
            answer_chars += len(str(data.get("delta") or ""))
        elif ev == "done":
            out["done"] = data
        elif ev == "error":
            out["error"] = data
    out["answer_chars"] = answer_chars
    return out


def main() -> int:
    token = login()
    print("[1] login ok (student user000001)")

    # ① 工具意图 query（llm 决策应选 add 并真执行）——query 可由 argv 覆盖（超时降级实验用）
    q1 = sys.argv[1] if len(sys.argv) > 1 else "请用工具计算 88 加 14 的和"
    r1 = stream_chat(token, q1)
    print(f"[2] tool-intent query -> mcp_calls={json.dumps(r1['mcp_calls'], ensure_ascii=False)}")
    print(f"    tokens={r1['tokens']} answer_chars={r1['answer_chars']} done_code={(r1['done'] or {}).get('code')}")
    ok1 = bool(r1["mcp_calls"]) and r1["mcp_calls"][0].get("status") == "success" \
        and r1["mcp_calls"][0].get("tool_name") == "add"
    print(f"    -> llm 决策+真执行 {'PASS' if ok1 else 'FAIL'} (call_id={r1['mcp_calls'][0].get('call_id') if r1['mcp_calls'] else None})")

    # ② 非工具 query（llm 判空 → 零工具调用）
    r2 = stream_chat(token, "什么是勾股定理？简单说明即可")
    print(f"[3] non-tool query -> mcp_calls={r2['mcp_calls']} tokens={r2['tokens']} "
          f"done_code={(r2['done'] or {}).get('code')}")
    ok2 = r2["mcp_calls"] == [] and r2["tokens"] > 0
    print(f"    -> 不误触发 {'PASS' if ok2 else 'FAIL'}")

    print(f"[4] call_ids for call_log check: {[c.get('call_id') for c in r1['mcp_calls']]}")
    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    sys.exit(main())
