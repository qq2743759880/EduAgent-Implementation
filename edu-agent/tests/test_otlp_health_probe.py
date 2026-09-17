# -*- coding: utf-8 -*-
"""W-NEXT-OTLP-001 单测 —— OtlpExporter / init_otlp() / probe 三层守门。

覆盖 GWT 5 步中的 OTLP1-G2/G3/G4 实证：
- test_disabled_endpoint_passes —— endpoint 空 → state=disabled，安全缺省 PASS
- test_ssrf_rejected_blocks_untrusted_host —— IMDS/外网 host 必拒
- test_tcp_probe_healthy_local —— 本地白名单 host:port 真 TCP 探活（用 127.0.0.1:0 假端口验失败路径）
- test_init_otlp_idempotent_and_no_exc —— init_otlp() 多次调用幂等 + 不抛
- test_trace_chat_entry_no_throw_disabled —— trace_chat_entry 在 disabled 模式零开销不抛
- test_settings_otlp_fields_exist —— 4 个 OTLP 字段在 Settings 类已注册（防 Pydantic 拒启）

设计依据：
- Mimosa ① host 写死 127.0.0.1；本测试用 127.0.0.1 任意空闲端口做 TCP 探活实证
- OTLP exporter 是 lifespan 接入点，状态需可注入：set_otlp_exporter() 用于测试隔离
- 单测不依赖 8000/DB；纯 unit
"""
from __future__ import annotations

import socket
import threading

import pytest


# ============================================================
# fixtures：测试隔离 OtlpExporter 单例
# ============================================================
@pytest.fixture(autouse=True)
def _reset_otlp_singleton():
    """每个测试前后：恢复默认 OtlpExporter 单例，避免状态泄漏。"""
    from app.observability import otlp as _otlp_mod
    original = _otlp_mod._default_exporter
    yield
    _otlp_mod._default_exporter = original


@pytest.fixture
def free_port():
    """拿一个空闲 TCP 端口（127.0.0.1 写死）。返回后端口立即关闭，
    测试代码可立即用同一端口做探活实证（OS 端口复用窗口）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def fake_tcp_server():
    """短时启动一个 127.0.0.1 TCP server；用 contextlib 退出时关闭。"""
    import contextlib
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    server.settimeout(2.0)
    port = server.getsockname()[1]
    try:
        yield ("127.0.0.1", port)
    finally:
        with contextlib.suppress(Exception):
            server.close()


# ============================================================
# test 1: endpoint 空 → disabled 安全缺省 PASS
# ============================================================
def test_disabled_endpoint_passes():
    """OTEL_EXPORTER_OTLP_ENDPOINT 空 → state=disabled，OTLP exporter 零开销。"""
    from app.observability.otlp import OtlpExporter, OTLP_DISABLED

    exp = OtlpExporter(endpoint="", service_name="test")
    state = exp.start()
    assert state == OTLP_DISABLED
    status = exp.status()
    assert status["state"] == OTLP_DISABLED
    assert status["endpoint"] == ""
    assert status["probe_ms"] == 0
    assert status["last_error"] == ""
    # disabled 模式下 export 应直接 no-op 返回 False
    assert exp.export({"name": "noop"}) is False


# ============================================================
# test 2: SSRF 守门阻断 IMDS/外网 host
# ============================================================
def test_ssrf_rejected_blocks_untrusted_host():
    """非白名单 host（IMDS/外网/私网未白名单）必须 state=ssrf_rejected 阻断。"""
    from app.observability.otlp import OtlpExporter, OTLP_SSRF_REJECTED

    # ① AWS IMDS endpoint：SSRF 杀招
    exp1 = OtlpExporter(endpoint="http://169.254.169.254/latest/meta-data")
    state1 = exp1.start()
    assert state1 == OTLP_SSRF_REJECTED, f"IMDS 未被拒: state={state1}"
    assert "SSRF" in exp1._last_error or "169.254" in exp1._last_error

    # ② 公网外网（dashscope 域名不在白名单）
    exp2 = OtlpExporter(endpoint="https://dashscope.aliyuncs.com/otlp")
    state2 = exp2.start()
    assert state2 == OTLP_SSRF_REJECTED, f"公网域名未被拒: state={state2}"

    # ③ RFC1918 私网但不在白名单（10.5.5.5）
    exp3 = OtlpExporter(endpoint="http://10.5.5.5:4318")
    state3 = exp3.start()
    assert state3 == OTLP_SSRF_REJECTED, f"未白名单私网未被拒: state={state3}"

    # ④ scheme = file://
    exp4 = OtlpExporter(endpoint="file:///etc/passwd")
    state4 = exp4.start()
    assert state4 == OTLP_SSRF_REJECTED, f"file scheme 未被拒: state={state4}"


# ============================================================
# test 3: 127.0.0.1 白名单内 host + TCP 探活路径
# ============================================================
def test_tcp_probe_healthy_local(fake_tcp_server):
    """白名单 127.0.0.1 + 真 TCP server 在线 → state=healthy 探活通过。"""
    from app.observability.otlp import OtlpExporter, OTLP_HEALTHY

    host, port = fake_tcp_server
    endpoint = f"http://{host}:{port}"
    exp = OtlpExporter(endpoint=endpoint, service_name="test", timeout_s=1.0)
    state = exp.start()
    assert state == OTLP_HEALTHY, f"白名单 127.0.0.1 真在线未被认 healthy: state={state} last_error={exp._last_error}"
    status = exp.status()
    assert status["state"] == OTLP_HEALTHY
    assert status["endpoint"] == endpoint
    assert status["probe_ms"] >= 0
    assert status["last_error"] == ""


def test_tcp_probe_failed_local_unbound_port(free_port):
    """白名单内 127.0.0.1 但端口未 bind → probe 失败 → state 兜底 disabled_probe。"""
    from app.observability.otlp import OtlpExporter, OTLP_DISABLED_PROBE

    # 端口 free_port 已被 bind 后立即 close，OS 端口复用窗口里大概率没人监听
    endpoint = f"http://127.0.0.1:{free_port}"
    exp = OtlpExporter(endpoint=endpoint, service_name="test", timeout_s=0.5)
    state = exp.start()
    # 即便探活失败，OTLP exporter 仍启用（OTel collector 晚启动场景）→ disabled_probe
    assert state == OTLP_DISABLED_PROBE
    status = exp.status()
    assert status["last_error"] != "" or status["probe_ms"] > 0


# ============================================================
# test 4: init_otlp() 多次调用幂等 + 不抛
# ============================================================
def test_init_otlp_idempotent_and_no_exc(monkeypatch):
    """init_otlp() 多次调用幂等；任何异常不抛（lifespan 友好）。"""
    from app.observability import otlp as _otlp_mod

    # 清掉 endpoint 防 settings 残留触发真探活
    monkeypatch.setattr(_otlp_mod.settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "")
    # 重置单例到 disabled 状态
    fresh = _otlp_mod.OtlpExporter(endpoint="", service_name="test")
    _otlp_mod.set_otlp_exporter(fresh)

    s1 = _otlp_mod.init_otlp()
    s2 = _otlp_mod.init_otlp()
    s3 = _otlp_mod.init_otlp()
    assert s1 == s2 == s3 == "disabled"


# ============================================================
# test 5: trace_chat_entry / trace_executor_entry 在 disabled 模式零开销
# ============================================================
def test_trace_chat_entry_no_throw_disabled(monkeypatch):
    """disabled 模式下 trace_chat_entry 返回 None、不抛、不打网络。"""
    from app.observability import otlp as _otlp_mod

    monkeypatch.setattr(_otlp_mod.settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "")
    fresh = _otlp_mod.OtlpExporter(endpoint="", service_name="test")
    _otlp_mod.set_otlp_exporter(fresh)
    _otlp_mod.init_otlp()

    out = _otlp_mod.trace_chat_entry(user_id="u1", query="hi", session_id="s1")
    assert out is None
    out2 = _otlp_mod.trace_executor_entry(tool="calc", user_id="u1")
    assert out2 is None


def test_trace_span_emit_buffered(fake_tcp_server):
    """healthy 模式下 trace_* 入环形缓冲，可 get_buffer_snapshot 取到。"""
    from app.observability import otlp as _otlp_mod

    host, port = fake_tcp_server
    exp = _otlp_mod.OtlpExporter(endpoint=f"http://{host}:{port}", service_name="test", timeout_s=1.0)
    state = exp.start()
    # 真 TCP server 在线 → healthy；export() 因真发 HTTP POST 可能失败（server 不答 HTTP），
    # 但 envelope 已写入环形缓冲，可断言 buffer_len ≥ 1
    assert state == "healthy"
    exp.trace_chat_entry(user_id="u1", query="hi")
    snap = exp.get_buffer_snapshot(10)
    assert len(snap) >= 1
    # envelope 形态验证
    env = snap[-1]
    assert "resourceSpans" in env
    rs0 = env["resourceSpans"][0]
    assert rs0["resource"]["attributes"][0]["value"]["stringValue"] == "test"
    spans = rs0["scopeSpans"][0]["spans"]
    assert spans[0]["name"] == "chat.entry"


# ============================================================
# test 6: Settings 类 OTLP 字段已注册（防 Pydantic 拒启）
# ============================================================
def test_settings_otlp_fields_exist():
    """Settings 类 OTLP_* 字段已注册，pydantic 不会拒启。"""
    from app.config import Settings

    fields = Settings.model_fields
    for name in [
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_SERVICE_NAME",
        "OTEL_EXPORTER_OTLP_TIMEOUT_S",
        "OTEL_EXPORTER_OTLP_PROBE_ON_START",
    ]:
        assert name in fields, f"Settings 缺字段: {name}"
    # 默认值验证
    s = Settings()
    assert s.OTEL_EXPORTER_OTLP_ENDPOINT == ""
    assert s.OTEL_SERVICE_NAME == "edu-agent"
    assert s.OTEL_EXPORTER_OTLP_TIMEOUT_S == 2.0
    assert s.OTEL_EXPORTER_OTLP_PROBE_ON_START is True


# ============================================================
# test 7: probe 脚本可独立运行 + 输出 [OTLP] JSON
# ============================================================
def test_probe_script_outputs_json(monkeypatch, capsys):
    """otlp_health_probe.py 在 disabled 配置下输出 [OTLP] {state:disabled}。"""
    import subprocess
    import sys as _sys
    import os as _os

    HERE = _os.path.dirname(_os.path.abspath(__file__))
    REPO = _os.path.abspath(_os.path.join(HERE, ".."))
    probe = _os.path.join(REPO, "scripts", "eval", "otlp_health_probe.py")
    # 子进程默认 OTEL_EXPORTER_OTLP_ENDPOINT 空 → 走 disabled 分支
    env = {**_os.environ, "OTEL_EXPORTER_OTLP_ENDPOINT": ""}
    r = subprocess.run(
        [_sys.executable, probe], capture_output=True, text=True, env=env,
        cwd=REPO, timeout=15,
    )
    assert r.returncode == 0, f"probe exit={r.returncode} stderr={r.stderr}"
    import re as _re
    import json as _json
    m = _re.search(r"\[OTLP\]\s*(\{.*\})", r.stdout)
    assert m, f"未输出 [OTLP] JSON: stdout={r.stdout!r}"
    j = _json.loads(m.group(1))
    assert j["state"] == "disabled"
    assert j["env_blocked"] is False


def test_probe_script_ssrf_block(monkeypatch, capsys):
    """otlp_health_probe.py 在 endpoint=公网时输出 ssrf_rejected。"""
    import subprocess
    import sys as _sys
    import os as _os

    HERE = _os.path.dirname(_os.path.abspath(__file__))
    REPO = _os.path.abspath(_os.path.join(HERE, ".."))
    probe = _os.path.join(REPO, "scripts", "eval", "otlp_health_probe.py")
    # 公网 endpoint → SSRF 守门必拒
    r = subprocess.run(
        [_sys.executable, probe, "--endpoint", "http://169.254.169.254/latest/meta-data"],
        capture_output=True, text=True, cwd=REPO, timeout=15,
    )
    assert r.returncode == 0, f"probe exit={r.returncode}"
    import re as _re
    import json as _json
    m = _re.search(r"\[OTLP\]\s*(\{.*\})", r.stdout)
    assert m, f"未输出 [OTLP] JSON: stdout={r.stdout!r}"
    j = _json.loads(m.group(1))
    assert j["state"] == "ssrf_rejected"
    assert j["ssrf_ok"] is False


# ============================================================
# test 8: OtlpExporter.shutdown() 不抛
# ============================================================
def test_shutdown_does_not_throw():
    from app.observability.otlp import OtlpExporter

    exp = OtlpExporter(endpoint="http://127.0.0.1:4318", service_name="test")
    exp.start()
    exp.shutdown()
    # 二次调用幂等
    exp.shutdown()
    s = exp.status()
    assert s["state"] == "disabled"
    assert s["buffer_len"] == 0


# ============================================================
# test 9: probe 用例白名单 host 但端口空闲 → probe_failed 兜底（disabled_probe）
# ============================================================
def test_probe_failed_local_unbound_port(free_port):
    """127.0.0.1 + 真空闲端口 → 探活失败但 OTLP 仍兜底 disabled_probe。"""
    from app.observability import otlp as _otlp_mod
    exp = _otlp_mod.OtlpExporter(
        endpoint=f"http://127.0.0.1:{free_port}",
        service_name="test",
        timeout_s=0.3,
    )
    state = exp.start()
    # 真空闲端口大概率没人监听（OS 端口复用窗口内）→ probe 失败但保留 endpoint
    assert state in ("probe_skipped", "probe_failed"), f"unexpected state={state}"
    # endpoint 仍在，OTel collector 晚启动场景友好
    s = exp.status()
    assert s["endpoint"] == f"http://127.0.0.1:{free_port}"


# ============================================================
# test 10: probe_on_start=False 跳过启动探活
# ============================================================
def test_probe_on_start_false_skips_probe(fake_tcp_server, monkeypatch):
    """OTEL_EXPORTER_OTLP_PROBE_ON_START=false → 跳过 TCP 探活，state=disabled_probe。"""
    from app.observability import otlp as _otlp_mod
    monkeypatch.setattr(_otlp_mod.settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:14318")
    monkeypatch.setattr(_otlp_mod.settings, "OTEL_EXPORTER_OTLP_PROBE_ON_START", False)

    exp = _otlp_mod.OtlpExporter(endpoint="http://127.0.0.1:14318", service_name="test")
    state = exp.start()
    assert state == "probe_skipped"
    # probe_ms 应为 0（未真探活）
    s = exp.status()
    assert s["probe_ms"] == 0
