# -*- coding: utf-8 -*-
"""W-NEXT-MCP-001 ⑬「MCP 三态」健康门探针（check-demo.mjs 调用）。

三段验收（对齐 kickoff ⑬）：
  ① 能力对账：audit_mcp_capability() → ok=true 且 checked>=10
  ② 内置工具落审计：调 calculator（内置）→ mcp_tool_call_log 出现对应 call_id 行（server_id=0）
  ③ 字段级脱敏：调 calculator 带 password 字段 → 落库 args_json 值 ***REDACTED*** 且不含明文

跑法（在 edu-agent/ 下，需 8000 在线 + MySQL 可达）：
    .venv/Scripts/python.exe scripts/eval/mcp_tristate_probe.py

输出：末尾打印一行 `[TRISTATE] <json>`，供 check-demo.mjs 解析。
  json: {audit_ok, audit_checked, builtin_logged, redacted, env_blocked, detail}
退出码：0=全绿；2=环境阻塞（后端/DB/认证不可达，WARN 不阻断）；1=真实失败（代码缺陷）。
"""
from __future__ import annotations

import asyncio
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

# W-NEXT-CHECKDEMO-004 修:.env 加载兜底 ——
# 现象:check-demo.mjs ⑬ 守卫 spawn 子进程时 cwd=仓库根,不是 edu-agent/。
#       pydantic-settings 的 env_file='.env' 是相对 cwd 的相对路径,cwd=仓库根时
#       找不到 edu-agent/.env → 启动期 ValidationError: LLM_API_KEY Field required,
#       _db_query_one 调 settings.MYSQL_* 全崩。和 W-NEXT-CHECKDEMO-003 (⑲) 同型根因。
# 修复:入口处显式 load_dotenv(EDU_ROOT/.env),让进程环境变量在 import app.config 之前
#       已经被填好,绕过 pydantic-settings 的 cwd-相对 env_file 寻址陷阱。
from dotenv import load_dotenv  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]          # edu-agent/
_ENV_PATH = _REPO / ".env"
if _ENV_PATH.is_file():
    load_dotenv(_ENV_PATH, override=False)  # 已有环境变量优先,避免覆盖 CI 注入
else:
    print(f"[mcp_tristate_probe] WARN .env not found at {_ENV_PATH} — pydantic Field required 风险", file=sys.stderr)
sys.path.insert(0, str(_REPO))

BACKEND = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
ADMIN = {"account": "adm02test", "password": "Test@123456"}


def _http(method: str, url: str, *, token: str | None = None, body: dict | None = None,
          timeout: int = 8):    # 禁用环境代理（HTTP_PROXY 会吞 loopback 请求 → 502）
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


async def _db_query_one(sql: str, args: tuple):
    import asyncmy
    from app.config import settings

    conn = await asyncmy.connect(
        host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        db=settings.MYSQL_DATABASE, autocommit=True,
    )
    try:
        async with conn.cursor() as cur:
            await cur.execute(sql, args)
            # 本机 asyncmy 版本 fetchone 非可等待对象，统一用 fetchall 取首行（与 R15b 探针一致）
            rows = await cur.fetchall()
            return rows[0] if rows else None
    finally:
        conn.close()


def _emit(audit_ok, audit_checked, builtin_logged, redacted, env_blocked, detail):
    payload = {
        "audit_ok": audit_ok, "audit_checked": audit_checked,
        "builtin_logged": builtin_logged, "redacted": redacted,
        "env_blocked": env_blocked, "detail": detail,
    }
    print(f"[TRISTATE] {json.dumps(payload, ensure_ascii=False)}")


async def main() -> int:
    result = {"audit_ok": False, "audit_checked": 0, "builtin_logged": False,
              "redacted": False, "env_blocked": False, "detail": ""}

    # ① 能力对账（纯函数，零 IO）
    try:
        from app.mcp.capability_audit import audit_mcp_capability

        r = audit_mcp_capability()
        result["audit_checked"] = r["checked"]
        result["audit_ok"] = bool(r["ok"]) and r["checked"] >= 10
        if not result["audit_ok"]:
            result["detail"] = (f"审计未通过: checked={r['checked']} "
                                f"virtual={r['virtual']} broken={r['broken']}")
    except Exception as e:  # noqa: BLE001
        result["detail"] = f"审计异常: {type(e).__name__}: {e}"

    # 后端连通性（环境阻塞判定）
    try:
        st, _ = _http("GET", f"{BACKEND}/health")
        if st != 200:
            raise RuntimeError(f"health HTTP {st}")
    except Exception as e:  # noqa: BLE001
        result["env_blocked"] = True
        result["detail"] = (result["detail"] + " | " if result["detail"] else "") + f"后端不可达: {e}"
        _emit(**result)
        return 2

    # 登录 admin（拿 token 调 /api/mcp/tools/test）
    try:
        _, login = _http("POST", f"{BACKEND}/api/auth/login",
                         body={"account": ADMIN["account"], "password": ADMIN["password"]})
        token = login.get("data", {}).get("access_token")
        if not token:
            raise RuntimeError("无 access_token（登录失败）")
    except Exception as e:  # noqa: BLE001
        result["env_blocked"] = True
        result["detail"] = (result["detail"] + " | " if result["detail"] else "") + f"登录失败: {e}"
        _emit(**result)
        return 2

    # ② 内置工具 calculator → 落审计行（server_id=0）
    #    内置工具无 mcp_tool 行、无 server_id：按 W-NEXT-2 接线约定传 tool_id=0 + tool_name，
    #    使 MCPToolTestReq 校验通过且 _resolve_builtin_name(0,...) 正确回落按名解析。
    cid2 = None
    try:
        _, calc = _http("POST", f"{BACKEND}/api/mcp/tools/test",
                        token=token, body={"tool_id": 0, "tool_name": "calculator",
                                           "args": {"a": 6, "b": 7, "op": "mul"}})
        cid2 = calc.get("data", {}).get("call_id")
        if not cid2:
            raise RuntimeError(f"calculator 响应无 call_id: {calc}")
        row = await _db_query_one(
            "SELECT call_id, server_id, tool_name FROM mcp_tool_call_log WHERE call_id=%s", (cid2,))
        if not row:
            raise RuntimeError(f"calculator 审计行未落库（call_id={cid2}）")
        if int(row[1]) != 0:
            raise RuntimeError(f"内置工具 server_id 应为 0，实测 {row[1]}")
        result["builtin_logged"] = True
    except Exception as e:  # noqa: BLE001
        result["detail"] = (result["detail"] + " | " if result["detail"] else "") + f"②内置落库失败: {e}"

    # ③ 内置工具 calculator 带 password → 脱敏校验
    cid3 = None
    try:
        _, calc3 = _http("POST", f"{BACKEND}/api/mcp/tools/test",
                         token=token, body={"tool_id": 0, "tool_name": "calculator",
                                            "args": {"a": 1, "b": 2, "op": "add",
                                                     "password": "secret123"}})
        cid3 = calc3.get("data", {}).get("call_id")
        if not cid3:
            raise RuntimeError(f"calculator(pw) 响应无 call_id: {calc3}")
        row3 = await _db_query_one(
            "SELECT args_json FROM mcp_tool_call_log WHERE call_id=%s", (cid3,))
        if not row3:
            raise RuntimeError(f"calculator(pw) 审计行未落库（call_id={cid3}）")
        args_json = str(row3[0] or "")
        if "secret123" in args_json:
            raise RuntimeError("明文密码出现在落库 args_json（脱敏失效）")
        if "***REDACTED***" not in args_json:
            raise RuntimeError("args_json 未见 ***REDACTED***（脱敏未生效）")
        result["redacted"] = True
    except Exception as e:  # noqa: BLE001
        result["detail"] = (result["detail"] + " | " if result["detail"] else "") + f"③脱敏失败: {e}"

    # 自清：删除本次探针写入的测试审计行（按 call_id）
    for cid in (cid2, cid3):
        if cid:
            try:
                await _db_query_one("DELETE FROM mcp_tool_call_log WHERE call_id=%s", (cid,))
            except Exception:  # noqa: BLE001
                pass

    _emit(**result)
    if result["env_blocked"]:
        return 2
    return 0 if (result["audit_ok"] and result["builtin_logged"] and result["redacted"]) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
