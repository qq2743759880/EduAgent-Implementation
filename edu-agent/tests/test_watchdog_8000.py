# -*- coding: utf-8 -*-
"""W-NEXT-STABILITY-001 watchdog_8000.py 单元测试。

覆盖：Monitor 连败触发/冷却防风暴/成功重置；pid 文件防重入（在岗拒绝/陈旧接管）；
netstat 监听解析；--once 模式退出码。不发真实网络请求（探活函数打桩）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import watchdog_8000 as wd  # noqa: E402


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


# ---------------------------------------------------------------- Monitor
def test_monitor_triggers_restart_exactly_at_threshold():
    clk = FakeClock()
    m = wd.Monitor(threshold=3, cooldown=90.0, clock=clk)
    assert m.feed_fail() == "FAIL_1/3"
    assert m.feed_fail() == "FAIL_2/3"
    assert m.feed_fail() == "RESTART"


def test_monitor_ok_resets_counter():
    clk = FakeClock()
    m = wd.Monitor(threshold=3, cooldown=90.0, clock=clk)
    m.feed_fail()
    m.feed_fail()
    assert m.feed_ok() is None
    assert m.consecutive == 0
    assert m.feed_fail() == "FAIL_1/3"  # 重新计数而非 FAIL_3/3


def test_monitor_cooldown_blocks_spawn_storm():
    clk = FakeClock()
    m = wd.Monitor(threshold=3, cooldown=90.0, clock=clk)
    assert m.feed_fail() == "FAIL_1/3"
    assert m.feed_fail() == "FAIL_2/3"
    assert m.feed_fail() == "RESTART"          # t=1000 触发
    clk.advance(30)                             # t=1030，冷却窗内
    assert m.feed_fail() == "FAIL_1/3"
    assert m.feed_fail() == "FAIL_2/3"
    assert m.feed_fail() == "RESTART_SKIP_COOLDOWN"
    clk.advance(120)                            # t=1150，冷却窗已过
    assert m.feed_fail() == "FAIL_1/3"
    assert m.feed_fail() == "FAIL_2/3"
    assert m.feed_fail() == "RESTART"


# ---------------------------------------------------------------- pid 文件防重入
def test_pid_file_takeover_stale(tmp_path, monkeypatch):
    pid_file = tmp_path / "watchdog_8000.pid"
    pid_file.write_text("999999")  # 不存在的 pid
    monkeypatch.setattr(wd, "PID_FILE", pid_file)
    monkeypatch.setattr(wd, "is_watchdog_alive", lambda p: False)
    monkeypatch.setattr(wd, "log_event", lambda msg, event_log=wd.EVENT_LOG: None)
    ok, why = wd.acquire_pid_file()
    assert ok and why == "acquired"
    assert pid_file.read_text() == str(os.getpid())


def test_pid_file_refuses_live_watchdog(tmp_path, monkeypatch):
    pid_file = tmp_path / "watchdog_8000.pid"
    pid_file.write_text("424242")
    monkeypatch.setattr(wd, "PID_FILE", pid_file)
    monkeypatch.setattr(wd, "is_watchdog_alive", lambda p: True)
    ok, why = wd.acquire_pid_file()
    assert not ok
    assert "another watchdog alive" in why


def test_pid_file_force_kills_prev(tmp_path, monkeypatch):
    pid_file = tmp_path / "watchdog_8000.pid"
    pid_file.write_text("424242")
    monkeypatch.setattr(wd, "PID_FILE", pid_file)
    monkeypatch.setattr(wd, "is_watchdog_alive", lambda p: True)
    killed = []
    monkeypatch.setattr(wd, "kill_pid", lambda p: killed.append(p) or True)
    events = []
    monkeypatch.setattr(wd, "log_event", lambda msg, event_log=wd.EVENT_LOG: events.append(msg))
    ok, _ = wd.acquire_pid_file(force=True)
    assert ok and killed == [424242]
    assert any("FORCE_TAKEOVER" in e for e in events)


SCRIPT_DIR = REPO / "scripts"


def test_is_watchdog_alive_requires_script_tag(monkeypatch):
    monkeypatch.setattr(wd, "process_cmdline", lambda p: "python -m uvicorn app.main:app --port 8000")
    assert wd.is_watchdog_alive(123) is False  # uvicorn 自身不算看门狗
    monkeypatch.setattr(wd, "process_cmdline", lambda p: f"python {SCRIPT_DIR / 'watchdog_8000.py'} --interval 30")
    assert wd.is_watchdog_alive(123) is True


# ---------------------------------------------------------------- netstat 解析
def test_find_listener_pid_parses_netstat(monkeypatch):
    canned = (
        "\n  TCP    127.0.0.1:8000         0.0.0.0:0              LISTENING       16060\n"
        "  TCP    127.0.0.1:3000         0.0.0.0:0              LISTENING       28124\n"
        "  TCP    127.0.0.1:8000         127.0.0.1:52341        ESTABLISHED     16060\n"
    ).encode("gbk")  # 中文 Windows netstat 实际为 GBK 字节流

    class R:
        stdout = canned

    monkeypatch.setattr(wd.subprocess, "run", lambda *a, **k: R())
    assert wd.find_listener_pid(8000) == 16060
    assert wd.find_listener_pid(9999) is None


# ---------------------------------------------------------------- --once 模式
def test_once_mode_exit_codes(monkeypatch, capsys):
    monkeypatch.setattr(wd, "probe_health", lambda timeout=5.0: (True, "ok"))
    monkeypatch.setattr(wd, "find_listener_pid", lambda port=8000: 1234)
    assert wd.run_once() == 0
    monkeypatch.setattr(wd, "probe_health", lambda timeout=5.0: (False, "ConnectionRefusedError"))
    assert wd.run_once() == 1


# ---------------------------------------------------------------- 探活契约
def test_probe_health_requires_status_ok(monkeypatch):
    class RespOk:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return b'{"status":"ok","app":"EduAgent","version":"0.3.0"}'

    monkeypatch.setattr(wd.urllib.request, "urlopen", lambda url, timeout: RespOk())
    ok, detail = wd.probe_health()
    assert ok and detail == "ok"

    class RespBad:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return b'{"status":"degraded"}'

    monkeypatch.setattr(wd.urllib.request, "urlopen", lambda url, timeout: RespBad())
    ok, detail = wd.probe_health()
    assert not ok and "degraded" in detail
