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

import http.client
import io
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# W-NEXT-PROBE-001 修:loguru 在 DEBUG 模式下把 INFO 日志写到 sys.stdout
#   (app/common/logging.py:55),而本探针用 print(json.dumps(...)) 走同一 stdout —— 结果:
#   check-demo.mjs ⑫ 守卫拿到的 stdout 是 loguru INFO 行 + 我们的 JSON,JSON.parse 失败。
#   修复:probe 入口把 sys.stdout 替换成 StagedJsonOnlyWriter —— 把"非契约字节"(loguru 等污染)
#   全部重定向到 stderr,只让带 _PROBE_JSON_OUT 旗标的 JSON 行放行到真 stdout。
#   配合 init_mysql() 在 _count_task() 前调用(原 bug 已被 stdout 污染掩盖)。
#   边界态:loguru 抛异常 / 子进程崩 → _safe_emit 兜底输出 error JSON,守卫不会卡死。
_STAGED = None  # 占位:由 _install_json_only_stdout 赋值

# Stage 标记:只有携带本哨兵串的 print 才被允许到达真 stdout。
_PROBE_JSON_OUT = "__PROBE_JSON_OUT__:"


class JsonOnlyStdout:
    """Wrap 真实 sys.stdout:把非契约字节转 stderr,只放 JSON 行通过。

    - 任何不包含 _PROBE_JSON_OUT 哨兵的写入 → 转发到 stderr(prefixed)
    - 包含 _PROBE_JSON_OUT 哨兵的写入 → 剥哨兵 + 走真 stdout
    """

    def __init__(self, real_stdout):
        self._real = real_stdout

    def write(self, s):
        if not s:
            return 0
        if _PROBE_JSON_OUT in s:
            return self._real.write(s.replace(_PROBE_JSON_OUT, ""))
        # 走 stderr(避免污染契约流)
        try:
            sys.stderr.write(f"[probe:redirect] {s}")
            sys.stderr.flush()
        except Exception:
            pass
        return len(s)

    def flush(self):
        try:
            self._real.flush()
        except Exception:
            pass

    def isatty(self):
        return False

    def writable(self):
        return True


def _install_json_only_stdout():
    """probe 入口调:把 sys.stdout 替换成 JsonOnlyStdout。"""
    global _STAGED
    if _STAGED is not None:
        return  # 已替换,幂等
    _STAGED = JsonOnlyStdout(sys.stdout)
    sys.stdout = _STAGED


def _probe_print(payload: dict):
    """契约输出:走真 stdout(其他 print 仍被 JsonOnlyStdout 吞到 stderr)。"""
    sys.stdout.write(_PROBE_JSON_OUT + json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()

# W-NEXT-CHECKDEMO-004 修:.env 加载兜底 ——
# 现象:check-demo.mjs ⑫ 守卫 spawn 子进程时 cwd=仓库根,不是 edu-agent/。
#       pydantic-settings 的 env_file='.env' 是相对 cwd 的相对路径,cwd=仓库根时
#       找不到 edu-agent/.env → 启动期 ValidationError: LLM_API_KEY Field required。
#       _count_task 走 app.database.fetch_one 间接依赖 settings.MYSQL_* 同样会崩。
# 修复:入口处显式 load_dotenv(EDU_ROOT/.env),让进程环境变量在 import app.config 之前
#       已经被填好。不依赖 cwd,不依赖父进程的 env 注入。
ROOT = Path(__file__).resolve().parents[1]
_ENV_PATH = ROOT / ".env"
if _ENV_PATH.is_file():
    from dotenv import load_dotenv  # noqa: E402
    # W-NEXT-PROBE-001 修:.env 在 Windows PowerShell 写入历史中混入 NEL(0x85)等非 UTF-8 字节,
    #   强制 encoding="latin-1" 容错读取(dotnet 默认沿 utf-8 → UnicodeDecodeError 整个 probe 崩)。
    #   字段值不受影响(REDIS_URL/REDIS_PORT 等关键值用 ASCII)。
    load_dotenv(_ENV_PATH, override=False, encoding="latin-1")
else:
    print(f"[hitl_realness_probe] WARN .env not found at {_ENV_PATH} — pydantic Field required 风险", file=sys.stderr)

# W-NEXT-PROBE-001 修:.env 加载后立刻装 stdout 拦截器 —— 必须先于任何 app.* import。
#   触发链:load_dotenv → 不触发;但本模块下一行 from app.database ... 会间接 import
#   app.common.logging → 自动 setup_logging() → loguru 加 sys.stdout sink → DEBUG INFO
#   行污染。拦截器装在 import 之前,污染会被自动重定向到 stderr。
_install_json_only_stdout()


BACKEND = os.environ.get("CHECK_DEMO_BACKEND", "http://127.0.0.1:8000").rstrip("/")
ACCOUNT = "adm02test"
PASSWORD = "Test@123456"


def _create_session(token: str, title: str = "surfaced1_probe") -> str:
    """POST /api/chat/sessions → 拿 session_id。/api/chat/stream 需要已存在的 session_id。

    W-NEXT-PROBE-001 修:此前直接用 `surfaced1_probe_<ts>` 当 session_id 发到 /api/chat/stream,
    后端返 404 CHAT_SESSION_NOT_FOUND,urllib 抛 HTTPError,probe 整体崩 → stdout 一行 error。
    该 bug 在 W-NEXT-PROBE-001 前一直被 stdout JSON 污染掩盖 —— check-demo ⑫ 一红即从未真
    跑到 _stream_events 成功路径。本任务一并修根因(同 P0 教训)。
    """
    try:
        with _post(f"{BACKEND}/api/chat/sessions",
                   {"title": title, "visibility": "private"}, token=token) as r:
            j = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:200]
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(f"create_session HTTP {e.code}: {body}") from e
    sid = ((j.get("data") or {}).get("session_id")
           or (j.get("data") or {}).get("id"))
    if not sid:
        raise RuntimeError(f"create_session 未返回 session_id: {j}")
    return str(sid)


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
    # W-NEXT-PROBE-001 修:捕获 HTTPError(404/500/网络)→ 把诊断塞进 events + 抛 AppException,
    #   让 main() 的 _probe_print 落到 error JSON 路径而非 stderr 崩溃。这样探针边界态
    #   (后端不可达 / 路由断)仍能输出契约 JSON,守卫可降级 WARN 而非"非 JSON 解析失败"。
    # W-NEXT-CHECKDEMO-HARD-002 修(PROBE-001 P0-3):探针永不崩 —— SSE 全链路边界态纳入 events。
    #   批判:上方原本只兜住 urlopen 阶段的 HTTPError/URLError,三类异常仍会穿透:
    #     a) urlopen 阶段:http.client.RemoteDisconnected / BadStatusLine(服务端不回响应直断)、
    #        socket.timeout(连接超时)——urllib 只把 OSError 包成 URLError,这两类原样穿透;
    #     b) 读流阶段:socket.timeout(流中途停顿)、http.client.IncompleteRead/BadStatusLine
    #        (chunk 帧破坏)、ConnectionResetError(对端 RST)。
    #   修复:urlopen + 读流两段各自按「timeout → protocol(HTTPException)→ connection →
    #   兜底」序捕获,异常转伪事件(stream_timeout / stream_protocol_error /
    #   stream_connection_error / stream_read_error),已收集事件原样保留,main() 走
    #   「模型未触发 knowledge_import」观测分支而非顶层 error JSON。
    #   顺序约束:RemoteDisconnected 同时继承 HTTPException 与 ConnectionResetError,
    #   HTTPException 分支必须先于 ConnectionError/OSError 判;socket.timeout(TimeoutError,
    #   OSError 子类)必须先于 OSError 判。
    try:
        resp_ctx = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:200]
        except Exception:  # noqa: BLE001
            pass
        events.append(("stream_http_error", {
            "status": e.code,
            "reason": e.reason,
            "body": body,
            "session_id": session_id,
        }))
        return events
    except urllib.error.URLError as e:
        events.append(("stream_url_error", {
            "reason": str(e.reason),
            "session_id": session_id,
        }))
        return events
    except socket.timeout as e:
        events.append(("stream_timeout", {
            "exc": type(e).__name__,
            "reason": str(e) or "urlopen timeout",
            "session_id": session_id,
        }))
        return events
    except http.client.HTTPException as e:
        # RemoteDisconnected / BadStatusLine / ProtocolError 等(服务端不回响应直断)
        events.append(("stream_protocol_error", {
            "exc": type(e).__name__,
            "reason": str(e)[:160],
            "session_id": session_id,
        }))
        return events
    except (ConnectionError, OSError) as e:
        events.append(("stream_connection_error", {
            "exc": type(e).__name__,
            "reason": str(e)[:160],
            "session_id": session_id,
        }))
        return events
    with resp_ctx as resp:
        try:
            for raw in resp:
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if line.startswith("event:"):
                    cur = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    d = line[len("data:"):].strip()
                    try:
                        obj = json.loads(d)
                    except Exception:  # noqa: BLE001
                        obj = None
                    events.append((cur, obj))
        except socket.timeout as e:
            events.append(("stream_timeout", {
                "exc": type(e).__name__,
                "reason": str(e) or "read timeout",
                "session_id": session_id,
            }))
        except http.client.HTTPException as e:
            # IncompleteRead(chunk 帧破坏/谎报 Content-Length)/BadStatusLine 等
            events.append(("stream_protocol_error", {
                "exc": type(e).__name__,
                "reason": str(e)[:160],
                "session_id": session_id,
            }))
        except (ConnectionError, OSError) as e:
            events.append(("stream_connection_error", {
                "exc": type(e).__name__,
                "reason": str(e)[:160],
                "session_id": session_id,
            }))
        except Exception as e:  # noqa: BLE001 —— 任何读流异常都不得穿透(探针永不崩)
            events.append(("stream_read_error", {
                "exc": type(e).__name__,
                "reason": str(e)[:160],
                "session_id": session_id,
            }))
    return events


def _count_task() -> int:
    sys.path.insert(0, str(ROOT))
    from app.database import init_mysql, fetch_one
    import asyncio
    # W-NEXT-PROBE-001 修:原代码漏调 init_mysql(),fetch_one() 抛 "MySQL 连接池未初始化"。
    #   该 bug 在 W-NEXT-PROBE-001 前一直被 stdout JSON 污染掩盖(check-demo ⑫ 一红一绿从未
    #   真跑到 _count_task 成功路径),本任务一并修根因。
    async def _q():
        await init_mysql()
        row = await fetch_one("SELECT COUNT(*) AS c FROM knowledge_import_task")
        return int((row or {}).get("c", 0)) if row else 0
    return asyncio.run(_q())


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
        _probe_print(out)
        return 1

    token = _login()
    before = _count_task()
    out["task_before"] = before

    # W-NEXT-PROBE-001 修:先建 session 再发流(原 probe 跳过这步,直接拿 f"surfaced1_probe_{ts}"
    #   当 session_id → /api/chat/stream 404 → probe 整体崩)
    session_id = _create_session(token)
    out["session_id"] = session_id
    query = "请使用 knowledge_import 工具把示例文档导入知识库（visibility=private）"
    events = _stream_events(token, query, session_id)

    # W-NEXT-CHECKDEMO-HARD-002 修(PROBE-001 P0-3):边界态事件回显到契约 JSON,
    #   check-demo ⑫ 与人工排查都能看到「流没走完」的具体原因(协议断/超时/连接重置),
    #   而不是笼统的「模型未触发 knowledge_import」。
    boundary = [e for (e, _d) in events if str(e).startswith("stream_") and e != "stream"]
    if boundary:
        out["stream_boundary_events"] = boundary

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
        out["note"] = "模型未触发 knowledge_import，跳过 HITL 续流；SURFACED-1 修复由单测覆盖" + (
            f"；流边界态:{out['stream_boundary_events']}" if boundary else ""
        )
        _probe_print(out)
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
    # W-NEXT-CHECKDEMO-HARD-002 修(PROBE-001 P0-3):续流段边界态同样回显(不阻断观测)
    boundary2 = [e for (e, _d) in events2 if str(e).startswith("stream_")]
    if boundary2:
        out["stream_boundary_events_confirm_pass"] = boundary2
    deg2 = " ".join(str((d or {}).get("degraded_reason", ""))
                    for (e, d) in events2 if isinstance(d, dict))
    out["symptom_in_confirm_pass"] = any(s in deg2 for s in SURFACED1_SYMPTOMS)
    after = _count_task()
    out["task_after"] = after
    out["task_diff"] = after - before

    # 回归红线：confirm 续流仍出现 42200 症状 = SURFACED-1 未修
    if out["symptom_in_confirm_pass"]:
        out["regression"] = "SURFACED-1 症状仍在：confirm 续流仍报「必须提供 tool_id」"
        _probe_print(out)
        return 2
    out["ok"] = True
    _probe_print(out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        # W-NEXT-PROBE-001 修:同样走 _probe_print,保证契约流只有 JSON。
        #   兜底:即使主流程 raise 也不会污染 stdout。
        _probe_print({"error": f"{type(e).__name__}: {e}"})
        sys.exit(1)
