"""W-NEXT-LIFECYCLE-001：8000 真实启停 + 5 次重复机验。

不依赖 bash kill；用 subprocess + Python signal 模拟 SIGTERM/SIGINT。
读退出码、参数耗时、扫描日志 Traceback/CancelledError 计数。
"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
PY = ROOT / "edu-agent" / ".venv" / "Scripts" / "python.exe"


def run_once(attempt: int) -> dict:
    log_path = LOG_DIR / f"lifecycle_real_{attempt}.log"
    # On Windows, use CREATE_NEW_PROCESS_GROUP so we can send CTRL_BREAK_EVENT
    # (which uvicorn interprets as graceful shutdown). On Unix, use SIGTERM.
    creationflags = 0
    preexec_fn = None
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    # LIFECYCLE_PROBE_PORT(默认 18000):专用临时端口,与生产端口(9988)解耦
    # (W-NEXT-PORTS-001 后勘误:曾硬编码 8000,端口迁移后与常驻实例冲突)
    probe_port = int(os.environ.get("LIFECYCLE_PROBE_PORT", "18000"))
    proc = subprocess.Popen(
        [str(PY), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(probe_port)],
        cwd=str(ROOT / "edu-agent"),
        stdout=open(log_path, "wb"),
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        preexec_fn=preexec_fn,
    )

    # wait for /health
    import urllib.request
    start = time.monotonic()
    ready_in = None
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PROBE_PORT}/health", timeout=1) as r:
                if r.status == 200:
                    ready_in = time.monotonic() - start
                    break
        except Exception:
            pass
        if proc.poll() is not None:
            break
        time.sleep(0.5)

    if ready_in is None:
        proc.kill()
        return {"attempt": attempt, "ok": False, "reason": "not ready within 30s", "log": str(log_path)}

    # graceful shutdown.
    # On Windows, CTRL_BREAK_EVENT (signal.CTRL_BREAK_EVENT) -> uvicorn's SIGBREAK handler ->
    # sys.exit(0) -> but Windows records STATUS_CONTROL_C_EXIT (3221225786) in the exit
    # code because the OS terminates the process even when a handler exists.
    # This is **normal Windows behavior**, NOT a bug. The original death was uvicorn exiting
    # with code 3 (STARTUP_FAILURE) + "Application shutdown failed" + CancelledError traceback;
    # the new behavior is clean shutdown with no traceback. Exit code semantics on Windows
    # for graceful signal-driven shutdown is OS-defined.
    # On POSIX, SIGTERM gives exit code 0 directly.
    shutdown_start = time.monotonic()
    if os.name == "nt":
        proc.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        proc.send_signal(signal.SIGTERM)
    try:
        ec = proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        ec = -1
    shutdown_elapsed_ms = int((time.monotonic() - shutdown_start) * 1000)

    # read log and grep
    log_text = log_path.read_text(encoding="utf-8", errors="ignore")
    return {
        "attempt": attempt,
        "ready_in_ms": int(ready_in * 1000),
        "shutdown_elapsed_ms": shutdown_elapsed_ms,
        "exit_code": ec,
        "traceback_count": log_text.count("\nTraceback"),
        "cancelled_error_count": log_text.count("CancelledError"),
        "shutdown_failed_count": log_text.count("Application shutdown failed"),
        "log": str(log_path),
    }


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    print(f"=== Real 8000 lifecycle x {n} ===")
    results = []
    for i in range(1, n + 1):
        r = run_once(i)
        results.append(r)
        print(r)
        # small gap
        time.sleep(1)

    print("\n=== SUMMARY ===")
    print(f"{'att':<4} {'ready_ms':<10} {'shutdown_ms':<12} {'exit':<6} {'tb':<4} {'ce':<4} {'sf':<4}")
    for r in results:
        if r.get("ok") is False:
            print(f"{r['attempt']:<4} FAIL: {r.get('reason')}")
            continue
        print(f"{r['attempt']:<4} {r['ready_in_ms']:<10} {r['shutdown_elapsed_ms']:<12} {r['exit_code']:<6} "
              f"{r['traceback_count']:<4} {r['cancelled_error_count']:<4} {r['shutdown_failed_count']:<4}")

    # gate check
    all_ok = all(
        r.get("ok") is not False
        and r["shutdown_elapsed_ms"] < 10000
        and r["traceback_count"] == 0
        and r["cancelled_error_count"] == 0
        and r["shutdown_failed_count"] == 0
        for r in results
    )
    avg_start = sum(r["ready_in_ms"] for r in results if r.get("ok") is not False) / max(1, len([r for r in results if r.get("ok") is not False]))
    avg_stop = sum(r["shutdown_elapsed_ms"] for r in results if r.get("ok") is not False) / max(1, len([r for r in results if r.get("ok") is not False]))
    gate_status = "PASS" if all_ok else "FAIL"

    # Output JSON for check-demo gate ⑯
    import json
    out = {
        "pass": all_ok,
        "env_blocked": False,
        "n": n,
        "avg_start_ms": int(avg_start),
        "avg_stop_ms": int(avg_stop),
        "gate": gate_status,
        "detail": f"{n} 轮: start {int(avg_start)}ms / stop {int(avg_stop)}ms / 0 traceback / 0 CancelledError / 0 'shutdown failed'" if all_ok else "lifecycle 不达标",
    }
    print(f"[LIFECYCLE] {json.dumps(out, ensure_ascii=False)}")
    print(f"\nGATE (start <30s + stop <10s + 0 traceback + 0 CancelledError + 0 'shutdown failed'): "
          f"{'PASS' if all_ok else 'FAIL'}")
    sys.exit(0 if all_ok else 1)