# -*- coding: utf-8 -*-
"""W-NEXT-CHECKDEMO-HARD-002 单测 —— 消化两份批判的遗留 P0（check-demo.mjs 域）。

承接批判与对应锁：
  PROBE-001 P0-1   detectRedisContainer 只走 publish/expose filter，自定义 network
                   漂移时 0 匹配盲区 → 第 3 试 docker ps -a 全表解析 ports 列。
                   锁：静态(函数/全表参数存在) + 动态(纯函数解析 + filter 全 0 时兜底路径)。
  PROBE-001 P0-3   hitl_realness_probe._stream_events 只兜 HTTPError/URLError，
                   ProtocolError/RemoteDisconnected/socket.timeout 仍 raise
                   → 边界态伪事件(stream_protocol_error 等)，探针永不崩。
                   锁：静态(四类伪事件 + except 排序) + 动态(注入异常全转为边界态事件)。
  PROBE-001 P0-4   fail-drill 多容器同宿主端口并存未覆盖 → 同宿主端口命中列表
                   running 优先 + 表序稳定(同输入必同输出)。
                   锁：动态(并存表 5 连跑全等 + running 优先)。
  DEBUG-DOC-001 P0-3a  ⑧ 探测面只测 /api/users/me → 补 /api/admin/users 双探点，
                   管理端护栏失效任何环境(含 DEBUG=true)直接 FAIL，文案同步。
                   锁：静态(双探点/护栏失效文案) + 动态(真后端无 token /api/admin/users
                   必须不可达——安全不变量)。
  DEBUG-DOC-001 P0-3b  ⑯ lifecycle 守卫加 .env 变更感知提示(改 .env 不重启 ⑧ 可能误判)。
                   锁：静态(附注行锚点存在)。

环境注意：
  - 静态层零外部依赖；动态 JS 层只需 node(不碰真 docker)；动态 Python 层
    子进程内 monkeypatch urlopen(不碰真网络)；仅 real-backend 一例需 8000 在线
    (不可达 pytest.skip)。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK_DEMO_MJS = REPO_ROOT / "scripts" / "check-demo.mjs"
HITL_PROBE = REPO_ROOT / "scripts" / "hitl_realness_probe.py"


# ============================================================
# 静态层 1:check-demo.mjs 全表兜底 + 纯函数锚点（PROBE-001 P0-1）
# ============================================================
def test_detect_redis_container_has_full_table_fallback():
    """detectRedisContainer 必须含 docker ps -a 全表第 3 试 + 纯函数解析。"""
    src = CHECK_DEMO_MJS.read_text(encoding="utf-8")
    assert "function parseDockerPortTableMatches" in src, (
        "纯函数 parseDockerPortTableMatches 缺失——全表兜底未抽纯函数(单测/盲测无法锁行为)"
    )
    assert "parseDockerPortTableMatches(hostPort, out)" in src, (
        "detectRedisContainer 未在第 3 试调用全表解析"
    )
    assert "{{.Names}}\\t{{.Ports}}\\t{{.State}}" in src, (
        "docker ps -a 全表 format 缺 Names/Ports/State 三列(State 用于 running 优先判定)"
    )
    # 第 3 试必须真的调 docker ps -a（防有人把 -a 删掉只剩 ps）
    m = re.search(
        r"runCmd\(\s*\"docker\",\s*\[\s*\"ps\",\s*\"-a\",\s*\"--format\"[^\]]*\]",
        src,
    )
    assert m, "未找到 docker ps -a 全表调用"
    # 抽取锚点(单测/盲测按锚点截取函数)必须保留
    assert "[HARD2:FNSPLIT-END]" in src, "HARD2:FNSPLIT-END 抽取锚点被删——单测/盲测将无法截取函数"


def test_02_label_keeps_dynamic_port_wording():
    """② 守卫动态反查文案不得回退(W-NEXT-PROBE-001 回归保护)。"""
    src = CHECK_DEMO_MJS.read_text(encoding="utf-8")
    assert "按 .env REDIS_PORT=" in src
    assert "反查容器" in src


# ============================================================
# 静态层 2:⑧ 双探点（DEBUG-DOC-001 P0-3a）
# ============================================================
def test_08_dual_probe_admin_users_present():
    """⑧ 必须双探点:/api/users/me + /api/admin/users,且管理端护栏失效文案在。"""
    src = CHECK_DEMO_MJS.read_text(encoding="utf-8")
    assert "/api/users/me" in src, "⑧ 丢失 /api/users/me 探点(回归)"
    assert "/api/admin/users" in src, "⑧ 缺 /api/admin/users 第二探点(DEBUG-DOC-001 P0-3a 未承接)"
    assert "双探点" in src, "⑧ 文案未同步双探点语义"
    assert "护栏失效" in src, "⑧ 缺管理端护栏失效判据文案"
    # 管理端护栏失效必须是 FAIL 分支(throw,不吃 __warn)
    m = re.search(r"if \(adminVuln\) \{[\s\S]{0,600}?throw new Error", src)
    assert m, "adminVuln 分支未直接 throw(管理端护栏失效必须任何环境 FAIL,不走 WARN 降级)"


# ============================================================
# 静态层 3:⑯ .env 变更感知提示（DEBUG-DOC-001 P0-3b）
# ============================================================
def test_16_env_change_hint_present():
    """⑯ 输出后必须追加 .env 变更感知提示行(带附注锚点)。"""
    src = CHECK_DEMO_MJS.read_text(encoding="utf-8")
    assert "[⑯ 附注]" in src, "⑯ 缺 .env 变更感知附注行(DEBUG-DOC-001 P0-3b 未承接)"
    assert ".env 变更感知" in src
    assert "可能误判" in src, "附注缺「⑧ 可能误判」关键语义"
    assert "重启" in src, "附注缺「重启后端」处置指引"


# ============================================================
# 静态层 4:probe 边界态事件 + except 排序（PROBE-001 P0-3）
# ============================================================
def _stream_events_body() -> str:
    src = HITL_PROBE.read_text(encoding="utf-8")
    start = src.index("def _stream_events")
    end = src.index("def _count_task")
    return src[start:end]


def test_hitl_probe_boundary_events_present():
    """_stream_events 必须含四类边界态伪事件(HTTPError/URLError 原有路径不回退)。"""
    body = _stream_events_body()
    for ev in (
        "stream_http_error",   # PROBE-001 已有,防回退
        "stream_url_error",    # PROBE-001 已有,防回退
        "stream_protocol_error",      # RemoteDisconnected/BadStatusLine/IncompleteRead
        "stream_timeout",             # socket.timeout
        "stream_connection_error",    # ConnectionResetError 等
        "stream_read_error",          # 兜底(探针永不崩)
    ):
        assert ev in body, f"_stream_events 缺边界态事件 {ev}"


def test_hitl_probe_except_ordering():
    """except 判序必须:socket.timeout 先于 OSError;HTTPException 先于 ConnectionError/OSError。

    RemoteDisconnected 同时继承 HTTPException 与 ConnectionResetError——
    HTTPException 分支在后会把它误归为 connection_error(须归 protocol_error)。
    socket.timeout(TimeoutError) 是 OSError 子类——后判会被 OSError 吞掉。
    """
    body = _stream_events_body()
    i_timeout = body.index("except socket.timeout")
    i_proto = body.index("except http.client.HTTPException")
    i_conn = body.index("except (ConnectionError, OSError)")
    assert i_timeout < i_conn, "socket.timeout 必须先于 (ConnectionError, OSError) 判"
    assert i_proto < i_conn, "http.client.HTTPException 必须先于 (ConnectionError, OSError) 判"
    # http.client / socket import 必须在(否则 NameError)
    src = HITL_PROBE.read_text(encoding="utf-8")
    assert re.search(r"^import http\.client$", src, re.MULTILINE), "缺 import http.client"
    assert re.search(r"^import socket$", src, re.MULTILINE), "缺 import socket"


# ============================================================
# 动态层 A(纯 Python,零网络):_stream_events 注入异常 → 全转边界态事件
# ============================================================
_INJECT_CODE = r'''
import sys, json
sys.path.insert(0, r"__SCRIPTS_DIR__")
import http.client, socket
import urllib.request
import hitl_realness_probe as h


class FakeResp:
    """SSE 响应桩:先吐 1 个 start 事件,随后在迭代中 raise 指定异常(模拟流中途断)。"""

    def __init__(self, exc):
        self._exc = exc
        self._n = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return self

    def __next__(self):
        # W-NEXT-CHECKDEMO-HARD-002 接手修:原桩单 chunk 吐 "event: start\ndata: {}\n\n"
        #   两行——_stream_events 按「chunk=一行」解析,该 chunk 以 "event:" 开头只会置 cur
        #   不 append,"start" 事件从未进 events → kinds[0]=="start" 断言必挂
        #   (前任误记为「Windows 下已收集事件丢失」,实为桩自身缺陷,全平台必现)。
        #   修:SSE 迭代按行分片——event 行与 data 行各吐一个 chunk。
        if self._n == 0:
            self._n += 1
            return b"event: start\n"
        if self._n == 1:
            self._n += 2
            return b"data: {}\n"
        raise self._exc


def run_case(name, mode, exc, expect_event):
    orig = urllib.request.urlopen
    try:
        if mode == "midstream":
            urllib.request.urlopen = lambda req, timeout=None: FakeResp(exc)
        else:  # urlopen 阶段直接 raise
            def _raise(req, timeout=None):
                raise exc
            urllib.request.urlopen = _raise
        ev = h._stream_events("tok", "q", "sess-1")
    finally:
        urllib.request.urlopen = orig
    kinds = [e for (e, _d) in ev]
    boundary = [e for e in kinds if str(e).startswith("stream_")]
    assert boundary == [expect_event], f"{name}: boundary={boundary} expect=[{expect_event}] all={kinds}"
    if mode == "midstream":
        assert kinds[0] == "start", f"{name}: 已收集事件丢失({kinds})"
    h._probe_print({"case": name, "ok": True, "boundary": boundary, "n_events": len(kinds)})


run_case("midstream_incomplete_read", "midstream",
         http.client.IncompleteRead(b"partial"), "stream_protocol_error")
run_case("midstream_remote_disconnected", "midstream",
         http.client.RemoteDisconnected("Remote end closed"), "stream_protocol_error")
run_case("midstream_bad_status_line", "midstream",
         http.client.BadStatusLine("x"), "stream_protocol_error")
run_case("midstream_socket_timeout", "midstream",
         socket.timeout("timed out"), "stream_timeout")
run_case("midstream_conn_reset", "midstream",
         ConnectionResetError("ECONNRESET"), "stream_connection_error")
run_case("midstream_generic", "midstream",
         RuntimeError("weird"), "stream_read_error")
run_case("urlopen_remote_disconnected", "urlopen",
         http.client.RemoteDisconnected("no response"), "stream_protocol_error")
run_case("urlopen_socket_timeout", "urlopen",
         socket.timeout("connect timeout"), "stream_timeout")
run_case("urlopen_conn_reset", "urlopen",
         ConnectionResetError("RST"), "stream_connection_error")
'''


def test_stream_events_never_raises_on_injected_errors():
    """9 类注入异常全部转为边界态伪事件,已收集事件保留,函数不 raise(P0-3 探针永不崩)。"""
    code = _INJECT_CODE.replace("__SCRIPTS_DIR__", str(HITL_PROBE.parent))
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
    f.write(code)
    f.close()
    try:
        proc = subprocess.run(
            [sys.executable, f.name],
            capture_output=True, text=True, timeout=60, check=False,
        )
        out_lines = [ln for ln in proc.stdout.split("\n") if ln.strip()]
        assert proc.returncode == 0, (
            f"注入态下探针代码崩了(P0-3 未闭环): rc={proc.returncode}\n"
            f"stdout={proc.stdout[:400]}\nstderr={proc.stderr[:600]}"
        )
        assert len(out_lines) == 9, f"应 9 例全输出,实得 {len(out_lines)}: {out_lines!r}"
        cases = {json.loads(ln)["case"]: json.loads(ln) for ln in out_lines}
        expect = {
            "midstream_incomplete_read": "stream_protocol_error",
            "midstream_remote_disconnected": "stream_protocol_error",
            "midstream_bad_status_line": "stream_protocol_error",
            "midstream_socket_timeout": "stream_timeout",
            "midstream_conn_reset": "stream_connection_error",
            "midstream_generic": "stream_read_error",
            "urlopen_remote_disconnected": "stream_protocol_error",
            "urlopen_socket_timeout": "stream_timeout",
            "urlopen_conn_reset": "stream_connection_error",
        }
        for case, ev in expect.items():
            assert cases[case]["ok"] is True, f"{case} 未闭环: {cases[case]}"
            assert cases[case]["boundary"] == [ev], f"{case} 归类错: {cases[case]}"
    finally:
        os.unlink(f.name)


# ============================================================
# 动态层 B(node,零 docker):全表解析纯函数 + 兜底路径 + 并存确定性
# ============================================================
_RUNCMD_STUB_AND_CASES = r'''
// ---- 测试桩:runCmd 按 mode 分发(不碰真 docker) ----
const MODE = process.argv[2];
const TABLE = [
  "mysql-c\t0.0.0.0:3308->3306/tcp\trunning",
  "exited-redis\t0.0.0.0:6377->6379/tcp\texited",
  "running-redis\t:::6377->6379/tcp\trunning",
  "ipv6-redis\t[::]:6379->6379/tcp\trunning",
  "expose-only\t6379/tcp\tcreated",
].join("\n");

async function runCmd(cmd, cargs, timeoutMs) {
  // W-NEXT-CHECKDEMO-HARD-002 接手修:detectRedisContainer 调用形如
  //   runCmd("docker", ["ps", "--filter", ...]) —— 模式标记在 cargs[1],
  //   原桩误判 cargs[0](恒为 "ps")→ 全部落到 throw,兜底路径从未被走到。
  if (MODE === "filters_zero") {
    // publish/expose 过滤双双 0 匹配(自定义 network 漂移模拟),全表兜底命中
    if (cargs[1] === "--filter") return "";
    if (cargs[1] === "-a") return TABLE;
  }
  if (MODE === "all_zero") {
    if (cargs[1] === "--filter") return "";
    if (cargs[1] === "-a") return "";
  }
  throw new Error("unexpected runCmd " + JSON.stringify(cargs));
}

const out = {};
out.mode = MODE;

// ---- 纯函数解析用例 ----
out.p_normal = parseDockerPortTableMatches(6377, "c1\t0.0.0.0:6377->6379/tcp, :::6377->6379/tcp\trunning");
out.p_ipv6 = parseDockerPortTableMatches(6379, "c6\t[::]:6379->6379/tcp\trunning");
out.p_expose_only_ignored = parseDockerPortTableMatches(6379, "c9\t6379/tcp\tcreated");
out.p_other_port = parseDockerPortTableMatches(6377, TABLE);
out.p_empty = parseDockerPortTableMatches(6377, "");
out.p_null = parseDockerPortTableMatches(6377, null);

// ---- P0-4 并存确定性:running 优先 + 表序稳定,5 连跑全等 ----
const five = [];
for (let i = 0; i < 5; i++) five.push(JSON.stringify(parseDockerPortTableMatches(6377, TABLE)));
out.p_coexist_deterministic = five.every((s) => s === five[0]);
out.p_coexist_order = parseDockerPortTableMatches(6377, TABLE);

// ---- 兜底路径:filter 全 0 → 全表救回 / 全 0 → 抛错 ----
try {
  out.detect_filters_zero = await detectRedisContainer(6377);
} catch (e) {
  out.detect_filters_zero = "THREW: " + e.message;
}
try {
  out.detect_all_zero = await detectRedisContainer(6377);
} catch (e) {
  out.detect_all_zero = "THREW: " + e.message;
}
console.log(JSON.stringify(out));
'''


def _run_js_harness(mode: str) -> dict:
    src = CHECK_DEMO_MJS.read_text(encoding="utf-8")
    start = src.index("function parseDockerPortTableMatches")
    end = src.index("[HARD2:FNSPLIT-END]")
    fns = src[start:end]
    harness = (
        "import { spawn } from \"node:child_process\";\n"
        "const DOCKER_TIMEOUT_MS = 8000;\n"
        f"{fns}\n"
        f"{_RUNCMD_STUB_AND_CASES}\n"
    )
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".mjs", delete=False, encoding="utf-8")
    f.write(harness)
    f.close()
    try:
        proc = subprocess.run(
            ["node", f.name, mode],
            capture_output=True, text=True, timeout=20, check=False,
        )
        assert proc.returncode == 0, f"node 桩跑挂(mode={mode}): {proc.stderr[:500]}"
        return json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        os.unlink(f.name)


def test_js_parse_normal_ipv6_expose_only():
    """纯函数:IPv4/IPv6 命中;仅 expose(无宿主映射)不命中;空输入安全。"""
    out = _run_js_harness("filters_zero")
    assert out["p_normal"] == ["c1"], out["p_normal"]
    assert out["p_ipv6"] == ["c6"], out["p_ipv6"]
    assert out["p_expose_only_ignored"] == [], out["p_expose_only_ignored"]
    assert out["p_empty"] == []
    assert out["p_null"] == []


def test_js_full_table_rescues_filter_zero_match():
    """P0-1 兜底:publish/expose 双 0 匹配 → docker ps -a 全表解析救回容器名。"""
    out = _run_js_harness("filters_zero")
    assert out["detect_filters_zero"] == "running-redis", (
        f"全表兜底未救回: {out['detect_filters_zero']}(P0-1 盲区未闭环)"
    )


def test_js_all_zero_raises_clean_error():
    """全 0 匹配 → 干净报错(文案含端口),非异常穿透。"""
    out = _run_js_harness("all_zero")
    assert out["detect_all_zero"].startswith("THREW: 未找到映射宿主端口 6377"), (
        out["detect_all_zero"]
    )


def test_js_coexistence_running_first_and_deterministic():
    """P0-4:同宿主端口两容器并存(exited+running)→ running 优先,5 连跑全等。"""
    out = _run_js_harness("filters_zero")
    assert out["p_coexist_deterministic"] is True, "并存判定 5 连跑不一致(P0-4 确定性破)"
    assert out["p_coexist_order"][0] == "running-redis", (
        f"running 未优先: {out['p_coexist_order']}"
    )
    assert out["p_coexist_order"][1] == "exited-redis", (
        f"组内表序不稳定: {out['p_coexist_order']}"
    )
    assert "mysql-c" not in out["p_coexist_order"], "无关端口容器误命中"


# ============================================================
# 动态层 C(真后端,可选):/api/admin/users 无 token 安全不变量
# ============================================================
def test_real_backend_admin_users_not_open_without_token():
    """真后端(8000 在线时):无 token /api/admin/users 必不可达——AdminAuthMiddleware
    强制 Bearer 是任何环境的安全不变量(task11 批判⑥),⑧ 双探点新判据的活体回归锁。"""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/admin/users", timeout=5) as r:
            status, body = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        pytest.skip("8000 后端不可达(环境受限,非代码问题)")
    open_backdoor = status == 200 or re.search(r"\"code\":\s*\"?0\"?", body)
    assert not open_backdoor, (
        f"无 token /api/admin/users 可达(HTTP {status})——管理端护栏失效,"
        f"⑧ 分支 0 将红: {body[:120]}"
    )


# ============================================================
# 动态层 D(接手新增):盲测 harness 全态锁定
#   tests/_wnextcheckdemohard2_blind.mjs —— ⑧ debugCheck 10 态 + ⑯ 附注 2 态
#   + ② 兜底 3 态,全部截取 check-demo.mjs 原文执行。此处锁「harness 本身全绿」,
#   防止后续改 check-demo 时截取锚点漂移/分支语义回退而无人发现。
# ============================================================
def test_blind_harness_all_states_ok():
    blind = Path(__file__).parent / "_wnextcheckdemohard2_blind.mjs"
    proc = subprocess.run(
        ["node", str(blind)],
        capture_output=True, text=True, timeout=120, check=False,
        cwd=str(blind.parent),
    )
    assert proc.returncode == 0, (
        f"盲测 harness 有红态/异常: rc={proc.returncode}\n"
        f"stdout={proc.stdout[-2500:]}\nstderr={proc.stderr[-800:]}"
    )
    assert "BLIND-ALL-OK" in proc.stdout, proc.stdout[-500:]
    # 15 态(⑧10 + ⑯2 + ②3)一态不许少
    assert proc.stdout.count("PASS [") == 15, (
        f"盲测态数量漂移(应 15): {proc.stdout[-500:]}"
    )
