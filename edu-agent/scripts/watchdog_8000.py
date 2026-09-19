#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""watchdog_8000.py — 8000 uvicorn 看门狗（W-NEXT-STABILITY-001）

背景（取证结论，见 test-reports/WNEXTSTABILITY1-completion-report.md）：
  8000 uvicorn 存在"无声死亡"史——服务中戛然而止、无 shutdown 日志、无 WER 崩溃事件。
  09-18 22:37 死亡=整机异常重启（Kernel-Power 41）；09-19 00:07 / 04:52 两次=外部
  TerminateProcess（killPort/taskkill /F /T 或 agent 会话 job 清理）。不可根除 → 看门狗兜底。

行为契约（任务书）：
  - 每 --interval(默认 30)s 探 GET /health（须 {"status":"ok"}）
  - 连续 --threshold(默认 3) 次失败 → 清 8000 端口僵尸监听（taskkill /F）
    → 按 AGENTS.md 命令式拉起 .venv uvicorn（优先 DETACHED+CREATE_BREAKAWAY_FROM_JOB
      脱离当前 job object，防"会话结束连带杀"）+ 写事件日志
  - pid 文件 logs/watchdog_8000.pid 防重入（存活且命令行含本脚本名 → 拒绝启动）
  - 重启冷却 --cooldown(默认 90)s 防拉起风暴

用法：
  python scripts/watchdog_8000.py                    # 前台守护（默认 30s/3 次）
  python scripts/watchdog_8000.py --interval 15      # 演示窗口：更快检出（杀→恢复约 50~75s）
  python scripts/watchdog_8000.py --once             # 单次检查，健康 exit 0 / 不健康 exit 1（不拉起）
  python scripts/watchdog_8000.py --baseline         # 打印 8000 常驻内存/CUDA 基线（OOM 假说留证据）
  python scripts/watchdog_8000.py --stop             # 停止运行中的看门狗（读 pid 文件）

仅 stdlib；Windows 优先（netstat/taskkill/tasklist/wmic），非 Windows 退化为探活+提示。
不触碰 app/**、config.py、contracts/**（W-NEXT-STABILITY-001 红线）。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent          # edu-agent/
LOG_DIR = REPO_ROOT / "logs"
PID_FILE = LOG_DIR / "watchdog_8000.pid"
EVENT_LOG = LOG_DIR / "watchdog_8000_events.log"
RESTART_LOG = LOG_DIR / "watchdog_8000_restart.log"          # 被拉起 uvicorn 的 stdout/stderr
PORT = 8000
HEALTH_URL = f"http://127.0.0.1:{PORT}/health"
PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
SCRIPT_TAG = "watchdog_8000.py"

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = 0x08000000


def _decode(b) -> str:
    """中文 Windows 外部命令输出可能是 GBK（netstat/tasklist/wmic），utf-8 失败退化 gbk。"""
    if isinstance(b, str):
        return b
    for enc in ("utf-8", "gbk"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace")


def _run_out(cmd: list[str], timeout: int = 15) -> str:
    """capture 字节并安全解码；失败返回空串（调用方按查不到处理）。"""
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return _decode(r.stdout or b"")
    except Exception:
        return ""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_event(msg: str, event_log: Path = EVENT_LOG) -> None:
    """事件日志：一行一事，立即落盘（防再死时丢证）。"""
    try:
        event_log.parent.mkdir(parents=True, exist_ok=True)
        with open(event_log, "a", encoding="utf-8") as f:
            f.write(f"[{now()}] {msg}\n")
    except OSError:
        pass
    print(f"[{now()}] {msg}", flush=True)


# ---------------------------------------------------------------- 探活
def probe_health(timeout: float = 5.0) -> tuple[bool, str]:
    """GET /health，须 200 且 status=ok。连接拒绝/超时/非 ok 均算失败。"""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=timeout) as resp:
            body = resp.read(4096).decode("utf-8", "replace")
        j = json.loads(body)
        if j.get("status") == "ok":
            return True, "ok"
        return False, f"status={j.get('status')!r}"
    except Exception as e:  # URLError/ConnectionRefused/timeout/socket
        return False, f"{type(e).__name__}: {e}"[:200]


# ---------------------------------------------------------------- 端口/进程工具
def find_listener_pid(port: int = PORT) -> int | None:
    """netstat 反查监听 PID（仅 LISTENING）。无监听返回 None。"""
    out = _run_out(["netstat", "-ano", "-p", "tcp"])
    if not out:
        return None
    for line in out.splitlines():
        parts = line.split()
        # TCP    127.0.0.1:8000    0.0.0.0:0    LISTENING    16060
        if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[3].upper() == "LISTENING":
            if parts[1].rsplit(":", 1)[-1] == str(port):
                try:
                    return int(parts[4])
                except ValueError:
                    continue
    return None


def process_cmdline(pid: int) -> str:
    """进程命令行（wmic 优先，退化 PowerShell CIM）。查不到返回空串。"""
    for cmd in (
        ["wmic", "process", "where", f"processid={pid}", "get", "commandline", "/value"],
        ["powershell", "-NoProfile", "-Command",
         f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"],
    ):
        out = _run_out(cmd, timeout=20)
        for ln in out.splitlines():
            ln = ln.strip()
            if ln.startswith("CommandLine="):
                val = ln.split("=", 1)[1].strip()
                if val:
                    return val
            elif ln and ln.lower() not in ("commandline", ""):
                return ln  # powershell 路径
    return ""


def kill_pid(pid: int) -> bool:
    try:
        r = subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------- 拉起
def spawn_uvicorn() -> tuple[bool, str]:
    """按 AGENTS.md 命令式拉起 8000 uvicorn（cwd=edu-agent，.venv python）。

    三级降级：
      1) DETACHED_PROCESS|NEW_GROUP|BREAKAWAY —— 脱离当前 job object，会话结束不连带杀
      2) DETACHED_PROCESS|NEW_GROUP           —— job 禁止 breakaway 时
      3) cmd /c start "" /B（AGENTS.md 原样）  —— 兜底
    返回 (是否已发起, 描述)。
    """
    exe = str(PYTHON) if PYTHON.exists() else sys.executable
    argv = [exe, "-m", "uvicorn", "app.main:app", "--port", str(PORT)]
    try:
        RESTART_LOG.parent.mkdir(parents=True, exist_ok=True)
        out_h = open(RESTART_LOG, "ab")  # 追加，不截断历史
    except OSError:
        out_h = subprocess.DEVNULL
    flags_chain = [
        ("detached+breakaway", DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB),
        ("detached", DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP),
    ]
    for label, flags in flags_chain:
        try:
            subprocess.Popen(argv, cwd=str(REPO_ROOT), stdout=out_h, stderr=out_h,
                             stdin=subprocess.DEVNULL, creationflags=flags,
                             close_fds=False)
            return True, f"spawned via {label}"
        except OSError as e:
            last = f"{label} failed: {e}"
    try:
        subprocess.Popen(["cmd", "/c", "start", "", "/B", *argv],
                         cwd=str(REPO_ROOT), creationflags=CREATE_NO_WINDOW)
        return True, "spawned via cmd start /B"
    except OSError as e:
        return False, f"{last}; cmd start failed: {e}"


# ---------------------------------------------------------------- 监控纯逻辑（可单测）
class Monitor:
    """连续失败计数 → 触发拉起；冷却窗防风暴。feed() 返回动作字符串或 None。"""

    def __init__(self, threshold: int = 3, cooldown: float = 90.0,
                 clock=time.monotonic):
        self.threshold = threshold
        self.cooldown = cooldown
        self.clock = clock
        self.consecutive = 0
        self.last_restart = -1e18

    def feed_ok(self) -> str | None:
        self.consecutive = 0
        return None

    def feed_fail(self) -> str:
        self.consecutive += 1
        if self.consecutive < self.threshold:
            return f"FAIL_{self.consecutive}/{self.threshold}"
        self.consecutive = 0
        t = self.clock()
        if t - self.last_restart < self.cooldown:
            return "RESTART_SKIP_COOLDOWN"
        self.last_restart = t
        return "RESTART"


# ---------------------------------------------------------------- pid 文件防重入
def is_watchdog_alive(pid: int) -> bool:
    """pid 存活且命令行含本脚本名 → 视为另一个看门狗在岗。"""
    if pid <= 0:
        return False
    cmdline = process_cmdline(pid)
    return bool(cmdline) and SCRIPT_TAG in cmdline


def acquire_pid_file(force: bool = False) -> tuple[bool, str]:
    """成功持锁返回 (True, 'acquired')；被在岗看门狗拒绝返回 (False, 原因)。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if PID_FILE.exists():
        try:
            old = int(PID_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            old = 0
        if old and old != os.getpid() and is_watchdog_alive(old):
            if not force:
                return False, f"another watchdog alive pid={old} (用 --stop 停止或 --force 抢占)"
            kill_pid(old)
            log_event(f"WATCHDOG_FORCE_TAKEOVER killed_prev_pid={old}")
        else:
            if old:
                log_event(f"WATCHDOG_STALE_PID_FILE replaced old_pid={old}")
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    return True, "acquired"


def stop_running() -> int:
    if not PID_FILE.exists():
        print("no pid file — watchdog not running")
        return 1
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        print("pid file corrupt")
        return 1
    if kill_pid(pid):
        print(f"stopped watchdog pid={pid}")
        PID_FILE.unlink(missing_ok=True)
        log_event(f"WATCHDOG_STOPPED pid={pid}")
        return 0
    print(f"failed to stop pid={pid}（可能已死）")
    PID_FILE.unlink(missing_ok=True)
    return 1


# ---------------------------------------------------------------- 内存/CUDA 基线
def baseline_line() -> str:
    """一行基线：8000 PID + RSS(MB) + 系统内存占用% + CUDA 显存。供 OOM 假说追踪。"""
    pid = find_listener_pid()
    rss = "?"
    if pid:
        out = _run_out(["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"])
        for row in out.splitlines():
            cols = [c.strip('"') for c in row.split('","')]
            if len(cols) >= 5 and cols[1] == str(pid):
                rss = f"{cols[-1].replace(' K','').replace(',','').strip()}K"
                break
    mem_pct = "?"
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        mem_pct = f"{st.dwMemoryLoad}%"
    except Exception:
        pass
    cuda = "?"
    out = _run_out(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                    "--format=csv,noheader,nounits"], timeout=15)
    cuda = out.strip().splitlines()[0] if out.strip() else "?"
    return f"BASELINE pid={pid} rss={rss} sysmem={mem_pct} cuda_used_total_mib={cuda}"


# ---------------------------------------------------------------- 主循环
def run_loop(interval: float, threshold: int, cooldown: float) -> int:
    ok, why = acquire_pid_file()
    if not ok:
        print(f"refuse to start: {why}")
        return 2
    log_event(f"WATCHDOG_START pid={os.getpid()} interval={interval}s threshold={threshold} cooldown={cooldown}s")
    mon = Monitor(threshold=threshold, cooldown=cooldown)
    cycle = 0
    try:
        while True:
            healthy, detail = probe_health()
            if healthy:
                if mon.consecutive:  # 自愈成功可观测
                    log_event(f"HEALTH_RECOVERED after {mon.consecutive} fails")
                mon.feed_ok()
            else:
                action = mon.feed_fail()
                listener = find_listener_pid()
                log_event(f"HEALTH_FAIL {action} detail={detail} listener_pid={listener}")
                if action == "RESTART":
                    log_event("RESTART_BEGIN")
                    if listener:
                        if kill_pid(listener):
                            log_event(f"PORT_CLEANUP killed zombie listener pid={listener}")
                            time.sleep(2.0)
                        else:
                            log_event(f"PORT_CLEANUP taskkill failed pid={listener}（继续尝试拉起）")
                    spawned, how = spawn_uvicorn()
                    log_event(f"RESTART_INITIATED ok={spawned} how={how}")
                    if spawned:
                        deadline = time.time() + 60
                        while time.time() < deadline:
                            time.sleep(5)
                            h2, d2 = probe_health(timeout=5)
                            if h2:
                                log_event("RESTART_OK 8000 back to healthy")
                                break
                        else:
                            log_event("RESTART_PENDING 60s 内未回 200（后续循环继续盯）")
            cycle += 1
            if cycle % 10 == 0:  # 每 10 轮采样一次内存基线（默认约 5 分钟）
                log_event(baseline_line())
            time.sleep(interval)
    except KeyboardInterrupt:
        log_event(f"WATCHDOG_EXIT kb interrupt pid={os.getpid()}")
        PID_FILE.unlink(missing_ok=True)
        return 0
    finally:
        if PID_FILE.exists() and PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
            PID_FILE.unlink(missing_ok=True)


def run_once() -> int:
    healthy, detail = probe_health()
    listener = find_listener_pid()
    print(f"health={'OK' if healthy else 'FAIL'} detail={detail} listener_pid={listener}")
    return 0 if healthy else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="8000 uvicorn watchdog (W-NEXT-STABILITY-001)")
    ap.add_argument("--interval", type=float, default=30.0, help="探活间隔秒（默认 30）")
    ap.add_argument("--threshold", type=int, default=3, help="连续失败次数阈值（默认 3）")
    ap.add_argument("--cooldown", type=float, default=90.0, help="两次拉起最小间隔秒（默认 90）")
    ap.add_argument("--once", action="store_true", help="单次检查，不拉起")
    ap.add_argument("--baseline", action="store_true", help="打印内存/CUDA 基线一行")
    ap.add_argument("--stop", action="store_true", help="停止在岗看门狗")
    ap.add_argument("--force", action="store_true", help="抢占式替换在岗看门狗")
    args = ap.parse_args(argv)

    if args.stop:
        return stop_running()
    if args.baseline:
        line = baseline_line()
        print(line)
        log_event(line)
        return 0
    if args.once:
        return run_once()
    if sys.platform != "win32":
        print("非 Windows：仅支持 --once / --baseline（拉起命令按 AGENTS.md 为 Windows 形态）")
        return run_once()
    return run_loop(args.interval, args.threshold, args.cooldown)


if __name__ == "__main__":
    sys.exit(main())
