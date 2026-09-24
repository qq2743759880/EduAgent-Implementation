# -*- coding: utf-8 -*-
"""TA7 共享工具：真实 HTTP 调 chat SSE + 直读 mcp_tool_call_log（机验证据）。

- 全程绕开 HTTP_PROXY（本机 loopback 会被吞成 502）。
- SSE 解析：event: start|retrieval|token|pending_confirm|done|error + data 行。
- DB：直连 127.0.0.1:3306（.env MYSQL_USER/PASSWORD），库名从 settings 兜底 edu。
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

def _find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "edu-agent" / ".env").exists():
            return p
    raise RuntimeError("未找到仓库根（含 edu-agent/.env）")


ROOT = _find_repo_root(Path(__file__).resolve())
EDU = ROOT / "edu-agent"
BASE = "http://127.0.0.1:9988"
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def post_json(path: str, payload: dict, token: str | None = None, timeout: int = 30):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
        method="POST",
    )
    with _opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def get_json(path: str, token: str | None = None, timeout: int = 30):
    req = urllib.request.Request(
        BASE + path,
        headers={**({"Authorization": f"Bearer {token}"} if token else {})},
        method="GET",
    )
    with _opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def delete_json(path: str, token: str | None = None, timeout: int = 30):
    req = urllib.request.Request(
        BASE + path,
        headers={**({"Authorization": f"Bearer {token}"} if token else {})},
        method="DELETE",
    )
    with _opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def login(account: str, password: str = "Test@123456") -> str:
    resp = post_json("/api/auth/login", {"account": account, "password": password})
    if resp.get("code") != 0:
        raise RuntimeError(f"登录失败 {account}: {resp}")
    return resp["data"]["access_token"]


def chat_stream(query: str, token: str, session_id: str | None = None, timeout: int = 300):
    """返回 (events, answer_text, done_data, raw_lines)。"""
    payload = {"query": query, "stream": True}
    if session_id:
        payload["session_id"] = session_id
    req = urllib.request.Request(
        BASE + "/api/chat/stream",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8",
                 "Accept": "text/event-stream",
                 "Authorization": f"Bearer {token}"},
        method="POST",
    )
    events: list[dict] = []
    answer = ""
    done: dict = {}
    raw: list[str] = []
    with _opener.open(req, timeout=timeout) as r:
        cur_event = None
        for raw_line in r:
            line = raw_line.decode("utf-8", "replace").rstrip("\n").rstrip("\r")
            raw.append(line)
            if line.startswith("event:"):
                cur_event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                try:
                    payload_d = json.loads(line.split(":", 1)[1].strip())
                except Exception:
                    continue
                if cur_event == "token":
                    answer += str(payload_d.get("delta") or "")
                if cur_event == "done":
                    done = payload_d
                events.append({"event": cur_event, "data": payload_d})
    return events, answer, done, raw


def db_conn():
    import pymysql

    env = {}
    for line in (EDU / ".env").read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return pymysql.connect(
        host="127.0.0.1", port=int(env.get("MYSQL_PORT", 3306)),
        user=env.get("MYSQL_USER", "root"), password=env.get("MYSQL_PASSWORD", "123456"),
        database=env.get("MYSQL_DB") or env.get("DB_NAME") or "edu",
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
    )


def q(sql: str, params=None):
    conn = db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params) if params is not None else cur.execute(sql)
            return cur.fetchall()
    finally:
        conn.close()


def x(sql: str, params=None) -> int:
    conn = db_conn()
    try:
        with conn.cursor() as cur:
            n = cur.execute(sql, params) if params is not None else cur.execute(sql)
        conn.commit()
        return n
    finally:
        conn.close()


def jj(o) -> str:
    return json.dumps(o, ensure_ascii=False, indent=2, default=str)


if __name__ == "__main__":
    print(jj(q("SELECT DATABASE() AS db, VERSION() AS v")))
