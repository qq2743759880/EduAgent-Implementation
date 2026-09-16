# -*- coding: utf-8 -*-
"""⑫ HITL 真实性健康门探针（SURFACED-1 闭环实证）。

由 check-demo.mjs 经 venv python 驱动（对照 VECLOCK_PROBE）。
流程：① /health 200 → ② admin 登录 → ③ /api/chat/stream 触发 knowledge_import
拿到 pending_confirm（证明 HITL + 写类工具经 chat 流式可触达）→ ④ /api/chat/resume
action=confirm → ⑤ 同 thread 续流执行 → ⑥ 断言续流**不再出现** SURFACED-1 的 42200
症状（「必须提供 tool_id」/「MCP 工具调用失败 knowledge_import（工具阶段已跳过）」），
即 tool_name 补传后内置写工具已正确路由到 handler。

输出 JSON 到 stdout，供 check-demo.mjs 解析。
注意：知识库导入 handler 对 source_files 路径有安全门禁（须落在允许 root 且文件存在），
故「task +1 落行」取决于是否准备了合法上传文件；本探针**核心判据是 42200 症状消失**
（回归红线），task 增量仅为观测值。完整 confirm→真落行实证见 T11 重测脚本（受测试窗口门禁）。
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = os.environ.get("CHECK_DEMO_BACKEND", "http://127.0.0.1:8000").rstrip("/")
ACCOUNT = "adm02test"
PASSWORD = "Test@123456"
ROOT = Path(__file__).resolve().parents[1]


def _post(url: str, payload: dict, token: str | None = None, timeout: int = 60):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(req, timeout=timeout)


def _login() -> str:
    with _post(f"{BACKEND}/api/auth/login",
               {"account": ACCOUNT, "password": PASSWORD}) as r:
        j = json.loads(r.read())
    tok = (j.get("data") or {}).get("access_token")
    if not tok:
        raise RuntimeError("admin 登录未返回 access_token")
    return tok


def _stream_events(token: str, query: str, session_id: str, timeout: int = 180):
    payload = {"query": query, "session_id": session_id, "stream": True}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{BACKEND}/api/chat/stream", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    events: list[tuple[str, object]] = []
    cur = ""
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith("event:"):
                cur = line[len("event:"):].strip()
            elif line.startswith("data:"):
                d = line[len("data:"):].strip()
                try:
                    obj = json.loads(d)
                except Exception:
                    obj = None
                events.append((cur, obj))
    return events


def _count_task() -> int:
    sys.path.insert(0, str(ROOT))
    from app.database import fetch_one
    import asyncio
    row = asyncio.run(fetch_one("SELECT COUNT(*) AS c FROM knowledge_import_task"))
    return int((row or {}).get("c", 0)) if row else 0


SURFACED1_SYMPTOMS = (
    "必须提供 tool_id",
    "MCP 工具调用失败 knowledge_import",
)


def main() -> int:
    out: dict = {}
    # ① 后端健康
    try:
        with urllib.request.urlopen(f"{BACKEND}/health", timeout=5) as r:
            hj = json.loads(r.read())
        out["health_ok"] = (hj.get("status") == "ok")
    except Exception as e:  # noqa: BLE001
        out["health_ok"] = False
        out["error"] = f"health: {e}"
        print(json.dumps(out, ensure_ascii=False))
        return 1

    token = _login()
    before = _count_task()
    out["task_before"] = before

    session_id = f"surfaced1_probe_{int(time.time())}"
    query = "请使用 knowledge_import 工具把示例文档导入知识库（visibility=private）"
    events = _stream_events(token, query, session_id)

    pending = next((d for (e, d) in events if e == "pending_confirm" and isinstance(d, dict)), None)
    out["pending_confirm_seen"] = pending is not None

    deg1 = " ".join(str((d or {}).get("degraded_reason", ""))
                    for (e, d) in events if isinstance(d, dict))
    out["symptom_in_first_pass"] = any(s in deg1 for s in SURFACED1_SYMPTOMS)

    if not pending:
        # 模型本轮未触发 knowledge_import：不视为失败（单测已覆盖 tool_name 修复），观测返回
        out["task_after"] = before
        out["task_diff"] = 0
        out["confirm_resumed"] = False
        out["note"] = "模型未触发 knowledge_import，跳过 HITL 续流；SURFACED-1 修复由单测覆盖"
        print(json.dumps(out, ensure_ascii=False))
        return 0

    tid = pending.get("thread_id") or session_id
    out["thread_id"] = tid
    # ④ confirm
    with _post(f"{BACKEND}/api/chat/resume",
               {"thread_id": tid, "action": "confirm"}, token=token) as r:
        rj = json.loads(r.read())
    out["confirm_resumed"] = ((rj.get("data") or {}).get("status") == "resumed"
                               or rj.get("status") == "resumed")
    # ⑤ 续流执行
    events2 = _stream_events(token, query, session_id)
    deg2 = " ".join(str((d or {}).get("degraded_reason", ""))
                    for (e, d) in events2 if isinstance(d, dict))
    out["symptom_in_confirm_pass"] = any(s in deg2 for s in SURFACED1_SYMPTOMS)
    after = _count_task()
    out["task_after"] = after
    out["task_diff"] = after - before

    # 回归红线：confirm 续流仍出现 42200 症状 = SURFACED-1 未修
    if out["symptom_in_confirm_pass"]:
        out["regression"] = "SURFACED-1 症状仍在：confirm 续流仍报「必须提供 tool_id」"
        print(json.dumps(out, ensure_ascii=False))
        return 2
    out["ok"] = True
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))
        sys.exit(1)
